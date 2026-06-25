"""
S4.4 — Upload training files and launch the Azure OpenAI fine-tuning job.

Steps performed:
  1. Upload train.jsonl + val.jsonl to the Azure OpenAI Files API.
  2. Create a fine-tuning job (model: gpt-4o-2024-08-06, n_epochs=3).
  3. Poll every 60 s until the job reaches a terminal state.
  4. Save the result to backend/data/cuad/finetune_job.json (needed for S4.5).

Run from backend/:
    python run_finetune.py

Outputs:
  backend/data/cuad/finetune_job.json  — job ID, file IDs, fine-tuned model name
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent / "data" / "cuad"
TRAIN_PATH  = DATA_DIR / "train.jsonl"
VAL_PATH    = DATA_DIR / "val.jsonl"
JOB_PATH    = DATA_DIR / "finetune_job.json"

BASE_MODEL  = "gpt-4o-2024-08-06"
N_EPOCHS    = 3
POLL_SECS   = 60   # how often to check job status

# Azure fine-tuning requires API version 2024-10-21 or later.
FT_API_VERSION = "2024-10-21"

TERMINAL_STATES = {"succeeded", "failed", "cancelled"}

console = Console()

# ── Azure OpenAI client ───────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=FT_API_VERSION,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _fmt_ts(unix_ts: int | None) -> str:
    if unix_ts is None:
        return "—"
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%H:%M:%S UTC")


def _status_color(status: str) -> str:
    return {
        "succeeded": "bold green",
        "failed":    "bold red",
        "cancelled": "bold red",
        "running":   "bold yellow",
        "queued":    "cyan",
    }.get(status, "white")


def upload_file(path: Path, label: str) -> str:
    """Upload a JSONL file and wait until Azure marks it as processed."""
    console.print(f"  [cyan]↑[/cyan] Uploading [bold]{label}[/bold] ({path.name}) …", end=" ")
    with open(path, "rb") as fh:
        result = client.files.create(file=fh, purpose="fine-tune")
    console.print(f"[green]✓[/green] [dim]{result.id}[/dim]")

    # Azure processes the file asynchronously; we must wait for status == "processed".
    console.print(f"     [dim]Waiting for file to be processed …[/dim]", end=" ")
    for _ in range(30):          # up to ~5 minutes
        time.sleep(10)
        file_obj = client.files.retrieve(result.id)
        if file_obj.status == "processed":
            console.print(f"[green]processed[/green]")
            return result.id
        if file_obj.status == "error":
            console.print(f"[red]error[/red]")
            raise RuntimeError(f"File {result.id} failed processing: {file_obj.status_details}")
        console.print(f"[yellow]{file_obj.status}[/yellow] …", end=" ")
    raise TimeoutError(f"File {result.id} did not reach 'processed' within 5 minutes.")


def print_job_table(job) -> None:
    """Render current job fields as a rich table."""
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Field",  style="dim", width=22)
    t.add_column("Value")

    status_text = Text(job.status, style=_status_color(job.status))

    t.add_row("Job ID",           job.id)
    t.add_row("Status",           status_text)
    t.add_row("Base model",       job.model)
    t.add_row("Created",          _fmt_ts(job.created_at))
    t.add_row("Finished",         _fmt_ts(getattr(job, "finished_at", None)))
    t.add_row("Fine-tuned model", getattr(job, "fine_tuned_model", None) or "—")

    if hasattr(job, "error") and job.error:
        t.add_row("Error code",   str(getattr(job.error, "code",    "—")))
        t.add_row("Error msg",    str(getattr(job.error, "message", "—")))

    console.print(t)


# ── step 1: upload files ──────────────────────────────────────────────────────
console.print(Panel(
    "[bold]S4.4 — Azure OpenAI Fine-tuning[/bold]\n"
    f"Base model : [cyan]{BASE_MODEL}[/cyan]\n"
    f"Epochs     : [cyan]{N_EPOCHS}[/cyan]\n"
    f"API version: [cyan]{FT_API_VERSION}[/cyan]",
    title="FilingsIQ · Stage 4",
    border_style="blue",
))

console.rule("[bold blue]Step 1 — Upload training files")
train_file_id = upload_file(TRAIN_PATH, "train.jsonl")
val_file_id   = upload_file(VAL_PATH,   "val.jsonl")

# ── step 2: create the fine-tuning job ───────────────────────────────────────
console.rule("[bold blue]Step 2 — Create fine-tuning job")
console.print(f"  [cyan]→[/cyan] Submitting job to Azure OpenAI …", end=" ")

job = client.fine_tuning.jobs.create(
    training_file=train_file_id,
    validation_file=val_file_id,
    model=BASE_MODEL,
    hyperparameters={"n_epochs": N_EPOCHS},
)

console.print(f"[green]✓[/green] Job created: [bold]{job.id}[/bold]")
print_job_table(job)

# Persist immediately — so we can recover the job ID if the terminal closes.
JOB_PATH.write_text(json.dumps({
    "job_id":          job.id,
    "train_file_id":   train_file_id,
    "val_file_id":     val_file_id,
    "base_model":      BASE_MODEL,
    "status":          job.status,
    "fine_tuned_model": None,
}, indent=2))
console.print(f"  [dim]Job info saved → {JOB_PATH}[/dim]")

# ── step 3: poll until terminal state ────────────────────────────────────────
console.rule("[bold blue]Step 3 — Polling (every 60 s)")
console.print(
    "  Training can take [bold]15–90 minutes[/bold]. "
    "This window must stay open.\n"
    "  If it closes, re-run the script — it will detect the existing job.\n"
)

poll_count = 0
while job.status not in TERMINAL_STATES:
    time.sleep(POLL_SECS)
    poll_count += 1
    job = client.fine_tuning.jobs.retrieve(job.id)

    # Fetch last few events for richer status info.
    events = list(client.fine_tuning.jobs.list_events(job.id, limit=3).data)
    event_msgs = [e.message for e in reversed(events)]

    now = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
    status_styled = Text(job.status, style=_status_color(job.status))
    console.print(f"  [{now}] poll #{poll_count:02d}  status=", end="")
    console.print(status_styled, end="")

    if event_msgs:
        console.print(f"  [dim]└ {event_msgs[-1]}[/dim]")
    else:
        console.print()

# ── step 4: final result ──────────────────────────────────────────────────────
console.rule("[bold blue]Step 4 — Result")
print_job_table(job)

ft_model = getattr(job, "fine_tuned_model", None)

# Update the saved JSON with final state.
JOB_PATH.write_text(json.dumps({
    "job_id":           job.id,
    "train_file_id":    train_file_id,
    "val_file_id":      val_file_id,
    "base_model":       BASE_MODEL,
    "status":           job.status,
    "fine_tuned_model": ft_model,
    "finished_at":      getattr(job, "finished_at", None),
}, indent=2))

if job.status == "succeeded":
    console.print(Panel(
        f"[bold green]Fine-tuning succeeded![/bold green]\n\n"
        f"Fine-tuned model : [bold cyan]{ft_model}[/bold cyan]\n"
        f"Saved to         : [dim]{JOB_PATH}[/dim]\n\n"
        "Next step → [bold]S4.5[/bold]: deploy on Developer tier "
        "and run the same test set to measure improvement.",
        border_style="green",
        title="✓ S4.4 Complete",
    ))
else:
    console.print(Panel(
        f"[bold red]Fine-tuning ended with status: {job.status}[/bold red]\n"
        f"Check the Azure portal for details.\n"
        f"Job ID: [dim]{job.id}[/dim]",
        border_style="red",
        title="✗ Job did not succeed",
    ))
