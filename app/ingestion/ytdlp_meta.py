from datetime import datetime, timezone
from typing import Any

import yt_dlp

from app.config import settings
from app.ingestion.engagement import compute_engagement
from app.models import Platform, TranscriptSegment


def _parse_count(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def fetch_metadata(url: str, platform: Platform) -> dict[str, Any]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    duration = float(info.get("duration") or 0)
    if duration > settings.max_video_duration_sec:
        raise ValueError(
            f"Video exceeds max duration ({settings.max_video_duration_sec}s). "
            "Use a shorter clip for the demo."
        )

    upload_date = info.get("upload_date")
    published_at = None
    if upload_date:
        try:
            published_at = datetime.strptime(upload_date, "%Y%m%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            published_at = None

    views = _parse_count(info.get("view_count"))
    likes = _parse_count(info.get("like_count"))
    comments = _parse_count(info.get("comment_count"))

    return {
        "video_id": str(info.get("id") or ""),
        "title": info.get("title") or "Untitled",
        "creator": info.get("uploader") or info.get("channel") or "Unknown",
        "thumbnail_url": info.get("thumbnail"),
        "published_at": published_at,
        "duration_sec": duration,
        "views": views,
        "likes": likes,
        "comments": comments,
        "engagement": compute_engagement(views, likes, comments),
        "raw": {
            "description": (info.get("description") or "")[:2000],
            "tags": info.get("tags") or [],
            "webpage_url": info.get("webpage_url") or url,
        },
    }


def subtitles_to_segments(info: dict[str, Any]) -> list[TranscriptSegment]:
    """Parse auto/manual subtitles from yt-dlp info if available."""
    segments: list[TranscriptSegment] = []
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    tracks = {**subs, **auto}

    preferred = ["en", "en-US", "en-orig"]
    vtt_content = None
    for lang in preferred:
        if lang in tracks:
            for fmt in tracks[lang]:
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    import urllib.request

                    vtt_content = urllib.request.urlopen(fmt["url"], timeout=30).read().decode(
                        "utf-8", errors="ignore"
                    )
                    break
        if vtt_content:
            break

    if not vtt_content:
        return segments

    return _parse_vtt(vtt_content)


def _parse_vtt(vtt: str) -> list[TranscriptSegment]:
    import re

    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n\n+", vtt)
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[0] if "-->" in lines[0] else (lines[1] if len(lines) > 1 else "")
        if "-->" not in time_line:
            continue
        m = re.match(
            r"(\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}",
            time_line,
        )
        if not m:
            continue
        parts = time_line.split("-->")
        start = _vtt_ts(parts[0].strip())
        end = _vtt_ts(parts[1].strip())
        text_lines = lines[1:] if "-->" in lines[0] else lines[2:]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            segments.append(TranscriptSegment(start_sec=start, end_sec=end, text=text))
    return segments


def _vtt_ts(ts: str) -> float:
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)
