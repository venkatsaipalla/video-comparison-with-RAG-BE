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


def _video_title_from_state(state: dict[str, Any], video_id: str) -> str | None:
    meta = state.get("metadata")
    if not isinstance(meta, dict):
        return None
    row = meta.get(video_id)
    if not isinstance(row, dict):
        return None
    title = row.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def citations_from_state(
    state: dict[str, Any], video_ids: list[str]
) -> list[dict[str, Any]]:
    """Extract source citations from brain session state (same shape as the FE)."""

    def label_for(video_id: str | None) -> str:
        if not video_id:
            return "Video"
        title = _video_title_from_state(state, video_id)
        try:
            i = video_ids.index(video_id)
        except ValueError:
            i = -1
        slot = "Video A" if i == 0 else "Video B" if i == 1 else None
        if title and slot:
            return f"{slot} · {title}"
        if slot:
            return slot
        if title:
            return title
        return video_id

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        video_id: str,
        start: Any,
        end: Any,
        excerpt: str,
        rerank_score: Any = None,
    ) -> None:
        text = excerpt.strip()
        if not text:
            return
        key = f"{video_id}:{start}:{text[:48]}"
        if key in seen:
            return
        seen.add(key)
        row: dict[str, Any] = {
            "chunk_id": key,
            "video_label": label_for(video_id or None),
            "video_id": str(video_id),
            "start_sec": start,
            "end_sec": end,
            "excerpt": text[:400],
        }
        if isinstance(rerank_score, (int, float)):
            row["rerank_score"] = rerank_score
        out.append(row)

    def add_chunk(raw: dict[str, Any]) -> None:
        excerpt = raw.get("text") or raw.get("quote") or ""
        if not isinstance(excerpt, str):
            return
        add(
            str(raw.get("video_id") or ""),
            raw.get("start_time"),
            raw.get("end_time"),
            excerpt,
            raw.get("rerank_score"),
        )

    def add_evidence(ev: dict[str, Any]) -> None:
        quote = ev.get("quote")
        if not isinstance(quote, str):
            return
        add(
            str(ev.get("video_id") or ""),
            ev.get("start_time"),
            ev.get("end_time"),
            quote,
        )

    context_chunks = state.get("context_chunks")
    if isinstance(context_chunks, list):
        for raw in context_chunks:
            if isinstance(raw, dict):
                add_chunk(raw)

    ctx = state.get("context")
    if isinstance(ctx, dict):
        chunks_by_video = ctx.get("chunks_by_video")
        if isinstance(chunks_by_video, dict):
            for chunks in chunks_by_video.values():
                if not isinstance(chunks, list):
                    continue
                for raw in chunks:
                    if isinstance(raw, dict):
                        add_chunk(raw)

    analysis = _parse_analysis_state(state)
    if analysis:

        def collect(obj: Any) -> None:
            if not obj or not isinstance(obj, dict):
                return
            evidence = obj.get("evidence")
            if isinstance(evidence, list):
                for e in evidence:
                    if isinstance(e, dict):
                        add_evidence(e)
            pvs = obj.get("per_video_summary")
            if isinstance(pvs, dict):
                for v in pvs.values():
                    collect(v)
            moments = obj.get("notable_moments")
            if isinstance(moments, list):
                for e in moments:
                    if isinstance(e, dict):
                        add_evidence(e)

        collect(analysis.get("comparison"))
        collect(analysis.get("virality"))
        collect(analysis.get("timeline"))
        collect(analysis.get("per_video_summary"))

    return out
