# FilingsIQ Interview Questions and Answers — Topics 7–15

This study guide continues the FilingsIQ interview bank with the nine remaining topics. The
answers are written in the first person so they can be practiced aloud, but they should be
adapted to the speaker's natural wording rather than memorized word for word.

> **Note (2026-09-22):** written against the Stage 9 snapshot (frontend v4/v5, `AAPL`/`MSFT`
> only, company import disabled in production). Stage 10 added public SEC company search with a
> 2-fiscal-year-capped background import and a UI redesign — see
> [ADR-007](adr/ADR-007-sec-search-and-ui-redesign.md) and `docs/system-analysis.md`. The
> underlying interview substance (RAG design, fine-tuning, Spark, MLOps, security trade-offs)
> still holds; answers that describe import as "disabled" or the frontend as one page describe
> the pre-Stage-10 state and would need updating before being used as-is.

---

## 7. Frontend and API

### 1. How does the company selector obtain AAPL and MSFT?

The Next.js server calls FastAPI's `GET /companies` endpoint when it renders the page. That
endpoint summarizes the companies and fiscal years present in Azure AI Search. AAPL and MSFT
are therefore included in the initial HTML instead of being hardcoded in the browser.

### 2. Why does the server render the initial company list?

The first Stage 9 deployment depended on a browser-side request after static HTML delivery, and
the production selector stayed empty even though the API was healthy. Server rendering makes
the first screen deterministic: the company data is fetched before the HTML is returned.

### 3. What caused the production company selector to appear empty in frontend version 4?

Initial company loading depended entirely on a cross-origin `useEffect` in the browser. Direct
HTTP checks verified the static page and backend independently, but the real hydrated browser
never completed that initialization path. Backend access logs confirmed that `/companies` was
not reached from the user's page.

### 4. Why did direct API testing fail to detect that browser problem?

Those tests proved that each individual component responded correctly, not that the browser
connected them correctly after hydration. I had tested transport and API behavior but not the
complete user-visible execution path. The incident showed why an end-to-end browser test is
different from a collection of HTTP smoke tests.

### 5. How did frontend version 5 fix the hydration problem?

I split the page into a dynamic server component and a client component. The server fetches the
company list and passes it as initial data, while browser requests go through a same-origin
Next.js proxy. The initial production HTML now already contains AAPL and MSFT.

### 6. What is hydration in a Next.js application?

Hydration is the process where browser JavaScript attaches interactive React behavior to HTML
that was produced on the server. A page can look correct as static HTML but still fail when its
client-side state or effects initialize. That distinction caused the version 4 defect.

### 7. What does the `/api/[...path]` route do?

It is a catch-all Next.js proxy. The browser calls the frontend's own `/api` path, and the
Next.js server forwards the method, body, and relevant headers to FastAPI using a server-only
backend address. It centralizes browser-to-backend communication.

### 8. Why is `BACKEND_API_URL` now server-only?

The browser no longer needs to know the FastAPI URL. Keeping it server-side avoids baking
environment-specific infrastructure into public JavaScript and allows routing or authentication
to change behind the proxy without rebuilding client logic.

### 9. What benefit comes from not exposing the backend URL in browser JavaScript?

It reduces client configuration, removes CORS from the normal browser path, and provides one
place to add sessions or authorization later. It is not an access-control mechanism by itself:
the backend remains public until authentication and network restrictions are implemented.

### 10. How does the fiscal-year selector change when the selected company changes?

`GET /companies` returns the available years for each indexed company. When the user selects a
ticker, the client derives the year options from that company's metadata and sends both ticker
and year in `/ask`. The backend independently enforces those filters.

### 11. How does the UI display SEC filing metadata?

Each answer includes structured citations alongside the raw excerpts. Source cards display the
company, form, fiscal year, filing date, and title, and link to the authoritative SEC filing.
The citation number matches the `[1]`, `[2]`, and similar markers in the answer.

### 12. How does the UI handle an offline fine-tuned classifier?

The backend catches the model-deployment-not-found case and returns `available: false` rather
than a server error. The frontend explains that the deployment is intentionally offline to
avoid hourly cost. Document chat continues to work because the classifier is independent.

### 13. How does the UI handle a long-running PDF upload?

It shows an indexing state and explains that layout extraction may take 30–90 seconds. The
backend runs blocking document processing in a small thread pool so the async endpoint does not
block the event loop. A production system would move this work to a durable background queue.

### 14. How would you make loading and error messages more user-friendly?

I would provide stage-specific progress, correlation IDs, retry guidance, and plain-language
errors instead of exposing raw backend details. For imports and uploads, I would return a job
ID and display queued, extracting, embedding, indexing, completed, or failed states.

### 15. How would you test the complete hydrated browser experience in CI?

I would use Playwright against production-built frontend and backend containers. The test would
open the page, verify that AAPL and MSFT are visible before interaction, select MSFT, submit a
question through `/api`, and assert that the answer and SEC citation render correctly.

---

## 8. Fine-tuning

### 1. Why does the project include a legal-clause classifier?

It demonstrates a second AI pattern beyond RAG: changing a model's specialized behavior through
training. Legal-clause classification is difficult enough to produce a meaningful measured
improvement, while the main RAG feature demonstrates changing document knowledge.

### 2. How is the classifier related to the main document-chat capability?

Both features analyze long business or legal documents, but they are separate pipelines. RAG
answers questions from retrieved SEC evidence; the classifier maps a contract clause to one of
41 CUAD categories. The classifier does not participate in SEC retrieval.

### 3. Why was CUAD chosen as the dataset?

CUAD contains real contracts with expert annotations across 41 clause categories. It supplied
thousands of labeled examples without inventing labels manually and created a credible
specialized task with overlapping legal concepts.

### 4. Why are 41 legal clause categories a meaningful fine-tuning problem?

Many labels use similar dense legal language, so a general model cannot rely on a few obvious
keywords. The 17.7% zero-shot baseline confirmed that the task was genuinely difficult rather
than a toy classification problem.

### 5. Why was a zero-shot baseline measured before fine-tuning?

Without a baseline, I could say training completed but could not show that it added value. I
evaluated the base and fine-tuned models on the same 671 held-out clauses, making the 59.8
percentage-point accuracy improvement measurable.

### 6. Why did the base model achieve only 17.7% accuracy?

The model had to choose exactly one label from 41 related categories using a short prompt.
Several categories overlap semantically, and the base model had not learned CUAD's exact label
boundaries. Distinctive categories performed better than subtle ones.

### 7. How were training, validation, and test examples separated?

The 6,702 positive clause examples were shuffled with a fixed seed and split 80/10/10: 5,361
training, 670 validation, and 671 test examples. The test set was held out from training and
used for both baseline and fine-tuned evaluation.

### 8. Were examples split by individual clause or by originating contract?

They were split at the clause-example level, not grouped by source contract. That is a
limitation because similar drafting from one contract could appear across splits. A stronger
evaluation would use a group split by contract to reduce leakage risk.

### 9. Could clauses from the same contract in training and test create leakage?

Yes. Even if the exact clause is not duplicated, shared drafting style or related provisions
can make the test set easier. I would rerun the experiment with contract-level separation
before treating 77.5% as a production-grade generalization claim.

### 10. Why report Macro F1 as well as accuracy?

Accuracy can be dominated by common categories. Macro F1 calculates an F1 score per label and
weights all 41 categories equally, revealing whether the model improved broadly rather than
only on frequent labels.

### 11. Why was `gpt-4o-2024-08-06` chosen instead of `gpt-4.1-mini`?

The intended smaller model was not available for fine-tuning in the project's East US 2
resource. `gpt-4o-2024-08-06` was the strongest available supported model and produced a
defensible comparison against an already capable baseline.

### 12. What did the 77.5% result prove?

It showed that specialized training materially improved behavior on the held-out clause set:
accuracy rose from 17.7% to 77.5%, and Macro F1 rose from 0.1543 to 0.6884. It did not prove
perfect performance or eliminate the need for contract-grouped validation.

### 13. Why was the fine-tuned model apparently slower during evaluation?

The deployment had a six-requests-per-minute quota, so measured latency mostly reflected quota
waiting rather than inherent model computation. I documented that constraint instead of
presenting the 10.5-times latency difference as a pure model-speed result.

### 14. Why is the fine-tuned deployment offline by default?

The available Standard deployment incurred an hourly hosting charge even when unused. I
deleted it after evaluation and designed `/classify` to degrade gracefully. It can be
temporarily deployed for a demonstration without creating continuous portfolio cost.

### 15. How do you decide between prompting, RAG, and fine-tuning?

I use prompting when the model needs instructions, RAG when it needs current or attributable
knowledge, and fine-tuning when it needs repeatable specialized behavior that prompting cannot
reliably provide. FilingsIQ uses all three for those distinct purposes.

---

## 9. PySpark and data pipeline

### 1. Why did you introduce PySpark for only five filings?

Five files do not require Spark operationally. I used a small real workload to demonstrate
manifest-driven batch design, parallel processing, aggregation, and MLflow tracking while
being explicit that the local scale alone does not justify a cluster.

### 2. What part of the pipeline actually uses Spark DataFrames?

Spark DataFrames hold the filing manifest and result records, display job state, and calculate
aggregates such as total chunks and uploads. Arrow moves pandas data into JVM columnar memory
so those operations avoid broken local Python workers.

### 3. What part uses `concurrent.futures`?

Driver-side `ThreadPoolExecutor` workers perform file reading, chunking, Azure OpenAI embedding,
and Azure AI Search uploading for individual filings. This is the local Windows execution
substitute for distributed Spark Python processing.

### 4. Why couldn't ordinary Spark Python workers be used locally?

With Windows, Python 3.12, and PySpark 3.5.3, Python worker subprocesses failed with EOF-related
errors even though JVM-side DataFrame operations worked. I isolated the incompatibility and
documented the hybrid architecture rather than pretending it was distributed execution.

### 5. How did Arrow solve the Windows worker problem?

Arrow converts pandas DataFrames into columnar JVM memory directly. Subsequent DataFrame
operations such as `show`, `filter`, and aggregation remain JVM-side and do not launch the
failing Python worker subprocesses.

### 6. Is this genuinely a distributed Spark pipeline?

No. It demonstrates Spark DataFrame orchestration locally, but per-filing work runs in driver
threads on one machine. A production Databricks implementation would distribute the same
processing function with `mapInPandas` or another cluster-native pattern.

### 7. How would the architecture change on Azure Databricks?

Filings would live in durable cloud storage, the manifest would be a distributed table, and
worker executors would process partitions. Secrets would use managed identities or a secret
scope, MLflow would use managed tracking, and retries would be implemented per task.

### 8. Why use `ThreadPoolExecutor` instead of sequential processing?

Embedding and search uploads spend much of their time waiting on network services. Threads
overlap that waiting and reduced end-to-end duration. The worker count is intentionally bounded
because excessive concurrency triggers Azure rate limits.

### 9. How do concurrent embedding requests interact with Azure rate limits?

Five workers can exceed token or request quotas simultaneously. The pipeline detects
rate-related exceptions, waits 15 seconds, and retries. Duration variation between filings in
the recorded run largely came from that backoff.

### 10. How does the pipeline retry after rate limiting?

Embedding batches run in a loop. Rate-related failures trigger a delay and retry; other
exceptions are raised so they are not hidden. A production implementation would use bounded
exponential backoff, jitter, and explicit retryable status codes.

### 11. What does MLflow record for every ingestion run?

It records configuration such as chunk size, overlap, worker count, embedding model, and target
index; per-filing chunk, upload, and duration metrics; summary totals and errors; and a CSV
artifact containing the complete result table.

### 12. Why use MLflow instead of ordinary log files?

Logs explain events, while MLflow makes runs comparable and reproducible. It keeps parameters,
metrics, status, and artifacts together under a named experiment so I can compare pipeline
configurations rather than manually correlate console files.

### 13. How do you make the pipeline idempotent?

Chunk IDs are deterministic, and company ingestion treats one ticker's five filings as a
replacement set. Re-running an import refreshes that company instead of duplicating it. Other
companies are not deleted.

### 14. What happens if embedding succeeds but uploading fails halfway through?

The current company replacement can leave a partial state, which is a known production gap. I
would upload to a versioned staging scope, verify counts, switch an active-version pointer, and
delete the old version only after successful validation.

### 15. How would you redesign the pipeline for 1,000 companies?

I would use a durable queue, object storage, distributed workers, per-company idempotency keys,
checkpointed stages, centralized rate limiting, and dead-letter handling. I would also revisit
embedding dimensions, index partitioning, retention, Search SKU, and cost budgets.

---

## 10. RAG evaluation and RAGAS

### 1. What is a golden evaluation set?

It is a fixed collection of representative questions with manually verified expected answers
and retrieval scopes. It allows the same system behavior to be measured repeatedly instead of
depending on informal demonstrations.

### 2. How were the 24 expected answers verified?

The Apple values were checked against the actual FY2021–FY2025 filing text, including internal
consistency checks on financial totals. Six upload questions were verified against the DLH
Holdings filing occupying the upload slot at that time.

### 3. What does RAGAS faithfulness measure?

Faithfulness asks whether claims in the generated answer are supported by the retrieved
contexts. It is primarily a generation-grounding signal, although poor table formatting can
make correct evidence difficult for the judge to recognize.

### 4. What does answer relevancy measure?

It estimates whether the response addresses the user's question rather than being grounded but
off-topic. It is unreliable for correct refusals because “not in the document” does not
reconstruct into a question similar to the original.

### 5. What is the difference between context precision and context recall?

Context precision measures how much retrieved content is useful, while context recall measures
whether the retriever found the information required to answer. High precision with low recall
means clean results that may still omit a critical fact.

### 6. Why does GPT-4o act as the evaluation judge?

Faithfulness and relevancy require semantic comparison rather than exact string matching.
GPT-4o can evaluate paraphrases and document evidence at scale. Human review remains necessary
for anomalies and high-stakes validation.

### 7. Is there a risk in using the same model family to generate and judge answers?

Yes. The judge can share biases with the generator and may prefer similar wording. A stronger
evaluation would combine a different judge model, deterministic checks for known figures, and
sampled human review.

### 8. Why does RAGAS run in a separate Python environment?

The working RAGAS and LangChain versions require an older OpenAI dependency stack that conflicts
with the deployed application's `openai==2.41.1` and other pipeline pins. Isolation prevents an
evaluation tool from destabilizing production dependencies.

### 9. Why did the first RAGAS run take approximately 74 minutes?

Twenty-four questions required live RAG calls plus four judge metrics each. The small Azure
deployment throttled higher concurrency, and two judge calls exhausted long retry sequences.
Reducing RAGAS to two workers produced reliable but slow execution.

### 10. Why are the quality thresholds category-specific?

Different question types exposed different metric behavior. Flattened tables lowered lookup
faithfulness artificially, cross-document questions had a real recall weakness, and correct
negative answers scored poorly on relevancy. One flat threshold would confuse those cases.

### 11. Why do correct negative answers receive poor answer-relevancy scores?

RAGAS derives a possible question from the answer and compares it with the original. A refusal
such as “the documents do not contain that information” does not resemble the original factual
question, so the metric approaches zero despite correct behavior.

### 12. How did table flattening produce a misleading faithfulness score?

The retrieved text contained the correct value, but row and column relationships had become a
linear token sequence. GPT-4o answered correctly, while the stricter judge could not
mechanically associate the value with its label and assigned a zero.

### 13. Were thresholds chosen independently or fitted to the first run?

They were set below the observed first-run category averages with margin. That makes them useful
as regression baselines but not independent acceptance criteria. They should be recalibrated
with additional runs and human-reviewed labels.

### 14. Could fitting thresholds to the first run hide weaknesses?

Yes. A weak baseline can produce a permissive gate, especially for cross-document comparison.
The current gate detects degradation from known behavior; it does not certify that every
category is production-ready.

### 15. How should the golden set change now that Microsoft and multi-company retrieval are live?

It should add Microsoft lookups, company-isolation tests, multi-year Microsoft questions,
cross-company comparisons, citation-metadata checks, and adversarial ticker/year combinations.
The stale shared-upload questions should be versioned or separated from permanent-corpus tests.

---

## 11. MLOps and monitoring

### 1. What does MLOps or LLMOps mean in FilingsIQ?

It means operating the AI system with repeatable evaluation, telemetry, safety controls,
versioned configuration, and deployment discipline. The project implements a RAGAS gate,
request tracing, Content Safety, MLflow tracking, and documented rollout behavior.

### 2. What telemetry is sent to Application Insights?

FastAPI request telemetry, Azure dependency calls, logs, and custom spans are exported through
OpenTelemetry. The RAG spans record the year filter, hit count, and timing without deliberately
logging complete question or answer text.

### 3. What is an OpenTelemetry span?

A span is one timed operation inside a larger trace. The request trace contains spans for
embedding the question, searching documents, and generating the answer, making latency and
failure location visible.

### 4. Why create separate spans for embedding, search, and generation?

A total response time does not show which dependency is slow. Separate spans let me determine
whether latency comes from Azure OpenAI embeddings, Azure AI Search, or GPT-4o completion and
then optimize the correct component.

### 5. How would you identify whether search or GPT-4o is causing high latency?

I would compare span duration distributions in Application Insights, broken down by operation,
company scope, errors, and deployment revision. P50, P95, and P99 values reveal persistent
versus occasional latency.

### 6. Why avoid logging full questions and answers?

Questions and documents may contain confidential financial, legal, or personal information.
Logging only operational metadata reduces privacy exposure while retaining performance and
failure diagnostics.

### 7. What alerts would you create in production?

I would alert on error rate, P95 latency, dependency failures, Content Safety check failures,
embedding throttling, search-capacity use, import failures, blocked-request anomalies, and
Container App revision health.

### 8. Why is the RAGAS workflow manually triggered?

A full run took roughly 74 minutes and several dollars in model calls. Running it on every
commit would be slow and wasteful. Manual or scheduled execution is more appropriate until a
faster deterministic test layer is added.

### 9. Has the GitHub Actions evaluation workflow ever run?

The workflow was written before the repository had a GitHub remote and is documented as not
having run at that time. Unless a later Actions run is verified, I would describe it as a
ready manual workflow rather than claim active CI evidence.

### 10. Why isn't RAGAS executed on every pull request?

Besides cost and duration, judge-model scores have normal variance. I would use fast unit and
retrieval-contract tests on every pull request, then run the expensive RAGAS suite manually,
nightly, or before a release.

### 11. How would you track quality changes across releases?

I would persist every evaluation result with the commit, prompt version, index version, model
deployment, and configuration. A dashboard would display metric trends and per-question
regressions rather than only the latest averages.

### 12. How would you detect an increase in “not enough information” responses?

I would record a structured answerability outcome without storing sensitive answer text, then
monitor its rate by company, year, and question category. A spike could indicate ingestion,
filtering, or retrieval problems.

### 13. How would you monitor retrieval independently from generation?

I would evaluate expected filing IDs, required facts, context recall, and ranking metrics before
calling the generator. Deterministic retrieval tests can identify missing evidence even if
GPT-4o happens to produce a plausible answer.

### 14. How would you compare two prompts or retrieval configurations safely?

I would run both configurations against the same versioned golden set, compare quality, latency,
and cost, review disagreements, and canary the preferred version on limited traffic before full
deployment.

### 15. What would a rollback decision look like if quality scores decreased?

I would define category-specific release thresholds and critical-question checks. If a deployed
revision violated them or production telemetry showed a material regression, traffic would
return to the prior version while I isolated whether prompt, model, index, or ingestion caused
the change.

---

## 12. Content Safety and governance

### 1. Why does the application screen questions before running RAG?

Screening first avoids spending embedding, search, and generation calls on clearly harmful
requests and creates one consistent control at the public chat boundary. A blocked request
returns HTTP 400 before GPT-4o receives it.

### 2. Which harmful-content categories are checked?

Azure AI Content Safety evaluates hate, self-harm, sexual, and violence categories. FilingsIQ
checks each returned severity and blocks the question if any category reaches the configured
threshold.

### 3. Why was severity 4 chosen as the blocking threshold?

Azure's scale is 0, 2, 4, and 6. A threshold of 4 blocks clearly harmful content while allowing
legitimate filing questions that mention war, attacks, litigation, or other risk-factor
language. It was tested with both explicit harm and borderline financial examples.

### 4. How did you test false positives involving financial risk-factor language?

I submitted a legitimate question about Apple's war and geopolitical-conflict risks. It passed
and received a normal grounded answer, while an explicit violent request was blocked. That
verified both sides of the chosen threshold locally and in production.

### 5. Why does Content Safety fail open instead of fail closed?

For this portfolio's risk profile, I prioritized keeping document chat available if the
non-core safety service has a transient outage. The exception is logged and the request
continues. A higher-risk application might correctly choose fail closed instead.

### 6. What risk is created by fail-open behavior?

A Content Safety outage or credential problem temporarily disables input screening. Without an
alert, operators may not realize that protection is unavailable. Production fail-open behavior
therefore needs strong monitoring and a documented risk decision.

### 7. Why is only the input screened?

Stage 7 focused on the open-ended public input boundary and limited scope. GPT-4o is grounded in
public filings, but generated output can still be problematic. Output screening is a sensible
production enhancement, especially for private or broader corpora.

### 8. Should generated answers also pass through Content Safety?

For an enterprise deployment, yes, subject to measured latency and false positives. I would
screen outputs, retain the grounding checks, and test financial/legal language so ordinary
risk disclosures are not incorrectly blocked.

### 9. Why is Content Safety optional when environment variables are absent?

The same code must run in fresh clones, tests, and evaluation environments without every Azure
service configured. Optional initialization prevents an auxiliary integration from crashing
the core application at import time.

### 10. How would the system behave during a Content Safety outage?

It logs a warning and proceeds through RAG. Users receive normal answers, but screening is
temporarily unavailable. I would add a failure-rate metric and alert so fail-open does not
become silent long-term degradation.

### 11. How would you alert operators that safety screening stopped working?

I would emit a structured metric for every safety exception and alert on any sustained rate,
not merely HTTP errors. The alert would include dependency status and revision information but
exclude the user's sensitive text.

### 12. What personal information is removed before indexing uploaded PDFs?

Azure AI Language detects supported PII categories such as people, addresses, contact details,
and identifiers. The pipeline replaces detected spans with category labels before chunking,
embedding, and indexing.

### 13. How do you handle false-positive PII detections?

The current demonstration accepts the service result, but production needs category-specific
policy, sampling, and quality tests. Public organization names may need preservation while
personal identifiers are redacted, and secured originals may be retained under access controls.

### 14. How would data-retention requirements affect the upload feature?

I would add tenant-specific storage, explicit expiration, deletion workflows, audit records,
and verification that chunks, source files, caches, and backups are all removed. The current
single shared upload slot is not sufficient for regulated enterprise use.

### 15. What governance controls are required for confidential enterprise documents?

Authentication, authorization, tenant isolation, encryption, private networking, retention and
legal-hold policies, audit logs, data residency, customer-managed keys where required, model
data-use review, incident response, and documented human oversight would all be necessary.

---

## 13. Security

### 1. Where are Azure credentials stored during local development?

They are stored in `backend/.env`, which is excluded from Git. The tracked `.env.example`
documents variable names without values. Commands and diagnostics must avoid printing the real
file contents.

### 2. Where are credentials stored in the deployed application?

Sensitive values are held in Azure Key Vault. The backend Container App uses its
system-assigned identity to resolve Key Vault references into runtime environment variables;
the values are not baked into Docker images.

### 3. Why use Azure Key Vault instead of ordinary Container App secrets?

Key Vault centralizes secret storage, RBAC, auditing, and future rotation. Plain application
secrets would still protect values from source control, but Key Vault provides a stronger
operational boundary and avoids passing literal keys through deployment commands.

### 4. What is a system-assigned managed identity?

It is an Azure identity created for the lifecycle of one resource. Azure handles its credential,
and RBAC grants it specific permissions. FilingsIQ uses this identity for Key Vault access and
ACR image pulls.

### 5. How does the backend authenticate to Key Vault?

The Container App presents its managed identity to Azure. Key Vault RBAC grants that identity
the Secrets User role, allowing runtime reads without storing a Key Vault username, password,
or client secret.

### 6. How do Container Apps pull images from ACR without an admin password?

Their managed identities receive the `AcrPull` role on the registry. Azure validates the
identity when the platform pulls an image, so the deployment does not use an ACR admin
credential.

### 7. Why are downstream Azure API keys still present as environment variables?

The project retrieves service keys from Key Vault because several SDK paths were initially
implemented with key authentication. Key Vault protects distribution, but the application
process still receives those keys. Using managed identity directly for supported services
would further reduce secret exposure.

### 8. Could managed identity replace those service API keys completely?

For services and SDK operations supporting Microsoft Entra authentication, yes, with suitable
RBAC roles. I would migrate Search and supported cognitive services incrementally, test
permissions, and retain keys only where the selected API currently requires them.

### 9. Why are the backend and frontend publicly accessible?

Public ingress makes the portfolio demo easy to review. It is a deliberate convenience
trade-off, not the production security target. A real deployment would normally expose only the
frontend or gateway and keep FastAPI private.

### 10. What is the security purpose of CORS?

CORS tells browsers which origins may read cross-origin responses. It reduces unwanted browser
integration but does not authenticate users or stop scripts and tools from calling a public API
directly.

### 11. Does CORS prevent someone from directly calling the public API?

No. CORS is enforced by browsers, not by the server as identity verification. `curl`, scripts,
or another backend can still call the endpoint. Authentication, authorization, rate limits,
and network controls are required.

### 12. What abuse is possible because `/upload` is public and unauthenticated?

An attacker could trigger Document Intelligence, PII, embedding, and indexing costs, repeatedly
replace the shared document, or consume worker capacity. File-size validation helps but does
not solve authorization or quota abuse.

### 13. Why is `/companies/import` disabled while `/upload` remains available?

Stage 9 explicitly closed the largest new anonymous paid-ingestion risk, but `/upload` is an
older demonstration path and remains a known gap. For production consistency, I would
authenticate, rate-limit, or disable both paid mutation endpoints.

### 14. How would you add tenant isolation?

Every document and chunk would carry a tenant ID enforced by backend-generated filters. Uploads
would use tenant-specific object storage and index scope, authorization would be checked on
every request, and users could never supply an unrestricted tenant filter themselves.

### 15. How was the accidentally exposed Azure AI Language key handled?

The incident was documented, the malformed local `.env` line was repaired without printing
values, and the Azure key was regenerated. The new value was moved to Key Vault and local
configuration through a non-printing temp-file workflow.

---

## 14. Deployment and reliability

### 1. Why are the frontend and backend deployed as separate containers?

They use different runtimes, scale independently, and have different security responsibilities.
The frontend serves Next.js and proxies browser traffic; the backend owns Python AI logic and
credentials. Separate images keep each runtime focused.

### 2. What is stored in Azure Container Registry?

ACR stores versioned backend and frontend OCI container images. Container Apps pulls those
images using managed identity. Source secrets and local data are excluded by Docker ignore
rules and runtime configuration.

### 3. Why do both Container Apps scale to zero?

Portfolio traffic is intermittent, so keeping replicas running continuously would waste money.
Scale-to-zero removes compute charges while idle. The trade-off is a cold start on the first
request after inactivity.

### 4. What user-experience problem can scale-to-zero create?

The first request may wait for a container to start, making the application appear slow or
unavailable. Server-side frontend calls can also wait on a cold backend. Production options
include one minimum replica, warm-up traffic, timeouts, and clear loading feedback.

### 5. Why did `az acr build` not work for this subscription?

ACR Tasks returned `TasksOperationsNotAllowed`, a restriction seen on some new or credit-based
subscriptions. I isolated the limitation and used local Docker builds plus direct registry
pushes rather than claiming cloud builds were active.

### 6. Why were images built locally instead?

Direct Docker push uses normal registry storage and was not affected by the ACR Tasks
restriction. It allowed deployment to continue, although it is a manual workaround rather than
the desired CI build path.

### 7. What risk comes from relying on a developer's local Docker installation?

Builds depend on one workstation's availability and process, are harder to audit, and may not
be reproducible. A CI runner should build from a commit, run tests and scans, generate
provenance, and push immutable images.

### 8. Why use versioned image tags instead of repeatedly pushing `latest`?

Container Apps did not create a new revision when the image reference string remained
`:latest`, even after the digest changed. Versioned tags such as `v4` and `v5` force a real
deployment and make rollback targets identifiable.

### 9. What happened when old and new Container App revisions briefly served traffic?

During the Content Safety rollout, a request reached the still-warm old revision and returned
200 before traffic fully settled on the new revision. Waiting and deactivating the stale
revision resolved it, showing that cutover is not instantaneous.

### 10. How would you implement readiness checks before shifting production traffic?

I would deploy a new revision without full traffic, verify health, dependencies, schema
compatibility, and critical queries, then increase traffic gradually. Automated checks would
stop promotion and route traffic back if thresholds fail.

### 11. Why was the backend not redeployed for the frontend version 5 hotfix?

The backend `/companies`, `/ask`, citations, and CORS behavior were already correct. The defect
was frontend initialization, so only the frontend image changed. Avoiding an unnecessary
backend rollout reduced risk.

### 12. How would you automate build, test, push, and deployment?

A GitHub Actions pipeline would build both images from a commit, run Python, TypeScript, unit,
integration, and browser tests, scan dependencies and images, push immutable tags, deploy
revisions, run smoke tests, and promote or roll back traffic.

### 13. Why is there no infrastructure-as-code implementation yet?

The project prioritized learning and verifying each Azure service through a small portfolio
budget. Manual creation proved the architecture, but Bicep or Terraform is still required for
repeatable environments, drift control, review, and disaster recovery.

### 14. How would you perform a zero-downtime search-schema migration?

For additive compatible fields, I can update the existing schema and backfill gradually. For
breaking changes, I would build a versioned index, ingest and verify it, switch an index alias
or configuration pointer, monitor, and retain the old index for rollback.

### 15. What disaster-recovery plan would you use if the search index were deleted?

The SEC manifests and authoritative source URLs make permanent filings reproducible. I would
recreate the schema from code, download or read durable source files, re-embed, restore the
index, and validate counts and golden questions. Private uploads require separate durable
storage and backup policy.

---

## 15. Difficult recruiter and behavioral questions

### 1. What was the hardest problem you encountered?

The hardest work was diagnosing failures that crossed service boundaries, especially the Stage
9 browser defect. Every individual HTTP check looked healthy, but the user-visible selector was
empty. Logs and a real browser-path analysis led to server rendering and same-origin proxying.

### 2. What architectural decision would you change if you started again?

I would define the company and filing metadata contract at the beginning, even for one company.
The Apple-only schema created a later migration with null legacy metadata and quota pressure
that could have been avoided.

### 3. Tell me about a defect that passed your original testing.

Frontend v4 passed image builds, backend tests, direct production API calls, asset checks, and
HTTP smoke tests, yet the hydrated browser never fetched companies. A user screenshot exposed
the gap, and I added server-rendered initial data plus a proxy.

### 4. Why didn't your tests catch the blank company selector?

I verified components rather than the complete browser experience. I had no production-build
Playwright test asserting that companies appeared after hydration. I converted that lesson into
a specific end-to-end testing requirement.

### 5. What did the frontend hydration incident teach you?

Successful APIs and static HTML do not guarantee a working application. Client initialization,
cross-origin behavior, cold starts, and hydration must be tested through the same path the user
executes.

### 6. Tell me about the secret-exposure incident and your response.

A debugging command printed a Language API key after two `.env` lines were accidentally joined.
I treated it as compromise, repaired the file without reprinting it, rotated the Azure key, and
strengthened the non-printing secret workflow.

### 7. What was the biggest compromise caused by budget limits?

The Basic Search tier constrains vector capacity, and the fine-tuned model cannot remain
deployed because Standard hosting bills hourly. I made those boundaries visible, disabled
anonymous imports, and designed graceful offline behavior.

### 8. Which feature is most over-engineered, and how do you defend it?

PySpark for five filings is the clearest candidate. It is not operationally necessary at that
scale; its purpose is to demonstrate a tracked batch architecture. I defend it by stating that
limitation plainly and showing the Databricks production path.

### 9. Is it accurate to call this application enterprise-grade?

It contains enterprise-grade patterns such as Key Vault, managed identity, telemetry,
evaluation, and documented decisions. It is not a complete enterprise product because it lacks
authentication, tenant isolation, private networking, automated delivery, and full resilience.

### 10. Can you claim that it produces “no hallucinations”?

No absolute claim is defensible. RAG, restrictive prompts, citations, and evaluation reduce and
measure hallucination risk, but retrieval can miss evidence and models can misinterpret it. I
would use “grounded answers with citations” instead.

### 11. What is the most important known retrieval weakness?

Unfiltered questions spanning several filings can miss a required chunk because retrieval is
fixed at five results. The golden set caught an incorrect highest-net-income answer when the
FY2025 evidence was absent.

### 12. Which technical debt item presents the greatest risk?

Public unauthenticated mutation endpoints and shared upload state create cost, abuse, and data
isolation risk. Before broader use, I would disable or protect upload, add identity and quotas,
and move ingestion to tenant-scoped background jobs.

### 13. What would you prioritize with one additional week?

I would finish Stage 9 documentation and ADR, add Microsoft and isolation cases to the golden
set, add Playwright production-path tests, and protect or disable public upload. Those changes
improve credibility and risk more than another visible feature.

### 14. What would you remove if you needed to simplify the project?

I would separate the fine-tuned classifier and local Spark demonstration from the deployed
product narrative. The core story would remain multi-company SEC ingestion, filtered hybrid
RAG, citations, evaluation, security, and deployment.

### 15. What did this project teach you that a tutorial could not?

It taught me that production failures live between components: quotas during migration,
dependency conflicts, asynchronous deletion, stale revisions, browser hydration, secret
handling, and cost controls. The strongest evidence is how I diagnosed and documented those
failures, not only the happy-path code.

---

## Practice guidance

For a recruiter screen, practice two- or three-sentence versions of each answer. For a technical
panel, expand answers using this pattern:

1. State the requirement.
2. Explain the decision.
3. Name the alternative.
4. Describe the accepted trade-off.
5. Provide a measured result or incident from FilingsIQ.
