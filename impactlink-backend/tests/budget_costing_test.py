from decimal import Decimal
import unittest
from unittest.mock import patch

from services.budget.costing import CostPlan, calculate_budget
from services.budget.generator import generate_budget
from services.budget_chatbot import CostEdit, apply_cost_edit, refine_budget


def plan():
    return {"staff": [{"id": "staff", "role": "Coordinator", "headcount": 2, "annual_salary": 60000, "fte_per_person": "0.5", "months": 6, "fringe_rate_pct": 20}],
            "direct_costs": [], "indirect": {"method": "funder", "rate_pct": 10, "base": "MTDC", "reference": "Funder guidance section 4"}}


def cost(identifier, kind, amount, **kwargs):
    return {"id": identifier, "description": identifier, "kind": kind, "quantity": 1, "unit_cost": amount, **kwargs}


class BudgetCostingTests(unittest.TestCase):
    def test_salary_effort_duration_and_fringe(self):
        budget = calculate_budget(plan(), 100000)
        self.assertEqual([item["amount"] for item in budget["items"]], [30000, 6000, 3600])
        self.assertEqual(budget["items"][0]["fte_count"], 1)
        self.assertEqual(budget["total_requested"], 39600)
        self.assertEqual(budget["unallocated_amount"], 60400)
        self.assertEqual(sum(item["amount"] for item in budget["items"]), budget["total_requested"])

    def test_ceiling_does_not_scale_salaries_or_fill_remaining_money(self):
        original = plan()
        small = calculate_budget(original, 10000)
        large = calculate_budget(original, 200000)
        self.assertEqual(small["items"], large["items"])
        self.assertEqual(small["funding_gap"], 29600)
        self.assertEqual(small["status"], "over_ceiling")
        self.assertEqual(original, plan())

    def test_scope_option_requires_explicit_application_and_recalculates_indirect(self):
        budget = calculate_budget(plan(), 30000)
        option = budget["scope_options"][0]
        self.assertEqual(budget["cost_inputs"]["staff"][0]["headcount"], 2)
        self.assertEqual(option["cost_inputs"]["staff"][0]["headcount"], 1)
        self.assertEqual(option["cost_inputs"]["staff"][0]["annual_salary"], "60000")
        self.assertEqual(option["total_requested"], 19800)
        self.assertEqual(option["savings"], 19800)
        self.assertEqual(option["funding_gap"], 0)

    def test_optional_scope_units_removed_without_repricing_essential_costs(self):
        inputs = {"direct_costs": [cost("workshops", "services", 1000, quantity=3, optional=True), cost("required", "travel", 1000)], "indirect": {"method": "none"}}
        budget = calculate_budget(inputs, 3000)
        self.assertEqual(len(budget["scope_options"]), 1)
        candidate = budget["scope_options"][0]
        self.assertEqual(candidate["total_requested"], 3000)
        self.assertEqual(candidate["cost_inputs"]["direct_costs"][1]["unit_cost"], "1000")

    def test_mtdc_exclusions_and_subaward_threshold_once_per_subaward(self):
        inputs = {"direct_costs": [cost("supplies", "supplies", 1000), cost("equipment", "equipment", 10000), cost("participants", "participant_support", 3000),
                                  cost("a1", "subaward", 30000, subaward_id="A"), cost("a2", "subaward", 30000, subaward_id="A"), cost("b", "subaward", 70000, subaward_id="B")],
                  "indirect": {"method": "de_minimis", "rate_pct": 15, "de_minimis_eligible": True}}
        result = calculate_budget(inputs, 1000000)
        indirect = result["compliance_summary"]["indirect"]
        self.assertEqual(indirect["mtdc"], 101000)
        self.assertEqual(indirect["calculated_amount"], 15150)
        self.assertEqual(sum(item["excluded_amount"] for item in indirect["exclusions"]), 43000)

    def test_prior_subaward_amount_reduces_remaining_threshold(self):
        inputs = {"direct_costs": [cost("a1", "subaward", 20000, subaward_id="A", prior_subaward_amount=40000), cost("a2", "subaward", 20000, subaward_id="A", prior_subaward_amount=40000)], "indirect": {"method": "none"}}
        result = calculate_budget(inputs, 100000)
        self.assertEqual(result["compliance_summary"]["indirect"]["mtdc"], 10000)

    def test_all_mtdc_exclusion_types_and_tdc_base(self):
        inputs = {"direct_costs": [cost(kind, kind, 1000) for kind in ("equipment", "capital", "rental", "tuition", "scholarships", "patient_care", "participant_support")], "indirect": {"method": "negotiated", "rate_pct": 20, "base": "TDC", "reference": "NICRA 2026"}}
        result = calculate_budget(inputs, 100000)
        self.assertEqual(result["compliance_summary"]["indirect"]["mtdc"], 0)
        self.assertEqual(result["compliance_summary"]["indirect"]["base_amount"], 7000)
        self.assertEqual(result["total_requested"], 8400)

    def test_total_cost_percentage_cap_solves_for_indirect_inclusive_total(self):
        inputs = {"direct_costs": [cost("work", "services", 90000)], "indirect": {"method": "funder", "reference": "Award terms", "rate_pct": 20, "funder_cap_pct": 10, "funder_cap_base": "total_cost"}}
        result = calculate_budget(inputs, 200000)
        self.assertEqual(result["total_requested"], 100000)
        self.assertEqual(result["compliance_summary"]["indirect"]["calculated_amount"], 10000)

    def test_zero_cap_recalculates_indirect_without_cutting_direct_costs(self):
        inputs = plan()
        inputs["indirect"]["funder_cap_pct"] = 0
        result = calculate_budget(inputs, 50000)
        self.assertEqual(result["total_requested"], 36000)
        self.assertEqual(result["items"][0]["amount"], 30000)

    def test_unknown_indirect_and_zero_fringe_require_review(self):
        inputs = plan()
        inputs["indirect"] = {}
        inputs["staff"][0]["fringe_rate_pct"] = 0
        result = calculate_budget(inputs, 100000)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["total_requested"], 30000)
        self.assertEqual(len(result["compliance_summary"]["warnings"]), 2)

    def test_cent_rounding(self):
        result = calculate_budget({"direct_costs": [cost("rounding", "services", "0.335", quantity=3)], "indirect": {"method": "none"}}, 100)
        self.assertEqual(result["total_requested"], 1.01)

    def test_invalid_inputs_are_blocked(self):
        for field, value in (("headcount", 2.4), ("annual_salary", -1), ("annual_salary", "NaN"), ("fte_per_person", 1.5), ("months", 0), ("fringe_rate_pct", 101)):
            inputs = plan(); inputs["staff"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                CostPlan.model_validate(inputs)

    def test_subaward_identity_and_consistent_prior_amount_required(self):
        for rows in ([cost("a", "subaward", 1)], [cost("a", "subaward", 1, subaward_id="A", prior_subaward_amount=10), cost("b", "subaward", 1, subaward_id="A", prior_subaward_amount=20)]):
            with self.assertRaises(ValueError):
                CostPlan.model_validate({"direct_costs": rows})

    def test_de_minimis_is_never_universal_default(self):
        for indirect in ({"method": "de_minimis", "rate_pct": 15}, {"method": "de_minimis", "rate_pct": 16, "de_minimis_eligible": True}, {"method": "de_minimis", "rate_pct": 15, "base": "TDC", "de_minimis_eligible": True}, {"method": "negotiated", "rate_pct": 20}):
            with self.assertRaises(ValueError):
                CostPlan.model_validate({"direct_costs": [cost("a", "services", 1)], "indirect": indirect})

    def test_unallowable_costs_are_blocked_without_silent_removal(self):
        with self.assertRaises(ValueError):
            calculate_budget({"direct_costs": [cost("flight", "travel", 1000)], "unallowable_kinds": ["travel"]}, 10000)

    def test_no_assumptions_are_extracted_from_prose(self):
        result = generate_budget({"key_activities": ["Hire 10 people"]}, 100000)
        self.assertEqual(result["error"], "budget_inputs_required")

    def test_proposal_writer_receives_placeholders_when_inputs_missing(self):
        from agents.budget_injector import get_budget_context
        context = get_budget_context({"project_title": "Community work"}, {})
        self.assertIn("placeholders", context)
        self.assertIn("Do not describe estimated figures", context)

    def test_narrative_verification_does_not_treat_annual_salary_as_project_cost(self):
        from agents.tools.budget_consistency import check_budget_consistency
        budget = calculate_budget(plan(), 100000)
        with patch("agents.tools.budget_consistency._load_budget", return_value=budget):
            result = check_budget_consistency("Annual salary is $60,000. The project budget totals $39,600.", {}, {})
        self.assertFalse(result["issues"])


class BudgetEditTests(unittest.TestCase):
    def test_chat_edit_recalculates_fringe_and_indirect_without_offsets(self):
        budget = calculate_budget(plan(), 100000)
        revised = apply_cost_edit(budget, CostEdit(line_id="staff", field="months", value=Decimal(12)))
        self.assertEqual(revised["total_requested"], 79200)
        self.assertEqual(budget["total_requested"], 39600)
        self.assertEqual(revised["unallocated_amount"], 20800)

    def test_fractional_headcount_and_ambiguous_transfers_do_not_modify_costs(self):
        budget = calculate_budget(plan(), 100000)
        for command in (CostEdit(line_id="staff", field="headcount", value=Decimal("2.4")), CostEdit(clarification="Which activity should change?")):
            result = apply_cost_edit(budget, command)
            self.assertEqual(result["cost_inputs"], budget["cost_inputs"])
            self.assertFalse(result["_edit_log"]["applied"])

    def test_legacy_budget_remains_viewable_without_unsafe_edit(self):
        budget = {"items": [{"category": "Personnel", "amount": 10000}], "total_requested": 10000}
        result = refine_budget(budget, "Move $5000 to equipment")
        self.assertEqual(result["items"], budget["items"])
        self.assertIn("earlier model", result["chat_response"])


if __name__ == "__main__":
    unittest.main()
