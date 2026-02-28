import os
import tempfile
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_community.document_loaders import PyPDFLoader
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate


# --- Pydantic Model (structured output) ---

class ProposalFeatures(BaseModel):
    organization_name: str = Field(description="Official name of the NGO or organization")
    project_title: str = Field(description="The name of the specific project or initiative")
    primary_mission: str = Field(description="A concise 2-3 sentence summary of the project's core goal")
    target_beneficiaries: List[str] = Field(description="Who receives help (e.g., 'At-risk youth', 'Rural farmers')")
    geographic_focus: List[str] = Field(description="Specific cities, regions, or countries where the project takes place")
    sdg_alignment: List[str] = Field(description="Which UN Sustainable Development Goals fit best (e.g., 'Goal 1: No Poverty')")
    requested_amount: Optional[int] = Field(description="Total budget requested in USD, if mentioned. Return null if not found.")
    budget_breakdown: List[str] = Field(description="High-level budget categories mentioned (e.g., 'Labor', 'Equipment', 'Travel')")
    cause_area: str = Field(description="Primary cause area (e.g., 'education', 'healthcare', 'climate', 'women empowerment')")
    key_activities: List[str] = Field(description="Main project activities listed in the proposal")


# --- Chain Builder ---

def build_extraction_chain():
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    structured_llm = llm.with_structured_output(ProposalFeatures)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert grant reviewer. Extract specific metadata from the NGO proposal 
to help match them with funders. If information is missing, infer from context or leave blank."""),
        ("user", "Here is the proposal text:\n\n{text}")
    ])

    return prompt | structured_llm


# --- Main Parse Function (called by FastAPI) ---

def parse_proposal(file_bytes: bytes, filename: str) -> dict:
    """
    Accepts raw file bytes from FastAPI upload.
    Writes to temp file (PyPDFLoader needs a path), extracts, returns dict.
    """
    suffix = ".pdf" if filename.endswith(".pdf") else ".txt"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        loader = PyPDFLoader(tmp_path)
        pages = loader.load()
        combined_text = "\n".join([page.page_content for page in pages[:10]])

        chain = build_extraction_chain()
        result = chain.invoke({"text": combined_text})

        return result.model_dump()

    finally:
        os.unlink(tmp_path)