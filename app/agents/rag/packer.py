"""Packer — deterministic, no LLM. Groups chunks by video, sorts by score,
trims text, and writes the final RAG context handed to Analysis."""
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from app import state_keys as K

_TEXT_TRIM = 320  # chars per chunk stored in state to keep Postgres happy


def _parse_json(raw: Any) -> dict:
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


class RagPacker(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        chunks: list[dict] = list(state.get(K.CONTEXT_CHUNKS) or [])
        metadata: dict[str, dict] = dict(state.get(K.METADATA) or {})
        grading = _parse_json(state.get(K.GRADING))
        plan = _parse_json(state.get(K.RETRIEVAL_PLAN))

        by_video: dict[str, list[dict]] = {}
        for c in chunks:
            vid = c.get("video_id") or "unknown"
            trimmed = {
                "text": (c.get("text") or "")[:_TEXT_TRIM],
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time"),
                "rerank_score": c.get("rerank_score"),
            }
            by_video.setdefault(vid, []).append(trimmed)

        for vid in by_video:
            by_video[vid].sort(
                key=lambda x: (x.get("rerank_score") or 0.0), reverse=True
            )

        queries_used: list[str] = []
        for q in plan.get("queries", []) or []:
            qt = (q.get("q") or "").strip()
            if qt:
                queries_used.append(qt)

        context = {
            "chunks_by_video": by_video,
            "metadata": metadata,
            "queries_used": queries_used,
            "grounded": bool(grading.get("sufficient", False)) or bool(chunks),
            "grading_reason": grading.get("reason_brief"),
        }

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={K.CONTEXT: context}),
        )


packer_agent = RagPacker(name="rag_packer")
