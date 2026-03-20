"""
graphql_server.py
GraphQL API for NGO collaboration matching.

Install:
    pip install strawberry-graphql[fastapi] uvicorn

Run:
    uvicorn graphql_server:app --reload --port 8001

Playground:
    http://localhost:8001/graphql
"""

import json
import os
from pathlib import Path
from typing import Optional
import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI

# ── Load data ─────────────────────────────────────────────────────────────────

DATA_DIR   = Path(__file__).parent / "data"
NGOS_FILE  = DATA_DIR / "dummy_ngos.json"
GRANTS_FILE = DATA_DIR / "grants_ca_gov_details.json"

_ngos: list[dict]   = json.loads(NGOS_FILE.read_text())
_grants: list[dict] = [
    g for g in json.loads(GRANTS_FILE.read_text())
    if not g.get("error") and g.get("grant_id")
]
_grant_map: dict[str, dict] = {g["grant_id"]: g for g in _grants}


# ── Strawberry types ──────────────────────────────────────────────────────────

@strawberry.type
class Organization:
    id: str
    name: str
    org_type: str
    location: str
    mission: str
    focus_areas: list[str]
    saved_grant_ids: list[str]
    applied_grant_ids: list[str]
    contact_email: str
    website: str
    size: str
    founded_year: int


@strawberry.type
class CollaboratorMatch:
    organization: Organization
    match_score: float
    match_reasons: list[str]
    shared_grants: list[str]
    shared_focus_areas: list[str]


@strawberry.type
class CollaborationResult:
    grant_id: str
    grant_title: str
    matches: list[CollaboratorMatch]


# ── Helpers ───────────────────────────────────────────────────────────────────

def dict_to_org(d: dict) -> Organization:
    return Organization(
        id=d["id"],
        name=d["name"],
        org_type=d["org_type"],
        location=d["location"],
        mission=d["mission"],
        focus_areas=d["focus_areas"],
        saved_grant_ids=d["saved_grant_ids"],
        applied_grant_ids=d["applied_grant_ids"],
        contact_email=d["contact_email"],
        website=d["website"],
        size=d["size"],
        founded_year=d["founded_year"],
    )


def score_ngo(
    ngo: dict,
    grant_ids: set[str],
    focus_areas: set[str],
    location: Optional[str],
) -> tuple[float, list[str], list[str], list[str]]:
    """
    Returns (score, reasons, shared_grants, shared_focus_areas).

    Scoring weights:
      - Saved the same grant:   +0.35 each (max 1.0)
      - Applied same grant:     +0.45 each (max 1.0)
      - Overlapping focus area: +0.20 each (max 1.0)
      - Same location:          +0.25 flat
    """
    score = 0.0
    reasons = []

    ngo_saved   = set(ngo["saved_grant_ids"])
    ngo_applied = set(ngo["applied_grant_ids"])
    ngo_focus   = set(ngo["focus_areas"])

    shared_saved   = grant_ids & ngo_saved
    shared_applied = grant_ids & ngo_applied
    shared_focus   = focus_areas & ngo_focus

    shared_grants = list(shared_saved | shared_applied)

    if shared_saved:
        pts = min(len(shared_saved) * 0.35, 1.0)
        score += pts
        reasons.append(f"Saved {len(shared_saved)} of the same grant(s)")

    if shared_applied:
        pts = min(len(shared_applied) * 0.45, 1.0)
        score += pts
        reasons.append(f"Previously applied for {len(shared_applied)} matching grant(s)")

    if shared_focus:
        pts = min(len(shared_focus) * 0.20, 1.0)
        score += pts
        reasons.append(f"Shares {len(shared_focus)} focus area(s): {', '.join(shared_focus)}")

    if location and ngo["location"].lower() == location.lower():
        score += 0.25
        reasons.append(f"Same location: {location}")

    # Normalise to 0–1
    max_possible = 1.0 + 1.0 + 1.0 + 0.25
    normalised = round(min(score / max_possible, 1.0), 3)

    return normalised, reasons, shared_grants, list(shared_focus)


# ── Resolvers ─────────────────────────────────────────────────────────────────

@strawberry.type
class Query:

    @strawberry.field
    def organizations(self) -> list[Organization]:
        return [dict_to_org(n) for n in _ngos]

    @strawberry.field
    def organization(self, id: str) -> Optional[Organization]:
        match = next((n for n in _ngos if n["id"] == id), None)
        return dict_to_org(match) if match else None

    @strawberry.field
    def organizations_by_focus(self, focus_areas: list[str]) -> list[Organization]:
        target = set(focus_areas)
        return [
            dict_to_org(n) for n in _ngos
            if target & set(n["focus_areas"])
        ]

    @strawberry.field
    def organizations_by_grant(self, grant_id: str) -> list[Organization]:
        return [
            dict_to_org(n) for n in _ngos
            if grant_id in n["saved_grant_ids"] or grant_id in n["applied_grant_ids"]
        ]

    @strawberry.field
    def find_collaborators(
        self,
        grant_ids: list[str],
        focus_areas: Optional[list[str]] = None,
        location: Optional[str] = None,
        min_score: Optional[float] = 0.1,
    ) -> list[CollaborationResult]:
        """
        Core query. For each grant in grant_ids, find NGOs that:
          1. Saved or applied for that grant (or similar grants)
          2. Share focus areas
          3. Optionally match on location
        Returns results grouped by grant, sorted by match score.
        """
        target_grants  = set(grant_ids)
        target_focus   = set(focus_areas or [])
        threshold      = min_score if min_score is not None else 0.1

        results = []

        for grant_id in grant_ids:
            grant = _grant_map.get(grant_id)
            grant_title = grant["title"] if grant else grant_id

            # Also pull focus areas from the grant itself if not provided
            grant_focus = set()
            if grant:
                cats = grant.get("funding_activity_categories") or []
                for c in cats:
                    grant_focus.add(c)

            combined_focus = target_focus | grant_focus

            matches = []
            for ngo in _ngos:
                score, reasons, shared_grants, shared_focus = score_ngo(
                    ngo,
                    target_grants,
                    combined_focus,
                    location,
                )
                if score >= threshold:
                    matches.append(CollaboratorMatch(
                        organization=dict_to_org(ngo),
                        match_score=score,
                        match_reasons=reasons,
                        shared_grants=shared_grants,
                        shared_focus_areas=shared_focus,
                    ))

            # Sort by score descending
            matches.sort(key=lambda m: m.match_score, reverse=True)

            results.append(CollaborationResult(
                grant_id=grant_id,
                grant_title=grant_title,
                matches=matches,
            ))

        return results


# ── App ───────────────────────────────────────────────────────────────────────

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="NGO Collaboration GraphQL API")
app.include_router(graphql_app, prefix="/graphql")


@app.get("/")
def root():
    return {
        "message": "NGO Collaboration API",
        "graphql": "/graphql",
        "docs": "/docs",
    }