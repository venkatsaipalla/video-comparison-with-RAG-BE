from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.agents.analysis._gate import make_gate
from app.config import settings
from app.prompts.analysis_virality import VIRALITY_INSTRUCTION
from app.schemas import ViralityBrief

virality_agent = LlmAgent(
    name="analysis_virality",
    description="Performance / virality specialist using metadata + chunks.",
    model=LiteLlm(model=settings.MODEL_WORKER),  # T1 mini
    instruction=VIRALITY_INSTRUCTION,
    output_schema=ViralityBrief,
    output_key=K.ANALYSIS_VIRALITY,
    before_agent_callback=make_gate("virality"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
