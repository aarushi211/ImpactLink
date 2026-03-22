-- migrations/001_sessions.sql
-- Run once against your Postgres database.

CREATE TABLE IF NOT EXISTS proposal_sessions (
    session_id  TEXT        PRIMARY KEY,
    state       JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index on updated_at so expiry cleanup queries are fast.
CREATE INDEX IF NOT EXISTS idx_sessions_updated
    ON proposal_sessions (updated_at);
