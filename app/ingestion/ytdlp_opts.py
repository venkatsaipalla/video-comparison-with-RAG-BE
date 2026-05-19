from __future__ import annotations

from app.ingestion.ytdlp_cookies import ensure_cookiefile


def metadata_opts() -> dict:
    """yt-dlp options for metadata / subtitle extraction (no download)."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # tv_embedded + android often work on datacenter IPs when cookies are set.
        "extractor_args": {
            "youtube": {"player_client": ["tv_embedded", "android", "web"]},
        },
    }
    cookiefile = ensure_cookiefile()
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts
