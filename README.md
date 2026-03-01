<<<<<<< HEAD
# 📊 ImpactLink: AI-Driven Strategic Funding Matcher
ImpactLink is a high-precision RAG (Retrieval-Augmented Generation) pipeline designed to help NGOs find and win the best-fit grants. Unlike basic keyword search tools, ImpactLink uses a Two-Stage Re-Ranking architecture and Semantic Chunking to ensure that logical eligibility—not just word similarity—drives the results.

## 🚀 Key Features
- **Smart Grant Discovery:**: View and filter a curated database of global grants with real-time match scoring
- **AI Proposal Draft Assistant:** Generate high-quality first drafts of grant applications tailored specifically to the requirements of a selected funder
- **Interactive Budget Builder:** Integrated tools to structure project finances, ensuring alignment with grant limits and category requirements
- **NGO Dashboard:** A centralized "Mission Control" to track active applications, saved grants, and project drafts
- **Semantic Proposal Parsing:** Uses `SentenceTransformer` to break long PDF proposals into "semantic chapters," ensuring the AI captures the mission from the intro and the budget from the appendix
- **Two-Stage Re-Ranker:**
    - Stage 1 (Recall): High-speed vector retrieval using `ChromaDB` and `all-MiniLM-L6-v2` to find potential matches
    - Stage 2: A logical "Deep Reasoner" re-ranking agent using Groq (Llama 3.1 8B) to verify hard constraints like geographic and mission eligibility
- **Privacy-First Architecture:** Designed to run with local LLMs (Ollama) or high-speed cloud inference (Groq) depending on the sensitivity of the NGO's data
- **ImpactLink Frontend**: A modern, responsive dashboard built with Next.js to visualize match scores and funding insights.

## 🔴 The Problem
Small NGOs often lack dedicated grant-writing teams. They spend ~40% of their time manually filtering through 50+ page PDFs, only to find they are ineligible due to a single clause buried in the appendix. This "Information Overload" leads to a 70% rejection rate for grassroots organizations.

## 🟢 The Solution
ImpactLink is a high-precision RAG pipeline that automates the eligibility "Deep Reasoner." By using semantic chunking and a two-stage re-ranking architecture, it ensures that NGOs only spend time on grants they are logically qualified to win. It then assists in drafting and budgeting to turn a mission into a winning proposal in minutes.

## 🛠️ Tech Stack
|Category | Tools|
|---------|-------|
|LLM Inference | Groq (Llama 3.1 8B / 3.3 70B), Ollama|
|Vector Database| ChromaDB|
|Embeddings | Hugging Face `all-MiniLM-L6-v2`|
|Orchestration | LangChain, Pydantic (Structured Output)|
|Backend | FastAPI (Python 3.12) |
|Frontend | Next.js 15+, Tailwind CSS, Lucide React |

## 🛠️ Product Workflow
ImpactLink takes an NGO from "Idea" to "Submitted" in one seamless flow:
- **Upload & Analyze:** Upload an existing project proposal or concept note (PDF).
- **Match:** The AI extracts your mission and constraints to find the top 5 most compatible grants.
- **Refine:** Use the Budget Builder to align your costs with the specific grant's ceiling.
- **Draft:** Use the Draft Assistant to "remix" your original proposal into the specific format required by the grantor.
- **Track:** Manage all your historical and pending applications through the Grant Dashboard.


## 📦 Installation & Setup
**1. Clone the repository:**
```
git clone https://github.com/aarushi211/grant-graph.git
cd grant-graph
```

**2. Set up your environment:**
Create a `.env` file in the root directory:
```
GROQ_API_KEY=your_groq_key_here
USE_GROQ=True
LOCAL_LLM_MODEL=llama3
```

**3. Install dependencies:**
```
pip install -r requirements.txt
```

**4. Run the Backend:**
```
python main.py
```

📁 Project Structure
- `/agents`: Logic for the Re-Ranker and Reasoning agents.
- `/services`: Core RAG logic and vector database management.
- `/impactlink-frontend`: Next.js web application.
- `graphql_server.py`: API layer for handling complex data queries.
- `load_vectors.py`: Script for ingesting and embedding grant datasets.

## 🗺️ Future Roadmap
While the core RAG pipeline and dashboard are functional, we envision ImpactLink evolving into a comprehensive ecosystem for non-profit success:
- **Multi-Agent Collaborative Drafting:** Implementing a "Critique Agent" that acts as a mock grant reviewer to score drafts and suggest improvements before submission.
- **Automatic Grant Scraping:** Integration with grants.gov and international NGO databases to provide real-time alerts for new funding opportunities.
- **Multi-Modal Ingestion:** Supporting image-to-text for scanning physical grant flyers or handwritten project notes from field workers.
- **Privacy-First Local Deployment:** Further optimizing the pipeline for quantized GGUF models to allow the entire suite to run offline on a standard laptop in areas with low internet connectivity.
- **Impact Reporting:** A module to help NGOs auto-generate progress reports for donors by pulling data from their internal project logs.

## 🏆 Hackathon Notes
Small NGOs often lack dedicated grant writers, putting them at a disadvantage against larger organizations. ImpactLink levels the playing field by providing professional-grade drafting and budgeting tools, allowing grassroots organizations to focus their energy where it belongs: on the mission.
=======
<div align="center">

# ⬡ ImpactLink

### AI Grant Intelligence Platform for NGOs

*Find grants · Write proposals · Build budgets · Discover collaborators*

![FastAPI](https://img.shields.io/badge/FastAPI-0D0D1A?style=for-the-badge&logo=fastapi&logoColor=6C63FF)
![React](https://img.shields.io/badge/React-0D0D1A?style=for-the-badge&logo=react&logoColor=6C63FF)
![LangChain](https://img.shields.io/badge/LangChain-0D0D1A?style=for-the-badge&logo=chainlink&logoColor=6C63FF)
![ChromaDB](https://img.shields.io/badge/ChromaDB-0D0D1A?style=for-the-badge&logoColor=6C63FF)
![Llama](https://img.shields.io/badge/Llama_3.3_70B-0D0D1A?style=for-the-badge&logoColor=6C63FF)

</div>

---

## What is ImpactLink?

ImpactLink is an end-to-end AI platform that helps under-resourced NGOs compete for grant funding. Upload your proposal, get AI-matched grants, draft funder-specific applications, build localized budgets, and find partner organizations — all in one workflow.

**The problem it solves:** Most NGOs spend 40+ hours per grant cycle on research and writing. ImpactLink cuts that to hours, not days.

---

## Features

| Feature | Description |
|---|---|
| ◎ **Grant Matching** | Upload a PDF/DOCX proposal → AI embeds it → vector search finds the best-fit grants from the database → LLM explains each match |
| ✍ **Draft Assistant** | Select a grant and your proposal → AI streams a complete 8-section funder-specific draft → inline edit, formatting toolbar, PDF export |
| ✦ **Proposal Builder** | No proposal yet? 7-step guided interview → AI drafts each section as you answer → approve, AI-revise, or edit inline |
| 💰 **Budget Builder** | Generate a localized line-item budget based on award ceiling + your geography → refine via plain-English chat |
| ⬡ **NGO Collaborators** | Toggle on GrantsList to see mission-aligned NGOs ranked by similarity → AI suggests collaboration type and shared focus |
| 📊 **Dashboard** | All saved work in one place → click any proposal to instantly filter the grant panel to that proposal's matches |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     React SPA                           │
│  Dashboard · GrantsList · Draft · Build · Budget        │
│  Upload · Profile · Login                               │
└──────────────────────┬──────────────────────────────────┘
                       │ REST / JSON
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Server                        │
│                                                         │
│  /api/upload     → parser.py → PyMuPDF                 │
│  /api/match      → vector_store.py → ChromaDB          │
│  /api/draft      → draft_agent.py  → Groq (SSE)        │
│  /api/build      → build_agent.py  → Groq (SSE)        │
│  /api/budget     → budget LLM agent → Groq             │
│  /api/collab     → ngo_collab.py   → MiniLM + Groq     │
│  /api/work/*     → work_store.py   → JSON store        │
│  /api/auth/*     → ngo_store.py    → JSON store        │
└──────────────┬──────────────────┬───────────────────────┘
               │                  │
    ┌──────────▼───────┐  ┌──────▼──────────────┐
    │    ChromaDB       │  │   Groq API           │
    │  (grant vectors)  │  │  Llama 3.3 70B       │
    └───────────────────┘  └─────────────────────┘
```

### Backend Stack

| Layer | Technology |
|---|---|
| API Server | FastAPI + Uvicorn |
| PDF Parsing | PyMuPDF |
| Vector Search | ChromaDB + `sentence-transformers` (MiniLM-L6-v2) |
| LLM | Llama 3.3 70B Versatile via Groq API |
| Orchestration | LangChain (ChatGroq + ChatPromptTemplate) |
| Storage | Flat JSON files (`ngo_profiles.json`, `work_store.json`) |

### Frontend Stack

| Layer | Technology |
|---|---|
| UI | React 18 + React Router v6 |
| HTTP | Axios (central `api.js` instance) |
| State | Custom hooks + AuthContext + sessionStorage |
| PDF Export | jsPDF (client-side) |
| Styling | Inline styles with CSS variables |

---

## Project Structure

```
impactlink/
├── ngo-backend/
│   ├── main.py                  # FastAPI app — all 25+ endpoints
│   ├── agents/
│   │   ├── draft_agent.py       # Streams 8-section proposal drafts
│   │   ├── build_agent.py       # Guided 7-step proposal builder
│   │   ├── scoring_agent.py     # Scores proposal across 6 dimensions
│   │   └── similarity_agent.py  # Funder similarity (legacy)
│   ├── services/
│   │   ├── vector_store.py      # ChromaDB RAG pipeline
│   │   ├── ngo_collab.py        # NGO mission similarity matching
│   │   ├── ngo_store.py         # Auth + profile CRUD
│   │   ├── work_store.py        # Drafts / builds / budgets CRUD
│   │   └── parser.py            # PDF → structured proposal dict
│   ├── data/
│   │   ├── grants_enriched.json # Grant database
│   │   ├── ngo_profiles.json    # NGO accounts + profiles
│   │   └── work_store.json      # Saved work (auto-created)
│   ├── load_vectors.py          # Populates ChromaDB from grants JSON
│   └── requirements.txt
│
└── impactlink-frontend/
    └── src/
        ├── pages/
        │   ├── Dashboard.js     # Hub — stats, grants, saved work
        │   ├── GrantsList.js    # Grants + Collaborators toggle
        │   ├── Draft.js         # Draft Assistant
        │   ├── BuildProposal.js # Guided Proposal Builder
        │   ├── Budget.js        # Budget Builder
        │   ├── Upload.js        # Proposal upload
        │   ├── GrantDetail.js   # Single grant view
        │   ├── Profile.js       # NGO profile editor
        │   └── Login.js         # Auth
        ├── hooks/
        │   ├── useGrants.js     # Grant matches from sessionStorage
        │   ├── useWorkStore.js  # Saved drafts/builds/budgets
        │   ├── useDraft.js      # SSE streaming for draft
        │   ├── useBudget.js     # Budget generate + refine
        │   └── useUpload.js     # File upload + auto-save
        ├── components/
        │   ├── GrantCard.js
        │   ├── CollabCard.js
        │   └── ...
        ├── context/
        │   └── AuthContext.js
        └── services/
            └── api.js           # Axios instance + helper functions
```

---

## API Reference

### Core Pipeline

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload` | Parse PDF/DOCX → embed → match + score |
| `POST` | `/api/match` | Match pre-parsed proposal to grants |
| `POST` | `/api/score` | Score proposal readiness (6 dimensions) |
| `POST` | `/api/draft/stream` | Stream 8-section draft (SSE) |
| `POST` | `/api/build/stream` | Guided builder conversation (SSE) |
| `POST` | `/api/build/revise` | LLM-rewrite one section |
| `POST` | `/api/budget/generate` | Generate localized line-item budget |
| `POST` | `/api/budget/refine` | Refine budget via chat |
| `POST` | `/api/collab/match` | Find mission-similar NGOs |

### Work Store

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/work/drafts` | Save draft (with `proposal_context`, `matches_id`) |
| `PATCH` | `/api/work/drafts` | Update draft sections |
| `GET` | `/api/work/drafts/:ngo_id` | List all drafts |
| `DELETE` | `/api/work/drafts/:ngo_id/:id` | Delete draft |
| `POST` | `/api/work/builds` | Save built proposal |
| `PATCH` | `/api/work/builds` | Update build |
| `POST` | `/api/work/budgets` | Save budget (links to proposal via `proposal_id`) |
| `GET` | `/api/work/summary/:ngo_id` | Counts + recent items |

### Auth & Profile

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create NGO account |
| `POST` | `/api/auth/login` | Authenticate |
| `GET` | `/api/profile/:ngo_id` | Fetch profile |
| `PATCH` | `/api/profile` | Update profile |

---

## Data Models

### Proposal (parsed from uploaded PDF)
```json
{
  "organization_name": "...",
  "primary_mission": "...",
  "project_title": "...",
  "cause_area": "...",
  "key_activities": ["..."],
  "target_beneficiaries": ["..."],
  "geographic_focus": ["..."],
  "sdg_alignment": ["SDG 4: Quality Education", "..."]
}
```

### DraftItem / BuildItem (work_store.json)
```json
{
  "id": "a3f9c12b8e1d",
  "ngo_id": "my_org_x4f2",
  "title": "USAID Youth Education Grant",
  "grant_id": "123",
  "proposal_context": { },
  "matches_id": ["123", "456", "789"],
  "budget_id": "b8e2f10a3c9d",
  "sections": {
    "executive_summary": { "title": "Executive Summary", "content": "..." },
    "problem_statement":  { "title": "Problem Statement", "content": "..." }
  },
  "section_order": ["executive_summary", "problem_statement", "..."],
  "word_count": 2847
}
```

### BudgetItem (work_store.json)
```json
{
  "id": "b8e2f10a3c9d",
  "proposal_id": "a3f9c12b8e1d",
  "grant_id": "123",
  "max_budget": 250000,
  "items": [
    { "category": "Personnel", "description": "Project Manager (12 months)", "amount": 48000, "justification": "..." }
  ],
  "total_requested": 247500,
  "locality_explanation": "Costs reflect Nairobi market rates..."
}
```

---

## Local Setup

### Backend

```bash
cd ngo-backend

# Install dependencies
pip install -r requirements.txt

# Set environment variables
echo "GROQ_API_KEY=your_key_here" > .env

# Load grants into ChromaDB (run once)
python load_vectors.py

# Start server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd impactlink-frontend

# Install dependencies
npm install

# Set environment variables
echo "REACT_APP_API_URL=http://localhost:8000" > .env

# Start dev server
npm start
```

### Requirements

- Python 3.10+
- Node.js 18+
- [Groq API key](https://console.groq.com) (free tier works)

---

## How the AI Pipeline Works

### Grant Matching (RAG)

```
1. Upload PDF
      ↓
2. PyMuPDF extracts text → parser.py structures it into proposal{}
      ↓
3. MiniLM-L6-v2 encodes proposal text → 384-dim embedding
      ↓
4. ChromaDB cosine similarity → top-5 grants retrieved
      ↓
5. Llama 3.3 70B (Groq) → adds match_explanation, fit_level, application_tip per grant
      ↓
6. Results merged: vector results are source of truth for IDs, LLM only contributes explanations
```

### NGO Collaboration Matching

```
1. User opens Collaborators tab
      ↓
2. All collab_open=True NGO profiles loaded from ngo_profiles.json
      ↓
3. Each profile encoded: "Mission: ... | Cause: ... | Activities: ... | SDGs: ... | Geography: ..."
      ↓
4. Cosine-ranked against proposal embedding (in-memory, no separate vector DB)
      ↓
5. Top-6 → Llama generates collab_explanation, collab_type, shared_focus
```

### Streaming Draft (SSE)

```
POST /api/draft/stream → Server-Sent Events
  → chunk: { type: "section_start", key: "executive_summary", title: "..." }
  → chunk: { type: "content", key: "executive_summary", content: "..." }
  → chunk: { type: "section_start", key: "problem_statement", ... }
  → ...
  → chunk: { type: "done" }
```

---

## Roadmap

- [ ] PostgreSQL migration — replace flat JSON with a proper database
- [ ] JWT authentication — stateless auth tokens
- [ ] Deadline alerts — notify NGOs of approaching grant close dates
- [ ] Multi-user organizations — team members sharing one NGO workspace
- [ ] Automated grant scraping — ingest new grants from Grants.gov and foundation sites
- [ ] Proposal version history — diff viewer and rollback
- [ ] Collaboration inbox — in-platform messaging between matched NGOs
- [ ] Impact tracking — link won grants to reported outcomes

---

<div align="center">

Built to help NGOs win the funding they deserve.

</div>
>>>>>>> d010df2c0f810098ae35332066c219e7c2614cad
