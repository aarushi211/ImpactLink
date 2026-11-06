"""Incrementally refresh official grant sources. Default is a read-only preview."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import psycopg
from services.grant_refresh import GrantSources, refresh_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["california", "grants_gov"], required=True)
    parser.add_argument("--limit", type=int, default=100, help="Maximum new grants per run; tracked grants are always refreshed")
    parser.add_argument("--keyword", default="", help="Federal discovery search; does not restrict refresh of tracked grants")
    parser.add_argument("--apply", action="store_true", help="Persist source updates and embeddings (otherwise preview only)")
    args = parser.parse_args()
    if not 0 <= args.limit <= 1000:
        parser.error("--limit must be between 0 and 1000")
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("DATABASE_URL is required")
    sources = GrantSources()
    model = None

    def encode(document):
        nonlocal model
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=os.getenv("SENTENCE_TRANSFORMERS_HOME"))
        return model.encode(document)

    with psycopg.connect(url, autocommit=True, connect_timeout=15, prepare_threshold=None) as conn:
        if args.source == "california":
            records = sources.california()
        else:
            existing = [row[0] for row in conn.execute("SELECT source_id FROM grants WHERE source = 'grants_gov'")]
            records = sources.federal(limit=args.limit, keyword=args.keyword, existing_ids=existing)
        report = refresh_records(conn, records, encode, new_limit=args.limit, dry_run=not args.apply)
    print(json.dumps({"source": args.source, "records_fetched": len(records), **report}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Avoid printing connection strings or source response tokens in unattended logs.
        print(f"Grant refresh failed ({type(exc).__name__}); no incomplete source batch was committed.", file=sys.stderr)
        sys.exit(1)
