"""
ragas_eval.py — run the golden Q&A set through the live RAG pipeline (rag.ask())
and score the results with RAGAS (faithfulness, answer relevancy, context
precision, context recall), using Azure OpenAI gpt-4o as the judge LLM and
text-embedding-3-small as the judge embeddings.

Runs in backend/venv-eval (NOT the main backend/venv) — ragas pulls in an older
langchain/openai stack that conflicts with the main app's pinned versions.

Usage (from backend/, using the eval venv):
    venv-eval\\Scripts\\python ragas_eval.py
"""

import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
from ragas.run_config import RunConfig

import rag

GOLDEN_QA_PATH = Path(__file__).parent / "data" / "eval" / "golden_qa.jsonl"
RESULTS_PATH = Path(__file__).parent / "data" / "eval" / "ragas_results.json"


def load_golden_qa() -> list[dict]:
    rows = []
    with open(GOLDEN_QA_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_pipeline(rows: list[dict]) -> list[dict]:
    """Call rag.ask() for every golden question; attach the pipeline's answer + sources."""
    results = []
    for row in rows:
        print(f"[{row['id']}] {row['question']}")
        outcome = rag.ask(row["question"], year=row["year"])
        results.append({**row, "answer": outcome["answer"], "sources": outcome["sources"]})
    return results


def build_ragas_dataset(results: list[dict]) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=r["question"],
            retrieved_contexts=r["sources"],
            response=r["answer"],
            reference=r["expected_answer"],
        )
        for r in results
    ]
    return EvaluationDataset(samples=samples)


def main():
    load_dotenv()

    rows = load_golden_qa()
    results = run_pipeline(rows)

    dataset = build_ragas_dataset(results)

    judge_llm = LangchainLLMWrapper(
        AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            temperature=0,
        )
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        AzureOpenAIEmbeddings(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        )
    )

    # Low concurrency + generous timeout: the Azure OpenAI deployment here is a small
    # S0 tier and throttles hard under RAGAS's default 16 parallel workers.
    run_config = RunConfig(timeout=300, max_workers=2, max_wait=90)

    eval_result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=run_config,
    )

    scores_df = eval_result.to_pandas()

    per_question = []
    for i, row in enumerate(results):
        per_question.append(
            {
                "id": row["id"],
                "category": row["category"],
                "year": row["year"],
                "question": row["question"],
                "answer": row["answer"],
                "expected_answer": row["expected_answer"],
                "faithfulness": scores_df.loc[i, "faithfulness"],
                "answer_relevancy": scores_df.loc[i, "answer_relevancy"],
                "context_precision": scores_df.loc[i, "context_precision"],
                "context_recall": scores_df.loc[i, "context_recall"],
            }
        )

    def avg(rows_subset, metric):
        # Individual judge calls occasionally fail even after retries and land as
        # NaN (not None) in the scores dataframe — exclude those, not just missing values.
        vals = [
            r[metric]
            for r in rows_subset
            if r[metric] is not None and not (isinstance(r[metric], float) and math.isnan(r[metric]))
        ]
        return sum(vals) / len(vals) if vals else None

    metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    permanent = [r for r in per_question if r["year"] != "upload"]
    upload = [r for r in per_question if r["year"] == "upload"]

    summary = {
        "overall": {m: avg(per_question, m) for m in metrics},
        "permanent_apple_filings": {m: avg(permanent, m) for m in metrics},
        "upload_slot": {m: avg(upload, m) for m in metrics},
        "num_questions": len(per_question),
        "num_permanent": len(permanent),
        "num_upload": len(upload),
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_question": per_question}, f, indent=2)

    print("\n=== RAGAS summary (averages, 0-1 scale) ===")
    print(f"Overall ({summary['num_questions']} questions):")
    for m in metrics:
        print(f"  {m:20s} {summary['overall'][m]:.3f}")
    print(f"\nPermanent Apple filings ({summary['num_permanent']} questions):")
    for m in metrics:
        v = summary["permanent_apple_filings"][m]
        print(f"  {m:20s} {v:.3f}" if v is not None else f"  {m:20s} n/a")
    print(f"\nUpload slot ({summary['num_upload']} questions, staleness risk per S7.1):")
    for m in metrics:
        v = summary["upload_slot"][m]
        print(f"  {m:20s} {v:.3f}" if v is not None else f"  {m:20s} n/a")
    print(f"\nFull results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
