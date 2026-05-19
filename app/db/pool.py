from __future__ import annotations

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


def _connect_kwargs() -> dict:
    """Supabase requires SSL for external connections; disable statement cache for pooler."""
    kwargs: dict = {"statement_cache_size": 0}
    if "supabase.co" in settings.database_url:
        kwargs["ssl"] = "require"
    return kwargs


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=10,
            **_connect_kwargs(),
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
