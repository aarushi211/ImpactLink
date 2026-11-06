"""User-recorded application requirements, drafting structure and deterministic limits."""

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApplicationSection(RequirementModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=6000)
    max_words: int | None = Field(default=None, gt=0, le=50000, strict=True)
    max_characters: int | None = Field(default=None, gt=0, le=200000, strict=True)
    required: bool = True


class ApplicationAttachment(RequirementModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    stage: Literal["loi", "full_proposal", "reporting"] = "full_proposal"
    required: bool = True
    status: Literal["not_started", "in_progress", "ready", "not_applicable"] = "not_started"
    notes: str = Field(default="", max_length=2000)


class ApplicationSpec(RequirementModel):
    stage: Literal["loi", "full_proposal", "reporting"] = "full_proposal"
    source_reference: str = Field(default="", max_length=2000)
    process_notes: str = Field(default="", max_length=6000)
    sections: list[ApplicationSection] = Field(default_factory=list, max_length=25)
    attachments: list[ApplicationAttachment] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({item.key for item in self.sections}) != len(self.sections):
            raise ValueError("Application question keys must be unique")
        if len({item.id for item in self.attachments}) != len(self.attachments):
            raise ValueError("Attachment IDs must be unique")
        return self


def spec_for(grant):
    raw = (grant or {}).get("application_spec")
    return ApplicationSpec.model_validate(raw) if raw is not None else None


def normalize_spec(raw):
    return ApplicationSpec.model_validate(raw).model_dump(mode="json")


def section_definitions(grant):
    spec = spec_for(grant)
    if spec and spec.sections:
        return [{**item.model_dump(), "instructions": item.instructions or f"Answer the funder's question: {item.title}. Use only known facts and mark information to confirm.",
                 "word_target": f"at most {item.max_words} words" if item.max_words else "a concise answer that fully addresses the question"} for item in spec.sections]
    if spec and spec.stage != "full_proposal":
        presets = {
            "loi": [("loi_summary", "Project and funding request", "Summarize the need, proposed work, requested support and funder fit. Do not invent a requested amount."),
                    ("loi_capacity", "Organization and fit", "Explain relevant experience, intended participants and fit with this funder using confirmed facts."),
                    ("loi_outcomes", "Expected outcomes and next steps", "State proposed measurable outcomes, timing and the next application step. Mark unknown commitments.")],
            "reporting": [("report_progress", "Activities and progress", "Report completed activities against the approved work plan; distinguish actual work from plans."),
                          ("report_outcomes", "Outcomes and evidence", "Report actual measured outcomes and evidence. Mark results or data not supplied as to confirm."),
                          ("report_financial", "Financial report narrative", "Explain actual spending, variances and remaining funds using supplied financial records only."),
                          ("report_changes", "Challenges and next steps", "Describe known challenges, approved changes and upcoming work. Do not invent approvals.")],
        }
        return [{"key": key, "title": title, "instructions": instructions, "word_target": "150–250 words"} for key, title, instructions in presets[spec.stage]]
    from agents.prompts import SECTIONS
    return [dict(section) for section in SECTIONS]


def length_check(content, section):
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    words, characters = len(re.findall(r"\S+", text)), len(text)
    max_words, max_chars = section.get("max_words"), section.get("max_characters")
    violations = []
    if max_words is not None and words > max_words:
        violations.append(f"{words} words exceeds the {max_words}-word limit")
    if max_chars is not None and characters > max_chars:
        violations.append(f"{characters} characters exceeds the {max_chars}-character limit")
    return {"words": words, "characters": characters, "max_words": max_words, "max_characters": max_chars,
            "within_limits": not violations, "violations": violations}


def constraint_prompt(section):
    parts = ["Answer only the requested question. Return answer text without a section heading."]
    if section.get("max_words"):
        parts.append(f"Hard maximum: {section['max_words']} whitespace-delimited words.")
    if section.get("max_characters"):
        parts.append(f"Hard maximum: {section['max_characters']} Unicode characters, including spaces, punctuation and line breaks.")
    if section.get("max_words") or section.get("max_characters"):
        parts.append("Stay comfortably under both limits; do not pad the answer. Plain text is preferred for portal fields.")
    return "\n".join(parts)


def section_for(grant, key):
    return next((item for item in section_definitions(grant) if item["key"] == key), {})


def annotate_sections(sections, grant, *, order=False):
    definitions = {item["key"]: item for item in section_definitions(grant)}
    keys = [key for key in definitions if key in sections] + [key for key in sections if key not in definitions] if order else list(sections)
    result = {}
    for key in keys:
        raw = sections[key]
        item = {"content": raw} if isinstance(raw, str) else dict(raw)
        definition = definitions.get(key, {})
        if definition.get("title"):
            item["title"] = definition["title"]
        check = length_check(item.get("content", ""), definition)
        result[key] = {**item, "limits": check, "flagged": bool(item.get("flagged") or not check["within_limits"])}
    return result


def validate_application(sections, grant):
    spec = spec_for(grant)
    checks = annotate_sections(sections, grant)
    expected = section_definitions(grant) if spec and (spec.sections or spec.stage != "full_proposal") else []
    missing = [item["key"] for item in expected if item.get("required", True) and not str((sections.get(item["key"]) or {}).get("content", "") if isinstance(sections.get(item["key"]), dict) else sections.get(item["key"], "")).strip()]
    over = [key for key, item in checks.items() if not item["limits"]["within_limits"]]
    pending = [item.id for item in (spec.attachments if spec else []) if item.stage == spec.stage and item.required and item.status != "ready"]
    return {"can_finalize_text": not missing and not over, "missing_sections": missing, "over_limit_sections": over,
            "pending_attachments": pending, "submission_readiness": "not_verified",
            "sections": {key: item["limits"] for key, item in checks.items()}}


def validate_review_input(state, user_input):
    """Reject over-limit final text before resuming a checkpoint (preserve interrupt)."""
    if state.get("gate") not in {"draft_review", "final_save"}:
        return
    sections = {key: dict(value) if isinstance(value, dict) else {"content": value} for key, value in state.get("sections", {}).items()}
    edits = user_input.get("sections", {})
    if not isinstance(edits, dict) or any(not isinstance(text, str) for text in edits.values()):
        raise ValueError("Application requirements: section edits must be text")
    for key, text in edits.items():
        if key in sections:
            sections[key]["content"] = text
    report = validate_application(sections, state.get("grant", {}))
    if not report["can_finalize_text"]:
        raise ValueError("Application requirements: fix missing or over-limit answers before confirming. Sections: " + ", ".join(report["missing_sections"] + report["over_limit_sections"]))


def merge_checklist(grant, user_input):
    statuses = user_input.get("attachment_statuses")
    if statuses is None:
        return grant
    spec = spec_for(grant)
    if not spec or not isinstance(statuses, dict) or set(statuses) - {item.id for item in spec.attachments}:
        raise ValueError("Application requirements: invalid attachment checklist")
    for item in spec.attachments:
        if item.id in statuses:
            if statuses[item.id] not in {"not_started", "in_progress", "ready", "not_applicable"}:
                raise ValueError("Application requirements: invalid attachment status")
            item.status = statuses[item.id]
    return {**grant, "application_spec": spec.model_dump(mode="json")}
