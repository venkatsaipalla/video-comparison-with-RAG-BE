from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models import Platform


def detect_platform(url: str) -> Platform:
    u = url.strip().lower()
    parsed = urlparse(u if u.startswith("http") else f"https://{u}")
    host = (parsed.netloc or "").replace("www.", "")
    path = parsed.path or ""

    if "youtube.com" in host or "youtu.be" in host:
        if "/shorts/" in path:
            return "youtube_shorts"
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"

    raise ValueError(
        f"Unsupported URL host: {host}. Use YouTube, YouTube Shorts, TikTok, or Instagram Reels."
    )


def extract_youtube_id(url: str) -> str | None:
    u = url.strip()
    if "youtu.be/" in u:
        return u.split("youtu.be/")[-1].split("?")[0]
    m = re.search(r"(?:v=|/shorts/|/embed/)([a-zA-Z0-9_-]{11})", u)
    return m.group(1) if m else None
