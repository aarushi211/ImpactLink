"""
agents/vocab_extractor.py
"""

import os
import json
import random
import logging
from utils.llm import RotatingGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_RAW_KEYS = os.getenv("GROQ_API_KEY", "")
GROQ_KEYS = [k.strip() for k in _RAW_KEYS.split(",") if k.strip()]


def _get_llm() -> RotatingGroq:
    from config import GROQ_API_KEY
    key = random.choice(GROQ_KEYS) if GROQ_KEYS else GROQ_API_KEY
    return RotatingGroq(model="llama-3.3-70b-versatile", temperature=0, groq_api_key=key)


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
    description = grant.get("description", "").strip()
    if not description:
        log.warning("vocab_extractor: grant has no description, returning empty vocab")
        return []

    llm      = _get_llm()
    chain    = VOCAB_PROMPT | llm
    response = chain.invoke({"description": description})
    raw      = response.content.strip()

    try:
        vocab = json.loads(raw)
        if not isinstance(vocab, list):
            raise ValueError(f"Expected list, got {type(vocab)}")
        return [v for v in vocab if isinstance(v, str) and v.strip()]
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("vocab_extractor: JSON parse failed — %s\nRaw output: %s", e, raw)
        return []


def vocab_to_prompt_str(vocab: list[str]) -> str:
    if not vocab:
        return "No specific vocabulary extracted — use language from the grant description."
    return "\n".join(f"- {v}" for v in vocab)