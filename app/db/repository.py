from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.jsonb import jsonb_param


async def upsert_google_user(
    pool: asyncpg.Pool,
    *,
    google_sub: str,
    email: str,
    name: str | None,
    avatar_url: str | None,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        INSERT INTO users (google_sub, email, name, avatar_url, last_login_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (google_sub) DO UPDATE SET
          email = EXCLUDED.email,
          name = COALESCE(EXCLUDED.name, users.name),
          avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
          last_login_at = now(),
          updated_at = now()
        RETURNING *
        """,
        google_sub,
        email,
        name,
        avatar_url,
    )


async def get_user(pool: asyncpg.Pool, user_id: UUID) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def create_comparison(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    video_a_url: str,
    video_b_url: str,
    video_ids: list[str],
    titles: dict[str, str | None],
    metadata: dict[str, dict[str, Any]],
    title: str | None = None,
) -> UUID:
    if not title:
        t_a = titles.get(video_ids[0]) if video_ids else None
        t_b = titles.get(video_ids[1]) if len(video_ids) > 1 else None
        if t_a and t_b:
            title = f"{t_a[:40]} vs {t_b[:40]}"
        else:
            title = "Video comparison"

    row = await pool.fetchrow(
        """
        INSERT INTO comparisons (
          user_id, title, video_a_url, video_b_url,
          video_ids, titles, metadata, status
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, 'ready')
        RETURNING id
        """,
        user_id,
        title,
        video_a_url,
        video_b_url,
        jsonb_param(video_ids),
        jsonb_param(titles),
        jsonb_param(metadata),
    )
    return row["id"]


async def get_comparison(
    pool: asyncpg.Pool, comparison_id: UUID, user_id: UUID
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT * FROM comparisons
        WHERE id = $1 AND user_id = $2
        """,
        comparison_id,
        user_id,
    )


async def list_comparisons(
    pool: asyncpg.Pool, user_id: UUID, limit: int = 50
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, title, video_a_url, video_b_url, status, created_at, updated_at
        FROM comparisons
        WHERE user_id = $1
        ORDER BY updated_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )


async def insert_message(
    pool: asyncpg.Pool,
    comparison_id: UUID,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO messages (comparison_id, role, content, citations)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id
        """,
        comparison_id,
        role,
        content,
        jsonb_param(citations or []),
    )
    await pool.execute(
        "UPDATE comparisons SET updated_at = now() WHERE id = $1",
        comparison_id,
    )
    return row["id"]


async def list_messages(
    pool: asyncpg.Pool, comparison_id: UUID
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, role, content, citations, created_at
        FROM messages
        WHERE comparison_id = $1
        ORDER BY created_at ASC
        """,
        comparison_id,
    )


async def delete_comparison(
    pool: asyncpg.Pool, comparison_id: UUID, user_id: UUID
) -> bool:
    result = await pool.execute(
        """
        DELETE FROM comparisons
        WHERE id = $1 AND user_id = $2
        """,
        comparison_id,
        user_id,
    )
    return result.endswith("1")
