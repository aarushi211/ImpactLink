# ImpactLink — Evaluation Guide

Repeatable metrics for budget logic, grant retrieval, and multi-agent drafting.

## Current regression verification

Latest local checks on November 5, 2026: **144 backend tests**, **63 frontend
tests across 19 suites**, and the frontend production build passed. These checks
cover regression behavior, not independent proposal quality or deployed-service
reliability. The frontend run excludes the default `App.test.js` scaffold and
used `CI=true`.

```bash
# From impactlink-backend, in its virtual environment
python -m unittest discover -s tests -p '*_test.py'

# From impactlink-frontend
npm test -- --watchAll=false --runInBand --testPathIgnorePatterns=src/App.test.js
npm run build
```

Coverage includes budget calculations/scope changes, eligibility and refresh
logic, application limits, AI-policy enforcement, privacy/provider-payload
checks, streamed requests, checkpoint recovery, saved-work workflows and
full-text consistency statuses. The current deterministic budget evaluation
contains eight synthetic checks; the older five-case result below belongs to
the previous engine.

CI currently runs the offline budget/retrieval scripts, not these complete
regression suites. [Future work](../FUTURE_WORK.md#4-independent-evaluation-and-broader-automated-checks)
tracks broader CI, human review and independent datasets.

Scenarios: `Data/eval_scenarios.json` (3 hand-crafted NGO profiles aligned to grants in PostgreSQL).

---

## Historical results (June 2026, local dev)

These are retained historical measurements from three synthetic scenarios and
the earlier 114-grant California corpus. They have **not** been re-established
for the current sources, eligibility filters, budget engine, model configuration,
privacy checks or consistency review. Do not present them as current quality or
latency benchmarks. Three scenarios do not support broad accuracy claims.

| Suite | Metric | Result |
|---|---|---|
| Budget engine | Pass rate | **5/5 (100%)** |
| Retrieval (live pgvector + LLM rerank) | Mean P@5 / R@5 | **0.47 / 0.78** |
| Retrieval (offline keyword) | Mean P@5 / R@5 | **0.47 / 0.78** |
| ScoringAgent smoke test | Weak vs strong draft | **20 vs 92** |
| Pipeline (full, 10 sections) | Completion | **3/3**, ~81s avg |
| Pipeline (quick, 3 sections) | Completion | **3/3**, ~18s avg |

### Per-scenario live retrieval

| Scenario | P@5 | R@5 | Primary grant |
|---|---|---|---|
| `la_urban_forestry` | 0.80 | 0.67 | Prop 4 Wildfire & Forest Resilience (`154743`) |
| `ca_library_community` | 0.20 | 1.00 | LSTA Community Impact Grants (`86477`) |
| `la_community_resilience` | 0.40 | 0.67 | BH UWC Consolidated Grant (`149622`) |

> LLM-as-Judge scores on pipeline runs cluster around 92/100 on synthetic inputs — useful for regression, not a fundability claim.

---

## Run evals

```bash
cd impactlink-backend

# CI-safe: deterministic budget + offline retrieval (no API keys)
python scripts/evaluate_logic.py --offline
python scripts/evaluate_retrieval.py

# Fast: budget + offline retrieval (no LLM pipeline)
python scripts/evaluate_all.py

# Live retrieval (needs DATABASE_URL + OPENAI_API_KEY)
python scripts/evaluate_retrieval.py --live

# Budget + retrieval + quick pipeline
python scripts/evaluate_all.py --with-pipeline --quick

# Individual suites
python scripts/evaluate_logic.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_pipeline.py --all
python scripts/evaluate_pipeline.py --all --quick
python scripts/evaluate_generation.py
```

Reports → `Data/eval_results/*.json`. LLM runs use the configured OpenAI model; monitor API spend in the OpenAI platform dashboard.

---

## Scripts

| Script | Purpose |
|---|---|
| `evaluate_all.py` | Combined suite |
| `evaluate_logic.py` | Budget engine deterministic tests |
| `evaluate_retrieval.py` | Offline + `--live` pgvector metrics |
| `evaluate_pipeline.py` | Full scratch-flow on fixed scenarios |
| `evaluate_generation.py` | Scorer weak vs strong smoke test |
| `sync_eval_grants_from_db.py` | Export DB → `eval_grants_catalog.json` |
| `eval_common.py` | Shared loaders and metrics helpers |

---

## Grant data for eval

| Source | Role |
|---|---|
| PostgreSQL `grants` table | Current corpus for live retrieval; source records are not independent relevance labels |
| `Data/eval_grants_catalog.json` | Offline retrieval (sync from DB) |
| `Data/eval_scenarios.json` | NGO slots + grant metadata + `relevant_grant_ids` |

Refresh the offline snapshot after source updates:

```bash
python scripts/sync_eval_grants_from_db.py
```

Routine source refreshes use `scripts/refresh_grants.py`, with preview mode by
default and `--apply` for writes. See [Development](./DEVELOPMENT.md#grant-data-pipeline).
The offline catalog and scenario labels can become stale independently; exporting
the database does not validate relevance labels or create a held-out benchmark.

---

## Demo search queries

Reproduce retrieval eval on `/grants`:

- *Urban greening Lower Los Angeles River disadvantaged communities*
- *Library community literacy LSTA California*
- *Baldwin Hills climate resilience disadvantaged communities*

---

## What we measure (and what we don't)

| Measured | Not measured (yet) |
|---|---|
| Budget math / compliance | Real grant win rate |
| Retrieval P@K / R@K on labeled scenarios | Human expert fundability ratings |
| Pipeline completion + latency | Improve-flow section segmentation |
| Scorer discrimination (smoke test) | Absolute quality on real proposals |

---

## Related

- [DEVELOPMENT.md](./DEVELOPMENT.md) — setup and API
- [../AI_Architecture.md](../AI_Architecture.md) — agent design
