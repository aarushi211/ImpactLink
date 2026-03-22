"""
flows/improve_flow.py

Flow A: Improve an existing proposal against a selected grant.

Gate sequence:
    none
      → [auto] extract vocab + analyze gaps
    gap_review          ← HUMAN GATE (user reviews gap list, confirms sections to rewrite)
      → [auto] rewrite flagged sections (parallel) + score + retry
    draft_review        ← HUMAN GATE (user reviews diffs, edits sections inline)
      → [auto] finalize state
    final_save          ← HUMAN GATE (user confirms + downloads)
      → complete

Each call to advance() loads state, does exactly one step, saves state,
and returns a GateResponse the API layer sends to the frontend.
The frontend calls advance() again when the user submits a gate.
"""

import logging
import concurrent.futures
from typing import Any

from state.proposal_state import ProposalState, SectionResult
from db.sessions import load_state, save_state
from agents.vocab_extractor import extract_funder_vocab
from agents.gap_analysis_agent import analyze_gaps, apply_user_adjustments
from agents.rewriter_agent import rewrite_section, retry_rewrite, gaps_for_section
from agents.scoring_agent_v2 import score_section, needs_retry, is_flagged, MAX_RETRIES
from utils.diff import diff_sections

log = logging.getLogger(__name__)

# How many sections to rewrite in parallel.
# Keep at 2–3 to avoid rate-limit errors from Groq.
MAX_WORKERS = 2


# ── Public entry point ────────────────────────────────────────────────────────

def advance(session_id: str, user_input: dict | None = None) -> dict:
    """
    Advance Flow A by one step.

    Args:
        session_id: the session to load
        user_input: data from the frontend for the current gate.
                    None on the first call (gate="none").

    Returns:
        GateResponse dict — see _gate_response() helpers below.
        The frontend reads `response["gate"]` to know what to render.

    Raises:
        ValueError if session not found or flow is not "improve".
        RuntimeError on unexpected gate value.
    """
    state = load_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")
    if state["flow"] != "improve":
        raise ValueError(f"Session {session_id} is flow '{state['flow']}', not 'improve'")

    gate = state["gate"]
    user_input = user_input or {}

    if gate == "none":
        return _step_analyze(state)

    if gate == "gap_review":
        return _step_rewrite(state, user_input)

    if gate == "draft_review":
        return _step_finalize(state, user_input)

    if gate == "final_save":
        return _step_complete(state, user_input)

    raise RuntimeError(f"Unexpected gate value: {gate!r}")


# ── Step implementations ──────────────────────────────────────────────────────

def _step_analyze(state: ProposalState) -> dict:
    """
    Step 1 (gate=none → gap_review):
    Extract funder vocab, run gap analysis against existing sections.
    No user input required for this step.
    """
    log.info("[%s] step: analyze", state["session_id"])
    grant   = state["grant"]
    profile = state["profile"]

    # Extract funder vocabulary
    vocab = extract_funder_vocab(grant)
    state["funder_vocab"] = vocab

    # Gap analysis compares EXISTING SECTION TEXT against grant requirements.
    # Pull raw text from original_sections (set when session was created).
    existing_text = state["original_sections"]
    if not existing_text:
        log.warning("[%s] no original_sections — gap analysis will be shallow", state["session_id"])

    analysis = analyze_gaps(
        existing_sections=existing_text,
        grant=grant,
        funder_vocab=vocab,
    )
    state["analysis"] = analysis
    state["gate"] = "gap_review"
    save_state(state)

    return {
        "gate":           "gap_review",
        "funder_vocab":   vocab,
        "analysis":       analysis,
        # The frontend renders analysis as a checklist.
        # User can uncheck gaps and edit sections_to_rewrite.
        "instructions":   (
            "Review the gaps identified below. Uncheck any you disagree with. "
            "Add any additional context in the notes field. "
            "Confirm which sections should be rewritten."
        ),
    }


def _step_rewrite(state: ProposalState, user_input: dict) -> dict:
    """
    Step 2 (gate=gap_review → draft_review):
    User has reviewed the gap list. Rewrite confirmed sections in parallel.
    Score each. Retry up to MAX_RETRIES if below threshold.

    user_input expected keys:
        confirmed_gaps:      list[str]   — gap descriptions user kept
        user_additions:      str         — free-text notes
        sections_to_rewrite: list[str]   — section keys user confirmed
    """
    log.info("[%s] step: rewrite", state["session_id"])

    confirmed_gaps      = user_input.get("confirmed_gaps", [])
    user_additions      = user_input.get("user_additions", "")
    sections_to_rewrite = user_input.get("sections_to_rewrite",
                                         state["analysis"].get("sections_to_rewrite", []))

    # Merge user input back into analysis
    analysis = apply_user_adjustments(
        state["analysis"],
        confirmed_gaps,
        user_additions,
        sections_to_rewrite,
    )
    state["analysis"] = analysis

    # Snapshot original content before any rewriting
    # (original_sections was set at session creation, but re-confirm here)
    original_text = state["original_sections"]

    grant        = state["grant"]
    profile      = state["profile"]
    funder_vocab = state["funder_vocab"]

    # Rewrite sections in parallel
    # First, initialize new_sections with the original sections so unrewritten ones are preserved
    new_sections = {}
    for key, text in original_text.items():
        new_sections[key] = {
            "title": _section_title(key),
            "content": text,
            "score": 0,
            "retries": 0,
            "flagged": False,
        }
    new_sections.update(state.get("sections", {}))  # keep anything already in state["sections"]

    def rewrite_one(section_key: str) -> tuple[str, SectionResult]:
        title    = _section_title(section_key)
        original = original_text.get(section_key, "")
        relevant_gaps = gaps_for_section(analysis, section_key)

        # Initial rewrite
        content = rewrite_section(
            section_key      = section_key,
            section_title    = title,
            original_content = original,
            gaps_for_section = relevant_gaps,
            funder_vocab     = funder_vocab,
            grant            = grant,
            profile          = profile,
        )

        # Score + retry loop
        retry_count = state["retry_counts"].get(section_key, 0)
        last_score  = 0
        feedback    = ""

        while True:
            result = score_section(
                section_key   = section_key,
                section_title = title,
                content       = content,
                grant         = grant,
                funder_vocab  = funder_vocab,
            )
            last_score = result["score"]
            feedback   = result["feedback"]

            if not needs_retry(last_score, retry_count):
                break

            log.info(
                "[%s] section '%s' scored %d — retry %d/%d",
                state["session_id"], section_key, last_score,
                retry_count + 1, MAX_RETRIES,
            )
            content = retry_rewrite(
                section_title   = title,
                current_content = content,
                scorer_feedback = feedback,
                funder_vocab    = funder_vocab,
            )
            retry_count += 1

        flagged = is_flagged(last_score, retry_count)
        if flagged:
            log.warning(
                "[%s] section '%s' flagged after %d retries (score=%d)",
                state["session_id"], section_key, retry_count, last_score,
            )

        return section_key, SectionResult(
            title   = title,
            content = content,
            score   = last_score,
            retries = retry_count,
            flagged = flagged,
        )

    # Run rewrites in parallel with a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(rewrite_one, key): key
            for key in sections_to_rewrite
        }
        for future in concurrent.futures.as_completed(futures):
            section_key = futures[future]
            try:
                key, result = future.result()
                new_sections[key] = result
                state["retry_counts"][key] = result["retries"]
                if result["flagged"]:
                    if key not in state["flagged_sections"]:
                        state["flagged_sections"].append(key)
            except Exception as e:
                log.error("[%s] rewrite failed for '%s': %s",
                          state["session_id"], section_key, e, exc_info=True)

    state["sections"] = new_sections

    # Compute diffs: original text → final rewritten text
    revised_text = {k: v["content"] for k, v in new_sections.items()
                    if k in sections_to_rewrite}
    state["diffs"] = diff_sections(original_text, revised_text)

    state["gate"] = "draft_review"
    save_state(state)

    return {
        "gate":             "draft_review",
        "sections":         new_sections,
        "diffs":            state["diffs"],
        "flagged_sections": state["flagged_sections"],
        "instructions":     (
            "Review the rewritten sections below. "
            "Flagged sections scored low after 2 retries — review these carefully. "
            "Edit any section text directly before confirming."
        ),
    }


def _step_finalize(state: ProposalState, user_input: dict) -> dict:
    """
    Step 3 (gate=draft_review → final_save):
    User has reviewed and optionally edited sections.
    Save the final (user-edited) section content.

    user_input expected keys:
        sections: dict[section_key, str]  — user's edited section text
                  Only keys the user changed need to be included.
    """
    log.info("[%s] step: finalize", state["session_id"])

    user_edits = user_input.get("sections", {})
    for key, edited_text in user_edits.items():
        if key in state["sections"]:
            state["sections"][key]["content"] = edited_text
        else:
            # User added a section that wasn't in the rewrite list
            state["sections"][key] = SectionResult(
                title   = _section_title(key),
                content = edited_text,
                score   = 0,
                retries = 0,
                flagged = False,
            )

    state["gate"] = "final_save"
    save_state(state)

    return {
        "gate":     "final_save",
        "sections": state["sections"],
        "instructions": (
            "Your proposal is ready. Confirm to download."
        ),
    }


def _step_complete(state: ProposalState, user_input: dict) -> dict:
    """
    Step 4 (gate=final_save → complete):
    User confirmed. Mark session complete.
    Export is handled by the API layer (download endpoint).
    """
    log.info("[%s] step: complete", state["session_id"])
    state["gate"] = "complete"
    save_state(state)

    return {
        "gate":       "complete",
        "session_id": state["session_id"],
        "org_name":   state["profile"].get("org_name", ""),
        "grant_title": state["grant"].get("title", ""),
        "sections":   state["sections"],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

# Section key → human-readable title map.
# Imported from draft_agent.py's SECTIONS list to stay in sync.
def _section_title(key: str) -> str:
    try:
        from agents.draft_agent import SECTIONS
        mapping = {s["key"]: s["title"] for s in SECTIONS}
        return mapping.get(key, key.replace("_", " ").title())
    except ImportError:
        return key.replace("_", " ").title()
