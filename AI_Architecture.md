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
    ngo_context: dict             # Ground truth extracted from uploaded docs
    grant_requirements: dict      # Rules extracted from the Funder's RFP
    draft_sections: List[Section] # Actively mutating array of proposal sections
    evaluation_scores: dict       # Real-time scoring from the Judge Agent
    current_node: str             # Pointer for session resumption

```

### 2.2 Map-Reduce Parallel Drafting
Instead of drafting linearly, the graph employs a distributed Map-Reduce pattern governed by a strict orchestration configuration:
1. **Map (Deterministic Planning)**: Rather than relying on a probabilistic LLM to guess the document structure, the Graph Orchestrator utilizes a static, compliance-driven configuration (`SECTIONS`) to segment the proposal into mandatory independent nodes (e.g., Executive Summary, Methodology, Sustainability). This guarantees structural integrity and saves inference latency.
2. **Execute (Parallel Generation)**: Thread-safe executor nodes draft these mapped sections concurrently against the Groq API, maintaining their own localized state.
3. **Reduce (State Assembly)**: The final graph node acts as the synthesizer, compiling the parallel outputs and merging the localized state dictionaries into a cohesive, structurally sound document ready for PDF export.

### 2.3 The "LLM-as-a-Judge" Reflection Loop
Every parallel branch includes an autonomous verification step. A dedicated `Scoring Agent` evaluates the generated text against a 100-point rubric. If a section scores $< 75$, the node transitions to a `Rewrite Agent` with the critique appended to the context window, explicitly preventing subpar drafts from reaching the user.

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