#!/usr/bin/env python3
"""Apply supabase/migrations/001_schema.sql using DATABASE_URL from .env."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db.pool import _connect_kwargs  # noqa: E402


async def main() -> None:
    import asyncpg

    sql = (ROOT / "supabase/migrations/001_schema.sql").read_text()
    conn = await asyncpg.connect(settings.database_url, **_connect_kwargs())
    try:
        await conn.execute(sql)
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
        )
        print("Schema applied. Tables:", ", ".join(r["tablename"] for r in rows))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
