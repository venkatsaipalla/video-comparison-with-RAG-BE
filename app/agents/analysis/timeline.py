from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.agents.analysis._gate import make_gate
from app.config import settings
from app.prompts.analysis_timeline import TIMELINE_INSTRUCTION
from app.schemas import TimelineBrief

_SKIP_PAYLOAD = {
    "skipped": True,
    "per_video_hooks": [],
    "notable_moments": [],
    "confidence": "low",
}

timeline_agent = LlmAgent(
    name="analysis_timeline",
    description="Timestamp / hook / retention-window specialist.",
    model=LiteLlm(model=settings.MODEL_WORKER, reasoning_effort="low"),  # T1 mini
    instruction=TIMELINE_INSTRUCTION,
    output_schema=TimelineBrief,
    output_key=K.ANALYSIS_TIMELINE,
    before_agent_callback=make_gate("timeline", _SKIP_PAYLOAD),
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
