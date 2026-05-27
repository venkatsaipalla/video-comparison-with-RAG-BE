"""Reducer — purely deterministic, NO LLM.

Programmatically merges the specialist briefs into the unified analysis
structure consumed by the Final synthesizer.

Specialist briefs use `list[Entry]` shapes (required for OpenAI structured
outputs strict mode). The Reducer converts those back into
`dict[video_id, ...]` for state["analysis"] so the Final agent can do
direct lookups by video_id.

Skipped or absent briefs become `null` in the final analysis. `confidence`
is the lowest among active briefs. `grounded` is boolean logic over the
RAG grounding flag + presence of any evidence. `notes` is built from a
small set of templated gap flags.
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
    return bool(brief) and not brief.get("skipped", False)


def _list_to_dict_by_video(entries: list) -> dict:
    """Convert [{video_id, ...}, ...] -> {video_id: {...without video_id...}, ...}"""
    out: dict = {}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        vid = e.get("video_id")
        if not vid:
            continue
        out[vid] = {k: v for k, v in e.items() if k != "video_id"}
    return out


def _signals_list_to_dict(entries: list) -> dict:
    """Convert [{video_id, signals[]}, ...] -> {video_id: [signals]}"""
    out: dict = {}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        vid = e.get("video_id")
        if not vid:
            continue
        out[vid] = list(e.get("signals") or [])
    return out


def _has_evidence(brief: dict) -> bool:
    if not _is_active(brief):
        return False
    if brief.get("evidence"):
        return True
    # per_video may be a list of entries each carrying its own evidence list
    for entry in brief.get("per_video", []) or []:
        if isinstance(entry, dict) and entry.get("evidence"):
            return True
    if brief.get("notable_moments"):
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

        # Convert list shapes to dicts keyed by video_id for the Final agent.
        per_video_summary = (
            _list_to_dict_by_video(summary.get("per_video", []))
            if _is_active(summary) else {}
        )

        comparison_out = comparison if _is_active(comparison) else None

        if _is_active(virality):
            virality_out = dict(virality)
            virality_out["per_video_signals"] = _signals_list_to_dict(
                virality.get("per_video_signals", [])
            )
        else:
            virality_out = None

        if _is_active(timeline):
            timeline_out = dict(timeline)
            timeline_out["per_video_hooks"] = _list_to_dict_by_video(
                timeline.get("per_video_hooks", [])
            )
        else:
            timeline_out = None

        metadata_view = (
            _list_to_dict_by_video(metadata_brief.get("per_video", []))
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
