from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "video-rag-brain"
    DATABASE_URL: str = 'sqlite:///./gadk.db'
    OPENAI_API_KEY: str

    MODEL_ROUTER: str = "openai/gpt-5-nano"
    MODEL_WORKER: str = "openai/gpt-5-mini"
    MODEL_SYNTH: str = "openai/gpt-5-mini"

    RETRIEVAL_BASE_URL: str = "http://localhost:9000"


settings = Settings()
