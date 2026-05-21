from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.config import settings
from app.prompts.rag import RAG_INSTRUCTION

rag_agent = LlmAgent(
    name="rag_agent",
    description="Plans and (later) executes retrieval against the external retrieval service.",
    model=LiteLlm(model=settings.MODEL_WORKER),
    instruction=RAG_INSTRUCTION,
    output_key="rag_plan",
)
