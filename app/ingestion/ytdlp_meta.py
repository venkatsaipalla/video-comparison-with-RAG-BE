from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yt_dlp

from app.config import settings
from app.ingestion.engagement import compute_engagement
from app.ingestion.subtitle_fetch import fetch_subtitle_text
from app.ingestion.ytdlp_opts import metadata_opts
from app.models import Platform, TranscriptSegment


def _parse_count(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def fetch_metadata(url: str, platform: Platform) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(metadata_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    duration = float(info.get("duration") or 0)
    if duration > settings.max_video_duration_sec:
        mins = int(duration // 60)
        cap = int(settings.max_video_duration_sec // 60)
        raise ValueError(
            f"Video is {mins} min; max allowed is {cap} min "
            f"(MAX_VIDEO_DURATION_SEC={settings.max_video_duration_sec}). "
            "Use a shorter clip or raise the limit in .env."
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


def download_subtitles_vtt(url: str, langs: list[str] | None = None) -> str | None:
    """Download captions to a temp VTT via yt-dlp (more reliable than raw timedtext URLs)."""
    langs = langs or ["hi", "en", "en-US"]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(id)s")
        opts = {
            **metadata_opts(),
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": langs,
            "subtitlesformat": "vtt",
            "ignoreerrors": True,
            "outtmpl": out,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        for path in Path(tmp).glob("*.vtt"):
            return path.read_text(encoding="utf-8", errors="ignore")
    return None


def subtitles_to_segments(info: dict[str, Any]) -> list[TranscriptSegment]:
    """Parse auto/manual subtitles from yt-dlp info if available."""
    segments: list[TranscriptSegment] = []
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    tracks = {**subs, **auto}

    preferred = ["en", "en-US", "en-orig", "hi", "hi-IN"]
    vtt_content = None
    for lang in preferred:
        if lang not in tracks:
            continue
        for fmt in tracks[lang]:
            if fmt.get("ext") == "vtt" and fmt.get("url"):
                vtt_content = fetch_subtitle_text(fmt["url"])
                if vtt_content:
                    break
        if vtt_content:
            break

    if not vtt_content:
        for lang, formats in tracks.items():
            for fmt in formats:
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    vtt_content = fetch_subtitle_text(fmt["url"])
                    if vtt_content:
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
        start = _vtt_ts(_strip_vtt_timestamp(parts[0]))
        end = _vtt_ts(_strip_vtt_timestamp(parts[1]))
        text_lines = lines[1:] if "-->" in lines[0] else lines[2:]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"<c>|</c>", "", text).strip()
        if text:
            segments.append(TranscriptSegment(start_sec=start, end_sec=end, text=text))
    return segments


def _strip_vtt_timestamp(ts: str) -> str:
    """YouTube VTT: '00:00:02.149 align:start position:0%' -> '00:00:02.149'."""
    return ts.strip().split()[0] if ts.strip() else ts


def _vtt_ts(ts: str) -> float:
    ts = _strip_vtt_timestamp(ts)
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)
