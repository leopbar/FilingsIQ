"""
S4.5 — Deploy the fine-tuned model (Developer tier) and evaluate it.

Steps:
  1. Read finetune_job.json → get the fine-tuned model name.
  2. Create a deployment on Developer tier via Azure OpenAI REST API.
  3. Poll until the deployment is ready.
  4. Classify the same 671 test clauses used in baseline_eval.py.
  5. Compute accuracy + macro F1.
  6. Compare with baseline_results.json and print a rich table.

Run from backend/:
    python ft_eval.py

Outputs:
  backend/data/cuad/ft_results.json        — final scores + per-category breakdown
  backend/data/cuad/ft_checkpoint.jsonl    — row-by-row predictions (resume-safe)
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI, BadRequestError, NotFoundError, RateLimitError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────
DATA_DIR        = Path(__file__).parent / "data" / "cuad"
JOB_PATH        = DATA_DIR / "finetune_job.json"
TEST_PATH       = DATA_DIR / "test.jsonl"
CHECKPOINT_PATH = DATA_DIR / "ft_checkpoint.jsonl"
RESULTS_PATH    = DATA_DIR / "ft_results.json"
BASELINE_PATH   = DATA_DIR / "baseline_results.json"

# Must match the deployment name you created in Azure OpenAI Studio.
DEPLOYMENT_NAME = "ft-cuad-classifier"
FT_API_VERSION  = "2024-10-21"
EVAL_DELAY      = 0.15  # seconds between inference calls

SYSTEM_MSG = (
    "You are a legal contract analyst. "
    "Given a clause extracted from a contract, classify it into exactly one "
    "of the 41 CUAD clause categories. "
    "Reply with the category name only — no explanation."
)

console = Console()

# ── load job info ─────────────────────────────────────────────────────────────
job_info = json.loads(JOB_PATH.read_text())
FT_MODEL = job_info["fine_tuned_model"]

ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
API_KEY  = os.environ["AZURE_OPENAI_API_KEY"]

# ── inference client ──────────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint=ENDPOINT,
    api_key=API_KEY,
    api_version=FT_API_VERSION,
)


def verify_deployment() -> bool:
    """Return True if the deployment is reachable by sending a minimal test call."""
    try:
        client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user",   "content": "test"},
            ],
            max_tokens=5,
        )
        return True
    except (NotFoundError, BadRequestError) as e:
        if "DeploymentNotFound" in str(e) or "404" in str(e):
            return False
        raise


# ── metric helpers ────────────────────────────────────────────────────────────
def macro_f1(rows: list[dict]) -> tuple[float, float, dict]:
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
    categories = sorted({r["truth"] for r in rows})
    per_cat = {}
    f1_scores = []
    for cat in categories:
        prec = tp[cat] / (tp[cat] + fp[cat]) if (tp[cat] + fp[cat]) else 0.0
        rec  = tp[cat] / (tp[cat] + fn[cat]) if (tp[cat] + fn[cat]) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_cat[cat] = {"precision": round(prec, 4), "recall": round(rec, 4),
                        "f1": round(f1, 4), "support": tp[cat] + fn[cat]}
        f1_scores.append(f1)
    macro = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    return accuracy, macro, per_cat


def classify(clause: str, retries: int = 5) -> str:
    delay = 2.0
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_MSG},
                    {"role": "user",   "content": clause},
                ],
                temperature=0,
                max_tokens=20,
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            if attempt == retries - 1:
                raise
            console.print(f"    [yellow]rate-limited[/yellow] — waiting {delay:.0f}s …")
            time.sleep(delay)
            delay *= 2
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — banner
# ─────────────────────────────────────────────────────────────────────────────
console.print(Panel(
    f"[bold]S4.5 — Fine-tuned Model Evaluation[/bold]\n"
    f"Fine-tuned model : [cyan]{FT_MODEL}[/cyan]\n"
    f"Deployment name  : [cyan]{DEPLOYMENT_NAME}[/cyan]\n"
    f"Tier             : [cyan]Developer[/cyan] (no hourly fee, auto-deletes in 24 h)",
    title="FilingsIQ · Stage 4",
    border_style="blue",
))

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — deploy (or reuse existing)
# ─────────────────────────────────────────────────────────────────────────────
console.rule("[bold blue]Step 1 — Verify Deployment")

console.print(f"  [cyan]→[/cyan] Checking deployment [bold]{DEPLOYMENT_NAME}[/bold] …", end=" ")
if verify_deployment():
    console.print(f"[green]✓ live[/green]")
else:
    console.print(f"[red]not found[/red]\n")
    console.print(Panel(
        f"[bold yellow]Deployment not found.[/bold yellow]\n\n"
        "Create it manually in [bold]Azure OpenAI Studio[/bold]:\n\n"
        "  1. Go to [cyan]oai.azure.com[/cyan] → your [bold]filingsiq-openai[/bold] resource\n"
        "  2. Left menu → [bold]Deployments[/bold] → [bold]Deploy model[/bold]\n"
        "  3. Click [bold]Fine-tuned models[/bold] tab\n"
        f"  4. Select [cyan]{FT_MODEL}[/cyan]\n"
        f"  5. Deployment name: [bold]{DEPLOYMENT_NAME}[/bold]\n"
        "  6. Scale type: [bold]Developer[/bold]\n"
        "  7. Click [bold]Deploy[/bold] — wait ~2 min — then re-run this script.\n",
        border_style="yellow",
        title="Action required",
    ))
    raise SystemExit(1)

console.print(f"  [green]✓[/green] Model is callable as [bold]{DEPLOYMENT_NAME}[/bold]\n")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — load test set + checkpoint
# ─────────────────────────────────────────────────────────────────────────────
console.rule("[bold blue]Step 2 — Evaluation")

test_rows = [json.loads(l) for l in TEST_PATH.read_text(encoding="utf-8").splitlines()]
console.print(f"  Test set: [bold]{len(test_rows):,}[/bold] examples")

done: dict[int, dict] = {}
if CHECKPOINT_PATH.exists():
    for line in CHECKPOINT_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        done[row["index"]] = row
    console.print(f"  Checkpoint: [bold]{len(done):,}[/bold] already done — resuming.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — classify
# ─────────────────────────────────────────────────────────────────────────────
checkpoint_fh = open(CHECKPOINT_PATH, "a", encoding="utf-8")
start_time    = time.time()
total         = len(test_rows)

try:
    for i, example in enumerate(test_rows):
        if i in done:
            continue

        truth  = example["messages"][2]["content"]
        clause = example["messages"][1]["content"]
        pred   = classify(clause)

        row = {"index": i, "truth": truth, "pred": pred}
        done[i] = row
        checkpoint_fh.write(json.dumps(row) + "\n")
        checkpoint_fh.flush()

        elapsed   = time.time() - start_time
        remaining = total - len(done)
        rate      = len(done) / elapsed if elapsed > 0 else 1
        eta_s     = remaining / rate if rate > 0 else 0
        match     = "[green]✓[/green]" if truth == pred else "[red]✗[/red]"

        console.print(
            f"  {match} [{len(done):>3}/{total}]  "
            f"[dim]truth=[/dim][cyan]{truth[:35]:35s}[/cyan]  "
            f"[dim]pred=[/dim]{('[green]' + pred + '[/green]') if truth == pred else ('[red]' + pred + '[/red]')}"
            f"  [dim]ETA {eta_s/60:.1f} min[/dim]"
        )
        time.sleep(EVAL_DELAY)
finally:
    checkpoint_fh.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — metrics
# ─────────────────────────────────────────────────────────────────────────────
all_rows              = [done[i] for i in range(total)]
accuracy, macro, per_cat = macro_f1(all_rows)
elapsed_total         = time.time() - start_time

results = {
    "model":        DEPLOYMENT_NAME,
    "ft_model":     FT_MODEL,
    "stage":        "fine_tuned_eval",
    "n_examples":   total,
    "accuracy":     round(accuracy, 4),
    "macro_f1":     round(macro,    4),
    "elapsed_sec":  round(elapsed_total, 1),
    "per_category": per_cat,
}
RESULTS_PATH.write_text(json.dumps(results, indent=2))

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — comparison table
# ─────────────────────────────────────────────────────────────────────────────
console.rule("[bold blue]Step 3 — Results vs Baseline")

baseline = json.loads(BASELINE_PATH.read_text())

acc_delta = accuracy - baseline["accuracy"]
f1_delta  = macro    - baseline["macro_f1"]

def _delta(val: float) -> Text:
    sign = "+" if val >= 0 else ""
    color = "green" if val > 0 else ("red" if val < 0 else "white")
    return Text(f"{sign}{val:+.1%}", style=f"bold {color}")

# Summary table
summary = Table(title="Overall Results", box=box.ROUNDED, border_style="blue")
summary.add_column("Metric",        style="dim", width=18)
summary.add_column("Baseline\n(zero-shot)", justify="right", width=18)
summary.add_column("Fine-tuned",    justify="right", width=18)
summary.add_column("Delta",         justify="right", width=12)

summary.add_row(
    "Accuracy",
    f"{baseline['accuracy']:.1%}",
    f"{accuracy:.1%}",
    _delta(acc_delta),
)
summary.add_row(
    "Macro F1",
    f"{baseline['macro_f1']:.4f}",
    f"{macro:.4f}",
    _delta(f1_delta),
)
summary.add_row(
    "Test examples",
    str(baseline["n_examples"]),
    str(total),
    Text("—", style="dim"),
)

console.print(summary)

# Per-category breakdown — top 10 most improved + top 10 worst
console.print()
cats = sorted(
    per_cat.keys(),
    key=lambda c: per_cat[c]["f1"] - baseline["per_category"].get(c, {}).get("f1", 0),
    reverse=True,
)

cat_table = Table(
    title="Per-category F1 — top 10 most improved",
    box=box.SIMPLE,
    border_style="dim",
)
cat_table.add_column("Category",      style="cyan", width=38)
cat_table.add_column("Baseline F1",   justify="right", width=12)
cat_table.add_column("Fine-tuned F1", justify="right", width=14)
cat_table.add_column("Delta",         justify="right", width=10)

for cat in cats[:10]:
    base_f1 = baseline["per_category"].get(cat, {}).get("f1", 0.0)
    ft_f1   = per_cat[cat]["f1"]
    delta   = ft_f1 - base_f1
    cat_table.add_row(cat, f"{base_f1:.3f}", f"{ft_f1:.3f}", _delta(delta))

console.print(cat_table)

# Final panel
console.print(Panel(
    f"[bold green]S4.5 complete![/bold green]\n\n"
    f"  Accuracy : [dim]{baseline['accuracy']:.1%}[/dim] → [bold green]{accuracy:.1%}[/bold green]  ([bold]{acc_delta:+.1%}[/bold])\n"
    f"  Macro F1 : [dim]{baseline['macro_f1']:.4f}[/dim] → [bold green]{macro:.4f}[/bold green]  ([bold]{f1_delta:+.4f}[/bold])\n\n"
    f"Results saved → [dim]{RESULTS_PATH}[/dim]\n\n"
    "Next step → [bold]S4.6[/bold]: cost + latency comparison, then update PROJECT_LOG.",
    border_style="green",
    title="✓ Fine-tuned Eval Done",
))
