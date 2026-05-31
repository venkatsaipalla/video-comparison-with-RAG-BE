from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, get_pool
from app.routes import auth as auth_routes
from app.routes import chat as chat_routes
from app.routes import comparisons as comparisons_routes
from app.routes import init as init_routes
from app.services.logger import get_logger

log = get_logger("main")

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    applied = await run_migrations()
    if applied:
        log.info("Migrations applied: %s", applied)
    yield
    await close_pool()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(comparisons_routes.router)
app.include_router(init_routes.router)
app.include_router(chat_routes.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.reload,
    )
