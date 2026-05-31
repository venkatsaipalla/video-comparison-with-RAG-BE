"""Minimal per-event LLM cost logging.

ADK 1.31.1 sets `event.usage_metadata` (a
`google.genai.types.GenerateContentResponseUsageMetadata`) on any event
emitted from an LLM call. LiteLLM populates it from the OpenAI response.

We map the agent name (`event.author`) to the configured model id via
`settings.MODEL_ROUTER` / `MODEL_WORKER` / `MODEL_SYNTH`, look up the
per-token price, and log a single line per LLM event.
"""
from __future__ import annotations

from app.config import settings
from app.services.logger import get_logger

log = get_logger("cost")

# USD per 1M tokens. Update here when OpenAI repricing happens.
_PRICES: dict[str, dict[str, float]] = {
    "gpt-5.1-nano": {"input": 0.05, "output": 0.40},
    "gpt-5.1-mini": {"input": 0.25, "output": 2.00},
}

# author -> configured model id (matches agent definitions).
_AUTHOR_MODEL: dict[str, str] = {
    "root_agent": settings.MODEL_ROUTER,
    "rag_planner": settings.MODEL_ROUTER,
    "rag_grader": settings.MODEL_ROUTER,
    "analysis_router": settings.MODEL_ROUTER,
    "analysis_summarizer": settings.MODEL_WORKER,
    "analysis_comparator": settings.MODEL_WORKER,
    "analysis_virality": settings.MODEL_WORKER,
    "analysis_timeline": settings.MODEL_WORKER,
    "final_agent": settings.MODEL_SYNTH,
}


def _price_key(model_id: str) -> str | None:
    """Map a LiteLLM-style id (e.g. 'openai/gpt-5.1-nano') to a _PRICES key."""
    if not model_id:
        return None
    tail = model_id.split("/")[-1].lower()
    for key in _PRICES:
        if key in tail:
            return key
    return None


def log_event_cost(author: str, usage_metadata) -> None:
    """Log token usage + USD cost for one LLM event. Safe to call with None."""
    if usage_metadata is None:
        return

    input_tokens = getattr(usage_metadata, "prompt_token_count", None) or 0
    output_tokens = getattr(usage_metadata, "candidates_token_count", None) or 0
    cached_tokens = getattr(usage_metadata, "cached_content_token_count", None) or 0

    model_id = _AUTHOR_MODEL.get(author, "")
    key = _price_key(model_id)
    if key is None:
        log.info(
            "llm_usage author=%s model=%s input=%d output=%d cached=%d cost=unknown",
            author, model_id or "?", input_tokens, output_tokens, cached_tokens,
        )
        return

    price = _PRICES[key]
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000

    log.info(
        "llm_usage author=%s model=%s input=%d output=%d cached=%d cost_usd=%.6f",
        author, key, input_tokens, output_tokens, cached_tokens, cost,
    )
