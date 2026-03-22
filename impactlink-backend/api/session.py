"""
api/session.py

Central HTTP endpoint for all session state transitions.
Framework-agnostic — adapt to Flask, FastAPI, or Django as needed.

All session interactions go through two endpoints:
    POST /api/session                  — create a new session
    POST /api/session/{session_id}/advance  — advance by one step

The gate field in the returned JSON tells the frontend what to render next.

Gate values and what the frontend should show:
    gap_review    → gap analysis checklist (Flow A)
    slot_filling  → single Q&A input (Flow B)
    slot_confirm  → slot review/edit form (Flow B)
    draft_review  → section editor with tracked changes (both flows)
    final_save    → confirmation + download button (both flows)
    complete      → done state (both flows)

Example (FastAPI):
    from fastapi import FastAPI, HTTPException
    from api.session import create_session, advance_session

    app = FastAPI()

    @app.post("/api/session")
    def create(body: dict):
        return create_session(body)

    @app.post("/api/session/{session_id}/advance")
    def advance(session_id: str, body: dict = {}):
        return advance_session(session_id, body)
"""

import uuid
import logging
from db.sessions import load_state, save_state
from state.proposal_state import new_state
from flows.improve_flow import advance as improve_advance
from flows.scratch_flow import advance as scratch_advance

log = logging.getLogger(__name__)


# ── Session creation ──────────────────────────────────────────────────────────

def create_session(body: dict) -> dict:
    """
    Create a new proposal session.

    Required body keys:
        flow:    "improve" | "scratch"
        profile: dict — NGO profile
        grant:   dict — selected grant

    For flow="improve" only:
        original_sections: dict[section_key, str]
            The existing proposal's section texts (plain strings).
            This is what the gap analysis compares against the grant.

    Returns:
        {"session_id": str, "gate": "none"}
    """
    flow    = body.get("flow")
    profile = body.get("profile", {})
    grant   = body.get("grant", {})

    if flow not in ("improve", "scratch"):
        raise ValueError(f"flow must be 'improve' or 'scratch', got {flow!r}")
    if flow == "improve" and not profile:
        raise ValueError("profile is required for the 'improve' flow")
    if not grant:
        raise ValueError("grant is required")

    session_id = str(uuid.uuid4())

    # For the improve flow, extract plain text from existing sections.
    # Caller may pass either {key: str} or {key: {title, content, ...}}
    original_sections = {}
    if flow == "improve":
        raw = body.get("original_sections", {})
        for key, val in raw.items():
            if isinstance(val, str):
                original_sections[key] = val
            elif isinstance(val, dict):
                original_sections[key] = val.get("content", "")

    state = new_state(
        session_id        = session_id,
        flow              = flow,
        profile           = profile,
        grant             = grant,
        original_sections = original_sections,
    )
    save_state(state)

    log.info("Created session %s (flow=%s)", session_id, flow)
    return {"session_id": session_id, "gate": "none"}


# ── Session advancement ───────────────────────────────────────────────────────

def advance_session(session_id: str, user_input: dict | None = None) -> dict:
    """
    Advance a session by one step.

    Loads state, routes to the correct flow, returns GateResponse.

    Args:
        session_id: the session to advance
        user_input: gate-specific data from the frontend (see gate docs above)

    Returns:
        GateResponse dict with at minimum: {"gate": str}

    Raises:
        ValueError if session not found
        RuntimeError on unexpected internal state
    """
    state = load_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")

    if state["gate"] == "complete":
        return {"gate": "complete", "session_id": session_id}

    flow = state["flow"]
    log.info("Advancing session %s (flow=%s, gate=%s)", session_id, flow, state["gate"])

    if flow == "improve":
        return improve_advance(session_id, user_input)
    elif flow == "scratch":
        return scratch_advance(session_id, user_input)
    else:
        raise RuntimeError(f"Unknown flow: {flow!r}")


# ── Session status ────────────────────────────────────────────────────────────

def get_session_status(session_id: str) -> dict:
    """
    Return lightweight session status without advancing it.
    Useful for the frontend to re-hydrate after a page refresh.
    """
    state = load_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")

    return {
        "session_id":       state["session_id"],
        "flow":             state["flow"],
        "gate":             state["gate"],
        "flagged_sections": state["flagged_sections"],
        "sections":         state.get("sections", {}),
        "analysis":         state.get("analysis"),
        "slots":            state.get("slots", {}),
    }
