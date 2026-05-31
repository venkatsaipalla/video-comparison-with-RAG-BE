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

# USD per 1M tokens. Short-context Standard pricing. Update on repricing.
# `cached_input` is the discounted rate for the portion of prompt tokens
# that hit OpenAI's prompt cache (reported as cached_content_token_count).
_PRICES: dict[str, dict[str, float]] = {
    "gpt-5.4-nano": {"input": 0.20, "cached_input": 0.02, "output": 1.25},
    "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
}

# author -> configured model id (matches agent definitions).
_AUTHOR_MODEL: dict[str, str] = {
    "root_agent": settings.MODEL_WORKER,
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
    """Map a LiteLLM-style id to a _PRICES key."""
    if not model_id:
        return None
    tail = model_id.split("/")[-1].lower()
    for key in _PRICES:
        if key in tail:
            return key
    return None


def new_totals() -> dict:
    """Fresh cumulative-cost accumulator for a single /chat turn."""
    return {"input": 0, "output": 0, "cached": 0, "cost_usd": 0.0}


def log_event_cost(author: str, usage_metadata, totals: dict | None = None) -> None:
    """Log token usage + USD cost for one LLM event. Safe to call with None.

    If `totals` is provided, accumulates this event's numbers into it in place
    so the caller can log a cumulative summary at end of turn.
    """
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
        if totals is not None:
            totals["input"] += input_tokens
            totals["output"] += output_tokens
            totals["cached"] += cached_tokens
        return

    price = _PRICES[key]
    # OpenAI counts cached tokens INSIDE prompt_token_count, so subtract
    # them out before applying the full input rate.
    billable_input = max(input_tokens - cached_tokens, 0)
    cost = (
        billable_input * price["input"]
        + cached_tokens * price["cached_input"]
        + output_tokens * price["output"]
    ) / 1_000_000

    log.info(
        "llm_usage author=%s model=%s input=%d output=%d cached=%d cost_usd=%.6f",
        author, key, input_tokens, output_tokens, cached_tokens, cost,
    )

    if totals is not None:
        totals["input"] += input_tokens
        totals["output"] += output_tokens
        totals["cached"] += cached_tokens
        totals["cost_usd"] += cost


def log_total_cost(totals: dict) -> None:
    """Log the cumulative token + USD totals for a /chat turn."""
    log.info(
        "llm_usage_total input=%d output=%d cached=%d cost_usd=%.6f",
        totals.get("input", 0),
        totals.get("output", 0),
        totals.get("cached", 0),
        totals.get("cost_usd", 0.0),
    )
