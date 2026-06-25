# ADR-006 — MLOps/LLMOps: RAGAS Eval Gate, Monitoring, Content Safety

**Date:** 2026-06-20
**Status:** Accepted
**Deciders:** FilingsIQ portfolio project

---

## Context

Job requirement #9 calls for *"MLOps / LLMOps"* — operational discipline around an LLM
application, not just the application itself. Going into Stage 7, FilingsIQ had a working,
deployed RAG pipeline (Stage 6.5) but no automated way to know if a change degraded answer
quality, no visibility into what was happening inside a live request, and no screening of
user input before it reached GPT-4o. This stage adds all three, without changing `/ask`'s
response contract:

1. A **golden-set eval gate** using RAGAS (faithfulness, answer relevancy, context precision,
   context recall) with a pass/fail exit code suitable for CI.
2. **Application Insights** instrumentation for request- and dependency-level tracing.
3. **Azure AI Content Safety** screening on `/ask`.

---

## Decision 1 — RAGAS eval in a separate venv, with category-aware thresholds

`ragas` requires an older `langchain` + `openai<2` stack that directly conflicts with the main
app's pinned `openai==2.41.1` and `mlflow`'s `pyarrow<18` pin. Rather than downgrade the main
app's dependencies (risking breaking the deployed service or Stage 4/5 scripts), eval runs in
an isolated **`backend/venv-eval`** (`requirements-eval.txt`). `backend/ragas_eval.py` imports
`rag.py` directly and scores its real output — not a mock — against
`backend/data/eval/golden_qa.jsonl` (24 hand-verified questions: 18 against the permanent Apple
FY2021–FY2025 filings, 6 against the upload slot).

The first full run surfaced two findings that shaped the design of `backend/eval_gate.py`:

- **Lookup-question faithfulness has a structural ~0.5 floor**, not because of hallucination,
  but because Document Intelligence flattens tables to plain text, and RAGAS's strict
  NLI-style faithfulness judge sometimes can't mechanically re-verify a number against the
  linearized table even when it's genuinely there (confirmed by manual inspection of a specific
  case, `q07`, where the answer was correct but scored faithfulness `0.0`).
- **Cross-document "all years" comparison questions are a real, separate weak point**: with no
  year filter, `top_k=5` over the 640-chunk multi-year index can miss the one chunk that
  contains the answer (confirmed on `q16`: the model answered the wrong fiscal year because the
  correct year's net income chunk was never retrieved).

A single flat threshold across all questions would either gate on the first artifact (a false
positive on the build) or average away the second (hiding a real defect). **Decision:**
`eval_gate.py` groups questions into `lookup` / `comparison_single_doc` / `comparison_cross_doc`
/ `negative` and applies different thresholds to each, set with margin below the first run's
observed averages — see `PROJECT_LOG.md` §S7.3 for the full threshold table. The `negative`
category's `answer_relevancy` metric is excluded from gating entirely: RAGAS's relevancy metric
reverse-engineers a question from the answer, and a correct "not in the document" refusal
doesn't resemble a question, scoring near-zero regardless of correctness — a documented metric
quirk, not a quality signal here.

The cross-document retrieval weakness itself is **not fixed** in this stage — Stage 7 is about
eval/monitoring infrastructure, not retrieval quality — but it is now a measured, documented,
regression-testable limitation instead of an unknown one.

---

## Decision 2 — Monitoring and Content Safety are both optional at runtime

Both `azure-monitor-opentelemetry` (Application Insights) and `azure-ai-contentsafety` are wired
to activate **only if their connection secrets are present in the environment**, falling back
to a no-op rather than crashing:

```python
_appinsights_conn = os.environ.get("AZURE_APPINSIGHTS_CONNECTION_STRING")
if _appinsights_conn:
    configure_azure_monitor(connection_string=_appinsights_conn)
```

This matters concretely: `rag.py` is imported directly by `backend/ragas_eval.py`, which runs
in `backend/venv-eval` — a venv that does not have `opentelemetry` installed at all. `rag.py`'s
OpenTelemetry import is wrapped in `try/except ImportError`, falling back to
`contextlib.nullcontext()` for its three custom spans (`embed_question`, `search_documents`,
`chat_completion`), so the eval pipeline keeps working unmodified.

Content Safety similarly **fails open**: if the `analyze_text` call itself raises (timeout,
outage, bad credentials), the check logs a warning and lets the request through rather than
returning a 500 from `/ask`. A non-critical safety gate should not become a single point of
failure for the core feature it's protecting — the same reasoning already applied to the
fine-tuned classifier's graceful `available:false` path in Stage 6.5.

**Severity threshold:** Content Safety's per-category severity scale is 0/2/4/6 (Hate,
SelfHarm, Sexual, Violence). `4` ("medium") was chosen and verified against a borderline case —
a legitimate question about Apple's 10-K risk factors mentioning "war," "armed conflict," and
cybersecurity "attacks" — to confirm normal filing language isn't false-positived while
explicit harmful requests are still blocked with `400`, not a 500.

---

## Decision 3 — CI workflow authored but explicitly not live

`.github/workflows/ragas-eval.yml` is `workflow_dispatch`-only: a real run costs ~74 minutes and
several dollars in GPT-4o judge calls (see `PROJECT_LOG.md` §S7.2), so it is not wired to
push/PR. More fundamentally, **this project has no git repository yet** — there is no GitHub
remote, so this workflow has never executed. It is included as a complete, ready-to-activate
definition rather than a working claim, with that caveat stated directly in the file's header
comment. This is a deliberate choice to keep the project's documentation honest about what has
and hasn't actually run, consistent with how ADR-005 documented `az acr build` being blocked
rather than implying a CI pipeline exists.

---

## A real security incident during this stage, and how it was handled

While debugging a `.env` parsing issue in S7.5, a `grep -n` command printed the
**`AZURE_LANGUAGE_KEY` value into the chat transcript** — a direct violation of this project's
"never paste secrets in chat" rule. Root cause: a PowerShell `Add-Content` call appended a new
secret line to `.env` without a leading newline, concatenating it onto the end of the existing
`AZURE_LANGUAGE_KEY=...` line; a follow-up debugging command then printed that combined line in
full.

**Response:** the corruption was fixed with a Python script that only manipulated string
positions and never printed file contents, and — treating the exposure as a real compromise
rather than a cosmetic mistake — **the key was rotated** (`az cognitiveservices account keys
regenerate`) before continuing to S7.6, with the new value pushed to Key Vault and `.env`
without ever displaying it. Every subsequent secret-handling command in this stage (the Content
Safety endpoint/key, the rotated key itself) was run through `az ... -o tsv` into a PowerShell
variable and `--file <tempfile>`, with explicit verification afterward using `grep -c
"^KEY_NAME="` (presence/line-count only) rather than printing values — the same discipline
ADR-005 established for the original 8 secrets, now reinforced after a real near-miss.

---

## A real Container Apps rollout characteristic, found during S7.7's redeploy

Immediately after updating the backend Container App to image `:v3`, `az containerapp revision
list` showed **both** the old (`v2`) and new (`v3`) revisions as `active:true` simultaneously,
despite the app being in `Single` revision mode with 100% traffic configured on latest. A test
request sent in that window hit the still-warm old replica (no Content Safety code at all) and
returned `200` instead of the expected `400`. Waiting ~15 seconds and re-testing produced the
correct result; the stale revision was then explicitly deactivated. This is documented as a
genuine Container Apps rollout-timing characteristic — traffic cutover is not instantaneous
even in Single mode — not a defect in the Content Safety wiring, and is the kind of thing a
real production rollout needs a brief settle time or readiness check to avoid, not something
this portfolio project needed to build tooling around.

---

## End-to-end verification (S7.7)

| Test | Result |
|---|---|
| RAGAS eval gate (`eval_gate.py`) against the saved first-run results | All 11 category/metric checks PASS, exit 0 |
| `/ask`, normal question, live URL | `200`, correct grounded answer ($416,161M FY2025 net sales) |
| `/ask`, explicit harmful request, live URL | `400`, graceful block — confirmed after rollout settled |
| `/ask`, borderline legitimate risk-factor question (war/conflict), live URL | `200`, correctly answered, no false positive |
| Application Insights, live, queried ~1 min after the above | **5 `request` + 34 `dependency` records** — full request-level tracing confirmed in production |

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Downgrade main app's `openai`/`langchain` to satisfy ragas in the same venv | Would touch the deployed application's pinned dependencies and Stage 4/5 scripts for an eval-only tool; isolated venv has zero blast radius. |
| One flat pass/fail threshold across all 24 questions | Would either gate on a known DI-table-formatting artifact or silently average away the genuine cross-document retrieval weakness found in S7.3. |
| Fail-closed on Content Safety API errors (block by default) | Turns a non-critical safety gate's own outage into an outage of the core chat feature; fail-open with a logged warning was judged the better trade-off for this app's risk profile. |
| Wire monitoring/safety as hard dependencies (crash without the secret) | Would break `backend/venv-eval` (no `opentelemetry`) and any future fresh clone/CI run without every secret configured. |
| Mark the GitHub Actions workflow as active/scheduled | Dishonest — there is no GitHub remote for this project; the file documents intended CI, not running CI. |

---

## Production target (beyond this portfolio implementation)

| Dimension | This implementation | Larger-scale production target |
|---|---|---|
| Eval cadence | Manual, single run (`workflow_dispatch`, never yet triggered) | Scheduled (e.g. nightly/weekly) CI run against a versioned golden set, with trend tracking across runs |
| Eval venv isolation | Separate local venv | Eval running in its own CI job/container so dependency conflicts never touch the deploy pipeline |
| Retrieval gap (cross-doc comparisons) | Documented, not fixed | Raise `top_k` or add a query-decomposition step for unfiltered multi-year questions |
| Content Safety severity | Single fixed threshold (4) | Per-category thresholds tuned against a labeled adversarial test set, reviewed periodically |
| Telemetry | Connection string via Key Vault, manual verification | Alerting rules (e.g. on error rate, P95 latency, blocked-request rate) wired to the same Application Insights resource |
| Secret-handling discipline | Manual care per command (temp files, `tsv`, no echo) | Pre-commit/pre-push secret scanning (e.g. `gitleaks`) as a backstop against the exact mistake that occurred in S7.5 |

---

## Consequences

**Positive:**
- Job requirement #9 ("MLOps/LLMOps") is now ✅ closed with three concrete, verified pieces:
  an automated eval gate, production telemetry, and an input safety screen.
- The eval process didn't just produce a score — it found and explained two genuine
  characteristics of the system (a table-legibility artifact and a real cross-document
  retrieval gap) that were previously unknown, which is the actual point of having an eval gate.
- A real secret-exposure incident was caught, explained honestly, and remediated (rotation) in
  the same step rather than glossed over — consistent with this project's existing pattern of
  documenting real mistakes (the ADR-005 plaintext-secrets near-miss) rather than only the
  clean path.

**Negative / trade-offs:**
- The eval gate runs against a static, already-saved `ragas_results.json`, not freshly every
  time — a real CI integration would need to decide how often to re-run RAGAS given its cost.
- Content Safety's fail-open behavior means a sustained Content Safety outage would silently
  disable the screening rather than alert anyone — acceptable for a portfolio demo, not the
  final word for a production deployment without a paired alert on check failures.
- The cross-document comparison retrieval weakness remains unfixed; it is now measured and
  gated against regression, but not solved.
