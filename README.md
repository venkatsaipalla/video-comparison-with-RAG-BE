# Creatorjoy Video Comparison RAG — Backend

FastAPI service that ingests two social video URLs (YouTube, Shorts, TikTok, Instagram Reels), stores transcripts + engagement in **Supabase Postgres + pgvector**, and serves **streaming cited chat** over SSE.

Companion frontend: [FE-video-comparison-by-rag](https://github.com/your-org/FE-video-comparison-by-rag)

## Architecture

```
Client (Next.js) → FastAPI → Supabase (pgvector + relational)
                         → OpenAI (embeddings + chat)
                         → yt-dlp / youtube-transcript-api (ingest)
```

### Why Supabase pgvector (not Pinecone)?

- **Free tier** covers screening scale: ~2 videos × ~40 chunks × 1k creators/day ≈ 80k vectors/month — well within Postgres limits.
- **Relational + vector** in one DB: sessions, videos, messages, and chunks join without sync jobs.
- **Scale path**: IVFFlat/HNSW tuning → read replica → dedicated vector index (Qdrant/Pinecone) if chunk count exceeds ~5M.

### RAG pipeline (v1)

1. **Intent router** (LangChain) — compare / hook / improvement / general
2. **Dense retrieval** — `match_chunks()` with optional hook-window filter
3. **Generation** — `gpt-4o-mini` with `[chunk:uuid]` citation format
4. **Citation validation** — only chunks present in retrieval context

v2 (documented, not shipped): multi-query, BM25 hybrid, cross-encoder rerank.

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Run [`supabase/migrations/001_schema.sql`](supabase/migrations/001_schema.sql) in **SQL Editor**.
3. Copy **Database URL** (Settings → Database → Connection string → URI).

### 2. Environment

```bash
cp .env.example .env
# Edit DATABASE_URL, OPENAI_API_KEY, CORS_ORIGINS
```

### 3. Run locally

**Requires Python 3.10+** (3.11 recommended). Python 3.9 will fail on chat routing types.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health: `GET http://localhost:8000/health`

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | `{ video_a_url, video_b_url }` → starts ingest |
| GET | `/sessions/{id}/status` | Poll ingest + video metrics |
| POST | `/sessions/{id}/chat` | SSE stream; body `{ message, conversation_id? }` |

### SSE events

- `token` — streamed answer text
- `citation` — `{ chunk_id, video_label, start_sec, excerpt, ... }`
- `done` — `{ message_id, conversation_id }`
- `error`

## Platform notes

| Platform | Ingest |
|----------|--------|
| YouTube / Shorts | `youtube-transcript-api` + yt-dlp metadata |
| TikTok / Instagram | yt-dlp metadata + subtitles; description fallback |

Public URLs only. Private or login-walled reels may fail — surface error in UI.

## Cost estimate (1,000 creators / day)

Assumptions: 2 videos, 40 chunks each, 10 chat turns/session.

| Step | Tokens (approx) | Cost @ mini/small |
|------|-----------------|-------------------|
| Embed once | 80k chunks × ~100 tok = 8M tok/mo | ~$0.16 (embeddings) |
| Chat | 10 × 2k tok × 1k × 30 = 600M tok/mo | ~$90–120 (chat) |

**Knobs**: cache by URL hash, cap video length (15 min), `top_k=12`, skip Whisper unless needed.

## Deploy (Render)

1. Push repo to GitHub.
2. [Render](https://render.com) → New **Web Service** → Docker.
3. Set env: `DATABASE_URL`, `OPENAI_API_KEY`, `CORS_ORIGINS=https://your-vercel-app.vercel.app`.
4. Health check path: `/health`.

Cold starts on free tier: wake service before demo.

## Loom script

1. Paste YouTube + TikTok URLs → ingest
2. Show engagement cards side-by-side
3. Ask: “Why did Video A outperform B?” — show citations
4. Ask: “Compare hooks in the first 5 seconds”
5. Refresh page — conversation memory from Supabase
