"""Explicit cost assumptions and deterministic calculations for proposal budgets."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CostModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True, validate_default=True)


class StaffCost(CostModel):
    id: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=200)
    headcount: int = Field(default=1, ge=1, le=10000, strict=True)
    annual_salary: Decimal = Field(gt=0, le=10000000)
    fte_per_person: Decimal = Field(gt=0, le=1)
    months: Decimal = Field(gt=0, le=120)
    fringe_rate_pct: Decimal = Field(default=0, ge=0, le=100)


CostKind = Literal["supplies", "services", "travel", "equipment", "capital", "rental", "tuition", "scholarships", "patient_care", "participant_support", "subaward"]


class DirectCost(CostModel):
    id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    kind: CostKind
    quantity: Decimal = Field(gt=0, le=10000000)
    unit_cost: Decimal = Field(ge=0, le=1000000000)
    optional: bool = False
    subaward_id: str = ""
    prior_subaward_amount: Decimal = Field(default=0, ge=0, le=1000000000000)

    @model_validator(mode="after")
    def subaward_identity(self):
        if self.kind == "subaward" and not self.subaward_id.strip():
            raise ValueError("Subaward lines need a shared subaward ID to apply the MTDC threshold once per subaward")
        if self.kind != "subaward" and (self.subaward_id or self.prior_subaward_amount):
            raise ValueError("Subaward fields only apply to subawards")
        return self


class IndirectCost(CostModel):
    method: Literal["unconfirmed", "none", "funder", "negotiated", "de_minimis"] = "unconfirmed"
    rate_pct: Decimal = Field(default=0, ge=0, le=100)
    base: Literal["MTDC", "TDC"] = "MTDC"
    reference: str = Field(default="", max_length=1000)
    de_minimis_eligible: bool = False
    funder_cap_pct: Decimal | None = Field(default=None, ge=0, lt=100)
    funder_cap_base: Literal["MTDC", "TDC", "total_cost"] = "MTDC"

    @model_validator(mode="after")
    def rate_basis(self):
        if self.method in {"none", "unconfirmed"} and self.rate_pct:
            raise ValueError("Choose a rate method before entering a nonzero indirect rate")
        if self.method == "de_minimis" and (self.base != "MTDC" or self.rate_pct > 15 or not self.de_minimis_eligible):
            raise ValueError("De minimis requires MTDC, a rate up to 15%, and confirmation that the award and organization qualify")
        if self.method in {"funder", "negotiated"} and not self.reference.strip():
            raise ValueError("Enter the funder rule or negotiated-rate agreement reference")
        return self


class CostPlan(CostModel):
    staff: list[StaffCost] = Field(default_factory=list, max_length=100)
    direct_costs: list[DirectCost] = Field(default_factory=list, max_length=200)
    indirect: IndirectCost = Field(default_factory=IndirectCost)
    unallowable_kinds: list[CostKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_inputs(self):
        lines = self.staff + self.direct_costs
        if not lines:
            raise ValueError("Add at least one staff or direct-cost line")
        if len({line.id for line in lines}) != len(lines):
            raise ValueError("Each staff and direct-cost line needs a unique ID")
        all_ids = [line.id for line in lines] + [line.id + ":fringe" for line in self.staff] + ["calculated:indirect"]
        if len(set(all_ids)) != len(all_ids) or any(line.id == "indirect" for line in lines):
            raise ValueError("Line IDs conflict with calculated fringe or indirect lines")
        prior = {}
        for cost in self.direct_costs:
            if cost.kind in self.unallowable_kinds:
                raise ValueError(f"{cost.description}: {cost.kind} is marked unallowable by the funder")
            if cost.kind == "subaward":
                if cost.subaward_id in prior and prior[cost.subaward_id] != cost.prior_subaward_amount:
                    raise ValueError("All lines for a subaward must report the same previously incurred amount")
                prior[cost.subaward_id] = cost.prior_subaward_amount
        return self


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dollars(value):
    return float(money(value))


EXCLUDED_MTDC = {"equipment", "capital", "rental", "tuition", "scholarships", "patient_care", "participant_support"}
LABELS = {"supplies": "Materials & Supplies", "services": "Services / Contractors", "travel": "Travel & Transportation",
          "equipment": "Equipment", "capital": "Capital Expenditures", "rental": "Facilities & Rent", "tuition": "Tuition Remission",
          "scholarships": "Scholarships & Fellowships", "patient_care": "Patient Care", "participant_support": "Participant Support", "subaward": "Subawards"}


def calculate_budget(inputs, max_budget, *, scope_options=True):
    plan = inputs if isinstance(inputs, CostPlan) else CostPlan.model_validate(inputs)
    ceiling = money(str(max_budget))
    if not ceiling.is_finite() or ceiling <= 0:
        raise ValueError("Grant ceiling must be positive")
    items, warnings = [], []
    direct_total = Decimal(0)
    mtdc = Decimal(0)
    for staff in plan.staff:
        salary = money(staff.annual_salary * staff.headcount * staff.fte_per_person * staff.months / 12)
        fringe = money(salary * staff.fringe_rate_pct / 100)
        items.append({"id": staff.id, "category": "Personnel", "description": f"{staff.role}: {staff.headcount} people × {staff.fte_per_person} FTE × {staff.months} months; ${staff.annual_salary:,.2f} annual salary",
                      "amount": dollars(salary), "fte_count": float(staff.headcount * staff.fte_per_person), "headcount": staff.headcount,
                      "annual_salary": float(staff.annual_salary), "months": float(staff.months), "fringe_rate_pct": float(staff.fringe_rate_pct), "compliance_notes": []})
        if fringe:
            items.append({"id": staff.id + ":fringe", "category": "Fringe Benefits", "description": f"{staff.role}: {staff.fringe_rate_pct}% of ${salary:,.2f} project salary", "amount": dollars(fringe), "compliance_notes": []})
        else:
            warnings.append(f"No fringe included for {staff.role}; confirm the organization's actual benefit costs.")
        direct_total += salary + fringe
        mtdc += salary + fringe
    subaward_used = {}
    exclusions = []
    for cost in plan.direct_costs:
        total = money(cost.quantity * cost.unit_cost)
        included = total
        if cost.kind in EXCLUDED_MTDC:
            included = Decimal(0)
        elif cost.kind == "subaward":
            used = subaward_used.get(cost.subaward_id, cost.prior_subaward_amount)
            included = min(total, max(Decimal(0), Decimal(50000) - used))
            subaward_used[cost.subaward_id] = used + total
        excluded = total - included
        if excluded:
            exclusions.append({"line_id": cost.id, "description": cost.description, "excluded_amount": dollars(excluded)})
        direct_total += total
        mtdc += included
        items.append({"id": cost.id, "category": LABELS[cost.kind], "description": f"{cost.description}: {cost.quantity} × ${cost.unit_cost:,.2f}", "amount": dollars(total), "quantity": float(cost.quantity), "unit_cost": float(cost.unit_cost), "mtdc_included": dollars(included), "compliance_notes": []})
    indirect = plan.indirect
    base_amount = mtdc if indirect.base == "MTDC" else direct_total
    uncapped = money(base_amount * indirect.rate_pct / 100)
    indirect_amount = uncapped
    if indirect.funder_cap_pct is not None:
        cap_base = {"MTDC": mtdc, "TDC": direct_total}.get(indirect.funder_cap_base)
        cap = cap_base * indirect.funder_cap_pct / 100 if cap_base is not None else direct_total * indirect.funder_cap_pct / (100 - indirect.funder_cap_pct)
        cap = cap.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        indirect_amount = min(indirect_amount, cap)
        if indirect_amount < uncapped:
            warnings.append(f"Indirect costs limited by the entered funder cap; ${uncapped - indirect_amount:,.2f} is not charged to this grant.")
    if indirect.method == "unconfirmed":
        warnings.append("Indirect rate is unconfirmed. Indirect costs are excluded until a rate and base are selected.")
    if indirect_amount:
        items.append({"id": "calculated:indirect", "category": "Indirect Costs / Overhead", "description": f"{indirect.rate_pct}% × {indirect.base} base ${base_amount:,.2f}" + (" (funder cap applied)" if indirect_amount < uncapped else ""), "amount": dollars(indirect_amount), "compliance_notes": []})
    total = direct_total + indirect_amount
    gap = max(Decimal(0), total - ceiling)
    result = {
        "model_version": 2, "cost_inputs": plan.model_dump(mode="json"), "items": items,
        "total_requested": dollars(total), "max_budget": dollars(ceiling), "funding_gap": dollars(gap),
        "unallocated_amount": dollars(max(Decimal(0), ceiling - total)),
        "status": "over_ceiling" if gap else "needs_review" if warnings else "within_ceiling",
        "locality_explanation": "Calculated from declared salaries, effort, project months and unit costs. Salary levels and funder allowability require review.",
        "compliance_summary": {"warnings": warnings, "violations_fixed": [], "hard_violations": [f"Requested costs exceed the grant ceiling by ${gap:,.2f}."] if gap else [],
            "requires_funder_review": True, "indirect": {"method": indirect.method, "base": indirect.base, "base_amount": dollars(base_amount), "mtdc": dollars(mtdc), "tdc": dollars(direct_total), "rate_pct": float(indirect.rate_pct), "calculated_amount": dollars(indirect_amount), "exclusions": exclusions, "reference": indirect.reference},
            "review_notes": ["Confirm salary reasonableness, benefit rates, direct/indirect classification, award-specific exclusions, cost share and required documentation.", "MTDC uses the current $50,000 threshold per subaward over its full period; enter prior amounts when applicable."]},
        "scope_options": [],
    }
    if gap and scope_options:
        for kind, rows in (("staff", plan.staff), ("direct_costs", plan.direct_costs)):
            for row in rows:
                if kind == "direct_costs" and not row.optional:
                    continue
                candidate = deepcopy(result["cost_inputs"])
                target = next(item for item in candidate[kind] if item["id"] == row.id)
                if kind == "staff":
                    if row.headcount <= 1:
                        continue
                    target["headcount"] -= 1
                    label = f"Reduce {row.role} headcount from {row.headcount} to {row.headcount - 1}; revise the work plan for the smaller team."
                else:
                    if row.quantity > 1 and row.quantity == row.quantity.to_integral_value():
                        target["quantity"] = str(row.quantity - 1)
                        label = f"Remove one unit of {row.description}; reduce the corresponding activity."
                    else:
                        candidate[kind].remove(target)
                        label = f"Remove optional activity/cost: {row.description}."
                if not candidate["staff"] and not candidate["direct_costs"]:
                    continue
                revised = calculate_budget(candidate, ceiling, scope_options=False)
                saving = money(str(result["total_requested"])) - money(str(revised["total_requested"]))
                if saving > 0:
                    result["scope_options"].append({"label": label, "savings": dollars(saving), "total_requested": revised["total_requested"], "funding_gap": revised["funding_gap"], "cost_inputs": candidate})
                if len(result["scope_options"]) >= 10:
                    break
            if len(result["scope_options"]) >= 10:
                break
    return result
