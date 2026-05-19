import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.db import repository as repo
from app.db.pool import get_pool
from app.ingestion import detect_platform
from app.models import CreateSessionRequest, SessionStatusResponse, VideoSummary
from app.services.ingest import ingest_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_video_summary(row) -> VideoSummary | None:
    if not row:
        return None
    eng = row["engagement"]
    if eng is not None and not isinstance(eng, dict):
        import json

        eng = json.loads(eng) if isinstance(eng, str) else eng
    return VideoSummary(
        id=str(row["id"]),
        platform=row["platform"],
        url=row["url"],
        title=row["title"],
        creator=row["creator"],
        thumbnail_url=row["thumbnail_url"],
        duration_sec=row["duration_sec"],
        views=row["views"],
        likes=row["likes"],
        comments=row["comments"],
        engagement=eng or {},
        ingest_status=row["ingest_status"],
        ingest_error=row["ingest_error"],
    )


@router.post("")
async def create_session(body: CreateSessionRequest, background_tasks: BackgroundTasks):
    pool = await get_pool()
    try:
        detect_platform(body.video_a_url)
        detect_platform(body.video_b_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    video_a_id = await repo.upsert_video_pending(
        pool, body.video_a_url, detect_platform(body.video_a_url)
    )
    video_b_id = await repo.upsert_video_pending(
        pool, body.video_b_url, detect_platform(body.video_b_url)
    )
    session_id = await repo.create_session(pool, video_a_id, video_b_id)

    background_tasks.add_task(
        ingest_session,
        session_id,
        body.video_a_url,
        body.video_b_url,
    )

    return {"session_id": str(session_id), "status": "ingesting"}


@router.post("/{session_id}/ingest")
async def trigger_ingest(session_id: UUID, background_tasks: BackgroundTasks):
    pool = await get_pool()
    session = await repo.get_session(pool, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    video_a = await repo.get_video(pool, session["video_a_id"])
    video_b = await repo.get_video(pool, session["video_b_id"])
    if not video_a or not video_b:
        raise HTTPException(status_code=400, detail="Session missing videos")

    background_tasks.add_task(
        ingest_session,
        session_id,
        video_a["url"],
        video_b["url"],
    )
    return {"session_id": str(session_id), "status": "ingesting"}


@router.get("/{session_id}/status", response_model=SessionStatusResponse)
async def session_status(session_id: UUID):
    pool = await get_pool()
    session = await repo.get_session(pool, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    video_a = (
        await repo.get_video(pool, session["video_a_id"])
        if session["video_a_id"]
        else None
    )
    video_b = (
        await repo.get_video(pool, session["video_b_id"])
        if session["video_b_id"]
        else None
    )

    return SessionStatusResponse(
        id=str(session["id"]),
        status=session["status"],
        error_message=session["error_message"],
        video_a=_to_video_summary(video_a),
        video_b=_to_video_summary(video_b),
    )
