"""
services/ngo_store.py
─────────────────────────────────────────────────────────────────
Simple JSON-file store for NGO profiles.
Stored at data/ngo_profiles.json

Schema per NGO:
{
  "id":              str  (slug: org name lowercased + 4-char hash),
  "email":           str,
  "password_hash":   str  (sha256 hex — no plaintext ever stored),
  "org_name":        str,
  "mission":         str,
  "location":        str,
  "cause_area":      str,
  "sdgs":            List[str],
  "website":         str,
  "founding_year":   int | null,
  "team_size":       str,
  "key_activities":  List[str],
  "geographic_focus":List[str],
  "collab_open":     bool,   ← for future NGO matching
  "collab_interests":List[str],
  "total_applied":   int,
  "total_won":       int,
  "funding_secured": int,
  "created_at":      ISO str,
  "updated_at":      ISO str,
}
"""

import json, hashlib, uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "ngo_profiles.json"


def _load() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {}


def _save(db: dict):
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(db, indent=2))


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _slug(org_name: str) -> str:
    base = org_name.lower().replace(" ", "_")[:20]
    suffix = uuid.uuid4().hex[:4]
    return f"{base}_{suffix}"


def _strip(profile: dict) -> dict:
    """Remove password_hash before sending to frontend."""
    return {k: v for k, v in profile.items() if k != "password_hash"}


# ── Public API ─────────────────────────────────────────────────

def register(email: str, password: str, org_name: str) -> dict:
    """Create a new NGO account. Returns stripped profile or raises ValueError."""
    db = _load()
    email = email.lower().strip()

    # Check duplicate email
    for profile in db.values():
        if profile["email"] == email:
            raise ValueError("An account with this email already exists.")

    ngo_id = _slug(org_name)
    now = datetime.now().isoformat()

    profile = {
        "id":               ngo_id,
        "email":            email,
        "password_hash":    _hash(password),
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
    db[ngo_id] = profile
    _save(db)
    return _strip(profile)


def login(email: str, password: str) -> dict:
    """Return stripped profile if credentials match, else raise ValueError."""
    db = _load()
    email = email.lower().strip()
    pw_hash = _hash(password)

    for profile in db.values():
        if profile["email"] == email and profile["password_hash"] == pw_hash:
            return _strip(profile)

    raise ValueError("Invalid email or password.")


def get_profile(ngo_id: str) -> dict:
    db = _load()
    if ngo_id not in db:
        raise ValueError("Profile not found.")
    return _strip(db[ngo_id])


def update_profile(ngo_id: str, updates: dict) -> dict:
    """Merge updates into the profile. Ignores protected fields."""
    PROTECTED = {"id", "email", "password_hash", "created_at"}
    db = _load()
    if ngo_id not in db:
        raise ValueError("Profile not found.")

    for k, v in updates.items():
        if k not in PROTECTED:
            db[ngo_id][k] = v
    db[ngo_id]["updated_at"] = datetime.now().isoformat()
    _save(db)
    return _strip(db[ngo_id])


def list_collab_profiles() -> list:
    """Return all profiles with collab_open=True (for future NGO matching)."""
    db = _load()
    return [_strip(p) for p in db.values() if p.get("collab_open")]