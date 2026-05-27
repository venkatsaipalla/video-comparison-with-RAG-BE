# Deploy brain API on Render

## Readiness checklist

| Item | Status |
|------|--------|
| `render.yaml` blueprint | Yes (`runtime: docker`) |
| `Dockerfile` + `uv sync` in image | Yes |
| `pyproject.toml` + `uv.lock` | Yes |
| `runtime.txt` → Python 3.11 | Yes |
| Entrypoint `main:app` | Yes |
| `GET /health` (no auth) | Yes |
| `PORT` from Render | Yes (`Settings.PORT`) |
| `greenlet` for ADK + SQLAlchemy async | Yes |
| Postgres for ADK sessions | Use `ADK_DATABASE_URL` (blueprint adds Render Postgres) |

## Not on Render

- **GPU retrieval repo** — deploy on a GPU host / VM with a stable HTTPS URL. Set `RETRIEVAL_BASE_URL` + `RETRIEVAL_API_KEY`.
- **Next.js UI** — deploy on [Vercel](https://vercel.com) (see `FE-video-comparison-by-rag/DEPLOY.md`).

## Request timeouts (important)

- `POST /init` waits on GPU ingest (up to **~5 minutes** client timeout).
- `POST /chat` runs the full multi-agent pipeline (often **1–3+ minutes**).

Use at least **Starter** plan and raise **HTTP request timeout** in the Render service settings (e.g. 300–600s). Free tier request limits are too low for `/init`.

If the build fails with `open Dockerfile: no such file`, the service is set to **Docker** on Render — this repo includes `Dockerfile` at the repo root. Push latest `main` and redeploy.

## 1. Blueprint deploy

1. Push this repo to GitHub.
2. Render → **New** → **Blueprint** → select repo.
3. Review `render.yaml` (web service + `adk-sessions` Postgres).
4. Set secrets when prompted:
   - `OPENAI_API_KEY`
   - `RETRIEVAL_BASE_URL` — public HTTPS URL of GPU service
   - `RETRIEVAL_API_KEY` — must match GPU repo
   - `CORS_ORIGINS` — e.g. `https://your-app.vercel.app,http://localhost:3000`
5. Deploy. Note the service URL: `https://video-rag-brain.onrender.com` (name may vary).

`BACKEND_API_KEY` is auto-generated. Copy it from the Render env tab.

## 2. Wire the frontend (Vercel)

In the **Next.js** project (server env only — never `NEXT_PUBLIC_`):

| Variable | Value |
|----------|--------|
| `NEXT_PUBLIC_API_URL` | `https://<your-render-service>.onrender.com` |
| `BRAIN_API_KEY` | same as Render `BACKEND_API_KEY` |
| `NEXT_PUBLIC_API_TIMEOUT_SEC` | `300` or higher for `/init` |

The Next.js route `/api/brain/*` proxies to Render and attaches `X-API-Key`.

## 3. Manual env reference

| Variable | Required | Notes |
|----------|----------|--------|
| `OPENAI_API_KEY` | Yes | LiteLLM → OpenAI |
| `BACKEND_API_KEY` | Yes | Clients send `X-API-Key` on `/init`, `/chat` |
| `RETRIEVAL_BASE_URL` | Yes | GPU service base URL (no trailing slash) |
| `RETRIEVAL_API_KEY` | Yes* | *If GPU enforces auth |
| `ADK_DATABASE_URL` | Yes on Render | Postgres URL; blueprint wires Render DB |
| `CORS_ORIGINS` | Yes | Comma-separated frontend origins |
| `ENVIRONMENT` | No | `production` disables uvicorn reload |
| `MODEL_ROUTER` / `WORKER` / `SYNTH` | No | Defaults in `render.yaml` |

Do **not** use `sqlite:///./gadk.db` on Render — disk is ephemeral; sessions are lost on restart.

## 4. Verify

```bash
curl https://<service>.onrender.com/health

curl -X POST https://<service>.onrender.com/init \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BACKEND_API_KEY" \
  -d '{"user_id":"test","urls":["https://www.youtube.com/watch?v=dQw4w9WgXcQ","https://www.youtube.com/watch?v=jNQXAC9IVRw"]}'
```

## Local parity

```bash
uv sync
cp .env.example .env
uv run python main.py
```

Optional: `uv export -o requirements.txt` only if a host requires pip-style installs.
