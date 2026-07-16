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


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _looks_like_title(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 6 or len(t) > 140:
        return False
    if any(n == t or t.startswith(n) for n in NOISE):
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

        seen.add(full)
        out.append({
            "title": text,
            "url": full,
            "location": "",
            "posted": "",
        })
    return out


# --------------------------------------------------------------------- driver

def scrape_page(url: str) -> tuple[list[dict], str]:
    """Return (jobs, method). Never raises."""
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

    soup = BeautifulSoup(r["text"], "lxml")

    jobs = _jsonld_jobs(soup, r["url"])
    if jobs:
        return jobs, "jsonld"

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    jobs = _generic_jobs(soup, r["url"])
    return jobs, "generic"
