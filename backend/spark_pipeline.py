"""
spark_pipeline.py — PySpark batch ingestion pipeline for 5 Apple 10-K filings.

Architecture (hybrid — see ADR-004):
  - Spark DataFrames manage the job manifest and results.
  - Driver-side concurrent.futures executes per-filing work in parallel.
  - Python worker subprocesses are not used (Windows + Python 3.12 + PySpark 3.5.3
    incompatibility confirmed in S5.1; on Azure Databricks the same process_filing
    function would run via mapInPandas).

Targets filingsiq-pipeline-index (separate from the production filingsiq-index)
so the RAG chat is not affected.

Usage:
    python spark_pipeline.py
"""

import os
import time
import concurrent.futures
from pathlib import Path

import mlflow
import pandas as pd
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PIPELINE_INDEX = "filingsiq-pipeline-index"
FILINGS_DIR    = Path(__file__).parent / "data" / "filings"
CHUNK_CHARS    = 2000
OVERLAP_CHARS  = 200
UPLOAD_BATCH   = 50
VECTOR_DIM     = 1536
MAX_WORKERS    = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_CHARS])
        start += CHUNK_CHARS - OVERLAP_CHARS
    return chunks


def embed_chunks(client: AzureOpenAI, deployment: str, chunks: list[str]) -> list[list[float]]:
    """Embed all chunks in batches of 16; retry on rate-limit."""
    embeddings = []
    for i in range(0, len(chunks), 16):
        batch = chunks[i:i + 16]
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


def ensure_pipeline_index(endpoint: str, key: str) -> None:
    """Create filingsiq-pipeline-index if it does not already exist."""
    idx_client = SearchIndexClient(endpoint, AzureKeyCredential(key))

    fields = [
        SimpleField(name="id",   type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
        SimpleField(name="year", type=SearchFieldDataType.String, filterable=True),
    ]

    index = SearchIndex(
        name=PIPELINE_INDEX,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")]
                    ),
                )
            ]
        ),
    )

    idx_client.create_or_update_index(index)
    print(f"Index '{PIPELINE_INDEX}' ready.")


# ---------------------------------------------------------------------------
# Per-filing worker — runs inside ThreadPoolExecutor
# ---------------------------------------------------------------------------

def process_filing(row: dict) -> dict:
    """
    Full pipeline for one filing: read -> chunk -> embed -> upload.
    Returns a result dict that becomes one row in the Spark results DataFrame.
    """
    fy        = int(row["fiscal_year"])
    file_path = str(row["file_path"])

    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )
    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=PIPELINE_INDEX,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )

    t0            = time.time()
    chunks_count  = 0
    uploaded      = 0
    status        = "ok"
    error_msg     = ""

    try:
        text         = Path(file_path).read_text(encoding="utf-8")
        chunks       = chunk_text(text)
        chunks_count = len(chunks)

        print(f"  FY{fy}: {chunks_count} chunks — embedding ...")
        embeddings = embed_chunks(openai_client, os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"], chunks)

        documents = [
            {"id": f"fy{fy}-chunk-{i}", "content": chunk, "embedding": emb, "year": f"FY{fy}"}
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
        ]

        for i in range(0, len(documents), UPLOAD_BATCH):
            batch   = documents[i:i + UPLOAD_BATCH]
            results = search_client.upload_documents(documents=batch)
            failed  = [r for r in results if not r.succeeded]
            if failed:
                raise RuntimeError(f"Upload failed for keys: {[r.key for r in failed]}")

        uploaded = len(documents)
        print(f"  FY{fy}: {uploaded} docs uploaded.")

    except Exception as exc:
        status    = "error"
        error_msg = str(exc)
        print(f"  FY{fy}: ERROR — {error_msg}")

    return {
        "fiscal_year": fy,
        "file_path":   file_path,
        "chunks":      chunks_count,
        "uploaded":    uploaded,
        "duration_s":  round(time.time() - t0, 1),
        "status":      status,
        "error":       error_msg,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    # Spark session — local mode, Arrow enabled, UI off to avoid port conflicts on Windows.
    # Arrow is critical: it converts pandas DataFrames to JVM columnar memory so that
    # show/collect/filter never need Python worker subprocesses (which crash on
    # Windows + Python 3.12 + PySpark 3.5.3 — confirmed in S5.1).
    spark = (
        SparkSession.builder
        .appName("FilingsIQ-Pipeline")
        .master("local[*]")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    print("Spark session started.\n")

    # Build manifest DataFrame
    filings = sorted(FILINGS_DIR.glob("10k_FY*.txt"))
    if not filings:
        raise FileNotFoundError(f"No 10k_FY*.txt files found in {FILINGS_DIR}")

    manifest_rows = [
        {"fiscal_year": int(p.stem.replace("10k_FY", "")), "file_path": str(p)}
        for p in filings
    ]
    manifest_df = spark.createDataFrame(pd.DataFrame(manifest_rows))

    print("Manifest:")
    manifest_df.show(truncate=False)

    # Ensure the pipeline index exists before workers start
    ensure_pipeline_index(os.environ["AZURE_SEARCH_ENDPOINT"], os.environ["AZURE_SEARCH_KEY"])

    rows_to_process = manifest_df.toPandas().to_dict("records")

    mlflow.set_experiment("filingsiq-pipeline")
    with mlflow.start_run(run_name="batch-ingest-apple-10k"):

        # Log pipeline configuration as parameters
        mlflow.log_params({
            "chunk_chars":       CHUNK_CHARS,
            "overlap_chars":     OVERLAP_CHARS,
            "upload_batch":      UPLOAD_BATCH,
            "max_workers":       MAX_WORKERS,
            "num_filings":       len(rows_to_process),
            "embedding_model":   os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "unknown"),
            "search_index":      PIPELINE_INDEX,
        })

        # Process all filings in parallel (driver-side threads)
        print(f"\nProcessing {len(rows_to_process)} filings with {MAX_WORKERS} parallel workers ...")
        pipeline_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(process_filing, rows_to_process))
        pipeline_duration = round(time.time() - pipeline_start, 1)

        # Collect results into a Spark DataFrame via Arrow
        results_df = spark.createDataFrame(pd.DataFrame(results))

        print("\nResults:")
        results_df.select("fiscal_year", "chunks", "uploaded", "duration_s", "status").show()

        totals = results_df.select(
            F.sum("chunks").alias("total_chunks"),
            F.sum("uploaded").alias("total_uploaded"),
        ).collect()[0]
        errors = results_df.filter(results_df.status == "error").count()
        print(f"Total chunks: {totals.total_chunks}  |  Uploaded: {totals.total_uploaded}  |  Errors: {errors}")

        # Log per-filing metrics
        for r in results:
            fy = r["fiscal_year"]
            mlflow.log_metrics({
                f"fy{fy}_chunks":     r["chunks"],
                f"fy{fy}_uploaded":   r["uploaded"],
                f"fy{fy}_duration_s": r["duration_s"],
            })

        # Log summary metrics
        mlflow.log_metrics({
            "total_chunks":      int(totals.total_chunks),
            "total_uploaded":    int(totals.total_uploaded),
            "error_count":       int(errors),
            "pipeline_duration_s": pipeline_duration,
        })

        # Log results table as a CSV artifact for a downloadable audit trail
        results_csv = Path(__file__).parent / "data" / "pipeline_results.csv"
        results_df.toPandas().to_csv(results_csv, index=False)
        mlflow.log_artifact(str(results_csv), artifact_path="results")
        print(f"\nMLflow run complete. Results artifact saved to {results_csv.name}")
        print("Launch the MLflow UI with:  mlflow ui")

    spark.stop()
    print("\nDone.")


if __name__ == "__main__":
    main()
