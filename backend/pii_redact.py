"""
S3.4 — PII detection + redaction via Azure AI Language
Input:  backend/data/filing_di.md   (DI-extracted Markdown)
Output: backend/data/filing_di_redacted.md

Run once: python pii_redact.py
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient

load_dotenv()

ENDPOINT = os.environ["AZURE_LANGUAGE_ENDPOINT"]
KEY = os.environ["AZURE_LANGUAGE_KEY"]

IN_PATH = Path(__file__).parent / "data" / "filing_di.md"
OUT_PATH = Path(__file__).parent / "data" / "filing_di_redacted.md"

CHUNK_SIZE = 5000   # chars per document (API hard limit: 5,120)
BATCH_SIZE = 5      # documents per request (F0 tier max)
BATCH_DELAY = 1.0   # seconds between batches — stays within F0 rate limits


def split_text(text: str) -> list[str]:
    return [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]


def redact(chunk: str, entities) -> str:
    # Replace from end to start so earlier offsets stay valid
    spans = sorted(
        [(e.offset, e.length, e.category) for e in entities],
        key=lambda x: x[0],
        reverse=True,
    )
    for offset, length, category in spans:
        chunk = chunk[:offset] + f"[{category.upper()}]" + chunk[offset + length :]
    return chunk


def main() -> None:
    text = IN_PATH.read_text(encoding="utf-8")
    print(f"Read {len(text):,} chars from {IN_PATH.name}")

    chunks = split_text(text)
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Split into {len(chunks)} chunks -> {total_batches} batch(es) of {BATCH_SIZE}")

    client = TextAnalyticsClient(endpoint=ENDPOINT, credential=AzureKeyCredential(KEY))

    redacted_chunks = []
    total_entities = 0

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} docs) ...", end=" ", flush=True)

        results = client.recognize_pii_entities(batch, language="en")

        for chunk, result in zip(batch, results):
            if result.is_error:
                print(f"\n  Warning: {result.error.message} — chunk kept as-is")
                redacted_chunks.append(chunk)
            else:
                total_entities += len(result.entities)
                redacted_chunks.append(redact(chunk, result.entities))

        print("done")

        if i + BATCH_SIZE < len(chunks):
            time.sleep(BATCH_DELAY)

    redacted_text = "".join(redacted_chunks)
    OUT_PATH.write_text(redacted_text, encoding="utf-8")

    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"\nDone. PII entities redacted: {total_entities}")
    print(f"Saved {size_kb} KB -> {OUT_PATH.name}")


if __name__ == "__main__":
    main()
