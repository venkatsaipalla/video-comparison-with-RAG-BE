from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.agents.analysis._gate import make_gate
from app.config import settings
from app.prompts.analysis_comparator import COMPARATOR_INSTRUCTION
from app.schemas import ComparisonBrief

comparator_agent = LlmAgent(
    name="analysis_comparator",
    description="Cross-video comparison specialist.",
    model=LiteLlm(model=settings.MODEL_WORKER),  # T1 mini
    instruction=COMPARATOR_INSTRUCTION,
    output_schema=ComparisonBrief,
    output_key=K.ANALYSIS_COMPARISON,
    before_agent_callback=make_gate("comparison"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
