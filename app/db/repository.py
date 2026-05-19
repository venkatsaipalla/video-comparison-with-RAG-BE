from __future__ import annotations

import json
import hashlib
from typing import Any
from uuid import UUID

import asyncpg

from app.models import Citation, EngagementMetrics, TranscriptSegment, VideoDocument


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _engagement_to_json(eng: EngagementMetrics) -> str:
    return json.dumps(eng.model_dump())


async def get_video_by_url(pool: asyncpg.Pool, url: str) -> asyncpg.Record | None:
    h = url_hash(url)
    return await pool.fetchrow("SELECT * FROM videos WHERE url_hash = $1", h)


async def upsert_video_pending(
    pool: asyncpg.Pool, url: str, platform: str
) -> UUID:
    h = url_hash(url)
    row = await pool.fetchrow(
        """
        INSERT INTO videos (platform, url, url_hash, ingest_status)
        VALUES ($1, $2, $3, 'pending')
        ON CONFLICT (url_hash) DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        platform,
        url.strip(),
        h,
    )
    return row["id"]


async def update_video_ingesting(pool: asyncpg.Pool, video_id: UUID) -> None:
    await pool.execute(
        "UPDATE videos SET ingest_status = 'ingesting', ingest_error = NULL WHERE id = $1",
        video_id,
    )


async def save_video_document(pool: asyncpg.Pool, video_id: UUID, doc: VideoDocument) -> None:
    eng = doc.engagement
    await pool.execute(
        """
        UPDATE videos SET
          platform = $2,
          external_id = $3,
          title = $4,
          creator = $5,
          thumbnail_url = $6,
          published_at = $7,
          duration_sec = $8,
          views = $9,
          likes = $10,
          comments = $11,
          engagement = $12::jsonb,
          metadata = $13::jsonb,
          ingest_status = 'ready',
          ingest_error = NULL
        WHERE id = $1
        """,
        video_id,
        doc.platform,
        doc.video_id,
        doc.title,
        doc.creator,
        doc.thumbnail_url,
        doc.published_at,
        doc.duration_sec,
        doc.views,
        doc.likes,
        doc.comments,
        _engagement_to_json(eng),
        json.dumps(doc.metadata),
    )

    await pool.execute("DELETE FROM transcript_segments WHERE video_id = $1", video_id)
    if doc.transcript_segments:
        await pool.executemany(
            """
            INSERT INTO transcript_segments (video_id, start_sec, end_sec, text)
            VALUES ($1, $2, $3, $4)
            """,
            [
                (video_id, s.start_sec, s.end_sec, s.text)
                for s in doc.transcript_segments
            ],
        )


async def mark_video_failed(pool: asyncpg.Pool, video_id: UUID, error: str) -> None:
    await pool.execute(
        """
        UPDATE videos SET ingest_status = 'failed', ingest_error = $2
        WHERE id = $1
        """,
        video_id,
        error[:2000],
    )


async def create_session(
    pool: asyncpg.Pool, video_a_id: UUID, video_b_id: UUID
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO sessions (status, video_a_id, video_b_id)
        VALUES ('pending', $1, $2)
        RETURNING id
        """,
        video_a_id,
        video_b_id,
    )
    return row["id"]


async def get_session(pool: asyncpg.Pool, session_id: UUID) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)


async def update_session_status(
    pool: asyncpg.Pool,
    session_id: UUID,
    status: str,
    error_message: str | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE sessions SET status = $2, error_message = $3
        WHERE id = $1
        """,
        session_id,
        status,
        error_message,
    )


async def get_video(pool: asyncpg.Pool, video_id: UUID) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM videos WHERE id = $1", video_id)


async def delete_chunks_for_session(pool: asyncpg.Pool, session_id: UUID) -> None:
    await pool.execute("DELETE FROM chunks WHERE session_id = $1", session_id)


async def insert_chunks(
    pool: asyncpg.Pool,
    session_id: UUID,
    video_id: UUID,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> None:
    for chunk, emb in zip(chunks, embeddings):
        emb_str = "[" + ",".join(str(x) for x in emb) + "]"
        await pool.execute(
            """
            INSERT INTO chunks (
              video_id, session_id, text, start_sec, end_sec,
              is_hook_window, metadata, embedding
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::vector)
            """,
            video_id,
            session_id,
            chunk["text"],
            chunk.get("start_sec"),
            chunk.get("end_sec"),
            chunk.get("is_hook_window", False),
            json.dumps(chunk.get("metadata", {})),
            emb_str,
        )


async def match_chunks(
    pool: asyncpg.Pool,
    session_id: UUID,
    query_embedding: list[float],
    top_k: int,
    hook_only: bool = False,
) -> list[asyncpg.Record]:
    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    return await pool.fetch(
        "SELECT * FROM match_chunks($1::vector, $2, $3, $4)",
        emb_str,
        session_id,
        top_k,
        hook_only,
    )


async def get_or_create_conversation(
    pool: asyncpg.Pool, session_id: UUID, conversation_id: UUID | None
) -> UUID:
    if conversation_id:
        row = await pool.fetchrow(
            "SELECT id FROM conversations WHERE id = $1 AND session_id = $2",
            conversation_id,
            session_id,
        )
        if row:
            return row["id"]
    row = await pool.fetchrow(
        "INSERT INTO conversations (session_id) VALUES ($1) RETURNING id",
        session_id,
    )
    return row["id"]


async def get_recent_messages(
    pool: asyncpg.Pool, conversation_id: UUID, limit: int = 10
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT role, content FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        conversation_id,
        limit,
    )


async def insert_message(
    pool: asyncpg.Pool,
    conversation_id: UUID,
    role: str,
    content: str,
    citations: list[Citation] | None = None,
) -> UUID:
    cites = json.dumps([c.model_dump() for c in (citations or [])])
    row = await pool.fetchrow(
        """
        INSERT INTO messages (conversation_id, role, content, citations)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id
        """,
        conversation_id,
        role,
        content,
        cites,
    )
    return row["id"]


async def get_conversation_summary(pool: asyncpg.Pool, conversation_id: UUID) -> str | None:
    row = await pool.fetchrow(
        "SELECT summary FROM conversations WHERE id = $1", conversation_id
    )
    return row["summary"] if row else None


async def update_conversation_summary(
    pool: asyncpg.Pool, conversation_id: UUID, summary: str
) -> None:
    await pool.execute(
        "UPDATE conversations SET summary = $2 WHERE id = $1",
        conversation_id,
        summary,
    )
