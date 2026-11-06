"""Public budget entry point; financial assumptions must be supplied explicitly."""

from .costing import calculate_budget


def generate_budget(proposal, max_budget, grant_document=None, cost_inputs=None):
    inputs = cost_inputs if cost_inputs is not None else proposal.get("budget_inputs")
    if inputs is None:
        return {"error": "budget_inputs_required", "details": "Enter staff salaries, FTE effort, project months, fringe and direct costs in Budget Setup. Financial assumptions are not inferred from prose."}
    try:
        return calculate_budget(inputs, max_budget)
    except ValueError as exc:
        return {"error": "invalid_budget_inputs", "details": str(exc)}
