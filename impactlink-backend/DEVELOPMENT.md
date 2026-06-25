# ImpactLink Backend — Development Guide

Local setup, API reference, and operational notes for `impactlink-backend/`.

---

## Prerequisites

- Python 3.11+
- Supabase PostgreSQL with `pgvector` enabled
- Firebase project (Auth + Storage)
- Groq API key ([console.groq.com](https://console.groq.com))

---

## Environment

Create `impactlink-backend/.env`:

```env
GROQ_API_KEY=gsk_...                    # comma-separate for key rotation
DATABASE_URL=postgresql://postgres:...@db....supabase.co:5432/postgres
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
ALLOW_ORIGINS=http://localhost:3000
PORT=8000
```

Place `firebase-service-account.json` in `impactlink-backend/` (Firebase Console → Service Accounts).

LangGraph checkpoint tables are created automatically on first run (`PostgresSaver.setup()` in `api/session.py`).

---

## Run

```bash
cd impactlink-backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker compose up --build   # from repo root, port 8081
```

**Note:** `docker-compose.yml` starts the **backend only** (port 8081). The frontend service block is commented out because the live demo runs on [Firebase Hosting](https://impactlink-cbfc5.web.app). For local full-stack development, run the frontend separately:

```bash
cd impactlink-frontend && npm install && npm start   # http://localhost:3000
```

Set `REACT_APP_API_URL=http://localhost:8000` in `impactlink-frontend/.env` (or `http://localhost:8081` if using Docker backend).

### CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR:

- `python scripts/evaluate_logic.py --offline` — deterministic budget compliance (no API keys)
- `python scripts/evaluate_retrieval.py` — offline keyword retrieval against `Data/eval_grants_catalog.json`

Full LLM-backed evals (`evaluate_all.py --with-pipeline`) run locally; see [EVALUATION.md](./EVALUATION.md).

---

## Codebase map

```
impactlink-backend/
├── main.py                 # FastAPI routes
├── api/session.py          # LangGraph session create/advance/status
├── flows/
│   ├── scratch_flow.py     # Build-from-scratch StateGraph
│   ├── improve_flow.py     # Improve-upload StateGraph
│   └── section_subgraph.py # Per-section draft → score → rewrite
├── agents/                 # Planning, scoring, coherence, slots, tools
├── state/proposal_state.py # ProposalState TypedDict
├── services/
│   ├── vector_store.py     # pgvector search + topic rerank
│   ├── parser.py           # PDF/DOCX parsing
│   └── budget/             # Deterministic budget engine
├── utils/llm.py            # RotatingGroq key pool
├── utils/metrics.py        # Latency instrumentation
├── load_vectors.py         # Seed grants into PostgreSQL
└── scripts/                # Eval + grant ingestion
```

---

## API reference

All routes except `/` require `Authorization: Bearer <Firebase JWT>`.

### Session (drafting)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/session` | Start `improve` or `scratch` flow |
| `POST` | `/api/session/{id}/advance` | Advance one gate (5 min timeout) |
| `GET` | `/api/session/{id}` | Current gate + state |

### Grants & upload

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload` | Parse PDF/DOCX, return matches |
| `POST` | `/api/match` | Re-match proposal to grants |
| `POST` | `/api/grants/search` | Topic search over corpus |

### Budget

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/budget/generate` | Generate compliant line-item budget |
| `POST` | `/api/budget/refine` | Natural-language budget edits |

### Other

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/build/revise` | AI-revise one section with user feedback |
| `GET` | `/api/metrics` | Aggregated latency stats |
| `GET` | `/api/metrics/{session_id}` | Per-session timing breakdown |
| `GET/POST/PATCH/DELETE` | `/api/work/{drafts\|builds\|budgets}` | Persist user work |

### Human gates

| Gate | `advance` payload |
|---|---|
| `slot_filling` | `{answer, slot_key}` |
| `slot_confirm` | `{confirmed: true}` or `{slots: {key: value}}` |
| `gap_review` | `{confirmed_gaps, sections_to_rewrite}` |
| `draft_review` | `{sections: {key: edited_text}}` |
| `final_save` | `{}` |

---

## Data flows

### Grant discovery

```
POST /api/upload → parser.parse_proposal() → vector_store.find_similar_grants()
```

### Build proposal (scratch)

```
POST /api/session {flow: "scratch"}
  → slot_filling → slot_confirm → plan_draft → draft_sections → coherence_check
  → draft_review → final_save → complete
```

### Budget

```
POST /api/budget/generate → generator.py (rules → personnel → allocate → compliance)
```

---

## Grant data pipeline

| Script | Purpose |
|---|---|
| `scripts/enrich_grants.py` | Scrape grants.ca.gov detail pages → rich JSON |
| `load_vectors.py` | Embed grants → PostgreSQL `grants` table |
| `scripts/sync_eval_grants_from_db.py` | Export DB → `Data/eval_grants_catalog.json` |
| `scripts/fetch_grants.py` | Bulk data.ca.gov API (field mapping needs fix) |

**Production DB** (114 grants) was loaded via `enrich_grants.py` + `load_vectors.py`, not `fetch_grants.py`.

Do **not** run `load_vectors.py` on broken `fetch_grants.py` output — it overwrites good data.

---

## Observability

```bash
curl http://localhost:8000/api/metrics
curl http://localhost:8000/api/metrics/<session_id>
```

Instrumentation: `utils/metrics.py` (decorator + `/api/metrics`).

### Benchmarks (local, Groq Llama 3.3 70B)

| Metric | Typical |
|---|---|
| Full 10-section draft | ~37–108s (avg ~81s) |
| Single LLM call | ~1–2s |
| Budget generation | ~1.3s |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `DATABASE_URL environment variable is required` | Add Supabase URL to `.env` |
| Session advance times out | Drafting can take 30–90s; client timeout is 5 min |
| CORS errors | `ALLOW_ORIGINS=http://localhost:3000` |
| `401 Unauthorized` | Sign in via Firebase; check frontend Firebase config |
| Budget tool fails on Windows | Emoji `print()` encoding in `generator.py`; fails open |

---

## Related docs

- [../AI_Architecture.md](../AI_Architecture.md) — agent topology and design
- [EVALUATION.md](./EVALUATION.md) — eval harness and metrics
- [../impactlink-frontend/README.md](../impactlink-frontend/README.md) — frontend setup
