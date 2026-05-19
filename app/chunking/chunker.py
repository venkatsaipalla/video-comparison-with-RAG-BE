from __future__ import annotations

from app.models import TranscriptSegment

HOOK_WINDOW_SEC = 5.0
MAX_CHUNK_CHARS = 800
OVERLAP_SEC = 1.0


def build_chunks(
    segments: list[TranscriptSegment],
    video_label: str,
) -> list[dict]:
    """Merge transcript segments into time-aligned chunks with hook metadata."""
    if not segments:
        return []

    chunks: list[dict] = []
    buffer_text: list[str] = []
    buffer_start = segments[0].start_sec
    buffer_end = segments[0].end_sec

    def flush():
        nonlocal buffer_text, buffer_start, buffer_end
        if not buffer_text:
            return
        text = " ".join(buffer_text).strip()
        is_hook = buffer_end <= HOOK_WINDOW_SEC or buffer_start < HOOK_WINDOW_SEC
        chunks.append(
            {
                "text": f"[{video_label}] ({_fmt_time(buffer_start)}-{_fmt_time(buffer_end)}) {text}",
                "start_sec": buffer_start,
                "end_sec": buffer_end,
                "is_hook_window": is_hook,
                "metadata": {"video_label": video_label},
            }
        )
        buffer_text = []

    for seg in segments:
        seg_text = seg.text.strip()
        if not seg_text:
            continue

        prospective = " ".join(buffer_text + [seg_text])
        if len(prospective) > MAX_CHUNK_CHARS and buffer_text:
            flush()
            buffer_start = seg.start_sec

        if not buffer_text:
            buffer_start = seg.start_sec
        buffer_text.append(seg_text)
        buffer_end = seg.end_sec

    flush()

    # Ensure at least one explicit hook chunk for first 5 seconds
    hook_segs = [s for s in segments if s.start_sec < HOOK_WINDOW_SEC]
    if hook_segs and not any(c["is_hook_window"] for c in chunks):
        text = " ".join(s.text for s in hook_segs)
        chunks.insert(
            0,
            {
                "text": f"[{video_label}] (hook 0:00-0:05) {text}",
                "start_sec": 0.0,
                "end_sec": min(HOOK_WINDOW_SEC, hook_segs[-1].end_sec),
                "is_hook_window": True,
                "metadata": {"video_label": video_label, "hook": True},
            },
        )

    return chunks


def _fmt_time(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"
