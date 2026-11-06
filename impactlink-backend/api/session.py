"""
api/session.py

Central HTTP endpoint for all session state transitions.
Uses LangGraph graphs for both flows.

LangGraph replaces:
    - db/sessions.py         (checkpointer handles persistence)
    - flows/improve_flow.py  (StateGraph with interrupt nodes)
    - flows/scratch_flow.py  (StateGraph with interrupt nodes)

All session interactions go through two endpoints:
    POST /api/v2/session                       — create a new session
    POST /api/v2/session/{session_id}/advance  — advance by one step

The gate field in the returned JSON tells the frontend what to render.

Gate values:
    gap_review    → gap checklist (Flow A)
    slot_filling  → single Q&A input (Flow B)
    slot_confirm  → slot review/edit form (Flow B)
    draft_review  → section editor with tracked changes (both)
    final_save    → confirm + download (both)
    complete      → done

FastAPI wiring (add to main.py):
    from api.session import router
    app.include_router(router, prefix="/api/v2")

Or manually:
    from api.session import create_session, advance_session, get_session_status

    @app.post("/api/v2/session")
    def create(body: dict, request: Request):
        user_id = get_user_id(request)   # your existing auth
        return create_session(body, user_id)

    @app.post("/api/v2/session/{session_id}/advance")
    def advance(session_id: str, body: dict, request: Request):
        user_id = get_user_id(request)
        return advance_session(session_id, body, user_id)

    @app.get("/api/v2/session/{session_id}")
    def status(session_id: str, request: Request):
        user_id = get_user_id(request)
        return get_session_status(session_id, user_id)
"""

import uuid
import logging
from typing import Iterator, Optional

import os
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from agents.gap_analysis_agent import validate_user_additions
from flows.improve_flow import build_improve_graph
from flows.scratch_flow import build_scratch_graph
from utils.diff import normalize_section_headings
from utils.session_execution import session_execution, is_session_running, resume_session_command
from services.application import normalize_spec, validate_application, validate_review_input, merge_checklist, ensure_ai_drafting_allowed

log = logging.getLogger(__name__)


def _application_response(response, grant):
    spec = response.get("application_spec") or grant.get("application_spec")
    if spec is not None:
        response["application_spec"] = spec
        response["application_validation"] = validate_application(response.get("sections", {}), {"application_spec": spec})
    return response


# ── Checkpointer — shared by both graphs ──────────────────────────────────────
# PostgresSaver stores all graph state in a PostgreSQL database.
# Both graphs use the same checkpointer so session IDs are globally unique.

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable is required.")
pool = ConnectionPool(
    conninfo=db_url,
    min_size=0,
    max_size=20,
    max_idle=60,
    check=ConnectionPool.check_connection,
    kwargs={"autocommit": True, "prepare_threshold": None, "connect_timeout": 10}
)
checkpointer = PostgresSaver(pool)
checkpointer.setup()

# ── Compiled graphs — built once at startup ───────────────────────────────────
# Building the graph is cheap but calling compile() repeatedly is wasteful.
# Both graphs share the same checkpointer instance.

improve_graph = build_improve_graph(checkpointer)
scratch_graph = build_scratch_graph(checkpointer)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _graph_for(flow: str):
    """Return the correct compiled graph for a flow name."""
    if flow == "improve":
        return improve_graph
    if flow == "scratch":
        return scratch_graph
    raise ValueError(f"Unknown flow: {flow!r}")


def _config(session_id: str) -> dict:
    """
    LangGraph config dict. thread_id is how LangGraph identifies a session.
    Every invoke/resume call for the same session must use the same thread_id.
    """
    return {"configurable": {"thread_id": session_id}}


def _get_graph_state(session_id: str, flow: str) -> dict:
    """
    Load the current graph state from the checkpointer without advancing.
    Returns the state values dict or an empty dict if session not found.
    """
    graph = _graph_for(flow)
    state = graph.get_state(_config(session_id))
    return state.values if state else {}


def _pending_interrupt(snapshot) -> Optional[dict]:
    """Return the active interrupt payload from a LangGraph state snapshot."""
    for task in getattr(snapshot, "tasks", ()):
        for pending in getattr(task, "interrupts", ()):
            value = getattr(pending, "value", None)
            if isinstance(value, dict):
                return value
    return None


def _find_interrupts(value):
    """Find interrupt payloads in flat or node-nested stream update chunks."""
    if isinstance(value, dict):
        if "__interrupt__" in value:
            return value["__interrupt__"]
        for nested in value.values():
            found = _find_interrupts(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_interrupts(nested)
            if found is not None:
                return found
    return None


def _check_ownership(state_values: dict, user_id: Optional[str]):
    """Raise if this session belongs to a different user."""
    owner = state_values.get("user_id")
    if owner and user_id and owner != user_id:
        raise ValueError("Unauthorized: session belongs to a different user.")


def _extract_gate_response(raw_result) -> dict:
    """
    LangGraph's invoke() returns the full state dict when the graph runs to
    completion or to an interrupt. When interrupted, the interrupt payload
    is available via the __interrupt__ key.

    This helper extracts the interrupt payload (what we want to send to the
    frontend) or falls back to reading the gate from state.
    """
    # When a node calls interrupt(payload), LangGraph stores that payload
    # in the result under __interrupt__. That's what we send to the frontend.
    interrupts = raw_result.get("__interrupt__")
    if interrupts:
        # interrupts is a list — take the first (there's only ever one at a time)
        return interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]

    # Graph ran to completion (hit END node)
    gate = raw_result.get("gate", "complete")
    return {
        "gate":        gate,
        "session_id":  raw_result.get("session_id", ""),
        "org_name":    (raw_result.get("profile") or {}).get("org_name")
                       or (raw_result.get("profile") or {}).get("organization_name", ""),
        "grant_title": (raw_result.get("grant") or {}).get("title", ""),
        "sections":    raw_result.get("sections", {}),
    }


# ── Session creation ───────────────────────────────────────────────────────────

def create_session(body: dict, user_id: Optional[str] = None) -> dict:
    """
    Create a new proposal session and run until the first interrupt.

    Required body keys:
        flow:    "improve" | "scratch"
        profile: dict — NGO profile
        grant:   dict — selected grant

    For flow="improve" only:
        original_sections: dict[section_key, str | {content: str}]

    Returns:
        The first interrupt payload — what the frontend should show first.
        Always contains {"gate": str, "session_id": str, ...}
    """
    flow    = body.get("flow")
    profile = body.get("profile", {})
    grant   = body.get("grant", {})
    if isinstance(grant, dict) and grant.get("application_spec") is not None:
        grant = {**grant, "application_spec": normalize_spec(grant["application_spec"])}

    if flow not in ("improve", "scratch"):
        raise ValueError(f"flow must be 'improve' or 'scratch', got {flow!r}")
    if flow == "improve" and not profile:
        raise ValueError("profile is required for the improve flow")
    if not grant:
        raise ValueError("grant is required")
    ensure_ai_drafting_allowed(grant)

    session_id = str(uuid.uuid4())

    # Normalize original_sections — accept {key: str} or {key: {content: str}}
    original_sections = {}
    if flow == "improve":
        for key, val in body.get("original_sections", {}).items():
            original_sections[key] = val if isinstance(val, str) else val.get("content", "")
        spec = grant.get("application_spec") or {}
        if not spec.get("sections") and spec.get("stage", "full_proposal") == "full_proposal":
            original_sections = normalize_section_headings(original_sections)

    # Initial state — same shape as ProposalState TypedDict
    initial_state = {
        "session_id":        session_id,
        "user_id":           user_id,
        "flow":              flow,
        "profile":           profile,
        "grant":             grant,
        "original_sections": original_sections,
        "funder_vocab":      [],
        "drafting_plan":     None,
        "agent_trace":       [],
        "slots":             {},
        "analysis":          None,
        "sections":          {},
        "diffs":             {},
        "gate":              "none",
        "retry_counts":      {},
        "flagged_sections":  [],
    }

    graph  = _graph_for(flow)
    config = _config(session_id)

    log.info("Creating session %s (flow=%s)", session_id, flow)

    # invoke() runs the graph from the start until it hits interrupt() or END
    raw_result = graph.invoke(initial_state, config)
    response   = _extract_gate_response(raw_result)
    response["session_id"] = session_id
    response["original_sections"] = original_sections

    return _application_response(response, grant)


# ── Session advancement ────────────────────────────────────────────────────────

def advance_session(
    session_id: str,
    user_input: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> dict:
    with session_execution(session_id):
        return _advance_session(session_id, user_input, user_id)


def _advance_session(
    session_id: str,
    user_input: Optional[dict] = None,
    user_id:    Optional[str]  = None,
) -> dict:
    """
    Advance a session by one step.

    Resumes the graph from its last interrupt point, passing user_input
    as the return value of interrupt(). Runs until the next interrupt or END.

    Args:
        session_id: the session to resume
        user_input: the user's response to the current gate.
                    For gap_review:   {confirmed_gaps, user_additions, sections_to_rewrite}
                    For slot_filling: {answer, slot_key}
                    For slot_confirm: {slots: {key: value}}
                    For draft_review: {sections: {key: edited_text}}
                    For final_save:   {} (empty — just confirming)

    Returns:
        The next interrupt payload or completion response.
    """
    user_input = user_input or {}

    # Load state to verify ownership and get flow type
    # We need flow to pick the right graph
    # Try improve first, then scratch (they share the same checkpointer)
    state_values = None
    flow         = None

    for candidate_flow in ("improve", "scratch"):
        sv = _get_graph_state(session_id, candidate_flow)
        if sv:
            state_values = sv
            flow         = sv.get("flow", candidate_flow)
            break

    if not state_values:
        raise ValueError(f"Session not found: {session_id}")

    _check_ownership(state_values, user_id)

    if state_values.get("gate") not in {"draft_review", "final_save", "complete"}:
        ensure_ai_drafting_allowed(state_values.get("grant", {}))
    validate_review_input(state_values, user_input)
    merge_checklist(state_values.get("grant", {}), user_input)

    if state_values.get("gate") == "gap_review" and "user_additions" in user_input:
        validate_user_additions(user_input["user_additions"])

    if state_values.get("gate") == "complete":
        return {
            "gate":       "complete",
            "session_id": session_id,
            "sections":   state_values.get("sections", {}),
        }

    graph  = _graph_for(flow)
    config = _config(session_id)

    log.info("Advancing session %s (flow=%s, gate=%s)",
             session_id, flow, state_values.get("gate"))

    # Command.RESUME tells LangGraph to continue from the last interrupt()
    # and return user_input as the value of that interrupt() call.
    raw_result = graph.invoke(
        resume_session_command(user_input),
        config,
    )

    response = _extract_gate_response(raw_result)
    response["session_id"] = session_id
    return _application_response(response, raw_result.get("grant") or state_values.get("grant", {}))


def stream_advance_session(
    session_id: str,
    user_input: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> Iterator[dict]:
    with session_execution(session_id):
        yield from _stream_advance_session(session_id, user_input, user_id)


def _stream_advance_session(
    session_id: str,
    user_input: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> Iterator[dict]:
    """Resume a session and yield rewrite tokens followed by its next gate."""
    user_input = user_input or {}
    state_values = None
    flow = None

    for candidate_flow in ("improve", "scratch"):
        state = _get_graph_state(session_id, candidate_flow)
        if state:
            state_values = state
            flow = state.get("flow", candidate_flow)
            break

    if not state_values:
        raise ValueError(f"Session not found: {session_id}")

    _check_ownership(state_values, user_id)
    if state_values.get("gate") not in {"draft_review", "final_save", "complete"}:
        ensure_ai_drafting_allowed(state_values.get("grant", {}))
    validate_review_input(state_values, user_input)
    merge_checklist(state_values.get("grant", {}), user_input)
    if state_values.get("gate") == "gap_review" and "user_additions" in user_input:
        validate_user_additions(user_input["user_additions"])

    if state_values.get("gate") == "complete":
        yield {
            "type": "complete",
            "response": {
                "gate": "complete",
                "session_id": session_id,
                "sections": state_values.get("sections", {}),
            },
        }
        return

    graph = _graph_for(flow)
    interrupts = None
    for mode, chunk in graph.stream(
        resume_session_command(user_input),
        _config(session_id),
        stream_mode=["messages", "updates", "custom"],
    ):
        if mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") in {
                "progress", "token", "section_start", "section_status", "section_complete"
            }:
                yield chunk
        elif mode == "messages":
            message, metadata = chunk
            if "draft_section_stream" not in metadata.get("tags", []):
                continue
            content = message.content
            if isinstance(content, str) and content:
                yield {
                    "type": "token",
                    "section_key": metadata.get("section_key", ""),
                    "content": content,
                }
        elif mode == "updates":
            stream_interrupts = _find_interrupts(chunk)
            if stream_interrupts is not None:
                interrupts = stream_interrupts

    if interrupts:
        raw_result = {"__interrupt__": interrupts}
    else:
        snapshot = graph.get_state(_config(session_id))
        pending = _pending_interrupt(snapshot)
        raw_result = (
            {"__interrupt__": [pending]}
            if pending
            else (snapshot.values if snapshot else {})
        )
    response = _extract_gate_response(raw_result)
    response["session_id"] = session_id
    yield {"type": "complete", "response": _application_response(response, raw_result.get("grant") or state_values.get("grant", {}))}


# ── Session status ─────────────────────────────────────────────────────────────

def get_session_status(
    session_id: str,
    user_id:    Optional[str] = None,
) -> dict:
    """
    Return current session state without advancing.
    Used by the frontend to re-hydrate after a page refresh.
    """
    # Try both flows
    state_values = None
    snapshot = None
    flow = None
    for candidate_flow in ("improve", "scratch"):
        candidate_snapshot = _graph_for(candidate_flow).get_state(_config(session_id))
        if candidate_snapshot and candidate_snapshot.values:
            snapshot = candidate_snapshot
            state_values = candidate_snapshot.values
            flow = candidate_flow
            break

    if not state_values:
        raise ValueError(f"Session not found: {session_id}")

    _check_ownership(state_values, user_id)

    pending = _pending_interrupt(snapshot) if snapshot else None
    response = dict(pending or {})
    response.update({
        "session_id":       session_id,
        "running":          is_session_running(session_id),
        "flow":             state_values.get("flow", flow),
        "gate":             response.get("gate", state_values.get("gate", "none")),
        "flagged_sections": response.get("flagged_sections", state_values.get("flagged_sections", [])),
        "sections":         response.get("sections", state_values.get("sections", {})),
        "original_sections": state_values.get("original_sections", {}),
        "analysis":         response.get("analysis", state_values.get("analysis")),
        "slots":            response.get("slots", state_values.get("slots", {})),
        "diffs":            response.get("diffs", state_values.get("diffs", {})),
        "funder_vocab":     response.get("funder_vocab", state_values.get("funder_vocab", [])),
    })
    return _application_response(response, state_values.get("grant", {}))
