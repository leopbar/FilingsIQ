"""
main.py — FastAPI app.

Endpoints:
  POST /ask       — RAG chat (question → grounded answer with citations)
  POST /classify  — Clause classifier (clause → CUAD category, fine-tuned GPT-4o)
  POST /upload    — PDF upload (DI → PII → chunk → embed → index)

Run from backend/:
    uvicorn main:app --reload
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import AzureOpenAI, NotFoundError
from pydantic import BaseModel

from rag import ask
from upload import process_upload

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application Insights (S7.5) — connection string comes from Key Vault in
# production (Container App env var), from backend/.env locally. Optional: the
# app must still run with monitoring off (e.g. CI, a fresh clone without the
# secret) rather than crash.
# ---------------------------------------------------------------------------

_appinsights_conn = os.environ.get("AZURE_APPINSIGHTS_CONNECTION_STRING")
if _appinsights_conn:
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=_appinsights_conn)

# ---------------------------------------------------------------------------
# Content Safety (S7.6) — screens incoming /ask questions. Optional, like
# Application Insights above: absence of the secret disables the check rather
# than crashing the app (e.g. local dev, CI without the secret).
# ---------------------------------------------------------------------------

_contentsafety_endpoint = os.environ.get("AZURE_CONTENTSAFETY_ENDPOINT")
_contentsafety_key = os.environ.get("AZURE_CONTENTSAFETY_KEY")
_contentsafety_client = (
    ContentSafetyClient(_contentsafety_endpoint, AzureKeyCredential(_contentsafety_key))
    if _contentsafety_endpoint and _contentsafety_key
    else None
)

# Azure's severity scale is 0/2/4/6 per category (Hate, SelfHarm, Sexual, Violence).
# 4 = "medium" — blocks clearly harmful content while allowing normal financial-
# document questions (including ones that mention e.g. "violence" or "self-harm"
# as risk-factor topics in a 10-K) through.
CONTENT_SAFETY_SEVERITY_THRESHOLD = 4


def _is_flagged(text: str) -> bool:
    """Return True if Content Safety flags `text` as harmful. Fails open (returns
    False) on any API error, so an outage in this gate doesn't take down /ask."""
    if not _contentsafety_client:
        return False
    try:
        result = _contentsafety_client.analyze_text(AnalyzeTextOptions(text=text))
        return any(
            cat.severity >= CONTENT_SAFETY_SEVERITY_THRESHOLD
            for cat in result.categories_analysis
        )
    except Exception as exc:
        logger.warning("Content Safety check failed, allowing request through: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Fine-tuned classifier config (Stage 4)
# ---------------------------------------------------------------------------

FT_DEPLOYMENT  = os.environ.get("AZURE_FT_DEPLOYMENT_NAME", "ft-cuad-classifier")
FT_API_VERSION = "2024-10-21"
FT_SYSTEM_MSG  = (
    "You are a legal contract analyst. "
    "Given a clause extracted from a contract, classify it into exactly one "
    "of the 41 CUAD clause categories. "
    "Reply with the category name only — no explanation."
)

# Thread pool for blocking upload pipeline (DI can take 1–2 min)
_upload_executor = ThreadPoolExecutor(max_workers=2)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="FilingsIQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://filingsiq-frontend.whitepebble-50a8bf56.eastus2.azurecontainerapps.io",
    ],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

if _appinsights_conn:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    year: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: list[str]


class ClassifyRequest(BaseModel):
    clause: str


class ClassifyResponse(BaseModel):
    category: str
    available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    if _is_flagged(body.question):
        raise HTTPException(
            status_code=400,
            detail="This question was flagged by content safety filters and could not be processed.",
        )
    result = ask(body.question, year=body.year or None)
    return AskResponse(answer=result["answer"], sources=result["sources"])


@app.post("/classify", response_model=ClassifyResponse)
def classify_endpoint(body: ClassifyRequest):
    if not body.clause.strip():
        raise HTTPException(status_code=400, detail="clause must not be empty")

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=FT_API_VERSION,
    )
    try:
        response = client.chat.completions.create(
            model=FT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": FT_SYSTEM_MSG},
                {"role": "user",   "content": body.clause},
            ],
            temperature=0,
            max_tokens=20,
        )
        category = response.choices[0].message.content.strip()
        return ClassifyResponse(category=category, available=True)
    except NotFoundError:
        return ClassifyResponse(category="", available=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(_upload_executor, process_upload, contents)
        return {
            "filename": file.filename,
            "chunks":   result["chunks"],
            "message":  f"Indexed {result['chunks']} chunks from '{file.filename}'.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
