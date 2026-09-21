"""SEC filing discovery and background import jobs for the API."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from company_ingest import import_company, list_indexed_companies
from edgar_download import EdgarError, build_filing_manifest, normalize_ticker

MAX_YEARS_PER_IMPORT = 2
_JOB_TTL_SECONDS = 3600

_executor = ThreadPoolExecutor(max_workers=1)  # one import at a time keeps cost bounded
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def list_available_filings(ticker: str) -> list[dict]:
    """10-Ks EDGAR has for `ticker`, flagged with whether each is already indexed."""
    ticker = normalize_ticker(ticker)
    manifest = build_filing_manifest(ticker, count=10)
    indexed = next(
        (set(c["fiscal_years"]) for c in list_indexed_companies() if c["ticker"] == ticker),
        set(),
    )
    return [
        {
            "fiscal_year": m["fiscal_year"],
            "filing_date": m["filing_date"],
            "sec_url": m["sec_url"],
            "indexed": m["fiscal_year"] in indexed,
        }
        for m in manifest
    ]


def _validate_years(fiscal_years: list[str]) -> list[str]:
    years = sorted({y.strip().upper() for y in fiscal_years if y.strip()}, reverse=True)
    if not years:
        raise EdgarError("Select at least one fiscal year.")
    if len(years) > MAX_YEARS_PER_IMPORT:
        raise EdgarError(f"You can import at most {MAX_YEARS_PER_IMPORT} fiscal years at a time.")
    return years


def _prune() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    for job_id in [j for j, v in _jobs.items() if v["finished_at"] and v["finished_at"] < cutoff]:
        del _jobs[job_id]


def start_import(ticker: str, fiscal_years: list[str]) -> dict:
    ticker = normalize_ticker(ticker)
    years = _validate_years(fiscal_years)
    with _lock:
        _prune()
        if any(job["status"] in ("queued", "running") for job in _jobs.values()):
            raise EdgarError("Another import is already running. Please wait for it to finish.")
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {
            "job_id": job_id,
            "ticker": ticker,
            "fiscal_years": years,
            "status": "queued",
            "message": "Queued",
            "result": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }

    def run() -> None:
        def progress(message: str) -> None:
            _jobs[job_id].update(status="running", message=message)

        try:
            progress("Starting")
            result = import_company(ticker, fiscal_years=years, progress=progress)
            _jobs[job_id].update(status="done", message="Import complete", result=result)
        except Exception as exc:  # surfaced to the UI, not swallowed
            _jobs[job_id].update(status="error", message="Import failed", error=str(exc))
        finally:
            _jobs[job_id]["finished_at"] = time.time()

    _executor.submit(run)
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if job is None:
        return None
    return {**job, "elapsed_s": round((job["finished_at"] or time.time()) - job["started_at"], 1)}
