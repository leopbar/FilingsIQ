# ADR-005 — Deployment to Azure Container Apps with Key Vault + Managed Identity

**Date:** 2026-06-19
**Status:** Accepted
**Deciders:** FilingsIQ portfolio project

---

## Context

Stage 6.5 turns the locally-running chat app into a polished, **live, publicly accessible**
deployment — covering the *"build and deploy enterprise-grade application"* gap (job
requirements #1/#2). Both the FastAPI backend and the Next.js frontend needed to run as
containers in Azure, with a real public URL, and without ever putting Azure API keys in
plaintext anywhere a process listing, command-line history, or chat transcript could expose
them.

---

## Decision

Deploy both services to **Azure Container Apps**, with images built locally and pushed to
**Azure Container Registry (ACR)**, and all sensitive configuration sourced from **Azure Key
Vault** via each Container App's **system-assigned managed identity** — never as literal
command-line arguments.

```
Local Docker build
      │  docker build (backend, frontend)
      ▼
Azure Container Registry (filingsiqacr, Basic tier)
      │  docker push
      ▼
Azure Container Apps Environment (filingsiq-env)
      │
      ├── filingsiq-backend   (FastAPI, scale 0→2, ACR pull via managed identity)
      │       │  reads secrets at runtime via
      │       ▼
      │   Azure Key Vault (filingsiq-kv)
      │     - Key Vault Secrets User role → backend's managed identity
      │     - 8 secrets: OpenAI / Search / DocIntel / Language endpoints + keys
      │
      └── filingsiq-frontend  (Next.js standalone, scale 0→2, ACR pull via managed identity)
              NEXT_PUBLIC_API_URL baked in at build time → backend's live FQDN
```

Live URLs:
- Frontend: `https://filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io`
- Backend: `https://filingsiq-backend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io`

---

## Why Key Vault + Managed Identity instead of plain Container Apps secrets

Azure Container Apps supports two ways to hand a container its secrets:

1. **Plain secrets** — pass `--secrets name=value` directly on `az containerapp create/update`.
   Simple, but the *value* travels as a literal command-line argument, visible in OS process
   listings (`ps`/Task Manager) for the lifetime of the process, and easy to accidentally paste
   into a chat log or shell history.
2. **Key Vault references** — store the value once in Key Vault, then tell the Container App
   `keyvaultref:<secret-URI>,identityref:system`. The app fetches the value itself at runtime
   using its own Azure AD identity. The value never appears in any CLI invocation.

This project's working agreement is explicit: *"The Azure API key lives ONLY in `backend/.env`
... never paste it in chat, never commit it."* Approach #1 violates that the moment a deploy
command runs. In fact, during this deployment, an automated safety check in the development
harness caught and blocked a first attempt that would have passed real API keys as plain
`--secrets` arguments — a useful real-world confirmation that this is a genuine risk, not a
theoretical one.

**Decision: route every sensitive value through Key Vault.** Concretely:

- `backend/push_secrets_to_keyvault.ps1` reads `backend/.env` and writes each value to a local
  temp file, then runs `az keyvault secret set --file <tempfile>` — the secret *value* goes
  through the file, never the command line; the file path is the only thing in argv. The temp
  file is deleted immediately after. This script itself is safe to keep in source control: it
  contains logic, not secrets.
- The deploying user is granted **Key Vault Secrets Officer** (to write secrets); the backend
  Container App's system-assigned identity is granted **Key Vault Secrets User** (to read them).
- Container App secrets are defined as `keyvaultref:...,identityref:system` and referenced by
  application env vars (`AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key`, etc.).

This closes a meaningful chunk of **credibility risk #1** ("enterprise-grade" vs. free-tier
shortcuts) ahead of schedule — Managed Identity and Key Vault were originally flagged as a
"still to do" item, not something expected this early in the project.

---

## Why ACR pulls use managed identity, not the registry admin password

The same reasoning applies to registry authentication. Rather than enabling the ACR admin
account and passing its username/password to `--registry-username`/`--registry-password`
(another literal secret on the command line), both Container Apps were created with
`--registry-identity system`. Azure CLI automatically grants the **AcrPull** RBAC role to the
Container App's managed identity on the target registry. The registry password is never
generated into a script, file, or command at any point in this deployment.

---

## Two Azure/CLI bugs discovered and worked around

**1. `az acr build` (cloud-side image build) is blocked on this subscription.**

```
ERROR: TasksOperationsNotAllowed — ACR Tasks requests for the registry ... are not permitted.
```

This is a known fraud-prevention restriction Microsoft applies to some new or free-credit
subscriptions; lifting it requires filing an Azure support ticket. **Workaround:** build both
images locally with Docker Desktop (already proven working in S6.5.5) and `docker push` them
to ACR directly. This uses plain registry storage and is unaffected by the Tasks restriction.

**2. `az containerapp create --yaml <file>` is broken in Azure CLI 2.87.0.**

Every attempt — including a minimal manifest with a public test image and zero secrets —
failed identically:

```
ERROR: Bad Request({"errors":{"$":["The JSON value could not be converted to System.Boolean.
Path: $ | LineNumber: 0 | BytePositionInLine: 4."]}})
```

A smoke test with the same public image using plain CLI flags (`--image`, `--target-port`,
`--ingress`) succeeded immediately, isolating the bug to the `--yaml` code path specifically,
not the resource definition itself or this subscription's permissions. **Workaround:** deploy
with explicit flags throughout, and use `az containerapp secret set` / `az containerapp update
--set-env-vars` for anything that doesn't fit on the `create` line.

---

## Other decisions

- **Scale to zero (`--min-replicas 0 --max-replicas 2`)** on both apps. No requests means no
  running container means no compute charge — consistent with this project's pattern of keeping
  always-on costs near zero (e.g., the AI Search ~$2.50/day reminder, the FT deployment that's
  spun up only for demos).
- **`NEXT_PUBLIC_API_URL` baked in at Docker build time**, not runtime. Next.js inlines
  `NEXT_PUBLIC_*` variables into the client-side JavaScript bundle during `next build`, so the
  frontend image had to be built (and rebuilt, once the real backend URL was known) with
  `--build-arg NEXT_PUBLIC_API_URL=https://filingsiq-backend...`. This is why backend deployment
  had to happen *before* the final frontend build — order matters.
- **Image tags must change to force a real rollout.** Re-pushing the same `:latest` tag to ACR
  and re-running `az containerapp update --image ...:latest` does **not** create a new revision
  — Container Apps treats the request as a no-op if the image *reference string* is unchanged,
  even though the underlying digest changed. Pushing a new tag (`:v2`) was required to force
  Container Apps to pull the updated image and roll out a new revision. This was discovered
  while deploying a CORS fix to the backend — the first attempt silently kept serving the old
  image until the tag was bumped.
- **CORS updated for the live frontend origin** in `backend/main.py`, alongside the existing
  `localhost:3000`/`3001` entries for local dev. Verified directly via an `Origin`-header HTTP
  request that `Access-Control-Allow-Origin` correctly echoes the live frontend's URL.

---

## End-to-end verification (S6.5.7)

All four Stage 6.5 features were tested directly against the live URLs (not localhost):

| Feature | Live test | Result |
|---|---|---|
| Chat (no filter) | `POST /ask`, no `year` | 200, grounded answer with citations |
| Year filter | `POST /ask`, `"year":"FY2023"` | Correctly scoped to FY2023/2022/2021 only |
| Clause classifier offline path | `POST /classify` | `{"category":"","available":false}` — graceful, no crash |
| PDF upload, unfamiliar document | Uploaded **DLH Holdings Corp.** FY2025 10-K (an obscure small-cap, chosen specifically so a correct answer could only come from grounding) through the live frontend | `POST /ask` with `"year":"upload"` returned DLH's actual business description (federal-government health/IT/cyber services) — proof the live pipeline is grounded in the uploaded document, not GPT-4o's prior knowledge |

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Azure App Service (Web App for Containers) | Older PaaS model; Container Apps is the more current Azure-native pattern for microservices and has built-in scale-to-zero, which App Service's cheaper tiers lack. |
| Azure Kubernetes Service (AKS) | Massive overkill for two containers; adds cluster management overhead with no portfolio benefit at this scale. |
| Plain `--secrets` + ACR admin password | Rejected — see "Why Key Vault" above. Real values would sit in command-line argv. |
| Keep `:latest` tag, force restart instead of re-deploy | Tried first; `az containerapp revision restart` does not re-pull the image, so a stale revision kept running. Versioned tags are required. |

---

## Production target (beyond this portfolio deployment)

| Dimension | This implementation | Larger-scale production target |
|---|---|---|
| Image builds | Local Docker, manual push | CI/CD pipeline (GitHub Actions) building and pushing on every merge |
| ACR builds | Blocked on this subscription (Tasks disabled) | Support ticket to lift the restriction, or build via GitHub Actions runners instead of `az acr build` |
| Secrets | Key Vault + per-app managed identity (already production-grade) | Same pattern, with secret rotation policies and Key Vault diagnostic logging to Azure Monitor |
| Networking | Public ingress on both apps | Private VNet integration, backend reachable only from the frontend's subnet |
| Scaling | 0→2 replicas, default rules | KEDA-based custom scaling rules (HTTP concurrency, queue depth) |
| Custom domain / TLS | Default `*.azurecontainerapps.io` | Custom domain with managed TLS certificate |

---

## Consequences

**Positive:**
- Job requirements #1/#2 ("build and deploy enterprise-grade application") are now ✅ closed —
  this is the first stage with a real, public, working URL.
- Credibility risk #1 (free-tier vs. enterprise-grade) gets a genuine, working Managed
  Identity + Key Vault implementation, not just an ADR table promising it for later.
- Two real-world Azure/CLI bugs were diagnosed methodically (isolated with minimal
  reproductions) rather than worked around blindly — a stronger signal than a deployment that
  "just worked."

**Negative / trade-offs:**
- `az acr build` being blocked means there is no cloud-native CI build path today; rebuilding
  requires Docker Desktop running locally. A GitHub Actions pipeline would remove this
  dependency and is the natural next step if this project continues past the portfolio stage.
- Both apps currently have public ingress with no VNet restriction — acceptable for a portfolio
  demo, not the final word on network security for a real production deployment.
- The clause-classifier fine-tuned deployment remains intentionally offline by default to avoid
  hourly billing; the live demo only shows the graceful "unavailable" path unless it's spun up
  beforehand for a specific demo session.
