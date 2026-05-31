from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth import require_api_key
from app.db import repository as repo
from app.db.pool import get_pool
from app.services.google_auth import verify_google_id_token
from app.services.logger import get_logger

log = get_logger("routes.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=10)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    avatar_url: str | None


@router.post("/google", response_model=UserResponse, dependencies=[Depends(require_api_key)])
async def auth_google(body: GoogleAuthRequest) -> UserResponse:
    log.info("/auth/google start id_token_len=%d", len(body.id_token))
    try:
        claims = verify_google_id_token(body.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=401, detail="invalid Google token") from e

    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise HTTPException(status_code=401, detail="token missing sub or email")

    pool = await get_pool()
    row = await repo.upsert_google_user(
        pool,
        google_sub=sub,
        email=email,
        name=claims.get("name"),
        avatar_url=claims.get("picture"),
    )
    log.info(
        "/auth/google done user_id=%s email=%s name=%r has_avatar=%s",
        row["id"],
        row["email"],
        row["name"],
        bool(row["avatar_url"]),
    )
    return UserResponse(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"],
        avatar_url=row["avatar_url"],
    )
