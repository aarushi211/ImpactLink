"""
flows/section_subgraph.py

Per-section drafting pipeline for the scratch flow.

Each section runs through three named agents in sequence:
  SectionDraftAgent   → initial generation
  SectionScoringAgent → LLM-as-a-Judge rubric scoring
  SectionRewriteAgent → targeted revision when score < threshold

run_section_subgraph() orchestrates the draft → score → rewrite loop for one section.
node_draft_sections in scratch_flow.py calls this in parallel via ThreadPoolExecutor.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from agents.prompts import (
    SECTION_PROMPT,
    _build_grant_context,
    _extract_user_values,
)
from agents.rewriter_agent import targeted_retry_rewrite, retry_rewrite
from agents.scoring_agent import (
    MAX_RETRIES,
    format_targeted_feedback,
    is_flagged,
    route_after_scoring,
    score_section_decision,
)
from agents.planning_agent import DraftingPlan
from agents.tools.budget_consistency import (
    check_budget_consistency,
    format_consistency_issues,
)
from agents.tools.grant_requirements import (
    format_grant_requirements,
    get_grant_requirement,
)
from agents.vocab_extractor import vocab_to_prompt_str
from state.proposal_state import SectionResult
from utils.llm import get_chat_model
from utils.metrics import metrics_collector
from services.application import constraint_prompt, length_check

log = logging.getLogger(__name__)

def _get_llm(*, streaming=False):
    return get_chat_model(streaming=streaming)


class SectionDraftAgent:
    """Generates the initial draft for a single proposal section."""

    @staticmethod
    def draft(
        section: dict,
        profile: dict,
        grant: dict,
        grant_ctx: dict,
        vocab_str: str,
        drafting_plan: Optional[dict] = None,
        prior_sections_context: str = "",
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        llm = _get_llm(streaming=on_token is not None)
        chain = SECTION_PROMPT | llm

        instructions = section["instructions"] + "\n\n" + constraint_prompt(section)
        if drafting_plan:
            plan = DraftingPlan.model_validate(drafting_plan)
            plan_ctx = plan.to_section_context(section["key"])
            if plan_ctx:
                instructions += f"\n\n━━━ DRAFTING PLAN FOR THIS SECTION ━━━\n{plan_ctx}"

        if prior_sections_context:
            instructions += (
                "\n\n━━━ PRIOR SECTIONS (maintain consistency) ━━━\n"
                + prior_sections_context
            )

        grant_req = get_grant_requirement(section["key"], grant)
        req_text = format_grant_requirements(grant_req)
        if req_text:
            instructions += f"\n\n━━━ GRANT REQUIREMENTS (get_grant_requirement tool) ━━━\n{req_text}"
            log.info("[SectionDraftAgent] get_grant_requirement → '%s'", section["key"])

        user_values = _extract_user_values(profile)
        if section["key"] == "budget_narrative":
            from agents.budget_injector import get_budget_context

            budget_ctx = get_budget_context(profile, grant)
            if budget_ctx:
                user_values += f"\n\nPre-calculated budget table:\n{budget_ctx}"

        payload = {
            "section_title": section["title"],
            "word_target": section["word_target"],
            "instructions": instructions,
            "proposal": str(profile),
            "grant": str(grant_ctx),
            "user_values": user_values + f"\n\nFunder vocabulary:\n{vocab_str}",
        }
        if on_token is None:
            return chain.invoke(payload).content.strip()
        parts = []
        with metrics_collector.timer("llm_call", "openai_draft_stream"):
            for chunk in chain.stream(payload):
                content = chunk.content
                if isinstance(content, list):
                    content = "".join(
                        block.get("text", "") for block in content
                        if isinstance(block, dict) and block.get("type") in ("text", "output_text")
                    )
                if isinstance(content, str) and content:
                    parts.append(content)
                    on_token(content)
        return "".join(parts).strip()


class SectionScoringAgent:
    """Scores a section draft and returns a structured routing decision."""

    @staticmethod
    def evaluate(
        section_key: str,
        section_title: str,
        content: str,
        grant: dict,
        funder_vocab: list[str],
    ) -> dict:
        return score_section_decision(
            section_key, section_title, content, grant, funder_vocab
        )


class SectionRewriteAgent:
    """Revises a section using scorer feedback (reflection loop)."""

    @staticmethod
    def rewrite(
        section_title: str,
        content: str,
        feedback: str,
        funder_vocab: list[str],
        targeted_feedback: list[dict] | None = None,
    ) -> str:
        if targeted_feedback:
            return targeted_retry_rewrite(
                section_title,
                content,
                targeted_feedback,
                feedback,
                funder_vocab,
            )
        return retry_rewrite(section_title, content, feedback, funder_vocab)


class SectionToolAgent:
    """Invokes deterministic tools when scoring routes to needs_tool_call."""

    @staticmethod
    def check_budget(section_content: str, profile: dict, grant: dict) -> str:
        result = check_budget_consistency(section_content, profile, grant)
        return format_consistency_issues(result)


def run_section_subgraph(
    section: dict,
    *,
    session_id: str,
    profile: dict,
    grant: dict,
    funder_vocab: list[str],
    drafting_plan: Optional[dict] = None,
    prior_sections_context: str = "",
    on_token: Optional[Callable[[str], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> tuple[str, SectionResult]:
    """
    Run the full per-section pipeline: draft → score → (rewrite → score)*.

    Returns (section_key, SectionResult).
    """
    section_key = section["key"]
    section_title = section["title"]
    grant_ctx = _build_grant_context(grant)
    vocab_str = vocab_to_prompt_str(funder_vocab)

    section_start = time.perf_counter()

    log.info(
        "[%s] [SectionDraftAgent] drafting '%s'",
        session_id,
        section_key,
    )
    content = SectionDraftAgent.draft(
        section,
        profile,
        grant,
        grant_ctx,
        vocab_str,
        drafting_plan,
        prior_sections_context,
        on_token=on_token,
    )

    if on_status:
        on_status("reviewing")

    retry_count = 0
    last_score = 0
    last_decision: dict = {}

    while True:
        log.info(
            "[%s] [SectionScoringAgent] scoring '%s'",
            session_id,
            section_key,
        )
        decision = SectionScoringAgent.evaluate(
            section_key, section_title, content, grant, funder_vocab
        )
        last_decision = decision
        last_score = decision["score"]
        route = route_after_scoring(decision, retry_count)
        limits = length_check(content, section)
        if not limits["within_limits"] and retry_count < MAX_RETRIES:
            route = "rewrite"

        log.info(
            "[%s] [SectionScoringAgent] '%s' score=%d → route=%s",
            session_id,
            section_key,
            last_score,
            route,
        )

        if route == "approve":
            break
        if route == "escalate":
            break

        rewrite_feedback = format_targeted_feedback(decision) + "\n\n" + constraint_prompt(section)
        if not limits["within_limits"]:
            rewrite_feedback += "\nShorten the answer while preserving the key facts: " + "; ".join(limits["violations"])
        targeted = decision.get("targeted_feedback") or []
        tool_name = decision.get("tool_to_call")

        if route == "needs_tool_call" or tool_name:
            tool = tool_name or "check_budget_consistency"
            if tool == "check_budget_consistency":
                tool_notes = SectionToolAgent.check_budget(content, profile, grant)
                if tool_notes:
                    rewrite_feedback = f"{rewrite_feedback}\n\n{tool_notes}"
                    log.info(
                        "[%s] [SectionToolAgent] check_budget_consistency → '%s'",
                        session_id,
                        section_key,
                    )
            elif tool == "get_grant_requirement":
                grant_req = get_grant_requirement(section_key, grant)
                rewrite_feedback += (
                    "\n\n[get_grant_requirement tool]\n"
                    + format_grant_requirements(grant_req)
                )

        if on_status:
            on_status("revising")
        content = SectionRewriteAgent.rewrite(
            section_title,
            content,
            rewrite_feedback,
            funder_vocab,
            targeted_feedback=targeted if targeted else None,
        )
        retry_count += 1

    section_duration = time.perf_counter() - section_start
    metrics_collector.record(
        category="node",
        name=f"section_subgraph/{section_key}",
        duration_s=section_duration,
        session_id=session_id,
        metadata={"score": last_score, "retries": retry_count},
    )

    flagged = is_flagged(last_score, retry_count) or not length_check(content, section)["within_limits"]
    if flagged:
        log.warning(
            "[%s] [SectionScoringAgent] '%s' score=%d → escalate (flagged after %d retries)",
            session_id,
            section_key,
            last_score,
            retry_count,
        )

    return section_key, SectionResult(
        title=section_title,
        content=content,
        score=last_score,
        retries=retry_count,
        flagged=flagged,
        limits=length_check(content, section),
    )
