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
import hashlib
import re
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from .http import fetch

ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Text that changes on every load even when the content is identical -- a CSRF
# token, a session id, today's date printed in a footer, a rotating "X people
# viewing" counter. Stripped before hashing so the fingerprint reflects the
# actual content, not the render.
_VOLATILE = re.compile(
    r"csrf|nonce|session|token|__VIEWSTATE|\bcsrftoken\b|"
    r"\d{1,2}:\d{2}(:\d{2})?|"  # clock times
    r"\d{4}-\d{2}-\d{2}t\d{2}:\d{2}",  # ISO timestamps
    re.I,
)


def content_hash(url: str) -> str:
    """A stable fingerprint of a page's meaningful text.

    We can only date about a third of careers pages from their own metadata.
    For the rest, we date them ourselves: hash the visible text now, and on the
    next scan a changed hash *is* the "this page was updated" event -- on a date
    we control, for 100% of readable pages. Returns "" if the page can't be read.
    """
    r = fetch(url)
    if not r["ok"] or not r["text"]:
        return ""
    return _hash_html(r["text"])


def _hash_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # Drop the chrome that shifts independently of the content we care about.
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True).lower()
    text = _VOLATILE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()

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


def last_updated(url: str, *, prev_hash: str = "",
                 prev_date: str = "") -> dict:
    """{'date', 'source', 'age_days', 'trust', 'hash'}.

    `prev_hash` / `prev_date` are the content fingerprint and date we recorded
    on the last scan. When the page exposes no metadata date of its own, they
    let us date it by change: a differing hash means "updated now", a matching
    hash means "unchanged since prev_date". This is what gives the ~1,400
    metadata-less pages a freshness signal at all.
    """
    if not url:
        return _empty()

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

    # Always compute the current fingerprint so callers can store it for next
    # time, regardless of whether a metadata date was found.
    cur_hash = _hash_html(r["text"]) if (r["ok"] and r["text"]) else ""

    # Content-hash fallback: only when nothing better dated the page.
    if not date_str and cur_hash:
        today = datetime.now(timezone.utc).date().isoformat()
        if not prev_hash:
            # First time we've fingerprinted it -- no baseline to compare, so we
            # can't claim a date yet. We still return the hash to seed next scan.
            return {"date": "", "source": "hash-seeded", "age_days": None,
                    "trust": "none", "hash": cur_hash}
        if cur_hash != prev_hash:
            date_str, source = today, "hash"       # changed -> updated today
        elif prev_date:
            date_str, source = prev_date, "hash"    # unchanged -> as old as before

    if not date_str:
        out = _empty()
        out["hash"] = cur_hash
        return out

    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - d).days
    except ValueError:
        out = _empty()
        out["hash"] = cur_hash
        return out

    # Last-Modified on a dynamic page is usually the render time, not a content
    # change, so it must not be read as evidence the page is fresh. A detected
    # content change ("hash") is real evidence, so it earns medium trust.
    trust = {"jsonld": "high", "meta": "high", "sitemap": "medium",
             "hash": "medium", "http": "low"}.get(source, "none")
    return {"date": date_str, "source": source, "age_days": age,
            "trust": trust, "hash": cur_hash}


def _empty() -> dict:
    return {"date": "", "source": "", "age_days": None, "trust": "none",
            "hash": ""}
