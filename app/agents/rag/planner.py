from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.config import settings
from app.prompts.rag_planner import PLANNER_INSTRUCTION
from app.schemas import RetrievalPlan

planner_agent = LlmAgent(
    name="rag_planner",
    description="Rewrites the user query and plans 1-3 retrieval calls (chunks and/or metadata).",
    model=LiteLlm(model=settings.MODEL_ROUTER),  # T0 nano
    instruction=PLANNER_INSTRUCTION,
    output_schema=RetrievalPlan,
    output_key=K.RETRIEVAL_PLAN,
    # output_schema is incompatible with tools and agent transfer; silence
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
