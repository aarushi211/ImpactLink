import firebase_admin
from firebase_admin import credentials, storage
import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends

# 1. INITIALIZE FIREBASE FIRST
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", "impactlink-710f2.firebasestorage.app")
if os.path.exists("firebase-service-account.json"):
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})
else:
    # Default credentials from environment (e.g. Google Cloud Run)
    firebase_admin.initialize_app(None, {"storageBucket": BUCKET_NAME})

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio

from services.parser import parse_proposal
from agents.scoring_agent import score_proposal

from services.vector_store import find_similar_grants, topic_search_grants
from services.budget import generate_budget
from services.budget_chatbot import refine_budget
from services.ngo_store import register, get_profile, update_profile, list_collab_profiles
from services.ngo_collab import find_similar_ngos
from services.auth import verify_token

from api.session import create_session, advance_session, get_session_status


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
    uid: str
    email: str
    org_name: str

class ProfileUpdateRequest(BaseModel):
    updates: dict
    ngo_id:  Optional[str] = None

class TopicSearchRequest(BaseModel):
    query:   str
    top_k:   int = 10

class CollabMatchRequest(BaseModel):
    proposal:    dict
    top_k:       int = 6

class ReviseRequest(BaseModel):
    current_draft: str
    feedback:      str

class BuildRequest(BaseModel):
    answers: list
    profile: dict
    grant:   Optional[dict] = None

class SaveDraftRequest(BaseModel):
    title:             str = ""
    grant_title:       str = ""
    grant_id:          str = ""
    agency:            str = ""
    proposal_context:  dict = {}
    matches_id:        list = []
    budget_id:         Optional[str] = None
    sections:          dict = {}
    section_order:     list = []
    ngo_id:            Optional[str] = None

class UpdateDraftRequest(BaseModel):
    draft_id:  str
    sections:  dict
    budget_id: Optional[str] = None
    ngo_id:    Optional[str] = None

class SaveBuildRequest(BaseModel):
    title:             str = ""
    org_name:          str = ""
    grant_title:       str = ""
    proposal_context:  dict = {}
    matches_id:        list = []
    budget_id:         Optional[str] = None
    sections:          dict = {}
    section_order:     list = []
    answers:           list = []
    ngo_id:            Optional[str] = None

class UpdateBuildRequest(BaseModel):
    build_id:  str
    sections:  dict
    budget_id: Optional[str] = None
    ngo_id:    Optional[str] = None

class SaveBudgetRequest(BaseModel):
    title:                str = ""
    grant_title:          str = ""
    grant_id:             str = ""
    max_budget:           int = 0
    proposal_id:          Optional[str] = None
    items:                list = []
    total_requested:      int = 0
    locality_explanation: str = ""
    ngo_id:               Optional[str] = None


# ── Core routes ────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ImpactLink AI backend running"}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...), uid: str = Depends(verify_token)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX files are supported.")
    file_bytes = await file.read()
    
    # Upload to Firebase Storage
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"proposals/{uid}/{file.filename}")
        await asyncio.to_thread(blob.upload_from_string, file_bytes, content_type=file.content_type)
        # We don't necessarily need a public URL yet, but the file is now in Storage
    except Exception as e:
        print(f"Storage upload failed: {e}")

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




# ── Budget routes ──────────────────────────────────────────────

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


# ── Auth & Profile routes ──────────────────────────────────────

@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    try:
        return {"profile": register(req.uid, req.email, req.org_name)}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/profile/me")
def profile_get(uid: str = Depends(verify_token)):
    try:
        return get_profile(uid)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.patch("/api/profile")
def profile_update(req: ProfileUpdateRequest, uid: str = Depends(verify_token)):
    try:
        return update_profile(uid, req.updates)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/api/ngos/collab")
def ngos_collab():
    return {"ngos": list_collab_profiles()}

@app.post("/api/collab/match")
async def collab_match(req: CollabMatchRequest, uid: str = Depends(verify_token)):
    all_ngos = list_collab_profiles()
    
    try:
        my_profile = get_profile(uid)
    except:
        my_profile = None

    all_ngos = [n for n in all_ngos if n["id"] != uid]
        
    results = await asyncio.to_thread(find_similar_ngos, req.proposal, all_ngos, req.top_k, my_profile)
    return {"collabs": results}







# ── Agentic Topic Search ───────────────────────────────────────────────────

@app.post("/api/grants/search")
async def grants_topic_search(req: TopicSearchRequest):
    results = await asyncio.to_thread(topic_search_grants, req.query, req.top_k)
    return {"grants": results, "query": req.query}

# ── Unified Session Routes ─────────────────────────────────────────────────

@app.post("/api/session")
async def session_create(body: dict, uid: str = Depends(verify_token)):
    try:
        return create_session(body, user_id=uid)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/session/{session_id}/advance")
async def session_advance(session_id: str, body: dict = {}, uid: str = Depends(verify_token)):
    try:
        return await asyncio.to_thread(advance_session, session_id, body, user_id=uid)
    except ValueError as e:
        if "Unauthorized" in str(e):
            raise HTTPException(403, str(e))
        raise HTTPException(404, str(e))
    except Exception as e:
        print(f"Session advance failed: {e}")
        raise HTTPException(500, "Internal session error")

@app.get("/api/session/{session_id}")
async def session_status(session_id: str, uid: str = Depends(verify_token)):
    try:
        return get_session_status(session_id, user_id=uid)
    except ValueError as e:
        if "Unauthorized" in str(e):
            raise HTTPException(403, str(e))
        raise HTTPException(404, str(e))
