"""Parse explicit edits, then recalculate salary, fringe and indirect costs in Python."""

import json
from decimal import Decimal
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from utils.llm import get_chat_model
from services.budget.costing import CostPlan, calculate_budget


class CostEdit(BaseModel):
    line_id: str | None = None
    field: Literal["headcount", "annual_salary", "fte_per_person", "months", "fringe_rate_pct", "quantity", "unit_cost", "rate_pct"] | None = None
    value: Decimal | None = None
    remove_line: bool = False
    clarification: str | None = None


EDIT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Parse one explicit change to these budget assumptions. Return exact line IDs.
Do not invent salaries, staffing levels, duration, rates or offsets. A headcount is an integer; FTE per person is 0..1.
If the user asks for an amount transfer without specifying a change in headcount, salary, FTE, months, unit cost or quantity, ask for clarification.
Only remove a line when explicitly asked. Edit global indirect rate using line_id='indirect', field='rate_pct'.
For multiple changes or unclear targets/values ask for clarification. Do not change unrelated lines.
An edit changes project costs; do not force the result to equal the grant ceiling."""),
    ("user", "Current assumptions:\n{inputs}\nRequest: {request}"),
])


def unchanged(budget, message):
    return {**budget, "chat_response": message, "clarification": message, "_edit_log": {"applied": False}}


def apply_cost_edit(budget, edit):
    plan = CostPlan.model_validate(budget["cost_inputs"]).model_dump(mode="json")
    if edit.clarification:
        return unchanged(budget, edit.clarification)
    target, bucket = None, None
    if edit.line_id == "indirect":
        target, bucket = plan["indirect"], "indirect"
    else:
        for name in ("staff", "direct_costs"):
            for line in plan[name]:
                if line["id"] == edit.line_id:
                    target, bucket = line, name
    if target is None:
        return unchanged(budget, "Specify the staff role or direct-cost line to change.")
    allowed = {"staff": {"headcount", "annual_salary", "fte_per_person", "months", "fringe_rate_pct"}, "direct_costs": {"quantity", "unit_cost"}, "indirect": {"rate_pct"}}
    if edit.remove_line and bucket != "indirect" and edit.field is None and edit.value is None:
        plan[bucket].remove(target)
    elif not edit.remove_line and edit.field in allowed[bucket] and edit.value is not None:
        if edit.field == "headcount":
            if edit.value != edit.value.to_integral_value():
                return unchanged(budget, "Headcount must be a whole number. Use FTE per person for part-time effort.")
            target[edit.field] = int(edit.value)
        else:
            target[edit.field] = str(edit.value)
    else:
        return unchanged(budget, "Specify one new staffing or unit-cost assumption. Salary, fringe and indirect totals are calculated from those inputs.")
    try:
        result = calculate_budget(plan, budget["max_budget"])
    except ValueError as exc:
        return unchanged(budget, f"That change needs review: {exc}")
    result["chat_response"] = f"Updated the requested assumption and recalculated salary, fringe and indirect costs. Total requested: ${result['total_requested']:,.2f}." + (f" The plan exceeds the ceiling by ${result['funding_gap']:,.2f}; review the scope options." if result["funding_gap"] else "")
    result["_edit_log"] = {"applied": True, "parsed_intent": edit.model_dump(mode="json")}
    return result


def refine_budget(current_budget, user_request):
    if current_budget.get("model_version") != 2 or not current_budget.get("cost_inputs"):
        return unchanged(current_budget, "This saved budget uses the earlier model. Enter its staff and direct-cost assumptions in Budget Setup and rebuild it to use FTE, fringe and indirect-base calculations.")
    try:
        CostPlan.model_validate(current_budget["cost_inputs"])
        llm = get_chat_model()
        edit = (EDIT_PROMPT | llm.with_structured_output(CostEdit)).invoke({"inputs": json.dumps(current_budget["cost_inputs"]), "request": user_request})
        return apply_cost_edit(current_budget, edit)
    except Exception:
        return unchanged(current_budget, "Could not apply that edit. Change the staffing or unit-cost inputs in Budget Setup and rebuild, or specify one clear change in chat.")
