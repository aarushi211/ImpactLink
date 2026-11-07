import firebase_admin
from firebase_admin import credentials, storage
import os
import json
import logging
from psycopg import OperationalError, InterfaceError
from dotenv import load_dotenv
load_dotenv()  # Must happen before os.getenv calls below

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
from utils.privacy import configure_privacy, redact_text, privacy_scope, validate_protected_terms
from utils.name_detection import ensure_name_detection, PrivacyDetectionUnavailable
configure_privacy()

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends

# 1. INITIALIZE FIREBASE FIRST
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")  # Set in .env
if not BUCKET_NAME:
    # Check if we are running in a container
    if os.path.exists("/.dockerenv"):
        raise RuntimeError("FIREBASE_STORAGE_BUCKET was not passed to Docker via -e or --env-file")
    else:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET is not set in your local .env file.")
if os.path.exists("firebase-service-account.json"):
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})
else:
    # Default credentials from environment (e.g. Google Cloud Run)
    firebase_admin.initialize_app(None, {"storageBucket": BUCKET_NAME})

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

from services.parser import parse_proposal
from services.vector_store import find_similar_grants, topic_search_grants, get_grant_by_id, check_grant_eligibility
from services.work_store import list_work, save_work, update_work, delete_work
from services.budget import generate_budget
from services.budget.costing import CostPlan
from services.application import ApplicationSection, ApplicationSpec, constraint_prompt, length_check, ensure_ai_drafting_allowed
from agents.coherence_agent import CoherenceAgent, review_metadata
from services.application_extraction import extract_application_setup
from services.budget_chatbot import refine_budget
from services.ngo_store import register, get_profile, update_profile, list_collab_profiles
from services.ngo_collab import find_similar_ngos
from services.auth import verify_token

from api.session import (
    create_session,
    advance_session,
    stream_advance_session,
    get_session_status,
    update_session_checklist,
)
from utils.metrics import metrics_collector
from utils.session_stream import heartbeat_events

import time as _time
from starlette.requests import Request
from starlette.responses import Response


app = FastAPI(title="ImpactLink AI Backend")


# ── Latency middleware ─────────────────────────────────────────

@app.middleware("http")
async def latency_middleware(request: Request, call_next):
    """Time every HTTP request and record it in the metrics collector."""
    start = _time.perf_counter()
    response: Response = await call_next(request)
    duration = _time.perf_counter() - start
    metrics_collector.record(
        category="api",
        name=request.url.path,
        duration_s=duration,
        metadata={
            "method": request.method,
            "status_code": response.status_code,
        },
    )
    return response

# CORS: read from env so production URL can be injected without code changes
_allow_origins = [
    o.strip() for o in os.getenv("ALLOW_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request models ─────────────────────────────────────────────

class ProposalRequest(BaseModel):
    proposal: dict
    top_k: int = Field(default=5, ge=1, le=50)
    grant_id: Optional[str] = None
    eligibility_context: Optional[dict] = None
    target_only: bool = False

class DraftRequest(BaseModel):
    proposal: dict
    grant: dict

class BudgetGenerateRequest(BaseModel):
    proposal: dict
    max_budget: int = Field(gt=0, le=1000000000000)
    cost_inputs: Optional[CostPlan] = None

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
    top_k:   int = Field(default=10, ge=1, le=50)
    eligibility_context: dict = Field(default_factory=dict)


class EligibilityCheckRequest(BaseModel):
    grant_ids: list[str] = Field(default_factory=list, max_length=200)
    eligibility_context: dict = Field(default_factory=dict)

class CollabMatchRequest(BaseModel):
    proposal:    dict
    top_k:       int = 6

class ReviseRequest(BaseModel):
    current_draft: str
    feedback:      str
    section_title: str = "Proposal Section"
    section_requirements: Optional[ApplicationSection] = None
    application_spec: Optional[ApplicationSpec] = None


class RedactionPreviewRequest(BaseModel):
    text: str = Field(max_length=50000)
    custom_terms: Optional[list[str]] = Field(default=None, max_length=100)


class ConsistencySection(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(max_length=200000)


class ConsistencyRequest(BaseModel):
    sections: dict[str, ConsistencySection] = Field(max_length=25)
    application_spec: Optional[ApplicationSpec] = None

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

async def verify_ai_user(uid: str = Depends(verify_token)):
    """Keep the authenticated account's current privacy policy alive through streams."""
    try:
        profile = await asyncio.to_thread(get_profile, uid)
        terms = validate_protected_terms(profile.get("privacy_redaction_terms", []))
        await asyncio.to_thread(ensure_name_detection)
    except ValueError:
        raise HTTPException(503, "Could not load valid privacy settings. AI processing was stopped; check your profile.")
    except PrivacyDetectionUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        raise HTTPException(503, "Could not load privacy settings. AI processing was stopped; please retry.")
    with privacy_scope(terms):
        yield uid


@app.get("/")
def root():
    return {"status": "ImpactLink AI backend running"}


@app.post("/api/privacy/preview")
def preview_ai_redaction(req: RedactionPreviewRequest, uid: str = Depends(verify_ai_user, scope="request")):
    del uid
    try:
        result = redact_text(req.text, custom_terms=req.custom_terms)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except PrivacyDetectionUnavailable as exc:
        raise HTTPException(503, str(exc))
    return {"text": result.text, "counts": result.counts, "method": "patterns_local_names_and_custom_terms"}


# ── Metrics routes ─────────────────────────────────────────────

@app.get("/api/metrics")
def get_metrics():
    """Return aggregated latency metrics across all events."""
    return metrics_collector.get_summary()

@app.get("/api/metrics/events")
def get_all_events():
    """Return all raw timing events."""
    return {"events": metrics_collector.get_all_events()}

@app.get("/api/metrics/{session_id}")
def get_session_metrics(session_id: str):
    """Return all timing events for a specific session."""
    return metrics_collector.get_session_report(session_id)

@app.post("/api/metrics/reset")
def reset_metrics():
    """Clear all collected metrics."""
    metrics_collector.reset()
    return {"status": "reset"}

@app.get("/api/metrics/export/events")
def export_events_csv():
    """Download all raw timing events as a CSV file."""
    from starlette.responses import Response
    csv_data = metrics_collector.export_events_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=impactlink_events.csv"},
    )

@app.get("/api/metrics/export/summary")
def export_summary_csv():
    """Download aggregated latency stats as a CSV file."""
    from starlette.responses import Response
    csv_data = metrics_collector.export_summary_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=impactlink_summary.csv"},
    )

@app.post("/api/upload")
async def upload(file: UploadFile = File(...), uid: str = Depends(verify_ai_user, scope="request")):
    if not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX files are supported.")
    file_bytes = await file.read()
    
    # Upload to Firebase Storage
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"proposals/{uid}/{file.filename}")
        await asyncio.to_thread(blob.upload_from_string, file_bytes, content_type=file.content_type)
        # We don't necessarily need a public URL yet, but the file is now in Storage
    except Exception as e:
        log.warning("Storage upload failed: %s", e)

    proposal = await asyncio.to_thread(parse_proposal, file_bytes, file.filename)
    if "error" in proposal:
        log.error("Proposal parsing failed: %s", proposal.get("details", "Unknown parsing error"))
        raise HTTPException(
            422,
            "Unable to extract proposal text. Please verify the file is a valid PDF or DOCX.",
        )
    try:
        applicant_profile = get_profile(uid)
    except ValueError:
        applicant_profile = {}
    proposal["eligibility_context"] = {
        "applicant_type": applicant_profile.get("applicant_type", ""),
        "project_states": applicant_profile.get("project_states", []),
    }
    # Upload parses the document only. Matching is an explicit /api/match action.
    return {"proposal": proposal, "matches": []}

@app.post("/api/match")
def match(req: ProposalRequest, uid: str = Depends(verify_ai_user, scope="request")):
    if req.target_only and not req.grant_id:
        raise HTTPException(422, "A target grant is required to refresh its match score.")
    return {
        "matches": find_similar_grants(
            req.proposal, req.top_k, include_grant_id=req.grant_id,
            eligibility_context=req.eligibility_context,
            target_only=req.target_only,
        )
    }


# ── Budget routes ──────────────────────────────────────────────

@app.post("/api/budget/generate")
async def budget_generate(req: BudgetGenerateRequest):
    result = await asyncio.to_thread(generate_budget, req.proposal, req.max_budget, None, req.cost_inputs)
    if "error" in result:
        raise HTTPException(422, result.get("details", "Budget generation failed"))
    return result

@app.post("/api/budget/refine")
async def budget_refine(req: BudgetRefineRequest, uid: str = Depends(verify_ai_user, scope="request")):
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
async def collab_match(req: CollabMatchRequest, uid: str = Depends(verify_ai_user, scope="request")):
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
async def grants_topic_search(req: TopicSearchRequest, uid: str = Depends(verify_ai_user, scope="request")):
    results = await asyncio.to_thread(topic_search_grants, req.query, req.top_k, req.eligibility_context)
    return {"grants": results, "query": req.query}

# ── Work Store (Drafts, Builds, Budgets) ───────────────────────────────────

@app.get("/api/work/{work_type}/me")
def get_user_work(work_type: str, uid: str = Depends(verify_token)):
    if work_type not in ("drafts", "builds", "budgets", "summary"):
        raise HTTPException(400, "Invalid work type")
    return {work_type: list_work(uid, work_type)}


@app.get("/api/grants/{grant_id}")
def grant_details(grant_id: str):
    grant = get_grant_by_id(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    return grant


@app.post("/api/grants/eligibility/check")
def check_cached_grants(req: EligibilityCheckRequest):
    return {"checks": check_grant_eligibility(req.grant_ids, req.eligibility_context)}

@app.post("/api/work/{work_type}")
def create_user_work(work_type: str, req: dict, uid: str = Depends(verify_token)):
    if work_type not in ("drafts", "builds", "budgets", "summary"):
        raise HTTPException(400, "Invalid work type")
    return save_work(uid, work_type, req)

@app.patch("/api/work/{work_type}/{work_id}")
def edit_user_work(work_type: str, work_id: str, req: dict, uid: str = Depends(verify_token)):
    try:
        return update_work(uid, work_id, req)
    except ValueError:
        raise HTTPException(404, "Not found")

@app.delete("/api/work/{work_type}/{work_id}")
def remove_user_work(work_type: str, work_id: str, uid: str = Depends(verify_token)):
    delete_work(uid, work_id)
    return {"status": "deleted"}

# ── Section revise (human-in-the-loop edit assist) ─────────────────────────

@app.post("/api/build/check-consistency")
async def check_consistency(req: ConsistencyRequest, uid: str = Depends(verify_ai_user, scope="request")):
    del uid
    grant = {"application_spec": req.application_spec.model_dump()} if req.application_spec else {}
    try:
        ensure_ai_drafting_allowed(grant)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    sections = {key: section.model_dump() for key, section in req.sections.items()}
    report = await asyncio.to_thread(CoherenceAgent.check, sections, grant)
    return review_metadata(report, sections)


@app.post("/api/grants/{grant_id}/application-requirements")
async def grant_application_requirements(grant_id: str, uid: str = Depends(verify_ai_user, scope="request")):
    del uid
    grant = await asyncio.to_thread(get_grant_by_id, grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    try:
        return await asyncio.to_thread(extract_application_setup, grant)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        log.exception("Application setup extraction failed")
        raise HTTPException(502, "Could not extract application setup. You can enter requirements manually or retry.")

@app.post("/api/build/revise")
async def build_revise(req: ReviseRequest, uid: str = Depends(verify_ai_user, scope="request")):
    """Apply user feedback to a single section via SectionRewriteAgent."""
    from agents.rewriter_agent import retry_rewrite

    del uid  # auth required; section content is user-supplied
    try:
        ensure_ai_drafting_allowed({"application_spec": req.application_spec.model_dump()} if req.application_spec else {})
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        content = await asyncio.to_thread(
            retry_rewrite,
            req.section_title,
            req.current_draft,
            req.feedback + ("\n\n" + constraint_prompt(req.section_requirements.model_dump()) if req.section_requirements else ""),
            [],
        )
        return {"content": content, "limits": length_check(content, req.section_requirements.model_dump() if req.section_requirements else {})}
    except Exception as e:
        log.exception("Section revise failed")
        raise HTTPException(500, str(e))


# ── Unified Session Routes ─────────────────────────────────────────────────

@app.post("/api/session")
async def session_create(body: dict, uid: str = Depends(verify_ai_user, scope="request")):
    try:
        return await asyncio.to_thread(create_session, body, user_id=uid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (OperationalError, InterfaceError):
        raise HTTPException(503, "The database is temporarily unavailable. Please retry after the connection recovers.")

@app.post("/api/session/{session_id}/advance")
async def session_advance(session_id: str, body: dict = {}, uid: str = Depends(verify_ai_user, scope="request")):
    try:
        return await asyncio.to_thread(advance_session, session_id, body, user_id=uid)
    except ValueError as e:
        if "Unauthorized" in str(e):
            raise HTTPException(403, str(e))
        if "User instructions" in str(e) or "Application requirements" in str(e) or "Funder AI policy" in str(e):
            raise HTTPException(422, str(e))
        raise HTTPException(404, str(e))
    except (OperationalError, InterfaceError):
        raise HTTPException(503, "The database connection was interrupted while saving session progress. Check the saved session status before drafting again.")
    except Exception as e:
        log.exception("Session advance failed")
        raise HTTPException(500, "Internal session error")


@app.post("/api/session/{session_id}/advance/stream")
async def session_advance_stream(
    session_id: str,
    body: dict = {},
    uid: str = Depends(verify_ai_user, scope="request"),
):
    def events():
        try:
            for event in stream_advance_session(session_id, body, user_id=uid):
                yield event
        except ValueError as e:
            message = str(e)
            log.warning("Streamed session advance rejected: %s", message)
            yield {"type": "error", "message": message}
        except (OperationalError, InterfaceError):
            log.exception("Session checkpoint connection failed after database retries")
            yield {"type": "error", "message": "The database connection was interrupted while saving the draft. Drafting may already be complete. Use Check saved session status before drafting again."}
        except Exception:
            log.exception("Streamed session advance failed")
            yield {"type": "error", "message": "Draft generation failed. Check the saved session status before retrying."}

    return StreamingResponse(
        heartbeat_events(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/api/session/{session_id}")
async def session_status(session_id: str, uid: str = Depends(verify_token)):
    try:
        return await asyncio.to_thread(get_session_status, session_id, user_id=uid)
    except ValueError as e:
        if "Unauthorized" in str(e):
            raise HTTPException(403, str(e))
        raise HTTPException(404, str(e))
    except (OperationalError, InterfaceError):
        raise HTTPException(503, "The database is temporarily unavailable. Wait a moment and check the saved session status again.")


@app.patch("/api/session/{session_id}/checklist")
async def session_checklist(session_id: str, body: dict, uid: str = Depends(verify_token)):
    try:
        return await asyncio.to_thread(update_session_checklist, session_id, body, user_id=uid)
    except ValueError as exc:
        message = str(exc)
        code = 403 if "Unauthorized" in message else 404 if message == "Session not found" else 409 if "already drafting" in message else 422
        raise HTTPException(code, message)
