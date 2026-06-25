# FilingsIQ — Demo Script

A ~4-minute walkthrough for presenting the live app in an interview or portfolio review.
Live app: https://filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io
Repo: https://github.com/leopbar/FilingsIQ

Each beat below is: **[on screen]** what to click/show — *"what to say"* — talking point.

---

## 1. Open with the problem (15s)

**[on screen]** The live chat UI, empty input box.

*"SEC filings are hundreds of pages of dense legal and financial text. FilingsIQ lets you ask a
plain-English question and get a grounded answer with citations — not a hallucination, an actual
quote from the filing."*

---

## 2. Grounded answer + citations (45s)

**[on screen]** Type: *"What were Apple's total net sales in fiscal 2025?"* → submit.

*"This goes through a full RAG pipeline: the question gets embedded, Azure AI Search does a
hybrid BM25 + vector search with a semantic re-ranker over the indexed filing, and GPT-4o
answers only from what comes back — with inline citations."*

**[on screen]** Click "show sources" → point at one citation.

*"Every citation links back to the literal excerpt the answer was built from. If the answer
isn't in the filing, the model is instructed to say so — not guess."*

---

## 3. Year filter — scoped retrieval (30s)

**[on screen]** Switch the year dropdown to **FY2023**, ask the same question again.

*"The index actually holds five years of Apple 10-Ks, FY2021 through FY2025, ingested through a
PySpark + MLflow batch pipeline. The year filter scopes retrieval to one filing — useful for
single-year lookups, and it's also how the system avoids confusing figures across years."*

> **Known limitation, worth saying out loud:** *"If you ask a cross-year question without
> picking a year — like 'which year had the highest net income' — retrieval over the unfiltered
> multi-year index sometimes misses the right chunk. I found and documented that gap with an
> automated eval, which is the next thing I want to show."*

---

## 4. PDF upload — bring your own document (45s)

**[on screen]** Open the "Upload a PDF" panel, upload a filing for a company the model has never
seen (the project's own test used DLH Holdings Corp., an obscure government-services firm — any
unfamiliar 10-K works to prove grounding, not memorized knowledge).

*"Behind this button: Document Intelligence does layout-aware extraction — it keeps tables
intact, not just raw OCR text — then Azure AI Language redacts PII before anything gets indexed.
The result is chunked, embedded, and added to the search index live."*

**[on screen]** Switch the year dropdown to "Uploaded doc," ask a question only answerable from
that filing.

*"The answer is grounded in the document I just uploaded seconds ago — proof this isn't relying
on GPT's general knowledge, it's actually reading what I gave it."*

---

## 5. Clause classifier (optional — only if the FT deployment is spun up; 30s)

**[on screen]** Clause classifier panel — paste a contract clause, classify.

*"This calls a GPT-4o model I fine-tuned specifically to classify legal clauses into 41 standard
categories from the CUAD dataset. Zero-shot, the base model gets 17.7% accuracy on this — the
categories are genuinely hard to tell apart. Fine-tuned, it jumps to 77.5%. I deployed it,
measured the before/after on 671 held-out clauses, then tore the deployment down afterward
because hosting a fine-tuned model bills by the hour — the UI handles that 'offline' state
gracefully rather than crashing, which you're seeing right now if I haven't spun it back up."*

> If the deployment is offline (the default state, to control cost): show the graceful
> "model offline" notice instead and explain it's intentional — that's a legitimate beat too,
> it demonstrates the offline path was designed for, not an accident.

---

## 6. The part that doesn't show up in the UI — MLOps (60s)

**[on screen]** Switch to slides or just talk — this is the operational layer behind the chat box.

*"Three things run around this pipeline that you don't see in the UI:*

1. *A **RAGAS eval gate** — a 24-question golden set scores every answer on faithfulness,
   relevancy, and retrieval quality. I don't gate everything on one flat threshold — I found a
   table-flattening artifact that was tanking one metric on otherwise-correct answers, and a
   genuine cross-document retrieval weakness, and treated those two findings differently rather
   than averaging them away.*
2. *Every live request is traced end-to-end in **Application Insights** — embed, search,
   generate, each as its own span, so I can see exactly where latency or errors happen in
   production, not just locally.*
3. *Every question hits **Azure AI Content Safety** before it reaches the model — fails open if
   the safety check itself errors, so a non-critical gate's outage doesn't take down chat.*

*All of this is deployed on Azure Container Apps, with every credential — eight of them — coming
from Key Vault through a managed identity. No plaintext secret ever touched a command line, a
file, or a chat transcript."*

---

## 7. Close (15s)

**[on screen]** GitHub repo README, scroll to the job-requirement coverage table.

*"The repo has the full decision trail — six ADRs covering every major call, including the ones
that didn't work on the first try. This was built to be defensible end-to-end, not just a demo
that works once."*

---

## Notes for recording

- The clause classifier (step 5) requires spinning up the `ft-cuad-classifier` deployment in
  Azure OpenAI Studio beforehand — it bills ~$1.70–3/hr while running. Decide before recording
  whether to spin it up (live classify) or demonstrate the graceful offline path instead (free).
- Steps 2–4 all hit the live, public Azure deployment — no local servers needed.
- Total runtime target: ~4 minutes if all sections are included; ~3 minutes skipping the
  classifier section.
