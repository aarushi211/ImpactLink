"""
flows/scratch_flow.py — LangGraph state machine for building proposals from scratch.

Section drafting is delegated to flows/section_subgraph.py (SectionDraftAgent,
SectionScoringAgent, SectionRewriteAgent) and orchestrated in parallel by
node_draft_sections.
"""

import logging
import concurrent.futures
import os
from contextvars import copy_context

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.config import get_stream_writer
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
from services.application import section_definitions, spec_for, annotate_sections, constraint_prompt, section_for, merge_checklist, validate_slot_confirmation
from agents.coherence_agent import CoherenceAgent, CoherenceReport, review_metadata, current_review, _sections_digest
from agents.rewriter_agent import targeted_retry_rewrite
from flows.section_subgraph import run_section_subgraph
from utils.metrics import metrics_collector

load_dotenv()
log = logging.getLogger(__name__)

try:
    MAX_WORKERS = max(1, min(4, int(os.getenv("DRAFT_MAX_WORKERS", "4"))))
except ValueError:
    log.warning("Invalid DRAFT_MAX_WORKERS; using 4")
    MAX_WORKERS = 4


def _progress_writer():
    try:
        return get_stream_writer()
    except RuntimeError:
        # Offline evaluation also invokes these nodes outside a graph runtime.
        return lambda event: None


# ── Node functions ─────────────────────────────────────────────────────────────

def node_init_slots(state: ProposalState) -> dict:
    log.info("[%s] node: init_slots", state["session_id"])
    with metrics_collector.timer("node", "init_slots", session_id=state["session_id"]):
        vocab = extract_funder_vocab(state["grant"])
        slots = initial_slots(state.get("profile"), state.get("grant"))
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
    validate_slot_confirmation(state, user_input)
    for key, value in user_input.get("slots", {}).items():
        if key in updated_slots:
            updated_slots[key]["value"]  = value
            updated_slots[key]["filled"] = bool(value and str(value).strip())

    return {"slots": updated_slots, "draft_instructions": user_input.get("draft_instructions", "").strip()}


def node_plan_draft(state: ProposalState) -> dict:
    """PlanningAgent: analyze grant + profile and produce a structured drafting plan."""
    sid = state["session_id"]
    _progress_writer()({"type": "progress", "message": "Planning your proposal..."})
    log.info("[%s] node: plan_draft (PlanningAgent)", sid)

    with metrics_collector.timer("node", "plan_draft", session_id=sid):
        profile = slots_to_profile(state["slots"])
        if state.get("draft_instructions"):
            profile["draft_instructions"] = state["draft_instructions"]
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
    writer = _progress_writer()
    writer({"type": "progress", "message": "Drafting and reviewing proposal sections..."})

    with metrics_collector.timer("node", "draft_sections", session_id=sid) as node_meta:
        profile = state.get("profile") or slots_to_profile(state["slots"])
        grant = state["grant"]
        vocab = state["funder_vocab"]
        drafting_plan = state.get("drafting_plan")

        sections_by_key = {s["key"]: s for s in section_definitions(grant)}
        spec = spec_for(grant)
        waves = [list(sections_by_key)] if spec and (spec.sections or spec.stage != "full_proposal") else DRAFTING_WAVES
        new_sections: dict = {}
        new_retry_counts = dict(state["retry_counts"])
        new_flagged = list(state["flagged_sections"])
        trace = list(state.get("agent_trace") or [])

        for wave_idx, wave_keys in enumerate(waves, start=1):
            wave_sections = [sections_by_key[k] for k in wave_keys if k in sections_by_key]
            prior_context = summarize_prior_sections(new_sections)

            log.info(
                "[%s] draft wave %d/%d: %s",
                sid, wave_idx, len(waves), wave_keys,
            )
            trace = append_agent_trace(
                trace,
                "draft_sections",
                f"wave {wave_idx}: {', '.join(wave_keys)}",
            )

            def run_one(section: dict, ctx: str = prior_context):
                key = section["key"]
                writer({"type": "section_start", "section_key": key, "title": section["title"]})
                return run_section_subgraph(
                    section,
                    session_id=sid,
                    profile=profile,
                    grant=grant,
                    funder_vocab=vocab,
                    drafting_plan=drafting_plan,
                    prior_sections_context=ctx,
                    on_token=lambda text: writer({"type": "token", "section_key": key, "content": text}),
                    on_status=lambda phase: writer({"type": "section_status", "section_key": key, "phase": phase}),
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(copy_context().run, run_one, s): s["key"] for s in wave_sections
                }
                for future in concurrent.futures.as_completed(futures):
                    section_key = futures[future]
                    try:
                        key, result = future.result()
                        new_sections[key] = result
                        writer({"type": "section_complete", "section_key": key, "section": result})
                        writer({"type": "progress", "message": f"Drafted {len(new_sections)} of {len(sections_by_key)} sections."})
                        new_retry_counts[key] = result["retries"]
                        if result["flagged"] and key not in new_flagged:
                            new_flagged.append(key)
                    except Exception as e:
                        log.error(
                            "[%s] SectionSubgraph failed for '%s': %s",
                            sid, section_key, e, exc_info=True,
                        )

        node_meta["sections_drafted"] = len(new_sections)
        node_meta["drafting_waves"] = len(waves)
        node_meta["max_workers"] = MAX_WORKERS

    return {
        "profile":          profile,
        "sections":         annotate_sections(new_sections, grant, order=True),
        "retry_counts":     new_retry_counts,
        "flagged_sections": new_flagged,
        "agent_trace":      trace,
    }


def node_coherence_check(state: ProposalState) -> dict:
    """CoherenceAgent: cross-section validation and targeted fixes (max 2)."""
    sid = state["session_id"]
    _progress_writer()({"type": "progress", "message": "Checking consistency across your proposal..."})
    log.info("[%s] node: coherence_check (CoherenceAgent)", sid)

    sections = dict(state.get("sections") or {})
    trace = list(state.get("agent_trace") or [])

    with metrics_collector.timer("node", "coherence_check", session_id=sid):
        report = CoherenceAgent.check(sections, state["grant"])

        if report.coherent or report.status != "completed":
            review = review_metadata(report, sections)
            trace = append_agent_trace(trace, "CoherenceAgent", review["status"])
            return {"coherence_review": review, "agent_trace": trace, "gate": "draft_review"}

        trace = append_agent_trace(
            trace,
            "CoherenceAgent",
            f"found {len(report.issues)} issue(s) — fixing up to 2",
        )

        fixes = CoherenceAgent.top_fixes(report)
        updated = dict(sections)
        vocab = state.get("funder_vocab", [])
        attempts = 0
        failed = False

        for issue in fixes:
            key = issue.section
            if key not in updated:
                continue
            sec = updated[key]
            attempts += 1
            try:
                new_content = targeted_retry_rewrite(
                    sec.get("title", key), sec.get("content", ""), [issue.model_dump()],
                    f"Coherence issue: {issue.issue}\nDo not invent facts to resolve contradictions. Preserve unresolved facts for human review.\n"
                    + constraint_prompt(section_for(state["grant"], key)) + "\nFull proposal context:\n" + _sections_digest(updated), vocab,
                )
                if not isinstance(new_content, str) or not new_content.strip():
                    raise ValueError("Empty consistency rewrite")
                updated[key] = {**sec, "content": new_content, "flagged": True, "coherence_modified": True}
                trace = append_agent_trace(trace, "CoherenceAgent", f"attempted consistency edit to {key}; requires review")
            except Exception as exc:
                failed = True
                log.warning("[%s] consistency edit failed (%s)", sid, type(exc).__name__)

        _progress_writer()({"type": "progress", "message": "Rechecking the full proposal after consistency edits..."})
        final_report = CoherenceAgent.check(updated, state["grant"])
        if failed:
            final_report = CoherenceReport(coherent=False, status="incomplete", issues=final_report.issues, reason="A consistency edit failed. The original text for that edit was retained; review the proposal manually.")
        review = review_metadata(final_report, updated, fixes_attempted=attempts)
        trace = append_agent_trace(trace, "CoherenceAgent", f"final review: {review['status']}")

    return {
        "sections": annotate_sections(updated, state["grant"], order=True),
        "coherence_review": review,
        "agent_trace": trace,
        "gate": "draft_review",
    }


def node_draft_review(state: ProposalState) -> dict:
    log.info("[%s] node: draft_review (interrupting)", state["session_id"])
    user_input = interrupt({
        "gate":             "draft_review",
        "sections":         state["sections"],
        "coherence_review": state.get("coherence_review"),
        "application_spec": state["grant"].get("application_spec"),
        "flagged_sections": state["flagged_sections"],
        "drafting_plan":    state.get("drafting_plan"),
        "agent_trace":      state.get("agent_trace", []),
        "instructions": (
            "Your proposal draft is ready. "
            "Review each section and edit as needed. "
            "Flagged sections scored low — review these carefully."
        ),
    })
    updated_sections = {key: dict(value) for key, value in state["sections"].items()}
    for key, text in user_input.get("sections", {}).items():
        if key in updated_sections:
            updated_sections[key]["content"] = text
    return {"sections": annotate_sections(updated_sections, state["grant"], order=True), "grant": merge_checklist(state["grant"], user_input), "coherence_review": current_review(state.get("coherence_review"), updated_sections)}


def node_final_save(state: ProposalState) -> dict:
    log.info("[%s] node: final_save (interrupting)", state["session_id"])
    user_input = interrupt({
        "gate":         "final_save",
        "application_spec": state["grant"].get("application_spec"),
        "sections":     state["sections"],
        "coherence_review": state.get("coherence_review"),
        "instructions": "Your proposal is ready. Confirm to download.",
    })
    return {"gate": "complete", "grant": merge_checklist(state["grant"], user_input)}


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
    builder.add_node("draft_sections",   node_draft_sections)
    builder.add_node("coherence_check", node_coherence_check)
    builder.add_node("draft_review",    node_draft_review)
    builder.add_node("final_save",     node_final_save)
    builder.add_node("complete",       node_complete)

    builder.set_entry_point("init_slots")
    builder.add_edge("init_slots",     "slot_filling")
    builder.add_edge("slot_confirm",   "plan_draft")
    builder.add_edge("plan_draft",     "draft_sections")
    builder.add_edge("draft_sections",   "coherence_check")
    builder.add_edge("coherence_check", "draft_review")
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
