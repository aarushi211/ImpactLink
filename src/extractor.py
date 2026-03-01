import os
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

os.environ["GOOGLE_API_KEY"] = "GOOGLE_API_KEY"

class ProposalFeatures(BaseModel):
    organization_name: str = Field(description="Official name of the NGO or organization")
    project_title: str = Field(description="The name of the specific project or initiative")
    primary_mission: str = Field(description="A concise 2-3 sentence summary of the project's core goal")
    target_beneficiaries: List[str] = Field(description="Who receives help (e.g., 'At-risk youth', 'Rural farmers')")
    geographic_focus: List[str] = Field(description="Specific cities, regions, or countries where the project takes place")
    sdg_alignment: List[str] = Field(description="Which UN Sustainable Development Goals fit best (e.g., 'Goal 1: No Poverty', 'Goal 4: Quality Education')")
    requested_amount: Optional[int] = Field(description="Total budget requested in USD, if mentioned. Return null if not found.")
    budget_breakdown: List[str] = Field(description="High-level budget categories mentioned (e.g., 'Labor', 'Equipment', 'Travel')")

def build_extraction_chain():
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(ProposalFeatures)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert grant reviewer. Your job is to extract specific metadata from the provided NGO proposal text to help match them with funders. If a piece of information is missing, do your best to infer it from context, or leave it blank if impossible."),
        ("user", "Here is the proposal text:\n\n{text}")
    ])

    return prompt | structured_llm

def extract_proposal_data(pdf_path: str) -> dict:
    print(f"📄 Loading PDF: {pdf_path}")
    
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    
    combined_text = "\n".join([page.page_content for page in pages[:10]])
    
    print("🧠 Processing with Gemini...")
    chain = build_extraction_chain()
    
    result = chain.invoke({"text": combined_text})
    
    return result.model_dump()

if __name__ == "__main__":
    sample_pdf = "Data/ago_-letter-proposal_for-candid-2.pdf" 
    
    if os.path.exists(sample_pdf):
        extracted_data = extract_proposal_data(sample_pdf)
        
        print("\n✅ Extraction Complete! Here is the JSON ready for your database:\n")
        import json
        print(json.dumps(extracted_data, indent=2))
    else:
        print(f"❌ Could not find {sample_pdf}. Please update the path and try again.")
