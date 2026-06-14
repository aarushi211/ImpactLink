<div align="center">

# ⬡ ImpactLink

### AI Grant Intelligence Platform for NGOs
*Find grants · Write proposals · Build budgets*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-0D0D1A?style=for-the-badge&logo=fastapi&logoColor=6C63FF)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React-0D0D1A?style=for-the-badge&logo=react&logoColor=6C63FF)](https://reactjs.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-0D0D1A?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![Supabase](https://img.shields.io/badge/Database-Supabase-0D0D1A?style=for-the-badge&logo=supabase&logoColor=6C63FF)](https://supabase.com/)
[![Groq](https://img.shields.io/badge/Inference-Groq-0D0D1A?style=for-the-badge&logoColor=6C63FF)](https://groq.com/)

[**Live Demo**](https://impactlink-cbfc5.web.app) · [**AI Architecture Deep-Dive**](./AI_Architecture.md)

</div>

---

## Table of Contents

1. [What Is ImpactLink?](#what-is-impactlink)
2. [System Architecture](#system-architecture)
3. [Agent Orchestration (Drafting Pipeline)](#agent-orchestration-drafting-pipeline)
4. [Codebase Map](#codebase-map)
5. [Data Flow: End-to-End](#data-flow-end-to-end)
6. [API Reference](#api-reference)
7. [How to Run Locally](#how-to-run-locally)
8. [Demo Walkthrough](#demo-walkthrough)
9. [Performance & Observability](#performance--observability)
10. [Scripts & Evaluation](#scripts--evaluation)
11. [Roadmap](#roadmap)

---

## What Is ImpactLink?

ImpactLink is a portfolio-grade AI platform that helps NGOs **find grants**, **draft proposals**, and **build compliant budgets**. It is built around two ideas:

1. **Agentic orchestration** — proposal drafting is a **LangGraph state machine** with named agents, human-in-the-loop gates, structured scoring routes, and deterministic tools (not a single mega-prompt).
2. **Deterministic financial logic** — budget math runs in Python with wage floors and compliance rules; the LLM only writes narrative around pre-calculated numbers.

### Core capabilities

| Feature | Description |
|---|---|
| **Grant matching** | Upload a PDF/DOCX proposal → parse features → semantic search over `pgvector` in Supabase |
| **Build from scratch** | Conversational slot-filling → multi-agent drafting of 10 canonical sections |
| **Improve existing** | Gap analysis → targeted section rewrites with word-level diffs |
| **Budget engine** | Rule extraction + personnel modeling + compliance enforcement |
| **Session persistence** | LangGraph `PostgresSaver` checkpoints survive refreshes and network drops |

### Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, React Router, Axios, Firebase Auth |
| Backend | FastAPI, LangGraph, LangChain, Pydantic |
| Inference | Groq `llama-3.3-70b-versatile` via custom `RotatingGroq` key pool |
| Database | Supabase PostgreSQL (`pgvector`, LangGraph checkpoints, `user_work` table) |
| Storage | Firebase Storage (uploaded proposals) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local) |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         React SPA (impactlink-frontend)                  │
│  Landing · Dashboard · Upload · Draft · Build · Budget · Grants        │
│  Firebase Auth JWT ────────────────────────────────────────────────────── │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTPS / REST
┌───────────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI (impactlink-backend/main.py)                │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │ Session API │  │ Grant RAG    │  │ Budget Eng. │  │ Work Store     │ │
│  │ LangGraph   │  │ vector_store │  │ generator   │  │ drafts/builds  │ │
│  └──────┬──────┘  └──────────────┘  └─────────────┘  └────────────────┘ │
└─────────┼───────────────────────────────────────────────────────────────┘
          │
    ┌─────▼─────┐     ┌──────────────┐     ┌─────────────────┐
    │ Groq API  │     │ Supabase PG  │     │ Firebase Storage │
    │ (LLM)     │     │ checkpoints  │     │ (uploads)        │
    └───────────┘     │ pgvector     │     └─────────────────┘
                      │ user_work    │
                      └──────────────┘
```

### Design principles

- **LLMs are probabilistic; money is not.** Budget totals, wage floors, and indirect cost caps are enforced in `services/budget/compliance.py`.
- **Graphs, not chains.** Drafting uses `StateGraph` with `interrupt()` for human gates and conditional routing after scoring.
- **Visible agent decisions.** `agent_trace` in state and structured logs (`[PlanningAgent]`, `[SectionScoringAgent] score=68 → route=needs_tool_call`) support debugging and portfolio demos.
- **Failover by default.** `RotatingGroq` rotates API keys, applies cooldown on 429s, and retries with exponential backoff.

---

## Agent Orchestration (Drafting Pipeline)

ImpactLink has **two LangGraph flows**, both driven through the unified session API (`/api/session`).

### Flow B: Build from scratch (recommended demo path)

```mermaid
graph TD
    START([User starts /build]) --> INIT[init_slots<br/>VocabExtractor]
    INIT --> SLOTS[slot_filling ⟲<br/>SlotExtractor]
    SLOTS --> CONFIRM[slot_confirm<br/>Human Gate]
    CONFIRM --> PLAN[plan_draft<br/>PlanningAgent]
    PLAN --> DRAFT[draft_sections<br/>3 phased waves]

    subgraph SectionSubgraph["SectionSubgraph (per section)"]
        DRAFT --> SD[SectionDraftAgent]
        SD --> SS[SectionScoringAgent]
        SS -->|approve| OK[done]
        SS -->|targeted_rewrite| SR[SectionRewriteAgent]
        SS -->|needs_tool_call| TOOL[ToolNode<br/>budget / grant req]
        SR --> SS
        TOOL --> SS
        SS -->|escalate| FLAG[flagged]
    end

    OK --> COH[coherence_check<br/>CoherenceAgent]
    COH --> REVIEW[draft_review<br/>Human Gate]
    REVIEW --> SAVE[final_save<br/>Human Gate]
    SAVE --> DONE([complete])
```

#### Graph nodes (`flows/scratch_flow.py`)

| Node | Agent / Service | Purpose |
|---|---|---|
| `init_slots` | `VocabExtractor` | Extract 10–15 funder phrases from grant description |
| `slot_filling` | `SlotExtractor` | Conversational Q&A; maps free text → 10 profile slots |
| `slot_confirm` | Human gate | User confirms collected slot values |
| `plan_draft` | `PlanningAgent` | Produces `DraftingPlan` (priorities, evidence, red flags) |
| `draft_sections` | `SectionSubgraph` × 10 | Phased parallel drafting in 3 dependency waves |
| `coherence_check` | `CoherenceAgent` | Cross-section consistency; up to 2 targeted fixes |
| `draft_review` | Human gate | User edits sections |
| `final_save` | Human gate | Confirm completion |
| `complete` | — | Session finished |

#### SectionSubgraph (`flows/section_subgraph.py`)

Each of the 10 sections in `agents/prompts.SECTIONS` runs:

```
SectionDraftAgent → SectionScoringAgent → route_after_scoring()
  ├─ approve           → section done
  ├─ targeted_rewrite  → SectionRewriteAgent (surgical fix) → re-score
  ├─ needs_tool_call   → check_budget_consistency / get_grant_requirement → rewrite → re-score
  └─ escalate          → flagged for human review (score < 75 after 2 retries)
```

**Phased drafting waves** (`agents/planning_agent.DRAFTING_WAVES`):

| Wave | Sections | Why |
|---|---|---|
| 1 | problem_statement, proposed_solution, target_beneficiaries | Core narrative |
| 2 | goals_and_objectives, evaluation_plan, organizational_capacity, budget_narrative | Structure + budget |
| 3 | executive_summary, sustainability, equity_statement | Summarize prior waves |

Later waves receive a rolling summary (~1200 chars) of earlier sections for consistency.

#### Structured scoring (`agents/scoring_agent.py`)

The scorer returns a `ScoringDecision`, not just a number:

```python
{
  "score": 68,
  "routing": "needs_tool_call",       # approve | targeted_rewrite | needs_tool_call | escalate
  "feedback": "...",
  "targeted_feedback": [
    {"issue": "...", "fix": "...", "severity": "high", "paragraph": 2}
  ],
  "tool_to_call": "check_budget_consistency",
  "cross_section_impact": ["if beneficiary count changes, update executive_summary"]
}
```

Threshold: **75/100**. Max automatic retries: **2**.

#### Deterministic tools (`agents/tools/`)

| Tool | When used |
|---|---|
| `get_grant_requirement` | Injected into every `SectionDraftAgent` prompt |
| `check_budget_consistency` | Routed when budget narrative scores low or scorer requests it |

#### PlanningAgent output (`agents/planning_agent.py`)

```python
DraftingPlan:
  section_priorities: [{key, priority, critical_because, evidence_needed, funder_phrases_to_use}]
  cross_section_dependencies: [{if_section, affects, because}]
  red_flags: [str]
  scoring_rubric_inference: {alignment, vocabulary, specificity, persuasion}
```

### Flow A: Improve existing proposal

```mermaid
graph LR
    A[extract_vocab] --> B[analyze_gaps]
    B --> C[gap_review]
    C --> D[rewrite_sections]
    D --> E[draft_review]
    E --> F[final_save]
```

| Node | Agent | Purpose |
|---|---|---|
| `extract_vocab` | `VocabExtractor` | Funder phrase extraction |
| `analyze_gaps` | `GapAnalysisAgent` | Compare uploaded sections vs grant requirements |
| `gap_review` | Human gate | User confirms gaps / sections to rewrite |
| `rewrite_sections` | `RewriterAgent` + `SectionScoringAgent` | Parallel rewrite with reflection loop |
| `draft_review` | Human gate | Review diffs and edit (`utils/diff.py`) |

> **Note:** The improve flow works best when uploaded proposals are split into canonical section keys. Currently uploads are often stored as a single `uploaded_content` blob — see [Roadmap](#roadmap).

### Shared state (`state/proposal_state.py`)

All agents read/write `ProposalState`, persisted via LangGraph `PostgresSaver`:

```python
ProposalState:
  session_id, user_id, flow              # "improve" | "scratch"
  profile, grant                         # NGO + selected grant
  funder_vocab                           # extracted phrases
  drafting_plan, agent_trace             # scratch flow planning + demo logs
  slots                                  # scratch: conversational slot-filling
  analysis                               # improve: gap analysis
  original_sections, sections, diffs     # section content + tracked changes
  gate                                   # current human interrupt
  retry_counts, flagged_sections         # reflection loop tracking
```

### Human gates

The frontend (`useProposalSession`) calls:

- `POST /api/session` — start flow, runs until first `interrupt()`
- `POST /api/session/{id}/advance` — resume with user input
- `GET /api/session/{id}` — re-hydrate state

| Gate | Frontend page | `advance` payload |
|---|---|---|
| `gap_review` | `Draft.js` | `{confirmed_gaps, user_additions, sections_to_rewrite}` |
| `slot_filling` | `BuildProposal.js` | `{answer, slot_key}` |
| `slot_confirm` | `BuildProposal.js` | `{confirmed: true}` or `{slots: {key: value}}` |
| `draft_review` | Both | `{sections: {key: edited_text}}` |
| `final_save` | `BuildProposal.js` | `{}` |
| `complete` | — | Done |

---

## Codebase Map

```
ImpactLink/
├── impactlink-backend/
│   ├── main.py                    # FastAPI app, all HTTP routes
│   ├── config.py                  # GROQ_API_KEY, model config
│   ├── api/
│   │   └── session.py             # LangGraph session create/advance/status
│   ├── flows/
│   │   ├── scratch_flow.py        # Flow B StateGraph (build from scratch)
│   │   ├── improve_flow.py        # Flow A StateGraph (improve upload)
│   │   └── section_subgraph.py    # Per-section agent pipeline
│   ├── agents/
│   │   ├── planning_agent.py      # PlanningAgent + DraftingPlan + waves
│   │   ├── coherence_agent.py     # Cross-section validation
│   │   ├── scoring_agent.py       # ScoringDecision + routing
│   │   ├── rewriter_agent.py      # Section rewrites (gap + retry + targeted)
│   │   ├── vocab_extractor.py     # Funder vocabulary extraction
│   │   ├── gap_analysis_agent.py  # Improve-flow gap detection
│   │   ├── slot_extractor.py      # Scratch-flow slot Q&A
│   │   ├── budget_injector.py     # Pre-calculated budget table → prompt
│   │   ├── prompts.py             # MASTER_SYSTEM + 10 SECTION definitions
│   │   └── tools/
│   │       ├── budget_consistency.py
│   │       └── grant_requirements.py
│   ├── state/
│   │   └── proposal_state.py      # ProposalState TypedDict
│   ├── services/
│   │   ├── parser.py              # PDF/DOCX → ProposalFeatures (semantic chunking)
│   │   ├── vector_store.py        # pgvector grant search + topic search
│   │   ├── budget/                # Deterministic budget engine
│   │   │   ├── generator.py
│   │   │   ├── compliance.py
│   │   │   ├── personnel.py
│   │   │   └── rules.py
│   │   ├── work_store.py          # Persist drafts/builds/budgets
│   │   ├── auth.py                # Firebase JWT verification
│   │   └── ngo_store.py           # NGO profiles
│   ├── utils/
│   │   ├── llm.py                 # RotatingGroq + KEY_POOL failover
│   │   ├── metrics.py             # Latency instrumentation
│   │   └── diff.py                # Word-level diffs for improve flow
│   ├── scripts/
│   │   ├── evaluate_generation.py # Scoring agent smoke test
│   │   ├── evaluate_logic.py      # Budget engine tests
│   │   └── fetch_grants.py        # Grant ingestion
│   └── Data/                      # Wage indices, eval templates, seed data
│
├── impactlink-frontend/
│   └── src/
│       ├── App.js                 # Routes
│       ├── pages/
│       │   ├── BuildProposal.js   # Scratch flow UI (primary demo)
│       │   ├── Draft.js           # Improve flow UI
│       │   ├── Upload.js          # PDF upload + grant matching
│       │   ├── Budget.js          # Standalone budget builder
│       │   ├── GrantsList.js      # Browse / search grants
│       │   └── Dashboard.js
│       ├── hooks/
│       │   ├── useProposalSession.js  # LangGraph session client
│       │   ├── useUpload.js
│       │   ├── useBudget.js
│       │   └── useWorkStore.js
│       └── services/
│           └── api.js             # Axios client + Firebase auth interceptor
│
├── docker-compose.yml             # Backend container (port 8081)
├── AI_Architecture.md             # Extended architecture notes
└── README.md
```

---

## Data Flow: End-to-End

### 1. Grant discovery (upload path)

```
User uploads PDF
  → POST /api/upload
  → parser.parse_proposal()        # SemanticChunker + Groq structured extraction
  → vector_store.find_similar_grants()  # pgvector cosine similarity
  → Frontend shows matched grants on Dashboard / GrantsList
```

### 2. Build proposal (scratch path — primary demo)

```
User opens /build, selects grant
  → POST /api/session {flow: "scratch", grant, profile}
  → LangGraph runs until slot_filling interrupt
  → User answers questions (POST .../advance per answer)
  → slot_confirm → plan_draft → draft_sections (3 waves) → coherence_check
  → draft_review interrupt (sections returned)
  → User clicks "Confirm Draft & Continue" (advance with edited sections)
  → final_save interrupt
  → User clicks "Complete Session" (advance with {})
  → gate: complete → download PDF client-side
```

### 3. Budget generation

```
User opens /budget
  → POST /api/budget/generate {proposal, max_budget}
  → generator.py: extract rules → personnel → allocate → compliance enforce
  → Returns line items with exact math
  → budget_narrative section receives pre-calculated table via budget_injector
```

---

## API Reference

### Session (drafting)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/session` | Start improve or scratch flow |
| `POST` | `/api/session/{id}/advance` | Advance one gate (5 min timeout) |
| `GET` | `/api/session/{id}` | Get current gate + state |

### Grants & upload

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload` | Parse PDF/DOCX, return proposal + matches |
| `POST` | `/api/match` | Re-match proposal to grants |
| `POST` | `/api/grants/search` | Topic search over grant corpus |

### Budget

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/budget/generate` | Generate compliant line-item budget |
| `POST` | `/api/budget/refine` | Natural-language budget edits |

### Work persistence

| Method | Path | Description |
|---|---|---|
| `GET/POST/PATCH/DELETE` | `/api/work/{drafts\|builds\|budgets}` | Save/load user work |

### Other

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/build/revise` | AI-revise a single section with user feedback |
| `GET` | `/api/metrics` | Aggregated latency stats |
| `GET` | `/api/metrics/{session_id}` | Per-session timing breakdown |

All routes except `/` require Firebase JWT (`Authorization: Bearer <token>`).

---

## How to Run Locally

### Prerequisites

- **Node.js** 18+
- **Python** 3.11+
- **Supabase** project with PostgreSQL + `pgvector` enabled
- **Firebase** project (Auth + Storage)
- **Groq** API key ([console.groq.com](https://console.groq.com))

### 1. Clone and install

```bash
git clone <repo-url>
cd ImpactLink

# Backend
cd impactlink-backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../impactlink-frontend
npm install
```

### 2. Backend environment

Create `impactlink-backend/.env`:

```env
# Required
GROQ_API_KEY=gsk_...                    # comma-separate multiple keys for rotation
DATABASE_URL=postgresql://postgres:...@db....supabase.co:5432/postgres
FIREBASE_STORAGE_BUCKET=your-project.appspot.com

# Optional
ALLOW_ORIGINS=http://localhost:3000
PORT=8000
```

Place `firebase-service-account.json` in `impactlink-backend/` (download from Firebase Console → Project Settings → Service Accounts).

LangGraph auto-creates checkpoint tables on first run via `PostgresSaver.setup()` in `api/session.py`.

### 3. Frontend environment

Create `impactlink-frontend/.env`:

```env
REACT_APP_API_URL=http://localhost:8000

REACT_APP_FIREBASE_API_KEY=...
REACT_APP_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=your-project
REACT_APP_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=...
REACT_APP_FIREBASE_APP_ID=...
```

### 4. Start services

**Terminal 1 — Backend:**

```bash
cd impactlink-backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**

```bash
cd impactlink-frontend
npm start
```

Open [http://localhost:3000](http://localhost:3000), sign in, and navigate to **Build** or **Upload**.

### 5. Docker (backend only)

```bash
# From repo root — requires .env and firebase-service-account.json
docker compose up --build
```

Backend runs at [http://localhost:8081](http://localhost:8081). Point `REACT_APP_API_URL=http://localhost:8081` in the frontend `.env`.

### Troubleshooting

| Issue | Fix |
|---|---|
| `DATABASE_URL environment variable is required` | Add Supabase connection string to backend `.env` |
| `FIREBASE_STORAGE_BUCKET is not set` | Add bucket name to backend `.env` |
| Session advance times out | Drafting 10 sections can take 30–90s; timeout is 5 min in `api.js` |
| CORS errors | Set `ALLOW_ORIGINS=http://localhost:3000` on backend |
| Budget tool silent on Windows | Known emoji `print()` encoding issue in `generator.py`; tool fails open gracefully |
| `401 Unauthorized` | Sign in via Firebase; check frontend Firebase config matches project |

---

## Demo Walkthrough

**Recommended path for portfolio demos: Build from scratch**

1. **Login** → complete NGO profile at `/profile`
2. **Grants** → browse or search; note a grant ID
3. **Build** (`/build`) → select target grant → **Start Building**
4. Answer 7–10 slot questions (org name, mission, problem, activities, etc.)
5. Confirm slots → backend runs:
   - `PlanningAgent` (check logs / browser console for `agent_trace`)
   - Phased section drafting with scoring routes
   - `CoherenceAgent` cross-section check
6. Review sections in right panel → **Confirm Draft & Continue**
7. **Complete Session** → download PDF

**Browser console** shows agent routing during drafting:

```
[ImpactLink Agent Trace]
[PlanningAgent] problem_statement priority=1, evidence=[...]
[SectionScoringAgent] budget_narrative score=68 → route=needs_tool_call
[CoherenceAgent] fixed executive_summary: beneficiary count mismatch
```

**90-second architecture pitch:**

> ImpactLink uses LangGraph to orchestrate grant drafting. A PlanningAgent analyzes the RFP before writing. Section agents draft in dependency waves, each passing through an LLM-as-Judge scorer that returns routing instructions — approve, targeted rewrite, tool call, or escalate. Deterministic tools check budget consistency; a CoherenceAgent validates cross-section alignment. The budget engine is pure Python; the LLM only handles narrative and planning. Human gates pause the graph for review at slot confirmation, draft review, and final save.

---

## Performance & Observability

Instrumentation lives in `utils/metrics.py`. Every HTTP request and agent call can be timed.

```bash
# Aggregated stats
curl http://localhost:8000/api/metrics

# Per-session breakdown (after a build)
curl http://localhost:8000/api/metrics/<session_id>
```

### Benchmarks (local dev, Llama 3.3 70B on Groq)

| Metric | Value |
|---|---|
| Full 10-section scratch draft | ~20–60s (depends on retries) |
| Single LLM call (avg) | ~1s |
| Budget generation pipeline | ~1.3s |
| Slot extraction per question | ~0.3–0.8s |

> Retries are the main latency variable. `budget_narrative` often triggers 1–2 reflection loops when budget table alignment is weak.

---

## Scripts & Evaluation

```bash
cd impactlink-backend

# Scoring agent smoke test
python scripts/evaluate_generation.py

# Budget engine integrity tests
python scripts/evaluate_logic.py

# Ingest grants into Supabase/pgvector
python scripts/fetch_grants.py
```

---

## Roadmap

**Done**
- [x] LangGraph multi-agent drafting pipeline (PlanningAgent, SectionSubgraph, CoherenceAgent)
- [x] Structured scoring routes + deterministic tools
- [x] Supabase + pgvector grant search
- [x] Deterministic budget engine with compliance rules
- [x] Groq key rotation and backoff (`RotatingGroq`)
- [x] Session checkpointing in PostgreSQL

**Next**
- [ ] Section segmenter for improve flow (split `uploaded_content` → canonical keys)
- [ ] Supabase RPC for unified metadata + vector filtering
- [ ] Row Level Security (RLS) for tenant isolation
- [ ] SSE progress streaming during long `draft_sections` runs
- [ ] Batch generation eval harness against gold set (`Data/eval_gold_set.json.template`)
- [ ] PII redaction middleware before LLM calls

---

<div align="center">

**Engineering social impact through intelligent automation**

[Architecture Deep-Dive](./AI_Architecture.md) · [Live Demo](https://impactlink-cbfc5.web.app)

</div>
