"""
S3.3 — Extract text + tables from filing.pdf using Azure Document Intelligence
(prebuilt-layout model, Markdown output) → backend/data/filing_di.md

Run once:  python di_extract.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat

load_dotenv()

ENDPOINT = os.environ["AZURE_DOCINTEL_ENDPOINT"]
KEY = os.environ["AZURE_DOCINTEL_KEY"]

PDF_PATH = Path(__file__).parent / "data" / "filing.pdf"
OUT_PATH = Path(__file__).parent / "data" / "filing_di.md"


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    print(f"Reading {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.0f} KB) …")

    client = DocumentIntelligenceClient(endpoint=ENDPOINT, credential=AzureKeyCredential(KEY))

    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    print("Sending to Document Intelligence (prebuilt-layout) — this takes ~1–2 minutes …")
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=pdf_bytes),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    result = poller.result()

    markdown = result.content
    OUT_PATH.write_text(markdown, encoding="utf-8")

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Done. Saved {size_kb:.0f} KB -> {OUT_PATH}")
    print(f"Total pages processed: {len(result.pages)}")


if __name__ == "__main__":
    main()
