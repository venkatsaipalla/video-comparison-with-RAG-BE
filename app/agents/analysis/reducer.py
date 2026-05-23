"""Reducer — purely deterministic, NO LLM.

Programmatically merges the specialist briefs (each already schema-validated
by its specialist's output_schema) into the unified FinalAnalysis structure.
Skipped or absent briefs become `null`. `confidence` is the lowest among
active briefs. `grounded` is boolean logic over RAG state + evidence
presence. `notes` is built from a small set of templated gap flags.
"""
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from app import state_keys as K

_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


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


def _is_active(brief: dict) -> bool:
    """A brief counts only if it exists and was not skipped."""
    return bool(brief) and not brief.get("skipped", False)


def _has_evidence(brief: dict) -> bool:
    if not _is_active(brief):
        return False
    if brief.get("evidence"):
        return True
    per_video = brief.get("per_video") or {}
    for v in per_video.values():
        if isinstance(v, dict) and v.get("evidence"):
            return True
    return False


def _lowest_confidence(briefs: list[dict]) -> str:
    active = [b.get("confidence", "low") for b in briefs if _is_active(b)]
    if not active:
        return "low"
    return min(active, key=lambda c: _CONF_RANK.get(c, 1))


class AnalysisReducer(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        plan = _parse(state.get(K.ANALYSIS_PLAN))
        context = _parse(state.get(K.CONTEXT))

        summary = _parse(state.get(K.ANALYSIS_SUMMARY))
        comparison = _parse(state.get(K.ANALYSIS_COMPARISON))
        virality = _parse(state.get(K.ANALYSIS_VIRALITY))
        timeline = _parse(state.get(K.ANALYSIS_TIMELINE))
        metadata_brief = _parse(state.get(K.ANALYSIS_METADATA))

        dimensions_used: list[str] = []
        for name, brief in (
            ("summary", summary),
            ("comparison", comparison),
            ("virality", virality),
            ("timeline", timeline),
            ("metadata", metadata_brief),
        ):
            if _is_active(brief):
                dimensions_used.append(name)

        per_video_summary = (
            summary.get("per_video", {}) if _is_active(summary) else {}
        )
        comparison_out = comparison if _is_active(comparison) else None
        virality_out = virality if _is_active(virality) else None
        timeline_out = timeline if _is_active(timeline) else None
        metadata_view = (
            metadata_brief.get("per_video", {})
            if _is_active(metadata_brief)
            else None
        )

        confidence = _lowest_confidence(
            [summary, comparison, virality, timeline]
        )

        rag_grounded = bool(context.get("grounded", True))
        any_active = bool(dimensions_used)
        any_evidence = any(
            _has_evidence(b) for b in (summary, comparison, virality, timeline)
        )
        metadata_only = dimensions_used == ["metadata"]
        grounded = bool(
            rag_grounded
            and any_active
            and (any_evidence or metadata_only)
        )

        notes_parts: list[str] = []
        if not any_active:
            notes_parts.append("no analysis dimensions produced output")
        elif not rag_grounded:
            notes_parts.append("retrieval flagged context as not grounded")
        elif not any_evidence and not metadata_only:
            notes_parts.append("no evidence quotes available across briefs")
        planned = set(plan.get("dimensions") or [])
        missing = sorted(planned - set(dimensions_used))
        if missing:
            notes_parts.append(
                f"planned dimensions missing from output: {','.join(missing)}"
            )
        notes = "; ".join(notes_parts)

        analysis = {
            "dimensions_used": dimensions_used,
            "confidence": confidence,
            "grounded": grounded,
            "notes": notes,
            "per_video_summary": per_video_summary,
            "comparison": comparison_out,
            "virality": virality_out,
            "timeline": timeline_out,
            "metadata_view": metadata_view,
        }

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={K.ANALYSIS: analysis}),
        )


reducer_agent = AnalysisReducer(name="analysis_reducer")
