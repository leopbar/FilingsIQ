"""
S4.1 -- Download and inspect the CUAD dataset (SQuAD-format JSON).

CUAD (Contract Understanding Atticus Dataset):
  510 real contracts, 41 expert-labeled clause categories.
  Source: original CUAD_v1.json from the Atticus Project GitHub repo.
  (The HuggingFace version was reformatted to raw PDFs in 2025; we use the
  original SQuAD-format JSON which has the labeled clause spans.)

Downloads CUAD_v1.json (~33 MB) to backend/data/cuad/ on first run.
Subsequent runs use the cached file.
"""
import json
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data" / "cuad"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Download from Zenodo if not already cached:
#   https://zenodo.org/api/files/08615d53-fa14-438d-b6f3-9533061a2532/CUAD_v1.zip
# Extract CUAD_v1/CUAD_v1.json from the zip and place it here.
ZENODO_URL = (
    "https://zenodo.org/api/files/08615d53-fa14-438d-b6f3-9533061a2532/CUAD_v1.zip"
)
JSON_PATH = OUT_DIR / "CUAD_v1.json"

# -- 1. Download if not already cached ----------------------------------------
if JSON_PATH.exists():
    print(f"Using cached {JSON_PATH} ({JSON_PATH.stat().st_size // 1024} KB)")
else:
    import io, zipfile
    print(f"Downloading CUAD_v1.zip from Zenodo (~101 MB) ...")
    zip_bytes = urllib.request.urlopen(ZENODO_URL).read()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        with z.open("CUAD_v1/CUAD_v1.json") as src, open(JSON_PATH, "wb") as dst:
            dst.write(src.read())
    print(f"Saved to {JSON_PATH} ({JSON_PATH.stat().st_size // 1024} KB)\n")

# -- 2. Parse -----------------------------------------------------------------
print("Parsing CUAD_v1.json ...")
with open(JSON_PATH, encoding="utf-8") as f:
    cuad = json.load(f)

contracts = cuad["data"]
print(f"Total contracts : {len(contracts)}")

# -- 3. Flatten to (clause_text, category) rows -------------------------------
rows = []          # rows where the clause IS present
absent_count = 0
categories = set()

for contract in contracts:
    title = contract["title"]
    for para in contract["paragraphs"]:
        for qa in para["qas"]:
            category = qa["question"]
            categories.add(category)
            if qa["answers"]:
                clause_text = qa["answers"][0]["text"].strip()
                if clause_text:
                    rows.append({
                        "title": title,
                        "category": category,
                        "clause_text": clause_text,
                    })
            else:
                absent_count += 1

print(f"Unique clause categories : {len(categories)}")
print(f"Present clause rows      : {len(rows):,}")
print(f"Absent clause rows       : {absent_count:,}")
print(f"Total QA pairs           : {len(rows) + absent_count:,}")

# -- 4. Print the 41 category short-names -------------------------------------
def short_label(full_question):
    """Extract the label name from inside the double-quotes in the CUAD question."""
    parts = full_question.split('"')
    if len(parts) >= 3:
        return parts[1]
    return full_question[:60]

labels_set = sorted({short_label(cat) for cat in categories})
print(f"\nThe {len(labels_set)} CUAD categories (short names):")
for i, label in enumerate(labels_set, 1):
    print(f"  {i:2d}. {label}")

# -- 5. Sample 3 present-clause rows ------------------------------------------
print("\n--- 3 sample present-clause rows ---")
for row in rows[:3]:
    label = short_label(row["category"])
    excerpt = row["clause_text"][:200]
    ellipsis = " ..." if len(row["clause_text"]) > 200 else ""
    print(f"\n  Contract : {row['title'][:60]}")
    print(f"  Category : {label}")
    print(f"  Clause   : {excerpt}{ellipsis}")

# -- 6. Save 5-row sample -----------------------------------------------------
sample_path = OUT_DIR / "sample_5.json"
sample_out = [
    {"category": short_label(r["category"]), "clause_text": r["clause_text"]}
    for r in rows[:5]
]
with open(sample_path, "w", encoding="utf-8") as f:
    json.dump(sample_out, f, indent=2, ensure_ascii=False)
print(f"\nSaved 5-row sample -> {sample_path}")

# -- 7. Save short category label list ----------------------------------------
labels_path = OUT_DIR / "category_labels.json"
with open(labels_path, "w", encoding="utf-8") as f:
    json.dump(labels_set, f, indent=2)
print(f"Saved {len(labels_set)} category labels -> {labels_path}")

print("\nS4.1 dataset inspection complete.")
