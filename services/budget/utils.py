import json
import os
from pathlib import Path
from typing import List, Dict, Any

from .models import BudgetAllocationPlan, BudgetLineItem

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOCALITY_DATA_PATH = os.path.join(BASE_DIR, "Data", "locality_index.json")
MIN_WAGE_PATH = os.path.join(BASE_DIR, "Data", "minimum_wage.json")


def get_minimum_wage(location: str) -> float:
    location_lower = location.lower()
    try:
        with open(MIN_WAGE_PATH, 'r') as f:
            MINIMUM_WAGE_HOURLY = json.load(f)
        for city, wage in MINIMUM_WAGE_HOURLY.items():
            if city in location_lower:
                return float(wage)
        return float(MINIMUM_WAGE_HOURLY.get("default", 15.0))
    except Exception as e:
        print(f"⚠️  Could not load minimum wage index. Using 15.0 default. Error: {e}")
        return 15.0


def load_locality_index() -> dict:
    try:
        with open(LOCALITY_DATA_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load locality index. Using default. Error: {e}")
        return {"default": 1.00}


def resolve_multiplier(locality_index: dict, location: str) -> float:
    for city, mult in locality_index.items():
        if city.lower() in location.lower():
            return mult
    return locality_index.get("default", 1.00)


def compute_labor_cap(max_budget: int, multiplier: float, personnel_cap_pct: float) -> int:
    col_adjusted = int((max_budget * 0.50) * multiplier)
    grant_hard_cap = int(max_budget * personnel_cap_pct / 100)
    return min(col_adjusted, grant_hard_cap)


def allocations_to_line_items(
    plan: BudgetAllocationPlan,
    max_budget: int,
) -> List[BudgetLineItem]:
    """
    Applies LLM percentage allocations directly to the max budget.
    Any gaps due to rounding are added to the largest item.
    """
    line_items: List[BudgetLineItem] = []

    for cat in plan.categories:
        amount = int(max_budget * (cat.percentage / 100.0))
        line_items.append(BudgetLineItem(
            category=cat.category,
            description=cat.description,
            amount=amount,
            fte_count=cat.fte_count,
        ))

    if line_items:
        gap = max_budget - sum(i.amount for i in line_items)
        max(line_items, key=lambda i: i.amount).amount += gap

    return line_items
