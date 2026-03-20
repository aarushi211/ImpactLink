from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional


class CategoryType(str, Enum):
    # Personnel bucket
    FIELD_STAFF          = "Field Staff"
    ADMIN_STAFF          = "Administrative Staff"
    PROJECT_LEAD         = "Project Lead / Management"
    CONSULTANTS          = "Consultants / Contractors"
    # Direct service bucket
    PROGRAM_ACTIVITIES   = "Program Activities"
    TRAINING_EDUCATION   = "Training & Education"
    OUTREACH             = "Community Outreach"
    EQUIPMENT_SUPPLIES   = "Equipment & Supplies"
    TRAVEL               = "Travel & Transportation"
    # Indirect bucket
    INDIRECT_OVERHEAD    = "Indirect Costs / Overhead"
    FACILITIES           = "Facilities & Rent"
    IT_COMMUNICATIONS    = "IT & Communications"
    # Other
    EVALUATION           = "Monitoring & Evaluation"
    CONTINGENCY          = "Contingency"


class GrantRules(BaseModel):
    personnel_cap_pct: float = Field(
        default=75.0,
        description="Max % of total budget allowed for all personnel categories combined."
    )
    indirect_cost_cap_pct: float = Field(
        default=15.0,
        description="Max % of total budget allowed for indirect/overhead costs."
    )
    indirect_cost_includes: List[str] = Field(
        default_factory=list,
        description=(
            "List of cost types the grant explicitly classifies as indirect/overhead. "
            "Use exact CategoryType enum values where possible. "
            f"Valid values: {[e.value for e in CategoryType]}"
        )
    )
    unallowable_costs: List[str] = Field(
        default_factory=list,
        description=(
            "CategoryType values explicitly forbidden by this grant. "
            f"Valid values: {[e.value for e in CategoryType]}"
        )
    )
    min_direct_service_pct: Optional[float] = Field(
        default=None,
        description="Minimum % that must be spent on direct program activities. Null if not specified."
    )
    requires_cost_share: bool = Field(
        default=False,
        description="True if the grant requires a matching contribution."
    )
    notes: str = Field(default="", description="Other notable restrictions in plain English.")


class BudgetCategory(BaseModel):
    category: CategoryType = Field(
        description="Must be one of the predefined CategoryType values."
    )
    description: str = Field(
        description="Justification tied to specific project activities."
    )
    percentage: float = Field(
        description="Share of total budget (0–100). All categories must sum to 100."
    )
    fte_count: Optional[float] = Field(
        default=None,
        description=(
            "For personnel categories only: number of full-time equivalents. "
            "Must be > 0 for Field Staff, Admin Staff, Project Lead. "
            "Leave null for non-personnel."
        )
    )


class BudgetAllocationPlan(BaseModel):
    categories: List[BudgetCategory]
    locality_explanation: str

    @model_validator(mode="after")
    def normalize_percentages(self):
        total = sum(c.percentage for c in self.categories)
        if abs(total - 100.0) > 0.01:
            print(f"⚠️  Percentages summed to {total:.2f}%. Normalizing...")
            for c in self.categories:
                c.percentage = (c.percentage / total) * 100.0
        return self


class BudgetLineItem(BaseModel):
    category: CategoryType
    description: str
    amount: int
    fte_count: Optional[float] = None
    compliance_notes: List[str] = Field(default_factory=list)
    wage_validated: bool = Field(
        default=False,
        description="True if this item's wage was already set/validated by the Python personnel engine."
    )


class LocalizedBudget(BaseModel):
    items: List[BudgetLineItem]
    total_requested: int
    locality_explanation: str
    compliance_summary: dict


class ComplianceViolation(Exception):
    pass
