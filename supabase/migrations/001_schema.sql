-- Creatorjoy RAG screening schema
-- Run in Supabase SQL Editor (Dashboard -> SQL -> New query)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS videos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform TEXT NOT NULL
    CHECK (platform IN ('youtube', 'youtube_shorts', 'tiktok', 'instagram')),
  url TEXT NOT NULL UNIQUE,
  url_hash TEXT NOT NULL UNIQUE,
  external_id TEXT,
  title TEXT,
  creator TEXT,
  thumbnail_url TEXT,
  published_at TIMESTAMPTZ,
  duration_sec DOUBLE PRECISION,
  views BIGINT,
  likes BIGINT,
  comments BIGINT,
  engagement JSONB DEFAULT '{}',
  metadata JSONB DEFAULT '{}',
  ingest_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (ingest_status IN ('pending', 'ingesting', 'ready', 'failed')),
  ingest_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ingesting', 'ready', 'failed')),
  video_a_id UUID REFERENCES videos(id) ON DELETE SET NULL,
  video_b_id UUID REFERENCES videos(id) ON DELETE SET NULL,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transcript_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  start_sec DOUBLE PRECISION NOT NULL,
  end_sec DOUBLE PRECISION NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_video ON transcript_segments(video_id);

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  start_sec DOUBLE PRECISION,
  end_sec DOUBLE PRECISION,
  is_hook_window BOOLEAN NOT NULL DEFAULT false,
  metadata JSONB DEFAULT '{}',
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_video ON chunks(video_id);
CREATE INDEX IF NOT EXISTS idx_chunks_session ON chunks(session_id);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);

CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  citations JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sessions_updated_at ON sessions;
CREATE TRIGGER sessions_updated_at
  BEFORE UPDATE ON sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS videos_updated_at ON videos;
CREATE TRIGGER videos_updated_at
  BEFORE UPDATE ON videos FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS conversations_updated_at ON conversations;
CREATE TRIGGER conversations_updated_at
  BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION match_chunks(
  query_embedding vector(1536),
  match_session_id UUID,
  match_count INT DEFAULT 12,
  filter_hook_only BOOLEAN DEFAULT false
)
RETURNS TABLE (
  id UUID,
  video_id UUID,
  text TEXT,
  start_sec DOUBLE PRECISION,
  end_sec DOUBLE PRECISION,
  is_hook_window BOOLEAN,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
  SELECT
    c.id,
    c.video_id,
    c.text,
    c.start_sec,
    c.end_sec,
    c.is_hook_window,
    c.metadata,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  WHERE c.session_id = match_session_id
    AND c.embedding IS NOT NULL
    AND (NOT filter_hook_only OR c.is_hook_window = true)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
$$;
