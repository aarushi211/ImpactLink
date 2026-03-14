from pydantic import BaseModel, Field
from typing import List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from services.budget.models import LocalizedBudget 
import json

CHAT_BUDGET_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a Financial Consultant for NGOs. 
You are helping a user refine their grant budget.

RULES:
1. You MUST keep the 'total_requested' exactly the same as the current budget.
2. If the user wants to increase one category, you MUST decrease another category to balance it.
3. Justify your changes in the 'locality_explanation' field.
4. Return the updated budget in the exact same JSON format.
"""),
    ("user", """
Current Budget:
{current_budget}

User Request:
"{user_request}"

Provide the revised budget:
""")
])

def refine_budget(current_budget: dict, user_request: str) -> dict:
    print(f"💬 Refining budget based on request: {user_request}")
    
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.1 
    )
    
    structured_llm = llm.with_structured_output(LocalizedBudget)
    chain = CHAT_BUDGET_PROMPT | structured_llm

    try:
        result = chain.invoke({
            "current_budget": json.dumps(current_budget, indent=2),
            "user_request": user_request
        })
        return result.model_dump()
    except Exception as e:
        return {"error": "Failed to refine budget", "details": str(e)}