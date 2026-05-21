from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.config import settings
from app.prompts.analysis import ANALYSIS_INSTRUCTION

analysis_agent = LlmAgent(
    name="analysis_agent",
    description="Classifies the analysis type(s) needed and produces a structured brief.",
    model=LiteLlm(model=settings.MODEL_WORKER),
    instruction=ANALYSIS_INSTRUCTION,
    output_key="analysis",
)
