# ADR-001 — Use Azure AI Search Basic Tier for Vector + Hybrid Search

**Date:** 2026-06-13
**Status:** Accepted
**Deciders:** FilingsIQ project team

---

## Context

FilingsIQ needs a vector database to store and retrieve document chunk embeddings
(1,536-dimensional vectors from `text-embedding-3-small`). The initial Stage 1
implementation used an in-memory approach: all embeddings were stored in a local
`vectors.json` file and similarity was computed in Python with brute-force cosine
comparison across 117 chunks at query time.

This approach is not production-viable for three reasons:

1. **Scale** — brute-force cosine similarity over millions of vectors is O(n); a real
   document corpus (thousands of filings) would make query latency unacceptable.
2. **Search quality** — pure vector search misses exact keyword/number matches (e.g.,
   ticker symbols, dollar figures, dates). A hybrid approach combining keyword (BM25)
   and vector search consistently outperforms either alone.
3. **Portability** — a file on disk is not shareable, not replicated, and not queryable
   by multiple backend instances.

Azure AI Search is the natural choice given the project already runs on Azure (Azure
OpenAI for embeddings and GPT-4o). The question is which **tier** to provision.

---

## Decision

**Provision Azure AI Search at the Basic tier** (`filingsiq-search`, East US,
resource group `filingsiq-rg`).

The index (`filingsiq-index`) is configured with:
- **Three fields:** `id` (key), `content` (searchable text), `embedding`
  (Collection(Single) × 1,536, HNSW algorithm)
- **Hybrid search:** BM25 keyword search on `content` + HNSW vector search on
  `embedding`, results merged via Reciprocal Rank Fusion (RRF)
- **Semantic re-ranker:** `semantic-config` designates `content` as the primary field;
  the re-ranker (an Azure-hosted cross-encoder model) re-scores the merged BM25+vector
  results as a second-pass L2 step

---

## Alternatives Considered

### Option A — Azure AI Search Free tier
- **Cost:** $0/month
- **Why rejected:** The Free tier does **not** support the semantic re-ranker. Hybrid
  search without re-ranking leaves significant relevance quality on the table. For a
  portfolio project whose purpose is to demonstrate enterprise-grade search, omitting
  the re-ranker would undermine the core claim.

### Option B — Azure AI Search Basic tier ✅ (chosen)
- **Cost:** ~$75/month (~$2.50/day); billed continuously (not scale-to-zero)
- **Why chosen:** Lowest tier that supports the semantic re-ranker. Covered by the
  $200 Azure free credit available at project start. Supports up to 15 indexes, 2 GB
  storage, and 3 replicas — more than sufficient for this workload.
- **Mitigation:** Delete the resource during long breaks to conserve credit; recreating
  takes ~2 minutes. The index schema and ingestion script (`create_index.py`,
  `ingest.py`) make recreation fully repeatable.

### Option C — Azure AI Search Standard tier
- **Cost:** ~$250/month — significantly higher for no benefit at this scale.
- **Why rejected:** Overkill for a single-index, 117-chunk proof-of-concept. Standard
  adds higher storage, more replicas, and higher QPS — none of which are bottlenecks here.

### Option D — Third-party vector DB (Qdrant, Pinecone, Weaviate)
- **Why rejected:** Adds a non-Azure dependency, complicates auth/networking, and
  distances the project from the "Azure AI Engineer" positioning. Azure AI Search
  integrates natively with Azure OpenAI (same tenant, same region, no cross-cloud
  latency), and the hybrid + re-ranker capability is competitive with purpose-built
  vector DBs at this scale.

---

## Consequences

### Positive
- **Hybrid search** (BM25 + vector) retrieves relevant chunks even when the query
  contains exact terms (product names, dollar figures) that pure vector search would
  rank poorly.
- **Semantic re-ranker** provides an AI-powered L2 re-scoring step, improving
  precision of the top-k results passed to GPT-4o — directly improving answer quality.
- **HNSW index** makes vector search sub-linear at scale; the architecture handles
  millions of chunks without a code change.
- **Native Azure integration** — same tenant as Azure OpenAI; Managed Identity (future)
  eliminates key-based auth entirely.
- **Zero frontend/API contract change** — the `/ask` endpoint signature is identical
  to Stage 1; only the retrieval backend swapped.

### Negative / Trade-offs
- **Billing is continuous** (~$2.50/day) even with zero queries. Not scale-to-zero.
  Acceptable for a time-bounded portfolio project; would require a cost-governance
  policy (auto-delete schedule, budget alert) in production.
- **Tier cannot be downgraded in place** — must delete and recreate to change tier.
  This is why we chose Basic from the start rather than starting on Free and upgrading.
- **Semantic re-ranker adds ~200–400 ms latency** per query (the cross-encoder model
  runs server-side in Azure). Acceptable for a document Q&A use case; would need
  evaluation for latency-sensitive applications.

---

## Production Target (what "enterprise-grade" looks like)

This ADR documents a **development configuration**. A production deployment of the
same architecture would add:

| Concern | Dev (current) | Production target |
|---|---|---|
| Authentication | API key in `.env` | Managed Identity (no secrets) |
| Network | Public endpoint | Private endpoint + VNet integration |
| Tier | Basic | Standard S2+ (higher QPS, replicas for HA) |
| Replicas | 1 | 3 (99.9% SLA) |
| Key management | `.env` file | Azure Key Vault reference |
| Cost governance | Manual delete | Budget alert + auto-teardown policy |
| Monitoring | None | Azure Monitor + App Insights query latency |

The current implementation deliberately uses free/cheap controls while the **architecture
pattern** (hybrid search, semantic re-ranker, HNSW index) is identical to what would run
in production. Knowing the difference — and documenting it — is the senior engineering
signal this project is designed to demonstrate.
