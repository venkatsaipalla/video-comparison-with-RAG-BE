from youtube_transcript_api import YouTubeTranscriptApi

from app.ingestion.detector import extract_youtube_id
from app.models import TranscriptSegment


def fetch_youtube_transcript(url: str) -> list[TranscriptSegment]:
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("Could not parse YouTube video ID from URL")

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
        try:
            transcript = transcript.translate("en")
        except Exception:
            pass
        items = transcript.fetch()
    except Exception:
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])

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
