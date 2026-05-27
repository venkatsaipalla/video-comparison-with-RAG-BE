"""Simple API-key auth via the `X-API-Key` request header."""
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """FastAPI dependency. Rejects requests without a valid X-API-Key header.
    Uses a constant-time comparison to avoid timing leaks."""
    if not api_key or not secrets.compare_digest(api_key, settings.BACKEND_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )
