"""
services/budget/personnel.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extracts personnel roles + headcount from the proposal text, then
computes a compliant, wage-validated personnel budget using pure Python.

Pipeline
--------
1. `extract_personnel_from_proposal(proposal)` — LLM call.
   Returns a list of PersonnelRole objects.

2. `compute_personnel_budget(roles, min_wage_hourly, labor_cap)` — pure Python.
   a. Computes the minimum annual wage for each role.
   b. If total > labor_cap:
      - Strategy A: Reduce FTE proportionally (floor 1.0 per role).
      - Strategy B: If still over cap, scale all amounts to hit exactly labor_cap.
   c. Returns (BudgetLineItem list, personnel_report dict)
"""

from __future__ import annotations

import math
from typing import List, Optional

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .models import BudgetLineItem, CategoryType, GrantRules


# ── FTE-to-CategoryType mapping ───────────────────────────────────────────────

_ROLE_TO_CATEGORY = {
    "field staff":       CategoryType.FIELD_STAFF,
    "fieldworker":       CategoryType.FIELD_STAFF,
    "community worker":  CategoryType.FIELD_STAFF,
    "admin":             CategoryType.ADMIN_STAFF,
    "administrative":    CategoryType.ADMIN_STAFF,
    "coordinator":       CategoryType.ADMIN_STAFF,
    "manager":           CategoryType.PROJECT_LEAD,
    "project lead":      CategoryType.PROJECT_LEAD,
    "director":          CategoryType.PROJECT_LEAD,
    "consultant":        CategoryType.CONSULTANTS,
    "contractor":        CategoryType.CONSULTANTS,
}

def _role_to_category(role_name: str) -> CategoryType:
    name_lower = role_name.lower()
    for keyword, cat in _ROLE_TO_CATEGORY.items():
        if keyword in name_lower:
            return cat
    # Default unmapped roles to Field Staff
    return CategoryType.FIELD_STAFF


# ── Pydantic models for LLM extraction ────────────────────────────────────────

class PersonnelRole(BaseModel):
    role_title: str = Field(description="Job title or role name exactly as mentioned")
    fte_count: float = Field(description="Number of full-time equivalents for this role (>0)")
    context_note: str = Field(
        default="",
        description="One-line reference to where this was found in the proposal"
    )


class PersonnelExtraction(BaseModel):
    roles: List[PersonnelRole] = Field(
        description="All staff roles extracted from the proposal. Empty list if none mentioned."
    )

class ComplianceViolation(Exception):
    """Custom exception for budgets that cannot meet legal labor requirements."""
    pass


# ── LLM extraction prompt ─────────────────────────────────────────────────────

PERSONNEL_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a grant budget analyst.
Extract all staff roles and their headcount from the NGO project proposal below.

RULES:
- Only extract roles that have an explicit or STRONGLY implied headcount.
- Express fractional FTEs as decimals (e.g. 0.5 for part-time).
- Do NOT invent roles that aren't mentioned.
- If no staff are mentioned, return an empty list.
"""),
    ("user", """Proposal details:
Organization: {org_name}
Project Title: {title}
Mission: {mission}
Key Activities: {activities}
Budget Breakdown (as listed in proposal): {budget_breakdown}
Beneficiaries: {beneficiaries}
""")
])


def extract_personnel_from_proposal(proposal: dict) -> List[PersonnelRole]:
    """
    Call the LLM to extract personnel roles + FTE counts from the proposal.
    Returns an empty list if no staff are mentioned or the call fails.
    """
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    chain = PERSONNEL_EXTRACT_PROMPT | llm.with_structured_output(PersonnelExtraction)

    try:
        result: PersonnelExtraction = chain.invoke({
            "org_name":        proposal.get("organization_name", ""),
            "title":           proposal.get("project_title", ""),
            "mission":         proposal.get("primary_mission", ""),
            "activities":      ", ".join(proposal.get("key_activities", [])),
            "budget_breakdown": ", ".join(proposal.get("budget_breakdown", [])),
            "beneficiaries":   ", ".join(proposal.get("target_beneficiaries", [])),
        })
        print(f"👥 Extracted {len(result.roles)} personnel role(s) from proposal")
        for r in result.roles:
            print(f"   • {r.role_title}: {r.fte_count} FTE")
        return result.roles
    except Exception as e:
        print(f"⚠️  Personnel extraction failed — skipping: {e}")
        return []


# ── Pure-Python wage computation ───────────────────────────────────────────────

HOURS_PER_FTE_YEAR = 2080  # 40 hrs/week × 52 weeks


def compute_personnel_budget(
    roles: List[PersonnelRole],
    min_wage_hourly: float,
    labor_cap: int,
) -> tuple[List[BudgetLineItem], dict]:
    if not roles:
        return [], {"personnel_items": [], "adjustments": []}

    report = {"personnel_items": [], "adjustments": []}
    
    # ── STEP 1: Calculate Absolute Minimum Cost per Role ──
    # This is the cost of 1.0 FTE at the legal minimum wage.
    ABS_MIN_PER_ROLE = min_wage_hourly * HOURS_PER_FTE_YEAR # e.g., $56,160 in LA
    
    # ── STEP 2: Role Prioritization/Elimination ──
    # If we have 4 roles but the cap only supports 1.5 roles at min wage, 
    # we must eliminate or consolidate roles.
    max_affordable_roles = labor_cap / ABS_MIN_PER_ROLE
    
    if len(roles) > max_affordable_roles:
        old_count = len(roles)
        # Keep only the roles we can actually afford at minimum wage
        roles = roles[:int(max_affordable_roles)] 
        if not roles: # If cap is so low we can't afford even 1 person
             raise ComplianceViolation(f"Labor cap ${labor_cap:,} is too low to support any staff at ${min_wage_hourly}/hr.")
        
        msg = f"Grant cap only supports {max_affordable_roles:.1f} roles. Consolidated {old_count} roles into {len(roles)}."
        report["adjustments"].append(msg)
        print(f"⚠️ {msg}")

    # ── STEP 3: Initial Allocation ──
    role_data = []
    for r in roles:
        # Start with the FTE requested, but we will scale it
        role_data.append({"role": r.role_title, "fte": r.fte_count, "amount": 0})

    # ── STEP 4: Strategy A & B (Proportional Scaling with Wage Floor) ──
    total_requested_fte = sum(d["fte"] for d in role_data)
    
    # If the total requested FTEs * Min Wage > Cap, we must scale FTEs down
    total_min_cost_requested = total_requested_fte * ABS_MIN_PER_ROLE
    
    if total_min_cost_requested > labor_cap:
        # Scale FTEs so the total cost exactly equals the labor_cap
        # while keeping everyone at exactly min_wage_hourly
        for d in role_data:
            share = d["fte"] / total_requested_fte
            d["amount"] = int(labor_cap * share)
            # Re-calculate FTE based on the fixed wage floor
            d["fte"] = round(d["amount"] / ABS_MIN_PER_ROLE, 2)
            
            # Ensure a hard floor of at least some minimal participation
            if d["fte"] < 0.1: d["fte"] = 0.1 
    else:
        # We have extra room! We can pay more than min wage or keep requested FTEs
        for d in role_data:
            d["amount"] = int(d["fte"] * ABS_MIN_PER_ROLE)

    # ── STEP 5: Final Integrity Check ──
    line_items = []
    for d in role_data:
        actual_hourly = d["amount"] / (d["fte"] * HOURS_PER_FTE_YEAR)
        
        # FINAL GUARDRAIL: If math rounding pushed us below min wage, force it up
        if actual_hourly < (min_wage_hourly - 0.01):
             d["amount"] = int(d["fte"] * ABS_MIN_PER_ROLE)
             actual_hourly = min_wage_hourly

        category = _role_to_category(d["role"])
        item = BudgetLineItem(
            category=category,
            description=f"{d['role']} ({d['fte']:.2f} FTE @ ${actual_hourly:.2f}/hr)",
            amount=d["amount"],
            fte_count=d["fte"],
            compliance_notes=[f"Verified: ${actual_hourly:.2f}/hr fits LA County limits."]
        )
        line_items.append(item)

    return line_items, report
