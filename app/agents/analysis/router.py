from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.config import settings
from app.prompts.analysis_router import ROUTER_INSTRUCTION
from app.schemas import AnalysisPlan

router_agent = LlmAgent(
    name="analysis_router",
    description="Picks up to 3 analysis dimensions to run.",
    model=LiteLlm(model=settings.MODEL_ROUTER),  # T0 nano
    instruction=ROUTER_INSTRUCTION,
    output_schema=AnalysisPlan,
    output_key=K.ANALYSIS_PLAN,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
