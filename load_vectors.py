"""
load_vectors.py
Run this ONCE to embed all grants and store them in ChromaDB.
"""

import json
import re
import chromadb
from sentence_transformers import SentenceTransformer

GRANTS_FILE = "data/grants_enriched.json"
CHROMA_PATH = "./chroma_db"
COLLECTION  = "grants"
MODEL_NAME  = "all-MiniLM-L6-v2"


def clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text or '').strip()


def make_id(grant: dict, index: int) -> str:
    """Return grant_id if present, otherwise generate a stable slug-based ID."""
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


def load_grants_to_vectordb():
    with open(GRANTS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    grants = raw.get("grants", raw) if isinstance(raw, dict) else raw

    # Skip records that failed to scrape (have an 'error' key and no description)
    valid_grants = [g for g in grants if not g.get("error")]
    skipped = len(grants) - len(valid_grants)
    if skipped:
        print(f"Skipping {skipped} failed/errored records")

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        client.delete_collection(COLLECTION)
        print(f"Cleared existing '{COLLECTION}' collection")
    except:
        pass

    collection = client.create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    ids, embeddings, metadatas, documents = [], [], [], []
    seen_ids = set()

    for i, grant in enumerate(valid_grants):
        grant_id = make_id(grant, i)

        # Guard against any remaining duplicates
        if grant_id in seen_ids:
            grant_id = f"{grant_id}-{i}"
        seen_ids.add(grant_id)

        text = grant_to_text(grant)
        embedding = model.encode(text).tolist()

        award_floor = grant.get("min_award_amount") or 0
        award_ceiling = grant.get("max_award_amount") or 0
        try:
            award_floor = int(str(award_floor).replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            award_floor = 0
        try:
            award_ceiling = int(str(award_ceiling).replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            award_ceiling = 0

        categories = grant.get('funding_activity_categories', [])
        if isinstance(categories, list):
            categories = ', '.join(categories)

        # Use the CA portal URL as the application link; fall back to apply_links
        apply_links = grant.get("apply_links") or []
        application_url = (
            apply_links[-1] if apply_links          # last link = direct application form
            else grant.get("grants_gov_url", "")
        )

        ids.append(grant_id)
        embeddings.append(embedding)
        documents.append(text)
        metadatas.append({
            "title":           grant.get("title", ""),
            "agency":          grant.get("funder_name", ""),
            "award_floor":     award_floor,
            "award_ceiling":   award_ceiling,
            "application_url": application_url,
            "portal_url":      grant.get("grants_gov_url", ""),
            "close_date":      grant.get("close_date") or "Ongoing",
            "focus_areas":     categories,
            "contact_email":   grant.get("contact_email") or "",
            "contact_name":    grant.get("contact_name") or "",
            "funding_method":  grant.get("funding_method") or "",
            "estimated_total": grant.get("estimated_total_funding") or "",
        })

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"\n✅ Loaded {len(ids)} grants into ChromaDB at '{CHROMA_PATH}'")
    print(f"   Collection: '{COLLECTION}'")
    print(f"   Ready for similarity search.")


if __name__ == "__main__":
    load_grants_to_vectordb()