from __future__ import annotations

import logging

import yt_dlp

from app.ingestion.detector import detect_platform, extract_youtube_id
from app.ingestion.ytdlp_opts import metadata_opts
from app.ingestion.youtube_transcript import fetch_youtube_transcript
from app.ingestion.ytdlp_meta import (
    download_subtitles_vtt,
    fetch_metadata,
    subtitles_to_segments,
    _parse_vtt,
)
from app.models import Platform, TranscriptSegment, VideoDocument

logger = logging.getLogger(__name__)


def fetch_video_document(url: str) -> VideoDocument:
    platform = detect_platform(url)
    meta = fetch_metadata(url, platform)
    segments = _fetch_transcript(url, platform, meta)

    if not segments:
        raise ValueError(
            "No transcript available for this video. "
            "Try a video with captions enabled, or a different platform URL."
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
