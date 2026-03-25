"""File-based cache for HTTP responses and extracted product data."""
import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _key_path(key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:32]
    return CACHE_DIR / f"{h}.json"


def get(key: str) -> dict | None:
    p = _key_path(key)
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def set_(key: str, value: dict, max_age_hours: int = 24) -> None:
    p = _key_path(key)
    data = {"value": value, "max_age_hours": max_age_hours}
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def get_cached(key: str) -> dict | None:
    data = get(key)
    if data is None:
        return None
    return data.get("value")
