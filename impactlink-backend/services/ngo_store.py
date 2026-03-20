# backend/services/ngo_store.py

'''
1. Firebase Auth handles the email duplication checks securely on Google's servers
2. Firebase Auth handles password hashing automatically.
3. Firebase Auth generates the unique uid for us, so we don't need the custom _slug function.
4. Firestore handles all the JSON reading, writing, and file management.
'''
from firebase_admin import firestore
from datetime import datetime

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
        "location":         "",
        "cause_area":       "",
        "sdgs":             [],
        "website":          "",
        "founding_year":    None,
        "team_size":        "",
        "key_activities":   [],
        "geographic_focus": [],
        "collab_open":      True,
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
    safe_updates["updated_at"] = datetime.now().isoformat()
    
    doc_ref.update(safe_updates)
    return doc_ref.get().to_dict()

def list_collab_profiles() -> list:
    db = _get_db() # Get the DB here
    docs = db.collection("ngo_profiles").where("collab_open", "==", True).stream()
    return [doc.to_dict() for doc in docs]