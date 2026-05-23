"""Thin async client for the external GPU retrieval repo."""
from typing import Any

import httpx

from app.config import settings

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


async def retrieve_chunks(
    query: str,
    video_ids: list[str],
    top_k: int = 5,
    candidate_k: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "chunks",
        "query": query,
        "video_ids": video_ids,
        "top_k": top_k,
    }
    if candidate_k is not None:
        payload["candidate_k"] = candidate_k

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{settings.RETRIEVAL_BASE_URL}/retrieve", json=payload)
        r.raise_for_status()
        return r.json()


async def retrieve_metadata(video_ids: list[str]) -> dict[str, Any]:
    payload = {"mode": "metadata", "video_ids": video_ids}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{settings.RETRIEVAL_BASE_URL}/retrieve", json=payload)
        r.raise_for_status()
        return r.json()
