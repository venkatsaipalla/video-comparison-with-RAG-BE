from __future__ import annotations

import json
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models import Intent


class RouteResult(TypedDict):
    intent: Intent
    hook_only: bool
    focus_video: Optional[str]


ROUTER_PROMPT = """Classify the user question about two compared social videos.
Return JSON only with keys:
- intent: one of compare_performance, hook_analysis, improvement_suggestions, general
- hook_only: true if question focuses on first 5 seconds / hook / opening
- focus_video: "A", "B", or null for both

Examples:
"Why did video A outperform B?" -> compare_performance, false, null
"Compare hooks in first 5 seconds" -> hook_analysis, true, null
"How do I improve my hook?" -> improvement_suggestions, true, null
"""


async def route_query(message: str) -> RouteResult:
    llm = ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    resp = await llm.ainvoke(
        [
            SystemMessage(content=ROUTER_PROMPT),
            HumanMessage(content=message),
        ]
    )
    text = (resp.content or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}

    intent = data.get("intent", "general")
    if intent not in (
        "compare_performance",
        "hook_analysis",
        "improvement_suggestions",
        "general",
    ):
        intent = "general"

    return RouteResult(
        intent=intent,
        hook_only=bool(data.get("hook_only")),
        focus_video=data.get("focus_video"),
    )
