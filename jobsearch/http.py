"""Cached HTTP fetching.

Every remote GET goes through here so that re-running the pipeline is cheap and
we never hammer a small NGO's site. Cache entries are keyed by URL hash and
expire after CACHE_TTL.
"""
import hashlib
import json
import time
from pathlib import Path

import requests

from .config import CACHE, HEADERS, TIMEOUT

CACHE_TTL = 60 * 60 * 24  # 24h


def _key(url: str) -> Path:
    return CACHE / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")


def fetch(url: str, *, ttl: int = CACHE_TTL, headers: dict | None = None) -> dict:
    """GET a URL, returning {ok, status, url, text}. Never raises."""
    path = _key(url)
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass

    try:
        r = requests.get(
            url, headers=headers or HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        # Only cache text; skip PDFs and other binaries.
        ctype = r.headers.get("content-type", "")
        text = r.text if "text" in ctype or "json" in ctype else ""
        out = {
            "ok": r.status_code < 400,
            "status": r.status_code,
            "url": r.url,
            "text": text,
            "content_type": ctype,
            # Kept for freshness checks (Last-Modified); lowercased so callers
            # don't have to guess at the server's capitalisation.
            "headers": {k.lower(): v for k, v in r.headers.items()},
        }
    except requests.exceptions.RequestException as e:
        out = {
            "ok": False,
            "status": 0,
            "url": url,
            "text": "",
            "error": f"{type(e).__name__}: {str(e)[:120]}",
        }

    path.write_text(json.dumps(out))
    return out
