"""MetadataLookup — deterministic specialist, NO LLM.

Reads state["metadata"] (populated by the RAG retriever on demand) and
emits a MetadataBrief in the list-of-entries shape used across all the
analysis specialists. Gated on the Router's plan: if "metadata" is not
in dimensions, writes {"skipped": true, "per_video": []}.
"""
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from app import state_keys as K

_METADATA_KEYS = (
    "video_id",
    "title",
    "channel",
    "duration",
    "upload_date",
    "view_count",
    "like_count",
)


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
            brief = {"skipped": True, "per_video": []}
        else:
            metadata = dict(state.get(K.METADATA) or {})
            entries: list[dict] = []
            for vid, md in metadata.items():
                if not isinstance(md, dict):
                    continue
                entry = {k: md.get(k) for k in _METADATA_KEYS}
                entry["video_id"] = vid
                entries.append(entry)
            brief = {"skipped": False, "per_video": entries}

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={K.ANALYSIS_METADATA: brief}),
        )


metadata_lookup_agent = MetadataLookup(name="analysis_metadata_lookup")
