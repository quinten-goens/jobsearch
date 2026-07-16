"""Extract job listings from a careers page.

There is no single scraper that works across 282 bespoke NGO and institution
websites, so this is layered by descending reliability. The first layer that
produces results wins, and every job records which layer found it so the UI can
show how much to trust it:

  1. ATS adapters      - documented JSON APIs. Exact.
  2. JSON-LD JobPosting - schema.org structured data. Exact when present.
  3. Generic heuristic  - look for repeated job-shaped links. Best effort.
"""
import json
import re
import urllib.parse
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .http import fetch

# A link is job-shaped if its text looks like a job title. These are the words
# that actually appear in Brussels policy job titles.
TITLE_WORDS = (
    "officer", "adviser", "advisor", "manager", "coordinator", "assistant",
    "director", "analyst", "consultant", "specialist", "intern", "internship",
    "trainee", "traineeship", "researcher", "fellow", "associate", "lead",
    "head of", "policy", "programme", "program", "project", "communications",
    "advocacy", "campaign", "legal", "finance", "hr ", "administrator",
    "expert", "engineer", "editor", "stagiaire", "chargé", "charge de",
    "responsable", "conseiller", "medewerker", "adviseur", "beleids",
    "attaché", "attache", "secretary", "representative", "liaison",
)

# Link paths that indicate an individual job posting rather than a listing page.
JOB_URL_PAT = re.compile(
    r"/(job|jobs|vacanc|vacature|career|offre|emploi|position|opening|"
    r"opportunit|stage|internship|recruit)[a-z-]*/[^/]{4,}", re.I
)

NOISE = (
    "cookie", "privacy", "newsletter", "subscribe", "sitemap", "contact us",
    "read more", "learn more", "all jobs", "view all", "see all", "back to",
    "home", "search", "filter", "login", "sign in", "register", "apply now",
    "share", "print", "download", "next", "previous", "français", "nederlands",
)

# Publication / closing dates as they appear near a listing. Careers pages
# write dates every way imaginable, so try ISO first (unambiguous), then the
# common EU day-month-year spellings in EN/FR/NL.
MONTHS = {
    m: i for i, ms in enumerate([
        ("january", "jan", "janvier", "januari"),
        ("february", "feb", "février", "fevrier", "februari"),
        ("march", "mar", "mars", "maart"),
        ("april", "apr", "avril"),
        ("may", "mai", "mei"),
        ("june", "jun", "juin", "juni"),
        ("july", "jul", "juillet", "juli"),
        ("august", "aug", "août", "aout", "augustus"),
        ("september", "sep", "sept", "septembre"),
        ("october", "oct", "octobre", "oktober"),
        ("november", "nov", "novembre"),
        ("december", "dec", "décembre", "decembre"),
    ], start=1) for m in ms
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

DATE_PATS = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                       # 2026-07-16
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_RE})\.?\s+(\d{{4}})\b", re.I),  # 16 July 2026
    re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I), # July 16, 2026
    re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"),             # 16/07/2026
)

POSTED_HINT = re.compile(
    r"(posted|published|online since|date de publication|gepubliceerd|"
    r"publication date)", re.I
)
DEADLINE_HINT = re.compile(
    r"(deadline|closing|closes|apply by|expires|date limite|uiterste|"
    r"limite de candidature|until)", re.I
)


def _parse_date(text: str) -> str:
    """First parseable date in `text` -> ISO, else ''."""
    for pat in DATE_PATS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groups()
        try:
            if pat is DATE_PATS[0]:
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            elif pat is DATE_PATS[1]:
                d, mo, y = int(g[0]), MONTHS[g[1].lower().rstrip(".")], int(g[2])
            elif pat is DATE_PATS[2]:
                mo, d, y = MONTHS[g[0].lower().rstrip(".")], int(g[1]), int(g[2])
            else:
                # Day-first: the EU convention, and what these sites use.
                d, mo, y = int(g[0]), int(g[1]), int(g[2])
            return date(y, mo, d).isoformat()
        except (ValueError, KeyError):
            continue
    return ""


def _relative_date(text: str) -> str:
    """'Posted 3 days ago' -> ISO date."""
    m = re.search(r"(\d+)\s*(day|week|month|hour|minute)s?\s+ago", text, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}[unit] * n
        return (date.today() - timedelta(days=days)).isoformat()
    if re.search(r"\b(today|just posted|new)\b", text, re.I):
        return date.today().isoformat()
    if re.search(r"\byesterday\b", text, re.I):
        return (date.today() - timedelta(days=1)).isoformat()
    return ""


def _dates_near(el) -> tuple[str, str]:
    """(posted, deadline) from a listing element and its immediate context."""
    posted = deadline = ""
    # <time datetime="..."> is the most reliable signal when present.
    for t in el.find_all("time"):
        iso = (t.get("datetime") or "")[:10]
        if re.match(r"\d{4}-\d{2}-\d{2}", iso):
            blob = (t.get_text(" ", strip=True) + " " +
                    (t.parent.get_text(" ", strip=True) if t.parent else ""))
            if DEADLINE_HINT.search(blob) and not posted:
                deadline = deadline or iso
            else:
                posted = posted or iso

    text = el.get_text(" ", strip=True)
    # Split on the hint words so a "Deadline 3 Sept" doesn't get read as the
    # publication date, and vice versa.
    for sentence in re.split(r"(?<=[.;|])\s+|\n", text):
        if DEADLINE_HINT.search(sentence) and not deadline:
            deadline = _parse_date(sentence)
        elif POSTED_HINT.search(sentence) and not posted:
            posted = _parse_date(sentence) or _relative_date(sentence)
    if not posted:
        posted = _relative_date(text)
    return posted, deadline


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


# Sidebar filter links look exactly like job links -- same anchor, same
# job-ish words -- but the trailing count gives them away: "Internship (15)",
# "Policy & EU Affairs (50)". A real posting doesn't end in a bare number.
FACET_PAT = re.compile(r"\(\s*\d+\s*\)\s*$")


def _looks_like_title(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 6 or len(t) > 140:
        return False
    if any(n == t or t.startswith(n) for n in NOISE):
        return False
    if FACET_PAT.search(t):
        return False
    return any(w in t for w in TITLE_WORDS)


# ---------------------------------------------------------------- ATS adapters

def _ats_greenhouse(url: str) -> list[dict] | None:
    m = re.search(r"greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)", url, re.I)
    if not m:
        return None
    board = m.group(1)
    r = fetch(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    if not r["ok"]:
        return None
    try:
        data = json.loads(r["text"])
    except json.JSONDecodeError:
        return None
    return [
        {
            "title": _clean(j.get("title")),
            "url": j.get("absolute_url"),
            "location": _clean((j.get("location") or {}).get("name")),
            "posted": j.get("updated_at", "")[:10],
        }
        for j in data.get("jobs", [])
    ]


def _ats_lever(url: str) -> list[dict] | None:
    m = re.search(r"lever\.co/([a-z0-9_-]+)", url, re.I)
    if not m:
        return None
    r = fetch(f"https://api.lever.co/v0/postings/{m.group(1)}?mode=json")
    if not r["ok"]:
        return None
    try:
        data = json.loads(r["text"])
    except json.JSONDecodeError:
        return None
    return [
        {
            "title": _clean(j.get("text")),
            "url": j.get("hostedUrl"),
            "location": _clean((j.get("categories") or {}).get("location")),
            "posted": "",
        }
        for j in data
    ]


def _ats_recruitee(url: str) -> list[dict] | None:
    m = re.search(r"([a-z0-9_-]+)\.recruitee\.com", url, re.I)
    if not m:
        return None
    r = fetch(f"https://{m.group(1)}.recruitee.com/api/offers/")
    if not r["ok"]:
        return None
    try:
        data = json.loads(r["text"])
    except json.JSONDecodeError:
        return None
    return [
        {
            "title": _clean(j.get("title")),
            "url": j.get("careers_url") or j.get("url"),
            "location": _clean(j.get("location")),
            "posted": (j.get("published_at") or "")[:10],
        }
        for j in data.get("offers", [])
    ]


def _ats_teamtailor(url: str) -> list[dict] | None:
    if "teamtailor.com" not in url.lower():
        return None
    r = fetch(url)
    if not r["ok"]:
        return None
    soup = BeautifulSoup(r["text"], "lxml")
    out = []
    for a in soup.select("a[href*='/jobs/']"):
        t = _clean(a.get_text(" "))
        if t and len(t) > 5:
            out.append({
                "title": t,
                "url": urllib.parse.urljoin(r["url"], a["href"]),
                "location": "",
                "posted": "",
            })
    return out or None


ATS_ADAPTERS = (_ats_greenhouse, _ats_lever, _ats_recruitee, _ats_teamtailor)


# ------------------------------------------------------------ structured data

def _jsonld_jobs(soup: BeautifulSoup, base: str) -> list[dict]:
    """schema.org JobPosting blocks. Exact when a site bothers to emit them."""
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        # Sites often wrap postings in an @graph or ItemList
        for item in list(items):
            if isinstance(item, dict):
                items.extend(item.get("@graph", []))
                for el in item.get("itemListElement", []) or []:
                    if isinstance(el, dict):
                        items.append(el.get("item", el))
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            loc = item.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = (loc or {}).get("address") or {}
            if isinstance(addr, str):
                city = addr
            else:
                city = addr.get("addressLocality") or addr.get("addressRegion") or ""
            url = item.get("url") or item.get("sameAs") or base
            out.append({
                "title": _clean(item.get("title")),
                "url": urllib.parse.urljoin(base, url) if url else base,
                "location": _clean(city),
                "posted": (item.get("datePosted") or "")[:10],
                "deadline": (item.get("validThrough") or "")[:10],
            })
    return [j for j in out if j["title"]]


# -------------------------------------------------------------------- generic

def _generic_jobs(soup: BeautifulSoup, base: str) -> list[dict]:
    """Best-effort: collect links that look like individual job postings."""
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        text = _clean(a.get_text(" "))
        full = urllib.parse.urljoin(base, href)
        if full in seen:
            continue

        url_hit = bool(JOB_URL_PAT.search(urllib.parse.urlparse(full).path))
        title_hit = _looks_like_title(text)
        # Require the link text to look like a title. A job-shaped URL alone
        # matches every "View all vacancies" nav link on the site.
        if not title_hit:
            continue
        # And prefer that the URL agrees, unless the title is very job-like.
        if not url_hit and not any(
            w in text.lower() for w in ("officer", "adviser", "advisor", "manager",
                                        "coordinator", "director", "intern",
                                        "analyst", "assistant", "head of")
        ):
            continue

        # Dates live on the surrounding row, not the anchor itself.
        row = a.find_parent(["li", "article", "tr", "div"]) or a
        posted, deadline = _dates_near(row)

        seen.add(full)
        out.append({
            "title": text,
            "url": full,
            "location": "",
            "posted": posted,
            "deadline": deadline,
        })
    return out


# --------------------------------------------------------------------- driver

# Pages that say, in so many words, that there is nothing open right now.
# Distinguishing this from "the scraper failed" matters: most small NGOs post a
# job every few months, so an empty careers page is the normal case, not a bug.
EMPTY_STATE = re.compile(
    r"(no (current |open )?(vacanc|job|position|opening)\w*"
    r"|no vacancies at this time|there are currently no"
    r"|pas d'offre|aucune offre|geen vacature"
    r"|check back (later|soon)|at the moment)",
    re.I,
)


def _extract(html: str, base: str) -> tuple[list[dict], str, bool]:
    """(jobs, method, looks_empty) from a page's HTML."""
    soup = BeautifulSoup(html, "lxml")

    jobs = _jsonld_jobs(soup, base)
    if jobs:
        return jobs, "jsonld", False

    body = soup.get_text(" ", strip=True)
    looks_empty = bool(EMPTY_STATE.search(body))

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return _generic_jobs(soup, base), "generic", looks_empty


def scrape_page(url: str, *, allow_render: bool = True) -> tuple[list[dict], str]:
    """Return (jobs, method). Never raises.

    Tries the cheap paths first and only pays for headless rendering when they
    come up empty and the page doesn't say it has no openings.
    """
    if not url:
        return [], "no-url"

    for adapter in ATS_ADAPTERS:
        try:
            jobs = adapter(url)
        except Exception:
            jobs = None
        if jobs:
            return [j for j in jobs if j.get("title")], f"ats:{adapter.__name__[5:]}"

    r = fetch(url)
    if not r["ok"]:
        return [], f"fetch-failed:{r['status']}"

    jobs, method, looks_empty = _extract(r["text"], r["url"])
    if jobs:
        return jobs, method
    if looks_empty:
        return [], "empty-page"

    # Nothing found and no "we have no openings" note: the listings may be
    # client-side rendered (Vue/React), so retry through a real browser.
    if allow_render:
        from .render import render

        rr = render(url)
        if rr["ok"] and rr["text"]:
            jobs, method, looks_empty = _extract(rr["text"], rr["url"])
            if jobs:
                return jobs, f"rendered:{method}"
            if looks_empty:
                return [], "empty-page"
    return [], "no-jobs-found"
