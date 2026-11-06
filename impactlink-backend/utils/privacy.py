"""Layered outbound redaction. Originals are never mapped back into AI output."""

from collections import Counter
from dataclasses import dataclass
import logging
import os
import re
import traceback
import json
from contextlib import contextmanager
from contextvars import ContextVar
from utils.name_detection import person_spans

_protected_terms = ContextVar("privacy_protected_terms", default=())
_PLACEHOLDER = re.compile(r"\[REDACTED_[A-Z_]+\]")


def validate_protected_terms(terms):
    if not isinstance(terms, (list, tuple)) or len(terms) > 100:
        raise ValueError("Privacy terms must be a list of at most 100 names or phrases.")
    normalized = []
    seen = set()
    for term in terms:
        if not isinstance(term, str):
            raise ValueError("Privacy terms must be text.")
        term = " ".join(term.split())
        if not 2 <= len(term) <= 200 or _PLACEHOLDER.search(term):
            raise ValueError("Each privacy term must contain 2–200 characters and cannot contain a redaction placeholder.")
        if term.casefold() not in seen:
            seen.add(term.casefold())
            normalized.append(term)
    return tuple(normalized)


@contextmanager
def privacy_scope(terms):
    token = _protected_terms.set(validate_protected_terms(terms))
    try:
        yield
    finally:
        _protected_terms.reset(token)


def _custom_pattern(terms):
    alternatives = []
    for term in sorted(terms, key=len, reverse=True):
        # Also catch the JSON-escaped Unicode form used by some prompt builders.
        for variant in {term, json.dumps(term, ensure_ascii=True)[1:-1]}:
            phrase = r"(?:\s|\\[nrt]|\\u0020|\\u00a0)+".join(re.escape(part) for part in variant.split())
            alternatives.append((r"(?<!\w)" if term[0].isascii() and term[0].isalnum() else "") + phrase + (r"(?!\w)" if term[-1].isascii() and term[-1].isalnum() else ""))
    return re.compile("|".join(alternatives), re.IGNORECASE) if alternatives else None


@dataclass(frozen=True)
class RedactionResult:
    text: str
    counts: dict[str, int]


PATTERNS = [
    ("secret", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.DOTALL)),
    ("secret", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("secret", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("secret", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("secret", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}")),
    ("ssn", re.compile(r"(?<!\d)\d{3}[-\u2010-\u2015\u2212]\d{2}[-\u2010-\u2015\u2212]\d{4}(?!\d)")),
    ("ssn", re.compile(r"\b(?:ssn|social\s+security(?:\s+number)?)\s*[:=#]?\s*\d{3}[ -]?\d{2}[ -]?\d{4}(?!\d)", re.IGNORECASE)),
    ("phone", re.compile(r"\b(?:phone|mobile|telephone)(?:\s+number)?\s*[:=#]?\s*\d{10}(?!\d)", re.IGNORECASE)),
    ("email", re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}(?![\w.-])")),
    ("phone", re.compile(r"(?<![\w$])(?:\+1[ .-]?)?(?:\([2-9]\d{2}\)[ .-]?\d{3}[ .-]?\d{4}|[2-9]\d{2}[ .-]\d{3}[ .-]\d{4})(?:[ \t]*(?:ext\.?|x)[ \t]*\d{1,6})?(?!\d)", re.IGNORECASE)),
    ("phone", re.compile(r"(?<!\w)\+(?:\d[ .()-]?){8,14}\d(?!\d)")),
]

LABELS = {
    "email": r"(?:contact[ _-]*)?e[ _-]?mail(?:[ _-]*address)?",
    "ssn": r"ssn|social[ _-]*security(?:[ _-]*(?:number|no\.?))?",
    "tax_id": r"ein|tax[ _-]*(?:id|identification(?:[ _-]*number)?)|employer[ _-]*identification[ _-]*number",
    "financial_id": r"(?:bank[ _-]*)?account[ _-]*(?:number|no\.?|#)|routing[ _-]*(?:number|no\.?)|credit[ _-]*card(?:[ _-]*number)?|card[ _-]*number|iban",
    "secret": r"(?:[a-z]+[ _-]+)*api[ _-]*key|(?:access|refresh|api)[ _-]*token|password|client[ _-]*secret|secret[ _-]*key",
    "phone": r"(?:phone|mobile|telephone|fax)(?:[ _-]*(?:number|no\.?))?",
    "name": r"(?:full|contact|client|patient|beneficiary)[ _-]*name",
    "address": r"(?:home|residential|street)[ _-]*address",
    "date_of_birth": r"dob|date[ _-]*of[ _-]*birth|birth[ _-]*date",
}
QUOTED_LABELS = [(kind, re.compile(r"(?P<prefix>(?<!\w)[\"']?(?:" + label + r")[\"']?\s*[:=]\s*)(?P<quote>[\"'])(?P<value>(?:\\.|(?!(?P=quote))[^\\\r\n])*)(?P=quote)", re.IGNORECASE)) for kind, label in LABELS.items()]
PLAIN_LABELS = [(kind, re.compile(r"(?P<prefix>(?<!\w)[\"']?(?:" + label + r")[\"']?\s*[:=]\s*)(?P<value>[^\"'\r\n,;|}]+)", re.IGNORECASE)) for kind, label in LABELS.items()]
KEY_KINDS = {re.sub(r"[^a-z0-9]", "", key): kind for kind, keys in {
    "email": ["email", "email_address", "contact_email"],
    "ssn": ["ssn", "social_security_number"], "tax_id": ["ein", "tax_id"],
    "name": ["full_name", "contact_name", "client_name", "patient_name", "beneficiary_name"],
    "address": ["home_address", "street_address", "residential_address"],
    "date_of_birth": ["dob", "date_of_birth", "birth_date"],
    "financial_id": ["account_number", "bank_account_number", "routing_number", "credit_card_number", "iban"],
    "secret": ["api_key", "openai_api_key", "password", "access_token", "refresh_token", "api_token", "client_secret", "secret_key"],
}.items() for key in keys}


def placeholder(kind):
    return f"[REDACTED_{kind.upper()}]"


def redact_text(text, *, custom_terms=None, detect_names=True):
    if not isinstance(text, str):
        raise TypeError("Redaction requires text")
    counts = Counter()
    terms = _protected_terms.get() if custom_terms is None else validate_protected_terms(custom_terms)
    custom = _custom_pattern(terms)
    if custom:
        protected = [(item.start(), item.end()) for item in _PLACEHOLDER.finditer(text)]
        def replace_custom(match):
            if any(match.start() < end and match.end() > start for start, end in protected):
                return match.group(0)
            counts["custom"] += 1
            return placeholder("custom")
        text = custom.sub(replace_custom, text)
    for kind, pattern in PATTERNS:
        def replace(match, kind=kind):
            counts[kind] += 1
            return placeholder(kind)
        text = pattern.sub(replace, text)
    for quoted, patterns in ((True, QUOTED_LABELS), (False, PLAIN_LABELS)):
        for kind, pattern in patterns:
            def replace_label(match, kind=kind, quoted=quoted):
                value = match.group("value").strip()
                if not value or value.startswith("[REDACTED_"):
                    return match.group(0)
                counts[kind] += 1
                quote = match.group("quote") if quoted else ""
                return match.group("prefix") + quote + placeholder(kind) + quote
            text = pattern.sub(replace_label, text)
    if detect_names and text.strip():
        ignored = [(item.start(), item.end()) for item in _PLACEHOLDER.finditer(text)]
        spans = [(start, end) for start, end in person_spans(text) if not any(start < right and end > left for left, right in ignored)]
        merged = []
        for start, end in spans:
            if merged and start < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        for start, end in reversed(merged):
            text = text[:start] + placeholder("name") + text[end:]
        if merged:
            counts["name"] += len(merged)
    return RedactionResult(text, dict(counts))


def redact_values(value):
    """Redact JSON values while preserving schema/property names and operational IDs."""
    if isinstance(value, str):
        return redact_text(value).text
    if isinstance(value, (list, tuple)):
        return [redact_values(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            kind = "secret" if normalized_key.endswith("apikey") else KEY_KINDS.get(normalized_key)
            if kind and item not in (None, "") and isinstance(item, (str, int, float)):
                result[key] = placeholder(kind)
            else:
                result[key] = redact_values(item)
        return result
    return value


class PrivacyLogFilter(logging.Filter):
    def filter(self, record):
        try:
            record.msg = redact_text(record.getMessage(), detect_names=False).text
            record.args = ()
            if record.exc_info:
                error_type, _, tb = record.exc_info
                record.exc_text = redact_text("".join(traceback.format_tb(tb)) + error_type.__name__ + " (exception message omitted)\n", detect_names=False).text
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = redact_text(record.exc_text, detect_names=False).text
            if record.stack_info:
                record.stack_info = redact_text(record.stack_info, detect_names=False).text
        except Exception:
            record.msg, record.args = "Log content withheld by privacy filter", ()
            record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


def configure_privacy():
    # Raw prompt-chain inputs may be traced before they reach the model client.
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[key] = "false"
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
    handlers = list(root.handlers)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "openai", "httpx"):
        handlers.extend(logging.getLogger(name).handlers)
    for handler in set(handlers):
        if not any(isinstance(item, PrivacyLogFilter) for item in handler.filters):
            handler.addFilter(PrivacyLogFilter())
