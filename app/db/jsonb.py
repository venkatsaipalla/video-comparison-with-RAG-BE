from __future__ import annotations

import json
from typing import Any


def jsonb_param(value: Any) -> str:
    """Encode for asyncpg JSONB binds (this pool expects str, not list/dict)."""
    return json.dumps(value)


def _loads_if_str(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def jsonb_dict(value: Any, *, video_ids: list[str] | None = None) -> dict[str, Any]:
    """Normalize a JSONB column to a dict (never call dict() on a raw string)."""
    value = _loads_if_str(value)
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list) and video_ids:
        # Legacy shape: parallel title strings aligned with video_ids
        return {
            vid: (value[i] if i < len(value) else None)
            for i, vid in enumerate(video_ids)
        }
    return {}


def jsonb_list(value: Any) -> list[Any]:
    """Normalize a JSONB column to a list."""
    value = _loads_if_str(value)
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return []


def jsonb_metadata(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize comparison metadata JSONB."""
    raw = jsonb_dict(value)
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = v
        else:
            out[str(k)] = {}
    return out
