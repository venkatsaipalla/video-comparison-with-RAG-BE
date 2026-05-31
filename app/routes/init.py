"""POST /init — the ONLY entry point that triggers ingestion.

Ingests both URLs on the GPU repo, then creates an ADK session whose state
has video_ids locked. Returns session_id for the frontend to pass into /chat.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app import state_keys as K
from app.config import settings
from app.db import repository as repo
from app.db.pool import get_pool
from app.services.auth import require_api_key
from app.services.ingest_client import ingest_urls
from app.services.logger import bind_context, get_logger
from app.services.session_service import session_service

log = get_logger("routes.init")

router = APIRouter(tags=["init"])


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


class InitRequest(BaseModel):
    user_id: UUID
    urls: list[HttpUrl] = Field(..., min_length=2, max_length=2)


class InitResponse(BaseModel):
    session_id: str
    video_ids: list[str]
    titles: dict[str, str | None]
    metadata: dict[str, dict[str, Any]]


@router.post(
    "/init", response_model=InitResponse, dependencies=[Depends(require_api_key)]
)
async def init_session(req: InitRequest) -> InitResponse:
    bind_context(user_id=str(req.user_id))
    urls = [str(u) for u in req.urls]
    log.info("/init start urls=%s", urls)

    pool = await get_pool()
    if not await repo.get_user(pool, req.user_id):
        raise HTTPException(status_code=404, detail="user not found; sign in first")

    try:
        resp = await ingest_urls(urls, user_id=str(req.user_id))
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

    comparison_id = await repo.create_comparison(
        pool,
        user_id=req.user_id,
        video_a_url=urls[0],
        video_b_url=urls[1],
        video_ids=video_ids,
        titles=titles,
        metadata=metadata,
    )

    # ADK session id = comparison id (persisted in ADK `sessions` table).
    await session_service.create_session(
        app_name=settings.APP_NAME,
        user_id=str(req.user_id),
        session_id=str(comparison_id),
        state={K.VIDEO_IDS: video_ids, K.METADATA: metadata},
    )

    bind_context(session_id=str(comparison_id))
    log.info(
        "/init done comparison_id=%s video_ids=%s titles=%s metadata_keys=%s",
        comparison_id,
        video_ids,
        titles,
        {vid: sorted(md.keys()) for vid, md in metadata.items()},
    )

    return InitResponse(
        session_id=str(comparison_id),
        video_ids=video_ids,
        titles=titles,
        metadata=metadata,
    )
