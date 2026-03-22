"""
state/proposal_state.py

Single source of truth for all data that moves through the proposal system.
Every agent reads from and writes to this object.
Serializes cleanly to JSON for Postgres storage.
"""

from typing import TypedDict, Literal, Optional


# ── Slot definition (used in scratch flow) ────────────────────────────────────

class Slot(TypedDict):
    question:    str
    filled:      bool
    value:       Optional[str]
    ask_count:   int          # how many times we've asked — cap re-asks at 2


# ── Section result (one drafted section) ─────────────────────────────────────

class SectionResult(TypedDict):
    title:       str
    content:     str          # current/final content
    score:       int          # last scorer result (0–100)
    retries:     int          # how many rewrites were done
    flagged:     bool         # True if score still low after max retries


# ── Diff token (for frontend tracked-changes rendering) ───────────────────────

class DiffToken(TypedDict):
    type:  Literal["add", "remove", "equal"]
    text:  str


# ── Main state object ─────────────────────────────────────────────────────────

class ProposalState(TypedDict):
    # Identity
    session_id:         str
    user_id:            Optional[str]
    flow:               Literal["improve", "scratch"]

    # Inputs
    profile:            dict          # NGO profile
    grant:              dict          # selected grant

    # Analysis (populated in step 1)
    funder_vocab:       list[str]     # extracted funder phrases

    # Flow B only: slot-filling
    slots:              dict[str, Slot]

    # Flow A only: gap analysis
    analysis:           Optional[dict]   # structured gap analysis result

    # Sections
    original_sections:  dict[str, str]           # raw text before any rewrite
    sections:           dict[str, SectionResult] # current state of each section

    # Diffs: original → final per section (list of DiffTokens)
    diffs:              dict[str, list[DiffToken]]

    # Control flow
    gate: Literal[
        "none",
        "gap_review",       # Flow A: user reviews gap analysis
        "slot_filling",     # Flow B: Q&A in progress
        "slot_confirm",     # Flow B: user confirms collected slots
        "draft_review",     # Both: user reviews drafted sections
        "final_save",       # Both: user confirms and downloads
        "complete",
    ]

    # Error tracking
    retry_counts:       dict[str, int]   # section_key → retry count so far
    flagged_sections:   list[str]        # sections that failed max retries


# ── Factory ───────────────────────────────────────────────────────────────────

def new_state(
    session_id: str,
    flow: Literal["improve", "scratch"],
    profile: dict,
    grant: dict,
    user_id: Optional[str] = None,
    original_sections: dict[str, str] | None = None,
) -> ProposalState:
    """Create a fresh ProposalState for a new session."""
    return ProposalState(
        session_id=session_id,
        user_id=user_id,
        flow=flow,
        profile=profile,
        grant=grant,
        funder_vocab=[],
        slots={},
        analysis=None,
        original_sections=original_sections or {},
        sections={},
        diffs={},
        gate="none",
        retry_counts={},
        flagged_sections=[],
    )
