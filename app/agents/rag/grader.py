"""Grader (LlmAgent) + EscalationCheck (custom BaseAgent that emits escalate)."""
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.lite_llm import LiteLlm

from app import state_keys as K
from app.config import settings
from app.prompts.rag_grader import GRADER_INSTRUCTION
from app.schemas import GradingResult

grader_agent = LlmAgent(
    name="rag_grader",
    description="Grades whether retrieved chunks suffice to answer the user's question.",
    model=LiteLlm(model=settings.MODEL_ROUTER, reasoning_effort="minimal"),  # T0 nano
    instruction=GRADER_INSTRUCTION,
    output_schema=GradingResult,
    output_key=K.GRADING,
    # output_schema is incompatible with tools and agent transfer; silence
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)


def _parse_grading(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    s = raw.strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        return {}


class GradingEscalationCheck(BaseAgent):
    """Reads state[grading] and emits escalate=True if sufficient."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        grading = _parse_grading(ctx.session.state.get(K.GRADING))
        if grading.get("sufficient") is True:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                actions=EventActions(escalate=True),
            )
        else:
            yield Event(invocation_id=ctx.invocation_id, author=self.name)


escalation_check = GradingEscalationCheck(name="grading_escalation_check")
