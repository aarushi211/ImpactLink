import os
import re
import random
import tempfile
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_experimental.text_splitter import SemanticChunker
from sentence_transformers import SentenceTransformer
from utils.llm import RotatingGroq
from config import GROQ_API_KEY

# Parse keys once at module level (mirrors vector_store.py)
_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


# ── Embedder ──────────────────────────────────────────────────────────────────

class LocalEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text]).tolist()[0]


# ── Pydantic schema ───────────────────────────────────────────────────────────

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


# ── LLM prompt ────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant reviewer. Extract metadata from the NGO proposal.
If information is missing, infer from context or leave blank.
CRITICAL: Return ONLY a valid JSON object matching the requested schema."""),
    ("user", "Here is the proposal text:\n\n{text}")
])


def _get_llm() -> RotatingGroq:
    """
    Always returns a fresh RotatingGroq with a pre-selected valid key.

    with_structured_output() initialises the Groq HTTP client at chain-build
    time — before _generate() ever runs — so key rotation inside _generate
    is too late.  Passing the key explicitly at construction time ensures
    every chain invocation starts with a valid credential.
    """
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=key,
    )


# ── Semantic chunk selector ───────────────────────────────────────────────────

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
        # 1. Load document
        loader = PyPDFLoader(tmp_path) if is_pdf else TextLoader(tmp_path, encoding="utf-8")
        pages = loader.load()
        full_text = "\n".join(page.page_content for page in pages)

        # 2. Choose context: semantic chunks for long docs, raw text for short ones
        LONG_DOC_THRESHOLD = 15000  # ~10 dense pages
        if len(full_text) > LONG_DOC_THRESHOLD:
            context = select_chunks(full_text)
        else:
            context = full_text

        print(f"🧠 Extracting features using Groq ({len(context)} chars)...")

        # 3. Build chain with a fresh LLM instance each call so the Groq client
        #    is always initialised with a valid, freshly-rotated key.
        llm = _get_llm()
        chain = EXTRACTION_PROMPT | llm.with_structured_output(ProposalFeatures)
        result = chain.invoke({"text": context})

        output = result.model_dump()
        output["raw_text"] = full_text
        return output

    except Exception as e:
        print(f"❌ Extraction Error: {e}")
        return {"error": "Failed to parse document", "details": str(e)}

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)