# 🏗️ ImpactLink: System Architecture & AI Topology

This document outlines the architectural decisions, data flows, and state management paradigms powering ImpactLink. The core philosophy: **LLMs are probabilistic, but enterprise software must be deterministic.**

**See also:** [Backend setup](./impactlink-backend/DEVELOPMENT.md) · [Evaluation](./impactlink-backend/EVALUATION.md) · [Project README](./README.md)

---

## 1. High-Level System Context

ImpactLink operates on a serverless, decoupled architecture prioritizing asynchronous throughput and fault tolerance.

- **Client Layer**: React 18 SPA utilizing Server-Sent Events (SSE) for low-latency streaming of AI agent states.
- **Orchestration Layer**: FastAPI (Python) serving as the asynchronous gateway, managing LangGraph state machines and connection pooling.
- **Data Layer**: Supabase (PostgreSQL) handling normalized relational data, `pgvector` embeddings, and Row Level Security (RLS) for tenant isolation.
- **Inference Layer**: Groq LPU clusters running `Llama-3.3-70b-versatile` for high-speed, parallelized generation.

---

## 2. Stateful Orchestration: The LangGraph Topology

Drafting a grant proposal is a high-latency, multi-step process that cannot rely on a single stateless prompt chain. We modeled the drafting process as a **Cyclic State Machine** with parallel execution capabilities.

### 2.1 The State Schema
State is maintained via LangGraph Checkpointers backed by PostgreSQL, ensuring that user sessions can survive network drops and serverless cold starts.

```python
class ProposalState(TypedDict):
    session_id:         str
    flow:               Literal["improve", "scratch"]
    profile:            dict
    grant:              dict
    funder_vocab:       list[str]
    slots:              dict[str, Slot]          # scratch flow only
    analysis:           Optional[dict]         # improve flow only
    original_sections:  dict[str, str]
    sections:           dict[str, SectionResult]
    diffs:              dict[str, list[DiffToken]]
    drafting_plan:      Optional[dict]           # PlanningAgent output (scratch flow)
    agent_trace:        list[dict]               # visible agent decisions for demo
    gate:               str                      # human interrupt identifier
    retry_counts:       dict[str, int]
    flagged_sections:   list[str]
```

### 2.2 Scratch Flow Graph Topology
The scratch flow (`flows/scratch_flow.py`) is a LangGraph `StateGraph` with human-in-the-loop gates:

```
init_slots → slot_filling ⟲ → slot_confirm → plan_draft → draft_sections → coherence_check → draft_review → final_save → complete
```

- **VocabExtractor** runs at `init_slots` to pull funder-specific phrases from the grant description.
- **Slot extraction** loops via `slot_filling` until all profile slots are filled, then pauses at `slot_confirm`.
- **PlanningAgent** (`agents/planning_agent.py`) runs at `plan_draft` before any section is written. It produces a `DraftingPlan` with per-section priorities, evidence needs, cross-section dependencies, and red flags. The plan is stored in `ProposalState.drafting_plan` and injected into each `SectionDraftAgent` prompt.
- **Agent trace** (`ProposalState.agent_trace`) records visible routing decisions for demo and debugging (e.g. `[PlanningAgent] problem_statement priority=1, evidence=[...]`).

### 2.3 SectionSubgraph: Named Per-Section Agents
`node_draft_sections` does not draft inline. It orchestrates parallel runs of `run_section_subgraph()` (`flows/section_subgraph.py`), one per canonical section in `agents/prompts.SECTIONS`:

| Agent | Role |
|---|---|
| **SectionDraftAgent** | Generates initial section content via `SECTION_PROMPT` |
| **SectionScoringAgent** | LLM-as-a-Judge rubric scoring (0–100) |
| **SectionRewriteAgent** | Targeted revision when score &lt; 75 |

Each subgraph logs routing decisions for observability:
```
[SectionScoringAgent] budget_narrative score=68 → route=targeted_rewrite (retry 1/2)
[SectionScoringAgent] budget_narrative score=92 → approve
```

`budget_narrative` additionally receives a pre-calculated table from **BudgetInjector** (deterministic Python engine) before drafting.

### 2.3.1 Deterministic Section Tools
| Tool | File | When invoked |
|---|---|---|
| `get_grant_requirement` | `agents/tools/grant_requirements.py` | Injected into every `SectionDraftAgent` prompt |
| `check_budget_consistency` | `agents/tools/budget_consistency.py` | Scoring routes `budget_narrative` to `needs_tool_call` before rewrite |

### 2.4 Phased Parallel Drafting
`node_draft_sections` drafts in three dependency waves (`DRAFTING_WAVES` in `planning_agent.py`):

| Wave | Sections | Rationale |
|---|---|---|
| 1 | problem_statement, proposed_solution, target_beneficiaries | Core narrative foundation |
| 2 | goals_and_objectives, evaluation_plan, organizational_capacity, budget_narrative | Structure + budget |
| 3 | executive_summary, sustainability, equity_statement | Summarize prior waves |

Within each wave, `ThreadPoolExecutor` runs SectionSubgraph instances concurrently (2 workers). Later waves receive a rolling summary of prior sections (~1200 chars) for cross-section consistency.

### 2.5 Structured Scoring Router
`SectionScoringAgent` returns a `ScoringDecision` — not just a score:

```python
class ScoringDecision(BaseModel):
    score: int
    routing: Literal["approve", "targeted_rewrite", "needs_tool_call", "escalate"]
    targeted_feedback: list[TargetedFeedback]
    tool_to_call: Optional[str]
    cross_section_impact: list[str]
```

`route_after_scoring()` drives the SectionSubgraph loop:
- **approve** — score ≥ 75, section done
- **targeted_rewrite** — `SectionRewriteAgent` fixes only listed issues
- **needs_tool_call** — invokes `check_budget_consistency` or `get_grant_requirement`, then rewrites
- **escalate** — max retries exhausted; flagged for human review

### 2.6 CoherenceAgent
After all sections draft, `node_coherence_check` runs `CoherenceAgent.check()` across the full proposal before `draft_review`.

**Detection method (LLM holistic review, not programmatic diff):**
1. Each section is truncated to ~500 characters in `_sections_digest()` and concatenated into one prompt.
2. A single Groq call (`llama-3.3-70b-versatile`, JSON mode) compares all sections together and returns a `CoherenceReport` with up to 5 structured issues (beneficiary count mismatches, budget vs. narrative gaps, KPI/goal misalignment, etc.).
3. If parsing fails, the agent fails open (`coherent=True`) so drafting is not blocked.

**Fix loop (max 2):**
- `CoherenceAgent.top_fixes()` sorts issues by severity (`high` → `medium` → `low`) and takes the top 2.
- For each issue, `targeted_retry_rewrite()` revises only the flagged section using the issue text as feedback.
- Decisions are appended to `agent_trace` for demo/debug visibility.

**Trade-offs:** This is one cheap cross-section pass after parallel drafting, but it is probabilistic — it can miss subtle contradictions or hallucinate false positives. A future upgrade could add deterministic checks (e.g. regex on dollar amounts, beneficiary counts) before the LLM pass.

## 3. The Hybrid RAG Pipeline (Supabase + pgvector)
Standard Semantic RAG is insufficient for grant matching, as funding relies heavily on hard constraints (e.g., geographic boundaries, maximum award ceilings).

### 3.1 Tiered Ingestion & Chunking
**Semantic Splitting**: Documents are chunked using percentile-based semantic splitters rather than arbitrary character counts, preserving complete thoughts and paragraphs.

**Metadata Tagging**: During ingestion, an LLM extracts key parameters (Region, Focus Area, Budget constraints) and stores them as standard relational columns alongside the `pgvector` embeddings.

<!-- ### 3.2 Unified Query Execution
When a user searches for grants, the system executes a single, atomic PostgreSQL query:

**Pre-filtering**: Standard SQL `WHERE` clauses immediately filter out non-compliant grants based on hard constraints (e.g., `WHERE region = 'Kenya' AND max_award >= 50000`).

**Semantic Ranking**: The `pgvector` cosine similarity (`<=>`) operation is executed only on the pre-filtered subset, drastically reducing computational overhead and ensuring sub-50ms latency. -->

## 4. The Deterministic Financial Engine
Budgets cannot suffer from LLM hallucinations. ImpactLink completely decouples financial intent from mathematical calculation.

### 4.1 Intent Parsing
The `Budget Agent` operates in a strictly constrained JSON-mode. It is only permitted to output intents and quantities (e.g., `{"item": "Field Worker", "quantity": 3, "duration_months": 12}`).

### 4.2 Python Validation Core
The JSON payload is passed to a rigid Python engine (`services/budget/compliance.py`).
- **Localization:** It cross-references the requested intent against a local database of minimum wage floors and Cost-of-Living (CoL) indices for the target region.
- **Rule Enforcement:** It automatically calculates and applies the exact allowed percentages for Overhead/Indirect Costs.
- **Proportional Scaling:** If the requested items exceed the grant's maximum award, the engine applies an algebraic scaling algorithm to reduce line items proportionally, ensuring the final budget is mathematically perfect and strictly compliant.

<!-- <!-- ## 4. Resiliency & Infrastructure Design
To maintain production-grade uptime despite external API volatility: -->

- **Provider-Agnostic Failover:** A custom LLM wrapper intercepts HTTP 429 (Rate Limit) and 503 (Service Unavailable) errors. It automatically rotates to standby API keys or alternative inference providers using an exponential backoff strategy, guaranteeing transaction completion.
- **Clock-Skew Mitigation:** Cross-region serverless deployments often face JWT validation failures due to microsecond clock drifts. Custom authentication middleware implements a 1.5-second skew tolerance to ensure stable authorization flows.
<!-- - **Stateless Containers:** The FastAPI application runs in isolated Docker containers via Google Cloud Run, allowing it to scale from 0 to 100+ instances concurrently without state collision, relying entirely on the PostgreSQL Checkpointers for memory.    -->

## 5. Phase 2 Architecture: Enterprise Scale (Roadmap)
To transition from a high-performance prototype to an enterprise-grade platform, the following architectural shifts are currently on the roadmap:

### 5.1 Push-Down Compute (RPC Vector Filtering)
Currently, vector similarity and metadata filtering (e.g., matching grant regions) are handled partially at the application layer. The roadmap includes migrating this to a Supabase Remote Procedure Call (RPC). This will allow the database to execute pre-filtering via SQL `WHERE` clauses before running the `pgvector` cosine similarity (`<=>`), drastically reducing memory overhead on the FastAPI servers.

### 5.2 Strict Database Tenancy (RLS)
While data isolation is currently managed via application logic (validating `user_id` on requests), the system will migrate to PostgreSQL Row Level Security (RLS). This pushes tenancy verification directly to the database engine, eliminating the risk of application-layer data leaks.

### 5.3 PII Redaction Middleware
To comply with strict NGO data privacy standards, a middleware layer utilizing regex and NLP parsing will be introduced to scrub Personally Identifiable Information (Emails, Phone Numbers, Names) from all JSON payloads before they are transmitted to the LLM inference providers.