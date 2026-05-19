from __future__ import annotations


def metadata_opts() -> dict:
    """yt-dlp options for metadata / subtitle extraction (no download)."""
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # YouTube often breaks default clients; android + web are reliable for extract_info.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
