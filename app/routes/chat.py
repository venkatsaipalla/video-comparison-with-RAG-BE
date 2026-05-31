"""POST /chat — runs the agent pipeline against a locked session.

A server-side URL guardrail refuses any message containing a URL before the
ADK Runner is invoked. The runner is created once at module import.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from google.adk.runners import Runner
from google.genai import types as genai_types
from pydantic import BaseModel

from app import state_keys as K
from app.agents.root_agent import root_agent
from app.config import settings
from app.db import repository as repo
from app.db.jsonb import jsonb_list, jsonb_metadata
from app.db.pool import get_pool
from app.services.auth import require_api_key
from app.services.logger import bind_context, get_logger
from app.services.session_service import session_service
from app.utils.citations import citations_from_state
from app.utils.cost import log_event_cost, log_total_cost, new_totals

log = get_logger("routes.chat")

router = APIRouter(tags=["chat"])

# Single ADK Runner reused across requests.
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


class ChatRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    message: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    state: dict[str, Any]


@router.post(
    "/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)]
)
async def chat(req: ChatRequest) -> ChatResponse:
    bind_context(user_id=str(req.user_id), session_id=str(req.session_id))
    msg_preview = req.message[:200].replace("\n", " ")
    log.info("/chat start message_len=%d preview=%r", len(req.message), msg_preview)

    pool = await get_pool()
    comparison = await repo.get_comparison(pool, req.session_id, req.user_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="comparison not found")

    # Server-side URL guardrail. Refuses without ever invoking the runner.
    if _URL_RE.search(req.message):
        log.warning("/chat blocked: URL in message")
        await repo.insert_message(pool, req.session_id, "user", req.message)
        await repo.insert_message(
            pool, req.session_id, "assistant", _URL_REFUSAL, citations=[]
        )
        return ChatResponse(
            session_id=str(req.session_id),
            answer=_URL_REFUSAL,
            state={},
        )

    await repo.insert_message(pool, req.session_id, "user", req.message)

    session = await session_service.get_session(
        app_name=settings.APP_NAME,
        user_id=str(req.user_id),
        session_id=str(req.session_id),
    )
    if session is None:
        video_ids = [str(v) for v in jsonb_list(comparison["video_ids"])]
        session = await session_service.create_session(
            app_name=settings.APP_NAME,
            user_id=str(req.user_id),
            session_id=str(req.session_id),
            state={
                K.VIDEO_IDS: video_ids,
                K.METADATA: jsonb_metadata(comparison["metadata"]),
            },
        )

    user_content = genai_types.Content(
        role="user", parts=[genai_types.Part(text=req.message)]
    )

    # Only Root (small-talk path) and Final (full pipeline path) may produce
    # the user-facing reply. Every other agent (RAG planner/grader, analysis
    # specialists) also emits is_final_response=True events carrying JSON
    # briefs — we must NOT surface those.
    root_text = ""
    final_text = ""
    cost_totals = new_totals()
    async for event in runner.run_async(
        user_id=str(req.user_id),
        session_id=session.id,
        new_message=user_content,
    ):
        if not event.is_final_response():
            continue
        if not (event.content and event.content.parts):
            continue
        if event.usage_metadata is not None:
            log_event_cost(event.author, event.usage_metadata, totals=cost_totals)
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
        app_name=settings.APP_NAME,
        user_id=str(req.user_id),
        session_id=session.id,
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
    video_ids = [str(v) for v in jsonb_list(comparison["video_ids"])]
    citations = citations_from_state(state, video_ids)
    await repo.insert_message(
        pool, req.session_id, "assistant", answer, citations=citations
    )

    log_total_cost(cost_totals)

    return ChatResponse(
        session_id=str(req.session_id),
        answer=answer,
        state=state,
    )
