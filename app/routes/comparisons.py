from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.db import repository as repo
from app.db.jsonb import jsonb_dict, jsonb_list, jsonb_metadata
from app.db.pool import get_pool

router = APIRouter(tags=["comparisons"])


class ComparisonListItem(BaseModel):
    id: str
    title: str | None
    video_a_url: str
    video_b_url: str
    status: str
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: datetime


class ComparisonDetail(BaseModel):
    id: str
    title: str | None
    video_a_url: str
    video_b_url: str
    video_ids: list[str]
    titles: dict[str, str | None]
    metadata: dict[str, dict[str, Any]]
    status: str
    messages: list[MessageItem]


@router.get(
    "/users/{user_id}/comparisons",
    response_model=list[ComparisonListItem],
    dependencies=[Depends(require_api_key)],
)
async def list_user_comparisons(user_id: UUID) -> list[ComparisonListItem]:
    pool = await get_pool()
    if not await repo.get_user(pool, user_id):
        raise HTTPException(status_code=404, detail="user not found")
    rows = await repo.list_comparisons(pool, user_id)
    return [
        ComparisonListItem(
            id=str(r["id"]),
            title=r["title"],
            video_a_url=r["video_a_url"],
            video_b_url=r["video_b_url"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get(
    "/comparisons/{comparison_id}",
    response_model=ComparisonDetail,
    dependencies=[Depends(require_api_key)],
)
async def get_comparison_detail(
    comparison_id: UUID,
    user_id: UUID = Query(..., description="Owner user id from Google sign-in"),
) -> ComparisonDetail:
    pool = await get_pool()
    row = await repo.get_comparison(pool, comparison_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="comparison not found")

    msgs = await repo.list_messages(pool, comparison_id)
    video_ids = [str(v) for v in jsonb_list(row["video_ids"])]
    titles_raw = jsonb_dict(row["titles"], video_ids=video_ids)
    titles = {k: (str(v) if v is not None else None) for k, v in titles_raw.items()}

    return ComparisonDetail(
        id=str(row["id"]),
        title=row["title"],
        video_a_url=row["video_a_url"],
        video_b_url=row["video_b_url"],
        video_ids=video_ids,
        titles=titles,
        metadata=jsonb_metadata(row["metadata"]),
        status=row["status"],
        messages=[
            MessageItem(
                id=str(m["id"]),
                role=m["role"],
                content=m["content"],
                citations=jsonb_list(m["citations"]),
                created_at=m["created_at"],
            )
            for m in msgs
        ],
    )


@router.delete(
    "/comparisons/{comparison_id}",
    dependencies=[Depends(require_api_key)],
)
async def delete_comparison(
    comparison_id: UUID,
    user_id: UUID = Query(..., description="Owner user id from Google sign-in"),
) -> dict[str, bool]:
    pool = await get_pool()
    deleted = await repo.delete_comparison(pool, comparison_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="comparison not found")
    return {"ok": True}
