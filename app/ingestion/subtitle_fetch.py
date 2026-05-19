from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_subtitle_text(url: str, *, retries: int = 4) -> str | None:
    """Download subtitle/caption file with backoff on YouTube 429."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries - 1:
                wait = 2**attempt + 2
                logger.warning("Subtitle URL 429, retry in %ss", wait)
                time.sleep(wait)
                continue
            logger.warning("Subtitle URL HTTP %s: %s", e.code, url[:80])
            return None
        except Exception as e:
            last_err = e
            logger.warning("Subtitle fetch failed: %s", e)
            return None
    if last_err:
        logger.warning("Subtitle fetch exhausted retries: %s", last_err)
    return None
