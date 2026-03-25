"""
services/budget/personnel.py
"""

from __future__ import annotations

import os
import random
import math
from typing import List, Optional

from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .models import BudgetLineItem, CategoryType, GrantRules

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm() -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=0, groq_api_key=key)


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
    return CategoryType.FIELD_STAFF


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
    pass


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
    Fresh LLM instance per call so with_structured_output() always gets a valid key.
    """
    llm   = _get_llm()
    chain = PERSONNEL_EXTRACT_PROMPT | llm.with_structured_output(PersonnelExtraction)

    try:
        result: PersonnelExtraction = chain.invoke({
            "org_name":         proposal.get("organization_name", ""),
            "title":            proposal.get("project_title", ""),
            "mission":          proposal.get("primary_mission", ""),
            "activities":       ", ".join(proposal.get("key_activities", [])),
            "budget_breakdown": ", ".join(proposal.get("budget_breakdown", [])),
            "beneficiaries":    ", ".join(proposal.get("target_beneficiaries", [])),
        })
        print(f"👥 Extracted {len(result.roles)} personnel role(s) from proposal")
        for r in result.roles:
            print(f"   • {r.role_title}: {r.fte_count} FTE")
        return result.roles
    except Exception as e:
        print(f"⚠️  Personnel extraction failed — skipping: {e}")
        return []


HOURS_PER_FTE_YEAR = 2080


def compute_personnel_budget(
    roles: List[PersonnelRole],
    min_wage_hourly: float,
    labor_cap: int,
) -> tuple[List[BudgetLineItem], dict]:
    if not roles:
        return [], {"personnel_items": [], "adjustments": []}

    report = {"personnel_items": [], "adjustments": []}

    ABS_MIN_PER_ROLE   = min_wage_hourly * HOURS_PER_FTE_YEAR
    max_affordable_roles = labor_cap / ABS_MIN_PER_ROLE

    if len(roles) > max_affordable_roles:
        old_count = len(roles)
        roles = roles[:int(max_affordable_roles)]
        if not roles:
            raise ComplianceViolation(
                f"Labor cap ${labor_cap:,} is too low to support any staff at ${min_wage_hourly}/hr."
            )
        msg = f"Grant cap only supports {max_affordable_roles:.1f} roles. Consolidated {old_count} roles into {len(roles)}."
        report["adjustments"].append(msg)
        print(f"⚠️ {msg}")

    role_data = [{"role": r.role_title, "fte": r.fte_count, "amount": 0} for r in roles]

    total_requested_fte   = sum(d["fte"] for d in role_data)
    total_min_cost_requested = total_requested_fte * ABS_MIN_PER_ROLE

    if total_min_cost_requested > labor_cap:
        for d in role_data:
            share      = d["fte"] / total_requested_fte
            d["amount"] = int(labor_cap * share)
            d["fte"]    = round(d["amount"] / ABS_MIN_PER_ROLE, 2)
            if d["fte"] < 0.1:
                d["fte"] = 0.1
    else:
        for d in role_data:
            d["amount"] = int(d["fte"] * ABS_MIN_PER_ROLE)

    line_items = []
    for d in role_data:
        actual_hourly = d["amount"] / (d["fte"] * HOURS_PER_FTE_YEAR)
        if actual_hourly < (min_wage_hourly - 0.01):
            d["amount"]   = int(d["fte"] * ABS_MIN_PER_ROLE)
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