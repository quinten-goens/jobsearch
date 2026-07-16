"""Headless rendering for JavaScript-built careers pages.

Plenty of these sites (Actiris, COCOF, jobsin.brussels) are Vue/React apps that
serve an empty shell to `requests` and fetch the listings client-side. Those
pages are invisible to the plain HTTP path, so we render them in Chromium.

This is slow (seconds per page, versus milliseconds), so it is opt-in: the
pipeline only reaches for it when the cheap path finds nothing.
"""
import hashlib
import json
import time
from pathlib import Path

from .config import CACHE, HEADERS, UA

RENDER_CACHE = CACHE / "render"
RENDER_CACHE.mkdir(parents=True, exist_ok=True)
RENDER_TTL = 60 * 60 * 12

_browser = None
_playwright = None


def _cache_path(url: str) -> Path:
    return RENDER_CACHE / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")


def _get_browser():
    """One browser for the whole run; launching costs ~1s each time."""
    global _browser, _playwright
    if _browser is None:
        from playwright.sync_api import sync_playwright

        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
    return _browser


def close_browser() -> None:
    global _browser, _playwright
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None


def render(url: str, *, wait_selector: str | None = None, ttl: int = RENDER_TTL) -> dict:
    """Load a URL in Chromium and return {ok, status, url, text}. Never raises."""
    path = _cache_path(url)
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass

    try:
        from playwright.sync_api import TimeoutError as PWTimeout

        browser = _get_browser()
        ctx = browser.new_context(
            user_agent=UA, locale="en-GB", viewport={"width": 1400, "height": 1000}
        )
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # networkidle is the reliable signal that the XHR-loaded listings
            # have arrived, but some sites poll forever and never go idle.
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PWTimeout:
                pass
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=6000)
                except PWTimeout:
                    pass
            out = {
                "ok": bool(resp and resp.status < 400),
                "status": resp.status if resp else 0,
                "url": page.url,
                "text": page.content(),
                "rendered": True,
            }
        finally:
            ctx.close()
    except Exception as e:
        out = {
            "ok": False, "status": 0, "url": url, "text": "",
            "error": f"{type(e).__name__}: {str(e)[:120]}", "rendered": True,
        }

    if out["text"]:
        path.write_text(json.dumps(out))
    return out
