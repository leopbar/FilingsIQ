"""
S4.6 — Baseline vs fine-tuned comparison: accuracy, latency, and cost.

Reads baseline_results.json and ft_results.json and prints a rich report.

Run from backend/:
    python compare.py
"""

import json
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DATA_DIR      = Path(__file__).parent / "data" / "cuad"
BASELINE_PATH = DATA_DIR / "baseline_results.json"
FT_PATH       = DATA_DIR / "ft_results.json"

# Azure OpenAI pricing (East US 2, as of 2026-06)
# gpt-4o standard:        $2.50 / 1M input tokens,  $10.00 / 1M output tokens
# gpt-4o fine-tuned:      $3.75 / 1M input tokens,  $15.00 / 1M output tokens
PRICE_BASE_IN  = 2.50 / 1_000_000
PRICE_BASE_OUT = 10.00 / 1_000_000
PRICE_FT_IN    = 3.75 / 1_000_000
PRICE_FT_OUT   = 15.00 / 1_000_000

# Token estimates per call (system ~50 + avg clause ~350 input; label ~7 output)
AVG_INPUT_TOKENS  = 400
AVG_OUTPUT_TOKENS = 7

console = Console()

# ── load results ──────────────────────────────────────────────────────────────
b = json.loads(BASELINE_PATH.read_text())
f = json.loads(FT_PATH.read_text())

n = b["n_examples"]   # 671

# ── derived metrics ───────────────────────────────────────────────────────────
b_latency = b["elapsed_sec"] / n          # sec per call (wall time incl. sleep)
f_latency = f["elapsed_sec"] / n

b_cost_per_call = (AVG_INPUT_TOKENS  * PRICE_BASE_IN +
                   AVG_OUTPUT_TOKENS * PRICE_BASE_OUT)
f_cost_per_call = (AVG_INPUT_TOKENS  * PRICE_FT_IN +
                   AVG_OUTPUT_TOKENS * PRICE_FT_OUT)

b_cost_total = b_cost_per_call * n
f_cost_total = f_cost_per_call * n

acc_delta = f["accuracy"]  - b["accuracy"]
f1_delta  = f["macro_f1"]  - b["macro_f1"]

def _delta(val: float, fmt: str = "+.1%") -> Text:
    color = "green" if val > 0 else ("red" if val < 0 else "white")
    return Text(f"{val:{fmt}}", style=f"bold {color}")

# ── banner ────────────────────────────────────────────────────────────────────
console.print(Panel(
    "[bold]S4.6 — Baseline vs Fine-tuned Comparison[/bold]\n"
    f"Test set : [cyan]{n:,}[/cyan] held-out clauses (never seen during training)\n"
    f"Task     : [cyan]41-category CUAD clause classification[/cyan]",
    title="FilingsIQ · Stage 4",
    border_style="blue",
))

# ── accuracy & F1 ─────────────────────────────────────────────────────────────
acc_table = Table(title="Quality", box=box.ROUNDED, border_style="blue")
acc_table.add_column("Metric",              style="dim",      width=14)
acc_table.add_column("Baseline\n(zero-shot)", justify="right", width=18)
acc_table.add_column("Fine-tuned",          justify="right",  width=14)
acc_table.add_column("Delta",               justify="right",  width=12)

acc_table.add_row("Accuracy",
    f"{b['accuracy']:.1%}", f"{f['accuracy']:.1%}", _delta(acc_delta))
acc_table.add_row("Macro F1",
    f"{b['macro_f1']:.4f}", f"{f['macro_f1']:.4f}", _delta(f1_delta, fmt="+.4f"))

console.print(acc_table)

# ── latency ───────────────────────────────────────────────────────────────────
lat_table = Table(title="Latency (wall time per call, 671-call run)", box=box.ROUNDED, border_style="blue")
lat_table.add_column("Model",           style="dim",      width=22)
lat_table.add_column("Total (sec)",     justify="right",  width=14)
lat_table.add_column("Per call (sec)",  justify="right",  width=16)
lat_table.add_column("Note",            width=46)

lat_table.add_row(
    "Baseline (gpt-4o)",
    f"{b['elapsed_sec']:,.0f}",
    f"{b_latency:.2f}",
    "Standard quota (~100 RPM)",
)
lat_table.add_row(
    "Fine-tuned",
    f"{f['elapsed_sec']:,.0f}",
    f"{f_latency:.2f}",
    "[yellow]Standard quota = 6 RPM[/yellow] — throttled by quota, not model speed",
)

console.print(lat_table)
console.print(
    "  [dim]Note: fine-tuned latency reflects the 6 RPM rate limit on the Standard "
    "deployment,\n  not inherent model latency. At higher quota the gap would be minimal.[/dim]\n"
)

# ── cost per inference call ───────────────────────────────────────────────────
cost_table = Table(title="Inference Cost (estimated, per-token pricing only)", box=box.ROUNDED, border_style="blue")
cost_table.add_column("Model",              style="dim",      width=22)
cost_table.add_column("Input $/1M tok",     justify="right",  width=16)
cost_table.add_column("Output $/1M tok",    justify="right",  width=17)
cost_table.add_column("Cost / call",        justify="right",  width=14)
cost_table.add_column(f"Cost × {n} calls",  justify="right",  width=16)

cost_table.add_row(
    "Baseline (gpt-4o)",
    "$2.50", "$10.00",
    f"${b_cost_per_call*1000:.4f}m",
    f"${b_cost_total:.3f}",
)
cost_table.add_row(
    "Fine-tuned",
    "$3.75", "$15.00",
    f"${f_cost_per_call*1000:.4f}m",
    f"${f_cost_total:.3f}",
)

console.print(cost_table)
console.print(
    f"  [dim]Fine-tuned inference costs ~1.5× more per token. "
    f"For {n} calls: ${b_cost_total:.2f} vs ${f_cost_total:.2f} — "
    f"a difference of ${f_cost_total - b_cost_total:.2f} for "
    f"a +{acc_delta:.0%} accuracy gain.[/dim]\n"
)

# ── training cost (one-time) ──────────────────────────────────────────────────
train_table = Table(title="One-time Training Cost", box=box.ROUNDED, border_style="blue")
train_table.add_column("Item",              style="dim",  width=34)
train_table.add_column("Value",             width=30)

train_table.add_row("Training tokens billed",   "1,717,000")
train_table.add_row("Rate (gpt-4o fine-tuning)", "~$25 / 1M tokens")
train_table.add_row("Estimated training cost",   "~$43")
train_table.add_row("Wall-clock training time",  "5 h 34 m")
train_table.add_row("Break-even point",
    f"~{int(43 / (f_cost_total - b_cost_total) * n):,} classified clauses")

console.print(train_table)

# ── final summary panel ───────────────────────────────────────────────────────
console.print(Panel(
    "[bold green]Stage 4 — Fine-tuning Complete[/bold green]\n\n"
    f"  Accuracy   : [dim]17.7%[/dim] → [bold green]77.5%[/bold green]   (+59.8 pp)\n"
    f"  Macro F1   : [dim]0.1543[/dim] → [bold green]0.6884[/bold green]  (+0.5341)\n"
    f"  Latency    : [dim]~0.9 s/call[/dim] → [yellow]~9.9 s/call[/yellow]  (quota-limited, not model-limited)\n"
    f"  Infer cost : [dim]${b_cost_per_call*1000:.3f}m[/dim] → [yellow]${f_cost_per_call*1000:.3f}m[/yellow] per call  (1.5× — negligible in practice)\n"
    f"  Training   : ~$43 one-time · 5 h 34 m wall clock\n\n"
    "The [bold]+59.8 pp accuracy gain[/bold] on 671 unseen examples proves the fine-tuning\n"
    "delivered real specialization, not memorization.\n\n"
    "Next step → [bold]S4.7[/bold]: write ADR-003-fine-tuning.md",
    border_style="green",
    title="✓ S4.6 Complete",
))
