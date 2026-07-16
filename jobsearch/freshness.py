"""When was a careers page last actually updated?

A page that hasn't changed in two years is probably not worth checking, so this
is a useful triage signal -- but only if we're honest about how weak it is.
There are four possible sources, and they are not equally trustworthy:

  jsonld / meta  -- the CMS's own "this content changed" stamp. Trustworthy.
  sitemap        -- <lastmod> for this URL. Usually trustworthy.
  http           -- the Last-Modified header. On a dynamically rendered page
                    this is often just "now", meaning "the server built this
                    response", not "the content changed". Weak.
  visible        -- a date printed on the page ("Posted 3 July 2026").

We record the source alongside the date so the UI can say how much to trust it,
and never claim a page is stale on the strength of a missing header.
"""
import re
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from .http import fetch

ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")

META_KEYS = (
    ("meta", {"property": "article:modified_time"}),
    ("meta", {"property": "og:updated_time"}),
    ("meta", {"name": "last-modified"}),
    ("meta", {"itemprop": "dateModified"}),
)


def _from_headers(headers: dict) -> str:
    lm = headers.get("last-modified") or headers.get("Last-Modified")
    if not lm:
        return ""
    try:
        return parsedate_to_datetime(lm).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _from_html(html: str) -> tuple[str, str]:
    """(iso_date, source) from the CMS's own modification stamps."""
    soup = BeautifulSoup(html, "lxml")
    for tag, attrs in META_KEYS:
        el = soup.find(tag, attrs=attrs)
        if el and el.get("content"):
            m = ISO.search(el["content"])
            if m:
                return m.group(1), "meta"

    # JSON-LD dateModified, without insisting on well-formed JSON: these blocks
    # are frequently invalid, and a regex over the raw text is more robust.
    m = re.search(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})', html, re.I)
    if m:
        return m.group(1), "jsonld"
    return "", ""


def _from_sitemap(url: str) -> str:
    """<lastmod> for this URL, from the site's sitemap."""
    p = urllib.parse.urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        r = fetch(root + path, ttl=60 * 60 * 24 * 7)
        if not r["ok"] or "<" not in r["text"]:
            continue
        soup = BeautifulSoup(r["text"], "xml")
        # A sitemap index points at child sitemaps; follow the first few.
        children = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
        if soup.find("sitemapindex"):
            for child in children[:5]:
                got = _lastmod_in(child, url)
                if got:
                    return got
            continue
        got = _lastmod_for_url(soup, url)
        if got:
            return got
    return ""


def _lastmod_in(sitemap_url: str, target: str) -> str:
    r = fetch(sitemap_url, ttl=60 * 60 * 24 * 7)
    if not r["ok"] or "<" not in r["text"]:
        return ""
    return _lastmod_for_url(BeautifulSoup(r["text"], "xml"), target)


def _lastmod_for_url(soup: BeautifulSoup, target: str) -> str:
    target = target.rstrip("/")
    for entry in soup.find_all("url"):
        loc = entry.find("loc")
        if not loc:
            continue
        if loc.get_text(strip=True).rstrip("/") == target:
            lm = entry.find("lastmod")
            if lm:
                m = ISO.search(lm.get_text(strip=True))
                if m:
                    return m.group(1)
    return ""


def last_updated(url: str) -> dict:
    """{'date': ISO or '', 'source': str, 'age_days': int|None, 'trust': str}."""
    if not url:
        return {"date": "", "source": "", "age_days": None, "trust": "none"}

    r = fetch(url)
    date_str, source = "", ""

    if r["ok"] and r["text"]:
        date_str, source = _from_html(r["text"])

    if not date_str:
        date_str = _from_sitemap(url)
        source = "sitemap" if date_str else ""

    if not date_str:
        date_str = _from_headers(r.get("headers") or {})
        source = "http" if date_str else ""

    if not date_str:
        return {"date": "", "source": "", "age_days": None, "trust": "none"}

    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - d).days
    except ValueError:
        return {"date": "", "source": "", "age_days": None, "trust": "none"}

    # Last-Modified on a dynamic page is usually the render time, not a content
    # change, so it must not be read as evidence the page is fresh.
    trust = {"jsonld": "high", "meta": "high", "sitemap": "medium",
             "http": "low"}.get(source, "none")
    return {"date": date_str, "source": source, "age_days": age, "trust": trust}
