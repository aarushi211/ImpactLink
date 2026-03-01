import json
from pydantic import BaseModel, Field
from typing import List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALITY_DATA_PATH = os.path.join(BASE_DIR, "data", "locality_index.json")

# --- 1. Pydantic Schemas for Strict Output ---
class BudgetLineItem(BaseModel):
    category: str = Field(description="e.g., 'Personnel', 'Equipment', 'Travel', 'Indirect Costs'")
    description: str = Field(description="Specific justification for this cost based on the proposal.")
    amount: int = Field(description="Exact dollar amount.")

class LocalizedBudget(BaseModel):
    items: List[BudgetLineItem] = Field(description="List of all budget line items.")
    total_requested: int = Field(description="Must exactly match the target grant budget.")
    locality_explanation: str = Field(description="1-2 sentences explaining how local economic factors influenced this budget.")

# --- 2. Deterministic Cost-of-Living Multipliers ---
def load_locality_index():
    try:
        with open(LOCALITY_DATA_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load locality index. Using default. Error: {e}")
        return {"default": 1.00}

# --- 3. Prompt Template ---
BUDGET_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert NGO Financial Director. 
Generate a realistic, localized line-item budget for the provided project.

CRITICAL CONSTRAINTS:
1. The `total_requested` MUST equal exactly the Target Budget Amount provided.
2. The sum of all `amount` values in the `items` list MUST equal the `total_requested`.
3. Use the 'Target Labor Cap' as a strict guide for Personnel costs.
4. Distribute the remaining funds across realistic categories (Equipment, Marketing, Admin, etc.) based on the project activities.
"""),
    ("user", """
Project Title: {title}
Activities: {activities}
Target Location: {location}
Cost of Living Multiplier: {multiplier}x the national average

Target Budget Amount (Grant Max): ${max_budget}
Target Labor Cap (Based on locality): ${labor_cap}

Generate the final JSON budget.
""")
])

def generate_budget(proposal: dict, max_budget: int) -> dict:
    print("💰 Generating locality-aware budget using Groq Data Fusion...")

    locality_index = load_locality_index()
    
    # --- DETERMINISTIC MATH STEP ---
    # 1. Extract location from the parsed NGO proposal
    locations = proposal.get("geographic_focus", [])
    target_location = locations[0] if locations else "Default"
    
    # 2. Find the multiplier based on the text
    multiplier = locality_index["default"]
    for city, mult in locality_index.items():
        if city.lower() in target_location.lower():
            multiplier = mult
            break
            
    # 3. Calculate hard constraints before asking the LLM
    # Base labor is usually 50% of a grant. We scale it by the local cost of living.
    calculated_labor_cap = int((max_budget * 0.50) * multiplier)
    
    # Safety rail: Don't let labor eat the whole grant (cap at 75%)
    if calculated_labor_cap > (max_budget * 0.75):
        calculated_labor_cap = int(max_budget * 0.75)

    # --- LLM GENERATION STEP ---
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0, # Keep it at 0 so the math doesn't get creative
    )
    structured_llm = llm.with_structured_output(LocalizedBudget)
    chain = BUDGET_PROMPT | structured_llm

    try:
        result = chain.invoke({
            "title": proposal.get("project_title", "NGO Project"),
            "activities": ", ".join(proposal.get("key_activities", [])),
            "location": target_location,
            "multiplier": multiplier,
            "max_budget": max_budget,
            "labor_cap": calculated_labor_cap
        })
        
        return result.model_dump()
        
    except Exception as e:
        print(f"❌ Budget Generation Error: {e}")
        return {"error": "Failed to generate budget", "details": str(e)}