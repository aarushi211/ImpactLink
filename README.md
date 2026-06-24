<div align="center">

# ⬡ ImpactLink

**AI grant intelligence for NGOs** — find grants, draft proposals, build compliant budgets.

[![Live Demo](https://img.shields.io/badge/Demo-Live-6C63FF?style=for-the-badge)](https://impactlink-cbfc5.web.app)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-0D0D1A?style=for-the-badge&logo=fastapi&logoColor=6C63FF)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React-0D0D1A?style=for-the-badge&logo=react&logoColor=6C63FF)](https://reactjs.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-0D0D1A?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)

[**Live Demo**](https://impactlink-cbfc5.web.app) · [**Architecture**](./AI_Architecture.md) · [**Setup**](./impactlink-backend/DEVELOPMENT.md) · [**Evaluation**](./impactlink-backend/EVALUATION.md)

</div>

---

## What it does

ImpactLink helps nonprofits **match grants**, **draft multi-section proposals**, and **generate rule-compliant budgets**. The core idea: **LangGraph orchestrates probabilistic LLM agents**; **Python enforces deterministic budget math**.

| Capability | Summary |
|---|---|
| Grant search | Semantic search over 114 CA grants (`pgvector` + LLM rerank) |
| Build proposal | Slot-filling → PlanningAgent → 10 sections with score/route/retry loops |
| Budget engine | Wage floors, indirect caps, personnel modeling — no LLM math |
| Improve flow | Gap analysis + targeted rewrites on uploaded proposals |

**Stack:** React · FastAPI · LangGraph · Groq (Llama 3.3 70B) · Supabase PostgreSQL · Firebase Auth

---

## Architecture (high level)

```
React SPA  ──REST──▶  FastAPI
                        ├── LangGraph sessions (scratch + improve flows)
                        ├── pgvector grant search
                        └── Budget engine (deterministic)
              Groq API · Supabase PG · Firebase Storage
```

**Scratch flow:** slot Q&A → plan → draft 10 sections (scored + retried) → coherence check → human review → PDF.

Details: [AI_Architecture.md](./AI_Architecture.md)

---

## Results at a glance

Evaluated on 3 hand-crafted NGO scenarios against a 114-grant California corpus (June 2026, local dev).

| Area | Result |
|---|---|
| Budget compliance tests | **5/5 pass** |
| Grant retrieval (live) | **P@5 0.47 · R@5 0.78** |
| Full draft pipeline | **3/3** scenarios, 10 sections, ~81s avg |
| Scorer discrimination | Weak draft **20** vs strong **92** |

Methodology and commands: [impactlink-backend/EVALUATION.md](./impactlink-backend/EVALUATION.md)

---

## Quick start

```bash
git clone <repo-url> && cd ImpactLink

# Backend (see DEVELOPMENT.md for .env)
cd impactlink-backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd impactlink-frontend && npm install && npm start
```

Open [localhost:3000](http://localhost:3000) → sign in → **Build** or **Grants**.

Full setup (Supabase, Firebase, Groq keys): **[impactlink-backend/DEVELOPMENT.md](./impactlink-backend/DEVELOPMENT.md)**

---

## Demo path (~3 min)

1. **Grants** — search *"urban greening Lower Los Angeles River disadvantaged communities"*
2. **Build** — select a grant → answer slot questions → watch agent orchestration panel
3. Review 10 drafted sections → **Confirm Draft & Continue** → download PDF

---

## Documentation

| Doc | Audience |
|---|---|
| [AI_Architecture.md](./AI_Architecture.md) | Agents, LangGraph topology, scoring routes, RAG, budget engine |
| [impactlink-backend/DEVELOPMENT.md](./impactlink-backend/DEVELOPMENT.md) | Local setup, API reference, data flows, troubleshooting |
| [impactlink-backend/EVALUATION.md](./impactlink-backend/EVALUATION.md) | Eval harness, metrics, grant data pipeline |
| [impactlink-frontend/README.md](./impactlink-frontend/README.md) | Frontend structure and env |

---

<div align="center">

**Engineering social impact through intelligent automation**

</div>
