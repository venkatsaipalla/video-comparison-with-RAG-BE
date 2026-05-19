from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from uuid import UUID

from openai import AsyncOpenAI

from app.agents.graph import run_router
from app.config import settings
from app.db import repository as repo
from app.db.pool import get_pool
from app.embeddings.openai_embed import embed_query, get_openai
from app.models import Citation


def _video_summary_row(row, label: str) -> str:
    eng = row["engagement"]
    if isinstance(eng, str):
        eng = json.loads(eng)
    return (
        f"{label} ({row['platform']}): {row['title'] or 'Untitled'} by {row['creator'] or 'Unknown'}\n"
        f"  Views: {row['views']}, Likes: {row['likes']}, Comments: {row['comments']}\n"
        f"  Like rate: {eng.get('like_rate')}, Comment rate: {eng.get('comment_rate')}, "
        f"Engagement rate: {eng.get('engagement_rate')}\n"
        f"  Duration: {row['duration_sec']}s"
    )


def _build_context(rows, video_a_id: str, video_b_id: str) -> tuple[str, dict[str, dict]]:
    chunk_map: dict[str, dict] = {}
    lines = []
    for i, r in enumerate(rows, 1):
        vid = str(r["video_id"])
        label = "Video A" if vid == video_a_id else "Video B" if vid == video_b_id else "Video"
        cid = str(r["id"])
        chunk_map[cid] = {
            "chunk_id": cid,
            "video_id": vid,
            "video_label": label,
            "start_sec": r["start_sec"],
            "end_sec": r["end_sec"],
            "excerpt": (r["text"] or "")[:400],
        }
        lines.append(f"[chunk:{cid}] [{label}] {r['text']}")
    return "\n\n".join(lines), chunk_map


def _extract_citations(content: str, chunk_map: dict[str, dict]) -> list[Citation]:
    cites: list[Citation] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[chunk:([a-f0-9-]{36})\]", content, re.I):
        cid = m.group(1)
        if cid in chunk_map and cid not in seen:
            seen.add(cid)
            c = chunk_map[cid]
            cites.append(
                Citation(
                    chunk_id=cid,
                    video_label=c["video_label"],
                    video_id=c["video_id"],
                    start_sec=c["start_sec"],
                    end_sec=c["end_sec"],
                    excerpt=c["excerpt"],
                )
            )
    return cites


async def stream_chat(
    session_id: UUID,
    message: str,
    conversation_id: UUID | None,
) -> AsyncGenerator[dict, None]:
    pool = await get_pool()
    session = await repo.get_session(pool, session_id)
    if not session:
        yield {"event": "error", "data": {"message": "Session not found"}}
        return
    if session["status"] != "ready":
        yield {"event": "error", "data": {"message": f"Session not ready: {session['status']}"}}
        return

    conv_id = await repo.get_or_create_conversation(pool, session_id, conversation_id)
    await repo.insert_message(pool, conv_id, "user", message)

    route = await run_router(message)
    hook_only = route["hook_only"] or route["intent"] == "hook_analysis"

    query_embedding = await embed_query(message)
    rows = await repo.match_chunks(
        pool,
        session_id,
        query_embedding,
        settings.top_k_chunks,
        hook_only=hook_only,
    )

    video_a = await repo.get_video(pool, session["video_a_id"])
    video_b = await repo.get_video(pool, session["video_b_id"])
    video_a_id = str(session["video_a_id"])
    video_b_id = str(session["video_b_id"])

    context, chunk_map = _build_context(rows, video_a_id, video_b_id)
    metrics_block = "\n".join(
        filter(
            None,
            [
                _video_summary_row(video_a, "Video A") if video_a else None,
                _video_summary_row(video_b, "Video B") if video_b else None,
            ],
        )
    )

    history = await repo.get_recent_messages(pool, conv_id, limit=8)
    history_text = "\n".join(
        f"{r['role']}: {r['content']}" for r in reversed(history[1:])
    )
    summary = await repo.get_conversation_summary(pool, conv_id)

    system = f"""You are Creatorjoy's AI co-pilot helping creators compare two social videos.

Use ONLY the retrieved transcript chunks and engagement metrics below. Cite evidence inline as [chunk:UUID] matching the chunk ids provided.

Intent for this question: {route['intent']}
Hook focus: {hook_only}

Engagement metrics:
{metrics_block}

Retrieved context:
{context}

Rules:
- Compare hooks, pacing, and CTAs when asked about first 5 seconds.
- Explain WHY one video may outperform another using engagement rates AND transcript evidence.
- Give actionable improvement suggestions grounded in Video B vs Video A patterns.
- If data is missing, say so honestly.
- End with 2-3 bullet takeaways.
"""

    messages = [{"role": "system", "content": system}]
    if summary:
        messages.append(
            {"role": "system", "content": f"Conversation summary: {summary}"}
        )
    if history_text:
        messages.append({"role": "user", "content": f"Prior turns:\n{history_text}"})
    messages.append({"role": "user", "content": message})

    client = get_openai()
    full_content = ""
    stream = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        stream=True,
        temperature=0.3,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            full_content += delta
            yield {"event": "token", "data": {"text": delta}}

    citations = _extract_citations(full_content, chunk_map)
    valid_ids = set(chunk_map.keys())
    citations = [c for c in citations if c.chunk_id in valid_ids]

    for cite in citations:
        yield {"event": "citation", "data": cite.model_dump()}

    msg_id = await repo.insert_message(
        pool, conv_id, "assistant", full_content, citations
    )

    yield {
        "event": "done",
        "data": {"message_id": str(msg_id), "conversation_id": str(conv_id)},
    }
