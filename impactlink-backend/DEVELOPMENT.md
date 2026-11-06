# ImpactLink Backend — Development Guide

Local setup, API reference, and operational notes for `impactlink-backend/`.

---

## Prerequisites

- Python 3.11+
- Neon PostgreSQL with `pgvector` enabled
- Firebase project (Auth + Storage)
- OpenAI API key ([OpenAI platform](https://platform.openai.com/api-keys))

---

## Environment

Create `impactlink-backend/.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-6.1-sol
DATABASE_URL=postgresql://neondb_owner:...@ep-example-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
ALLOW_ORIGINS=http://localhost:3000
PORT=8000
```

Place `firebase-service-account.json` in `impactlink-backend/` (Firebase Console → Service Accounts).

LangGraph checkpoint tables are created automatically on first run (`PostgresSaver.setup()` in `api/session.py`).

### Migrating existing data to Neon

ImpactLink's local environments and live backend now use Neon. See
[NEON_MIGRATION.md](./NEON_MIGRATION.md) for the completed cutover and validation.
The steps below document the migration tooling for future use with an empty target.

Create an empty Neon database in a region near the backend. Keep the existing
Supabase `DATABASE_URL` in `impactlink-backend/.env` and add `NEON_DATABASE_URL`
using Neon's **direct** connection string (disable connection pooling in its
Connect dialog). Include `sslmode=require`. Keep credentials out of git/chat.

Install PostgreSQL client tools (`pg_dump`, `pg_restore`) at least as new as the
source server. The migration script also finds Windows PostgreSQL installs.
From `impactlink-backend/`, using the backend virtualenv:

```bash
python scripts/migrate_to_neon.py         # Read-only preflight; target must be empty
# Stop backend writes before copying, and keep them stopped until cutover.
python scripts/migrate_to_neon.py --copy
```

The script copies the public application schema, including grant embeddings,
saved work, and all LangGraph checkpoint tables, using one consistent source
snapshot. It verifies every table's row count and contents before reporting
success. Firebase data remains in Firebase. The source database is never changed.
Dump files are temporary and deleted when the command exits.

After verification, preserve the old URL securely as `SUPABASE_DATABASE_URL`,
then set `DATABASE_URL` to the Neon connection string in both local `.env` files
(repo root for Compose, backend for Python). For runtime, Neon's pooled URL is
supported; keep the direct URL for future migrations. Update the deployed
backend's database secret/environment and restart or redeploy it. Check grant
search, saved work, and resuming an existing proposal session before allowing
writes again. If validation fails before writes resume, restore the old URL.
After new writes reach Neon, switching back requires reconciling those writes.

Database pools release idle connections after 60 seconds, validate connections
before checkout, and disable prepared statements for transaction pooler
compatibility. Neon can sleep during inactivity and wake on the next request.

The repository root contains `neon.ts` and Neon CLI dependencies. `neon deploy`
reconciles the linked branch and pulls its database URLs into the root `.env`.
Keep the backend `.env` synchronized separately when running Python directly.
`npm run build` at the repository root builds the React frontend.

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

Docker Compose reads `${...}` values from a repo-root `.env` file (or the shell
environment). The backend `.env` file is used when running Python directly; it
is not automatically loaded by Compose. Keep API keys out of version control.

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
├── utils/llm.py            # Shared OpenAI model configuration + call metrics
├── utils/metrics.py        # Latency instrumentation
├── load_vectors.py         # Seed grants into PostgreSQL
└── scripts/                # Eval + grant ingestion
```

---

## API reference

### Saved work and matching

Generated builds and revised proposals are saved when they reach draft review.
Find Grants passes the latest section text to `/api/match` automatically, then
saves the resulting grant snapshots with the proposal. Dashboard rows open the
specific saved build, revision, or budget using `?load=<id>`; a proposal's Find
Grants action opens `/grants?proposal=<id>` and runs a fresh match. Budget
refinements update the existing saved budget rather than creating another one.

Updates use `PATCH /api/work/{type}/{id}`. Grant details can be loaded directly
with `GET /api/grants/{grant_id}`, independently of browser matching caches.

Saved-work and session routes require `Authorization: Bearer <Firebase JWT>`.

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

### LLM provider

The backend uses OpenAI's `gpt-6.1-sol` by default. Override `OPENAI_MODEL` to
select another compatible Chat Completions model. Structured-output calls
require a model that supports JSON Schema outputs. Set `OPENAI_API_KEY` as a
local environment variable or in `.env`; in Cloud Run, store it as a Secret
Manager secret and expose it to the service as `OPENAI_API_KEY`. Never commit
the key. API usage is billed separately from ChatGPT subscriptions.

### Benchmarks (local)

The November 5 baseline used two section workers and the current model:

| Metric | Observed |
|---|---|
| Full 10-section draft after slot confirmation | 625s |
| Planning | 58s |
| Section drafting, scoring, and rewrites | 561s |

Section concurrency now defaults to four workers. The three dependency waves
remain sequential, and all scoring, rewrite, and coherence checks remain enabled.
The new schedule can run each wave in one batch instead of two. Actual latency
depends on model response times and API rate limits; the four-worker end-to-end
time needs a new measurement. Metrics record `max_workers` on `draft_sections`.

Set `DRAFT_MAX_WORKERS=1`, `2`, or `3` to lower concurrency if the account is
rate-limited. The maximum is four. Compose forwards this setting; for a direct
Python run, put it in the backend `.env` or process environment.

Build Proposal streams the initial section text into a live preview, including
interleaved sections from parallel workers. Scoring and any required revisions
follow generation; `section_complete` replaces the preview with reviewed text.
The final coherence check supplies the authoritative draft before editing and
approval open. Stream events include `section_start`, `token`, `section_status`,
`section_complete`, `progress`, and the final `complete` response.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `DATABASE_URL environment variable is required` | Add the Neon PostgreSQL URL to `.env` |
| Session advance times out | Full drafting can take over 10 minutes. Slot confirmation uses SSE progress and 15-second heartbeats, with a 90-second idle timeout and a 20-minute overall limit. Recover using the build page's `?session=<id>` URL or Check saved session status. |
| CORS errors | `ALLOW_ORIGINS=http://localhost:3000` |
| `401 Unauthorized` | Sign in via Firebase; check frontend Firebase config |
| Budget tool fails on Windows | Emoji `print()` encoding in `generator.py`; fails open |

---

## Related docs

- [../AI_Architecture.md](../AI_Architecture.md) — agent topology and design
- [EVALUATION.md](./EVALUATION.md) — eval harness and metrics
- [../impactlink-frontend/README.md](../impactlink-frontend/README.md) — frontend setup
