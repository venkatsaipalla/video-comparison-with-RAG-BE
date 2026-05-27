# Video Comparison RAG — Brain (Cognitive Layer)

A production-style **multi-agent RAG backend** that answers analytical questions about **two YouTube videos** per session (compare, summarize, virality/performance, timestamps, metadata). Built with **Google ADK 1.31.1**, **LiteLLM 1.82.6**, and **FastAPI**, using **OpenAI GPT-5** models.

This is one of **two repositories**:

| Repo | Responsibility |
|---|---|
| **Brain (this repo)** | Orchestration, agents, sessions, reasoning, final synthesis. The "cognitive layer". |
| **GPU repo** (`video-comparison-RAG-with-GPU`) | Ingestion + transcript chunking + dense/sparse embeddings + Qdrant RRF fusion + cross-encoder reranking. Exposes `/ingest` and `/retrieve`. |

The brain repo **never** does retrieval math — it only decides *what* to ask and *how* to present it, calling the GPU repo over HTTP.

---

## What it does

1. `POST /init` — accepts exactly **2 YouTube URLs**, calls the GPU repo's `/ingest`, locks the resulting `video_ids` + metadata into an ADK session, returns `session_id`. This is the **only** endpoint that can trigger ingestion.
2. `POST /chat` — accepts `session_id` + `message`, runs the agent pipeline, returns a grounded, cited answer.
3. `GET /health` — open, unauthenticated.

The two `video_ids` are **fixed for the whole session**. No agent or chat call can add/change them.

---

## Architecture

```
/chat ──▶ Root (LlmAgent, nano)         classify intent; small-talk answered here
            │  transfer if VIDEO_ANALYSIS
            ▼
         pipeline (SequentialAgent)
            │
            ├── RAG  (SequentialAgent)
            │     └── retrieval_loop (LoopAgent, max_iterations=2)   self-corrective RAG
            │           ├── Planner   (LlmAgent, nano)   rewrite query + plan 1-3 retrievals
            │           ├── Retriever (BaseAgent, NO LLM) parallel /retrieve calls, exact-text dedup
            │           ├── Grader    (LlmAgent, nano)   is the evidence sufficient?
            │           └── EscalationCheck (BaseAgent)  escalate=True exits loop early
            │     └── Packer (BaseAgent, NO LLM)         group by video, trim, write state["context"]
            │
            ├── Analysis (SequentialAgent)
            │     ├── Router (LlmAgent, nano)            pick ≤3 dimensions
            │     ├── Specialists (ParallelAgent)        gated — only chosen ones call the LLM
            │     │     ├── Summarizer   (LlmAgent, mini)
            │     │     ├── Comparator   (LlmAgent, mini)
            │     │     ├── Virality     (LlmAgent, mini)
            │     │     ├── Timeline     (LlmAgent, mini)
            │     │     └── MetadataLookup (BaseAgent, NO LLM)
            │     └── Reducer (BaseAgent, NO LLM)        merge briefs -> state["analysis"]
            │
            └── Final (LlmAgent, mini)                   synthesize cited, user-facing answer
```

State flows through ADK session state (`output_key` per agent); downstream agents read upstream output instead of re-prompting.

---

## How it calls the GPU repo

| Brain action | GPU endpoint | When |
|---|---|---|
| `/init` ingestion | `POST /ingest {urls}` | once per session; returns `video_ids` + metadata |
| RAG retrieval | `POST /retrieve mode=chunks {query, video_ids, top_k}` | per turn; GPU does hybrid search + RRF + rerank |
| metadata | `POST /retrieve mode=metadata` | **never during chat** — metadata is pre-loaded at `/init` |

All calls send the `X-API-Key` header (`RETRIEVAL_API_KEY`).

---

## Cost & latency optimizations

- **Model tiers** (via LiteLLM aliases): `nano` for routing/planning/grading, `mini` for specialists + final. Heavy work is pushed to the GPU repo, not the LLM.
- **Gated parallel specialists**: the Router picks ≤3 dimensions. Non-selected specialists are **short-circuited by a `before_agent_callback`** that returns a schema-valid `{"skipped": true}` payload — **the LLM is never called**, zero token cost.
- **Deterministic agents (no LLM)**: Retriever, Packer, MetadataLookup, and the Reducer are plain `BaseAgent`s. The Reducer merges specialist briefs and computes `confidence` / `grounded` / `notes` purely in code — no LLM call to "combine JSON".
- **Metadata pre-loaded at `/init`**: avoids a `/retrieve mode=metadata` round-trip on every metadata question.
- **`reasoning_effort` tuned**: GPT-5 models reason before answering, which dominated latency. Set to `"minimal"` on nano agents and `"low"` on mini agents — cut end-to-end time roughly in half with no quality loss on structured paths.
- **Self-corrective RAG** capped at `max_iterations=2`: re-plans against the Grader's `missing_aspects` instead of blindly retrying; exact-text dedup avoids re-using chunks.

---

## Structured outputs

All LLM agents that emit JSON use ADK `output_schema` (Pydantic) → OpenAI **strict** structured outputs. Strict mode requires every field `required`, `additionalProperties:false`, and no arbitrary-keyed dicts — so per-video data is modeled as `list[Entry]` (each carries `video_id`); the Reducer converts these back to `dict[video_id, …]` for consumption. Field descriptions are kept (they help the model).

---

## Constraints

- Exactly **2 videos per session**, locked at `/init`.
- URLs in a `/chat` message are **refused** (server-side regex + Root guardrail) — changing videos requires a new session.
- Ingestion is owned solely by `/init`; no agent can import the ingest client.

---

## Sessions / database

ADK sessions persist via `DatabaseSessionService`.

- Set `ADK_DATABASE_URL` to a **Supabase/Postgres** URL for persistent sessions (async driver is auto-applied).
- If left as the default `sqlite:///./gadk.db`, it runs against a **local SQLite** file — no external DB needed.
- (ADK also supports a fully in-memory session service for throwaway runs.)

---

## Run

```bash
pip install -r requirements.txt   # or: uv sync
cp .env.example .env              # fill in the values below
python main.py                    # serves on $HOST:$PORT, hot-reload when ENVIRONMENT=dev
```

Key env vars:

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (LiteLLM routes through it) |
| `BACKEND_API_KEY` | clients must send it as `X-API-Key` to `/init` and `/chat` |
| `RETRIEVAL_API_KEY` | sent as `X-API-Key` to the GPU repo |
| `RETRIEVAL_BASE_URL` | GPU repo base URL |
| `ADK_DATABASE_URL` | Postgres URL, or default SQLite |
| `MODEL_ROUTER` / `MODEL_WORKER` / `MODEL_SYNTH` | tier model IDs |
| `ENVIRONMENT` | `dev` enables uvicorn reload |

---

## Testing

A ready-to-run notebook is provided at **`notebooks/test_chat.ipynb`** covering: `/health`, `/init`, small-talk, full-pipeline analysis, metadata-only query, the URL guardrail, auth (401) paths, and error cases. Set `API_KEY` in the notebook to match `BACKEND_API_KEY`.

---

## Centralized logging

`app/logger.py` provides a context-aware logger: every line is prefixed with `user_id` + `session_id` (via `contextvars`, propagated through async tasks) and timestamped to the millisecond (`Mon Nov 11 14:23:45.123`). HTTP calls to the GPU repo and every agent's final event are logged for full per-request tracing.
