-- Migration registry: skip any row where is_applied = 1
CREATE TABLE IF NOT EXISTS schema_migrations (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_applied SMALLINT NOT NULL DEFAULT 0 CHECK (is_applied IN (0, 1))
);
