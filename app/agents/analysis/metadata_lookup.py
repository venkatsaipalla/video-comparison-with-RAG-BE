"""MetadataLookup — deterministic specialist, NO LLM.

Reads state["metadata"] (populated by the RAG retriever on demand) and
writes the per-video metadata dict into state["analysis_metadata"]. Gated
on the Router's plan: if "metadata" is not in dimensions, writes
{"skipped": true}.
"""
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

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


class MetadataLookup(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        plan = _parse(state.get(K.ANALYSIS_PLAN))
        dims = plan.get("dimensions") or []

        if "metadata" not in dims:
            brief = {"skipped": True, "per_video": {}}
        else:
            metadata = dict(state.get(K.METADATA) or {})
            brief = {"skipped": False, "per_video": metadata}

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={K.ANALYSIS_METADATA: brief}),
        )


metadata_lookup_agent = MetadataLookup(name="analysis_metadata_lookup")
