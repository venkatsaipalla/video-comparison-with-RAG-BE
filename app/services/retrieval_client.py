"""Thin async client for the external GPU retrieval repo."""
import time
from typing import Any

import httpx

from app.config import settings
from app.logger import get_logger

log = get_logger("retrieval_client")

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _preview(s: str, n: int = 120) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 3] + "..."


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

    log.info(
        "POST /retrieve mode=chunks video_ids=%s top_k=%d candidate_k=%s query=%r",
        video_ids,
        top_k,
        candidate_k,
        _preview(query),
    )
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.RETRIEVAL_BASE_URL}/retrieve", json=payload
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        log.error(
            "POST /retrieve <- HTTP %d body=%r took=%.3fs",
            e.response.status_code,
            _preview(e.response.text, 300),
            time.perf_counter() - t0,
        )
        raise
    except httpx.HTTPError as e:
        log.error(
            "POST /retrieve <- transport error: %s took=%.3fs",
            e,
            time.perf_counter() - t0,
        )
        raise

    dt = time.perf_counter() - t0
    log.info(
        "POST /retrieve <- status=%d results=%d took=%.3fs",
        r.status_code,
        len(data.get("results") or []),
        dt,
    )
    return data


async def retrieve_metadata(video_ids: list[str]) -> dict[str, Any]:
    payload = {"mode": "metadata", "video_ids": video_ids}

    log.info("POST /retrieve mode=metadata video_ids=%s", video_ids)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.RETRIEVAL_BASE_URL}/retrieve", json=payload
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        log.error(
            "POST /retrieve <- HTTP %d body=%r took=%.3fs",
            e.response.status_code,
            _preview(e.response.text, 300),
            time.perf_counter() - t0,
        )
        raise
    except httpx.HTTPError as e:
        log.error(
            "POST /retrieve <- transport error: %s took=%.3fs",
            e,
            time.perf_counter() - t0,
        )
        raise

    dt = time.perf_counter() - t0
    log.info(
        "POST /retrieve <- status=%d metadata=%d took=%.3fs",
        r.status_code,
        len(data.get("metadata") or []),
        dt,
    )
    return data
