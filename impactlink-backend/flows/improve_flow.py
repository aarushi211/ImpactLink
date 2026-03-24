# flows/improve_flow_lg.py

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from state.proposal_state import ProposalState
from agents.vocab_extractor import extract_funder_vocab
from agents.gap_analysis_agent import analyze_gaps, apply_user_adjustments
from agents.rewriter_agent import rewrite_section, retry_rewrite
from agents.scoring_agent import score_section, needs_retry, is_flagged, MAX_RETRIES
from utils.diff import diff_sections
import concurrent.futures
import logging

log = logging.getLogger(__name__)
MAX_WORKERS = 2


# ── Node functions ─────────────────────────────────────────────────────────
# Each node receives the full state, does one job, returns updated fields.
# LangGraph merges the returned dict back into state automatically.

def node_extract_vocab(state: ProposalState) -> dict:
    """Node 1: extract funder vocabulary."""
    log.info("[%s] node: extract_vocab", state["session_id"])
    vocab = extract_funder_vocab(state["grant"])
    return {"funder_vocab": vocab}


def node_analyze_gaps(state: ProposalState) -> dict:
    """Node 2: run gap analysis against existing sections."""
    log.info("[%s] node: analyze_gaps", state["session_id"])
    analysis = analyze_gaps(
        existing_sections=state["original_sections"],
        grant=state["grant"],
        funder_vocab=state["funder_vocab"],
    )
    return {"analysis": analysis}


def node_gap_review(state: ProposalState) -> dict:
    """
    Node 3: HUMAN GATE — pause and wait for user to review gaps.

    interrupt() saves the full graph state to the checkpointer
    and raises an exception that suspends execution.
    When the user submits their response, the graph resumes
    HERE with the user's input available via interrupt().
    """
    log.info("[%s] node: gap_review (interrupting)", state["session_id"])

    # interrupt() pauses the graph and returns whatever the user sends back
    user_input = interrupt({
        "gate":         "gap_review",
        "analysis":     state["analysis"],
        "funder_vocab": state["funder_vocab"],
        "instructions": (
            "Review the gaps identified below. Uncheck any you disagree with. "
            "Add any additional context in the notes field. "
            "Confirm which sections should be rewritten."
        ),
    })

    # Execution resumes here after the user submits
    confirmed_gaps      = user_input.get("confirmed_gaps", [])
    user_additions      = user_input.get("user_additions", "")
    sections_to_rewrite = user_input.get("sections_to_rewrite",
                                         state["analysis"].get("sections_to_rewrite", []))

    updated_analysis = apply_user_adjustments(
        state["analysis"], confirmed_gaps, user_additions, sections_to_rewrite
    )
    return {"analysis": updated_analysis}


def node_rewrite_sections(state: ProposalState) -> dict:
    """Node 4: rewrite flagged sections in parallel with score/retry."""
    log.info("[%s] node: rewrite_sections", state["session_id"])

    sections_to_rewrite = state["analysis"].get("sections_to_rewrite", [])
    original_text       = state["original_sections"]
    grant               = state["grant"]
    profile             = state["profile"]
    funder_vocab        = state["funder_vocab"]
    analysis            = state["analysis"]

    # Preserve unrewritten sections
    new_sections = {}
    for key, text in original_text.items():
        new_sections[key] = {
            "title": key.replace("_", " ").title(),
            "content": text, "score": 0, "retries": 0, "flagged": False,
        }

    new_retry_counts  = dict(state["retry_counts"])
    new_flagged       = list(state["flagged_sections"])

    def rewrite_one(section_key):
        from agents.rewriter_agent import gaps_for_section as gfs
        title         = section_key.replace("_", " ").title()
        original      = original_text.get(section_key, "")
        relevant_gaps = gfs(analysis, section_key)

        content     = rewrite_section(section_key, title, original,
                                      relevant_gaps, funder_vocab, grant, profile)
        retry_count = new_retry_counts.get(section_key, 0)
        last_score  = 0
        feedback    = ""

        while True:
            result     = score_section(section_key, title, content, grant, funder_vocab)
            last_score = result["score"]
            feedback   = result["feedback"]
            if not needs_retry(last_score, retry_count):
                break
            content     = retry_rewrite(title, content, feedback, funder_vocab)
            retry_count += 1

        flagged = is_flagged(last_score, retry_count)
        return section_key, {
            "title": title, "content": content,
            "score": last_score, "retries": retry_count, "flagged": flagged,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(rewrite_one, k): k for k in sections_to_rewrite}
        for future in concurrent.futures.as_completed(futures):
            key, result = future.result()
            new_sections[key]       = result
            new_retry_counts[key]   = result["retries"]
            if result["flagged"] and key not in new_flagged:
                new_flagged.append(key)

    revised_text = {k: v["content"] for k, v in new_sections.items()
                    if k in sections_to_rewrite}
    diffs = diff_sections(original_text, revised_text)

    return {
        "sections":         new_sections,
        "retry_counts":     new_retry_counts,
        "flagged_sections": new_flagged,
        "diffs":            diffs,
    }


def node_draft_review(state: ProposalState) -> dict:
    """
    Node 5: HUMAN GATE — user reviews diffs and edits sections.
    Same interrupt() pattern as gap_review.
    """
    log.info("[%s] node: draft_review (interrupting)", state["session_id"])

    user_input = interrupt({
        "gate":             "draft_review",
        "sections":         state["sections"],
        "diffs":            state["diffs"],
        "flagged_sections": state["flagged_sections"],
        "instructions":     (
            "Review the rewritten sections below. "
            "Flagged sections scored low after 2 retries — review carefully. "
            "Edit any section text directly before confirming."
        ),
    })

    # Apply user's inline edits
    updated_sections = dict(state["sections"])
    for key, edited_text in user_input.get("sections", {}).items():
        if key in updated_sections:
            updated_sections[key]["content"] = edited_text

    return {"sections": updated_sections}


def node_final_save(state: ProposalState) -> dict:
    """
    Node 6: HUMAN GATE — user confirms and downloads.
    """
    log.info("[%s] node: final_save (interrupting)", state["session_id"])

    interrupt({
        "gate":         "final_save",
        "sections":     state["sections"],
        "instructions": "Your proposal is ready. Confirm to download.",
    })

    # Nothing to update — user just confirmed
    return {}


# ── Graph assembly ─────────────────────────────────────────────────────────

def build_improve_graph(checkpointer):
    """
    Assemble the Flow A graph.
    Call this once at startup and reuse the compiled graph.
    """
    builder = StateGraph(ProposalState)

    # Add nodes — each is a function defined above
    builder.add_node("extract_vocab",      node_extract_vocab)
    builder.add_node("analyze_gaps",       node_analyze_gaps)
    builder.add_node("gap_review",         node_gap_review)
    builder.add_node("rewrite_sections",   node_rewrite_sections)
    builder.add_node("draft_review",       node_draft_review)
    builder.add_node("final_save",         node_final_save)

    # Add edges — the order of execution
    builder.set_entry_point("extract_vocab")
    builder.add_edge("extract_vocab",    "analyze_gaps")
    builder.add_edge("analyze_gaps",     "gap_review")
    builder.add_edge("gap_review",       "rewrite_sections")
    builder.add_edge("rewrite_sections", "draft_review")
    builder.add_edge("draft_review",     "final_save")
    builder.add_edge("final_save",       END)

    return builder.compile(
        checkpointer=checkpointer,
    )