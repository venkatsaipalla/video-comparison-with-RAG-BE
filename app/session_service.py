from google.adk.sessions import DatabaseSessionService

from app.config import settings


def _to_async_url(url: str) -> str:
    """ADK DatabaseSessionService uses async SQLAlchemy; force asyncpg driver."""
    if url.startswith("postgresql+asyncpg://"):
        out = url
    elif url.startswith("postgresql://"):
        out = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        out = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("sqlite:///"):
        out = "sqlite+aiosqlite:///" + url[len("sqlite:///") :]
    else:
        return url
    # Supabase requires TLS (matches app/db/pool.py).
    if "supabase.co" in out and "ssl=" not in out:
        out += "&ssl=require" if "?" in out else "?ssl=require"
    return out


# ADK persists agent sessions/events/state in Postgres (sessions, events, app_states, …).
# App data uses separate tables: users, comparisons, messages (see migrations/).
session_service = DatabaseSessionService(
    db_url=_to_async_url(settings.DATABASE_URL)
)
