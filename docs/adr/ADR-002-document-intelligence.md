# ADR-002 — Use Azure Document Intelligence + Azure AI Language for Document Processing

**Date:** 2026-06-14
**Status:** Accepted
**Deciders:** FilingsIQ project team

---

## Context

FilingsIQ answers questions about SEC filings by retrieving relevant chunks from an Azure AI
Search index and passing them to GPT-4o. The quality of those answers depends directly on the
quality of the text stored in the index.

The Stage 1 ingestion pipeline produced that text by downloading the Apple 10-K as an HTML
file from SEC EDGAR and stripping all HTML tags with a regular expression. This approach had
two significant problems:

1. **Broken tables** — Financial tables (revenue breakdowns, income statements, balance
   sheets) are the most information-dense parts of a 10-K. In HTML they are structured as
   `<table>/<tr>/<td>` elements with clear row and column relationships. After regex stripping,
   those relationships are lost: all values collapse into a flat stream of numbers with no
   indication of which column (year) or row (product line) each number belongs to. GPT-4o
   must guess at the structure, producing unreliable answers to table questions.

2. **No governance story for sensitive content** — The job requirement explicitly mentions
   "Cognitive Services" (plural), and responsible data handling (PII detection and redaction
   before storage) is a core governance expectation for any document processing pipeline
   that might handle real filings in production.

The solution for both problems is to replace the regex pipeline with Azure's purpose-built
document processing services.

---

## Decision

**Use Azure Document Intelligence (DI) prebuilt-layout model to extract structured content
from the filing PDF, and Azure AI Language to detect and redact PII before the content
enters the search index.**

### Document pipeline (one-time, per filing)

```
filing_raw.html  (SEC EDGAR)
      ↓  html_to_pdf.py  (Playwright/Chromium — renders iXBRL HTML faithfully)
filing.pdf
      ↓  di_extract.py   (DI prebuilt-layout → Markdown + HTML tables)
filing_di.md
      ↓  pii_redact.py   (Azure AI Language recognize_pii_entities → category labels)
filing_di_redacted.md
      ↓  ingest.py        (chunk → embed → upload to filingsiq-index)
Azure AI Search index
```

### Service configuration

| Service | Resource | Tier | Region |
|---|---|---|---|
| Azure Document Intelligence | `filingsiq-docintel` | Standard S0 (pay-per-use) | East US 2 |
| Azure AI Language | `filingsiq-language` | Free F0 | East US 2 |

### What DI produces

The `prebuilt-layout` model returns the document as Markdown with:
- `##`/`###` headings for section titles (Item 1, Item 7, etc.)
- Financial tables as structured HTML embedded in the Markdown, preserving row/column
  relationships across all years side-by-side
- Correct reading order across columns and across page boundaries

### What PII redaction produces

Azure AI Language scans the extracted Markdown in 5,000-character batches and replaces
detected entities with category labels: `[PERSON]`, `[ORGANIZATION]`, `[PHONENUMBER]`, etc.
1,196 entities were redacted in the Apple 10-K. The redacted file is what enters the index.

---

## Alternatives Considered

### Option A — Regex HTML stripping (Stage 1 approach)
- **Cost:** $0 (pure Python, no Azure service)
- **Why rejected:** Destroys table structure. Financial tables are the primary target for
  quantitative questions ("Mac revenue 2024 vs 2023") and the most valuable content in a
  10-K. Regex stripping makes those questions unreliable. This is not a marginal quality
  difference — it is a fundamental capability gap.

### Option B — Python PDF libraries (PyMuPDF, pdfplumber, pdfminer)
- **Cost:** $0 (open-source)
- **Why rejected:** These libraries extract text from PDF character streams, which does not
  reconstruct table structure. A table cell containing "29,984" is indistinguishable from a
  footnote number without the HTML context that DI provides. They also require manual
  post-processing to handle multi-column layouts and spanning table headers. DI handles all
  of this natively, and using it is the point of the "Document Intelligence" requirement.

### Option C — Azure Document Intelligence prebuilt-read model
- **Cost:** Same as prebuilt-layout (pay-per-use, S0)
- **Why rejected:** The `prebuilt-read` model extracts text and reading order but does **not**
  reconstruct tables. It is the right choice for prose-heavy documents with no tables.
  For a financial filing where tables carry critical quantitative data, `prebuilt-layout`
  is the correct model.

### Option D — Azure Document Intelligence prebuilt-layout ✅ (chosen)
- **Cost:** ~$1 total for the Apple 10-K (~$0.01/page, ~100 pages); $0 when idle
- **Why chosen:** The only option that preserves table structure as machine-readable HTML.
  Markdown output format is a native DI capability (no post-processing). Correctly handles
  the iXBRL/HTML → PDF → structured text pipeline end-to-end.

### Option E — No PII redaction
- **Why rejected:** The job requirement says "Cognitive Services" (plural) — a single
  service (DI) does not satisfy it. More importantly, a production document processing
  pipeline that stores third-party filing content without PII screening is a governance gap.
  Azure AI Language F0 is free and requires minimal integration effort; the benefit
  (demonstrated responsible AI handling) far outweighs the cost.

---

## Consequences

### Positive
- **Table questions now work correctly** — chunks contain structured HTML table rows with
  column context intact. Verified: *"Mac net sales 2024 vs 2023"* → correct figures
  ($29,984M and $29,357M) with citations, retrieved in a single query.
- **Better reading order** — DI handles multi-column layouts and page headers/footers;
  regex stripping cannot. Chunks reflect the document's logical flow, not its HTML source order.
- **Governance demonstrated** — PII detection and redaction before indexing is a concrete
  responsible-AI practice, directly evidenced by `pii_redact.py` and the redacted output.
- **"Cognitive Services" (plural) satisfied** — Azure Document Intelligence + Azure AI
  Language together cover the job requirement explicitly.
- **No pipeline contract change** — the `/ask` API, the frontend, and the AI Search index
  schema are unchanged. Only the *content* of the index improved.
- **ADR trail** — this document + ADR-001 form a governance artifact set demonstrating
  deliberate, documented architectural decisions.

### Negative / Trade-offs
- **One-time cost ~$1** for DI extraction of the Apple 10-K (DI S0, ~$0.01/page). Acceptable
  and already incurred. Scaling to thousands of filings would require cost modelling.
- **Extra pipeline steps** — the ingestion path is now four scripts instead of one. This is
  the right trade-off for quality, but it increases operational complexity. Stage 5
  (PySpark pipeline) will automate this chain.
- **PII false positives** — Azure AI Language aggressively tags "Apple Inc." as
  `[ORGANIZATION]` and SEC file numbers as `[PHONENUMBER]`. These are expected false
  positives in a public document. The redaction capability is demonstrated; precision tuning
  (custom entity categories, confidence thresholds) is a production concern.
- **PDF as intermediary** — the Apple 10-K is published as HTML on EDGAR; we convert it to
  PDF first so DI can process it. A production pipeline would prefer a native PDF source
  where available, falling back to HTML→PDF conversion only when needed.

---

## Production Target (what "enterprise-grade" looks like)

This ADR documents a **development configuration**. A production deployment would add:

| Concern | Dev (current) | Production target |
|---|---|---|
| Authentication | API keys in `.env` | Managed Identity (no secrets) |
| Network | Public endpoints | Private endpoints + VNet |
| DI tier | Standard S0 (pay-per-use) | Standard S0 with commitment tier for high volume |
| PII handling | Redact before indexing | Redact + audit log to Azure Storage + RBAC on raw files |
| Pipeline orchestration | Four manual scripts | Azure Data Factory or Databricks (Stage 5) |
| Filing source | Single PDF converted from HTML | Native PDFs from EDGAR where available |
| PII precision | Default model, all categories | Custom categories + confidence threshold tuning |
| Error handling | Raise on failure | Dead-letter queue + retry policy + alerting |
| Monitoring | None | App Insights + DI usage metrics + cost alerts |

The current implementation deliberately keeps operations simple while the **processing
pattern** (PDF → DI layout → PII redact → chunk → embed → index) is identical to what
would run in production. The senior engineering signal is knowing which shortcuts are
temporary and documenting the production path explicitly.
