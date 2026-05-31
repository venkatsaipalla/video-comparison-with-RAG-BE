# Video Comparison RAG — Brain (Cognitive Layer)

A production-style **multi-agent RAG backend** that answers analytical questions about **two YouTube videos** per session (compare, summarize, virality/performance, timestamps, metadata). Built with **Google ADK 1.31.1**, **LiteLLM 1.82.6**, and **FastAPI**, currently running entirely on **OpenAI `gpt-5-mini`** via LiteLLM.

This is one of **two repositories**:

| Repo | Responsibility |
|---|---|
| **Brain (this repo)** | Orchestration, agents, sessions, reasoning, final synthesis. The "cognitive layer". |
| **GPU repo** (`video-comparison-RAG-with-GPU`) | Ingestion + transcript chunking + dense/sparse embeddings + Qdrant RRF fusion + cross-encoder reranking. Exposes `/ingest` and `/retrieve`. |

The brain repo **never** does retrieval math — it only decides *what* to ask and *how* to present it, calling the GPU repo over HTTP.

---

## What it does

1. `POST /init` — accepts exactly **2 YouTube URLs** + `user_id`, calls the GPU repo's `/ingest` (forwarding `user_id`), locks the resulting `video_ids` + metadata into an ADK session, returns `session_id`. This is the **only** endpoint that can trigger ingestion.
2. `POST /chat` — accepts `user_id` + `session_id` + `message`, runs the agent pipeline, returns a grounded, cited answer. Every retrieval call to the GPU repo forwards `user_id` and `session_id`.
3. `GET /health` — open, unauthenticated.

The two `video_ids` are **fixed for the whole session**. No agent or chat call can add/change them.

---

## Architecture

```
/chat ──▶ Root (LlmAgent)               classify intent; small-talk answered here
            │  transfer if VIDEO_ANALYSIS
            ▼
         pipeline (SequentialAgent)
            │
            ├── RAG  (SequentialAgent)
            │     └── retrieval_loop (LoopAgent, max_iterations=2)   self-corrective RAG
            │           ├── Planner   (LlmAgent)         rewrite query + plan 1-3 retrievals
            │           ├── Retriever (BaseAgent, NO LLM) parallel /retrieve calls, exact-text dedup
            │           ├── Grader    (LlmAgent)         is the evidence sufficient?
            │           └── EscalationCheck (BaseAgent)  escalate=True exits loop early
            │     └── Packer (BaseAgent, NO LLM)         group by video, trim, write state["context"]
            │
            ├── Analysis (SequentialAgent)
            │     ├── Router (LlmAgent)                  pick ≤3 dimensions
            │     ├── Specialists (ParallelAgent)        gated — only chosen ones call the LLM
            │     │     ├── Summarizer   (LlmAgent)
            │     │     ├── Comparator   (LlmAgent)
            │     │     ├── Virality     (LlmAgent)
            │     │     ├── Timeline     (LlmAgent)
            │     │     └── MetadataLookup (BaseAgent, NO LLM)
            │     └── Reducer (BaseAgent, NO LLM)        merge briefs -> state["analysis"]
            │
            └── Final (LlmAgent)                          synthesize cited, user-facing answer
```

State flows through ADK session state (`output_key` per agent); downstream agents read upstream output instead of re-prompting.

---

## Models

Every LLM agent in the pipeline currently uses **`gpt-5-mini`** via three LiteLLM aliases — `MODEL_ROUTER`, `MODEL_WORKER`, `MODEL_SYNTH`. The aliases are kept distinct in code so the tiers can be re-split later (e.g. nano for routing/grading) without touching any agent.

`reasoning_effort` is set per-role to balance cost and reliability:

| Agent | `reasoning_effort` | Notes |
|---|---|---|
| `root_agent` | `low` | Routing reliability matters — `minimal` skewed toward narrating the transfer instead of calling `transfer_to_agent`. |
| `rag_planner`, `rag_grader`, `analysis_router` | `minimal` | Pure structured-output paths; no quality regression observed. |
| `analysis_summarizer`, `analysis_comparator`, `analysis_virality`, `analysis_timeline` | `low` | Need to actually reason over chunks + metadata. |
| `final_agent` | `low` | Conversational synthesis; pre-analyzed inputs reduce required reasoning. |

---

## How it calls the GPU repo

| Brain action | GPU endpoint | Payload includes | When |
|---|---|---|---|
| `/init` ingestion | `POST /ingest` | `urls`, `user_id` | once per session; returns `video_ids` + metadata |
| RAG chunk retrieval | `POST /retrieve mode=chunks` | `query`, `video_ids`, `user_id`, `session_id`, `top_k` | per turn; GPU does hybrid search + RRF + rerank |
| RAG metadata | `POST /retrieve mode=metadata` | `video_ids`, `user_id`, `session_id` | rarely — metadata is pre-loaded at `/init` and cached in session state |

All calls send the `X-API-Key` header (`RETRIEVAL_API_KEY`). `user_id` and `session_id` are forwarded on every call for GPU-side scoping/audit.

---

## Cost & latency optimizations

- **Heavy work is pushed to the GPU repo**: dense + sparse + RRF + cross-encoder reranking all happen on the retrieval service, not in tokens.
- **Gated parallel specialists**: the Analysis Router picks ≤3 dimensions. Non-selected specialists are **short-circuited by a `before_agent_callback`** that returns a schema-valid `{"skipped": true}` payload — **the LLM is never called**, zero token cost.
- **Deterministic agents (no LLM)**: Retriever, Packer, MetadataLookup, and the Reducer are plain `BaseAgent`s. The Reducer merges specialist briefs and computes `confidence` / `grounded` / `notes` purely in code — no LLM call to "combine JSON".
- **Metadata pre-loaded at `/init`**: cached in ADK session state, so most metadata questions avoid a `/retrieve` round-trip entirely. Prompts treat metadata as a **first-class evidence source** — e.g. a video's topic is often answerable from its title alone.
- **`reasoning_effort` tuned per role**: GPT-5 reasons before answering, which dominated latency. The table above is the current per-agent setting.
- **Self-corrective RAG** capped at `max_iterations=2`: re-plans against the Grader's `missing_aspects` instead of blindly retrying; exact-text dedup avoids re-using chunks.

### Cost logging

Every LLM event in `/chat` is priced from `event.usage_metadata` (`prompt_token_count`, `candidates_token_count`, `cached_content_token_count`) using the table in [`app/utils/cost.py`](app/utils/cost.py):

| Model | input $/1M | output $/1M |
|---|---|---|
| `gpt-5-nano` | 0.05 | 0.40 |
| `gpt-5-mini` | 0.25 | 2.00 |

Each turn produces N per-event lines (`llm_usage author=… input=… output=… cached=… cost_usd=…`) followed by one cumulative summary line (`llm_usage_total input=… output=… cached=… cost_usd=…`) emitted immediately before the `ChatResponse` is returned. Logging only — totals are not persisted to the DB and not surfaced in the API response.

---

## Structured outputs

All LLM agents that emit JSON use ADK `output_schema` (Pydantic) → OpenAI **strict** structured outputs. Strict mode requires every field `required`, `additionalProperties:false`, and no arbitrary-keyed dicts — so per-video data is modeled as `list[Entry]` (each carries `video_id`); the Reducer converts these back to `dict[video_id, …]` for consumption. Field descriptions are kept (they help the model).

---

## Constraints

- Exactly **2 videos per session**, locked at `/init`.
- URLs in a `/chat` message are **refused** (server-side regex + Root guardrail) — changing videos requires a new session.
- Ingestion is owned solely by `/init`; no agent can import the ingest client.
- The Final agent **never** exposes raw `video_id` strings to the user — videos are referenced by their (optionally compressed) metadata title, or a positional `Video A` / `Video B` fallback.

---

## Project layout

```
app/
├── agents/                       # ADK agent definitions
│   ├── root_agent.py
│   ├── pipeline.py               # SequentialAgent: rag -> analysis -> final
│   ├── final_agent.py
│   ├── rag/                      # planner, retriever, grader, packer
│   └── analysis/                 # router, summarizer, comparator,
│                                 # virality, timeline, metadata_lookup, reducer
├── prompts/                      # one .py per LLM agent
├── routes/
│   ├── init.py                   # POST /init
│   ├── chat.py                   # POST /chat (owns the ADK Runner)
│   ├── auth.py                   # /auth/* (Google sign-in)
│   └── comparisons.py            # /comparisons/* (sidebar history)
├── services/
│   ├── auth.py                   # X-API-Key dependency
│   ├── google_auth.py            # Google ID-token verification
│   ├── ingest_client.py          # → GPU /ingest
│   ├── retrieval_client.py       # → GPU /retrieve (chunks + metadata)
│   ├── session_service.py        # ADK DatabaseSessionService (asyncpg)
│   └── logger.py                 # context-aware structured logger
├── utils/
│   ├── citations.py              # state -> UI citation list
│   └── cost.py                   # per-event + cumulative LLM cost logging
├── db/                           # asyncpg pool, repository, jsonb helpers, migrations
├── config.py                     # Settings (pydantic-settings)
├── schemas.py                    # all Pydantic output schemas
└── state_keys.py                 # constants for ADK session state keys
main.py                           # FastAPI app, lifespan, include_router
```

---

## Sessions / database

One Postgres URL (`DATABASE_URL`), two sets of tables:

| Layer | Tables | Purpose |
|---|---|---|
| **App** (`migrations/`) | `users`, `comparisons`, `messages`, `schema_migrations` | Google sign-in, sidebar history, UI chat transcript |
| **ADK** (`DatabaseSessionService`) | `sessions`, `events`, `app_states`, `user_states`, `adk_internal_metadata` | Agent state + full event log for multi-turn RAG |

ADK creates its tables automatically on startup (asyncpg driver is applied in [`app/services/session_service.py`](app/services/session_service.py)).

---

## Deploy (Render)

Use the **[Render Blueprint](render.yaml)** and follow **[DEPLOY.md](DEPLOY.md)**. Pair with Vercel for the Next.js UI and a separately hosted GPU retrieval service.

## Run

```bash
uv sync
cp .env.example .env              # fill in the values below
uv run python main.py             # serves on $HOST:$PORT, hot-reload when ENVIRONMENT=dev
```

Key env vars:

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (LiteLLM routes through it) |
| `BACKEND_API_KEY` | clients must send it as `X-API-Key` to `/init` and `/chat` |
| `RETRIEVAL_API_KEY` | sent as `X-API-Key` to the GPU repo |
| `RETRIEVAL_BASE_URL` | GPU repo base URL |
| `DATABASE_URL` | Postgres (app + ADK tables) |
| `MODEL_ROUTER` / `MODEL_WORKER` / `MODEL_SYNTH` | tier model IDs (all default to `openai/gpt-5-mini`) |
| `GOOGLE_CLIENT_ID` | for verifying Google sign-in ID tokens |
| `CORS_ORIGINS` | comma-separated allowed origins |
| `ENVIRONMENT` | `dev` enables uvicorn reload |

---

## Testing

A ready-to-run notebook is provided at **`notebooks/test_chat.ipynb`** covering: `/health`, `/init`, small-talk, full-pipeline analysis, metadata-only query, the URL guardrail, auth (401) paths, and error cases. Set `API_KEY` in the notebook to match `BACKEND_API_KEY`.

---

## Centralized logging

[`app/services/logger.py`](app/services/logger.py) provides a context-aware logger: every line is prefixed with `user_id` + `session_id` (via `contextvars`, propagated through async tasks) and timestamped to the millisecond (`Mon Nov 11 14:23:45.123`). HTTP calls to the GPU repo, every agent's final event, and the per-turn LLM cost totals are logged for full per-request tracing.
