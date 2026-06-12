# 🏗️ ImpactLink: System Architecture & AI Topology

This document outlines the architectural decisions, data flows, and state management paradigms powering ImpactLink. The system is designed around a core philosophy: **LLMs are probabilistic, but enterprise software must be deterministic.**

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
    gate:               str                      # human interrupt identifier
    retry_counts:       dict[str, int]
    flagged_sections:   list[str]
```

### 2.2 Scratch Flow Graph Topology
The scratch flow (`flows/scratch_flow.py`) is a LangGraph `StateGraph` with human-in-the-loop gates:

```
init_slots → slot_filling ⟲ → slot_confirm → draft_sections → draft_review → final_save → complete
```

- **VocabExtractor** runs at `init_slots` to pull funder-specific phrases from the grant description.
- **Slot extraction** loops via `slot_filling` until all profile slots are filled, then pauses at `slot_confirm`.

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

### 2.4 Map-Reduce Parallel Drafting
1. **Map**: Static `SECTIONS` config defines 10 mandatory section keys (structural integrity, no LLM guessing).
2. **Execute**: `ThreadPoolExecutor` runs SectionSubgraph instances concurrently (2 workers).
3. **Reduce**: `node_draft_sections` merges `SectionResult` dicts into `ProposalState.sections`.

### 2.5 The "LLM-as-a-Judge" Reflection Loop
Inside each SectionSubgraph, `SectionScoringAgent` evaluates against a 100-point rubric (Alignment, Vocabulary, Specificity, Persuasion). If score &lt; 75 and retries remain, `SectionRewriteAgent` revises using scorer feedback, then re-scores. Sections still below threshold after 2 retries are flagged for human review at `draft_review`.

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