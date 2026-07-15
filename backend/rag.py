"""
rag.py — hybrid search (BM25 + vector) via Azure AI Search, then ask GPT-4o.

Usage (quick smoke-test from backend/):
    python rag.py "What were Apple's total net sales in fiscal 2025?"
"""

import logging
import os
import sys
from contextlib import nullcontext

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from openai import AzureOpenAI

from search_filters import build_search_filter

# opentelemetry is only installed in the main app venv, not backend/venv-eval
# (ragas_eval.py imports this module from venv-eval) — degrade to no-op spans
# rather than fail the import when it's absent.
try:
    from opentelemetry import trace

    _tracer = trace.get_tracer(__name__)
except ImportError:
    _tracer = None

logger = logging.getLogger(__name__)


def _span(name: str):
    return _tracer.start_as_current_span(name) if _tracer else nullcontext()


SYSTEM_PROMPT = """\
You are a financial document analyst. Answer the user's question using ONLY
the document excerpts provided below. Do not use prior knowledge.

For each fact you state, cite the excerpt it comes from by writing [1], [2],
etc., matching the source numbers in the excerpts. If the excerpts do not
contain enough information to answer, say so clearly.
"""


def ask(
    question: str,
    top_k: int = 5,
    year: str | None = None,
    ticker: str | None = None,
) -> dict:
    """
    Embed the question, run hybrid search + semantic re-ranking in Azure AI Search,
    call GPT-4o with the top chunks, return answer + sources.

    Args:
        ticker: Optional company ticker filter, e.g. "MSFT".
        year: Optional fiscal year filter, e.g. "FY2023". None means all years.

    Returns:
        {
            "answer": "<GPT-4o answer with inline citations>",
            "sources": ["<chunk text 1>", "<chunk text 2>", ...]
        }
    """
    load_dotenv()

    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    embedding_deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    chat_deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

    # Embed the question
    with _span("embed_question"):
        emb_response = openai_client.embeddings.create(
            model=embedding_deployment, input=[question]
        )
        question_embedding = emb_response.data[0].embedding

    # Use the pipeline index (has all 5 fiscal years; supports year filtering).
    index_name = os.environ.get("AZURE_SEARCH_PIPELINE_INDEX_NAME", "filingsiq-pipeline-index")

    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=index_name,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )
    vector_query = VectorizedQuery(
        vector=question_embedding,
        k_nearest_neighbors=top_k,
        fields="embedding",
    )
    with _span("search_documents") as span:
        results = search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="semantic-config",
            top=top_k,
            select=[
                "content", "ticker", "company_name", "cik", "form_type",
                "fiscal_year", "year", "filing_date", "accession_number", "sec_url",
            ],
            filter=build_search_filter(ticker, year),
        )
        hits = [dict(result) for result in results]
        if span:
            span.set_attribute("rag.ticker_filter", ticker or "none")
            span.set_attribute("rag.year_filter", year or "none")
            span.set_attribute("rag.hits_returned", len(hits))

    if not hits:
        scope = "the selected filings"
        if ticker:
            scope = f"the indexed {ticker.upper()} filings"
        return {
            "answer": f"I could not find relevant excerpts in {scope}.",
            "sources": [],
            "citations": [],
        }

    # Build context block for the prompt
    context_lines = []
    citations = []
    source_texts = []
    for index, hit in enumerate(hits, 1):
        content = str(hit["content"]).strip()
        source_texts.append(content)
        source_ticker = hit.get("ticker") or ("AAPL" if ticker == "AAPL" else "")
        company_name = hit.get("company_name") or (
            "Apple Inc." if source_ticker == "AAPL" else "Uploaded document"
        )
        fiscal_year = hit.get("fiscal_year") or hit.get("year") or ""
        form_type = hit.get("form_type") or ("10-K" if fiscal_year != "upload" else "PDF")
        filing_date = hit.get("filing_date") or ""
        label_parts = [company_name, form_type, fiscal_year]
        label = " · ".join(part for part in label_parts if part and part != "upload")
        context_lines.append(f"[{index}] Source: {label}\n{content}")
        citations.append(
            {
                "source_number": index,
                "ticker": source_ticker,
                "company_name": company_name,
                "form_type": form_type,
                "fiscal_year": fiscal_year,
                "filing_date": filing_date,
                "accession_number": hit.get("accession_number") or "",
                "sec_url": hit.get("sec_url") or "",
                "title": label or f"Source {index}",
            }
        )
    context_block = "\n\n---\n\n".join(context_lines)
    user_message = f"Document excerpts:\n\n{context_block}\n\nQuestion: {question}"

    # Call GPT-4o
    with _span("chat_completion"):
        chat_response = openai_client.chat.completions.create(
            model=chat_deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )

    logger.info(
        "rag.ask completed: ticker_filter=%s year_filter=%s hits=%d answer_chars=%d",
        ticker or "none",
        year or "none",
        len(hits),
        len(chat_response.choices[0].message.content or ""),
    )

    return {
        "answer": chat_response.choices[0].message.content,
        "sources": source_texts,
        "citations": citations,
    }


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "What were Apple's total net sales in fiscal 2025?"
    )
    print(f"Question: {question}\n")
    result = ask(question, ticker="AAPL", year="FY2025")
    print("Answer:\n")
    print(result["answer"])
    print("\n--- Sources used ---")
    for i, src in enumerate(result["sources"], 1):
        preview = src[:200].replace("\n", " ")
        print(f"[{i}] {preview}…")
