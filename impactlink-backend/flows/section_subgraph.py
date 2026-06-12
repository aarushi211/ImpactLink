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
import os
import random
import time
from typing import Optional

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
from utils.llm import RotatingGroq
from utils.metrics import metrics_collector

log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm(temperature: float = 0.3) -> RotatingGroq:
    from config import GROQ_API_KEY

    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        groq_api_key=key,
    )


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
    ) -> str:
        llm = _get_llm(temperature=0.3)
        chain = SECTION_PROMPT | llm

        instructions = section["instructions"]
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

        response = chain.invoke({
            "section_title": section["title"],
            "word_target": section["word_target"],
            "instructions": instructions,
            "proposal": str(profile),
            "grant": str(grant_ctx),
            "user_values": user_values + f"\n\nFunder vocabulary:\n{vocab_str}",
        })
        return response.content.strip()


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
    )

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

        rewrite_feedback = format_targeted_feedback(decision)
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

    flagged = is_flagged(last_score, retry_count)
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
    )
