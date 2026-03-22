"""
db/sessions.py

JSON file persistence for ProposalState.
Replaces Postgres for simpler local development.
"""

import json
import os
import logging
from state.proposal_state import ProposalState
import fcntl

log = logging.getLogger(__name__)

# Path to the JSON file
DB_FILE = os.path.join(os.path.dirname(__file__), "sessions.json")

def _load_db() -> dict[str, ProposalState]:
    """Internal: Load the entire sessions database from disk."""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to load sessions JSON: %s", e)
        return {}

def _save_db(db: dict[str, ProposalState]) -> None:
    """Internal: Save the entire sessions database to disk."""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(db, f, indent=2, ensure_ascii=False)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        log.error("Failed to save sessions JSON: %s", e)

# ── Public API ────────────────────────────────────────────────────────────────

def load_state(session_id: str) -> ProposalState | None:
    """
    Load a session's state from the JSON database.
    Returns None if the session does not exist.
    """
    db = _load_db()
    return db.get(session_id)

def save_state(state: ProposalState) -> None:
    """
    Upsert a session's state to the JSON database.
    """
    db = _load_db()
    db[state["session_id"]] = state
    _save_db(db)

def delete_state(session_id: str) -> None:
    """Remove a session."""
    db = _load_db()
    if session_id in db:
        del db[session_id]
        _save_db(db)

