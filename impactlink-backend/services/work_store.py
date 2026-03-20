# backend/services/work_store.py
from firebase_admin import firestore
import uuid
from datetime import datetime

# Grab the database instance initialized in main.py
db = firestore.client()

# ── Helpers ────────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]

def _now() -> str:
    return datetime.now().isoformat()

def _word_count(sections: dict) -> int:
    total = 0
    for sec in sections.values():
        content = sec.get("content", "") if isinstance(sec, dict) else ""
        total += len(content.split())
    return total

def _get_collection(ngo_id: str, collection_name: str):
    """Helper to return the reference to a specific subcollection lazily."""
    db = firestore.client() # Get the DB here
    return db.collection("ngo_profiles").document(ngo_id).collection(collection_name)

# ── DRAFTS ──────────────────────────────────────────────────────

def save_draft(ngo_id: str, payload: dict) -> dict:
    draft_id = _uid()
    now = _now()
    item = {
        "id":               draft_id,
        "ngo_id":           ngo_id,
        "title":            payload.get("title") or payload.get("grant_title") or "Untitled Draft",
        "grant_title":      payload.get("grant_title", ""),
        "grant_id":         payload.get("grant_id", ""),
        "agency":           payload.get("agency", ""),
        "proposal_context": payload.get("proposal_context") or {},
        "matches_id":       payload.get("matches_id") or [],
        "budget_id":        payload.get("budget_id") or None,
        "sections":         payload.get("sections", {}),
        "section_order":    payload.get("section_order", []),
        "word_count":       _word_count(payload.get("sections", {})),
        "created_at":       now,
        "updated_at":       now,
    }
    
    _get_collection(ngo_id, "drafts").document(draft_id).set(item)
    return item

def update_draft(ngo_id: str, draft_id: str, sections: dict, budget_id: str = None) -> dict:
    doc_ref = _get_collection(ngo_id, "drafts").document(draft_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise ValueError(f"Draft {draft_id} not found.")
        
    updates = {
        "sections": sections,
        "word_count": _word_count(sections),
        "updated_at": _now()
    }
    if budget_id is not None:
        updates["budget_id"] = budget_id
        
    doc_ref.update(updates)
    return doc_ref.get().to_dict()

def list_drafts(ngo_id: str) -> list:
    docs = _get_collection(ngo_id, "drafts").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(20).stream()
    return [doc.to_dict() for doc in docs]

def get_draft(ngo_id: str, draft_id: str) -> dict:
    doc = _get_collection(ngo_id, "drafts").document(draft_id).get()
    if not doc.exists:
         raise ValueError(f"Draft {draft_id} not found.")
    return doc.to_dict()

def delete_draft(ngo_id: str, draft_id: str):
    _get_collection(ngo_id, "drafts").document(draft_id).delete()


# ── BUILDS ──────────────────────────────────────────────────────

def save_build(ngo_id: str, payload: dict) -> dict:
    build_id = _uid()
    now = _now()
    item = {
        "id":               build_id,
        "ngo_id":           ngo_id,
        "title":            payload.get("title") or payload.get("grant_title") or "Built Proposal",
        "org_name":         payload.get("org_name", ""),
        "grant_title":      payload.get("grant_title", ""),
        "proposal_context": payload.get("proposal_context") or {},
        "matches_id":       payload.get("matches_id") or [],
        "budget_id":        payload.get("budget_id") or None,
        "sections":         payload.get("sections", {}),
        "section_order":    payload.get("section_order", []),
        "answers":          payload.get("answers", []),
        "word_count":       _word_count(payload.get("sections", {})),
        "created_at":       now,
        "updated_at":       now,
    }
    
    _get_collection(ngo_id, "builds").document(build_id).set(item)
    return item

def update_build(ngo_id: str, build_id: str, sections: dict, budget_id: str = None) -> dict:
    doc_ref = _get_collection(ngo_id, "builds").document(build_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise ValueError(f"Build {build_id} not found.")
        
    updates = {
        "sections": sections,
        "word_count": _word_count(sections),
        "updated_at": _now()
    }
    if budget_id is not None:
        updates["budget_id"] = budget_id
        
    doc_ref.update(updates)
    return doc_ref.get().to_dict()

def list_builds(ngo_id: str) -> list:
    docs = _get_collection(ngo_id, "builds").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(20).stream()
    return [doc.to_dict() for doc in docs]

def get_build(ngo_id: str, build_id: str) -> dict:
    doc = _get_collection(ngo_id, "builds").document(build_id).get()
    if not doc.exists:
         raise ValueError(f"Build {build_id} not found.")
    return doc.to_dict()

def delete_build(ngo_id: str, build_id: str):
    _get_collection(ngo_id, "builds").document(build_id).delete()


# ── BUDGETS ─────────────────────────────────────────────────────

def save_budget(ngo_id: str, payload: dict) -> dict:
    budget_id = _uid()
    now = _now()
    item = {
        "id":                   budget_id,
        "ngo_id":               ngo_id,
        "title":                payload.get("title") or payload.get("grant_title") or "Budget",
        "grant_title":          payload.get("grant_title", ""),
        "grant_id":             payload.get("grant_id", ""),
        "max_budget":           payload.get("max_budget", 0),
        "proposal_id":          payload.get("proposal_id") or None,
        "items":                payload.get("items", []),
        "total_requested":      payload.get("total_requested", 0),
        "locality_explanation": payload.get("locality_explanation", ""),
        "created_at":           now,
        "updated_at":           now,
    }
    
    _get_collection(ngo_id, "budgets").document(budget_id).set(item)

    # Back-link: update parent draft/build with this budget_id
    proposal_id = payload.get("proposal_id")
    if proposal_id:
        # Check if it's a draft
        draft_ref = _get_collection(ngo_id, "drafts").document(proposal_id)
        if draft_ref.get().exists:
            draft_ref.update({"budget_id": budget_id, "updated_at": now})
        else:
            # Check if it's a build
            build_ref = _get_collection(ngo_id, "builds").document(proposal_id)
            if build_ref.get().exists:
                build_ref.update({"budget_id": budget_id, "updated_at": now})

    return item

def list_budgets(ngo_id: str) -> list:
    docs = _get_collection(ngo_id, "budgets").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(20).stream()
    return [doc.to_dict() for doc in docs]

def get_budget(ngo_id: str, budget_id: str) -> dict:
    doc = _get_collection(ngo_id, "budgets").document(budget_id).get()
    if not doc.exists:
         raise ValueError(f"Budget {budget_id} not found.")
    return doc.to_dict()

def delete_budget(ngo_id: str, budget_id: str):
    _get_collection(ngo_id, "budgets").document(budget_id).delete()


# ── SUMMARY ─────────────────────────────────────────────────────

def get_summary(ngo_id: str) -> dict:
    """Fetches counts and recent items to populate the dashboard."""
    drafts = list_drafts(ngo_id)
    builds = list_builds(ngo_id)
    budgets = list_budgets(ngo_id)

    # All proposals = drafts + builds merged, newest first
    all_proposals = sorted(
        [{"_type": "draft",  **d} for d in drafts] +
        [{"_type": "build",  **b} for b in builds],
        key=lambda x: x.get("updated_at", ""), reverse=True,
    )

    return {
        "drafts_count":    len(drafts),
        "builds_count":    len(builds),
        "budgets_count":   len(budgets),
        "recent_drafts":   drafts[:3],
        "recent_builds":   builds[:3],
        "recent_budgets":  budgets[:3],
        "all_proposals":   all_proposals,  # for Draft + Budget page selectors
    }