from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.adk.runners import Runner
from google.genai import types as genai_types
from pydantic import BaseModel
from app.agents.root_agent import root_agent
from app.config import settings
from app.session_service import session_service
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title=settings.APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

runner = Runner(
    app_name=settings.APP_NAME,
    agent=root_agent,
    session_service=session_service,
)


class ChatRequest(BaseModel):
    user_id: str
    session_id: str | None = None
    message: str
    video_ids: list[str] | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    state: dict[str, Any]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # Get or create session in Supabase Postgres via DatabaseSessionService.
    if req.session_id:
        session = await session_service.get_session(
            app_name=settings.APP_NAME, user_id=req.user_id, session_id=req.session_id
        )
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
    else:
        initial_state: dict[str, Any] = {}
        if req.video_ids:
            initial_state["video_ids"] = req.video_ids
        session = await session_service.create_session(
            app_name=settings.APP_NAME, user_id=req.user_id, state=initial_state
        )

    # If caller passed video_ids on an existing session, refresh state.
    if req.session_id and req.video_ids:
        await session_service.append_event(
            session=session,
            event={"state_delta": {"video_ids": req.video_ids}},
        )

    user_content = genai_types.Content(
        role="user", parts=[genai_types.Part(text=req.message)]
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=req.user_id,
        session_id=session.id,
        new_message=user_content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    refreshed = await session_service.get_session(
        app_name=settings.APP_NAME, user_id=req.user_id, session_id=session.id
    )
    state = dict(refreshed.state) if refreshed else {}

    return ChatResponse(
        session_id=session.id,
        answer=final_text or state.get("answer", ""),
        state=state,
    )
