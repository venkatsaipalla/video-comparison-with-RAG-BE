"""GPU ingestion client.

IMPORTANT: This module is reserved for the brain repo's /init endpoint only.
No agent (root, RAG, analysis, final) is permitted to import from here. The
ingestion lifecycle is owned exclusively by the /init HTTP entry point so
that video_ids cannot be added or changed mid-session by anything else.
"""
import httpx

from app.config import settings

# Ingestion is slow (transcript fetch + chunking + embedding on GPU side).
# Generous timeout, since GPU repo parallelises 2 URLs internally.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


async def ingest_urls(urls: list[str]) -> dict:
    """POST /ingest on the retrieval (GPU) repo. Returns the raw response JSON."""
    payload = {"urls": urls}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{settings.RETRIEVAL_BASE_URL}/ingest", json=payload)
        r.raise_for_status()
        return r.json()
