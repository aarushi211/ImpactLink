"""
flows/scratch_flow_lg.py — fixed: no module-level LLM singleton
"""

import os
import random
import logging
import concurrent.futures

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from state.proposal_state import ProposalState, SectionResult
from agents.vocab_extractor import extract_funder_vocab, vocab_to_prompt_str
from agents.slot_extractor import (
    initial_slots, next_question, extract_slots,
    apply_extractions, is_slot_exhausted, slots_to_profile,
)
from agents.scoring_agent import score_section, needs_retry, is_flagged, MAX_RETRIES
from agents.prompts import SECTIONS, _build_grant_context, _extract_user_values, SECTION_PROMPT
from agents.rewriter_agent import retry_rewrite
from utils.llm import RotatingGroq
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

MAX_WORKERS = 2

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm(temperature: float = 0.3) -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=temperature, groq_api_key=key)


# ── Node functions ─────────────────────────────────────────────────────────────

def node_init_slots(state: ProposalState) -> dict:
    log.info("[%s] node: init_slots", state["session_id"])
    vocab = extract_funder_vocab(state["grant"])
    slots = initial_slots(state.get("profile"))
    return {"funder_vocab": vocab, "slots": slots, "gate": "slot_filling"}


def node_slot_filling(state: ProposalState) -> dict:
    log.info("[%s] node: slot_filling", state["session_id"])

    result = next_question(state["slots"])
    if result is None:
        return {"gate": "slot_confirm"}

    current_key, current_question = result

    user_input = interrupt({
        "gate":     "slot_filling",
        "slot_key": current_key,
        "question": current_question,
        **_slot_progress(state["slots"]),
    })

    answer    = user_input.get("answer", "").strip()
    asked_key = user_input.get("slot_key", current_key)

    updated_slots   = state["slots"]
    updated_flagged = list(state["flagged_sections"])

    if answer:
        extracted     = extract_slots(answer, updated_slots)
        updated_slots = apply_extractions(updated_slots, extracted, asked_key)

        if extracted:
            log.info("[%s] filled slots: %s", state["session_id"], list(extracted.keys()))
        else:
            log.info("[%s] no slots filled from answer to '%s'", state["session_id"], asked_key)

        asked_slot = updated_slots.get(asked_key, {})
        if is_slot_exhausted(asked_slot):
            log.warning("[%s] slot '%s' exhausted", state["session_id"], asked_key)
            if asked_key not in updated_flagged:
                updated_flagged.append(asked_key)

        for k, slot in updated_slots.items():
            if is_slot_exhausted(slot) and not slot.get("filled"):
                updated_slots[k]["filled"] = True

    nxt  = next_question(updated_slots)
    gate = "slot_filling" if nxt is not None else "slot_confirm"

    return {"slots": updated_slots, "flagged_sections": updated_flagged, "gate": gate}


def node_slot_confirm(state: ProposalState) -> dict:
    log.info("[%s] node: slot_confirm (interrupting)", state["session_id"])
    unfilled   = [k for k, v in state["slots"].items() if not v.get("filled")]
    user_input = interrupt({
        "gate":          "slot_confirm",
        "slots":         state["slots"],
        "flagged_slots": unfilled,
        "instructions":  (
            "Review the information collected below. "
            "Edit any field before confirming. "
            "Flagged fields were not answered — please fill them in now."
        ),
    })

    updated_slots = {k: dict(v) for k, v in state["slots"].items()}
    for key, value in user_input.get("slots", {}).items():
        if key in updated_slots:
            updated_slots[key]["value"]  = value
            updated_slots[key]["filled"] = bool(value and str(value).strip())

    return {"slots": updated_slots}


def node_draft_sections(state: ProposalState) -> dict:
    log.info("[%s] node: draft_sections", state["session_id"])

    profile   = slots_to_profile(state["slots"])
    grant     = state["grant"]
    grant_ctx = _build_grant_context(grant)
    vocab     = state["funder_vocab"]
    vocab_str = vocab_to_prompt_str(vocab)

    def draft_one(section: dict) -> tuple[str, SectionResult]:
        # Fresh LLM per section draft — thread-safe, valid key guaranteed
        llm   = _get_llm(temperature=0.3)
        chain = SECTION_PROMPT | llm

        user_values = _extract_user_values(profile)
        if section["key"] == "budget_narrative":
            from agents.budget_injector import get_budget_context
            budget_ctx = get_budget_context(profile, grant)
            if budget_ctx:
                user_values += f"\n\nPre-calculated budget table:\n{budget_ctx}"

        response = chain.invoke({
            "section_title": section["title"],
            "word_target":   section["word_target"],
            "instructions":  section["instructions"],
            "proposal":      str(profile),
            "grant":         str(grant_ctx),
            "user_values":   user_values + f"\n\nFunder vocabulary:\n{vocab_str}",
        })
        content     = response.content.strip()
        retry_count = 0
        last_score  = 0
        feedback    = ""

        while True:
            result     = score_section(section["key"], section["title"], content, grant, vocab)
            last_score = result["score"]
            feedback   = result["feedback"]
            if not needs_retry(last_score, retry_count):
                break
            log.info("[%s] section '%s' scored %d — retry %d/%d",
                     state["session_id"], section["key"], last_score, retry_count + 1, MAX_RETRIES)
            content     = retry_rewrite(section["title"], content, feedback, vocab)
            retry_count += 1

        flagged = is_flagged(last_score, retry_count)
        return section["key"], SectionResult(
            title=section["title"], content=content,
            score=last_score, retries=retry_count, flagged=flagged,
        )

    new_sections     = {}
    new_retry_counts = dict(state["retry_counts"])
    new_flagged      = list(state["flagged_sections"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(draft_one, s): s["key"] for s in SECTIONS}
        for future in concurrent.futures.as_completed(futures):
            section_key = futures[future]
            try:
                key, result = future.result()
                new_sections[key]     = result
                new_retry_counts[key] = result["retries"]
                if result["flagged"] and key not in new_flagged:
                    new_flagged.append(key)
            except Exception as e:
                log.error("[%s] draft failed for '%s': %s",
                          state["session_id"], section_key, e, exc_info=True)

    return {
        "profile":          profile,
        "sections":         new_sections,
        "retry_counts":     new_retry_counts,
        "flagged_sections": new_flagged,
        "gate":             "draft_review",
    }


def node_draft_review(state: ProposalState) -> dict:
    log.info("[%s] node: draft_review (interrupting)", state["session_id"])
    user_input = interrupt({
        "gate":             "draft_review",
        "sections":         state["sections"],
        "flagged_sections": state["flagged_sections"],
        "instructions": (
            "Your proposal draft is ready. "
            "Review each section and edit as needed. "
            "Flagged sections scored low — review these carefully."
        ),
    })
    updated_sections = dict(state["sections"])
    for key, text in user_input.get("sections", {}).items():
        if key in updated_sections:
            updated_sections[key]["content"] = text
    return {"sections": updated_sections}


def node_final_save(state: ProposalState) -> dict:
    log.info("[%s] node: final_save (interrupting)", state["session_id"])
    interrupt({
        "gate":         "final_save",
        "sections":     state["sections"],
        "instructions": "Your proposal is ready. Confirm to download.",
    })
    return {"gate": "complete"}


def node_complete(state: ProposalState) -> dict:
    log.info("[%s] node: complete", state["session_id"])
    return {"gate": "complete"}


def should_continue_slots(state: ProposalState) -> str:
    return "slot_confirm" if state["gate"] == "slot_confirm" else "slot_filling"


def build_scratch_graph(checkpointer):
    builder = StateGraph(ProposalState)
    builder.add_node("init_slots",     node_init_slots)
    builder.add_node("slot_filling",   node_slot_filling)
    builder.add_node("slot_confirm",   node_slot_confirm)
    builder.add_node("draft_sections", node_draft_sections)
    builder.add_node("draft_review",   node_draft_review)
    builder.add_node("final_save",     node_final_save)
    builder.add_node("complete",       node_complete)

    builder.set_entry_point("init_slots")
    builder.add_edge("init_slots",     "slot_filling")
    builder.add_edge("slot_confirm",   "draft_sections")
    builder.add_edge("draft_sections", "draft_review")
    builder.add_edge("draft_review",   "final_save")
    builder.add_edge("final_save",     "complete")
    builder.add_edge("complete",       END)
    builder.add_conditional_edges(
        "slot_filling",
        should_continue_slots,
        {"slot_filling": "slot_filling", "slot_confirm": "slot_confirm"},
    )
    return builder.compile(checkpointer=checkpointer)


def _slot_progress(slots: dict) -> dict:
    total  = len(slots)
    filled = sum(1 for v in slots.values() if v.get("filled"))
    return {
        "slots_filled": filled,
        "slots_total":  total,
        "progress":     round(filled / total * 100) if total else 0,
    }