from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def get_openai() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = get_openai()
    resp = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in resp.data]


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
