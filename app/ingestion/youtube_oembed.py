from __future__ import annotations

import json
import urllib.parse
import urllib.request

from app.ingestion.detector import extract_youtube_id
from app.ingestion.engagement import compute_engagement


def fetch_youtube_metadata_oembed(url: str) -> dict:
    """Lightweight metadata when yt-dlp is blocked (no view/like counts)."""
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("Could not parse YouTube video ID from URL")

    oembed_url = (
        "https://www.youtube.com/oembed?"
        + urllib.parse.urlencode({"url": url, "format": "json"})
    )
    with urllib.request.urlopen(oembed_url, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return {
        "video_id": video_id,
        "title": data.get("title") or "Untitled",
        "creator": data.get("author_name") or "Unknown",
        "thumbnail_url": data.get("thumbnail_url"),
        "published_at": None,
        "duration_sec": 0.0,
        "views": None,
        "likes": None,
        "comments": None,
        "engagement": compute_engagement(None, None, None),
        "raw": {
            "description": "",
            "tags": [],
            "webpage_url": url,
            "metadata_source": "oembed",
        },
    }
