"""GPU ingestion client.

IMPORTANT: This module is reserved for the brain repo's /init endpoint only.
No agent (root, RAG, analysis, final) is permitted to import from here. The
ingestion lifecycle is owned exclusively by the /init HTTP entry point so
that video_ids cannot be added or changed mid-session by anything else.
"""
import time

import httpx

from app.config import settings
from app.logger import get_logger

log = get_logger("ingest_client")

# Ingestion is slow (transcript fetch + chunking + embedding on GPU side).
# Generous timeout, since GPU repo parallelises 2 URLs internally.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def _preview(s: str, n: int = 300) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 3] + "..."


async def ingest_urls(urls: list[str]) -> dict:
    """POST /ingest on the retrieval (GPU) repo. Returns the raw response JSON."""
    payload = {"urls": urls}

    headers = (
        {"X-API-Key": settings.RETRIEVAL_API_KEY}
        if settings.RETRIEVAL_API_KEY
        else {}
    )

    log.info("POST /ingest urls=%s", urls)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{settings.RETRIEVAL_BASE_URL}/ingest",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        log.error(
            "POST /ingest <- HTTP %d body=%r took=%.3fs",
            e.response.status_code,
            _preview(e.response.text),
            time.perf_counter() - t0,
        )
        raise
    except httpx.HTTPError as e:
        log.error(
            "POST /ingest <- transport error: %s took=%.3fs",
            e,
            time.perf_counter() - t0,
        )
        raise

    dt = time.perf_counter() - t0
    results = data.get("results") or []
    ok = sum(1 for r in results if r.get("success"))
    log.info(
        "POST /ingest <- status=%d ok=%d/%d took=%.3fs",
        r.status_code,
        ok,
        len(results),
        dt,
    )
    return data
