from __future__ import annotations


def cookies_configured() -> bool:
    from app.ingestion.ytdlp_cookies import ensure_cookiefile

    return ensure_cookiefile() is not None


def classify_youtube_failure(error_messages: list[str]) -> str:
    """Turn raw yt-dlp / transcript API errors into a clear user-facing message."""
    text = " ".join(error_messages).lower()
    has_cookies = cookies_configured()

    geo_markers = (
        "not available in your country",
        "not made this video available in your country",
        "geo restricted",
        "georestricted",
        "available in your country",
        "country's laws",
        "region",
        "blocked it in your country",
    )
    if any(m in text for m in geo_markers):
        return (
            "This video is geo-restricted for the server region (often US/EU on Render). "
            "It may play in your browser but cannot be ingested from the cloud host. "
            "Try a globally public video or one without regional limits."
        )

    if "sign in to confirm" in text or "not a bot" in text:
        if has_cookies:
            return (
                "YouTube blocked automated access even with cookies. "
                "Export fresh cookies.txt from your browser, update YTDLP_COOKIES_B64 on Render, "
                "and redeploy."
            )
        return (
            "YouTube blocked the server (bot check). "
            "Add YTDLP_COOKIES_B64 on Render — export cookies while logged into YouTube. "
            "See README."
        )

    if "429" in text or "too many requests" in text:
        return (
            "YouTube rate-limited caption requests. Wait 1–2 minutes, start a new session, "
            "and try again."
        )

    if "private" in text or "members-only" in text or "join this channel" in text:
        return "This video is private or members-only and cannot be ingested."

    if "unavailable" in text and "removed" in text:
        return "This video is unavailable or was removed on YouTube."

    if "no element found" in text or "no transcripts were found" in text:
        return (
            "No usable captions were returned for this video. "
            "Confirm subtitles/auto-captions are enabled on YouTube (often Hindi or English). "
            "If ingest works locally but fails on Render, refresh YTDLP_COOKIES_B64."
        )

    if not has_cookies:
        return (
            "Could not fetch captions. The server has no YouTube cookies (YTDLP_COOKIES_B64). "
            "Add cookies on Render for reliable ingest, or try a different public video."
        )

    return (
        "Could not fetch captions for this video. "
        "Ensure it has subtitles enabled and is publicly available worldwide."
    )
