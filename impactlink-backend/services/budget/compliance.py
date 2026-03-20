from typing import List, Set, Tuple

from .models import BudgetLineItem, CategoryType, GrantRules, ComplianceViolation
from .constants import PERSONNEL_CATEGORIES, DIRECT_SERVICE_CATEGORIES


def enforce_grant_rules(
    line_items: List[BudgetLineItem],
    max_budget: int,
    rules: GrantRules,
    indirect_categories: Set[CategoryType],
    unallowable_categories: Set[CategoryType],
    labor_cap: int,
    min_wage_hourly: float,
) -> Tuple[List[BudgetLineItem], dict]:
    report: dict = {
        "violations_fixed": [],
        "hard_violations": [],
        "wage_checks": [],
    }

    # ── Rule 1: Unallowable costs (hard block) ────────────────
    blocked = [i for i in line_items if i.category in unallowable_categories]
    if blocked:
        names = [i.category.value for i in blocked]
        report["hard_violations"].append(f"Unallowable categories: {names}")
        raise ComplianceViolation(
            f"Budget contains categories forbidden by this grant: {names}."
        )

    # ── Rule 2: Indirect cost cap ─────────────────────────────
    # Uses the grant-defined set, not keywords
    indirect_items = [i for i in line_items if i.category in indirect_categories]
    indirect_total = sum(i.amount for i in indirect_items)
    indirect_cap_amount = int(max_budget * rules.indirect_cost_cap_pct / 100)

    if indirect_total > indirect_cap_amount:
        excess = indirect_total - indirect_cap_amount
        for item in indirect_items:
            trim = int(excess * (item.amount / indirect_total))
            item.amount -= trim
            item.compliance_notes.append(
                f"Trimmed ${trim:,} to meet {rules.indirect_cost_cap_pct}% indirect cap."
            )
        report["violations_fixed"].append(
            f"Indirect costs: ${indirect_total:,} → ${indirect_cap_amount:,}"
        )

    # ── Rule 3: Personnel cap (CoL-Adjusted via labor_cap) ────
    personnel_items = [i for i in line_items if i.category in PERSONNEL_CATEGORIES]
    personnel_total = sum(i.amount for i in personnel_items)

    if personnel_total > labor_cap:
        excess = personnel_total - labor_cap
        for item in personnel_items:
            trim = int(excess * (item.amount / personnel_total))
            item.amount -= trim
            item.compliance_notes.append(
                f"Trimmed ${trim:,} to meet CoL-adjusted personnel cap."
            )
        report["violations_fixed"].append(
            f"Personnel: ${personnel_total:,} → ${labor_cap:,} (CoL adjusted)"
        )

    # ── Rule 4: Per-role minimum wage check ───────────────────
    # Items whose wage was already set by the Python personnel engine are skipped.
    wage_violations = []
    for item in personnel_items:
        if item.wage_validated:
            report["wage_checks"].append({
                "category":    item.category.value,
                "fte_count":   float(item.fte_count or 0),
                "compliant":   True,
                "note":        "Pre-validated by personnel engine — check skipped.",
            })
            continue

        fte = item.fte_count or 0.0
        if fte <= 0:
            report["wage_checks"].append({
                "category": item.category.value,
                "compliant": None,
                "note": "No FTE count provided — wage check skipped.",
            })
            continue

        hours_per_year_per_fte = 2080
        total_hours  = fte * hours_per_year_per_fte
        per_hour_rate = item.amount / total_hours if total_hours > 0 else 0
        compliant = per_hour_rate >= min_wage_hourly

        check = {
            "category":      item.category.value,
            "fte_count":     float(fte),
            "allocated_amount": item.amount,
            "per_hour_rate": round(per_hour_rate, 2),
            "min_wage_hourly": min_wage_hourly,
            "compliant":     compliant,
        }
        report["wage_checks"].append(check)

        if not compliant:
            shortfall = int((min_wage_hourly - per_hour_rate) * total_hours)
            warning_msg = (
                f"{item.category.value}: ${per_hour_rate:.2f}/hr "
                f"< minimum ${min_wage_hourly:.2f}/hr "
                f"(shortfall: ${shortfall:,} for {fte} FTEs)"
            )
            wage_violations.append(warning_msg)
            item.compliance_notes.append(f"⚠️ Minimum wage warning: {warning_msg}")

    if wage_violations:
        report["violations_fixed"].append(
            "Minimum wage warning(s) — manual review suggested:\n" +
            "\n".join(wage_violations)
        )


    # ── Rule 5: Minimum direct service spend (flag only) ──────
    if rules.min_direct_service_pct:
        direct_items = [i for i in line_items if i.category in DIRECT_SERVICE_CATEGORIES]
        direct_total = sum(i.amount for i in direct_items)
        min_pct = rules.min_direct_service_pct or 0.0
        min_direct = int(max_budget * min_pct / 100)
        if direct_total < min_direct:
            note = (
                f"Direct service ${direct_total:,} below required "
                f"{min_pct}% (${min_direct:,}). Manual review needed."
            )
            report["violations_fixed"].append(note)
            for item in direct_items:
                item.compliance_notes.append("⚠️ Direct service minimum not met.")

    return line_items, report
