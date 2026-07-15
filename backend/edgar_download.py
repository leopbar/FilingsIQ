"""Resolve any SEC ticker and download its latest 10-K filings from EDGAR.

Usage:
    python edgar_download.py MSFT

Output:
    backend/data/filings/MSFT/manifest.json
    backend/data/filings/MSFT/<accession-number>.txt
"""

import argparse
import html
import json
import os
import re
import time
from pathlib import Path

import requests

from filing_metadata import FilingMetadata


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
TARGET_COUNT = 5
OUT_DIR = Path(__file__).parent / "data" / "filings"


class EdgarError(RuntimeError):
    """A user-facing EDGAR discovery or download error."""


def _headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get(
            "SEC_USER_AGENT", "FilingsIQ/1.0 lbarretti@gmail.com"
        ),
        "Accept-Encoding": "gzip, deflate",
    }


def _get_json(url: str, timeout: int = 30) -> dict:
    response = requests.get(url, headers=_headers(), timeout=timeout)
    response.raise_for_status()
    return response.json()


def normalize_ticker(ticker: str) -> str:
    value = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.-]{1,10}", value):
        raise EdgarError("Ticker must contain 1–10 letters, numbers, periods, or hyphens.")
    return value


def resolve_ticker(ticker: str) -> dict[str, str]:
    """Resolve a ticker to the SEC's ten-digit CIK and conformed company name."""
    normalized = normalize_ticker(ticker)
    companies = _get_json(TICKERS_URL)
    for company in companies.values():
        if str(company["ticker"]).upper() == normalized:
            return {
                "ticker": normalized,
                "company_name": str(company["title"]),
                "cik": str(company["cik_str"]).zfill(10),
            }
    raise EdgarError(f"Ticker '{normalized}' was not found in the SEC company list.")


def _recent_rows(submissions: dict) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    return [
        {name: values[index] for name, values in recent.items() if index < len(values)}
        for index in range(len(forms))
    ]


def build_filing_manifest(ticker: str, count: int = TARGET_COUNT) -> list[dict[str, str]]:
    """Return metadata for the newest available 10-K filings for one ticker."""
    if not 1 <= count <= 10:
        raise EdgarError("Filing count must be between 1 and 10.")

    company = resolve_ticker(ticker)
    submissions = _get_json(
        f"{SUBMISSIONS_BASE}/CIK{company['cik']}.json"
    )
    company_name = str(submissions.get("name") or company["company_name"])
    cik_short = company["cik"].lstrip("0") or "0"
    manifest: list[dict[str, str]] = []

    for row in _recent_rows(submissions):
        if row.get("form") != "10-K":
            continue
        report_date = str(row.get("reportDate", ""))
        accession_number = str(row.get("accessionNumber", ""))
        primary_document = str(row.get("primaryDocument", ""))
        if not report_date or not accession_number or not primary_document:
            continue

        accession_compact = accession_number.replace("-", "")
        sec_url = (
            f"{ARCHIVE_BASE}/{cik_short}/{accession_compact}/{primary_document}"
        )
        metadata = FilingMetadata(
            ticker=company["ticker"],
            company_name=company_name,
            cik=company["cik"],
            form_type="10-K",
            fiscal_year=f"FY{report_date[:4]}",
            filing_date=str(row.get("filingDate", "")),
            accession_number=accession_number,
            sec_url=sec_url,
        )
        manifest.append(
            {
                **metadata.as_search_fields(),
                "primary_document": primary_document,
            }
        )
        if len(manifest) == count:
            break

    if not manifest:
        raise EdgarError(f"No 10-K filings were found for ticker '{company['ticker']}'.")
    return manifest


def strip_html(source: str) -> str:
    """Convert filing HTML to readable plain text without external parser dependencies."""
    source = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", source)
    source = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    source = html.unescape(source)
    source = re.sub(r"[ \t]+", " ", source)
    source = re.sub(r"\n\s*\n\s*\n+", "\n\n", source)
    return source.strip()


def fetch_filing_text(filing: dict[str, str]) -> str:
    response = requests.get(filing["sec_url"], headers=_headers(), timeout=60)
    response.raise_for_status()
    time.sleep(0.2)
    return strip_html(response.text)


def download_company_filings(
    ticker: str,
    count: int = TARGET_COUNT,
    out_dir: Path = OUT_DIR,
) -> list[dict[str, str]]:
    """Download filings and persist a machine-readable company manifest."""
    manifest = build_filing_manifest(ticker, count=count)
    company_dir = out_dir / manifest[0]["ticker"]
    company_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, str]] = []
    for filing in manifest:
        path = company_dir / f"{filing['accession_number']}.txt"
        if not path.exists():
            path.write_text(fetch_filing_text(filing), encoding="utf-8")
        saved.append({**filing, "file_path": str(path)})

    manifest_path = company_dir / "manifest.json"
    manifest_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a company's latest SEC 10-K filings.")
    parser.add_argument("ticker", help="SEC-listed ticker, for example MSFT")
    parser.add_argument("--count", type=int, default=TARGET_COUNT)
    args = parser.parse_args()

    filings = download_company_filings(args.ticker, count=args.count)
    first = filings[0]
    print(f"Downloaded {len(filings)} filings for {first['company_name']} ({first['ticker']}).")
    for filing in filings:
        print(f"  {filing['fiscal_year']}  {filing['filing_date']}  {filing['file_path']}")


if __name__ == "__main__":
    main()
