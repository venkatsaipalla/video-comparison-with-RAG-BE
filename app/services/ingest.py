from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.chunking.chunker import build_chunks
from app.db import repository as repo
from app.db.pool import get_pool
from app.embeddings.openai_embed import embed_texts
from app.ingestion import detect_platform, fetch_video_document

logger = logging.getLogger(__name__)

_ingest_lock = asyncio.Lock()
_running: set[UUID] = set()


async def ingest_session(session_id: UUID, video_a_url: str, video_b_url: str) -> None:
    if session_id in _running:
        return
    _running.add(session_id)
    pool = await get_pool()
    try:
        await repo.update_session_status(pool, session_id, "ingesting")
        video_a_id = await repo.upsert_video_pending(
            pool, video_a_url, detect_platform(video_a_url)
        )
        video_b_id = await repo.upsert_video_pending(
            pool, video_b_url, detect_platform(video_b_url)
        )
        await pool.execute(
            "UPDATE sessions SET video_a_id = $2, video_b_id = $3 WHERE id = $1",
            session_id,
            video_a_id,
            video_b_id,
        )

        await repo.delete_chunks_for_session(pool, session_id)

        ok_a = await _ingest_video(pool, session_id, video_a_id, video_a_url, "Video A")
        # Brief pause reduces YouTube 429s when fetching captions for both videos.
        await asyncio.sleep(3)
        ok_b = await _ingest_video(pool, session_id, video_b_id, video_b_url, "Video B")

        if ok_a and ok_b:
            await repo.update_session_status(pool, session_id, "ready")
        else:
            await repo.update_session_status(
                pool,
                session_id,
                "failed",
                "One or both videos failed to ingest. Check video URLs and captions.",
            )
    except Exception as e:
        logger.exception("Session ingest failed: %s", session_id)
        await repo.update_session_status(pool, session_id, "failed", str(e))
    finally:
        _running.discard(session_id)


async def _ingest_video(
    pool,
    session_id: UUID,
    video_id: UUID,
    url: str,
    label: str,
) -> bool:
    existing = await repo.get_video(pool, video_id)
    if existing and existing["ingest_status"] == "ready":
        await _ensure_chunks_for_session(pool, session_id, video_id, label)
        return True

    try:
        await repo.update_video_ingesting(pool, video_id)
        doc = await asyncio.to_thread(fetch_video_document, url)
        await repo.save_video_document(pool, video_id, doc)
        chunks = build_chunks(doc.transcript_segments, label)
        if not chunks:
            raise ValueError("No chunks produced from transcript")
        texts = [c["text"] for c in chunks]
        embeddings = await embed_texts(texts)
        await repo.insert_chunks(pool, session_id, video_id, chunks, embeddings)
        return True
    except Exception as e:
        logger.exception("Video ingest failed %s: %s", url, e)
        await repo.mark_video_failed(pool, video_id, str(e))
        return False


async def _ensure_chunks_for_session(pool, session_id: UUID, video_id: UUID, label: str):
    """Re-link chunks when video was cached from prior session."""
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM chunks WHERE session_id = $1 AND video_id = $2",
        session_id,
        video_id,
    )
    if count and count > 0:
        return

    video = await repo.get_video(pool, video_id)
    if not video or video["ingest_status"] != "ready":
        return

    segments = await pool.fetch(
        """
        SELECT start_sec, end_sec, text FROM transcript_segments
        WHERE video_id = $1 ORDER BY start_sec
        """,
        video_id,
    )
    from app.models import TranscriptSegment

    segs = [
        TranscriptSegment(start_sec=r["start_sec"], end_sec=r["end_sec"], text=r["text"])
        for r in segments
    ]
    chunks = build_chunks(segs, label)
    texts = [c["text"] for c in chunks]
    embeddings = await embed_texts(texts)
    await repo.insert_chunks(pool, session_id, video_id, chunks, embeddings)
