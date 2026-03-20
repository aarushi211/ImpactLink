import os
import re
import tempfile
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_experimental.text_splitter import SemanticChunker
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from config import USE_GROQ, GROQ_API_KEY, LOCAL_LLM_MODEL


# ── Embedder (reuses your existing model) ────────────────────────────────────

class LocalEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text]).tolist()[0]


# ── Pydantic schema (unchanged from your working code) ───────────────────────

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


# ── LLM + chain (unchanged from your working code) ───────────────────────────

def get_extraction_llm():
    if USE_GROQ:
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            groq_api_key=GROQ_API_KEY,
        )
    else:
        return ChatOllama(
            model=LOCAL_LLM_MODEL,
            temperature=0,
            format="json",
            num_ctx=8192,
        )

def build_extraction_chain():
    llm = get_extraction_llm()
    structured_llm = llm.with_structured_output(ProposalFeatures)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert grant reviewer. Extract metadata from the NGO proposal.
If information is missing, infer from context or leave blank.
CRITICAL: Return ONLY a valid JSON object matching the requested schema."""),
        ("user", "Here is the proposal text:\n\n{text}")
    ])

    return prompt | structured_llm


# ── Semantic chunk selector (the only new piece) ──────────────────────────────

def select_chunks(full_text: str, character_budget: int = 12000) -> str:
    """
    Split the document into semantic chunks and return the most informative
    sections within the character budget.

    For grant proposals the richest content is typically:
      - Chunk 0   -> executive summary / org overview
      - Chunk 1   -> project description / activities
      - Last chunk -> budget / evaluation / closing

    Falls back to plain truncation if chunking produces nothing useful.
    """
    embeddings = LocalEmbedder()
    splitter = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=80,
    )
    chunks = splitter.create_documents([full_text])

    if not chunks:
        return full_text[:character_budget]

    n = len(chunks)
    # Deduplicated priority order: first, second, last
    priority = list(dict.fromkeys([0, 1, n - 1] if n >= 3 else list(range(n))))

    selected, total = [], 0
    for idx in priority:
        snippet = chunks[idx].page_content[:4000]   # cap each individual chunk
        if total + len(snippet) <= character_budget:
            selected.append(snippet)
            total += len(snippet)

    print(f"🔍 Selected {len(selected)}/{n} semantic chunks ({total} chars)")
    return "\n\n---NEXT SECTION---\n\n".join(selected)


# ── Main parse function ───────────────────────────────────────────────────────

def parse_proposal(file_bytes: bytes, filename: str) -> dict:
    is_pdf = filename.lower().endswith(".pdf")
    suffix = ".pdf" if is_pdf else ".txt"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # 1. Load document (same as your original)
        loader = PyPDFLoader(tmp_path) if is_pdf else TextLoader(tmp_path, encoding="utf-8")
        pages = loader.load()
        full_text = "\n".join(page.page_content for page in pages)

        # 2. Choose context: semantic chunks for long docs, raw text for short ones
        LONG_DOC_THRESHOLD = 15000  # ~10 dense pages; tune as needed
        if len(full_text) > LONG_DOC_THRESHOLD:
            context = select_chunks(full_text)
        else:
            # Short doc — pass everything directly, exactly like your original
            context = full_text

        mode_name = "Groq" if USE_GROQ else "Local Ollama"
        print(f"🧠 Extracting features using {mode_name} ({len(context)} chars)...")

        # 3. Run chain (identical to your working original)
        chain = build_extraction_chain()
        result = chain.invoke({"text": context})
        return result.model_dump()

    except Exception as e:
        print(f"❌ Extraction Error: {e}")
        return {"error": "Failed to parse document", "details": str(e)}

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)