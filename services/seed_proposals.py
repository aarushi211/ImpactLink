"""
seed_proposals.py

Seeds the 'proposals' ChromaDB collection with fake NGO proposals
so the collaboration feature works during demo / hackathon.

Run ONCE before demo:
    python seed_proposals.py

It will NOT wipe your existing 'grants' collection.
"""

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_PATH = "./chroma_db"
MODEL_NAME  = "all-MiniLM-L6-v2"

# ── Fake proposals ────────────────────────────────────────────────────────────
# Each has realistic proposal text + metadata matching real CA grant focus areas.
# Tied loosely to real grant themes so similarity matching actually fires.

SEED_PROPOSALS = [
    {
        "org_id": "org-001",
        "org_name": "GreenRoots Alliance",
        "location": "Los Angeles",
        "contact_email": "greenrootsalliance@example.org",
        "website": "https://greenroots-alliance.org",
        "focus_areas": "Environment & Water, Parks & Recreation",
        "proposal_text": """
            Project Title: LA River Riparian Corridor Restoration
            Mission: We restore degraded riparian habitats along the Los Angeles River
            to improve water quality, increase biodiversity, and provide green space
            for underserved communities in South LA.
            Target Beneficiaries: Low-income residents, migratory birds, native fish species
            Geography: Los Angeles, Lower LA River corridor
            Key Activities: Native plant restoration, invasive species removal,
            community stewardship volunteer programs, water quality monitoring
            Cause Area: Environmental conservation and community access to nature
        """.strip(),
    },
    {
        "org_id": "org-002",
        "org_name": "Bay Area Housing Advocates",
        "location": "San Francisco",
        "contact_email": "bayareahousingadvocates@example.org",
        "website": "https://bay-area-housing-advocates.org",
        "focus_areas": "Housing, Disadvantaged Communities",
        "proposal_text": """
            Project Title: Affordable Housing Trust Fund for Extremely Low Income Families
            Mission: We develop and preserve affordable housing units for families earning
            below 30% AMI in the Bay Area, with a focus on preventing displacement
            and building community land trusts.
            Target Beneficiaries: Extremely low income households, formerly homeless families
            Geography: San Francisco, Oakland, San Jose
            Key Activities: Construction loans for affordable units, ADU development programs,
            homebuyer education, anti-displacement legal services
            Cause Area: Affordable housing and economic equity
        """.strip(),
    },
    {
        "org_id": "org-003",
        "org_name": "Sierra Wildfire Collaborative",
        "location": "Sacramento",
        "contact_email": "sierrawildfirecollaborative@example.org",
        "website": "https://sierra-wildfire-collaborative.org",
        "focus_areas": "Disaster Prevention & Relief, Environment & Water",
        "proposal_text": """
            Project Title: Community-Led Forest Resilience and Fire Prevention Program
            Mission: We reduce wildfire risk in Sierra Nevada communities through
            prescribed burns, forest thinning, and community fire preparedness
            training, partnering with tribal land stewards and local fire departments.
            Target Beneficiaries: Rural mountain communities, indigenous tribes, wildlife
            Geography: Sierra Nevada foothills, Sacramento region, Statewide
            Key Activities: Prescribed fire planning, forest thinning contracts,
            defensible space education, emergency evacuation planning
            Cause Area: Wildfire prevention and forest health
        """.strip(),
    },
    {
        "org_id": "org-004",
        "org_name": "Coastal Restoration Fund",
        "location": "Santa Barbara",
        "contact_email": "coastalrestorationfund@example.org",
        "website": "https://coastal-restoration-fund.org",
        "focus_areas": "Environment & Water, Science",
        "proposal_text": """
            Project Title: Ocean Acidification Monitoring and Kelp Forest Recovery
            Mission: We monitor and restore coastal marine ecosystems threatened by
            ocean acidification and hypoxia along the Central California coast,
            working with fishing communities to protect livelihoods and biodiversity.
            Target Beneficiaries: Fishing communities, marine species, coastal ecosystems
            Geography: Santa Barbara, Central California Coast
            Key Activities: Water chemistry monitoring, kelp spore restoration,
            harmful algal bloom early warning systems, fishermen engagement
            Cause Area: Marine conservation and climate adaptation
        """.strip(),
    },
    {
        "org_id": "org-005",
        "org_name": "Valley Health Partners",
        "location": "Fresno",
        "contact_email": "valleyhealthpartners@example.org",
        "website": "https://valley-health-partners.org",
        "focus_areas": "Health & Human Services, Disadvantaged Communities",
        "proposal_text": """
            Project Title: Rural Primary Care Expansion for Farmworker Communities
            Mission: We deliver preventive and primary care services to uninsured
            and underinsured farmworker families in the Central Valley through
            mobile clinics and community health workers.
            Target Beneficiaries: Farmworkers, undocumented immigrants, rural low-income families
            Geography: Fresno, Bakersfield, Central Valley
            Key Activities: Mobile health clinic operations, nurse practitioner training,
            health screenings, Spanish-language patient navigation
            Cause Area: Rural health equity and access
        """.strip(),
    },
    {
        "org_id": "org-006",
        "org_name": "Urban Farms Collective",
        "location": "Los Angeles",
        "contact_email": "urbanfarmscollective@example.org",
        "website": "https://urban-farms-collective.org",
        "focus_areas": "Agriculture, Disadvantaged Communities, Employment",
        "proposal_text": """
            Project Title: Urban Agriculture Job Training for Transition-Age Youth
            Mission: We train disconnected youth in urban agriculture, food systems,
            and green job skills, providing paid apprenticeships at community farms
            across South and East Los Angeles.
            Target Beneficiaries: Transition-age youth 18-24, formerly incarcerated individuals
            Geography: Los Angeles, South LA, East LA
            Key Activities: Agricultural job training, composting education,
            farmers market vending, food justice advocacy
            Cause Area: Workforce development and food security
        """.strip(),
    },
    {
        "org_id": "org-007",
        "org_name": "San Diego Watershed Alliance",
        "location": "San Diego",
        "contact_email": "sandiegowatershedalliance@example.org",
        "website": "https://san-diego-watershed-alliance.org",
        "focus_areas": "Environment & Water, Science",
        "proposal_text": """
            Project Title: Watershed Restoration and Stormwater Capture in San Diego
            Mission: We restore native vegetation in San Diego watersheds to improve
            water quality, increase groundwater recharge, and reduce polluted
            stormwater runoff into coastal waters.
            Target Beneficiaries: Downstream communities, coastal ecosystems, native species
            Geography: San Diego, coastal watersheds
            Key Activities: Riparian planting, stormwater infrastructure grants,
            water quality testing, school education programs
            Cause Area: Water conservation and watershed health
        """.strip(),
    },
    {
        "org_id": "org-008",
        "org_name": "NorCal Resilience Network",
        "location": "Oakland",
        "contact_email": "norcalresiliencenetwork@example.org",
        "website": "https://norcal-resilience-network.org",
        "focus_areas": "Disaster Prevention & Relief, Disadvantaged Communities",
        "proposal_text": """
            Project Title: Climate Resilience Hubs for Oakland Frontline Communities
            Mission: We build climate resilience in Oakland's most vulnerable neighborhoods
            by establishing community hubs that provide cooling centers, emergency
            preparedness resources, and green infrastructure.
            Target Beneficiaries: Low-income communities of color, elderly residents, renters
            Geography: Oakland, East Bay
            Key Activities: Resilience hub operations, hazard mitigation planning,
            green infrastructure installation, community emergency response training
            Cause Area: Climate adaptation and community resilience
        """.strip(),
    },
    {
        "org_id": "org-009",
        "org_name": "Tribal Land Stewards Network",
        "location": "Statewide",
        "contact_email": "triballandstewardsnetwork@example.org",
        "website": "https://tribal-land-stewards-network.org",
        "focus_areas": "Environment & Water, Agriculture",
        "proposal_text": """
            Project Title: Tribal Nature-Based Solutions for Climate Adaptation
            Mission: We support California tribal nations in implementing traditional
            ecological knowledge and nature-based solutions to restore land, water,
            and cultural resources on and near tribal territories.
            Target Beneficiaries: Tribal communities, native ecosystems, cultural heritage sites
            Geography: Statewide, tribal lands across California
            Key Activities: Traditional fire management, salmon habitat restoration,
            acorn grove stewardship, tribal youth conservation corps
            Cause Area: Indigenous land stewardship and climate resilience
        """.strip(),
    },
    {
        "org_id": "org-010",
        "org_name": "Renewable Energy Access CA",
        "location": "Riverside",
        "contact_email": "renewableenergyaccessca@example.org",
        "website": "https://renewable-energy-access-ca.org",
        "focus_areas": "Energy, Disadvantaged Communities",
        "proposal_text": """
            Project Title: Solar Access Program for Inland Empire Low-Income Households
            Mission: We bring rooftop solar and battery storage to low-income families
            in the Inland Empire who are disproportionately burdened by high energy
            costs and extreme heat, partnering with utilities and local workforce programs.
            Target Beneficiaries: Low-income households, renters, mobile home residents
            Geography: Riverside, San Bernardino, Inland Empire
            Key Activities: Solar installation subsidies, energy efficiency audits,
            green workforce training, community outreach in Spanish and Tagalog
            Cause Area: Clean energy equity and climate justice
        """.strip(),
    },
    {
        "org_id": "org-011",
        "org_name": "North Coast Salmon Fund",
        "location": "Statewide",
        "contact_email": "northcoastsalmonfund@example.org",
        "website": "https://north-coast-salmon-fund.org",
        "focus_areas": "Environment & Water, Science",
        "proposal_text": """
            Project Title: Klamath-Trinity Watershed Fish Passage and Habitat Restoration
            Mission: We restore salmon and steelhead populations in Northern California
            rivers by removing fish barriers, revegetating stream banks, and partnering
            with tribal and commercial fishermen on recovery planning.
            Target Beneficiaries: Salmon and steelhead populations, tribal fishing communities
            Geography: Klamath-Trinity watershed, Northern California
            Key Activities: Fish barrier removal, stream bank restoration,
            spawning gravel augmentation, water temperature monitoring
            Cause Area: Fisheries restoration and tribal food sovereignty
        """.strip(),
    },
    {
        "org_id": "org-012",
        "org_name": "California Housing Justice Coalition",
        "location": "Los Angeles",
        "contact_email": "californiahousingjusticecoalition@example.org",
        "website": "https://california-housing-justice-coalition.org",
        "focus_areas": "Housing, Disadvantaged Communities",
        "proposal_text": """
            Project Title: Permanent Supportive Housing for Chronically Homeless Adults
            Mission: We develop permanent supportive housing with wraparound services
            for chronically homeless adults in Los Angeles, combining affordable units
            with on-site mental health, substance use, and employment support.
            Target Beneficiaries: Chronically homeless adults, veterans, people with disabilities
            Geography: Los Angeles, Long Beach
            Key Activities: Housing construction and rehabilitation, case management,
            benefits enrollment, peer support programs, landlord engagement
            Cause Area: Homelessness and housing stability
        """.strip(),
    },
    {
        "org_id": "org-013",
        "org_name": "Central Valley Employment Hub",
        "location": "Fresno",
        "contact_email": "centralvalleyemploymenthub@example.org",
        "website": "https://central-valley-employment-hub.org",
        "focus_areas": "Employment, Disadvantaged Communities, Labor & Training",
        "proposal_text": """
            Project Title: Farmworker Advancement and Career Pathways Program
            Mission: We provide agricultural workers in the Central Valley with
            English language training, vocational certifications, and career pathway
            support to transition into higher-wage green economy jobs.
            Target Beneficiaries: Farmworkers, monolingual Spanish speakers, H-2A visa workers
            Geography: Fresno, Tulare, Kings counties, Central Valley
            Key Activities: ESL and digital literacy classes, CDL and pesticide
            applicator certification, job placement, employer partnerships
            Cause Area: Workforce development for agricultural communities
        """.strip(),
    },
    {
        "org_id": "org-014",
        "org_name": "Mojave Desert Conservation League",
        "location": "Bakersfield",
        "contact_email": "mojavedesertconservationleague@example.org",
        "website": "https://mojave-desert-conservation-league.org",
        "focus_areas": "Environment & Water, Parks & Recreation",
        "proposal_text": """
            Project Title: Desert Tortoise Habitat Corridor and Public Access Program
            Mission: We protect and restore desert tortoise habitat in the Mojave
            while creating accessible trails and interpretive programs for communities
            in the Inland Empire and Coachella Valley.
            Target Beneficiaries: Desert wildlife, low-income communities lacking park access
            Geography: Mojave Desert, Coachella Valley, Inland Empire
            Key Activities: Habitat corridor land acquisition, tortoise monitoring,
            trail construction, bilingual interpretive signage, school field trips
            Cause Area: Desert conservation and outdoor equity
        """.strip(),
    },
    {
        "org_id": "org-015",
        "org_name": "Eastside Arts & Libraries",
        "location": "Los Angeles",
        "contact_email": "eastsideartslibraries@example.org",
        "website": "https://eastside-arts-libraries.org",
        "focus_areas": "Libraries and Arts, Disadvantaged Communities, Education",
        "proposal_text": """
            Project Title: Community Library Innovation Hubs for East LA
            Mission: We transform underutilized library branches in East Los Angeles
            into community innovation hubs with maker spaces, digital literacy programs,
            and culturally relevant arts programming for youth and seniors.
            Target Beneficiaries: Low-income youth, seniors, immigrant families
            Geography: Los Angeles, East LA, Boyle Heights
            Key Activities: Makerspace installation, STEAM after-school programs,
            bilingual digital literacy classes, mural and public art commissions
            Cause Area: Education equity and community cultural life
        """.strip(),
    },
]


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed_proposals():
    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Clear and recreate proposals collection
    try:
        client.delete_collection("proposals")
        print("Cleared existing 'proposals' collection")
    except:
        pass

    collection = client.create_collection(
        name="proposals",
        metadata={"hnsw:space": "cosine"}
    )

    ids, embeddings, documents, metadatas = [], [], [], []

    for p in SEED_PROPOSALS:
        embedding = model.encode(p["proposal_text"]).tolist()

        ids.append(p["org_id"])
        embeddings.append(embedding)
        documents.append(p["proposal_text"])
        metadatas.append({
            "org_name":     p["org_name"],
            "location":     p["location"],
            "contact_email": p["contact_email"],
            "website":      p["website"],
            "focus_areas":  p["focus_areas"],
        })

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"\n✅ Seeded {len(ids)} proposals into 'proposals' collection")
    print(f"   ChromaDB path: {CHROMA_PATH}")


if __name__ == "__main__":
    seed_proposals()