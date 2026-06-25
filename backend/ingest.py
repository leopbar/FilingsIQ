"""
ingest.py — chunk the filing, embed each chunk, and upload to Azure AI Search.

Run once (or whenever the filing changes):
    python ingest.py
"""

import os
import time

from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHUNK_CHARS = 2000   # ~500 tokens at ~4 chars/token
OVERLAP_CHARS = 200  # ~50-token overlap to avoid cutting sentences cold
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "filing_di_redacted.md")
UPLOAD_BATCH = 50   # documents per upload batch


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping character-based windows."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_chunks(client: AzureOpenAI, deployment: str, chunks: list[str]) -> list[list[float]]:
    """Embed all chunks, batching up to 16 at a time and retrying on rate-limit."""
    embeddings = []
    batch_size = 16

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        print(f"  Embedding chunks {i + 1}–{min(i + batch_size, len(chunks))} / {len(chunks)} …")

        while True:
            try:
                response = client.embeddings.create(model=deployment, input=batch)
                # The SDK returns items sorted by index, so order is preserved.
                embeddings.extend([item.embedding for item in response.data])
                break
            except Exception as exc:
                if "rate" in str(exc).lower():
                    print("    Rate-limited — waiting 15 s …")
                    time.sleep(15)
                else:
                    raise

    return embeddings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ["AZURE_OPENAI_API_VERSION"]
    embedding_deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    print(f"Reading {DATA_FILE} …")
    with open(DATA_FILE, encoding="utf-8") as f:
        text = f.read()
    print(f"  {len(text):,} characters loaded.")

    print(f"Chunking (size={CHUNK_CHARS} chars, overlap={OVERLAP_CHARS} chars) …")
    chunks = chunk_text(text, CHUNK_CHARS, OVERLAP_CHARS)
    print(f"  {len(chunks)} chunks created.")

    print("Embedding …")
    embeddings = embed_chunks(client, embedding_deployment, chunks)

    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key      = os.environ["AZURE_SEARCH_KEY"]
    search_index    = os.environ["AZURE_SEARCH_INDEX_NAME"]

    search_client = SearchClient(
        endpoint=search_endpoint,
        index_name=search_index,
        credential=AzureKeyCredential(search_key),
    )

    documents = [
        {"id": f"chunk-{i}", "content": chunk, "embedding": emb}
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    print(f"Uploading {len(documents)} documents to index '{search_index}' …")
    for i in range(0, len(documents), UPLOAD_BATCH):
        batch = documents[i : i + UPLOAD_BATCH]
        results = search_client.upload_documents(documents=batch)
        failed = [r for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"Upload failed for: {[r.key for r in failed]}")
        print(f"  Uploaded {min(i + UPLOAD_BATCH, len(documents))} / {len(documents)}")

    print("Done.")


if __name__ == "__main__":
    main()
