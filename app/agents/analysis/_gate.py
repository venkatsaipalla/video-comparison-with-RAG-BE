"""Gate helper: before_agent_callback that skips a specialist's LLM call
when its dimension was not selected by the Router.

Returning a `types.Content` from before_agent_callback bypasses the LLM and
uses the returned content as the agent's output. We return a JSON payload
matching the specialist's output_schema with skipped=true so the Reducer
can ignore it.
"""
import json
import re
from typing import Any, Optional

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from app import state_keys as K


def _parse(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    s = m.group(0) if m else raw
    try:
        return json.loads(s)
    except Exception:
        return {}


def make_gate(dimension: str):
    """Return a before_agent_callback that skips the agent when `dimension`
    is not in the Router's selected dimensions."""

    def _gate(callback_context: CallbackContext) -> Optional[types.Content]:
        plan = _parse(callback_context.state.get(K.ANALYSIS_PLAN))
        dims = plan.get("dimensions") or []
        if dimension in dims:
            return None  # run normally
        # Skip: emit a schema-valid "skipped=true" payload.
        skip_payload = json.dumps({"skipped": True})
        return types.Content(
            role="model", parts=[types.Part(text=skip_payload)]
        )

    return _gate
