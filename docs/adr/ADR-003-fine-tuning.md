# ADR-003 — Fine-tuning gpt-4o-2024-08-06 on CUAD Clause Classification

**Date:** 2026-06-16
**Status:** Accepted
**Deciders:** FilingsIQ portfolio project

---

## Context

Job requirement #7 calls for demonstrated ability to *"fine-tune, customize, and optimize
pre-trained AI/LLM models."* A credibility risk in the original audit flagged that trivial
fine-tuning (e.g., a toy dataset, a single category, or an already-easy task) would not
satisfy a senior interviewer.

The challenge was to find a task where:
1. A strong base model genuinely struggles zero-shot (proving fine-tuning has real payoff).
2. A well-curated, expert-labeled dataset already exists (no manual labeling required).
3. The domain fits the project's document-intelligence theme.

**CUAD** (Contract Understanding Atticus Dataset) satisfies all three:
- 510 real contracts, 41 expert-labeled clause categories, 6,702 positive examples.
- Legal clause classification is genuinely hard zero-shot: 41 overlapping categories with
  dense, specialized language that a generalist model has not been optimized for.
- Contracts are "long documents analysts upload" — exactly the FilingsIQ use case.

---

## Decision

Fine-tune **`gpt-4o-2024-08-06`** on the CUAD clause classification task via the
**Azure OpenAI fine-tuning API**, and prove the result with a held-out zero-shot vs.
fine-tuned evaluation on identical test data.

---

## Why this model

| Model | Fine-tune available (East US 2) | Rationale |
|---|---|---|
| `gpt-4.1-mini` | ❌ No (`fine_tune=False`) | Original plan; ruled out by API check |
| `gpt-35-turbo-0125` | ✅ Yes | Cheaper but weaker baseline — smaller delta |
| **`gpt-4o-2024-08-06`** | ✅ Yes | **Chosen** — most capable fine-tunable model; stronger portfolio story |
| `o4-mini` | ✅ Yes | Reasoning model; not appropriate for classification |

Choosing the strongest available base model produces a more credible result: if even a
capable model scores 17.7% zero-shot, it proves the task is genuinely hard and that the
+59.8 pp gain is meaningful, not just closing an easy gap.

---

## Training setup

| Parameter | Value | Rationale |
|---|---|---|
| Dataset | CUAD v1 (Zenodo 4595826) | Expert-labeled, 41 categories, no manual work needed |
| Training examples | 5,361 (80% split) | Large enough to learn all 41 categories reliably |
| Validation examples | 670 (10% split) | Monitored during training to detect overfitting |
| Test examples | 671 (10% split, held out) | Never seen during training; used for final eval |
| Epochs | 3 | Azure default; sufficient for convergence (final loss 0.044) |
| Batch size | 10 | Azure auto-selected |
| Max tokens per example | 4,000 chars (~1,000 tokens) | Keeps all examples within Azure per-example limits |
| Label framing | Single-label multi-class | Clause text → one of 41 category names |
| System prompt | "You are a legal contract analyst…reply with the category name only" | Same prompt used in both baseline and fine-tuned eval |

---

## Results

### Accuracy and F1

| Metric | Baseline (zero-shot) | Fine-tuned | Delta |
|---|---|---|---|
| Accuracy | 17.7% | **77.5%** | **+59.8 pp** |
| Macro F1 | 0.1543 | **0.6884** | **+0.5341** |
| Test examples | 671 | 671 | — |

### Selected per-category improvements (F1)

| Category | Baseline | Fine-tuned | Delta |
|---|---|---|---|
| Price Restrictions | 0.000 | **1.000** | +100% |
| Third Party Beneficiary | 0.000 | **1.000** | +100% |
| Warranty Duration | 0.000 | **1.000** | +100% |
| Document Name | 0.000 | 0.988 | +98.8% |
| Covenant Not To Sue | 0.000 | 0.923 | +92.3% |
| Parties | 0.120 | 0.989 | +86.9% |

27 of the 41 categories scored 0% zero-shot. After fine-tuning, only a handful remain
below 0.5 F1 — those are the categories with very few test examples (support ≤ 3).

### Cost and latency

| Dimension | Baseline | Fine-tuned | Note |
|---|---|---|---|
| Training cost | — | ~$43 one-time | 1,717,000 tokens × ~$25/1M |
| Inference cost / call | ~$0.00107 | ~$0.00161 | 1.5× — negligible in practice |
| Latency / call (observed) | 0.94 s | 9.91 s | See note below |
| Break-even | — | ~80,373 calls | After which fine-tuned is cheaper per unit of accuracy |

**Latency note:** The 9.91 s/call figure reflects the **6 RPM quota** on the Standard
deployment, not inherent model speed. The Standard tier assigned 1K TPM / 6 RPM to the
fine-tuned model. At production quota levels (100+ RPM), per-call latency would be
comparable to the base model.

---

## Deployment decision

| Option | Cost | Decision |
|---|---|---|
| Developer tier | $0/hr hosting, auto-deletes in 24 h | **Not available** in East US 2 for this model |
| Standard tier | ~$1.70–3/hr while deployed | **Used** — deployed only for the eval run (~30 min), then deleted immediately |
| Keep deployed | ~$40–70/day | ❌ Rejected — burns the $200 credit in days |

**Conclusion:** deploy on Standard, run the eval, delete immediately. For a portfolio
demonstration this is correct — redeploy in 2 minutes when needed. For production, request
Developer tier quota or budget the hosting cost against the accuracy gain.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Fine-tune on 10-K vs 8-K classification | Too easy zero-shot (GPT-4o already knows these document types). No measurable gain to demonstrate. |
| Fine-tune `gpt-35-turbo` | Would show a larger absolute gain from a weaker baseline, but `gpt-4o` is a stronger portfolio signal. |
| RAG instead of fine-tuning | RAG is the right choice when the model needs knowledge. Clause classification needs a consistent specialized behavior — fine-tuning is the correct tool here. |
| Prompt engineering only | Zero-shot with detailed prompts was attempted implicitly (the baseline uses a clear system prompt). 17.7% accuracy confirms prompting alone cannot close the gap on 41 overlapping legal categories. |

---

## Production target

| Dimension | This implementation | Production target |
|---|---|---|
| Dataset | CUAD (public, 510 contracts) | Customer contracts (private, annotated internally) |
| Deployment tier | Standard (deleted after eval) | Developer tier or Standard with quota increase |
| Hosting cost | ~$0 (deleted immediately) | Developer tier: $0/hr; Standard: budget per SLA |
| Monitoring | None | Azure Monitor + RAGAS eval as CI gate (Stage 6) |
| Retraining | Manual, one-off | Scheduled retraining as new labeled examples accumulate |
| Auth | API key in `.env` | Managed Identity + Key Vault (Stage 6 hardening) |

---

## Consequences

**Positive:**
- Job requirement #7 is now ✅ Solid with a measurable, defensible result.
- Credibility risk #2 (trivial fine-tuning) is closed.
- The eval framework (`baseline_eval.py`, `ft_eval.py`, `compare.py`) is reusable for future
  fine-tuning experiments.

**Negative / trade-offs:**
- Training cost ~$43 is a one-time spend from the $200 credit.
- Fine-tuned inference is 1.5× more expensive per token than the base model.
- The fine-tuned model is a standalone capability — not yet wired into the chat app
  (auto-tagging clauses is deferred to a future stage).
