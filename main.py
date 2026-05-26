import re
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.adk.runners import Runner
from google.genai import types as genai_types
from pydantic import BaseModel, Field, HttpUrl

from app import state_keys as K
from app.agents.root_agent import root_agent
from app.config import settings
from app.logger import bind_context, get_logger
from app.services.ingest_client import ingest_urls
from app.session_service import session_service

log = get_logger("main")

load_dotenv()

app = FastAPI(title=settings.APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

runner = Runner(
    app_name=settings.APP_NAME,
    agent=root_agent,
    session_service=session_service,
)


# Server-side guardrail: any URL in a chat message is refused before the
# runner is even invoked. Cheap, deterministic, no LLM cost.
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_URL_REFUSAL = (
    "I can't process URLs during chat. Each session is locked to the two "
    "videos you uploaded at the start. To analyze different videos, please "
    "start a new session through the upload flow."
)

# Fields the GPU may return on `results[]` root and/or under `metadata`.
_INGEST_META_KEYS = (
    "title",
    "channel",
    "creator",
    "uploader",
    "platform",
    "thumbnail_url",
    "thumbnail",
    "duration",
    "duration_sec",
    "view_count",
    "views",
    "like_count",
    "likes",
    "comment_count",
    "comments",
    "upload_date",
    "engagement",
)


def _normalize_ingest_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Merge nested metadata with top-level ingest fields for the UI."""
    md = dict(result.get("metadata") or {})
    for key in _INGEST_META_KEYS:
        if key not in md and result.get(key) is not None:
            md[key] = result[key]
    if not md.get("title") and result.get("title"):
        md["title"] = result["title"]
    return md


# ---------- /init ----------

class InitRequest(BaseModel):
    user_id: str
    urls: list[HttpUrl] = Field(..., min_length=2, max_length=2)


class InitResponse(BaseModel):
    session_id: str
    video_ids: list[str]
    titles: dict[str, str | None]
    metadata: dict[str, dict[str, Any]]


@app.post("/init", response_model=InitResponse)
async def init_session(req: InitRequest) -> InitResponse:
    """The ONLY entry point that triggers ingestion. Ingests both URLs on
    the GPU repo, then creates an ADK session whose state has video_ids
    locked. Returns session_id for the frontend to pass into /chat.
    """
    bind_context(user_id=req.user_id)
    urls = [str(u) for u in req.urls]
    log.info("/init start urls=%s", urls)

    try:
        resp = await ingest_urls(urls)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"ingestion service returned {e.response.status_code}: {e.response.text[:300]}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ingestion service unreachable: {e}")

    results = resp.get("results") or []
    failed = [r for r in results if not r.get("success")]
    if failed:
        # Surface the first failure reason; the frontend should re-prompt the user.
        first = failed[0]
        raise HTTPException(
            status_code=422,
            detail=f"ingestion failed for {first.get('url')}: {first.get('error') or 'unknown'}",
        )

    video_ids: list[str] = []
    titles: dict[str, str | None] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for r in results:
        vid = r.get("video_id")
        if not vid:
            raise HTTPException(
                status_code=502,
                detail="ingestion returned success without a video_id",
            )
        video_ids.append(vid)
        md = _normalize_ingest_metadata(r)
        metadata[vid] = md
        titles[vid] = md.get("title") or r.get("title")

    if len(video_ids) != 2:
        raise HTTPException(
            status_code=422,
            detail=f"expected 2 ingested videos, got {len(video_ids)}",
        )

    # Lock video_ids into session state at creation. /chat cannot modify them.
    # Pre-populate metadata cache from the ingest response .
    session = await session_service.create_session(
        app_name=settings.APP_NAME,
        user_id=req.user_id,
        state={K.VIDEO_IDS: video_ids, K.METADATA: metadata},
    )

    bind_context(session_id=session.id)
    log.info(
        "/init done video_ids=%s titles=%s metadata_keys=%s",
        video_ids,
        titles,
        {vid: sorted(md.keys()) for vid, md in metadata.items()},
    )

    return InitResponse(
        session_id=session.id,
        video_ids=video_ids,
        titles=titles,
        metadata=metadata,
    )


# ---------- /chat ----------

class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    state: dict[str, Any]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    bind_context(user_id=req.user_id, session_id=req.session_id)
    msg_preview = req.message[:200].replace("\n", " ")
    log.info("/chat start message_len=%d preview=%r", len(req.message), msg_preview)

    # Server-side URL guardrail. Refuses without ever invoking the runner.
    if _URL_RE.search(req.message):
        log.warning("/chat blocked: URL in message")
        return ChatResponse(
            session_id=req.session_id,
            answer=_URL_REFUSAL,
            state={},
        )

    session = await session_service.get_session(
        app_name=settings.APP_NAME, user_id=req.user_id, session_id=req.session_id
    )
    if session is None:
        log.warning("/chat 404: session not found")
        raise HTTPException(status_code=404, detail="session not found")

    user_content = genai_types.Content(
        role="user", parts=[genai_types.Part(text=req.message)]
    )

    # Only Root (small-talk path) and Final (full pipeline path) may produce
    # the user-facing reply. Every other agent (RAG planner/grader, analysis
    # specialists) also emits is_final_response=True events carrying JSON
    # briefs — we must NOT surface those.
    root_text = ""
    final_text = ""
    async for event in runner.run_async(
        user_id=req.user_id,
        session_id=session.id,
        new_message=user_content,
    ):
        if not event.is_final_response():
            continue
        if not (event.content and event.content.parts):
            continue
        text = "".join(p.text or "" for p in event.content.parts)
        snippet = text[:200].replace("\n", " ")
        log.info(
            "agent_final author=%s text_len=%d snippet=%r",
            event.author,
            len(text),
            snippet,
        )
        if event.author == "final_agent":
            final_text = text
        elif event.author == "root_agent":
            root_text = text

    refreshed = await session_service.get_session(
        app_name=settings.APP_NAME, user_id=req.user_id, session_id=session.id
    )
    state = dict(refreshed.state) if refreshed else {}

    # Preference order:
    #   1. final_agent's text (full pipeline ran end-to-end)
    #   2. state["answer"] (final_agent ran but text wasn't captured in events)
    #   3. root_agent's text (small-talk / unsupported branch; pipeline skipped)
    if final_text:
        source = "final_agent"
        answer = final_text
    elif state.get(K.ANSWER):
        source = "state_answer"
        answer = state[K.ANSWER]
    else:
        source = "root_agent"
        answer = root_text

    log.info("/chat done source=%s answer_len=%d", source, len(answer))
    return ChatResponse(
        session_id=session.id,
        answer=answer,
        state=state,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.reload,
    )
