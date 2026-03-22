"""
utils/diff.py

Word-level diff between two texts.
Returns structured tokens — NOT a formatted string.
The frontend uses these to render tracked changes (green adds, red removes).

Uses Python's difflib — deterministic, fast, no LLM call.
"""

import difflib
from state.proposal_state import DiffToken


def word_diff(old_text: str, new_text: str) -> list[DiffToken]:
    """
    Compare old_text and new_text at the word level.

    Returns a list of DiffTokens:
        {"type": "equal",  "text": "unchanged words"}
        {"type": "remove", "text": "deleted words"}
        {"type": "add",    "text": "inserted words"}

    A "replace" opcode becomes one "remove" token followed by one "add" token
    so the frontend always has a flat list of three token types to render.

    Usage:
        tokens = word_diff(original_section, rewritten_section)
        # pass tokens to frontend as JSON
    """
    old_words = old_text.split()
    new_words = new_text.split()

    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    result: list[DiffToken] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.append({
                "type": "equal",
                "text": " ".join(old_words[i1:i2]),
            })
        elif tag == "replace":
            # Split into remove + add so frontend logic stays simple.
            result.append({
                "type": "remove",
                "text": " ".join(old_words[i1:i2]),
            })
            result.append({
                "type": "add",
                "text": " ".join(new_words[j1:j2]),
            })
        elif tag == "delete":
            result.append({
                "type": "remove",
                "text": " ".join(old_words[i1:i2]),
            })
        elif tag == "insert":
            result.append({
                "type": "add",
                "text": " ".join(new_words[j1:j2]),
            })

    return result


def diff_sections(
    original: dict[str, str],
    revised:  dict[str, str],
) -> dict[str, list[DiffToken]]:
    """
    Diff a full set of sections.

    original: {section_key: original_text, ...}
    revised:  {section_key: revised_text, ...}

    Returns: {section_key: [DiffToken, ...], ...}

    Only diffs sections that exist in both dicts.
    Sections present in revised but not original are returned as all-"add".
    """
    result = {}
    all_keys = set(original) | set(revised)

    for key in all_keys:
        old = original.get(key, "")
        new = revised.get(key, "")
        result[key] = word_diff(old, new)

    return result
