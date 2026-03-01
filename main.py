from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio

from services.parser import parse_proposal
from agents.scoring_agent import score_proposal
from agents.draft_agent import draft_proposal, draft_proposal_stream
from services.vector_store import find_similar_grants
from services.budget_generator import generate_budget
from services.budget_chatbot import refine_budget

app = FastAPI(title="ImpactLink AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request models ────────────────────────────────────────
class ProposalRequest(BaseModel):
    proposal: dict
    top_k: int = 5

class DraftRequest(BaseModel):
    proposal: dict
    grant: dict

# ── Routes ───────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ImpactLink AI backend running"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """
    Upload PDF → parse + score + match in parallel.
    Returns: { proposal, scoring, matches }
    """
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX files are supported.")

    file_bytes = await file.read()
    proposal = parse_proposal(file_bytes, file.filename)

    scoring, matches = await asyncio.gather(
        asyncio.to_thread(score_proposal, proposal),
        asyncio.to_thread(find_similar_grants, proposal, 5),
    )

    return { "proposal": proposal, "scoring": scoring, "matches": matches }


@app.post("/api/match")
def match(req: ProposalRequest):
    """Get grant matches for an already-parsed proposal."""
    matches = find_similar_grants(req.proposal, req.top_k)
    return { "matches": matches }


@app.post("/api/score")
def score(req: ProposalRequest):
    """Score an already-parsed proposal."""
    scoring = score_proposal(req.proposal)
    return { "scoring": scoring }


@app.post("/api/draft")
def draft(req: DraftRequest):
    """
    Draft a complete proposal for a specific grant.
    Non-streaming — returns all sections at once.
    """
    result = draft_proposal(req.proposal, req.grant)
    return result


@app.post("/api/draft/stream")
def draft_stream(req: DraftRequest):
    """
    Draft a proposal with streaming — yields each section as it completes.
    Frontend reads chunks via EventSource / fetch with ReadableStream.
    """
    def generate():
        for chunk in draft_proposal_stream(req.proposal, req.grant):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


# ── Budget routes ─────────────────────────────────────────

class BudgetGenerateRequest(BaseModel):
    proposal: dict
    max_budget: int

class BudgetRefineRequest(BaseModel):
    current_budget: dict
    user_request: str


@app.post("/api/budget/generate")
async def budget_generate(req: BudgetGenerateRequest):
    """
    Generate a localized line-item budget from a proposal + grant max amount.
    Returns: { items, total_requested, locality_explanation }
    """
    result = await asyncio.to_thread(generate_budget, req.proposal, req.max_budget)
    if "error" in result:
        raise HTTPException(500, result.get("details", "Budget generation failed"))
    return result


@app.post("/api/budget/refine")
async def budget_refine(req: BudgetRefineRequest):
    """
    Refine an existing budget based on a plain-English user request.
    Keeps total_requested constant, rebalances line items.
    Returns: { items, total_requested, locality_explanation }
    """
    result = await asyncio.to_thread(refine_budget, req.current_budget, req.user_request)
    if "error" in result:
        raise HTTPException(500, result.get("details", "Budget refinement failed"))
    return result