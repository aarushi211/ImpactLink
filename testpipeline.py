import json
from services.parser import parse_proposal
from agents.scoring_agent import score_proposal
from services.vector_store import find_similar_grants

PDF_PATH = "data/p1.pdf"

# ── STEP 1: Parse ────────────────────────────────────────
print("=" * 50)
print("STEP 1: Parsing Proposal PDF...")
print("=" * 50)
with open(PDF_PATH, "rb") as f:
    file_bytes = f.read()

proposal = parse_proposal(file_bytes, "p1.pdf")
print(json.dumps(proposal, indent=2))

# ── STEP 2: Score ────────────────────────────────────────
print("\n" + "=" * 50)
print("STEP 2: Scoring Proposal...")
print("=" * 50)
scoring = score_proposal(proposal)
print(json.dumps(scoring, indent=2))

# ── STEP 3: RAG Match ────────────────────────────────────
print("\n" + "=" * 50)
print("STEP 3: Finding + Explaining Matching Grants (RAG)...")
print("=" * 50)
matches = find_similar_grants(proposal, top_k=5)

for i, match in enumerate(matches):
    print(f"\n#{i+1} — {match['title']}")
    print(f"   Agency:     {match['agency']}")
    print(f"   Score:      {match['similarity_score']}% | Fit: {match['fit_level'].upper()}")
    print(f"   Budget:     ${match['award_floor']:,} - ${match['award_ceiling']:,}")
    print(f"   Deadline:   {match['close_date'] or 'Rolling'}")
    print(f"   Why match:  {match['match_explanation']}")
    print(f"   💡 Tip:     {match['application_tip']}")
    print(f"   Apply:      {match['application_url']}")

print("\n" + "=" * 50)
print("PIPELINE COMPLETE")
print("=" * 50)