"""
load_vectors.py

Run this ONCE (or whenever the grants data changes) to embed all grants
and store them in PostgreSQL using the pgvector extension.

Usage:
    python load_vectors.py

Requires:
    - DATABASE_URL env var pointing to your Postgres instance
    - pgvector extension enabled:  CREATE EXTENSION IF NOT EXISTS vector;
"""

import os
import json
import re
import logging
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import psycopg

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

GRANTS_FILE = "data/grants_enriched.json"
MODEL_NAME  = "all-MiniLM-L6-v2"
DB_URL      = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is required.")


def clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text or '').strip()


def make_id(grant: dict, index: int) -> str:
    if grant.get("grant_id"):
        return str(grant["grant_id"])
    title = grant.get("title", "")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    return f"ca-{index}-{slug}" if slug else f"ca-{index}"


def grant_to_text(grant: dict) -> str:
    eligibility = grant.get('eligibility', [])
    if isinstance(eligibility, list):
        eligibility = ', '.join(eligibility)
    categories = grant.get('funding_activity_categories', [])
    if isinstance(categories, list):
        categories = ', '.join(categories)
    return f"""
    Title: {grant.get('title', '')}
    Funder: {grant.get('funder_name', '')}
    Agency: {grant.get('top_agency', '')}
    Description: {clean_html(grant.get('description', ''))}
    Categories: {categories}
    Eligibility: {eligibility}
    """.strip()


def _parse_amount(val) -> int:
    try:
        return int(str(val).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0


def load_grants_to_pgvector():
    with open(GRANTS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    grants = raw.get("grants", raw) if isinstance(raw, dict) else raw
    valid_grants = [g for g in grants if not g.get("error")]
    skipped = len(grants) - len(valid_grants)
    if skipped:
        log.info("Skipping %d errored records", skipped)

    log.info("Loading embedding model: %s", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)

    with psycopg.connect(DB_URL, autocommit=True) as conn:
        # Enable pgvector extension
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # Drop and recreate table cleanly (safe since load_vectors is a one-time seed script)
        conn.execute("DROP TABLE IF EXISTS grants")
        log.info("Dropped existing grants table (rebuilding fresh)")

        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grants (
                grant_id        TEXT PRIMARY KEY,
                title           TEXT,
                agency          TEXT,
                award_floor     BIGINT,
                award_ceiling   BIGINT,
                application_url TEXT,
                portal_url      TEXT,
                close_date      TEXT,
                focus_areas     TEXT,
                contact_email   TEXT,
                contact_name    TEXT,
                funding_method  TEXT,
                estimated_total TEXT,
                description     TEXT,
                eligibility     JSONB,
                document        TEXT,
                embedding       vector(384)
            )
        """)

        # HNSW index for fast cosine ANN — created once, ignored if exists
        conn.execute("""
            CREATE INDEX IF NOT EXISTS grants_embedding_idx
            ON grants USING hnsw (embedding vector_cosine_ops)
        """)

        log.info("Embedding and upserting %d grants …", len(valid_grants))
        seen_ids: set = set()
        inserted = 0

        for i, grant in enumerate(valid_grants):
            grant_id = make_id(grant, i)
            if grant_id in seen_ids:
                grant_id = f"{grant_id}-{i}"
            seen_ids.add(grant_id)

            doc        = grant_to_text(grant)
            embedding  = model.encode(doc).tolist()
            vec_str    = "[" + ",".join(str(v) for v in embedding) + "]"

            categories = grant.get("funding_activity_categories", [])
            if isinstance(categories, list):
                categories = ", ".join(categories)

            apply_links     = grant.get("apply_links") or []
            application_url = apply_links[-1] if apply_links else grant.get("grants_gov_url", "")

            eligibility = grant.get("eligibility", [])
            if not isinstance(eligibility, list):
                eligibility = [eligibility] if eligibility else []

            conn.execute("""
                INSERT INTO grants (
                    grant_id, title, agency, award_floor, award_ceiling,
                    application_url, portal_url, close_date, focus_areas,
                    contact_email, contact_name, funding_method, estimated_total,
                    description, eligibility, document, embedding
                ) VALUES (
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s::vector
                )
                ON CONFLICT (grant_id) DO UPDATE SET
                    title           = EXCLUDED.title,
                    agency          = EXCLUDED.agency,
                    award_floor     = EXCLUDED.award_floor,
                    award_ceiling   = EXCLUDED.award_ceiling,
                    application_url = EXCLUDED.application_url,
                    portal_url      = EXCLUDED.portal_url,
                    close_date      = EXCLUDED.close_date,
                    focus_areas     = EXCLUDED.focus_areas,
                    contact_email   = EXCLUDED.contact_email,
                    contact_name    = EXCLUDED.contact_name,
                    funding_method  = EXCLUDED.funding_method,
                    estimated_total = EXCLUDED.estimated_total,
                    description     = EXCLUDED.description,
                    eligibility     = EXCLUDED.eligibility,
                    document        = EXCLUDED.document,
                    embedding       = EXCLUDED.embedding
            """, (
                grant_id,
                grant.get("title", ""),
                grant.get("funder_name", ""),
                _parse_amount(grant.get("min_award_amount")),
                _parse_amount(grant.get("max_award_amount")),
                application_url,
                grant.get("grants_gov_url", ""),
                grant.get("close_date") or "Ongoing",
                categories,
                grant.get("contact_email") or "",
                grant.get("contact_name") or "",
                grant.get("funding_method") or "",
                str(grant.get("estimated_total_funding") or ""),
                clean_html(grant.get("description", "")),
                json.dumps(eligibility),
                doc,
                vec_str,
            ))
            inserted += 1
            if inserted % 50 == 0:
                log.info("  … %d / %d", inserted, len(valid_grants))

    log.info("✅  Loaded %d grants into PostgreSQL (pgvector)", inserted)
    log.info("   Table: grants  |  Index: hnsw cosine  |  Dims: 384")


if __name__ == "__main__":
    load_grants_to_pgvector()