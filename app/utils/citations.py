from __future__ import annotations

import json
from typing import Any


def _parse_analysis_state(state: dict[str, Any]) -> dict[str, Any] | None:
    analysis = state.get("analysis")
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            return None
    if not analysis or not isinstance(analysis, dict):
        return None
    return analysis


def citations_from_state(
    state: dict[str, Any], video_ids: list[str]
) -> list[dict[str, Any]]:
    """Extract source citations from brain session state (same shape as the FE)."""
    analysis = _parse_analysis_state(state)
    if not analysis:
        return []

    def label_for(video_id: str | None) -> str:
        if not video_id:
            return "Video"
        try:
            i = video_ids.index(video_id)
        except ValueError:
            return video_id
        if i == 0:
            return "Video A"
        if i == 1:
            return "Video B"
        return video_id

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(ev: dict[str, Any]) -> None:
        quote = ev.get("quote")
        if not quote or not isinstance(quote, str):
            return
        vid = ev.get("video_id") or ""
        start = ev.get("start_time")
        key = f"{vid}:{start}:{quote[:40]}"
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "chunk_id": key,
                "video_label": label_for(vid if isinstance(vid, str) else None),
                "video_id": str(vid),
                "start_sec": start,
                "end_sec": ev.get("end_time"),
                "excerpt": quote[:400],
            }
        )

    def collect(obj: Any) -> None:
        if not obj or not isinstance(obj, dict):
            return
        evidence = obj.get("evidence")
        if isinstance(evidence, list):
            for e in evidence:
                if isinstance(e, dict):
                    add(e)
        pvs = obj.get("per_video_summary")
        if isinstance(pvs, dict):
            for v in pvs.values():
                collect(v)
        moments = obj.get("notable_moments")
        if isinstance(moments, list):
            for e in moments:
                if isinstance(e, dict):
                    add(e)

    collect(analysis.get("comparison"))
    collect(analysis.get("virality"))
    collect(analysis.get("timeline"))
    collect(analysis.get("per_video_summary"))

    return out
