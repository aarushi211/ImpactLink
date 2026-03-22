"""
agents/slot_extractor.py

Flow B (scratch build): structured slot extraction from free-text answers.

After each user answer, this agent maps the answer to the slot schema.
Only confidently filled slots are returned — ambiguous answers trigger re-ask.

Slot loop logic (in scratch_flow.py):
1. Find next unfilled slot → send question to user
2. User answers → call extract_slots()
3. Update state with filled slots (may fill multiple at once)
4. Repeat until all slots filled
5. Human gate: slot_confirm
6. Draft
"""

import json
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from state.proposal_state import Slot

load_dotenv()
log = logging.getLogger(__name__)

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# ── Slot definitions ──────────────────────────────────────────────────────────
# The canonical list of slots the scratch flow must fill before drafting.
# order determines question sequence.

SLOT_DEFINITIONS: list[Slot] = [
    {
        "key":       "org_name",
        "question":  "What is your organization's full legal name?",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "mission",
        "question":  "In one sentence, what is your organization's mission?",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "problem",
        "question":  "What specific problem does this project address, and where does it exist?",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "activities",
        "question":  "What are the 3–5 main activities your project will carry out? Be specific — include what, how often, and who leads each.",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "beneficiaries",
        "question":  "Who will directly benefit from this project, and how many people? Include demographics and how you will reach them.",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "geography",
        "question":  "What specific geographic area does this project serve? (city, county, zip codes, or region)",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "budget_total",
        "question":  "What is your total project budget, and what are the main cost categories? (e.g. staff 60%, materials 20%, travel 10%)",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "kpis",
        "question":  "What are 3–5 measurable outcomes you will track? Be specific: include target numbers and timelines.",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "sustainability",
        "question":  "How will this project continue after the grant ends? Name specific funding sources or strategies.",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
    {
        "key":       "org_capacity",
        "question":  "What makes your organization uniquely qualified for this project? Mention past programs with outcomes, team expertise, and key partnerships.",
        "filled":    False,
        "value":     None,
        "ask_count": 0,
    },
]

MAX_ASK_COUNT = 2   # re-ask at most twice before flagging

# ── Extraction prompt ─────────────────────────────────────────────────────────

EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are extracting structured data from a user's free-text answer.

Your task: map the answer to one or more slot keys from the provided list.
Only fill a slot if the answer clearly and confidently addresses it.
If the answer is too vague, short, or off-topic for a slot — leave it out.

Return ONLY a JSON object where keys are slot names and values are the extracted content.
If nothing was answered confidently, return an empty object: {{}}
No preamble, no markdown fences, no explanation."""),
    ("user", """SLOTS TO FILL (unfilled only):
{unfilled_slots}

ALREADY FILLED (do not re-extract these):
{filled_slots}

USER'S ANSWER:
{answer}

Extract now:"""),
])


# ── Public API ────────────────────────────────────────────────────────────────

def initial_slots() -> dict[str, Slot]:
    """Return a fresh slots dict keyed by slot key."""
    return {s["key"]: dict(s) for s in SLOT_DEFINITIONS}


def next_question(slots: dict[str, Slot]) -> tuple[str, str] | None:
    """
    Find the next unfilled slot and return (slot_key, question).
    Returns None if all slots are filled.

    Respects the order defined in SLOT_DEFINITIONS.
    """
    for slot_def in SLOT_DEFINITIONS:
        key = slot_def["key"]
        slot = slots.get(key, {})
        if not slot.get("filled"):
            return key, slot.get("question", slot_def["question"])
    return None


def extract_slots(
    answer:       str,
    current_slots: dict[str, Slot],
) -> dict[str, str]:
    """
    Extract slot values from a user's free-text answer.

    Args:
        answer:        the user's raw answer
        current_slots: current slot state (to know what's filled/unfilled)

    Returns:
        dict of {slot_key: extracted_value} for confidently filled slots.
        Empty dict if nothing was confidently answered.
        Never modifies current_slots — caller applies the updates.
    """
    unfilled = {k: v["question"] for k, v in current_slots.items() if not v["filled"]}
    filled   = {k: v["value"]    for k, v in current_slots.items() if v["filled"]}

    if not unfilled:
        return {}

    unfilled_str = "\n".join(f"- {k}: {q}" for k, q in unfilled.items())
    filled_str   = "\n".join(f"- {k}: {v}" for k, v in filled.items()) or "None yet."

    chain = EXTRACT_PROMPT | llm
    response = chain.invoke({
        "unfilled_slots": unfilled_str,
        "filled_slots":   filled_str,
        "answer":         answer,
    })

    raw = response.content.strip()
    try:
        extracted = json.loads(raw)
        if not isinstance(extracted, dict):
            raise ValueError(f"Expected dict, got {type(extracted)}")
        # Only keep keys that are actually valid unfilled slots
        return {k: str(v) for k, v in extracted.items()
                if k in unfilled and v and str(v).strip()}
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("slot_extractor: parse failed — %s\nRaw: %s", e, raw)
        return {}


def apply_extractions(
    slots:      dict[str, Slot],
    extracted:  dict[str, str],
    target_key: str,
) -> dict[str, Slot]:
    """
    Apply extracted values to the slots dict.
    Increments ask_count for the target slot regardless of whether it was filled.

    Args:
        slots:      current slots dict
        extracted:  dict of {slot_key: value} from extract_slots()
        target_key: the slot key that was just asked

    Returns:
        Updated slots dict (new copy — does not mutate input).
    """
    updated = {k: dict(v) for k, v in slots.items()}  # shallow copy

    # Increment ask count for the slot we just asked
    if target_key in updated:
        updated[target_key]["ask_count"] = updated[target_key].get("ask_count", 0) + 1

    # Apply all extracted values
    for key, value in extracted.items():
        if key in updated:
            updated[key]["value"]  = value
            updated[key]["filled"] = True

    return updated


def is_slot_exhausted(slot: Slot) -> bool:
    """
    Returns True if we've asked this slot MAX_ASK_COUNT times without filling it.
    The flow should skip this slot and flag it for the human confirmation gate.
    """
    return (not slot.get("filled")) and (slot.get("ask_count", 0) >= MAX_ASK_COUNT)


def slots_to_profile(slots: dict[str, Slot]) -> dict:
    """
    Convert filled slots to an org profile dict compatible with draft_agent.py.
    Used after slot_confirm gate to build the proposal input.
    """
    return {
        "organization_name":  _val(slots, "org_name"),
        "mission":            _val(slots, "mission"),
        "problem_statement":  _val(slots, "problem"),
        "key_activities":     [_val(slots, "activities")],
        "target_beneficiaries": [_val(slots, "beneficiaries")],
        "geographic_focus":   [_val(slots, "geography")],
        "total_budget":       _val(slots, "budget_total"),
        "kpis":               [_val(slots, "kpis")],
        "sustainability":      _val(slots, "sustainability"),
        "org_capacity":       _val(slots, "org_capacity"),
    }


def _val(slots: dict[str, Slot], key: str) -> str:
    slot = slots.get(key, {})
    return slot.get("value") or ""
