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
import warnings
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .http import fetch

# We deliberately parse everything -- including the occasional sitemap or page
# served as XML -- with the lxml HTML parser, which is fine for our purposes
# (extracting dates/text). bs4's warning about it is just noise in the logs.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Text that changes on every load even when the content is identical -- a CSRF
# token, a session id, today's date printed in a footer, a rotating "X people
# viewing" counter. Stripped before hashing so the fingerprint reflects the
# actual content, not the render. Critical now that a hash change *overrides*
# metadata freshness: a token that rotates per request must not read as a
# content change, or every such page would falsely flip to "fresh" daily.
_VOLATILE = re.compile(
    # key=value / key: value for the usual volatile keys -- consume the VALUE too,
    # not just the keyword, so the rotating part is actually removed.
    r"(csrf|csrftoken|nonce|session(id)?|sid|token|auth|__viewstate|"
    r"__requestverificationtoken|_token|jsessionid|phpsessid|viewstate)"
    r"\s*[=:]\s*[\"']?[\w\-./+%]+|"
    # long hex / base64-ish blobs that are tokens with no keyword nearby
    r"\b[0-9a-f]{16,}\b|\b[A-Za-z0-9\-_]{24,}\b|"
    r"\d{1,2}:\d{2}(:\d{2})?|"          # clock times
    r"\d{4}-\d{2}-\d{2}t\d{2}:\d{2}",   # ISO timestamps
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

    # Always compute the current fingerprint first: a detected content change is
    # the strongest freshness evidence we have, so it gets to override a metadata
    # date that may be stale (a hand-edited NGO page adds a vacancy without the
    # CMS bumping dateModified -- exactly the off-board case we care about).
    cur_hash = _hash_html(r["text"]) if (r["ok"] and r["text"]) else ""
    if cur_hash and prev_hash and cur_hash != prev_hash:
        today = datetime.now(timezone.utc).date().isoformat()
        # The content moved since we last saw it: the page is fresh, full stop.
        return {"date": today, "source": "hash", "age_days": 0,
                "trust": "high", "hash": cur_hash}

    # No content change (or no baseline yet): fall back to whatever date the page
    # publishes about itself, best source first.
    date_str, source = "", ""

    if r["ok"] and r["text"]:
        date_str, source = _from_html(r["text"])

    if not date_str:
        date_str = _from_sitemap(url)
        source = "sitemap" if date_str else ""

    if not date_str:
        date_str = _from_headers(r.get("headers") or {})
        source = "http" if date_str else ""

    # Still nothing from metadata: date it by the hash itself.
    if not date_str and cur_hash:
        if not prev_hash:
            # First time we've fingerprinted it -- no baseline to compare, so we
            # can't claim a date yet. We still return the hash to seed next scan.
            return {"date": "", "source": "hash-seeded", "age_days": None,
                    "trust": "none", "hash": cur_hash}
        # prev_hash exists and (given the override above) equals cur_hash:
        # unchanged since last time.
        if prev_date:
            date_str, source = prev_date, "hash"  # as old as we last recorded it
        else:
            # Unchanged but we never had a date for it (a metadata-less page whose
            # first scan only seeded). Keep it seeded -- a stable baseline with no
            # date yet -- rather than blanking the source, so the fingerprint is
            # preserved and a *future* change still flips it to "hash".
            return {"date": "", "source": "hash-seeded", "age_days": None,
                    "trust": "none", "hash": cur_hash}

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

    # A detected content *change* returned high trust inline above. Reaching here
    # with source "hash" means the opposite -- content unchanged, carrying the
    # prior date forward -- so it's medium, same as before. Last-Modified on a
    # dynamic page is usually the render time, not a content change, so it stays
    # low and is never read as evidence a page is fresh.
    trust = {"jsonld": "high", "meta": "high", "sitemap": "medium",
             "hash": "medium", "http": "low"}.get(source, "none")
    return {"date": date_str, "source": source, "age_days": age,
            "trust": trust, "hash": cur_hash}


def _empty() -> dict:
    return {"date": "", "source": "", "age_days": None, "trust": "none",
            "hash": ""}
