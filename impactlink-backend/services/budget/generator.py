"""
services/budget/generator.py  —  Personnel-first budget pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pipeline
--------
1. Extract grant rules   (LLM, no math)
2. Resolve enum sets     (Python)
3. Resolve CoL, min wage, labor cap  (Python)
3b. Extract personnel from proposal  (LLM → PersonnelRole list)
3c. Compute personnel budget         (Python engine — wage-validated)
4. LLM allocates SECONDARY categories from the remaining budget
5. Percentages → $ amounts           (Python)
6. Merge personnel + secondary items (Python)
7. Compliance enforcement            (indirect cap, direct service only)
8. Final rebalance                   (fill any gaps into safe categories)
"""

from typing import Optional, List, Set

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .models import (
    CategoryType, BudgetAllocationPlan, BudgetCategory,
    BudgetLineItem, LocalizedBudget, ComplianceViolation, GrantRules,
)
from .constants import PERSONNEL_CATEGORIES, INDIRECT_CATEGORIES_DEFAULT
from .utils import (
    load_locality_index, resolve_multiplier,
    get_minimum_wage, compute_labor_cap, allocations_to_line_items,
)
from .rules import extract_grant_rules, resolve_indirect_categories, resolve_unallowable_categories
from .compliance import enforce_grant_rules
from .personnel import extract_personnel_from_proposal, compute_personnel_budget


# ── Proposal-context categories (keyed from proposal.budget_breakdown) ────────

def _proposal_preferred_categories(proposal: dict) -> List[str]:
    """
    Return a list of category VALUE strings the proposal explicitly mentions
    in its budget_breakdown field. Used to guide the LLM's secondary allocation.
    """
    raw = proposal.get("budget_breakdown", [])
    if not isinstance(raw, list):
        return []
    all_values = {c.value.lower(): c.value for c in CategoryType}
    matched = []
    for entry in raw:
        entry_lower = str(entry).lower()
        for keyword, value in all_values.items():
            if keyword in entry_lower or entry_lower in keyword:
                if value not in matched:
                    matched.append(value)
    return matched


# ── LLM prompt for secondary category allocation ──────────────────────────────

SECONDARY_BUDGET_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert NGO Financial Director.

Your job is to allocate the REMAINING grant budget across SECONDARY spending categories.
Personnel costs are ALREADY fixed — do NOT include any of these categories:
{fixed_personnel_categories}

RULES:
- Choose categories ONLY from this list: {valid_categories}
- Do NOT output dollar amounts — percentages of the REMAINING budget only.
- All percentages must sum to 100.0.
- These categories are FORBIDDEN for this grant: {unallowable_costs}
- Indirect/admin costs (combined) must not exceed {indirect_cap}% of the REMAINING budget.
- PRIORITIZE these categories because they appear in the proposal's budget: {preferred_categories}
  (include them if they are not forbidden; still allocate meaningfully to others as needed)
"""),
    ("user", """\
Project Title: {title}
Activities: {activities}
Location: {location}
Cost of Living Multiplier: {multiplier}x
Remaining budget for secondary categories: ${remaining_budget:,}
""")
])


def generate_budget(
    proposal: dict,
    max_budget: int,
    grant_document: Optional[str] = None,
) -> dict:
    print("💰 Starting personnel-first budget generation pipeline…\n")

    # ── Step 1: Extract grant rules ───────────────────────────────────────────
    rules = extract_grant_rules(grant_document) if grant_document else GrantRules()

    # ── Step 2: Resolve enum sets ─────────────────────────────────────────────
    indirect_categories   = resolve_indirect_categories(rules)
    unallowable_categories = resolve_unallowable_categories(rules)

    # ── Step 3: Deterministic math ────────────────────────────────────────────
    locality_index  = load_locality_index()
    locations       = proposal.get("geographic_focus", [])
    target_location = locations[0] if locations else "Default"

    multiplier      = resolve_multiplier(locality_index, target_location)
    min_wage_hourly = get_minimum_wage(target_location)
    labor_cap       = compute_labor_cap(max_budget, multiplier, rules.personnel_cap_pct)

    print(f"📍 Location:       {target_location}")
    print(f"📈 CoL Multiplier: {multiplier}x")
    print(f"💵 Min Wage:       ${min_wage_hourly:.2f}/hr")
    print(f"👥 Labor Cap:      ${labor_cap:,}")
    print(f"📦 Indirect cats:  {[c.value for c in indirect_categories]}")
    print(f"🚫 Unallowable:    {[c.value for c in unallowable_categories]}\n")

    try:
        # ── Step 3b: Extract personnel from proposal ──────────────────────────
        extracted_roles = extract_personnel_from_proposal(proposal)

        # ── Step 3c: Compute compliant personnel budget ───────────────────────
        personnel_items, personnel_report = compute_personnel_budget(
            extracted_roles, min_wage_hourly, labor_cap
        )
        personnel_total = sum(i.amount for i in personnel_items)
        remaining_budget = max_budget - personnel_total

        print(f"\n📊 Personnel total: ${personnel_total:,}")
        print(f"📊 Remaining for secondary categories: ${remaining_budget:,}\n")

        if remaining_budget <= 0:
            raise ComplianceViolation(
                f"Personnel costs (${personnel_total:,}) consumed the entire budget (${max_budget:,}). "
                "Consider reducing headcount or the maximum budget."
            )

        # ── Step 4: LLM allocates secondary categories ────────────────────────
        # Determine categories that can still be used (exclude personnel + unallowable)
        fixed_cats_values  = [c.value for c in PERSONNEL_CATEGORIES]
        unallow_values     = [c.value for c in unallowable_categories]
        valid_secondary    = [
            c.value for c in CategoryType
            if c not in PERSONNEL_CATEGORIES and c not in unallowable_categories
        ]
        preferred_cats     = _proposal_preferred_categories(proposal)
        # Keep only preferred that are valid
        preferred_cats     = [p for p in preferred_cats if p in valid_secondary]

        llm       = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
        sec_chain = SECONDARY_BUDGET_PROMPT | llm.with_structured_output(BudgetAllocationPlan)

        sec_plan: BudgetAllocationPlan = sec_chain.invoke({
            "fixed_personnel_categories": ", ".join(fixed_cats_values),
            "valid_categories":           valid_secondary,
            "unallowable_costs":          unallow_values or ["none"],
            "indirect_cap":               rules.indirect_cost_cap_pct,
            "preferred_categories":       preferred_cats or ["(none specified)"],
            "title":                      proposal.get("project_title", "NGO Project"),
            "activities":                 ", ".join(proposal.get("key_activities", [])),
            "location":                   target_location,
            "multiplier":                 multiplier,
            "remaining_budget":           remaining_budget,
        })

        # ── Step 5: Percentages → dollar amounts for secondary items ──────────
        secondary_items = allocations_to_line_items(sec_plan, remaining_budget)

        # ── Step 6: Merge personnel + secondary ───────────────────────────────
        line_items = personnel_items + secondary_items

        # ── Step 7: Compliance enforcement (indirect + direct service) ────────
        line_items, compliance_report = enforce_grant_rules(
            line_items, max_budget, rules,
            indirect_categories, unallowable_categories, labor_cap, min_wage_hourly,
        )
        # Attach personnel report to compliance summary
        compliance_report["personnel_report"] = personnel_report

        # ── Step 8: Final rebalance ───────────────────────────────────────────
        total = sum(i.amount for i in line_items)
        if total != max_budget:
            gap = max_budget - total
            safe_items = [
                i for i in line_items
                if i.category not in PERSONNEL_CATEGORIES
                and i.category not in indirect_categories
            ]
            if safe_items:
                max(safe_items, key=lambda i: i.amount).amount += gap
            elif line_items:
                line_items[0].amount += gap  # last resort
            total = max_budget

        assert sum(i.amount for i in line_items) == max_budget, "Budget integrity check failed."

        # Choose a locality explanation from the LLM output
        locality_explanation = sec_plan.locality_explanation or (
            f"Budget generated for {target_location} with a CoL multiplier of {multiplier}x."
        )

        result = LocalizedBudget(
            items=line_items,
            total_requested=total,
            locality_explanation=locality_explanation,
            compliance_summary=compliance_report,
        )

        print(f"\n✅ Budget complete: {len(line_items)} line items | Total: ${total:,}")
        print(f"   👷 Personnel ({len(personnel_items)} roles): ${personnel_total:,}")
        print(f"   📋 Secondary ({len(secondary_items)} cats): ${remaining_budget:,}")
        for adj in personnel_report.get("adjustments", []):
            print(f"   🔧 {adj}")
        for fix in compliance_report.get("violations_fixed", []):
            print(f"   ⚠️  {fix}")

        return result.model_dump()

    except ComplianceViolation as e:
        print(f"\n🚨 COMPLIANCE BLOCK:\n{e}")
        return {"error": "compliance_violation", "details": str(e)}
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return {"error": "generation_failed", "details": str(e)}
