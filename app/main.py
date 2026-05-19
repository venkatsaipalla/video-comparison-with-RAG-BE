from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.pool import close_pool, get_pool
from app.routes import chat, health, sessions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = urlparse(settings.database_url)
    logger.info(
        "Connecting to database host=%s port=%s user=%s",
        db.hostname,
        db.port,
        db.username,
    )
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Creatorjoy Video Comparison RAG API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(chat.router)
