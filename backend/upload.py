"""
upload.py — PDF upload pipeline: DI extract → PII redact → chunk → embed → index.
Called by the POST /upload endpoint in main.py.

The uploaded chunks land in filingsiq-pipeline-index with year="upload".
Any previously uploaded chunks (year="upload") are deleted before indexing the new doc,
so only one uploaded document is active at a time.
"""

import os
import time

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI

UPLOAD_YEAR   = "upload"
CHUNK_CHARS   = 2000
OVERLAP_CHARS = 200
EMBED_BATCH   = 16
UPLOAD_BATCH  = 50
PII_CHUNK     = 5000
PII_BATCH     = 5      # F0 tier max docs per request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_CHARS])
        start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def _embed(client: AzureOpenAI, deployment: str, chunks: list[str]) -> list[list[float]]:
    embeddings = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        while True:
            try:
                resp = client.embeddings.create(model=deployment, input=batch)
                embeddings.extend([item.embedding for item in resp.data])
                break
            except Exception as exc:
                if "rate" in str(exc).lower():
                    time.sleep(15)
                else:
                    raise
    return embeddings


def _di_extract(pdf_bytes: bytes) -> str:
    """Send PDF bytes to Azure Document Intelligence → return Markdown."""
    client = DocumentIntelligenceClient(
        endpoint=os.environ["AZURE_DOCINTEL_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_DOCINTEL_KEY"]),
    )
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=pdf_bytes),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    return poller.result().content


def _pii_redact(text: str) -> str:
    """Redact PII entities in text using Azure AI Language (F0 tier aware)."""
    client = TextAnalyticsClient(
        endpoint=os.environ["AZURE_LANGUAGE_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_LANGUAGE_KEY"]),
    )
    pieces = [text[i : i + PII_CHUNK] for i in range(0, len(text), PII_CHUNK)]
    redacted = []

    for i in range(0, len(pieces), PII_BATCH):
        batch   = pieces[i : i + PII_BATCH]
        results = client.recognize_pii_entities(batch, language="en")

        for piece, result in zip(batch, results):
            if result.is_error:
                redacted.append(piece)
            else:
                spans = sorted(
                    [(e.offset, e.length, e.category) for e in result.entities],
                    key=lambda x: x[0],
                    reverse=True,
                )
                for offset, length, category in spans:
                    piece = piece[:offset] + f"[{category.upper()}]" + piece[offset + length :]
                redacted.append(piece)

        if i + PII_BATCH < len(pieces):
            time.sleep(1.0)  # F0 tier: stay within 1 req/sec

    return "".join(redacted)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_upload(pdf_bytes: bytes) -> dict:
    """
    Full pipeline for an uploaded PDF:
      1. DI extract  → Markdown
      2. PII redact
      3. Chunk
      4. Delete existing upload chunks from the index
      5. Embed
      6. Upload to filingsiq-pipeline-index (year="upload")

    Returns {"chunks": N}.
    """
    pipeline_index = os.environ.get("AZURE_SEARCH_PIPELINE_INDEX_NAME", "filingsiq-pipeline-index")

    # 1. Extract
    markdown = _di_extract(pdf_bytes)

    # 2. Redact
    redacted = _pii_redact(markdown)

    # 3. Chunk
    chunks = _chunk_text(redacted)

    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=pipeline_index,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )

    # 4. Delete any previously uploaded docs (year="upload")
    old_results = list(search_client.search(
        search_text=None,
        filter=f"year eq '{UPLOAD_YEAR}'",
        select=["id"],
        top=1000,
        query_type="simple",
    ))
    if old_results:
        old_ids = [{"id": r["id"]} for r in old_results]
        for i in range(0, len(old_ids), UPLOAD_BATCH):
            search_client.delete_documents(documents=old_ids[i : i + UPLOAD_BATCH])

    # 5. Embed
    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    embeddings = _embed(openai_client, os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"], chunks)

    # 6. Upload
    documents = [
        {"id": f"upload-chunk-{i}", "content": chunk, "embedding": emb, "year": UPLOAD_YEAR}
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    for i in range(0, len(documents), UPLOAD_BATCH):
        search_client.upload_documents(documents=documents[i : i + UPLOAD_BATCH])

    return {"chunks": len(chunks)}
