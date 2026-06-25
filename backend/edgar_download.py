"""
edgar_download.py — fetch 5 years of Apple 10-K filings from EDGAR.

Downloads the primary HTML document for each of the 5 most recent 10-K filings
(FY2021-FY2025), strips HTML to plain text, and saves one file per fiscal year.

Usage:
    python edgar_download.py

Output: backend/data/filings/10k_FY{year}.txt
"""

import os
import re
import time
import requests
from pathlib import Path


HEADERS = {
    # EDGAR terms of service require a descriptive User-Agent with contact email.
    "User-Agent": "FilingsIQ/1.0 lbarretti@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

CIK_PADDED = "0000320193"          # Apple Inc. — zero-padded to 10 digits
CIK_SHORT   = CIK_PADDED.lstrip("0")  # "320193" — used in archive URLs
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK_PADDED}.json"
ARCHIVE_BASE    = "https://www.sec.gov/Archives/edgar/data"
TARGET_COUNT    = 5  # most recent 10-K filings (FY2021-FY2025)

OUT_DIR = Path(__file__).parent / "data" / "filings"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    """Remove HTML markup and decode common entities; collapse excess whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


def get_10k_filings(submissions: dict) -> list[dict]:
    """Return 10-K filing metadata rows from the EDGAR submissions JSON."""
    recent = submissions["filings"]["recent"]
    results = []
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            accession_dashed = recent["accessionNumber"][i]
            results.append({
                "accession": accession_dashed.replace("-", ""),
                "filed": recent["filingDate"][i],
                "report_date": recent["reportDate"][i],
                "primary_doc": recent["primaryDocument"][i],
            })
    return results  # newest first


def fiscal_year(report_date: str) -> int:
    """Parse the fiscal year from reportDate (YYYY-MM-DD).

    Apple's fiscal year ends in late September, so the calendar year of
    reportDate equals the fiscal year number.
    """
    return int(report_date.split("-")[0])


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_filing(filing: dict, fy: int) -> Path:
    """Download one 10-K, strip HTML, write to disk. Returns the output path."""
    out_path = OUT_DIR / f"10k_FY{fy}.txt"
    if out_path.exists():
        size_kb = out_path.stat().st_size // 1024
        print(f"  FY{fy}: already exists ({size_kb} KB), skipping.")
        return out_path

    url = (
        f"{ARCHIVE_BASE}/{CIK_SHORT}"
        f"/{filing['accession']}/{filing['primary_doc']}"
    )
    print(f"  FY{fy}: GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    text = strip_html(resp.text)
    out_path.write_text(text, encoding="utf-8")

    size_kb = out_path.stat().st_size // 1024
    print(f"  FY{fy}: saved {size_kb} KB -> {out_path.name}")

    # EDGAR rate-limit guidance: no more than 10 requests/second.
    time.sleep(0.5)
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Apple Inc. submissions from EDGAR …")
    resp = requests.get(SUBMISSIONS_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    submissions = resp.json()

    company = submissions.get("name", "Unknown")
    print(f"  Company : {company}")
    print(f"  CIK     : {CIK_PADDED}")

    all_10k = get_10k_filings(submissions)
    print(f"  Found {len(all_10k)} 10-K filings in recent history.")

    targets = all_10k[:TARGET_COUNT]
    print(f"\nDownloading {len(targets)} most-recent 10-K filings …")
    for filing in targets:
        fy = fiscal_year(filing["report_date"])
        download_filing(filing, fy)

    print("\nSummary:")
    for path in sorted(OUT_DIR.glob("10k_FY*.txt")):
        size_kb = path.stat().st_size // 1024
        char_count = len(path.read_text(encoding="utf-8"))
        print(f"  {path.name}   {size_kb:>5} KB   {char_count:>9,} chars")

    print("\nDone.")


if __name__ == "__main__":
    main()
