"""
services/budget_chatbot.py — Python-Controlled Budget Refinement Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Four-stage pipeline — NO LLM edits numbers:

Stage 1  Intent Extraction  (LLM)
  ┗ Parse user_request → BudgetEditCommand
    {action: increase|decrease|set|move|add|remove,
     target_category, amount_delta|target_amount,
     offset_from_category|"auto"}

Stage 2  Python Edit Application
  ┗ Apply the change deterministically, rebalance total

Stage 3  Python Validation & Auto-Correction
  ┗ Min-wage floor, indirect cap, budget integrity — same rules as generator
    Collect human-readable list of corrections made

Stage 4  Explanation Generation  (LLM)
  ┗ Given (original, requested change, corrections, result) → plain-English reply
    e.g. "I increased Equipment, but limited the Field Staff cut to keep wages ≥ $27/hr"
"""

from __future__ import annotations

import copy
import json
from typing import List, Literal, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from services.budget.models import BudgetLineItem, CategoryType
from services.budget.constants import PERSONNEL_CATEGORIES
from services.budget.utils import get_minimum_wage

HOURS_PER_FTE_YEAR = 2080
DEFAULT_INDIRECT_CAP_PCT = 15.0  # fallback when not embedded in budget


# ── Stage 1: Structured edit command ──────────────────────────────────────────

class BudgetEditCommand(BaseModel):
    action: Literal["increase", "decrease", "set", "move", "add_category", "remove_category"] = Field(
        description="What the user wants to do"
    )
    target_category: str = Field(
        description="The CategoryType value being modified (e.g. 'Equipment & Supplies')"
    )
    amount_delta: Optional[int] = Field(
        default=None,
        description="Dollar change for increase/decrease (always positive — sign set by action)"
    )
    target_amount: Optional[int] = Field(
        default=None,
        description="Absolute target dollar amount for 'set'"
    )
    offset_from: Optional[str] = Field(
        default=None,
        description=(
            "CategoryType value to take money from (for increase/move). "
            "Use null/'auto' to let Python distribute evenly from other categories."
        )
    )
    clarification_needed: Optional[str] = Field(
        default=None,
        description="Non-null if the request is ambiguous and needs clarification"
    )


INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a budget parsing assistant.
Parse the user's budget edit request into a structured command.

CATEGORY NAMES (use these exact values):
{category_list}

RULES:
- amount_delta must always be positive (the action field carries the sign).
- If the user says "move $X from A to B", use action=move, target_category=B, offset_from=A.
- If the user says "cut X in half", compute amount_delta as current_X_amount / 2.
- If you cannot determine what the user wants, set clarification_needed.
"""),
    ("user", """\
Current budget line items:
{budget_summary}

User request: "{user_request}"
""")
])


# ── Stage 2: Python edit engine ────────────────────────────────────────────────

def _items_from_budget(budget: dict) -> List[BudgetLineItem]:
    """Reconstruct BudgetLineItem list from the serialized budget dict."""
    items = []
    for raw in budget.get("items", []):
        try:
            items.append(BudgetLineItem(**raw))
        except Exception:
            pass
    return items


def _find_item(items: List[BudgetLineItem], category_value: str) -> Optional[BudgetLineItem]:
    for item in items:
        if item.category.value.lower() == category_value.lower():
            return item
    return None


def _auto_offset_items(
    items: List[BudgetLineItem],
    exclude_category: str,
    delta: int,
) -> List[Tuple[BudgetLineItem, int]]:
    """
    Distribute `delta` dollars across categories that are NOT the target or personnel.
    Returns list of (item, amount_trimmed_from_it).
    If not enough headroom, take from all non-target items proportionally.
    """
    candidates = [
        i for i in items
        if i.category.value.lower() != exclude_category.lower()
    ]
    if not candidates:
        return []
    total_others = sum(c.amount for c in candidates)
    if total_others <= 0:
        return []
    result = []
    for c in candidates:
        share = int(delta * (c.amount / total_others))
        result.append((c, share))
    return result


def _apply_edit(
    items: List[BudgetLineItem],
    cmd: BudgetEditCommand,
    total_budget: int,
) -> Tuple[List[BudgetLineItem], List[str]]:
    """
    Apply the edit command to the line items (in-place).
    Returns (modified items, list of change descriptions).
    """
    changes: List[str] = []

    target = _find_item(items, cmd.target_category)

    if cmd.action == "add_category":
        if target:
            changes.append(f"Category '{cmd.target_category}' already exists.")
            return items, changes
        amount = cmd.target_amount or cmd.amount_delta or 0
        new_item = BudgetLineItem(
            category=CategoryType(cmd.target_category),
            description=f"Added via chatbot",
            amount=amount,
        )
        items.append(new_item)
        # Take the money from auto-offset
        offsets = _auto_offset_items(items, cmd.target_category, amount)
        for item, trim in offsets:
            item.amount = max(0, item.amount - trim)
            changes.append(f"Reduced '{item.category.value}' by ${trim:,} to fund new category")
        changes.append(f"Added '{cmd.target_category}': ${amount:,}")
        return items, changes

    if cmd.action == "remove_category":
        if not target:
            changes.append(f"Category '{cmd.target_category}' not found.")
            return items, changes
        freed = target.amount
        items.remove(target)
        # Redistribute freed amount to largest non-personnel item
        non_personnel = [i for i in items if i.category not in PERSONNEL_CATEGORIES]
        if non_personnel:
            largest = max(non_personnel, key=lambda i: i.amount)
            largest.amount += freed
            changes.append(f"Removed '{cmd.target_category}' (${freed:,}) → redistributed to '{largest.category.value}'")
        changes.append(f"Removed '{cmd.target_category}'")
        return items, changes

    if not target:
        changes.append(f"Could not find category '{cmd.target_category}' in budget.")
        return items, changes

    original_amount = target.amount

    if cmd.action == "set":
        desired = cmd.target_amount or 0
        delta = desired - target.amount
    elif cmd.action in ("increase", "move"):
        delta = cmd.amount_delta or 0
    elif cmd.action == "decrease":
        # Calculate the legal floor first
        if target.category in PERSONNEL_CATEGORIES:
            min_floor = min_wage_hourly * HOURS_PER_FTE_YEAR * (target.fte_count or 1.0)
            # Prevent the delta from going below this floor
            max_possible_cut = target.amount - int(min_floor)
            requested_cut = cmd.amount_delta or 0
            
            if requested_cut > max_possible_cut:
                actual_delta = -max_possible_cut
                changes.append(f"⚠️ Limited the cut to {target.category.value} to ${max_possible_cut:,} to maintain the $27/hr wage floor.")
            else:
                actual_delta = -requested_cut
        else:
            actual_delta = -(cmd.amount_delta or 0)
    else:
        delta = 0

    # Apply the delta to the target
    target.amount = max(0, target.amount + delta)
    actual_delta = target.amount - original_amount
    if actual_delta >= 0:
        changes.append(f"Increased '{cmd.target_category}' by ${actual_delta:,}")
    else:
        changes.append(f"Decreased '{cmd.target_category}' by ${abs(actual_delta):,}")

    # Rebalance: take money from or give money to offset category
    if actual_delta != 0:
        if cmd.offset_from and cmd.offset_from.lower() not in ("auto", "null", "none", ""):
            offset_item = _find_item(items, cmd.offset_from)
            if offset_item:
                offset_item.amount = max(0, offset_item.amount - actual_delta)
                diff = actual_delta
                if diff >= 0:
                    changes.append(f"Reduced '{cmd.offset_from}' by ${diff:,}")
                else:
                    changes.append(f"Increased '{cmd.offset_from}' by ${abs(diff):,}")
            else:
                # Fall through to auto-offset
                offsets = _auto_offset_items(items, cmd.target_category, actual_delta)
                for item, trim in offsets:
                    item.amount = max(0, item.amount - trim)
        else:
            offsets = _auto_offset_items(items, cmd.target_category, actual_delta)
            for item, trim in offsets:
                actual_trim = min(item.amount, trim)
                item.amount -= actual_trim
                if actual_trim > 0:
                    changes.append(f"Auto-reduced '{item.category.value}' by ${actual_trim:,}")

    return items, changes


# ── Stage 3: Validation & Auto-Correction ─────────────────────────────────────

def _validate_and_correct(
    items: List[BudgetLineItem],
    total_budget: int,
    min_wage_hourly: float,
) -> Tuple[List[BudgetLineItem], List[str]]:
    """
    Enforce compliance rules and return a list of human-readable corrections.
    """
    corrections: List[str] = []

    # 1. Minimum wage floor for personnel items
    for item in items:
        if item.category not in PERSONNEL_CATEGORIES:
            continue
        fte = item.fte_count or 0
        if fte <= 0:
            continue
        min_annual = min_wage_hourly * HOURS_PER_FTE_YEAR * fte
        if item.amount < min_annual:
            old = item.amount
            item.amount = int(min_annual)
            corrections.append(
                f"Increased '{item.category.value}' from ${old:,} → ${item.amount:,} "
                f"to meet ${min_wage_hourly:.2f}/hr minimum wage for {fte:.1f} FTE"
            )

    # 2. Indirect cost cap (approx 15% if not known)
    indirect_total = sum(
        i.amount for i in items
        if i.category.value in {"Indirect Costs / Overhead", "Facilities & Rent", "IT & Communications"}
    )
    indirect_cap = int(total_budget * DEFAULT_INDIRECT_CAP_PCT / 100)
    if indirect_total > indirect_cap:
        excess = indirect_total - indirect_cap
        # Trim the largest indirect item
        indirect_items = [
            i for i in items
            if i.category.value in {"Indirect Costs / Overhead", "Facilities & Rent", "IT & Communications"}
        ]
        for ix in indirect_items:
            trim = min(ix.amount, excess)
            ix.amount -= trim
            excess -= trim
            corrections.append(
                f"Trimmed '{ix.category.value}' by ${trim:,} to respect the {DEFAULT_INDIRECT_CAP_PCT}% indirect cap"
            )
            if excess <= 0:
                break

    # 3. Fix rounding so amounts sum to exactly total_budget
    current_total = sum(i.amount for i in items)
    gap = total_budget - current_total
    if gap != 0 and items:
        # Add/subtract from the largest non-personnel item
        safe = [i for i in items if i.category not in PERSONNEL_CATEGORIES]
        target = max(safe, key=lambda i: i.amount) if safe else max(items, key=lambda i: i.amount)
        target.amount += gap
        if abs(gap) > 0:
            corrections.append(
                f"Adjusted '{target.category.value}' by ${gap:+,} to maintain total of ${total_budget:,}"
            )

    return items, corrections


# ── Stage 4: Explanation prompt ────────────────────────────────────────────────

EXPLAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a friendly NGO Financial Consultant.
Explain the budget changes that were just made in clear, non-technical language.
Be concise (2-4 sentences max). Refer to dollar amounts. If corrections were made, explain WHY they were necessary (e.g., wage law, grant cap).
Use a warm, professional tone. Start with what was done, then explain any constraints.
"""),
    ("user", """\
User asked: "{user_request}"

Changes applied:
{changes}

Compliance corrections made (if any):
{corrections}

Final budget summary:
{final_summary}
""")
])


def _format_budget_summary(items: List[BudgetLineItem], total: int) -> str:
    lines = [f"  Total: ${total:,}"]
    for i in items:
        fte_str = f" ({i.fte_count:.1f} FTE)" if i.fte_count else ""
        lines.append(f"  • {i.category.value}{fte_str}: ${i.amount:,}")
    return "\n".join(lines)


# ── Main entry point ───────────────────────────────────────────────────────────

def refine_budget(current_budget: dict, user_request: str) -> dict:
    """
    Three-stage pipeline:
    1. LLM extracts structured intent from user_request
    2. Python applies the edit and validates/autocorrects
    3. LLM generates a natural-language explanation of what happened
    """
    print(f"💬 Budget chat: {user_request}")

    total_budget: int = current_budget.get("total_requested", 0)
    if total_budget == 0:
        return {"error": "Invalid budget", "details": "total_requested is 0 or missing."}

    items = _items_from_budget(current_budget)
    if not items:
        return {"error": "Invalid budget", "details": "No line items found."}

    # Derive location from compliance_summary if available
    location = "default"
    for check in current_budget.get("compliance_summary", {}).get("wage_checks", []):
        if isinstance(check, dict) and check.get("min_wage_hourly"):
            min_wage_hourly = float(check["min_wage_hourly"])
            break
    else:
        min_wage_hourly = get_minimum_wage(location)

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

    # ── Stage 1: Parse intent ─────────────────────────────────────────────────
    budget_summary = _format_budget_summary(items, total_budget)
    category_list = [c.value for c in CategoryType]

    intent_chain = INTENT_PROMPT | llm.with_structured_output(BudgetEditCommand)
    try:
        cmd: BudgetEditCommand = intent_chain.invoke({
            "category_list": ", ".join(category_list),
            "budget_summary": budget_summary,
            "user_request": user_request,
        })
    except Exception as e:
        return {"error": "Intent parsing failed", "details": str(e)}

    if cmd.clarification_needed:
        return {
            "clarification": cmd.clarification_needed,
            "items": current_budget.get("items", []),
            "total_requested": total_budget,
            "locality_explanation": current_budget.get("locality_explanation", ""),
            "compliance_summary": current_budget.get("compliance_summary", {}),
            "chat_response": f"I need a bit more info: {cmd.clarification_needed}",
        }

    print(f"   📋 Intent: {cmd.action} '{cmd.target_category}' Δ={cmd.amount_delta} from '{cmd.offset_from}'")

    # ── Stage 2: Apply edit ───────────────────────────────────────────────────
    items_copy = copy.deepcopy(items)
    items_copy, changes = _apply_edit(items_copy, cmd, total_budget)

    # ── Stage 3: Validate & auto-correct ─────────────────────────────────────
    items_copy, corrections = _validate_and_correct(items_copy, total_budget, min_wage_hourly)

    # ── Stage 4: Explain ──────────────────────────────────────────────────────
    final_summary = _format_budget_summary(items_copy, total_budget)
    explain_chain = EXPLAIN_PROMPT | llm

    try:
        explanation = explain_chain.invoke({
            "user_request": user_request,
            "changes": "\n".join(changes) if changes else "No changes were needed.",
            "corrections": "\n".join(corrections) if corrections else "None — all rules satisfied.",
            "final_summary": final_summary,
        })
        chat_response = explanation.content.strip()
    except Exception:
        # Graceful fallback
        parts = ["Here's what I did:"] + changes
        if corrections:
            parts.append("Compliance corrections:")
            parts.extend(f"  • {c}" for c in corrections)
        chat_response = "\n".join(parts)

    # ── Assemble final budget dict ────────────────────────────────────────────
    return {
        "items": [i.model_dump() for i in items_copy],
        "total_requested": total_budget,
        "locality_explanation": current_budget.get("locality_explanation", ""),
        "compliance_summary": current_budget.get("compliance_summary", {}),
        "chat_response": chat_response,
        "_edit_log": {
            "parsed_intent": cmd.model_dump(),
            "changes": changes,
            "corrections": corrections,
        },
    }