# ImpactLink

**A grant discovery and proposal preparation prototype for nonprofits.**

[Live demo](https://impactlink-cbfc5.web.app) | [Architecture](AI_Architecture.md) | [Backend setup](impactlink-backend/DEVELOPMENT.md) | [Evaluation](impactlink-backend/EVALUATION.md) | [Future work](FUTURE_WORK.md)

ImpactLink connects grant search, proposal drafting and explicit budget calculations. AI interprets instructions and drafts text; Python calculates costs and checks recorded limits. The application supports preparation and review, but does not verify submission readiness or predict funding success.

## Implemented capabilities

| Capability | Current behavior |
|---|---|
| Grant discovery | Local embeddings and PostgreSQL `pgvector` search with AI reranking. Official California and Grants.gov refresh adapters preserve source identity and verification metadata. Corpus size changes with refreshes. |
| Eligibility | Deadline, declared applicant category and recorded geography checks exclude confirmed mismatches. Missing or additional conditions remain unverified. |
| Build proposals | Guided questions, drafting plans and streamed section replies within the chat. A ten-section general starter is available; funder questions can replace it. |
| Funder application structure | Ordered questions, word/character limits, LOI and reporting starters, logic-model/work-plan prompts and attachment checklists. Checklist entries are not uploaded documents. |
| Improve proposals | PDF/DOCX parsing, gap review, targeted rewrites and tracked comparisons. Sessions pause for human review and persist in PostgreSQL. |
| Budget model | Explicit salaries, headcount, FTE, months, fringe and direct costs; MTDC/TDC indirect bases, rate references, caps and unallowable categories. Over-budget plans retain actual costs and offer explicit scope options. |
| Saved work | Reopen generated/revised proposals and budgets from the dashboard. Find Grants uses the current generated text automatically. PDF export paginates long sections. |
| AI privacy | Outbound identifier patterns, local English personal-name detection and private account-specific terms. Profile includes a redaction preview. AI requests stop if privacy settings or the detector cannot load. Originals remain stored in the app. |
| Funder AI-use policies | Record unknown, permitted, disclosure-required or prohibited use, with sources and conditions. Recorded prohibitions block proposal AI drafting/revision and consistency rechecks. Required disclosure must be marked ready before session completion. |
| Consistency review | Full-text checks up to 60,000 characters including headings, rechecks after up to two automatic edits, visible unresolved/incomplete checks, and stale results after edits. Manual rechecks and saved review results are supported in Build. |

Policies, checklist readiness, financial assumptions and applicant details are user-recorded. Automatic checks can miss sensitive content or contradictions. AI scores are not independent evidence of proposal quality.

## Stack and data flow

**React 19 | FastAPI | LangGraph | OpenAI API | Neon PostgreSQL/pgvector | Firebase Auth, Firestore and Storage**

```text
React SPA -- REST + server-sent events --> FastAPI
  +-- LangGraph: scratch and improve sessions
  +-- Local embeddings + pgvector grant retrieval
  +-- Python budget calculations and application-limit checks
  +-- Local privacy checks before outbound AI calls
  +-- Neon: grants, saved work, session checkpoints
  +-- Firebase: identity, profiles, original uploads
  +-- OpenAI API: interpretation, drafting, reranking, scoring and review
```

Database tenant isolation currently relies on application ownership checks. Database-enforced isolation remains [future work](FUTURE_WORK.md#1-database-level-user-isolation).

## Local setup

Configure the backend environment using the [development guide](impactlink-backend/DEVELOPMENT.md), and Firebase/API settings using the [frontend README](impactlink-frontend/README.md).

From the repository root, in separate terminals:

```bash
# Backend: activate a Python virtual environment first
cd impactlink-backend
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
uvicorn main:app --reload --port 8000
```

```bash
# Frontend
cd impactlink-frontend
npm ci
npm start
```

Requirements include the local English name model; it is installed during setup, not downloaded during AI requests. Open [localhost:3000](http://localhost:3000) and sign in.

## Demo flow

1. In Profile, set the applicant category and project states. Add private redaction terms if needed.
2. Search Grants for a topic such as "urban greening Lower Los Angeles River disadvantaged communities." Review eligibility and source freshness; available results depend on the current corpus and deadlines.
3. In Build, record the funder questions, limits, attachments and AI-use policy, then answer the guided questions.
4. Watch the draft stream into the chat. Review consistency findings, edit and recheck text, and prepare any required disclosure.
5. Save the proposal, use Find Grants to match its text, reopen it from the dashboard and export a PDF. Enter explicit cost assumptions in Budget Setup to create a budget.

## Validation and limitations

The latest local checks on **November 5, 2026** passed **144 backend tests**, **63 frontend tests** and the frontend production build. The frontend run excludes the existing default `App.test.js` scaffold. These are regression checks, not a live deployment audit or a grant-quality benchmark.

Earlier retrieval/drafting measurements used three synthetic scenarios and an older corpus/configuration. They are historical smoke-test results, not current accuracy or latency guarantees. See [Evaluation](impactlink-backend/EVALUATION.md) for commands and limitations.

## Future work

Next priorities are database-enforced user isolation, deeper eligibility rules, cash/in-kind matching contributions, independent evaluation, refresh operations and document/post-award workflows. Grant-writer interviews and a researched competitive comparison are also outstanding. The [prioritized backlog](FUTURE_WORK.md) records scope and completion criteria.

## Documentation

| Document | Contents |
|---|---|
| [Architecture](AI_Architecture.md) | Current data flow, sessions, privacy and consistency review |
| [Backend development](impactlink-backend/DEVELOPMENT.md) | Environment, APIs, refresh operations and troubleshooting |
| [Frontend README](impactlink-frontend/README.md) | Routes, UI workflows, configuration and checks |
| [Evaluation](impactlink-backend/EVALUATION.md) | Regression commands, historical results and evidence gaps |
| [Future work](FUTURE_WORK.md) | Remaining engineering, operations and user validation |
