from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.config import settings
from app.prompts.final import FINAL_INSTRUCTION

final_agent = LlmAgent(
    name="final_agent",
    description="Compiles upstream outputs into the user-facing answer.",
    model=LiteLlm(model=settings.MODEL_SYNTH),
    instruction=FINAL_INSTRUCTION,
    output_key="answer",
)
