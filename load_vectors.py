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
    with open(GRANTS_FILE, "r") as f:
        raw = json.load(f)
   
    grants = raw.get("grants", raw) if isinstance(raw, dict) else raw
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

    for grant in grants:
        text = grant_to_text(grant)
        embedding = model.encode(text).tolist()

        award_floor = grant.get("min_award_amount") or 0
        award_ceiling = grant.get("max_award_amount") or 0
        try:
            award_floor = int(award_floor)
        except (ValueError, TypeError):
            award_floor = 0
        try:
            award_ceiling = int(award_ceiling)
        except (ValueError, TypeError):
            award_ceiling = 0

        categories = grant.get('funding_activity_categories', [])
        if isinstance(categories, list):
            categories = ', '.join(categories)

        ids.append(str(grant["grant_id"]))
        embeddings.append(embedding)
        documents.append(text)
        metadatas.append({
            "title":           grant.get("title", ""),
            "agency":          grant.get("funder_name", ""),
            "award_floor":     award_floor,
            "award_ceiling":   award_ceiling,
            "application_url": grant.get("grants_gov_url", ""),
            "close_date":      grant.get("close_date", ""),
            "focus_areas":     categories,
            "contact_email":   grant.get("contact_email", ""),
            "contact_name":    grant.get("contact_name", ""),
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