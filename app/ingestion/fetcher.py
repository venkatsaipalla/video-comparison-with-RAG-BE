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
from app.ingestion.errors import classify_youtube_failure
from app.models import Platform, TranscriptSegment, VideoDocument

logger = logging.getLogger(__name__)


def _is_youtube_bot_block(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "sign in to confirm" in msg or "not a bot" in msg


def _is_youtube_geo_block(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        m in msg
        for m in (
            "not available in your country",
            "not made this video available",
            "geo restricted",
            "blocked it in your country",
        )
    )


def _fetch_metadata_with_fallback(url: str, platform: Platform) -> dict:
    try:
        return fetch_metadata(url, platform)
    except Exception as e:
        if platform not in ("youtube", "youtube_shorts"):
            raise
        if _is_youtube_geo_block(e):
            raise ValueError(classify_youtube_failure([str(e)])) from e
        if not _is_youtube_bot_block(e):
            raise
        logger.warning("yt-dlp blocked on YouTube, using oEmbed metadata: %s", e)
        return fetch_youtube_metadata_oembed(url)


def fetch_video_document(url: str) -> VideoDocument:
    platform = detect_platform(url)
    meta = _fetch_metadata_with_fallback(url, platform)
    segments, transcript_errors = _fetch_transcript(url, platform, meta)

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
        raise ValueError(
            _transcript_failure_message(url, platform, transcript_errors)
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


def _transcript_failure_message(
    url: str, platform: Platform, errors: list[str]
) -> str:
    if platform in ("youtube", "youtube_shorts"):
        return classify_youtube_failure(errors)
    return (
        "No transcript available for this video. "
        "Try a URL with captions enabled or a different platform."
    )


def _fetch_transcript(
    url: str, platform: Platform, meta: dict
) -> tuple[list[TranscriptSegment], list[str]]:
    errors: list[str] = []
    is_youtube = platform in ("youtube", "youtube_shorts")
    langs = ["hi", "en", "en-US", "en-GB"] if is_youtube else ["en"]

    # 1) yt-dlp VTT file download — most reliable with cookies on cloud hosts
    try:
        vtt = download_subtitles_vtt(url, langs=langs)
        if vtt:
            segments = _parse_vtt(vtt)
            if segments:
                return segments, errors
    except Exception as e:
        errors.append(str(e))
        logger.warning("yt-dlp VTT download failed for %s: %s", url, e)

    # 2) youtube-transcript-api
    if is_youtube:
        try:
            return fetch_youtube_transcript(url), errors
        except Exception as e:
            errors.append(str(e))
            logger.warning("youtube-transcript-api failed for %s: %s", url, e)

    # 3) yt-dlp subtitle URLs from extract_info
    try:
        with yt_dlp.YoutubeDL(metadata_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
        segments = subtitles_to_segments(info)
        if segments:
            return segments, errors
    except Exception as e:
        errors.append(str(e))
        logger.warning("yt-dlp subtitle URL fallback failed for %s: %s", url, e)

    # 4) Description-only fallback when yt-dlp metadata included it
    desc = (meta.get("raw") or {}).get("description") or ""
    if desc.strip():
        return [
            TranscriptSegment(
                start_sec=0.0,
                end_sec=min(meta.get("duration_sec") or 60.0, 60.0),
                text=desc[:4000],
            )
        ], errors

    return [], errors
