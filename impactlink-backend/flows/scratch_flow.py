"""
flows/scratch_flow.py — LangGraph state machine for building proposals from scratch.

Section drafting is delegated to flows/section_subgraph.py (SectionDraftAgent,
SectionScoringAgent, SectionRewriteAgent) and orchestrated in parallel by
node_draft_sections.
"""

import logging
import concurrent.futures

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from dotenv import load_dotenv

from state.proposal_state import ProposalState
from agents.vocab_extractor import extract_funder_vocab
from agents.slot_extractor import (
    initial_slots, next_question, extract_slots,
    apply_extractions, is_slot_exhausted, slots_to_profile,
)
from agents.planning_agent import (
    DRAFTING_WAVES,
    PlanningAgent,
    append_agent_trace,
    summarize_prior_sections,
)
from agents.prompts import SECTIONS
from flows.section_subgraph import run_section_subgraph
from utils.metrics import metrics_collector

load_dotenv()
log = logging.getLogger(__name__)

MAX_WORKERS = 2


# ── Node functions ─────────────────────────────────────────────────────────────

def node_init_slots(state: ProposalState) -> dict:
    log.info("[%s] node: init_slots", state["session_id"])
    with metrics_collector.timer("node", "init_slots", session_id=state["session_id"]):
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
        with metrics_collector.timer("node", "slot_filling_extraction", session_id=state["session_id"],
                                     metadata={"slot_key": asked_key}):
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


def node_plan_draft(state: ProposalState) -> dict:
    """PlanningAgent: analyze grant + profile and produce a structured drafting plan."""
    sid = state["session_id"]
    log.info("[%s] node: plan_draft (PlanningAgent)", sid)

    with metrics_collector.timer("node", "plan_draft", session_id=sid):
        profile = slots_to_profile(state["slots"])
        plan = PlanningAgent.create_plan(
            grant=state["grant"],
            profile=profile,
            funder_vocab=state["funder_vocab"],
        )
        plan_dict = plan.model_dump()

        trace = list(state.get("agent_trace") or [])
        for sp in sorted(plan.section_priorities, key=lambda x: x.priority)[:3]:
            trace = append_agent_trace(
                trace,
                "PlanningAgent",
                (
                    f"{sp.key} priority={sp.priority}, "
                    f"evidence={sp.evidence_needed[:2]}"
                ),
                metadata={"critical_because": sp.critical_because},
            )
        for flag in plan.red_flags[:3]:
            trace = append_agent_trace(trace, "PlanningAgent", f"red_flag: {flag}")

        log.info("[%s] [PlanningAgent] plan ready — %d priorities, %d red flags",
                 sid, len(plan.section_priorities), len(plan.red_flags))

    return {
        "profile": profile,
        "drafting_plan": plan_dict,
        "agent_trace": trace,
    }


def node_draft_sections(state: ProposalState) -> dict:
    """Orchestrate phased parallel SectionSubgraph runs (3 dependency waves)."""
    log.info("[%s] node: draft_sections (phased SectionSubgraph)", state["session_id"])
    sid = state["session_id"]

    with metrics_collector.timer("node", "draft_sections", session_id=sid) as node_meta:
        profile = state.get("profile") or slots_to_profile(state["slots"])
        grant = state["grant"]
        vocab = state["funder_vocab"]
        drafting_plan = state.get("drafting_plan")

        sections_by_key = {s["key"]: s for s in SECTIONS}
        new_sections: dict = {}
        new_retry_counts = dict(state["retry_counts"])
        new_flagged = list(state["flagged_sections"])
        trace = list(state.get("agent_trace") or [])

        for wave_idx, wave_keys in enumerate(DRAFTING_WAVES, start=1):
            wave_sections = [sections_by_key[k] for k in wave_keys if k in sections_by_key]
            prior_context = summarize_prior_sections(new_sections)

            log.info(
                "[%s] draft wave %d/%d: %s",
                sid, wave_idx, len(DRAFTING_WAVES), wave_keys,
            )
            trace = append_agent_trace(
                trace,
                "draft_sections",
                f"wave {wave_idx}: {', '.join(wave_keys)}",
            )

            def run_one(section: dict, ctx: str = prior_context):
                return run_section_subgraph(
                    section,
                    session_id=sid,
                    profile=profile,
                    grant=grant,
                    funder_vocab=vocab,
                    drafting_plan=drafting_plan,
                    prior_sections_context=ctx,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(run_one, s): s["key"] for s in wave_sections
                }
                for future in concurrent.futures.as_completed(futures):
                    section_key = futures[future]
                    try:
                        key, result = future.result()
                        new_sections[key] = result
                        new_retry_counts[key] = result["retries"]
                        if result["flagged"] and key not in new_flagged:
                            new_flagged.append(key)
                    except Exception as e:
                        log.error(
                            "[%s] SectionSubgraph failed for '%s': %s",
                            sid, section_key, e, exc_info=True,
                        )

        node_meta["sections_drafted"] = len(new_sections)
        node_meta["drafting_waves"] = len(DRAFTING_WAVES)

    return {
        "profile":          profile,
        "sections":         new_sections,
        "retry_counts":     new_retry_counts,
        "flagged_sections": new_flagged,
        "agent_trace":      trace,
        "gate":             "draft_review",
    }


def node_draft_review(state: ProposalState) -> dict:
    log.info("[%s] node: draft_review (interrupting)", state["session_id"])
    user_input = interrupt({
        "gate":             "draft_review",
        "sections":         state["sections"],
        "flagged_sections": state["flagged_sections"],
        "drafting_plan":    state.get("drafting_plan"),
        "agent_trace":      state.get("agent_trace", []),
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
    builder.add_node("plan_draft",     node_plan_draft)
    builder.add_node("draft_sections", node_draft_sections)
    builder.add_node("draft_review",   node_draft_review)
    builder.add_node("final_save",     node_final_save)
    builder.add_node("complete",       node_complete)

    builder.set_entry_point("init_slots")
    builder.add_edge("init_slots",     "slot_filling")
    builder.add_edge("slot_confirm",   "plan_draft")
    builder.add_edge("plan_draft",     "draft_sections")
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