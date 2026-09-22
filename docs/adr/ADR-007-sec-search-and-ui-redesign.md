# ADR-007 — SEC Company Search (Year-Scoped Import) and UI Redesign

**Date:** 2026-09-21
**Status:** Accepted
**Deciders:** FilingsIQ portfolio project

---

## Context

Through Stage 9, adding a company meant either editing code (`edgar_download.py` from a
terminal) or the disabled-in-production `POST /companies/import` endpoint, which always pulled a
company's latest **five** 10-Ks and replaced its entire indexed set. There was no way for a user
of the live app to add a company at all, and no way to top up a single missing year without
re-downloading and re-embedding everything else already indexed for that ticker.

Separately, the UI was a single long page of stacked shadcn/ui cards (`frontend/app/page.tsx`) —
functional, but visually plain, with no way to browse multiple indexed companies at a glance and
no theme option.

This stage addresses both, without changing the manual PDF-upload flow (`/upload`), which stays
exactly as it was — it remains the path for documents that aren't SEC-indexed 10-Ks.

---

## Decision 1 — SEC search is public, but capped at 2 fiscal years per import

`GET /sec/search` (SEC's public `company_tickers.json`, cached in memory for 6 hours) and
`GET /sec/filings` (a ticker's available 10-Ks, each flagged `indexed: true/false`) let a user
find and preview a company before committing to an import. `POST /sec/import` then imports **at
most 2 fiscal years** per call — enforced in `import_jobs._validate_years()` on the backend, not
just disabled in the UI — as a background job (`ThreadPoolExecutor(max_workers=1)`, so only one
import runs at a time) that the frontend polls via `GET /sec/import/{job_id}` for live progress.

This is a deliberate change from Stage 9's posture, where import was hard-disabled in production
(`ENABLE_COMPANY_IMPORT=false`) because it was all-or-nothing per company (five filings, full
re-embed). Capping each import at 2 years bounds the cost and time of any single anonymous
request enough to leave the feature **on** in production. It does not add authentication —
anyone with the URL can still trigger an import — so this is a cost-bounding control, not an
access control. See "Consequences" below.

## Decision 2 — imports now replace only the requested years, not the whole company

`import_company()` and `_company_filter()` (`backend/company_ingest.py`) take an optional
`fiscal_years` set. When present, both the SEC download and the Azure AI Search delete-before-
upload step are scoped to just those years; a company's other indexed years are left untouched.
Without it (the old single-company-import code path), behavior is unchanged — the whole set is
replaced. This turns "add one missing year" from "re-import and re-embed everything" into
"embed the one year that's missing," which matters more now that import is public and users will
reasonably expect to top up a company incrementally rather than always re-pull five years.

## Decision 3 — job state is in-process memory, not a durable store

`import_jobs.py` keeps running/finished jobs in a plain `dict`, pruned after an hour. This means
job state is lost on a container restart or scale-to-zero cooldown, and it does not survive
multiple replicas (a poll could land on a replica that never ran the job). The backend Container
App's `maxReplicas` was set to **1** specifically for this reason — see Decision in ADR-005 for
why Container Apps was chosen at all; this is a narrower constraint on top of it. A durable queue
(Service Bus + a table for job status) is the production-scale answer and is out of scope here,
consistent with this project's pattern of building the smallest thing that's honest about the
scale it's built for.

## Decision 4 — UI redesign: sidebar + chat thread instead of one long page

The frontend moved from one page of stacked cards to a persistent sidebar (companies, SEC search,
upload, classifier) next to a chat thread with citation chips that reveal the exact source
excerpt inline, rather than a single collapsible "Sources" block at the bottom of the page. A
light/dark toggle was added (`components/theme-toggle.tsx`), applied pre-paint via an inline
script in `layout.tsx` to avoid a flash of the wrong theme. The manual upload and clause-
classifier panels moved into dialogs (`components/tool-dialogs.tsx`) reachable from the sidebar,
rather than being permanently stacked on the page — the PDF upload flow itself (Document
Intelligence → PII redaction → chunk → embed → index) is unchanged.

This is a visual and information-architecture change, not a backend contract change: `/ask`,
`/companies`, `/classify`, and `/upload` all keep their existing request/response shapes.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Keep import fully disabled in production, add SEC search as read-only preview | Defeats the point of the feature — the user explicitly wants to add companies from the live app, not just browse what SEC has. |
| Allow up to 5 years per import (match the old default) | A 5-year import is a multi-minute, multi-dollar operation for an unauthenticated caller; 2 years bounds worst-case cost per request roughly in line with a single filing's DI/upload cost. |
| Durable job queue (Service Bus + table) for import progress | Correct production answer, but a real infrastructure addition; in-memory state with `maxReplicas=1` is an honest, cheaper fit for current traffic and is documented as a known limitation, not hidden. |
| Replace the whole company set on every import, even when only one year is requested | Wastes embedding cost and download time on years that are already correctly indexed; year-scoped deletion was a small, contained change to `_company_filter`. |
| Rebuild the frontend on a component library other than the existing shadcn/ui + Base UI stack | The existing primitives (Button, Card, Select, Textarea) were reused; only new primitives needed for the redesign (Dialog) were added, avoiding a full dependency swap. |

---

## Production target (beyond this portfolio implementation)

| Dimension | This implementation | Larger-scale production target |
|---|---|---|
| Import authorization | None — any caller with the URL can trigger an import | Entra ID auth + per-user rate limits, so the 2-year cap is a UX nicety instead of the only cost control |
| Import job state | In-process `dict`, `maxReplicas=1` | Durable queue + status table (Service Bus + Postgres/Cosmos), surviving restarts and multiple replicas |
| Import concurrency | One import at a time, process-wide | Per-user or per-company concurrency limits, not a single global lock |
| SEC ticker cache | In-memory, 6-hour TTL, per replica | Shared cache (Redis) so multiple replicas don't each cold-fetch `company_tickers.json` |
| UI theme | `localStorage` + a pre-paint inline script | Same approach scales fine — no change needed at larger scale |

---

## Consequences

**Positive:**
- A user of the live app can now add a company end-to-end from the UI — search, pick years,
  watch progress, chat — without any code change or redeploy, closing the gap Stage 9 explicitly
  left open pending a cost-bounding design.
- Incremental "add one more year" no longer re-embeds a company's whole filing set.
- The UI is materially easier to navigate with more than one or two indexed companies, and now
  has a working theme toggle.

**Negative / trade-offs:**
- Import is still unauthenticated. The 2-year cap and single-worker queue bound cost per request
  and prevent pile-up, but a motivated caller can still run repeated imports; this is a
  documented, not-yet-closed gap (tracked alongside the pre-existing `/upload` gap from the
  system analysis document).
- Import job state does not survive a container restart mid-import; a user polling a job that
  disappears mid-run sees a 404 rather than a clean "failed" status.
- The frontend's dialogs and sidebar add real component surface area (`sec-import-dialog.tsx`,
  `tool-dialogs.tsx`, `answer-view.tsx`) compared to the single-file Stage 9 page — more files to
  keep in sync with the backend contract, though each is now smaller and more focused.
