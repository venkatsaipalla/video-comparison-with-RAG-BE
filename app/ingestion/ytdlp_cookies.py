from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_cookie_path: Path | None = None


def ensure_cookiefile() -> str | None:
    """
    Resolve yt-dlp cookie file for YouTube bot checks on cloud IPs (e.g. Render).

    Set one of:
    - YTDLP_COOKIES_FILE: path to Netscape cookies.txt
    - YTDLP_COOKIES_B64: base64-encoded cookies.txt (good for Render secrets)
    - YTDLP_COOKIES: raw Netscape file contents (multiline)
    """
    global _cookie_path
    if _cookie_path is not None and _cookie_path.exists():
        return str(_cookie_path)

    file_path = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if file_path and Path(file_path).is_file():
        _cookie_path = Path(file_path)
        logger.info("yt-dlp using cookies file %s", _cookie_path)
        return str(_cookie_path)

    raw = os.environ.get("YTDLP_COOKIES", "").strip()
    b64 = os.environ.get("YTDLP_COOKIES_B64", "").strip().replace("\n", "").replace(" ", "")
    if b64:
        try:
            raw = base64.b64decode(b64).decode("utf-8")
        except Exception as e:
            logger.warning("Invalid YTDLP_COOKIES_B64: %s", e)
            return None

    if not raw or ".youtube.com" not in raw and "# Netscape" not in raw:
        return None

    fd, name = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
    except Exception:
        os.close(fd)
        raise
    _cookie_path = Path(name)
    logger.info("yt-dlp using cookies from env (temp file)")
    return str(_cookie_path)
