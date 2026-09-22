# FilingsIQ

An AI system that lets you **chat with SEC filings**: ask a question in plain English, get a
grounded answer with citations pulled directly from the document — never fabricated.

**🔗 Live app:** https://filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io

Built as a portfolio project demonstrating Azure AI Engineer skills end-to-end: RAG, vector
search, document processing, fine-tuning, a Spark data pipeline, containerized deployment, and
production MLOps/LLMOps discipline — not a notebook demo, a deployed, monitored, evaluated
application.

> A "filing" is just a long text document (10-K annual report, 10-Q quarterly report, etc.).
> No finance expertise is required to understand what's built here — the AI techniques
> (extract → chunk → embed → search → answer) are identical regardless of document type.

---

## What it does

- **Search and add any SEC-listed company** from the live app — search by name or ticker,
  preview its available 10-Ks, and import up to 2 fiscal years at a time as a background job
  with live progress. Re-running an import only re-embeds the years you picked; a company's
  other indexed years are left alone.
- **Ask questions** about any indexed company's 10-K filings, or upload your own PDF and chat
  with it instead — the manual upload path (Document Intelligence → PII redaction → index) is
  unchanged and always available.
- **Filter by fiscal year** to scope answers to a specific filing, or leave it open for
  cross-year questions.
- **Classify legal clauses** into one of 41 standard contract-clause categories using a model
  fine-tuned specifically for that task.
- Every answer is **grounded and cited** — the model is instructed to answer only from retrieved
  excerpts, with inline `[1]`, `[2]`… citations that expand in the UI to show the exact source
  excerpt and a link to the filing on sec.gov.
- Harmful or out-of-scope input is **screened before it reaches the model**, and every request is
  traced end-to-end in Application Insights.
- A sidebar of indexed companies, a chat-thread UI with citation chips, and a **light/dark theme
  toggle**.

---

## Architecture

```
Browser (Next.js chat UI: sidebar + chat thread)
      │  POST /ask  { question, ticker?, year? }
      ▼
FastAPI backend
      │  0. screen question        → Azure AI Content Safety (fails open, returns 400 if blocked)
      │  1. embed question         → Azure OpenAI (text-embedding-3-small)
      │  2. hybrid search          → Azure AI Search (BM25 + HNSW vector + semantic re-ranker)
      │  3. generate grounded answer → Azure OpenAI (gpt-4o), cited from retrieved chunks
      │  ↳ every step traced       → Application Insights (OpenTelemetry spans)
      ▼
{ answer, sources, citations }

SEC company search + import (POST /sec/import, background job):
  search/filings ──EDGAR──▶ pick ≤2 fiscal years ──chunk + embed──▶ Azure AI Search
                                                                    (replaces only those years)

Manual PDF ingestion (POST /upload, unchanged):
  filing.pdf ──Document Intelligence──▶ layout markdown ──Azure AI Language──▶ PII-redacted
             ──chunk + embed──▶ Azure AI Search index

Batch pipeline (5 years of filings at once, offline):
  EDGAR ──PySpark + MLflow──▶ parallel chunk/embed/upload, every run tracked
```

**Two retrieval indexes:**
- `filingsiq-index` — the original single-document Apple FY2025 10-K (Stage 1–3).
- `filingsiq-pipeline-index` — every company added since (Apple, Microsoft, and whatever has been
  searched and imported through the live app) plus whichever document is currently uploaded
  through "Upload a PDF."

See [ADR-007](docs/adr/ADR-007-sec-search-and-ui-redesign.md) for why import is public but capped
at 2 fiscal years per request, and why it replaces only the requested years instead of a
company's whole filing set.

---

## Key results

| Capability | Result |
|---|---|
| **Fine-tuning** (`gpt-4o-2024-08-06` on CUAD legal-clause classification, 41 categories) | Accuracy **17.7% → 77.5%** (+59.8 pp), Macro F1 **0.15 → 0.69** on 671 held-out test clauses |
| **RAG answer quality** (RAGAS, 24-question golden set) | Faithfulness 0.79 · Answer relevancy 0.87 · Context precision 0.76 · Context recall 0.89 |
| **PySpark batch pipeline** | 5 years of Apple 10-Ks → 640 chunks, parallel-processed, 0 errors, full MLflow tracking |
| **Live deployment** | Two Azure Container Apps (scale-to-zero), Key Vault + Managed Identity for every secret, no plaintext credentials anywhere |

---

## Job requirement coverage

| # | Requirement | Status | How |
|---|---|---|---|
| 1 | Azure OpenAI + related AI services | ✅ | gpt-4o + text-embedding-3-small |
| 2 | Prompt engineering + RAG + vector search | ✅ | Grounded RAG, hybrid + semantic search |
| 3 | Vector database + Cognitive Search | ✅ | Azure AI Search (BM25 + HNSW + semantic re-ranker) — [ADR-001](docs/adr/ADR-001-azure-ai-search-basic-tier.md) |
| 4 | Document processing (Document Intelligence + Cognitive Services) | ✅ | DI layout extraction + Azure AI Language PII redaction — [ADR-002](docs/adr/ADR-002-document-intelligence.md) |
| 5 | Governance & best practices | ✅ | Key Vault + Managed Identity, no plaintext secrets, ADR trail — [ADR-005](docs/adr/ADR-005-deployment.md) |
| 6 | Design & architect AI solutions on Azure | ✅ | Multi-service architecture, deployed live on Azure Container Apps |
| 7 | Fine-tuning & model optimization | ✅ | gpt-4o fine-tuned on CUAD; +59.8 pp accuracy — [ADR-003](docs/adr/ADR-003-fine-tuning.md) |
| 8 | PySpark + scalable data pipelines | ✅ | Hybrid Spark + MLflow batch pipeline — [ADR-004](docs/adr/ADR-004-pyspark-pipeline.md) |
| 9 | MLOps / LLMOps | ✅ | RAGAS eval gate, Application Insights tracing, Content Safety screening — [ADR-006](docs/adr/ADR-006-mlops-llmops.md) |
| 10 | Customer enablement / presentations | ✅ | This README + ADR set |
| — | Build & deploy an enterprise-grade application | ✅ | Live on Azure Container Apps; self-service company search — [ADR-007](docs/adr/ADR-007-sec-search-and-ui-redesign.md) |

See [`docs/adr/`](docs/adr/) for the full set of Architecture Decision Records — each documents
the context, decision, alternatives considered, and a dev-vs-production-target comparison.

---

## Tech stack

**Azure:** OpenAI (gpt-4o, text-embedding-3-small, fine-tuning) · AI Search · Document
Intelligence · AI Language · AI Content Safety · Application Insights · Key Vault · Container
Registry · Container Apps.

**App:** FastAPI (Python) · Next.js 16 + TypeScript + Tailwind + shadcn/ui + Base UI.

**Data/ML:** PySpark · MLflow · RAGAS · CUAD dataset.

**Ops:** Docker · GitHub Actions (eval workflow, not yet wired to a live CI run).

---

## Running it locally

### Prerequisites
- Python 3.10+, Node.js 18+
- An Azure OpenAI resource (`gpt-4o` + `text-embedding-3-small` deployments)
- Azure AI Search, Document Intelligence, and AI Language resources (optional — required only
  for the document-processing and PII-redaction parts of the ingestion pipeline)

### Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # fill in your Azure credentials
uvicorn main:app --reload
```
Backend runs at `http://localhost:8000` (`/docs` for interactive API docs).

### Frontend
```powershell
cd frontend
npm install
npm run dev
```
Frontend runs at `http://localhost:3000`.

### Docker (both services together)
```powershell
docker compose up --build
```

> **Note:** ingestion (`ingest.py`, `upload.py`, `spark_pipeline.py`, SEC company search/import)
> talks to live Azure services and will incur costs. The live app's indexes are already
> populated — local setup is only needed if you want to rebuild the pipeline yourself.

---

## Project structure

```
FilingsIQ/
  backend/
    main.py              # FastAPI app: /ask, /companies, /sec/*, /classify, /upload
    rag.py                # hybrid + semantic retrieval → gpt-4o grounded answer
    upload.py             # PDF upload pipeline: DI extract → PII redact → chunk → embed → index
    ingest.py             # chunk → embed → upload (single-document ingestion)
    create_index.py       # Azure AI Search index schema
    di_extract.py          # Document Intelligence layout extraction
    pii_redact.py          # Azure AI Language PII redaction
    spark_pipeline.py     # PySpark + MLflow batch pipeline (5 years of filings)
    edgar_download.py     # SEC EDGAR: company search, filing discovery, download
    company_ingest.py     # persistent multi-company chunk/embed/replace (year-scoped)
    import_jobs.py        # background SEC import jobs: validation, progress, polling
    prepare_cuad.py / baseline_eval.py / run_finetune.py / ft_eval.py / compare.py
                           # fine-tuning pipeline: data prep → baseline → train → eval → compare
    ragas_eval.py / eval_gate.py
                           # RAGAS quality evaluation + pass/fail threshold gate
    test_stage9.py / test_sec_search_import.py
                           # offline regression tests
    Dockerfile / requirements*.txt
  frontend/
    app/page.tsx          # server component: loads companies, renders FilingsClient
    app/filings-client.tsx # sidebar + chat thread: ask, SEC search, upload, classifier
    app/api/[...path]/route.ts # same-origin proxy to the backend
    components/sec-import-dialog.tsx # search → pick ≤2 years → live import progress
    components/tool-dialogs.tsx      # upload and clause-classifier dialogs
    components/answer-view.tsx       # renders answers with clickable citation chips
    components/theme-toggle.tsx      # light/dark toggle
    components/ui/                   # shadcn/ui + Base UI primitives
    lib/api.ts             # typed client for every backend endpoint
    Dockerfile
  docs/adr/                # Architecture Decision Records (ADR-001…007)
  .github/workflows/        # RAGAS eval CI workflow (manual trigger)
  docker-compose.yml
```

---

## Known limitations (documented honestly, not hidden)

- **SEC company search/import has no authentication.** Anyone with the live URL can trigger an
  import. The 2-fiscal-year cap and single-job-at-a-time queue bound the cost and blast radius
  of any one request, but this is a cost control, not an access control — see
  [ADR-007](docs/adr/ADR-007-sec-search-and-ui-redesign.md).
- **Import job progress is kept in memory**, not a durable store, so it does not survive a
  container restart mid-import and requires the backend to run a single replica.
- **Cross-document synthesis is weak.** Questions spanning all years without a `year` filter
  (e.g. "which fiscal year had the highest net income?") sometimes miss the right chunk in
  unfiltered retrieval over the multi-year index — a known retrieval-quality gap, tracked in
  [ADR-006](docs/adr/ADR-006-mlops-llmops.md).
- **The clause-classifier deployment is offline by default** to avoid standing hourly billing on
  the fine-tuned model. The live `/classify` endpoint degrades gracefully (`available: false`)
  rather than failing.
- **The upload slot holds one document at a time** — uploading a new PDF replaces the previous
  one in the `filingsiq-pipeline-index`.
- **PySpark runs in a hybrid mode on Windows** (Spark DataFrames for orchestration, driver-side
  threading for per-file processing) due to a Python-worker incompatibility on Windows +
  Python 3.12 + PySpark 3.5.3. The processing logic is the same one that would run via
  `mapInPandas` on a real Spark cluster — documented in
  [ADR-004](docs/adr/ADR-004-pyspark-pipeline.md).
