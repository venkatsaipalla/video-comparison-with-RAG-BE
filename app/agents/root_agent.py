from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app.agents.pipeline import pipeline_agent
from app.config import settings
from app.prompts.root import ROOT_INSTRUCTION

# Root coordinator:
# routing failures (narrating the transfer in prose instead of calling
# transfer_to_agent) were materially less frequent on mini even at
# reasoning_effort='low'. Latency cost is acceptable for one routing
# decision per turn.
root_agent = LlmAgent(
    name="root_agent",
    description="Entry coordinator. Classifies intent and delegates to the pipeline.",
    model=LiteLlm(model=settings.MODEL_WORKER, reasoning_effort="low"),
    instruction=ROOT_INSTRUCTION,
    sub_agents=[pipeline_agent],
)