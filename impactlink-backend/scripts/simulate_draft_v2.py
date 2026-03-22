"""
scripts/simulate_draft_v2.py

Simulation script for the enhanced 8-step proposal drafting workflow.
"""

import os
import sys
import asyncio
import json

# Add parent directory to sys.path to allow imports from agents and services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.draft_agent_v2 import extract_funder_vocab, analyze_gaps, draft_proposal_v2
from services.export import export_to_docx, export_to_pdf

# Dummy Data
DUMMY_PROPOSAL = {
    "organization_name": "Green Future Initiative",
    "mission": "Empowering underserved communities through urban reforestation and environmental education.",
    "total_budget": 250000,
    "target_beneficiaries": ["Low-income youth", "Unemployed residents", "Local schools"],
    "key_activities": ["Tree planting", "Horticultural training", "Community workshops"],
    "geographic_focus": ["South Los Angeles", "East Los Angeles"],
    "timeline": "18 months",
    "number_served": 500,
    "kpis": ["5,000 trees planted", "100 youth certified in horticulture", "20 community workshops held"]
}

DUMMY_GRANT = {
    "grant_id": "CA-URBAN-2025",
    "title": "California Urban Canopy Expansion Grant",
    "agency": "California Department of Forestry and Fire Protection (CAL FIRE)",
    "description": """The Urban Canopy Expansion Grant program aims to improve environmental quality and public health by increasing the urban canopy in disadvantaged communities. 
    Qualified projects should focus on:
    - Species diversity for climate resilience.
    - Community engagement and education.
    - Long-term maintenance and survivability of planted trees.
    - Workforce development in green sectors.
    We prioritize 'disadvantaged community' impact as defined by CalEnviroScreen. 
    We seek projects that use 'nature-based solutions' and provide 'ecosystem services' while fostering 'climate equity'.""",
    "focus_areas": "Urban Greening, Forestry, Climate Resilience",
    "eligibility": ["Non-profits", "Local Governments", "Tribal Governments"],
    "award_ceiling": 500000,
    "cost_sharing_required": True,
    "application_tip": "Focus heavily on the long-term maintenance plan and community ownership."
}

async def run_simulation():
    print("🚀 Starting Enhanced Proposal Drafting Workflow Simulation (v2)")
    print("-" * 60)

    # Step 1: Extract funder vocab
    print("\n[Step 1] Extracting funder vocab...")
    vocab = await extract_funder_vocab(DUMMY_GRANT["description"])
    print(f"✅ Funder Vocab:\n{vocab}")

    # Step 2: Analyze gaps
    print("\n[Step 2] Analyzing gaps...")
    gaps = await analyze_gaps(DUMMY_PROPOSAL, DUMMY_GRANT["description"])
    print("✅ Identified Gaps:")
    for gap in gaps:
        print(f" - {gap}")

    # Step 3: Gap review
    print("\n[Step 3] Gap review (Simulated)...")
    print("User: 'The list looks good. Please focus on the maintenance plan gap.'")
    # For simulation, we proceed with the current gaps.

    # Step 4, 5, 6: Drafting, Scoring, Diffs
    print("\n[Step 4, 5, 6] Drafting proposal with parallel sections, scoring, and retries...")
    print("(This may take a minute or two...)")
    final_proposal = await draft_proposal_v2(DUMMY_PROPOSAL, DUMMY_GRANT)
    print("✅ Drafting complete.")

    # Show some section results
    for key in final_proposal["section_order"]:
        section = final_proposal["sections"][key]
        print(f"\n--- Section: {section['title']} ---")
        print(f"Score: {section['score']}/10 | Retries: {section['retries']}")
        if section['diffs']:
            print("Diff sample (first retry):")
            print(section['diffs'][0][:200] + "...")
        print(f"Snippet: {section['content'][:300]}...")

    # Step 7: Draft review
    print("\n[Step 7] Draft review (Simulated)...")
    print("User: 'Sections look great. Ready to export.'")

    # Step 8: Save / download
    print("\n[Step 8] Exporting to DOCX and PDF...")
    docx_path = "proposal_draft_v2.docx"
    pdf_path = "proposal_draft_v2.pdf"
    
    export_to_docx(final_proposal, docx_path)
    export_to_pdf(final_proposal, pdf_path)
    
    print(f"✅ Exported to {docx_path}")
    print(f"✅ Exported to {pdf_path}")

    print("\n✨ Simulation successful! ✨")

if __name__ == "__main__":
    asyncio.run(run_simulation())
