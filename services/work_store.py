"""
services/work_store.py
Per-NGO persistent store for saved work.
File: data/work_store.json

Schema
──────
DraftItem:
  id, ngo_id, title, grant_title, grant_id, agency,
  proposal_context  ← raw proposal dict (org name, mission, activities, etc.)
  matches_id        ← list of matched grant_ids at save time
  budget_id         ← id of linked BudgetItem (set when budget is saved for this draft)
  sections, section_order, word_count, created_at, updated_at

BuildItem:
  id, ngo_id, title, org_name, grant_title,
  proposal_context, matches_id, budget_id,
  sections, section_order, answers, word_count, created_at, updated_at

BudgetItem:
  id, ngo_id, title, grant_title, max_budget,
  proposal_id   ← id of parent draft/build this budget belongs to
  items, total_requested, locality_explanation, created_at, updated_at
"""

import json, uuid
from pathlib import Path
from datetime import datetime

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "work_store.json"


# ── internal ────────────────────────────────────────────────────

def _load() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {}

def _save(db: dict):
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(db, indent=2))

def _uid() -> str:
    return uuid.uuid4().hex[:12]

def _now() -> str:
    return datetime.now().isoformat()

def _bucket(db: dict, ngo_id: str) -> dict:
    if ngo_id not in db:
        db[ngo_id] = {"drafts": [], "builds": [], "budgets": []}
    return db[ngo_id]

def _word_count(sections: dict) -> int:
    total = 0
    for sec in sections.values():
        content = sec.get("content", "") if isinstance(sec, dict) else ""
        total += len(content.split())
    return total


# ── DRAFTS ──────────────────────────────────────────────────────

def save_draft(ngo_id: str, payload: dict) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)
    now = _now()
    item = {
        "id":               _uid(),
        "ngo_id":           ngo_id,
        "title":            payload.get("title") or payload.get("grant_title") or "Untitled Draft",
        "grant_title":      payload.get("grant_title", ""),
        "grant_id":         payload.get("grant_id", ""),
        "agency":           payload.get("agency", ""),
        # Full proposal context so Draft/Budget pages can reload it
        "proposal_context": payload.get("proposal_context") or {},
        # Grant IDs that were matched at save time
        "matches_id":       payload.get("matches_id") or [],
        # Will be populated when a budget is saved for this draft
        "budget_id":        payload.get("budget_id") or None,
        "sections":         payload.get("sections", {}),
        "section_order":    payload.get("section_order", []),
        "word_count":       _word_count(payload.get("sections", {})),
        "created_at":       now,
        "updated_at":       now,
    }
    bkt["drafts"].insert(0, item)
    bkt["drafts"] = bkt["drafts"][:20]
    _save(db)
    return item

def update_draft(ngo_id: str, draft_id: str, sections: dict,
                 budget_id: str = None) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)
    for item in bkt["drafts"]:
        if item["id"] == draft_id:
            item["sections"]   = sections
            item["word_count"] = _word_count(sections)
            item["updated_at"] = _now()
            if budget_id is not None:
                item["budget_id"] = budget_id
            _save(db)
            return item
    raise ValueError(f"Draft {draft_id} not found.")

def list_drafts(ngo_id: str) -> list:
    return _bucket(_load(), ngo_id).get("drafts", [])

def get_draft(ngo_id: str, draft_id: str) -> dict:
    for d in list_drafts(ngo_id):
        if d["id"] == draft_id:
            return d
    raise ValueError(f"Draft {draft_id} not found.")

def delete_draft(ngo_id: str, draft_id: str):
    db  = _load()
    bkt = _bucket(db, ngo_id)
    bkt["drafts"] = [d for d in bkt["drafts"] if d["id"] != draft_id]
    _save(db)


# ── BUILDS ──────────────────────────────────────────────────────

def save_build(ngo_id: str, payload: dict) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)
    now = _now()
    item = {
        "id":               _uid(),
        "ngo_id":           ngo_id,
        "title":            payload.get("title") or payload.get("grant_title") or "Built Proposal",
        "org_name":         payload.get("org_name", ""),
        "grant_title":      payload.get("grant_title", ""),
        "proposal_context": payload.get("proposal_context") or {},
        "matches_id":       payload.get("matches_id") or [],
        "budget_id":        payload.get("budget_id") or None,
        "sections":         payload.get("sections", {}),
        "section_order":    payload.get("section_order", []),
        "answers":          payload.get("answers", []),
        "word_count":       _word_count(payload.get("sections", {})),
        "created_at":       now,
        "updated_at":       now,
    }
    bkt["builds"].insert(0, item)
    bkt["builds"] = bkt["builds"][:20]
    _save(db)
    return item

def update_build(ngo_id: str, build_id: str, sections: dict,
                 budget_id: str = None) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)
    for item in bkt["builds"]:
        if item["id"] == build_id:
            item["sections"]   = sections
            item["word_count"] = _word_count(sections)
            item["updated_at"] = _now()
            if budget_id is not None:
                item["budget_id"] = budget_id
            _save(db)
            return item
    raise ValueError(f"Build {build_id} not found.")

def list_builds(ngo_id: str) -> list:
    return _bucket(_load(), ngo_id).get("builds", [])

def get_build(ngo_id: str, build_id: str) -> dict:
    for b in list_builds(ngo_id):
        if b["id"] == build_id:
            return b
    raise ValueError(f"Build {build_id} not found.")

def delete_build(ngo_id: str, build_id: str):
    db  = _load()
    bkt = _bucket(db, ngo_id)
    bkt["builds"] = [b for b in bkt["builds"] if b["id"] != build_id]
    _save(db)


# ── BUDGETS ─────────────────────────────────────────────────────

def save_budget(ngo_id: str, payload: dict) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)
    now = _now()
    item = {
        "id":                   _uid(),
        "ngo_id":               ngo_id,
        "title":                payload.get("title") or payload.get("grant_title") or "Budget",
        "grant_title":          payload.get("grant_title", ""),
        "grant_id":             payload.get("grant_id", ""),
        "max_budget":           payload.get("max_budget", 0),
        # Link back to the draft/build this budget was generated for
        "proposal_id":          payload.get("proposal_id") or None,
        "items":                payload.get("items", []),
        "total_requested":      payload.get("total_requested", 0),
        "locality_explanation": payload.get("locality_explanation", ""),
        "created_at":           now,
        "updated_at":           now,
    }
    bkt["budgets"].insert(0, item)
    bkt["budgets"] = bkt["budgets"][:20]
    _save(db)

    # Back-link: update parent draft/build with this budget_id
    proposal_id = payload.get("proposal_id")
    if proposal_id:
        for d in bkt.get("drafts", []):
            if d["id"] == proposal_id:
                d["budget_id"]  = item["id"]
                d["updated_at"] = now
        for b in bkt.get("builds", []):
            if b["id"] == proposal_id:
                b["budget_id"]  = item["id"]
                b["updated_at"] = now
        _save(db)

    return item

def list_budgets(ngo_id: str) -> list:
    return _bucket(_load(), ngo_id).get("budgets", [])

def get_budget(ngo_id: str, budget_id: str) -> dict:
    for b in list_budgets(ngo_id):
        if b["id"] == budget_id:
            return b
    raise ValueError(f"Budget {budget_id} not found.")

def delete_budget(ngo_id: str, budget_id: str):
    db  = _load()
    bkt = _bucket(db, ngo_id)
    bkt["budgets"] = [b for b in bkt["budgets"] if b["id"] != budget_id]
    _save(db)


# ── SUMMARY ─────────────────────────────────────────────────────

def get_summary(ngo_id: str) -> dict:
    db  = _load()
    bkt = _bucket(db, ngo_id)

    def recent(items, n=3):
        return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)[:n]

    # All proposals = drafts + builds merged, newest first
    all_proposals = sorted(
        [{"_type": "draft",  **d} for d in bkt.get("drafts", [])] +
        [{"_type": "build",  **b} for b in bkt.get("builds", [])],
        key=lambda x: x.get("updated_at", ""), reverse=True,
    )

    return {
        "drafts_count":    len(bkt.get("drafts",  [])),
        "builds_count":    len(bkt.get("builds",  [])),
        "budgets_count":   len(bkt.get("budgets", [])),
        "recent_drafts":   recent(bkt.get("drafts",  [])),
        "recent_builds":   recent(bkt.get("builds",  [])),
        "recent_budgets":  recent(bkt.get("budgets", [])),
        "all_proposals":   all_proposals,   # for Draft + Budget page selectors
    }