"""Persistent multi-company SEC 10-K ingestion for the FilingsIQ API."""

import logging
import os
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from openai import AzureOpenAI

from edgar_download import download_company_filings, normalize_ticker
from search_schema import ensure_search_index

logger = logging.getLogger(__name__)

CHUNK_CHARS = 2000
OVERLAP_CHARS = 200
EMBED_BATCH = 16
UPLOAD_BATCH = 50
SEARCH_PAGE_SIZE = 1000


def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_CHARS])
        start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def _embed(client: AzureOpenAI, deployment: str, chunks: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        while True:
            try:
                response = client.embeddings.create(model=deployment, input=batch)
                embeddings.extend(item.embedding for item in response.data)
                break
            except Exception as exc:
                if "rate" in str(exc).lower() or "429" in str(exc):
                    time.sleep(15)
                else:
                    raise
    return embeddings


def _escape_filter(value: str) -> str:
    return value.replace("'", "''")


def _company_filter(ticker: str, fiscal_years: Optional[Iterable[str]] = None) -> str:
    """Filter matching a company's indexed 10-K chunks, optionally limited to some years."""
    years = sorted(fiscal_years) if fiscal_years else None
    current = f"ticker eq '{_escape_filter(ticker)}' and form_type eq '10-K'"
    if years:
        clause = " or ".join(f"fiscal_year eq '{_escape_filter(y)}'" for y in years)
        current += f" and ({clause})"
    if ticker == "AAPL":
        # S9 migration only: the original 640 Apple chunks predate all metadata.
        legacy = "ticker eq null and year ne 'upload'"
        if years:
            clause = " or ".join(f"year eq '{_escape_filter(y)}'" for y in years)
            legacy += f" and ({clause})"
        return f"({current}) or ({legacy})"
    return current


def _existing_chunk_ids(
    search_client: SearchClient,
    ticker: str,
    fiscal_years: Optional[Iterable[str]] = None,
) -> set[str]:
    """Return the IDs of the chunks currently indexed for a company and its selected years.

    Reading past the first page of results is unreliable without a sortable key, so a
    selection too large for one page is refused instead of replaced from a partial list.
    """
    results = search_client.search(
        search_text="*",
        filter=_company_filter(ticker, fiscal_years),
        select=["id"],
        top=SEARCH_PAGE_SIZE,
        include_total_count=True,
    )
    ids = {row["id"] for row in results}
    total = results.get_count()
    if total != len(ids):
        raise RuntimeError(
            f"{ticker} has {total} chunks in this selection, too many to replace safely "
            f"in one import (limit {SEARCH_PAGE_SIZE}). Nothing was changed."
        )
    return ids


def _delete_chunks(search_client: SearchClient, ids: Iterable[str]) -> None:
    documents = [{"id": chunk_id} for chunk_id in ids]
    for start in range(0, len(documents), UPLOAD_BATCH):
        search_client.delete_documents(documents=documents[start : start + UPLOAD_BATCH])


def _replace_chunks(
    search_client: SearchClient,
    documents: list[dict],
    existing_ids: set[str],
) -> None:
    """Write the new chunks, and remove the ones they supersede only after that succeeds.

    The service can reject an upload, for example when its storage quota is full, and
    that must not cost a company the filings it already has indexed. Chunk IDs are
    deterministic, so re-importing a filing overwrites its chunks in place.
    """
    written: set[str] = set()
    try:
        for start in range(0, len(documents), UPLOAD_BATCH):
            batch = documents[start : start + UPLOAD_BATCH]
            written.update(document["id"] for document in batch)
            results = search_client.upload_documents(documents=batch)
            failed = [result.key for result in results if not result.succeeded]
            if failed:
                raise RuntimeError(f"Azure Search rejected chunk IDs: {failed}")
    except Exception:
        # Remove only what this import added. Chunks that were already indexed stay.
        try:
            _delete_chunks(search_client, written - existing_ids)
        except Exception:
            logger.exception("Could not remove a partial upload; re-raising the original error.")
        raise

    _delete_chunks(search_client, existing_ids - {document["id"] for document in documents})


def import_company(
    ticker: str,
    count: int = 5,
    fiscal_years: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Download, embed, and replace a company's indexed 10-Ks.

    Without `fiscal_years` the company's whole 10-K set is replaced. With it, only
    those fiscal years are replaced and the company's other years are left alone.
    """
    load_dotenv()
    say = progress or (lambda _message: None)
    years = sorted({y.upper() for y in fiscal_years}) if fiscal_years else None
    ticker = normalize_ticker(ticker)
    index_name = os.environ.get("AZURE_SEARCH_PIPELINE_INDEX_NAME", "filingsiq-pipeline-index")
    ensure_search_index(
        os.environ["AZURE_SEARCH_ENDPOINT"],
        os.environ["AZURE_SEARCH_KEY"],
        index_name,
    )

    say("Downloading filings from SEC EDGAR")
    filings = download_company_filings(ticker, count=count, fiscal_years=years)
    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    documents: list[dict] = []
    filing_summaries: list[dict] = []

    # Prepare every replacement document before touching the search index.
    for position, filing in enumerate(filings, start=1):
        say(f"Embedding {filing['fiscal_year']} ({position}/{len(filings)})")
        chunks = _chunk_text(Path(filing["file_path"]).read_text(encoding="utf-8"))
        embeddings = _embed(
            openai_client,
            os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            chunks,
        )
        accession_key = filing["accession_number"].replace("-", "")
        metadata = {
            key: filing[key]
            for key in (
                "ticker",
                "company_name",
                "cik",
                "form_type",
                "fiscal_year",
                "filing_date",
                "accession_number",
                "sec_url",
            )
        }
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            documents.append(
                {
                    "id": f"{ticker}-{accession_key}-chunk-{index}",
                    "content": chunk,
                    "embedding": embedding,
                    "year": filing["fiscal_year"],
                    **metadata,
                }
            )
        filing_summaries.append(
            {
                "fiscal_year": filing["fiscal_year"],
                "filing_date": filing["filing_date"],
                "accession_number": filing["accession_number"],
                "sec_url": filing["sec_url"],
                "chunks": len(chunks),
            }
        )

    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=index_name,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )
    say("Writing to the search index")
    existing_ids = _existing_chunk_ids(search_client, ticker, years)
    _replace_chunks(search_client, documents, existing_ids)

    return {
        "ticker": ticker,
        "company_name": filings[0]["company_name"],
        "cik": filings[0]["cik"],
        "filings": filing_summaries,
        "filing_count": len(filings),
        "chunks": len(documents),
        "replaced_chunks": len(existing_ids),
    }


def list_indexed_companies() -> list[dict]:
    """Return company and year options derived from the search index itself."""
    load_dotenv()
    index_name = os.environ.get("AZURE_SEARCH_PIPELINE_INDEX_NAME", "filingsiq-pipeline-index")
    ensure_search_index(
        os.environ["AZURE_SEARCH_ENDPOINT"],
        os.environ["AZURE_SEARCH_KEY"],
        index_name,
    )
    client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=index_name,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )

    facet_results = client.search(search_text="*", top=0, facets=["ticker,count:100"])
    ticker_facets = (facet_results.get_facets() or {}).get("ticker", [])
    companies: list[dict] = []

    for facet in ticker_facets:
        ticker = str(facet["value"])
        rows = list(
            client.search(
                search_text="*",
                filter=f"ticker eq '{_escape_filter(ticker)}'",
                select=[
                    "ticker", "company_name", "cik", "form_type", "fiscal_year",
                    "accession_number",
                ],
                top=1000,
            )
        )
        if not rows:
            continue
        first = rows[0]
        companies.append(
            {
                "ticker": ticker,
                "company_name": first.get("company_name") or ticker,
                "cik": first.get("cik") or "",
                "form_types": sorted({row.get("form_type") for row in rows if row.get("form_type")}),
                "fiscal_years": sorted(
                    {row.get("fiscal_year") for row in rows if row.get("fiscal_year")},
                    reverse=True,
                ),
                "filing_count": len(
                    {row.get("accession_number") for row in rows if row.get("accession_number")}
                ),
                "chunk_count": int(facet["count"]),
                "legacy": False,
            }
        )

    # Temporary S9 compatibility: Apple was indexed before metadata fields existed.
    if not any(company["ticker"] == "AAPL" for company in companies):
        legacy_rows = list(
            client.search(
                search_text="*",
                filter="ticker eq null and year ne 'upload'",
                select=["year"],
                top=1000,
            )
        )
        if legacy_rows:
            years = sorted(
                {row.get("year") for row in legacy_rows if row.get("year")},
                reverse=True,
            )
            companies.append(
                {
                    "ticker": "AAPL",
                    "company_name": "Apple Inc.",
                    "cik": "0000320193",
                    "form_types": ["10-K"],
                    "fiscal_years": years,
                    "filing_count": len(years),
                    "chunk_count": len(legacy_rows),
                    "legacy": True,
                }
            )

    return sorted(companies, key=lambda company: (company["ticker"] != "AAPL", company["ticker"]))
