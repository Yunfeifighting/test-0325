"""HTTP client with timeout, retry, User-Agent, and rate limiting."""
import time
from typing import Optional

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 20
RETRIES = 3
RETRY_DELAY = 2
MIN_REQUEST_INTERVAL = 0.5
_last_request_time = 0.0


def _rate_limit() -> None:
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def fetch(url: str, headers: Optional[dict] = None) -> tuple[str | None, int | None]:
    """Fetch URL and return (text, status_code) or (None, None) on failure."""
    _rate_limit()
    hdrs = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if headers:
        hdrs.update(headers)
    for attempt in range(RETRIES + 1):
        try:
            r = requests.get(url, headers=hdrs, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text, r.status_code
        except requests.RequestException as e:
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return None, getattr(e, "response", None) and e.response.status_code or None
    return None, None


def fetch_image_bytes(url: str, max_bytes: int = 2_500_000) -> bytes | None:
    """Fetch image bytes (for Streamlit rendering when hotlink fails)."""
    _rate_limit()
    hdrs = {
        "User-Agent": UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=hdrs, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
        data = b"".join(chunks)
        return data if len(data) > 64 else None
    except requests.RequestException:
        return None
