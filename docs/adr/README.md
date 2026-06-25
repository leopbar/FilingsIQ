# Architecture Decision Records — Index

Each ADR follows the same format: Context → Decision → Alternatives considered → Consequences,
plus a dev-vs-production-target comparison. Read in order — each stage builds on the last.

| ADR | Decision | One-line takeaway |
|---|---|---|
| [ADR-001](ADR-001-azure-ai-search-basic-tier.md) | Azure AI Search **Basic tier** for vector + hybrid search | Replaced in-memory cosine similarity with a real vector DB; Basic is the minimum tier with a semantic re-ranker — bills ~$2.50/day continuously, the one resource worth deleting between work sessions. |
| [ADR-002](ADR-002-document-intelligence.md) | **Document Intelligence (layout) + Azure AI Language (PII)** for ingestion | Swapped regex-stripped HTML for real PDF layout extraction (tables preserved) plus PII redaction — covers "Cognitive Services" as a plural requirement, not just one. |
| [ADR-003](ADR-003-fine-tuning.md) | **Fine-tune `gpt-4o-2024-08-06`** on CUAD legal-clause classification | Accuracy 17.7% → 77.5% (+59.8 pp) on 671 held-out clauses — a fine-tuning task hard enough zero-shot to make the delta meaningful, not a toy demonstration. |
| [ADR-004](ADR-004-pyspark-pipeline.md) | **Hybrid Spark + `concurrent.futures` + MLflow** batch pipeline | Spark DataFrames manage the manifest/results; driver-side threading does the actual work (Windows + Python 3.12 + PySpark 3.5.3 breaks Python worker subprocesses) — framed honestly as the local-dev path vs. `mapInPandas` on a real cluster. |
| [ADR-005](ADR-005-deployment.md) | Deploy to **Azure Container Apps** with **Key Vault + Managed Identity** | No plaintext secret ever touched a command line, file, or chat transcript — Key Vault + system-assigned identities for both the app and the ACR pull, closing the "enterprise-grade vs. free-tier" credibility gap. |
| [ADR-006](ADR-006-mlops-llmops.md) | **RAGAS eval gate + Application Insights + Content Safety** | Category-aware quality thresholds (not one flat bar — a DI table-flattening artifact and a real cross-document retrieval gap needed different treatment), full request tracing in production, and fail-open input screening. |

## Recurring themes across all six

- **Honest framing over hidden gaps.** Every ADR that hit a real limitation (Windows/PySpark,
  CLI bugs, retrieval weaknesses, RAGAS metric quirks) documents it explicitly rather than
  glossing over it — including a security incident (a key briefly exposed via a debug `grep`,
  caught and rotated) recorded in ADR-006 rather than omitted.
- **Dev vs. production target.** Each ADR distinguishes what was built for a portfolio budget
  (Basic tier, Standard fine-tune deployment torn down after eval, local Windows Spark) from what
  the production-grade equivalent would be (higher Search tier, Developer/PTU fine-tune hosting,
  a real Databricks cluster).
- **No secret ever in plaintext.** From ADR-005 onward, every credential goes through Key Vault
  via a temp-file pattern — never a literal CLI argument, tracked file, or chat message.
