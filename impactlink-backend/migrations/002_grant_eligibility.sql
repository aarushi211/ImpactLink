-- Preserve the existing corpus and embeddings while adding source eligibility data.
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS eligible_geographies TEXT;
ALTER TABLE public.grants ADD COLUMN IF NOT EXISTS eligibility_rules JSONB NOT NULL DEFAULT '{}';
