# ImpactLink frontend

React 19 SPA for a nonprofit grant-discovery and proposal-preparation prototype.

[Project overview](../README.md) | [Backend setup](../impactlink-backend/DEVELOPMENT.md) | [Architecture](../AI_Architecture.md) | [Future work](../FUTURE_WORK.md)

## Setup

From `impactlink-frontend/`, run `npm ci` and create `.env`:

```env
REACT_APP_API_URL=http://localhost:8000
REACT_APP_FIREBASE_API_KEY=...
REACT_APP_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=your-project
REACT_APP_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=...
REACT_APP_FIREBASE_APP_ID=...
```

```bash
npm start
npm run build
```

The development UI uses port 3000. Run the backend separately; use API port 8081 instead if running the Compose backend. Firebase web configuration belongs here; database credentials, AI keys and service-account credentials belong only on the backend.

## Routes

| Path | Purpose |
|---|---|
| `/` and `/login` | Public landing page and sign-in |
| `/dashboard` | Reopen saved proposals, revisions, budgets and grant records |
| `/profile` | Organization identity, programs, communities, service areas, eligibility defaults, collaboration preferences and private masking terms |
| `/onboarding` | Three-step setup for new email and Google accounts; saves each step and supports finishing later |
| `/grants` | Browse/topic search, proposal matching, upload, eligibility and source freshness |
| `/grants/:id` | Load an individual grant independently of browser matching caches |
| `/build` | Expanded setup form: proposal name, optional grant, prefilled/manual application requirements and Start |
| `/build/write?session=<id>` | Assistant questions, answer confirmation and streamed draft replies with a right-hand steps panel |
| `/draft` | Proposal/grant selection, automatic prefill, requirements and Review gaps |
| `/draft/write?session=<id>` | Review gaps, select areas and click Draft; then view formatted output, edit, compare and refresh the grant match |
| `/budget` | Explicit cost assumptions, calculated budgets, scope options and AI-assisted edits |
| `/upload` | Compatibility redirect to `/grants` |

Application routes require sign-in. Work-item links use `?load=<id>`; active builds can recover through `?session=<id>`. Find Grants saves/passes the current proposal context and uses `/grants?proposal=<id>` when a saved ID exists.

## Current workflows

- **Application requirements:** record stage, ordered funder questions, word/character caps and attachment checklists. Custom questions replace the general starter. LOI/reporting starters and logic-model/work-plan prompts are available.
- **AI-use policy:** record funder permission, source and conditions. Prohibited policies disable proposal AI actions; required disclosure must be marked ready before session completion. These are user-recorded rules, not independently verified policies.
- **Consistency review in Build:** see unresolved issues, failed/incomplete checks and reviewed coverage. Text edits mark results stale. Check full proposal consistency runs another AI review and saves its result; it does not verify facts or automatically rewrite text.
- **Privacy:** shared notices explain outbound AI processing and retained originals. Profile's Extra AI redaction list applies across the account after saving; preview can test unsaved terms without an AI call. Automatic detection can still miss sensitive content.
- **Budgets:** enter salary, headcount, FTE, duration, fringe, direct costs and indirect assumptions. Over-budget results retain actual costs and expose explicit scope changes.
- **Saving/export:** reopen generated work from Dashboard, match generated text automatically, and export paginated PDFs. Saved text and original uploads remain in app storage.

Draft Assistant prefills only requirements explicitly present in stored grant
text, with source excerpts and missing-data warnings. Slow prefill can be skipped
for manual entry. Redraft opens a separate writing view without the old score or
selector sidebars. Revisions save separately as `Original title - Grant title`;
Find Grants and edit/compare controls appear after rewriting. Refreshing the
writing URL restores its checkpoint; opening `?load=<id>` edits a saved revision.

## Source map

| Area | Files |
|---|---|
| Proposal flows | `src/pages/BuildProposal.js`, `src/pages/Draft.js` |
| Session state and recovery | `src/hooks/useProposalSession.js` |
| Saved work and navigation | `src/hooks/useWorkStore.js`, `src/services/proposals.js` |
| HTTP and SSE | `src/services/api.js` |
| Requirements and policies | `src/components/ApplicationRequirements.js`, `src/utils/application.js` |
| Consistency results | `src/components/ConsistencyReview.js` |
| Privacy notice/preview | `src/components/AiPrivacyNotice.js` |
| PDF layout | `src/utils/proposalPdf.js` |

## Validation

```bash
npm test -- --watchAll=false --runInBand --testPathIgnorePatterns=src/App.test.js
npm run build
```

Latest local verification on November 5, 2026: **63 tests across 19 suites passed**, and the production build passed. The default `App.test.js` scaffold is excluded; replacing it and adding broader checks to CI remain future work. The recorded run used `CI=true`.

## Future work

The [shared backlog](../FUTURE_WORK.md) covers deeper eligibility inputs, cash/in-kind contributions, attachment management, award/reporting tracking, refresh health, independent evaluation and practitioner feedback. Database-enforced isolation requires backend changes; frontend route protection alone does not provide it.
