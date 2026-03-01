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
from services.ngo_store import register, login, get_profile, update_profile, list_collab_profiles
from services.ngo_collab import find_similar_ngos
from agents.build_agent import build_proposal_stream, revise_section
from services.work_store import (
    save_draft,   update_draft,  list_drafts,  get_draft,  delete_draft,
    save_build,   update_build,  list_builds,  get_build,  delete_build,
    save_budget,                 list_budgets, get_budget, delete_budget,
    get_summary,
)

app = FastAPI(title="ImpactLink AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────

class ProposalRequest(BaseModel):
    proposal: dict
    top_k: int = 5

class DraftRequest(BaseModel):
    proposal: dict
    grant: dict

class BudgetGenerateRequest(BaseModel):
    proposal: dict
    max_budget: int

class BudgetRefineRequest(BaseModel):
    current_budget: dict
    user_request: str

class RegisterRequest(BaseModel):
    email:    str
    password: str
    org_name: str

class LoginRequest(BaseModel):
    email:    str
    password: str

class ProfileUpdateRequest(BaseModel):
    ngo_id:  str
    updates: dict

class CollabMatchRequest(BaseModel):
    proposal:    dict
    ngo_id:      Optional[str] = None   # exclude requester's own profile
    top_k:       int = 6

class ReviseRequest(BaseModel):
    current_draft: str
    feedback:      str

class BuildRequest(BaseModel):
    answers: list
    profile: dict
    grant:   Optional[dict] = None

class SaveDraftRequest(BaseModel):
    ngo_id:            str
    title:             str = ""
    grant_title:       str = ""
    grant_id:          str = ""
    agency:            str = ""
    proposal_context:  dict = {}
    matches_id:        list = []
    budget_id:         Optional[str] = None
    sections:          dict
    section_order:     list

class UpdateDraftRequest(BaseModel):
    ngo_id:    str
    draft_id:  str
    sections:  dict
    budget_id: Optional[str] = None

class SaveBuildRequest(BaseModel):
    ngo_id:            str
    title:             str = ""
    org_name:          str = ""
    grant_title:       str = ""
    proposal_context:  dict = {}
    matches_id:        list = []
    budget_id:         Optional[str] = None
    sections:          dict
    section_order:     list
    answers:           list = []

class UpdateBuildRequest(BaseModel):
    ngo_id:    str
    build_id:  str
    sections:  dict
    budget_id: Optional[str] = None

class SaveBudgetRequest(BaseModel):
    ngo_id:               str
    title:                str = ""
    grant_title:          str = ""
    grant_id:             str = ""
    max_budget:           int = 0
    proposal_id:          Optional[str] = None
    items:                list
    total_requested:      int
    locality_explanation: str = ""


# ── Core routes ────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ImpactLink AI backend running"}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX files are supported.")
    file_bytes = await file.read()
    proposal = parse_proposal(file_bytes, file.filename)
    scoring, matches = await asyncio.gather(
        asyncio.to_thread(score_proposal, proposal),
        asyncio.to_thread(find_similar_grants, proposal, 5),
    )
    return {"proposal": proposal, "scoring": scoring, "matches": matches}

@app.post("/api/match")
def match(req: ProposalRequest):
    return {"matches": find_similar_grants(req.proposal, req.top_k)}

@app.post("/api/score")
def score(req: ProposalRequest):
    return {"scoring": score_proposal(req.proposal)}

@app.post("/api/draft")
def draft(req: DraftRequest):
    return draft_proposal(req.proposal, req.grant)

@app.post("/api/draft/stream")
def draft_stream(req: DraftRequest):
    return StreamingResponse(
        (chunk for chunk in draft_proposal_stream(req.proposal, req.grant)),
        media_type="text/plain",
    )


# ── Budget routes ──────────────────────────────────────────────


# ── Budget routes ─────────────────────────────────────────

class BudgetGenerateRequest(BaseModel):
    proposal: dict
    max_budget: int

class BudgetRefineRequest(BaseModel):
    current_budget: dict
    user_request: str


@app.post("/api/budget/generate")
async def budget_generate(req: BudgetGenerateRequest):
    result = await asyncio.to_thread(generate_budget, req.proposal, req.max_budget)
    if "error" in result:
        raise HTTPException(500, result.get("details", "Budget generation failed"))
    return result

@app.post("/api/budget/refine")
async def budget_refine(req: BudgetRefineRequest):
    result = await asyncio.to_thread(refine_budget, req.current_budget, req.user_request)
    if "error" in result:
        raise HTTPException(500, result.get("details", "Budget refinement failed"))
    return result


# ── Auth routes ────────────────────────────────────────────────

@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    try:
        return {"profile": register(req.email, req.password, req.org_name)}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    try:
        return {"profile": login(req.email, req.password)}
    except ValueError as e:
        raise HTTPException(401, str(e))

@app.get("/api/profile/{ngo_id}")
def profile_get(ngo_id: str):
    try:
        return get_profile(ngo_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.patch("/api/profile")
def profile_update(req: ProfileUpdateRequest):
    try:
        return update_profile(req.ngo_id, req.updates)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/api/ngos/collab")
def ngos_collab():
    return {"ngos": list_collab_profiles()}

@app.post("/api/collab/match")
async def collab_match(req: CollabMatchRequest):
    """Find NGOs whose mission/work is most similar to the given proposal."""
    all_ngos = list_collab_profiles()
    # Exclude the requesting NGO from results
    if req.ngo_id:
        all_ngos = [n for n in all_ngos if n["id"] != req.ngo_id]
    results = await asyncio.to_thread(find_similar_ngos, req.proposal, all_ngos, req.top_k)
    return {"collabs": results}


# ── Build routes ───────────────────────────────────────────────

@app.post("/api/build/stream")
def build_stream(req: BuildRequest):
    return StreamingResponse(
        (chunk for chunk in build_proposal_stream(req.answers, req.profile, req.grant)),
        media_type="text/plain",
    )

@app.post("/api/build/revise")
async def build_revise(req: ReviseRequest):
    result = await asyncio.to_thread(revise_section, req.current_draft, req.feedback)
    return {"content": result}


# ── Work Store — Drafts ────────────────────────────────────────

@app.post("/api/work/drafts")
def work_save_draft(req: SaveDraftRequest):
    return save_draft(req.ngo_id, req.dict())

@app.patch("/api/work/drafts")
def work_update_draft(req: UpdateDraftRequest):
    try:
        return update_draft(req.ngo_id, req.draft_id, req.sections, req.budget_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/api/work/drafts/{ngo_id}")
def work_list_drafts(ngo_id: str):
    return {"items": list_drafts(ngo_id)}

@app.get("/api/work/drafts/{ngo_id}/{draft_id}")
def work_get_draft(ngo_id: str, draft_id: str):
    try:
        return get_draft(ngo_id, draft_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.delete("/api/work/drafts/{ngo_id}/{draft_id}")
def work_delete_draft(ngo_id: str, draft_id: str):
    delete_draft(ngo_id, draft_id)
    return {"ok": True}


# ── Work Store — Builds ────────────────────────────────────────

@app.post("/api/work/builds")
def work_save_build(req: SaveBuildRequest):
    return save_build(req.ngo_id, req.dict())

@app.patch("/api/work/builds")
def work_update_build(req: UpdateBuildRequest):
    try:
        return update_build(req.ngo_id, req.build_id, req.sections, req.budget_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/api/work/builds/{ngo_id}")
def work_list_builds(ngo_id: str):
    return {"items": list_builds(ngo_id)}

@app.get("/api/work/builds/{ngo_id}/{build_id}")
def work_get_build(ngo_id: str, build_id: str):
    try:
        return get_build(ngo_id, build_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.delete("/api/work/builds/{ngo_id}/{build_id}")
def work_delete_build(ngo_id: str, build_id: str):
    delete_build(ngo_id, build_id)
    return {"ok": True}


# ── Work Store — Budgets ───────────────────────────────────────

@app.post("/api/work/budgets")
def work_save_budget(req: SaveBudgetRequest):
    return save_budget(req.ngo_id, req.dict())

@app.get("/api/work/budgets/{ngo_id}")
def work_list_budgets(ngo_id: str):
    return {"items": list_budgets(ngo_id)}

@app.get("/api/work/budgets/{ngo_id}/{budget_id}")
def work_get_budget(ngo_id: str, budget_id: str):
    try:
        return get_budget(ngo_id, budget_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.delete("/api/work/budgets/{ngo_id}/{budget_id}")
def work_delete_budget(ngo_id: str, budget_id: str):
    delete_budget(ngo_id, budget_id)
    return {"ok": True}


# ── Work Store — Summary ───────────────────────────────────────

@app.get("/api/work/summary/{ngo_id}")
def work_summary(ngo_id: str):
    return get_summary(ngo_id)
