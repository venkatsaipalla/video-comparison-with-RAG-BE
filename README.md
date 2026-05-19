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

## Deploy on Render (free tier)

### Prerequisites

- Repo pushed to GitHub
- Supabase schema applied (`python scripts/apply_schema.py` or SQL Editor)
- Vercel frontend URL ready

### Option A — Blueprint (`render.yaml`)

1. [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint** → connect this repo.
2. Set secrets when prompted:
   - `DATABASE_URL` — Supabase **Session pooler** URI (port `5432`)
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS` — comma-separated, e.g.  
     `https://compare-video.vercel.app,http://localhost:3000`
3. Deploy. Note the service URL: `https://creatorjoy-rag-api.onrender.com` (name may vary).

### Option B — Manual web service

1. **New → Web Service** → connect GitHub repo.
2. **Runtime:** Docker (uses root `Dockerfile`).
3. **Plan:** Free.
4. **Health check path:** `/health`.
5. **Environment variables** (same as `.env.example`):

   | Key | Example |
   |-----|---------|
   | `DATABASE_URL` | `postgresql://postgres.xxx:...@...pooler.supabase.com:5432/postgres` |
   | `OPENAI_API_KEY` | `sk-...` |
   | `CORS_ORIGINS` | `https://your-app.vercel.app,http://localhost:3000` |

6. Create Web Service → wait for build (first Docker build ~5–10 min).

### Wire Vercel

In the frontend project (Vercel → Settings → Environment Variables):

```env
NEXT_PUBLIC_API_URL=https://YOUR-SERVICE.onrender.com
```

Redeploy Vercel after changing this.

### Verify

```bash
curl https://YOUR-SERVICE.onrender.com/health
# {"status":"ok"}
```

Open the Vercel app, run a comparison, then chat.

### Free-tier caveats

- **Cold start:** service sleeps after ~15 min idle; open `/health` before a demo.
- **Slow ingest:** free instances are small; first ingest may take several minutes.
- **Timeouts:** very long videos may hit request limits; keep clips under 30 min (`MAX_VIDEO_DURATION_SEC`).

### YouTube “Sign in to confirm you’re not a bot” on Render

YouTube often blocks **datacenter IPs** (Render, Fly, etc.). Fix:

1. On your Mac, install a browser extension such as **“Get cookies.txt LOCALLY”** (Chrome/Firefox).
2. While logged into YouTube in that browser, export cookies for `youtube.com` → `cookies.txt` (Netscape format).
3. Base64-encode the file:

   ```bash
   base64 -i cookies.txt | tr -d '\n' | pbcopy
   ```

4. In Render → your service → **Environment** → add:

   ```env
   YTDLP_COOKIES_B64=<paste base64 string>
   ```

5. **Manual Deploy** (or push a commit) to restart with the new env.

Without cookies, the app falls back to **oEmbed + transcript API** (titles work; views/likes may be missing). Cookies restore full yt-dlp metadata and are more reliable for captions.

**Geo-restricted videos:** Some videos play in your browser (India, etc.) but **cannot be ingested from Render’s US/EU servers**. The UI will say “geo-restricted” — pick a globally public video for demos.

**Verify cookies on Render:** Check deploy logs for `YouTube cookies loaded for yt-dlp`. If you see `No YouTube cookies`, fix `YTDLP_COOKIES_B64` (no line breaks in the value).

## Loom script

1. Paste YouTube + TikTok URLs → ingest
2. Show engagement cards side-by-side
3. Ask: “Why did Video A outperform B?” — show citations
4. Ask: “Compare hooks in the first 5 seconds”
5. Refresh page — conversation memory from Supabase
