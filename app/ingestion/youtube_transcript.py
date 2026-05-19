from __future__ import annotations

import logging
import time

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound

from app.ingestion.detector import extract_youtube_id
from app.models import TranscriptSegment

logger = logging.getLogger(__name__)

PREFERRED_LANGS = ["en", "en-US", "en-GB"]
# Many creator videos only ship Hindi (or other) auto-captions — fetch native first.
GENERATED_FALLBACK_LANGS = [
    "hi",
    "en",
    "es",
    "pt",
    "de",
    "fr",
    "ja",
    "ko",
    "id",
    "ta",
    "te",
    "mr",
]


def _items_to_segments(items) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for item in items:
        start = float(item["start"])
        duration = float(item.get("duration", 0))
        text = (item.get("text") or "").strip()
        if text:
            segments.append(
                TranscriptSegment(
                    start_sec=start,
                    end_sec=start + duration,
                    text=text,
                )
            )
    return segments


def _fetch_with_retry(transcript, *, retries: int = 3) -> list:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return transcript.fetch()
        except Exception as e:
            last_err = e
            err = str(e).lower()
            if "429" in err or "too many requests" in err:
                wait = 2**attempt + 1
                logger.warning(
                    "YouTube transcript rate-limited, retry %s/%s in %ss",
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
                continue
            raise
    raise last_err  # type: ignore[misc]


def fetch_youtube_transcript(url: str) -> list[TranscriptSegment]:
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("Could not parse YouTube video ID from URL")

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    try:
        transcript = transcript_list.find_transcript(PREFERRED_LANGS)
        return _items_to_segments(_fetch_with_retry(transcript))
    except NoTranscriptFound:
        pass

    for lang in GENERATED_FALLBACK_LANGS:
        try:
            transcript = transcript_list.find_generated_transcript([lang])
            return _items_to_segments(_fetch_with_retry(transcript))
        except NoTranscriptFound:
            continue
        except Exception as e:
            logger.warning("Generated transcript %s failed for %s: %s", lang, video_id, e)

    for transcript in transcript_list:
        try:
            # Native track only — translation hits a second timedtext URL and 429s easily.
            return _items_to_segments(_fetch_with_retry(transcript))
        except Exception as e:
            logger.warning(
                "Transcript %s failed for %s: %s",
                getattr(transcript, "language_code", "?"),
                video_id,
                e,
            )

    raise ValueError(
        f"No transcript available for YouTube video {video_id}. "
        "Enable captions on the video or wait a minute and retry (rate limit)."
    )
