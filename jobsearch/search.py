"""Web search with a Brave API primary and a DuckDuckGo HTML fallback.

Brave gives clean JSON and a 2k/month free tier. Without a key (or once the
quota is spent) we fall back to scraping DuckDuckGo's no-JS endpoint, which is
lower quality and needs throttling but requires no signup.
"""
import hashlib
import json
import os
import threading
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from .config import BRAVE_API_KEY, CACHE, HEADERS, TIMEOUT

SEARCH_CACHE = CACHE / "search"
SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
SEARCH_TTL = 60 * 60 * 24 * 7  # a week; careers pages don't move that fast

# DuckDuckGo rate-limits hard and returns an empty page rather than a 429 when
# it does. The lock serialises callers so the delay actually holds under
# concurrency -- without it, workers race past the check and all get nothing.
#
# DDG_DELAY is deliberately generous: at ~3s we got soft-banned after roughly
# 20 searches, and once banned every query returns empty until it lifts. For a
# long unattended sweep, slower is the only thing that works. Override with
# JOBSEARCH_DDG_DELAY.
_ddg_lock = threading.Lock()
_last_ddg_call = 0.0
DDG_DELAY = float(os.getenv("JOBSEARCH_DDG_DELAY", "12"))
DDG_RETRIES = 4
# When DDG starts refusing everything, back off for a long stretch rather than
# burning through the remaining orgs collecting empty results.
DDG_COOLDOWN = float(os.getenv("JOBSEARCH_DDG_COOLDOWN", "300"))
_consecutive_empty = 0


def _cache_path(query: str):
    return SEARCH_CACHE / (hashlib.sha256(query.encode()).hexdigest()[:32] + ".json")


# Brave's free tier is quota-limited per month but also rate-limited per second.
# Serialise and space out calls: a 429 storm burns quota for nothing.
_brave_lock = threading.Lock()
_last_brave_call = 0.0
BRAVE_DELAY = float(os.getenv("JOBSEARCH_BRAVE_DELAY", "1.1"))


def _brave(query: str, count: int = 5) -> list[dict] | None:
    """Return results, or None if Brave is unavailable (so we can fall back)."""
    global _last_brave_call
    if not BRAVE_API_KEY:
        return None

    for attempt in range(4):
        with _brave_lock:
            elapsed = time.time() - _last_brave_call
            if elapsed < BRAVE_DELAY:
                time.sleep(BRAVE_DELAY - elapsed)
            _last_brave_call = time.time()
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": count, "country": "be"},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
                timeout=TIMEOUT,
            )
            if r.status_code == 429:
                # Rate limited, not out of quota: back off and retry rather
                # than falling through to DuckDuckGo, which is banned anyway.
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                print(f"  ! Brave rejected the key (HTTP {r.status_code})")
                return None
            if r.status_code != 200:
                return None
            data = r.json()
            return [
                {
                    "url": w.get("url", ""),
                    "title": w.get("title", ""),
                    "snippet": w.get("description", ""),
                    "engine": "brave",
                }
                for w in data.get("web", {}).get("results", [])[:count]
            ]
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError):
            return None
    return None


def _ddg_once(query: str, count: int) -> list[dict]:
    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        out = []
        for res in soup.select(".result")[:count]:
            a = res.select_one("a.result__a")
            if not a:
                continue
            href = a.get("href", "")
            # DDG wraps links in a redirect: /l/?uddg=<encoded>
            if "uddg=" in href:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = qs.get("uddg", [href])[0]
            if not href.startswith("http"):
                continue
            snip = res.select_one(".result__snippet")
            out.append(
                {
                    "url": href,
                    "title": a.get_text(" ", strip=True),
                    "snippet": snip.get_text(" ", strip=True) if snip else "",
                    "engine": "ddg",
                }
            )
        return out
    except requests.exceptions.RequestException:
        return []


def _ddg(query: str, count: int = 5) -> list[dict]:
    """Scrape DuckDuckGo's HTML endpoint, serialised and throttled."""
    global _last_ddg_call, _consecutive_empty
    with _ddg_lock:
        for attempt in range(DDG_RETRIES):
            elapsed = time.time() - _last_ddg_call
            if elapsed < DDG_DELAY:
                time.sleep(DDG_DELAY - elapsed)
            _last_ddg_call = time.time()

            out = _ddg_once(query, count)
            if out:
                _consecutive_empty = 0
                return out

            # Empty almost always means throttled, not "no such page".
            _consecutive_empty += 1
            if _consecutive_empty >= 3:
                # We're banned, not unlucky. Wait it out; pressing on would
                # just mark every remaining org as a false miss.
                print(f"  ! DDG appears to be blocking us — cooling down "
                      f"{DDG_COOLDOWN:.0f}s")
                time.sleep(DDG_COOLDOWN)
                _consecutive_empty = 0
            else:
                time.sleep(DDG_DELAY * (attempt + 2))
        return []


def search(query: str, count: int = 5) -> list[dict]:
    """Cached search. Brave first, DuckDuckGo if Brave is unavailable."""
    path = _cache_path(query)
    if path.exists() and time.time() - path.stat().st_mtime < SEARCH_TTL:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass

    results = _brave(query, count)
    if results is None:
        results = _ddg(query, count)

    # Never cache an empty result: it almost always means we were throttled,
    # and writing it would freeze a transient failure in for the whole TTL.
    if results:
        path.write_text(json.dumps(results))
    return results
