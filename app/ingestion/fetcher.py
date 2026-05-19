from __future__ import annotations

import logging

import yt_dlp

from app.ingestion.detector import detect_platform, extract_youtube_id
from app.ingestion.ytdlp_opts import metadata_opts
from app.ingestion.youtube_transcript import fetch_youtube_transcript
from app.ingestion.youtube_oembed import fetch_youtube_metadata_oembed
from app.ingestion.ytdlp_meta import (
    download_subtitles_vtt,
    fetch_metadata,
    subtitles_to_segments,
    _parse_vtt,
)
from app.config import settings
from app.models import Platform, TranscriptSegment, VideoDocument

logger = logging.getLogger(__name__)


def _is_youtube_bot_block(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "sign in to confirm" in msg or "not a bot" in msg or "cookies" in msg


def _fetch_metadata_with_fallback(url: str, platform: Platform) -> dict:
    try:
        return fetch_metadata(url, platform)
    except Exception as e:
        if platform not in ("youtube", "youtube_shorts") or not _is_youtube_bot_block(e):
            raise
        logger.warning("yt-dlp blocked on YouTube, using oEmbed metadata: %s", e)
        return fetch_youtube_metadata_oembed(url)


def fetch_video_document(url: str) -> VideoDocument:
    platform = detect_platform(url)
    meta = _fetch_metadata_with_fallback(url, platform)
    segments = _fetch_transcript(url, platform, meta)

    if meta.get("duration_sec", 0) <= 0 and segments:
        meta["duration_sec"] = max(s.end_sec for s in segments)

    if meta["duration_sec"] > settings.max_video_duration_sec:
        mins = int(meta["duration_sec"] // 60)
        cap = int(settings.max_video_duration_sec // 60)
        raise ValueError(
            f"Video is {mins} min; max allowed is {cap} min "
            f"(MAX_VIDEO_DURATION_SEC={settings.max_video_duration_sec})."
        )

    if not segments:
        hint = ""
        if platform in ("youtube", "youtube_shorts"):
            hint = (
                " On cloud hosts (Render), set YTDLP_COOKIES_B64 in env — see README."
            )
        raise ValueError(
            "No transcript available for this video. "
            "Try a video with captions enabled, or a different platform URL."
            + hint
        )

    return VideoDocument(
        platform=platform,
        url=url.strip(),
        video_id=meta["video_id"],
        title=meta["title"],
        creator=meta["creator"],
        published_at=meta["published_at"],
        views=meta["views"],
        likes=meta["likes"],
        comments=meta["comments"],
        duration_sec=meta["duration_sec"],
        thumbnail_url=meta["thumbnail_url"],
        engagement=meta["engagement"],
        transcript_segments=segments,
        metadata=meta["raw"],
    )


def _fetch_transcript(
    url: str, platform: Platform, meta: dict
) -> list[TranscriptSegment]:
    if platform in ("youtube", "youtube_shorts"):
        try:
            return fetch_youtube_transcript(url)
        except Exception as e:
            logger.warning("youtube-transcript-api failed for %s: %s", url, e)

    # yt-dlp: download VTT to disk (avoids 429 on timedtext URLs during dev)
    try:
        vtt = download_subtitles_vtt(
            url, langs=["hi", "en", "en-US"] if platform in ("youtube", "youtube_shorts") else ["en"]
        )
        if vtt:
            segments = _parse_vtt(vtt)
            if segments:
                return segments
    except Exception as e:
        logger.warning("yt-dlp VTT download failed for %s: %s", url, e)

    # yt-dlp: parse subtitle URLs from info dict
    try:
        with yt_dlp.YoutubeDL(metadata_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
        segments = subtitles_to_segments(info)
        if segments:
            return segments
    except Exception as e:
        logger.warning("yt-dlp subtitle URL fallback failed for %s: %s", url, e)

    # Description-only fallback for very short clips
    desc = (meta.get("raw") or {}).get("description") or ""
    if desc:
        return [
            TranscriptSegment(
                start_sec=0.0,
                end_sec=min(meta.get("duration_sec") or 60.0, 60.0),
                text=desc[:4000],
            )
        ]

    return []
