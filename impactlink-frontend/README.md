# ImpactLink Frontend

React SPA for the ImpactLink grant intelligence platform.

## Setup

```bash
npm install
```

Create `.env`:

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
npm start    # http://localhost:3000
npm run build
```

Backend must be running — see [../impactlink-backend/DEVELOPMENT.md](../impactlink-backend/DEVELOPMENT.md).

## Key routes

| Path | Purpose |
|---|---|
| `/build` | Scratch proposal flow (primary demo) + agent orchestration panel |
| `/grants` | Browse and topic-search grants |
| `/upload` | PDF upload + grant matching |
| `/draft` | Improve existing proposal |
| `/budget` | Standalone budget builder |
| `/dashboard` | User home |

## Structure

```
src/
├── pages/
│   ├── BuildProposal.js    # LangGraph scratch session UI
│   ├── Draft.js            # Improve flow UI
│   ├── Upload.js           # PDF upload
│   ├── GrantsList.js       # Grant search
│   └── Budget.js
├── hooks/
│   ├── useProposalSession.js   # Session create/advance
│   ├── useUpload.js
│   └── useBudget.js
└── services/api.js         # Axios + Firebase auth interceptor
```

## Related

- [../README.md](../README.md) — project overview
- [../AI_Architecture.md](../AI_Architecture.md) — backend agent design
