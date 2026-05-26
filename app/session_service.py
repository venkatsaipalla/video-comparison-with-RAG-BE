from google.adk.sessions import DatabaseSessionService
from app.config import settings

def _to_async_url(url: str) -> str:
    # ADK's DatabaseSessionService uses async SQLAlchemy; force asyncpg driver.
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    return url

# ADK persists sessions / state / events into this DB.
session_service = DatabaseSessionService(db_url=_to_async_url(settings.ADK_DATABASE_URL))