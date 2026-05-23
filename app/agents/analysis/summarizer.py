from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.agents.analysis._gate import make_gate
from app.config import settings
from app.prompts.analysis_summarizer import SUMMARIZER_INSTRUCTION
from app.schemas import SummaryBrief

summarizer_agent = LlmAgent(
    name="analysis_summarizer",
    description="Per-video grounded summary specialist.",
    model=LiteLlm(model=settings.MODEL_WORKER),  # T1 mini
    instruction=SUMMARIZER_INSTRUCTION,
    output_schema=SummaryBrief,
    output_key=K.ANALYSIS_SUMMARY,
    before_agent_callback=make_gate("summary"),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
