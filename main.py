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
from app.services.ingest_client import ingest_urls
from app.session_service import session_service

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


# ---------- /init ----------

class InitRequest(BaseModel):
    user_id: str
    urls: list[HttpUrl] = Field(..., min_length=2, max_length=2)


class InitResponse(BaseModel):
    session_id: str
    video_ids: list[str]
    titles: dict[str, str | None]


@app.post("/init", response_model=InitResponse)
async def init_session(req: InitRequest) -> InitResponse:
    """The ONLY entry point that triggers ingestion. Ingests both URLs on
    the GPU repo, then creates an ADK session whose state has video_ids
    locked. Returns session_id for the frontend to pass into /chat.
    """
    urls = [str(u) for u in req.urls]

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
    for r in results:
        vid = r.get("video_id")
        if not vid:
            raise HTTPException(
                status_code=502,
                detail="ingestion returned success without a video_id",
            )
        video_ids.append(vid)
        titles[vid] = r.get("title")

    if len(video_ids) != 2:
        raise HTTPException(
            status_code=422,
            detail=f"expected 2 ingested videos, got {len(video_ids)}",
        )

    # Lock video_ids into session state at creation. /chat cannot modify them.
    session = await session_service.create_session(
        app_name=settings.APP_NAME,
        user_id=req.user_id,
        state={K.VIDEO_IDS: video_ids, K.METADATA: {}},
    )

    return InitResponse(session_id=session.id, video_ids=video_ids, titles=titles)


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
    # Server-side URL guardrail. Refuses without ever invoking the runner.
    if _URL_RE.search(req.message):
        return ChatResponse(
            session_id=req.session_id,
            answer=_URL_REFUSAL,
            state={},
        )

    session = await session_service.get_session(
        app_name=settings.APP_NAME, user_id=req.user_id, session_id=req.session_id
    )
    if session is None:
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
    answer = final_text or state.get(K.ANSWER, "") or root_text

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
