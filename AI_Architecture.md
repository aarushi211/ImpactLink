# ImpactLink architecture

This describes the current repository implementation. The hosted demo may require deployment to reflect the latest local changes. ImpactLink is a prototype: deterministic calculations and validation complement AI drafting but do not establish factual correctness or funding eligibility.

[Overview](README.md) | [Backend setup](impactlink-backend/DEVELOPMENT.md) | [Evaluation](impactlink-backend/EVALUATION.md) | [Future work](FUTURE_WORK.md)

## 1. Components and persistence

| Component | Responsibility |
|---|---|
| React 19 SPA | Authenticated workflows, streamed draft replies, editing, saved-work navigation and PDF layout |
| FastAPI | REST APIs, Firebase token verification, account privacy scope, SSE and worker-thread dispatch |
| LangGraph | Checkpointed scratch/improve workflows with human review gates |
| Neon PostgreSQL | Grant records and `pgvector` embeddings, saved `user_work`, session checkpoints |
| Firebase Auth / Firestore / Storage | Identity, nonprofit profiles including private redaction terms, and original uploads |
| OpenAI API | Extraction, drafting, reranking, intent interpretation, scoring and review through the shared wrapper |
| Local models | `all-MiniLM-L6-v2` embeddings and spaCy English personal-name detection |

Database pools have bounded sizes, release idle connections, check connections before reuse and disable prepared statements for transaction-pooler compatibility. Checkpoints support recovery after browser disconnects; they do not guarantee that a task survives process termination.

Isolation currently relies on authenticated application ownership checks. PostgreSQL row-level security is **not implemented**. See [future work](FUTURE_WORK.md#1-database-level-user-isolation).

## 2. Proposal workflows

`state/proposal_state.py` defines identity, profile/grant inputs, original/generated sections, diffs, slot answers, drafting plan, agent trace, retries, flags and optional `coherence_review` metadata. Funder requirements live in `grant.application_spec`.

### Build from scratch

```text
init_slots -> slot_filling (repeat) -> slot_confirm
  -> plan_draft -> draft_sections -> coherence_check
  -> draft_review -> final_save -> complete
```

The planner supplies priorities, evidence needs and dependencies. Without custom questions, a ten-section starter uses three dependency waves:

| Wave | General starter sections |
|---|---|
| 1 | Problem statement, proposed solution, target beneficiaries |
| 2 | Goals/objectives, evaluation, organizational capacity, budget narrative |
| 3 | Executive summary, sustainability, equity statement |

Each wave runs up to four section workers by default (`DRAFT_MAX_WORKERS`, capped at four). Later waves receive summaries of earlier text. Custom funder questions replace the general section set; LOI/reporting stages have distinct starters.

The section subgraph drafts, scores and routes to approval, targeted revision, a deterministic tool or human escalation. It permits at most two rewrite retries and currently uses a score threshold of 75. AI rubric scores are not calibrated probabilities or fundability ratings.

### Improve an existing proposal

The improve flow extracts funder vocabulary, analyzes gaps, pauses for user additions/rewrite selection, then rewrites and scores sections before review and confirmation. Uploaded context can supply missing custom application answers. The UI compares original and revised text. The automatic coherence node below belongs to the scratch flow.

### Streaming and recovery

`POST /api/session/{id}/advance/stream` emits section starts, tokens, statuses, completed sections, progress and a final response. Synchronous graph work runs off the event loop; SSE heartbeats keep idle connections active. Initial text is provisional: scoring, revision and coherence edits can change it before review.

Draft replies appear in the chat conversation. An execution guard rejects simultaneous advances for the same session within the process. Checkpoints and `GET /api/session/{id}` support recovery; cross-process execution coordination is not claimed.

## 3. Application requirements and AI-use policies

`services/application.py` validates user-recorded stage, source reference, process notes, ordered questions, limits, attachment checklist and AI policy. Deterministic word/character checks flag generated text and reject missing/over-limit final answers before resuming review checkpoints. Characters include spaces and normalized line breaks; final portal counts need verification.

Attachments are stage-specific, self-reported checklist entries, not stored/validated attachment files. LOI/reporting starters and optional logic-model/work-plan prompts are preparation aids, not portal integrations or full post-award management.

AI policies are `unknown`, `permitted`, `disclosure_required` or `prohibited`. Recorded prohibitions block session creation, drafting resumes and standalone revision/consistency checks. Resumes consult saved policy rather than a replacement in the request. Manual review remains available. Required disclosure must be marked ready before final session completion; drafts can still be saved. Policy verification and submission of disclosures remain the user's responsibility.

## 4. Consistency review

`agents/coherence_agent.py` reviews full section text up to **60,000 characters including headings**. Empty/blank sections or larger inputs return `incomplete` without sending a partial prompt and claiming a pass.

The model returns a coherent verdict and at most five structured issues with exact section keys, suggested actions and severity. Invalid JSON, contradictory verdicts, unknown section references and provider errors return `unavailable`, never a successful verdict.

The scratch flow attempts at most two severity-prioritized edits, preserves original text when an edit fails, and checks the full resulting proposal again. Edited sections remain flagged for review; earlier section scores predate these edits. A failed edit prevents a successful final review status.

Saved `coherence_review` metadata records `passed`, `issues_found`, `incomplete`, `unavailable` or `stale`, with issues, coverage, edit attempts and a content fingerprint. Manual edits invalidate previous results. Build can request another authenticated check through `POST /api/build/check-consistency`; manual rechecks do not automatically rewrite text. Reports travel through session responses and saved build metadata.

This remains an AI consistency assessment, not source-evidence verification. It can miss contradictions or flag harmless differences. Incomplete checks proceed to human review with explicit warnings rather than being presented as passes.

## 5. Grant retrieval and refresh

`services/vector_store.py` uses local embeddings and PostgreSQL cosine-distance retrieval followed by AI reranking. `services/eligibility.py` evaluates deadlines, recorded applicant categories and geography before final results are selected. Confirmed mismatches are excluded; unknown dates, local restrictions and additional requirements remain unverified. Tax status, fiscal sponsorship, financial capacity and matching-fund eligibility need deeper structured checks.

`services/grant_refresh.py` and `scripts/refresh_grants.py` normalize official California and Grants.gov records. Refreshes track source identity/URLs, source updates, verification timestamps and content hashes, updating incrementally and re-embedding changed content. Discovery limits apply to new records; tracked federal records refresh independently of the discovery keyword. Routine refreshes preserve the corpus instead of replacing it wholesale.

The daily workflow in `.github/workflows/refresh-grants.yml` requires `GRANT_REFRESH_DATABASE_URL`. A workflow file is not evidence of successful production scheduling: deployment, credentials, run verification and alerts remain operational work. Corpus size and available opportunities change over time.

## 6. Budget calculations

The active entry point is `services/budget/generator.py`, backed by `services/budget/costing.py`. It requires explicit cost inputs rather than inferring financial assumptions from prose.

- Personnel: annual salary x headcount x FTE per person x project months / 12; fringe applies to project salary.
- Direct lines retain quantities, unit costs and categories. Recorded unallowable categories are rejected rather than silently removed.
- Indirect: selected MTDC/TDC base, eligible exclusions, cumulative subaward handling, recorded rate method/reference and entered caps. De minimis inputs require explicit eligibility confirmation.
- Over-budget plans retain actual costs and expose the gap. Scope options recalculate explicit changes; the engine does not proportionally scale every line or invent fractional staff.
- Natural-language refinements become constrained cost-input edits recalculated by Python.

This validates arithmetic against entered assumptions. It does not certify award compliance, determine wage-law compliance or fully model cash/in-kind matching contributions. Legacy budget modules are not the active public calculation path.

## 7. Privacy and provider behavior

`utils/privacy.py`, `utils/name_detection.py` and `utils/llm.py` layer identifier patterns, local English personal-name detection and private account-specific terms before outbound model calls. The shared wrapper handles ordinary, structured, synchronous, asynchronous and streaming calls and tool-history values while preserving operational/schema fields.

Authenticated AI routes load current account privacy settings and propagate them through worker threads and streams. Failure to load settings or the name model stops AI processing. Profile previews run locally on the app server without an AI call or saving preview text. Private term lists are omitted from collaborator directories.

Optional provider response storage/model caching and environment-based external tracing are disabled. Logging filters mask common identifiers and omit exception message bodies. Original uploaded/saved text remains in app storage. Detection is not complete anonymization: non-English names and identifying narratives can be missed, and harmless text can be masked. Provider retention policies still apply.

The shared client reads `OPENAI_API_KEY` and `OPENAI_MODEL`, with bounded SDK retries. There is no standby-key rotation or guaranteed provider failover. Firebase token verification retries once after a 1.5-second delay when a token is reported as used too early; this is not a microsecond clock tolerance.

## 8. Evidence and future work

Latest local regression checks passed 144 backend tests, 63 frontend tests and a frontend production build; the default frontend scaffold test is excluded. These checks do not establish production reliability or real-world proposal quality. Historical synthetic measurements are separated in the [evaluation guide](impactlink-backend/EVALUATION.md).

The [future-work backlog](FUTURE_WORK.md) covers database isolation, deeper eligibility, match accounting, independent evaluation, refresh operations, document/post-award workflows and practitioner research.
