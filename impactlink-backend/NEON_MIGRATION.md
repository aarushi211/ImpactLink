# Neon cutover — November 4, 2026

The live Firebase-hosted app and both local backend/Compose environments use the
Neon production branch in AWS US West 2. Firebase authentication, Firestore, file
storage, frontend hosting, and the deployed backend image retain their existing
configuration.

## Deployment

- Cloud Run project: `impactlink-cbfc5`, region: `us-west1`.
- Service: `backend-105208079841`.
- Revision receiving 100% of traffic: `backend-105208079841-00004-wof`.
- Runtime `DATABASE_URL` references Secret Manager `NEON_DATABASE_URL:1`.
- Local `DATABASE_URL` uses Neon's pooled endpoint; `DATABASE_URL_UNPOOLED` is
  available for administrative operations.
- Supabase credentials remain in the original Cloud Run secret and local
  `SUPABASE_DATABASE_URL` entries. The source database was not modified.
- The temporary Neon verification branch and Cloud Run candidate tag were removed.

## Verification

All application tables were copied using a consistent source snapshot. Row counts
and row-content fingerprints matched before and after the public cutover:

| Table | Rows |
| --- | ---: |
| grants | 109 |
| user_work | 5 |
| checkpoints | 297 |
| checkpoint_writes | 1,778 |
| checkpoint_blobs | 866 |
| checkpoint_migrations | 10 |

- Root `npm run build`: `Compiled successfully.` Existing warning: stale
  Browserslist data.
- Migration safeguards: seven tests passed.
- Local backend, candidate revision, and public app: Firebase sign-in, grant
  search, draft create/read/update/delete, and proposal checkpoint write/read passed.
- The candidate passed the same checks after a deliberate compute suspension,
  demonstrating automatic wake-up and connection recovery.
- Temporary Firebase users, drafts, and checkpoint records were removed.

Neon's account-managed inactivity timeout remains at its default. The API's value
`0` selects that default; the account rejected a custom interval, so the policy
does not override it.

To repeat the runtime checks from the repository root with the backend virtualenv:

```bash
python impactlink-backend/scripts/verify_neon_runtime.py --base-url https://impactlink-cbfc5.web.app
```

The script needs local Firebase admin credentials and creates a dedicated temporary
test user. It removes that user and its database records when finished.

## Rollback

The previous Supabase revision is `backend-105208079841-00003-fpq`. After live
writes reach Neon, reconcile those writes before moving traffic back to Supabase.
Keep Neon as the authoritative database unless a deliberate rollback is needed.
