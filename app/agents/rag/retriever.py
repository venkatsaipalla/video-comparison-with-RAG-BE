"""Deterministic retriever — calls the GPU repo, no LLM."""
import asyncio
import json
import re
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from app import state_keys as K
from app.services.retrieval_client import retrieve_chunks, retrieve_metadata


def _parse_plan(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    s = raw.strip()
    # Strip ```json ... ``` fences if the model added them.
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        return {}


class RagRetriever(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        plan = _parse_plan(state.get(K.RETRIEVAL_PLAN))

        existing_chunks: list[dict] = list(state.get(K.CONTEXT_CHUNKS) or [])
        seen_texts: set[str] = set(state.get(K.SEEN_TEXTS) or [])
        metadata: dict[str, dict] = dict(state.get(K.METADATA) or {})
        video_ids: list[str] = list(state.get(K.VIDEO_IDS) or [])

        # ADK session carries the authenticated user_id and the session_id;
        # forward both to the GPU repo on every retrieve call.
        user_id = str(ctx.session.user_id or "")
        session_id = str(ctx.session.id or "")

        coros: list[tuple[str, Any]] = []

        if plan.get("needs_metadata"):
            missing_md = [v for v in video_ids if v not in metadata]
            if missing_md:
                coros.append((
                    "metadata",
                    retrieve_metadata(missing_md, user_id=user_id, session_id=session_id),
                ))

        if plan.get("needs_chunks"):
            queries = (plan.get("queries") or [])[:3]
            for q in queries:
                qtext = (q.get("q") or "").strip()
                if not qtext:
                    continue
                vids = q.get("video_ids") or video_ids
                top_k = int(q.get("top_k") or 5)
                coros.append((
                    "chunks",
                    retrieve_chunks(
                        qtext,
                        vids,
                        user_id=user_id,
                        session_id=session_id,
                        top_k=top_k,
                    ),
                ))

        if not coros:
            yield Event(invocation_id=ctx.invocation_id, author=self.name)
            return

        results = await asyncio.gather(
            *(c for _, c in coros), return_exceptions=True
        )

        new_chunks: list[dict] = []
        for (kind, _), res in zip(coros, results):
            if isinstance(res, Exception):
                continue
            if kind == "metadata":
                for md in res.get("metadata", []) or []:
                    vid = md.get("video_id")
                    if vid:
                        metadata[vid] = md
            elif kind == "chunks":
                for c in res.get("results", []) or []:
                    text = (c.get("text") or "").strip()
                    if not text or text in seen_texts:
                        continue
                    seen_texts.add(text)
                    payload = c.get("metadata") or {}
                    new_chunks.append(
                        {
                            "text": text,
                            "video_id": payload.get("video_id"),
                            "start_time": payload.get("start_time"),
                            "end_time": payload.get("end_time"),
                            "rerank_score": c.get("rerank_score"),
                            "rrf_score": c.get("rrf_score"),
                        }
                    )

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(
                state_delta={
                    K.CONTEXT_CHUNKS: existing_chunks + new_chunks,
                    K.SEEN_TEXTS: list(seen_texts),
                    K.METADATA: metadata,
                }
            ),
        )


retriever_agent = RagRetriever(name="rag_retriever")
