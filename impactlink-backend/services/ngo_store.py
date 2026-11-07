# backend/services/ngo_store.py

'''
1. Firebase Auth handles the email duplication checks securely on Google's servers
2. Firebase Auth handles password hashing automatically.
3. Firebase Auth generates the unique uid for us, so we don't need the custom _slug function.
4. Firestore handles all the JSON reading, writing, and file management.
'''
from firebase_admin import firestore
from datetime import datetime
from services.eligibility import STATES, TYPES
from utils.privacy import validate_protected_terms

def _get_db():
    """Helper function to return the Firestore client lazily."""
    return firestore.client()

# ── Public API ─────────────────────────────────────────────────

def register(uid: str, email: str, org_name: str) -> dict:
    email = email.lower().strip()
    now = datetime.now().isoformat()
    db = _get_db() # Get the DB here

    doc_ref = db.collection("ngo_profiles").document(uid)

    profile = {
        "id":               uid,
        "email":            email,
        "org_name":         org_name,
        "mission":          "",
        "onboarding_completed": False,
        "location":         "",
        "cause_area":       "",
        "sdgs":             [],
        "website":          "",
        "founding_year":    None,
        "team_size":        "",
        "key_activities":   [],
        "target_beneficiaries": [],
        "geographic_focus": [],
        "applicant_type":   "",
        "project_states":   [],
        "privacy_redaction_terms": [],
        "collab_open":      False,
        "collab_interests": [],
        "total_applied":    0,
        "total_won":        0,
        "funding_secured":  0,
        "created_at":       now,
        "updated_at":       now,
    }
    
    doc_ref.set(profile)
    return profile

def get_profile(ngo_id: str) -> dict:
    db = _get_db() # Get the DB here
    doc_ref = db.collection("ngo_profiles").document(ngo_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise ValueError("Profile not found.")
        
    return doc.to_dict()

def update_profile(ngo_id: str, updates: dict) -> dict:
    PROTECTED = {"id", "email", "created_at"}
    db = _get_db() # Get the DB here
    
    doc_ref = db.collection("ngo_profiles").document(ngo_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise ValueError("Profile not found.")

    safe_updates = {k: v for k, v in updates.items() if k not in PROTECTED}
    if "org_name" in safe_updates:
        name = safe_updates["org_name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
            raise ValueError("Organization name must contain 1–200 characters.")
        safe_updates["org_name"] = name.strip()
    for key in ("onboarding_completed", "collab_open"):
        if key in safe_updates and not isinstance(safe_updates[key], bool):
            raise ValueError("Setup and collaboration preferences must be true or false.")
    year = safe_updates.get("founding_year")
    if year is not None and (type(year) is not int or not 1800 <= year <= datetime.now().year):
        raise ValueError("Enter a valid founding year, or leave it blank.")
    if "target_beneficiaries" in safe_updates:
        groups = safe_updates["target_beneficiaries"]
        if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups) or sum(map(len, groups)) > 5000:
            raise ValueError("Communities served must be a list of text entries, up to 5,000 characters in total.")
        safe_updates["target_beneficiaries"] = list(dict.fromkeys(group.strip() for group in groups if group.strip()))
    if "privacy_redaction_terms" in safe_updates:
        safe_updates["privacy_redaction_terms"] = list(validate_protected_terms(safe_updates["privacy_redaction_terms"]))
    if "applicant_type" in safe_updates and (not isinstance(safe_updates["applicant_type"], str) or safe_updates["applicant_type"] not in {"", *TYPES.values()}):
        raise ValueError("Choose a supported applicant type or leave it unspecified.")
    if "project_states" in safe_updates:
        states = safe_updates["project_states"]
        if not isinstance(states, list) or any(not isinstance(state, str) or state.strip().casefold() not in STATES for state in states):
            raise ValueError("Project states must be U.S. state names or codes, such as California or CA. Leave the list empty if unknown or outside the U.S.")
        safe_updates["project_states"] = sorted({STATES[state.strip().casefold()] for state in states})
    safe_updates["updated_at"] = datetime.now().isoformat()
    
    doc_ref.update(safe_updates)
    return doc_ref.get().to_dict()

def list_collab_profiles() -> list:
    db = _get_db() # Get the DB here
    docs = db.collection("ngo_profiles").where("collab_open", "==", True).stream()
    # Private redaction terms must never be published in collaborator directories.
    return [{key: value for key, value in doc.to_dict().items() if key != "privacy_redaction_terms"} for doc in docs]
