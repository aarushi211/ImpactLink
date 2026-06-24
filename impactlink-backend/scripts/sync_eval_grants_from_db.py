"""
scripts/sync_eval_grants_from_db.py

Export grants from PostgreSQL into Data/eval_grants_catalog.json for offline
retrieval eval. Run after load_vectors.py or whenever the DB changes.

Usage:
    cd impactlink-backend
    python scripts/sync_eval_grants_from_db.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from dotenv import load_dotenv

DATA_DIR = ROOT / "Data"
OUTPUT = DATA_DIR / "eval_grants_catalog.json"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def main() -> int:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    import psycopg

    with psycopg.connect(db_url) as conn:
        cur = conn.execute("""
            SELECT grant_id, title, agency, description, focus_areas,
                   award_floor, award_ceiling, application_url, close_date
            FROM grants
            ORDER BY grant_id
        """)
        rows = cur.fetchall()

    grants = []
    for row in rows:
        gid, title, agency, desc, focus, floor, ceiling, url, close = row
        grants.append({
            "id": str(gid),
            "grant_id": str(gid),
            "title": _clean(title),
            "agency": _clean(agency),
            "description": _clean(desc)[:2000],
            "focus_areas": _clean(focus) if focus else _clean(desc)[:300],
            "min_award_amount": int(floor or 0),
            "max_award_amount": int(ceiling or 0),
            "application_url": url or "",
            "close_date": close or "",
        })

    payload = {
        "description": "Auto-synced from PostgreSQL grants table. Regenerate with sync_eval_grants_from_db.py",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "grant_count": len(grants),
        "grants": grants,
    }

    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Synced {len(grants)} grants -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
