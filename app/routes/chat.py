import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.agents.chat import stream_chat
from app.db import repository as repo
from app.db.pool import get_pool
from app.models import ChatRequest

router = APIRouter(prefix="/sessions", tags=["chat"])


@router.post("/{session_id}/chat")
async def chat(session_id: UUID, body: ChatRequest):
    pool = await get_pool()
    session = await repo.get_session(pool, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        try:
            async for event in stream_chat(
                session_id, body.message, body.conversation_id
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}),
            }

    return EventSourceResponse(event_generator())
