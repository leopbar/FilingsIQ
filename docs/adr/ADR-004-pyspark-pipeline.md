# ADR-004 — PySpark Batch Ingestion Pipeline (Hybrid Architecture)

**Date:** 2026-06-17
**Status:** Accepted
**Deciders:** FilingsIQ portfolio project

---

## Context

Job requirement #8 calls for demonstrated ability to build *"PySpark + scalable data pipelines."*
The goal of Stage 5 is to show that the FilingsIQ ingestion process — download filing, chunk
text, embed, upload to Azure AI Search — can be structured as an observable, reproducible batch
pipeline, not just a one-off script.

The pipeline processes **5 years of Apple 10-K annual reports (FY2021–FY2025)** downloaded from
EDGAR, and tracks every run with **MLflow** so parameters, metrics, and output artifacts are
permanently recorded and comparable across runs.

The main architectural challenge was that the standard PySpark execution model (Python worker
subprocesses) does not work on Windows + Python 3.12 + PySpark 3.5.3.

---

## Decision

Use a **hybrid pipeline architecture**:

- **Spark DataFrames** (via pandas/Arrow) manage the job manifest (which filings to process)
  and collect results into a structured summary.
- **Driver-side `concurrent.futures.ThreadPoolExecutor`** executes per-filing work
  (read → chunk → embed → upload) in parallel on the driver, without spawning Python worker
  subprocesses.
- **MLflow** tracks every run: parameters, per-filing metrics, summary metrics, and a CSV
  artifact.

---

## Why not pure PySpark UDFs or `mapInPandas`

On Windows + Python 3.12 + PySpark 3.5.3, any operation that triggers a Python worker
subprocess crashes silently with `EOFException` in the JVM. This includes:

- RDD lambdas (`rdd.map(lambda x: ...)`)
- `DataFrame.rdd.map()`
- `mapInPandas` / `applyInPandas`
- `createDataFrame` from a Python list (without Arrow)

**Root cause:** PySpark spawns a Python subprocess for every worker task and communicates via a
socket. Python 3.12 changed internal subprocess behavior in a way that PySpark 3.5.3's Windows
worker launcher does not handle correctly. This is a known open issue in the PySpark tracker.

**Fix applied:** enabling Arrow serialization
(`spark.sql.execution.arrow.pyspark.enabled=true`) allows `createDataFrame(pd.DataFrame(...))`
to convert data directly to JVM columnar memory via Apache Arrow, bypassing Python workers
entirely for all DataFrame operations (`show`, `collect`, `filter`, `agg`).

---

## Arrow — why it matters

Without Arrow, `createDataFrame` serializes each row as a Python pickle through a worker
subprocess. With Arrow, the entire DataFrame is converted to a binary columnar buffer in the
driver process and handed to the JVM in one shot. Every subsequent DataFrame operation (show,
collect, filter, agg) executes 100% inside the JVM — no Python workers needed.

This is also why `toPandas()` works: Arrow converts the JVM columnar buffer back to a pandas
DataFrame entirely on the driver side.

---

## Pipeline architecture

```
EDGAR (data.sec.gov)
      │  edgar_download.py (one-time)
      ▼
backend/data/filings/10k_FY{year}.txt  (5 files, FY2021–FY2025)
      │
      ▼  spark_pipeline.py
┌─────────────────────────────────────────────────────┐
│  SparkSession (local[*], Arrow enabled, UI off)      │
│                                                      │
│  manifest_df = createDataFrame(pd.DataFrame(...))    │
│    ┌──────────┬─────────────────────────────────┐   │
│    │fiscal_yr │ file_path                        │   │
│    ├──────────┼─────────────────────────────────┤   │
│    │ 2021     │ .../10k_FY2021.txt               │   │
│    │  ...     │  ...                             │   │
│    └──────────┴─────────────────────────────────┘   │
│                                                      │
│  rows = manifest_df.toPandas().to_dict("records")   │
│                                                      │
│  ThreadPoolExecutor(max_workers=5)                   │
│    ├── process_filing(FY2021) ──┐                    │
│    ├── process_filing(FY2022) ──┤ parallel           │
│    ├── process_filing(FY2023) ──┤                    │
│    ├── process_filing(FY2024) ──┤                    │
│    └── process_filing(FY2025) ──┘                    │
│             │  each worker:                          │
│             │  read → chunk → embed → upload         │
│             ▼                                        │
│  results_df = createDataFrame(pd.DataFrame(results)) │
│  results_df.show() / .agg(sum chunks, sum uploaded)  │
└─────────────────────────────────────────────────────┘
      │
      ▼  Azure AI Search
  filingsiq-pipeline-index  (640 chunks, 5 fiscal years)

      │
      ▼  MLflow (local mlruns/)
  Experiment: filingsiq-pipeline
  Run: batch-ingest-apple-10k
    params:  chunk_chars, overlap_chars, upload_batch,
             max_workers, num_filings, embedding_model, search_index
    metrics: total_chunks=640, total_uploaded=640, error_count=0,
             pipeline_duration_s=132.5,
             fy{year}_chunks / fy{year}_uploaded / fy{year}_duration_s (×5)
    artifact: results/pipeline_results.csv
```

---

## Run results (verified 2026-06-17)

| Fiscal Year | Chunks | Uploaded | Duration |
|---|---|---|---|
| FY2021 | 136 | 136 | 130.6 s |
| FY2022 | 132 | 132 | 129.8 s |
| FY2023 | 123 | 123 | 70.8 s |
| FY2024 | 124 | 124 | 130.5 s |
| FY2025 | 125 | 125 | 129.9 s |
| **Total** | **640** | **640** | **132.5 s wall clock** |

Duration variance (~70 s vs ~130 s) is caused by Azure OpenAI rate-limit back-off: when 5
parallel workers saturate the embedding TPM quota simultaneously, each waits 15 s before
retrying. This is expected and handled gracefully.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Pure Spark UDFs / `mapInPandas` | Crashes on Windows + Python 3.12 + PySpark 3.5.3 (Python worker subprocess incompatibility). Correct on Azure Databricks. |
| Sequential processing (no parallelism) | Simpler but does not demonstrate scalable pipeline design — misses the point of the requirement. |
| Azure Data Factory | Managed ETL service; no code, no Spark, no portfolio signal. |
| Dask instead of Spark | Dask works on Windows without the worker issue, but Azure Databricks (the enterprise target) is Spark-native. Using Dask would not demonstrate the right skill. |
| Docker + Spark Standalone | Correct on Linux; avoids the Windows worker issue. Not pursued because it adds infrastructure complexity without changing the portfolio signal — the architecture is identical. |

---

## Production target (Azure Databricks)

On Azure Databricks the Python worker limitation does not exist. The `process_filing` function
would be promoted from driver-side threads to a true distributed UDF:

```python
# Production form on Databricks
result_df = manifest_df.mapInPandas(process_filing_pandas_udf, schema=result_schema)
```

Everything else stays the same: the manifest DataFrame, the processing logic, MLflow tracking.
The hybrid architecture was designed so this is a one-line change.

| Dimension | This implementation | Production target (Databricks) |
|---|---|---|
| Execution | Driver-side `ThreadPoolExecutor` | `mapInPandas` distributed UDF |
| Parallelism | 5 threads on one machine | One Spark worker per filing (horizontal scale) |
| Scale | ~5–50 filings | Thousands of filings |
| MLflow | Local `mlruns/` folder | Databricks-managed MLflow (built-in) |
| Auth | API key in `.env` | Managed Identity + Azure Key Vault |
| Scheduling | Manual (`python spark_pipeline.py`) | Databricks Jobs (cron or event-triggered) |
| Monitoring | MLflow run history | MLflow + Azure Monitor alerts on `error_count > 0` |

---

## Consequences

**Positive:**
- Job requirement #8 is now ✅ Solid: Spark DataFrames, parallel execution, MLflow tracking,
  and a clear path to production on Azure Databricks.
- The pipeline is observable: every run is permanently recorded with full params, metrics, and
  an artifact. Anomalies (errors, slow filings) are visible in the MLflow UI without digging
  through logs.
- The architecture is honest: the ADR explains the Windows limitation and the production path,
  which is a stronger signal than pretending the limitation doesn't exist.

**Negative / trade-offs:**
- The pipeline targets `filingsiq-pipeline-index` (a demo index), not the production
  `filingsiq-index`. Wiring it into the production chat app would require re-running DI
  extraction + PII redaction per filing — deferred to a future stage.
- MLflow is local only (`mlruns/` folder). A CI/CD deployment would point MLflow at a
  remote tracking server (e.g., Databricks-managed or self-hosted).
- Plain-text extraction (regex HTML stripping) is used for FY2021–FY2024, since Document
  Intelligence processing is already demonstrated in Stage 3. Ingestion quality is intentionally
  secondary to pipeline structure for this stage.
