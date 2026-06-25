"""
S3.2 -- Render the Apple 10-K HTML filing from SEC EDGAR to a PDF.

Strategy: download the raw .htm file locally first, then open it with
headless Chromium via a file:// URL. This avoids SEC bot-protection blocking
the headless browser and lets the full 1.5 MB document load from disk before
printing. The iXBRL content is inline in the HTML, so no external JS is needed.

Run once:
    python html_to_pdf.py
Output: backend/data/filing.pdf
"""

import asyncio
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

EDGAR_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/"
    "000032019325000079/aapl-20250927.htm"
)
DATA_DIR = Path(__file__).parent / "data"
HTML_PATH = DATA_DIR / "filing_raw.html"
OUTPUT_PATH = DATA_DIR / "filing.pdf"

HEADERS = {"User-Agent": "FilingsIQ-Portfolio lbarretti@gmail.com"}


def download_html() -> None:
    if HTML_PATH.exists():
        print(f"HTML already on disk ({HTML_PATH.stat().st_size // 1024} KB), skipping download.")
        return
    print("Downloading HTML from SEC EDGAR...")
    req = urllib.request.Request(EDGAR_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp, HTML_PATH.open("wb") as f:
        data = resp.read()
        f.write(data)
    print(f"Downloaded {len(data) // 1024} KB -> {HTML_PATH.name}")


async def render_to_pdf() -> None:
    file_url = HTML_PATH.as_uri()
    print(f"Launching headless Chromium...")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print(f"Opening {HTML_PATH.name} from disk...")
        await page.goto(file_url, wait_until="domcontentloaded", timeout=120_000)

        # Give JS a moment to finish any inline rendering (iXBRL viewers)
        await page.wait_for_timeout(3_000)

        print(f"Rendering to PDF: {OUTPUT_PATH}")
        await page.pdf(
            path=str(OUTPUT_PATH),
            format="A4",
            print_background=True,
            margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"},
        )

        await browser.close()

    size_mb = OUTPUT_PATH.stat().st_size / 1_048_576
    print(f"Done. {OUTPUT_PATH.name} -- {size_mb:.1f} MB")


if __name__ == "__main__":
    download_html()
    asyncio.run(render_to_pdf())
