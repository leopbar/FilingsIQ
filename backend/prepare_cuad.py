"""
S4.2 — Prepare CUAD fine-tuning data as chat-format JSONL.

Reads CUAD_v1.json, extracts present-clause rows, formats each as an
OpenAI chat-format example (system + user + assistant), and writes
train / val / test splits to backend/data/cuad/.

Run once:  python prepare_cuad.py
"""

import json
import random
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent / "data" / "cuad"
CUAD_PATH  = DATA_DIR / "CUAD_v1.json"
LABELS_PATH = DATA_DIR / "category_labels.json"

TRAIN_PATH = DATA_DIR / "train.jsonl"
VAL_PATH   = DATA_DIR / "val.jsonl"
TEST_PATH  = DATA_DIR / "test.jsonl"

# Azure OpenAI fine-tuning rejects examples above ~65k tokens.
# 4,000 chars ≈ 1,000 tokens — safely within per-example limits and
# keeps training cost predictable.
MAX_CLAUSE_CHARS = 4_000

SYSTEM_MSG = (
    "You are a legal contract analyst. "
    "Given a clause extracted from a contract, classify it into exactly one "
    "of the 41 CUAD clause categories. "
    "Reply with the category name only — no explanation."
)

SPLIT = {"train": 0.80, "val": 0.10, "test": 0.10}
SEED  = 42

# ── load ──────────────────────────────────────────────────────────────────────
print("Loading CUAD_v1.json …")
with open(CUAD_PATH, encoding="utf-8") as f:
    cuad = json.load(f)

with open(LABELS_PATH, encoding="utf-8") as f:
    valid_labels = set(json.load(f))

# ── extract present-clause rows ───────────────────────────────────────────────
# CUAD is SQuAD-format: data → paragraphs → qas → answers.
# Each question title encodes the category; "answers" is non-empty for
# present clauses.
examples = []
skipped_label = 0

for article in cuad["data"]:
    for para in article["paragraphs"]:
        for qa in para["qas"]:
            if not qa.get("answers"):
                continue  # absent clause — skip

            # Question title: "Highlight the parts … related to "Category" …"
            # The category is the part between the last set of quotes.
            title = qa.get("question", "")
            # Extract text between last pair of double-quotes
            parts = title.split('"')
            if len(parts) < 2:
                skipped_label += 1
                continue
            category = parts[-2].strip()

            if category not in valid_labels:
                skipped_label += 1
                continue

            # Use the first answer span as the clause text
            clause = qa["answers"][0]["text"].strip()
            if not clause:
                continue

            # Truncate long clauses
            if len(clause) > MAX_CLAUSE_CHARS:
                clause = clause[:MAX_CLAUSE_CHARS]

            examples.append({
                "messages": [
                    {"role": "system",    "content": SYSTEM_MSG},
                    {"role": "user",      "content": clause},
                    {"role": "assistant", "content": category},
                ]
            })

print(f"  Present-clause examples extracted : {len(examples):,}")
print(f"  Skipped (unrecognised label)      : {skipped_label:,}")

# ── shuffle & split ───────────────────────────────────────────────────────────
random.seed(SEED)
random.shuffle(examples)

n       = len(examples)
n_train = int(n * SPLIT["train"])
n_val   = int(n * SPLIT["val"])

train_set = examples[:n_train]
val_set   = examples[n_train : n_train + n_val]
test_set  = examples[n_train + n_val :]

print(f"\nSplit (seed={SEED}):")
print(f"  train : {len(train_set):,}")
print(f"  val   : {len(val_set):,}")
print(f"  test  : {len(test_set):,}")

# ── write JSONL ───────────────────────────────────────────────────────────────
def write_jsonl(path: Path, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(rows):,} rows -> {path}")

print("\nWriting JSONL files …")
write_jsonl(TRAIN_PATH, train_set)
write_jsonl(VAL_PATH,   val_set)
write_jsonl(TEST_PATH,  test_set)

print("\nDone. S4.2 complete.")
print("Next: S4.3 — zero-shot baseline eval on test.jsonl")
