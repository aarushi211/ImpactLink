<div align="center">

# ⬡ ImpactLink

### AI Grant Intelligence Platform for NGOs
*Find grants · Write proposals · Build budgets*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-0D0D1A?style=for-the-badge&logo=fastapi&logoColor=6C63FF)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React-0D0D1A?style=for-the-badge&logo=react&logoColor=6C63FF)](https://reactjs.org/)
[![Supabase](https://img.shields.io/badge/Database-Supabase-0D0D1A?style=for-the-badge&logo=supabase&logoColor=6C63FF)](https://supabase.com/)
[![Groq](https://img.shields.io/badge/Inference-Groq-0D0D1A?style=for-the-badge&logoColor=6C63FF)](https://groq.com/)

[**🎥 Live Demo**](https://impactlink-cbfc5.web.app) | [**🏗️ AI Architecture Deep-Dive**](./AI_Architecture.md) 
 </div>

---

## 🌟 Overview

**ImpactLink** is a production-grade AI platform designed to bridge the resource gap for under-served NGOs. By combining **Stateful Agentic Workflows** with **Deterministic Financial Logic**, it transforms a complex 40-hour grant application cycle into a streamlined, high-quality output in minutes. 

This repository demonstrates enterprise-level engineering, featuring **Reflection Patterns**, **Graph Orchestration**, and **Localized RAG** architecture.

---

## ⚡ Performance Metrics

All latency numbers below are **real measurements** captured via the built-in instrumentation layer (`utils/metrics.py`). Timings were recorded on a local development environment using **Llama 3.3 70B** on Groq LPU inference.

### System-Level Summary
| Metric | Measured Value |
|---|---|
| **Full 10-Section Proposal (Scratch)** | **19.7s** end-to-end (parallel drafting + scoring + retries) |
| **3-Section Rewrite (Improve)** | **2.8s** end-to-end (parallel rewrite + scoring) |
| **Average LLM Call Latency** | **0.99s** (Groq LPU, Llama 3.3 70B) |
| **Slot Extraction (per question)** | **0.31 – 0.78s** including JSON parsing |
| **Budget Generation Pipeline** | **1.33s** (rule extraction + personnel + allocation) |
| **API Request Overhead** | **< 50ms** for data endpoints |

### Pipeline Step Latencies (Measured)

#### Flow A: Improve Existing Proposal
| Step | Category | Duration | Details |
|---|---|---|---|
| Extract Funder Vocab | Agent → Node | 0.71s | 1 LLM call (0.67s) + JSON parse |
| Gap Analysis | Agent → Node | 1.34s | 1 LLM call (1.30s) + JSON parse |
| Rewrite Section (×3 parallel) | Node | 2.84s wall-clock | 3 sections rewritten concurrently |
| ↳ `executive_summary` | Agent + Score | 1.43s | Score: 85/100, 0 retries |
| ↳ `evaluation_plan` | Agent + Score | 1.71s | Score: 88/100, 0 retries |
| ↳ `program_description` | Agent + Score | 1.40s | Score: 85/100, 0 retries |
| **Total Session (create → review)** | **API** | **5.48s** | |

#### Flow B: Scratch Proposal (10 Sections)
| Step | Category | Duration | Details |
|---|---|---|---|
| Init Slots + Vocab | Node | 0.001s | No grant description → instant |
| Slot Filling (7 rounds) | Agent | 0.28 – 0.78s each | LLM extraction + JSON parse per answer |
| Draft Sections (×10 parallel) | Node | **19.68s** wall-clock | 2 workers, 10 sections |
| ↳ `executive_summary` | Draft + Score | 2.55s | Score: 85, 0 retries |
| ↳ `problem_statement` | Draft + Score | 3.46s | Score: 87, 0 retries |
| ↳ `proposed_solution` | Draft + Score | 3.42s | Score: 92, 0 retries |
| ↳ `target_beneficiaries` | Draft + Score | 2.90s | Score: 88, 0 retries |
| ↳ `budget_narrative` | Draft + Score + **2 Retries** | **9.80s** | Score: 70→70→92 |
| ↳ `evaluation_plan` | Draft + Score | 3.51s | Score: 85, 0 retries |
| ↳ `sustainability` | Draft + Score | 2.75s | Score: 85, 0 retries |
| ↳ `equity_statement` | Draft + Score | 2.69s | Score: 85, 0 retries |
| **Total Session (draft advance)** | **API** | **19.99s** | |

#### Budget Generation Pipeline
| Step | Duration | Details |
|---|---|---|
| Extract Grant Rules | Service | ~0.3s | LLM structured output |
| Extract Personnel | Service | 0.29 – 0.38s | 4 roles identified |
| Secondary Allocation | LLM | 0.94s | Structured output with constraints |
| Compliance Enforcement | CPU | <10ms | Deterministic Python logic |
| **Total Pipeline** | **Service** | **1.33s** | |

> **Key Insight — Self-Correction Cost:** The `budget_narrative` section triggered **2 automatic retries** (scored 70 → 70 → 92), adding ~6.3s. Sections passing on the first attempt average **2.5 – 3.5s** each. The reflection loop is the primary latency variable.

---

## 🏗️ Architectural Topology: Stateful Reflection

Instead of a linear prompt chain, ImpactLink utilizes a **LangGraph StateGraph** to manage complex, multi-turn proposal drafting. This architecture enables **Map-Reduce parallelism** for section generation and iterative **Self-Correction (Reflection)**.

```mermaid
graph TD
    A[User Prompt] --> B[VocabExtractor: init_slots]
    B --> C[slot_filling: Conversational Q&A]
    C -->|All slots filled| D[slot_confirm: Human Gate]
    D --> P[PlanningAgent: plan_draft]
    P --> E[node_draft_sections: 3 Phased Waves]

    subgraph "SectionSubgraph per section"
        E --> F[SectionDraftAgent]
        F --> G[SectionScoringAgent]
        G -->|score ≥ 75| H[Section Approved]
        G -->|score < 75| I[SectionRewriteAgent]
        I --> G
    end

    H --> J[draft_review: Human Gate]
    J --> K[final_save]
    K --> L[complete: PDF Export]
```

## 🛠️ Core Engineering Challenges & Solutions
### 1. The "Hallucination-Proof" Budget Engine
- **Challenge:** LLMs are probabilistic, but financial budgets require deterministic exactness.
- **Solution:** Built a **Deterministic-Agentic Hybrid**. The LLM only parses intent (e.g., "Add a Project Manager"). That intent is fed into a rigid Python engine that enforces real-world constraints like local minimum wage laws and proportional indirect cost caps. **Math is always perfect; AI is only the interface.**

### 2. Robust RAG & Relational Search
- **Challenge:** Most RAG implementations fail on long documents, and NGOs need grants that match hard metadata (e.g., Region: "Kenya"), not just semantic similarity.
- **Solution:**
    - **Tiered Retrieval:** Uses `SemanticChunker` (percentile-based) to split documents contextually.
    - **Unified Querying:** Migrated to **Supabase (PostgreSQL + `pgvector`)**. This enables SQL queries that filter by relational metadata first, then rank by semantic similarity in a single database round-trip.
    - **Idempotent Lifecycle:** Handled via PostgreSQL `ON CONFLICT`, ensuring grant updates or re-indexing operations are atomic and never duplicate data.

### 3. Output Observability: LLM-as-a-Judge
- **Challenge:** Zero-shot drafts often lack the nuance required for high-stakes grant writing.
- **Solution:** Every generated proposal section is audited by an autonomous **Scoring Agent** using a strict 100-point rubric assessing Alignment, Vocabulary, Specificity, and Persuasion. Sections scoring below 75 are automatically sent back to the Rewrite Node with targeted feedback.

### 4. Production Security & Resilience
- **Challenge:** Public LLM APIs have strict rate limits, and serverless architectures face cold-start/clock-skew issues.
- **Solution:** 
    - **Provider-Agnostic Failover:** Architected a custom provider factory (`utils/llm.py`) that handles rate-limiting and service disruptions with exponential backoff, ensuring drafting sessions are highly available.
    - **Auth Resilience:** Custom `verify_token` middleware handles 1.5s clock-skew retries for Firebase JWTs, critical for cross-region serverless deployments.

<!-- ## 🔒 Security & Data Privacy
To ensure NGO data integrity and compliance with donor privacy standards:
- **PII Redaction:** Implemented a pre-processing middleware that scrubs Personally Identifiable Information (PII) before sending payloads to LLM providers.
- **Data Isolation:** Utilized **Supabase Row Level Security (RLS)** to ensure that NGO mission statements and financial data are cryptographically isolated between organizations.
- **Stateless Inference:** The AI layer is architected to be stateless; user-uploaded grant documents are never used for model training or stored beyond the active RAG session context. -->

## 📁 Project Structure
```bash
impactlink/
├── impactlink-backend/
│   ├── agents/          # Multi-agent specialized logic (Draft, Build, Scoring)
│   ├── api/             # FastAPI routers and SSE implementations
│   ├── services/        # Core logic: Vector store, Budget engine, NGO matching
│   ├── utils/           # Provider failover, Retry logic, and formatting
│   ├── Data/            # Seed data and localization indices
│   └── main.py          # Application entry point
└── impactlink-frontend/
    └── src/
        ├── pages/       # Dashboard and feature-specific views
        ├── hooks/       # AI state management (SSE, Drafting, Budgets)
        └── services/    # Centralized API logic (Axios)
```

### ⚙️ Setup & Verification
**Prerequisites**
- Node.js (v18+)
- Python (3.11+)
- Docker (Optional)
- Environment Variables: `GROQ_API_KEY`, `DATABASE_URL`, `FIREBASE_STORAGE_BUCKET`

**Local Development**
```bash
# 1. Start the Backend
cd impactlink-backend
pip install -r requirements.txt
python main.py

# 2. Start the Frontend
cd ../impactlink-frontend
npm install
npm run start
```

**Automated Testing (E2E Pipeline)**
You can run the full integration test pipeline to verify the AI stack (PDF Parse -> RAG Search -> Scoring -> Budget Logic):
```bash
cd impactlink-backend
python testpipeline.py
```

### 📈 Roadmap: Enterprise Hardening (Next Steps)
[x] Production Migration: Transition from flat JSON/ChromaDB to Supabase + Cloud Run.<br>
[x] API Resilience: Implemented robust failover handling for inference rate limits.<br>
[ ] Database-Level RAG Execution: Migrating application-layer Python vector filtering into a unified Supabase RPC function to process hard metadata constraints (e.g., Region) and pgvector similarity in a single atomic database query.<br>
[ ] Enterprise Data Security: Implementing Supabase Row Level Security (RLS) for cryptographic tenant isolation, alongside a custom PII Redaction Middleware to scrub sensitive NGO data before payloads reach the LLM inference layer.<br>
[ ] Graph-Based RAG: Transitioning to Knowledge Graphs to map funder-to-NGO relationships visually.<br>
[ ] Financial API Integrations: Direct integration with NGO-specific accounting software for real-time spend tracking.<br>

<div align="center">
<h3>Engineering Social Impact through Intelligent Automation</h3>
<p><i>A production-grade AI platform for NGOs.</i></p>
</div>