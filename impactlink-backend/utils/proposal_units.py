import re


def text_units(content: str):
    """Stable editable spans; keep Markdown tables as complete blocks."""
    table = r"^[ \t]*\|[^\n]*\|[ \t]*\r?\n[ \t]*\|[ \t:|\-]+\|?[ \t]*(?:\r?\n[ \t]*\|[^\n]*\|[ \t]*)*"
    sentence = r"\S.*?(?:[.!?](?=\s|$)|(?=\n)|\Z)"
    return list(re.finditer(f"(?:{table})|(?:{sentence})", content, flags=re.MULTILINE | re.DOTALL))
