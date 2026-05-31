from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.config import settings
from app.prompts.final import FINAL_INSTRUCTION

# Final synthesizer. Reads state["analysis"] + state["video_ids"] + the
# conversation history (auto-injected by ADK) and writes the user-facing
# answer to state["answer"]. No output_schema — output is conversational
# prose, not JSON. T1 mini is sufficient: heavy work was done upstream.
final_agent = LlmAgent(
    name="final_agent",
    description="Synthesizes the user-facing answer from the unified analysis result.",
    model=LiteLlm(model=settings.MODEL_SYNTH, reasoning_effort="low"),  # T1 mini (gpt-5.1-mini)
    instruction=FINAL_INSTRUCTION,
    output_key=K.ANSWER,
)
