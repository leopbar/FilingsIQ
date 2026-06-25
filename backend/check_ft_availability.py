"""
S4.1 — Confirm gpt-4.1-mini fine-tuning availability in East US 2.

Calls the Azure OpenAI /models endpoint to list all deployed/available models
and checks whether gpt-4.1-mini (or a variant) appears and has fine-tune capability.
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
api_key = os.environ["AZURE_OPENAI_API_KEY"]

# 2024-10-21 is the GA version that includes fine-tuning job support
API_VERSION = "2024-10-21"
TARGET = "gpt-4.1-mini"

print(f"Endpoint : {endpoint}")
print(f"API ver  : {API_VERSION}")
print(f"Looking for : {TARGET}\n")

headers = {"api-key": api_key, "Content-Type": "application/json"}

# ── 1. List all models ──────────────────────────────────────────────────────
url = f"{endpoint}/openai/models?api-version={API_VERSION}"
resp = requests.get(url, headers=headers)
if resp.status_code != 200:
    print(f"ERROR {resp.status_code}: {resp.text}")
    sys.exit(1)

models = resp.json().get("data", [])
print(f"{'Model ID':<45} {'fine_tune':>10}  {'status'}")
print("-" * 75)

target_rows = []
for m in sorted(models, key=lambda x: x.get("id", "")):
    mid = m.get("id", "")
    caps = m.get("capabilities", {})
    ft = caps.get("fine_tune", False)
    status = m.get("status", "—")
    marker = "  <-- MATCH" if TARGET in mid else ""
    print(f"  {mid:<43} {str(ft):>10}  {status}{marker}")
    if TARGET in mid:
        target_rows.append((mid, ft, status))

print()

# ── 2. Also probe the fine-tuning jobs endpoint to confirm the API is live ──
ft_url = f"{endpoint}/openai/fine_tuning/jobs?api-version={API_VERSION}&limit=5"
ft_resp = requests.get(ft_url, headers=headers)
print(f"Fine-tuning jobs endpoint: HTTP {ft_resp.status_code}")
if ft_resp.status_code == 200:
    jobs = ft_resp.json().get("data", [])
    print(f"  Existing fine-tuning jobs: {len(jobs)}")
    for j in jobs:
        print(f"    {j.get('id')} — model={j.get('model')} status={j.get('status')}")
    if not jobs:
        print("  (none yet — that's expected)")
else:
    print(f"  Response: {ft_resp.text[:300]}")

# ── 3. Summary ───────────────────────────────────────────────────────────────
print()
if target_rows:
    for mid, ft, status in target_rows:
        print(f"[FOUND] '{mid}'  fine_tune={ft}  status={status}")
else:
    print(f"[NOT FOUND] '{TARGET}' not found in the /models list.")
    print("   This does NOT necessarily mean fine-tuning is unavailable --")
    print("   Azure sometimes only lists deployed models here, not base models.")
    print("   Check the Azure AI Foundry portal: Fine-tuning > Create > Base model.")
