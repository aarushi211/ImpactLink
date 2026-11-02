import os
import re
import tempfile
from io import BytesIO
import logging
from typing import List, Optional
from docx import Document
from pydantic import BaseModel, Field
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_experimental.text_splitter import SemanticChunker
from sentence_transformers import SentenceTransformer
from utils.llm import get_chat_model

log = logging.getLogger(__name__)


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


def _extract_docx_text(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    sections = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(cells):
                sections.append(" | ".join(cells))
    return "\n".join(sections)


def _get_llm():
    return get_chat_model()


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

    log.info("Selected %d/%d semantic chunks (%d chars)", len(selected), n, total)
    return "\n\n---NEXT SECTION---\n\n".join(selected)


# ── Main parse function ───────────────────────────────────────────────────────

def parse_proposal(file_bytes: bytes, filename: str) -> dict:
    is_pdf = filename.lower().endswith(".pdf")
    is_docx = filename.lower().endswith(".docx")
    suffix = ".pdf" if is_pdf else ".txt"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        if is_pdf:
            pages = PyPDFLoader(tmp_path).load()
            full_text = "\n".join(page.page_content for page in pages)
        elif is_docx:
            full_text = _extract_docx_text(file_bytes)
        else:
            pages = TextLoader(tmp_path, encoding="utf-8").load()
            full_text = "\n".join(page.page_content for page in pages)

        if not full_text.strip():
            raise ValueError("The uploaded document contains no extractable text.")

        # 2. Choose context: semantic chunks for long docs, raw text for short ones
        LONG_DOC_THRESHOLD = 15000  # ~10 dense pages
        if len(full_text) > LONG_DOC_THRESHOLD:
            context = select_chunks(full_text)
        else:
            context = full_text

        log.info("Extracting proposal features using OpenAI (%d chars)", len(context))

        # 3. Build chain with a fresh LLM instance for this extraction call.
        llm = _get_llm()
        chain = EXTRACTION_PROMPT | llm.with_structured_output(ProposalFeatures)
        result = chain.invoke({"text": context})

        output = result.model_dump()
        output["raw_text"] = full_text
        return output

    except Exception as e:
        log.exception("Proposal extraction failed")
        return {"error": "Failed to parse document", "details": str(e)}

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)