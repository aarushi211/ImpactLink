# ImpactLink — Evaluation Guide

Repeatable metrics for budget logic, grant retrieval, and multi-agent drafting.

Scenarios: `Data/eval_scenarios.json` (3 hand-crafted NGO profiles aligned to grants in PostgreSQL).

---

## Latest results (June 2026, local dev)

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

# Fast: budget + offline retrieval (no LLM)
python scripts/evaluate_all.py

# Live retrieval (needs DATABASE_URL + GROQ_API_KEY)
python scripts/evaluate_retrieval.py --live

# Budget + retrieval + quick pipeline
python scripts/evaluate_all.py --with-pipeline --quick

# Individual suites
python scripts/evaluate_logic.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_pipeline.py --all              # ~4 min
python scripts/evaluate_pipeline.py --all --quick      # ~1 min
python scripts/evaluate_generation.py
```

Reports → `Data/eval_results/*.json`. LLM runs print `[EVAL]` messages for Groq key rotation and 429 retries.

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
| PostgreSQL `grants` table | Ground truth for live eval (114 CA grants) |
| `Data/eval_grants_catalog.json` | Offline retrieval (sync from DB) |
| `Data/eval_scenarios.json` | NGO slots + grant metadata + `relevant_grant_ids` |

Refresh catalog after DB reload:

```bash
python scripts/sync_eval_grants_from_db.py
```

**Note:** `scripts/fetch_grants.py` output is not the production DB source. Use `enrich_grants.py` + `load_vectors.py` to reload grants.

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
