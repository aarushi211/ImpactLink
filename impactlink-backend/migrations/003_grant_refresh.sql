ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS source_updated_at TEXT;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS grants_source_identity
    ON public.grants (source, source_id);
