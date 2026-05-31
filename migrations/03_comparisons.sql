-- One row per video-pair comparison (sidebar history item)
CREATE TABLE IF NOT EXISTS comparisons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT,
  video_a_url TEXT NOT NULL,
  video_b_url TEXT NOT NULL,
  video_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  titles JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'ready'
    CHECK (status IN ('ingesting', 'ready', 'failed')),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comparisons_user_updated
  ON comparisons(user_id, updated_at DESC);
