"""Ordered SQL migrations with schema_migrations tracking."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from app.db.pool import get_pool

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _is_applied(conn: asyncpg.Connection, name: str) -> bool:
    row = await conn.fetchrow(
        "SELECT is_applied FROM schema_migrations WHERE name = $1",
        name,
    )
    return row is not None and row["is_applied"] == 1


async def _mark_applied(conn: asyncpg.Connection, name: str) -> None:
    await conn.execute(
        """
        INSERT INTO schema_migrations (name, is_applied)
        VALUES ($1, 1)
        ON CONFLICT (name) DO UPDATE SET is_applied = 1, applied_at = now()
        """,
        name,
    )


async def run_migrations() -> list[str]:
    """Apply pending migrations in filename order. Returns names applied."""
    if not MIGRATIONS_DIR.is_dir():
        log.warning("No migrations directory at %s", MIGRATIONS_DIR)
        return []

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        return []

    pool = await get_pool()
    applied: list[str] = []

    async with pool.acquire() as conn:
        for path in files:
            name = path.name
            try:
                already = await _is_applied(conn, name)
            except asyncpg.UndefinedTableError:
                already = False

            if already:
                log.info("Migration skip (is_applied=1): %s", name)
                continue

            sql = path.read_text(encoding="utf-8")
            log.info("Applying migration: %s", name)
            await conn.execute(sql)
            await _mark_applied(conn, name)
            applied.append(name)
            log.info("Migration applied: %s", name)

    return applied
