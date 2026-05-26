from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.agents.pipeline import pipeline_agent
from app.config import settings
from app.prompts.root import ROOT_INSTRUCTION

# Root coordinator: cheap router model. Either answers trivially or
# transfers control to the `pipeline` sub-agent for full analysis.
root_agent = LlmAgent(
    name="root_agent",
    description="Entry coordinator. Classifies intent and delegates to the pipeline.",
    model=LiteLlm(model=settings.MODEL_ROUTER, reasoning_effort="minimal"),
    instruction=ROOT_INSTRUCTION,
    sub_agents=[pipeline_agent],
)
