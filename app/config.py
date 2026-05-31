from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "video-rag-brain"
    ENVIRONMENT: str = "dev"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Postgres — app tables (users, comparisons, messages) + ADK tables
    # (sessions, events, app_states, user_states, adk_internal_metadata) in the same DB.
    DATABASE_URL: str
    OPENAI_API_KEY: str

    # Google Sign-In (verify ID tokens from NextAuth / Google OAuth)
    GOOGLE_CLIENT_ID: str = ""

    MODEL_ROUTER: str = "openai/gpt-5-nano"
    MODEL_WORKER: str = "openai/gpt-5-mini"
    MODEL_SYNTH: str = "openai/gpt-5-mini"

    RETRIEVAL_BASE_URL: str = "http://localhost:9000"
    # Sent as the X-API-Key header on every call to the GPU retrieval repo.
    RETRIEVAL_API_KEY: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000"

    # Clients must send this value in the `X-API-Key` request header.
    BACKEND_API_KEY: str

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def reload(self) -> bool:
        return self.ENVIRONMENT.lower().startswith("dev")


settings = Settings()
