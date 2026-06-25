"""
S4.3 — Zero-shot baseline evaluation on the CUAD test set.

Calls the base gpt-4o deployment (no fine-tuning) with the same system
prompt used in training, classifies each of the 671 test clauses, and
measures accuracy + macro F1 against the ground-truth labels.

Run from backend/:
    python baseline_eval.py

Outputs:
  backend/data/cuad/baseline_results.json   — final scores + per-category breakdown
  backend/data/cuad/baseline_checkpoint.jsonl — row-by-row predictions (resume-safe)
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI, RateLimitError

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────
DATA_DIR        = Path(__file__).parent / "data" / "cuad"
TEST_PATH       = DATA_DIR / "test.jsonl"
CHECKPOINT_PATH = DATA_DIR / "baseline_checkpoint.jsonl"
RESULTS_PATH    = DATA_DIR / "baseline_results.json"

# Same prompt used when building the training data (prepare_cuad.py)
SYSTEM_MSG = (
    "You are a legal contract analyst. "
    "Given a clause extracted from a contract, classify it into exactly one "
    "of the 41 CUAD clause categories. "
    "Reply with the category name only — no explanation."
)

DEPLOYMENT = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]  # gpt-4o

# ── helpers ───────────────────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
)


def classify(clause: str, retries: int = 5) -> str:
    """Call the base model; return the raw text of the assistant reply."""
    delay = 2.0
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SYSTEM_MSG},
                    {"role": "user",   "content": clause},
                ],
                temperature=0,
                max_tokens=20,  # category name is short; no explanation requested
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            if attempt == retries - 1:
                raise
            print(f"    [rate-limited] waiting {delay:.0f}s …")
            time.sleep(delay)
            delay *= 2
    return ""  # unreachable


def macro_f1(rows: list[dict]) -> tuple[float, dict]:
    """
    Compute overall accuracy + macro F1 from a list of
    {"truth": str, "pred": str} dicts.
    Returns (macro_f1_score, per_category_dict).
    """
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    correct = 0

    for r in rows:
        t, p = r["truth"], r["pred"]
        if t == p:
            correct += 1
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1

    accuracy = correct / len(rows) if rows else 0.0

    categories = set(r["truth"] for r in rows)
    per_cat = {}
    f1_scores = []
    for cat in sorted(categories):
        prec = tp[cat] / (tp[cat] + fp[cat]) if (tp[cat] + fp[cat]) else 0.0
        rec  = tp[cat] / (tp[cat] + fn[cat]) if (tp[cat] + fn[cat]) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_cat[cat] = {"precision": round(prec, 4),
                        "recall":    round(rec,  4),
                        "f1":        round(f1,   4),
                        "support":   tp[cat] + fn[cat]}
        f1_scores.append(f1)

    macro = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    return accuracy, macro, per_cat


# ── load test set ─────────────────────────────────────────────────────────────
test_rows = []
with open(TEST_PATH, encoding="utf-8") as f:
    for line in f:
        test_rows.append(json.loads(line))

print(f"Test set loaded: {len(test_rows):,} examples")

# ── load checkpoint (resume support) ─────────────────────────────────────────
done: dict[int, dict] = {}  # index → {truth, pred}
if CHECKPOINT_PATH.exists():
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            done[row["index"]] = row
    print(f"Checkpoint found: {len(done):,} rows already done — resuming.")

# ── main loop ─────────────────────────────────────────────────────────────────
checkpoint_fh = open(CHECKPOINT_PATH, "a", encoding="utf-8")

start_time = time.time()
total = len(test_rows)

try:
    for i, example in enumerate(test_rows):
        if i in done:
            continue

        truth = example["messages"][2]["content"]   # assistant turn = ground truth
        clause = example["messages"][1]["content"]  # user turn = clause text

        pred = classify(clause)

        row = {"index": i, "truth": truth, "pred": pred}
        done[i] = row
        checkpoint_fh.write(json.dumps(row) + "\n")
        checkpoint_fh.flush()

        elapsed = time.time() - start_time
        remaining = total - len(done)
        rate = len(done) / elapsed if elapsed > 0 else 1
        eta_s = remaining / rate if rate > 0 else 0

        print(
            f"  [{len(done):>3}/{total}]  "
            f"truth={truth!r:40s}  pred={pred!r}  "
            f"ETA {eta_s/60:.1f} min"
        )

        time.sleep(0.15)  # ~6–7 req/s — stays within typical TPM limits

finally:
    checkpoint_fh.close()

# ── compute metrics ───────────────────────────────────────────────────────────
all_rows = [done[i] for i in range(total)]
accuracy, macro, per_cat = macro_f1(all_rows)

elapsed_total = time.time() - start_time
results = {
    "model":        DEPLOYMENT,
    "stage":        "baseline_zero_shot",
    "n_examples":   total,
    "accuracy":     round(accuracy, 4),
    "macro_f1":     round(macro, 4),
    "elapsed_sec":  round(elapsed_total, 1),
    "per_category": per_cat,
}

with open(RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

# ── summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("BASELINE ZERO-SHOT RESULTS")
print("=" * 60)
print(f"  Model       : {DEPLOYMENT} (base, no fine-tuning)")
print(f"  Test examples: {total:,}")
print(f"  Accuracy    : {accuracy:.1%}")
print(f"  Macro F1    : {macro:.4f}")
print(f"  Elapsed     : {elapsed_total/60:.1f} min")
print(f"\nFull results saved to {RESULTS_PATH}")
print("\nNext: S4.4 — upload training files and start the fine-tuning job.")
