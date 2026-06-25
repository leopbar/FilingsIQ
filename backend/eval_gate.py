"""
eval_gate.py — pass/fail gate over backend/data/eval/ragas_results.json.

Thresholds are deliberately category-aware, based on root-cause analysis of the
first real run (see PROJECT_LOG.md S7.3):

- "lookup" faithfulness has a structural ~0.5 floor on table-derived facts: Document
  Intelligence flattens tables to plain text, and RAGAS's strict NLI faithfulness
  judge sometimes can't mechanically verify a number against the linearized table
  even when the answer is correct and the number is genuinely present (confirmed by
  manual inspection of q07's sources). Threshold is set below the observed average,
  not at 0.9+, to avoid gating on this known artifact rather than a real regression.
- "negative" questions (the RAG correctly says "not in the document") score
  answer_relevancy == 0.0 by design: the metric reverse-engineers a question from the
  answer and compares it to the original question, and a refusal doesn't resemble a
  question. This is excluded from gating entirely for the negative category — it is
  not a quality signal here.
- "comparison" questions are split by whether they need only a single filing's
  built-in multi-year table (comparison_single_doc, e.g. "Mac 2024 vs 2023" — both
  years are in the same retrieved chunk) vs. true cross-filing synthesis with no year
  filter (comparison_cross_doc, e.g. "highest net income across FY2021-2025"). The
  cross-doc case is a known, real weakness (q16 answered the wrong year because
  top_k=5 missed the FY2025 chunk entirely) — thresholds there are lower and explicitly
  flagged as "monitor, not yet fixed" rather than silently treated as equally reliable.

Usage:
    venv-eval\\Scripts\\python eval_gate.py
Exit code 0 = pass, 1 = fail (suitable for a CI step).
"""

import json
import math
import sys
from pathlib import Path

RESULTS_PATH = Path(__file__).parent / "data" / "eval" / "ragas_results.json"

# metric -> threshold. A metric absent from a group's dict is reported but not gated.
THRESHOLDS = {
    "lookup": {
        "faithfulness": 0.6,
        "answer_relevancy": 0.9,
        "context_precision": 0.6,
        "context_recall": 0.8,
    },
    "comparison_single_doc": {
        "faithfulness": 0.8,
        "answer_relevancy": 0.8,
        "context_precision": 0.6,
        "context_recall": 0.8,
    },
    "comparison_cross_doc": {
        # Known weak spot (S7.3 root cause: top_k=5 misses chunks across 5 fiscal
        # years). Low bar catches total failure; the real fix is future work, not
        # this gate's job.
        "faithfulness": 0.4,
        "answer_relevancy": 0.7,
    },
    "negative": {
        # Must not hallucinate. answer_relevancy intentionally excluded (see module
        # docstring) and context metrics aren't meaningful for "not in the document".
        "faithfulness": 0.9,
    },
}


def group_key(row: dict) -> str:
    if row["category"] == "comparison":
        return "comparison_single_doc" if row["year"] is not None else "comparison_cross_doc"
    return row["category"]


def avg(rows: list[dict], metric: str):
    vals = [
        r[metric]
        for r in rows
        if r[metric] is not None and not (isinstance(r[metric], float) and math.isnan(r[metric]))
    ]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def main():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    per_question = data["per_question"]

    groups: dict[str, list[dict]] = {}
    for row in per_question:
        groups.setdefault(group_key(row), []).append(row)

    all_passed = True
    print(f"{'Group':<24}{'Metric':<20}{'Score':<10}{'Threshold':<12}Result")
    print("-" * 76)

    for group_name, thresholds in THRESHOLDS.items():
        rows = groups.get(group_name, [])
        if not rows:
            print(f"{group_name:<24}(no questions in this run)")
            continue
        for metric, threshold in thresholds.items():
            score, n = avg(rows, metric)
            if score is None:
                status = "SKIP (no data)"
            else:
                passed = score >= threshold
                all_passed = all_passed and passed
                status = "PASS" if passed else "FAIL"
            score_str = f"{score:.3f}" if score is not None else "n/a"
            print(f"{group_name:<24}{metric:<20}{score_str:<10}{threshold:<12}{status}")

    print("-" * 76)
    if all_passed:
        print("EVAL GATE: PASS")
        sys.exit(0)
    else:
        print("EVAL GATE: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
