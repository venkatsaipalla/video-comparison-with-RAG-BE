# Deployment guide

## Backend (Render or Fly.io)

### Render (recommended for screening)

1. Connect GitHub repo `BE-video-comparison-rag`.
2. New **Web Service** → Environment: **Docker**.
3. Set environment variables:
   - `DATABASE_URL` — Supabase connection string (pooler URI, port 6543, `?sslmode=require`)
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS` — `https://YOUR_VERCEL_APP.vercel.app,http://localhost:3000`
4. Health check path: `/health`
5. Deploy. Note the public URL (e.g. `https://creatorjoy-rag-api.onrender.com`).

### Fly.io (alternative)

```bash
fly launch --no-deploy
fly secrets set DATABASE_URL=... OPENAI_API_KEY=... CORS_ORIGINS=...
fly deploy
```

## Frontend (Vercel)

1. Import `FE-video-comparison-by-rag` on Vercel.
2. Set `NEXT_PUBLIC_API_URL` to your Render/Fly URL.
3. Deploy.

## Supabase

Run `supabase/migrations/001_schema.sql` once in the SQL editor.

## Smoke test

```bash
curl https://YOUR_API/health
# {"status":"ok"}

# Create session (replace URLs)
curl -X POST https://YOUR_API/sessions \
  -H "Content-Type: application/json" \
  -d '{"video_a_url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","video_b_url":"https://www.youtube.com/watch?v=jNQXAC9IVRw"}'
```

Poll `GET /sessions/{id}/status` until `ready`, then test chat from the Vercel UI.

## HTTPS / SSE

Both platforms terminate TLS. SSE works over `POST /sessions/{id}/chat` with `Accept: text/event-stream`.
