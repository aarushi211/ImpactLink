import json
from config import USE_GROQ  
from services.parser import parse_proposal
from agents.scoring_agent import score_proposal
from services.vector_store import find_similar_grants
from services.budget import generate_budget

PDF_PATH = "Data/Urban Green Tech.pdf"

print("=" * 50)
print(f"PIPELINE STARTING (Mode: {'GROQ' if USE_GROQ else 'LOCAL'})")
print("=" * 50)

# ── STEP 1: Parse ────────────────────────────────────────
print("\nSTEP 1: Parsing Proposal PDF...")
with open(PDF_PATH, "rb") as f:
    file_bytes = f.read()

proposal = parse_proposal(file_bytes, PDF_PATH)
# print(json.dumps(proposal, indent=2)) # Commented for brevity

# ── STEP 2: Score ────────────────────────────────────────
print("\nSTEP 2: Scoring Proposal...")
scoring = score_proposal(proposal)

# ── STEP 3: RAG Match ────────────────────────────────────
print(f"\nSTEP 3: Finding Grants with {'Groq Cloud' if USE_GROQ else 'Local LLM'}...")
# find_similar_grants will now use the flag internally 
matches = find_similar_grants(proposal, top_k=5)

for i, match in enumerate(matches):
    print(f"\n#{i+1} — {match['title']}")
    print(f"   Score:      {match['similarity_score']}% | Fit: {match['fit_level'].upper()}")
    print(f"   Why match:  {match['match_explanation']}")
    print(f"   💡 Tip:     {match['application_tip']}")

print("\n" + "=" * 50)
print("STEP 4: Generating Localized Budget for Top Match...")
print("=" * 50)

if matches:
    # Use the award ceiling of the #1 match to set the budget target
    top_match = matches[0]
    # Default to 100k if award_ceiling is missing/0 to avoid errors
    max_grant_amount = top_match.get("award_ceiling") or 100000
    
    print(f"🎯 Target Grant: {top_match['title']}")
    print(f"💰 Max Budget: ${max_grant_amount:,}")
    
    budget_result = generate_budget(proposal, max_grant_amount)
    
    if "error" not in budget_result:
        print(f"\n📍 Locality Insight: {budget_result['locality_explanation']}")
        print("\n--- Line Item Breakdown ---")
        for item in budget_result['items']:
            print(f"- {item['category']} (${item['amount']:,}): {item['description']}")
        print(f"\nTOTAL REQUESTED: ${budget_result['total_requested']:,}")
    else:
        print(f"❌ Budget Error: {budget_result['error']}")
else:
    print("⚠️ No grants found to generate a budget for.")

print("\n" + "=" * 50)
print("PIPELINE COMPLETE")
print("=" * 50)