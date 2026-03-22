"""
agents/vocab_extractor.py

Extracts the funder's distinctive vocabulary from a grant description.
Runs once per session before any drafting.
Output is injected into every section prompt.

Why this matters: mirrors exact funder language, which is the single
highest-leverage improvement to draft quality and reviewer scores.
"""

import json
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

VOCAB_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert grant writer analyzing a funder's program description.

Your task: extract the 10–15 most distinctive phrases this funder uses to describe
their priorities, eligible activities, and expected outcomes.

These are NOT generic grant-writing terms ("measurable outcomes", "capacity building").
These are the SPECIFIC words this funder uses that reviewers will look for
in applications — phrases that, if missing, signal the applicant didn't read the RFP.

Examples of good vocab extraction:
- "riparian corridor restoration" (not just "habitat")
- "severely disadvantaged communities" (not just "low-income")
- "adaptive reuse" (not just "renovation")
- "participatory budgeting" (not just "community input")

Return ONLY a JSON array of strings. No preamble, no markdown fences.
Example: ["phrase one", "phrase two", "phrase three"]"""),
    ("user", "GRANT DESCRIPTION:\n{description}"),
])


def extract_funder_vocab(grant: dict) -> list[str]:
    """
    Extract distinctive funder vocabulary from a grant dict.

    Args:
        grant: the full grant dict (must contain a "description" key)

    Returns:
        list of 10–15 distinctive phrases as strings.
        Falls back to empty list on parse failure — never crashes the flow.
    """
    description = grant.get("description", "").strip()
    if not description:
        log.warning("vocab_extractor: grant has no description, returning empty vocab")
        return []

    chain = VOCAB_PROMPT | llm
    response = chain.invoke({"description": description})
    raw = response.content.strip()

    try:
        vocab = json.loads(raw)
        if not isinstance(vocab, list):
            raise ValueError(f"Expected list, got {type(vocab)}")
        # Sanitize: keep only non-empty strings
        return [v for v in vocab if isinstance(v, str) and v.strip()]
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("vocab_extractor: JSON parse failed — %s\nRaw output: %s", e, raw)
        return []


def vocab_to_prompt_str(vocab: list[str]) -> str:
    """Format vocab list for injection into section prompts."""
    if not vocab:
        return "No specific vocabulary extracted — use language from the grant description."
    return "\n".join(f"- {v}" for v in vocab)
