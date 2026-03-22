"""
flows/scratch_flow.py

Flow B: Write a proposal from scratch via guided slot-filling Q&A.

Gate sequence:
    none
      → [auto] extract funder vocab, initialize slots, send first question
    slot_filling        ← HUMAN GATE (repeating: user answers one question at a time)
      → [auto] extract slots, send next question OR advance when all filled
    slot_confirm        ← HUMAN GATE (user reviews all collected info, edits inline)
      → [auto] draft all sections + score + retry
    draft_review        ← HUMAN GATE (user reviews drafted proposal, edits inline)
      → [auto] finalize state
    final_save          ← HUMAN GATE (user confirms + downloads)
      → complete

advance() handles both the slot_filling loop AND gate transitions.
The frontend sends the same endpoint call for every user interaction.
"""

import logging
import concurrent.futures

from state.proposal_state import ProposalState, SectionResult
from db.sessions import load_state, save_state
from agents.vocab_extractor import extract_funder_vocab
from agents.slot_extractor import (
    initial_slots, next_question, extract_slots,
    apply_extractions, is_slot_exhausted, slots_to_profile,
)
from agents.scoring_agent_v2 import score_section, needs_retry, is_flagged, MAX_RETRIES
from agents.draft_agent import SECTIONS, _build_grant_context, _extract_user_values
from agents.rewriter_agent import retry_rewrite
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

MAX_WORKERS = 2

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

# ── Public entry point ────────────────────────────────────────────────────────

def advance(session_id: str, user_input: dict | None = None) -> dict:
    """
    Advance Flow B by one step.

    Args:
        session_id: the session to load
        user_input: data from the frontend.
            During slot_filling: {"answer": str}
            During slot_confirm: {"slots": {key: value, ...}}
            During draft_review: {"sections": {key: str, ...}}
            During final_save:   {} (just a confirmation)

    Returns:
        GateResponse dict. Frontend reads `response["gate"]` to know what to show.
    """
    state = load_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")
    if state["flow"] != "scratch":
        raise ValueError(f"Session {session_id} is flow '{state['flow']}', not 'scratch'")

    gate = state["gate"]
    user_input = user_input or {}

    if gate == "none":
        return _step_init(state)

    if gate == "slot_filling":
        return _step_slot_filling(state, user_input)

    if gate == "slot_confirm":
        return _step_draft(state, user_input)

    if gate == "draft_review":
        return _step_finalize(state, user_input)

    if gate == "final_save":
        return _step_complete(state)

    raise RuntimeError(f"Unexpected gate value: {gate!r}")


# ── Step implementations ──────────────────────────────────────────────────────

def _step_init(state: ProposalState) -> dict:
    """
    Step 1 (gate=none → slot_filling):
    Extract funder vocab, initialize slot state, ask first question.
    """
    log.info("[%s] step: init", state["session_id"])

    vocab = extract_funder_vocab(state["grant"])
    state["funder_vocab"] = vocab
    state["slots"] = initial_slots()
    state["gate"] = "slot_filling"
    save_state(state)

    # Ask the first question
    result = next_question(state["slots"])
    key, question = result  # next_question returns None only when all filled

    return {
        "gate":          "slot_filling",
        "slot_key":      key,
        "question":      question,
        "slots_filled":  0,
        "slots_total":   len(state["slots"]),
        "progress":      0,
    }


def _step_slot_filling(state: ProposalState, user_input: dict) -> dict:
    """
    Step 2 (gate=slot_filling, repeating):
    Process one user answer, send next question OR advance to slot_confirm.

    user_input expected keys:
        answer:   str — the user's free-text answer
        slot_key: str — which slot was being asked (for ask_count tracking)
    """
    answer    = user_input.get("answer", "").strip()
    asked_key = user_input.get("slot_key", "")

    if not answer:
        # Empty answer — re-ask the same question
        result = next_question(state["slots"])
        if result is None:
            return _advance_to_slot_confirm(state)
        key, question = result
        return {
            "gate":     "slot_filling",
            "slot_key": key,
            "question": question,
            "warning":  "Please provide an answer before continuing.",
            **_slot_progress(state["slots"]),
        }

    # Extract slots from the answer
    extracted = extract_slots(answer, state["slots"])
    state["slots"] = apply_extractions(state["slots"], extracted, asked_key)

    if extracted:
        log.info("[%s] filled slots: %s", state["session_id"], list(extracted.keys()))
    else:
        log.info("[%s] no slots confidently filled from answer to '%s'", state["session_id"], asked_key)

    save_state(state)

    # Check if the slot we just asked is exhausted (asked MAX times, still unfilled)
    asked_slot = state["slots"].get(asked_key, {})
    if is_slot_exhausted(asked_slot):
        log.warning("[%s] slot '%s' exhausted — flagging for human review", state["session_id"], asked_key)
        if asked_key not in state["flagged_sections"]:
            state["flagged_sections"].append(asked_key)

    # Find next unfilled, non-exhausted slot
    nxt = next_question(state["slots"])

    if nxt is None:
        # All slots filled (or exhausted) — advance to confirm gate
        return _advance_to_slot_confirm(state)

    key, question = nxt

    # Check if next slot is already exhausted — skip ahead
    while is_slot_exhausted(state["slots"].get(key, {})):
        state["slots"][key]["filled"] = True  # mark exhausted as filled to skip
        nxt = next_question(state["slots"])
        if nxt is None:
            return _advance_to_slot_confirm(state)
        key, question = nxt

    save_state(state)

    return {
        "gate":     "slot_filling",
        "slot_key": key,
        "question": question,
        **_slot_progress(state["slots"]),
    }


def _advance_to_slot_confirm(state: ProposalState) -> dict:
    """Transition to slot_confirm gate."""
    state["gate"] = "slot_confirm"
    save_state(state)

    filled   = {k: v for k, v in state["slots"].items() if v.get("filled")}
    unfilled = [k for k, v in state["slots"].items() if not v.get("filled")]

    return {
        "gate":             "slot_confirm",
        "slots":            state["slots"],
        "flagged_slots":    unfilled,
        "instructions":     (
            "Review the information collected below. "
            "Edit any field before confirming. "
            "Flagged fields were not answered — please fill them in now."
        ),
    }


def _step_draft(state: ProposalState, user_input: dict) -> dict:
    """
    Step 3 (gate=slot_confirm → draft_review):
    User confirmed (and possibly edited) slot values.
    Build proposal profile and draft all sections.

    user_input expected keys:
        slots: dict[slot_key, str] — user's confirmed/edited values
    """
    log.info("[%s] step: draft", state["session_id"])

    # Apply any user edits to slots
    user_slot_edits = user_input.get("slots", {})
    for key, value in user_slot_edits.items():
        if key in state["slots"]:
            state["slots"][key]["value"]  = value
            state["slots"][key]["filled"] = bool(value and value.strip())

    # Convert slots → proposal profile
    profile = slots_to_profile(state["slots"])
    state["profile"] = profile

    grant     = state["grant"]
    grant_ctx = _build_grant_context(grant)
    vocab     = state["funder_vocab"]

    from agents.vocab_extractor import vocab_to_prompt_str
    vocab_str = vocab_to_prompt_str(vocab)

    # Import section prompt from draft_agent for consistency
    from agents.draft_agent import SECTION_PROMPT
    chain = SECTION_PROMPT | llm

    def draft_one(section: dict) -> tuple[str, SectionResult]:
        user_values = _extract_user_values(profile)
        response = chain.invoke({
            "section_title": section["title"],
            "word_target":   section["word_target"],
            "instructions":  section["instructions"],
            "proposal":      str(profile),
            "grant":         str(grant_ctx),
            "user_values":   user_values + f"\n\nFunder vocabulary to use:\n{vocab_str}",
        })
        content = response.content.strip()

        # Score + retry loop
        retry_count = 0
        last_score  = 0
        feedback    = ""

        while True:
            result = score_section(
                section_key   = section["key"],
                section_title = section["title"],
                content       = content,
                grant         = grant,
                funder_vocab  = vocab,
            )
            last_score = result["score"]
            feedback   = result["feedback"]

            if not needs_retry(last_score, retry_count):
                break

            log.info(
                "[%s] section '%s' scored %d — retry %d/%d",
                state["session_id"], section["key"],
                last_score, retry_count + 1, MAX_RETRIES,
            )
            content = retry_rewrite(
                section_title   = section["title"],
                current_content = content,
                scorer_feedback = feedback,
                funder_vocab    = vocab,
            )
            retry_count += 1

        flagged = is_flagged(last_score, retry_count)
        return section["key"], SectionResult(
            title   = section["title"],
            content = content,
            score   = last_score,
            retries = retry_count,
            flagged = flagged,
        )

    # Draft all sections in parallel
    new_sections = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(draft_one, s): s["key"] for s in SECTIONS}
        for future in concurrent.futures.as_completed(futures):
            section_key = futures[future]
            try:
                key, result = future.result()
                new_sections[key] = result
                state["retry_counts"][key] = result["retries"]
                if result["flagged"] and key not in state["flagged_sections"]:
                    state["flagged_sections"].append(key)
            except Exception as e:
                log.error("[%s] draft failed for '%s': %s",
                          state["session_id"], section_key, e, exc_info=True)

    state["sections"] = new_sections
    state["gate"]     = "draft_review"
    save_state(state)

    return {
        "gate":             "draft_review",
        "sections":         new_sections,
        "flagged_sections": state["flagged_sections"],
        "instructions":     (
            "Your proposal draft is ready. "
            "Review each section and edit as needed. "
            "Flagged sections scored low — review these carefully."
        ),
    }


def _step_finalize(state: ProposalState, user_input: dict) -> dict:
    """
    Step 4 (gate=draft_review → final_save):
    Save user's edited sections.
    """
    log.info("[%s] step: finalize", state["session_id"])

    user_edits = user_input.get("sections", {})
    for key, text in user_edits.items():
        if key in state["sections"]:
            state["sections"][key]["content"] = text

    state["gate"] = "final_save"
    save_state(state)

    return {
        "gate":         "final_save",
        "sections":     state["sections"],
        "instructions": "Your proposal is ready. Confirm to download.",
    }


def _step_complete(state: ProposalState) -> dict:
    """Step 5 (gate=final_save → complete)."""
    log.info("[%s] step: complete", state["session_id"])
    state["gate"] = "complete"
    save_state(state)

    return {
        "gate":        "complete",
        "session_id":  state["session_id"],
        "org_name":    state["profile"].get("organization_name", ""),
        "grant_title": state["grant"].get("title", ""),
        "sections":    state["sections"],
    }


# ── Progress helper ───────────────────────────────────────────────────────────

def _slot_progress(slots: dict) -> dict:
    total  = len(slots)
    filled = sum(1 for v in slots.values() if v.get("filled"))
    return {
        "slots_filled": filled,
        "slots_total":  total,
        "progress":     round(filled / total * 100) if total else 0,
    }
