"""Scrapers for the Brussels EU-affairs job boards.

These matter more than the per-org scrapers: the boards aggregate live postings
from most of the same organisations, in clean consistent HTML, and a small NGO
that posts twice a year will show up here on the day it posts. Each board is a
hand-written adapter because there are only a few of them and they're stable.
"""
import re
import urllib.parse
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from .http import fetch


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _rel_date(text: str) -> str:
    """'Posted 3 days ago' -> ISO date. Boards rarely give absolute dates."""
    m = re.search(r"(\d+)\s+(day|week|month|hour)s?\s+ago", text, re.I)
    if not m:
        if re.search(r"today|just posted", text, re.I):
            return date.today().isoformat()
        if re.search(r"yesterday", text, re.I):
            return (date.today() - timedelta(days=1)).isoformat()
        return ""
    n, unit = int(m.group(1)), m.group(2).lower()
    days = {"hour": 0, "day": 1, "week": 7, "month": 30}[unit] * n
    return (date.today() - timedelta(days=days)).isoformat()


def _deadline(text: str) -> str:
    """'Deadline 19 August' -> ISO date, assuming the next occurrence."""
    m = re.search(r"deadline\s+(\d{1,2})\s+(\w+)\s*(\d{4})?", text, re.I)
    if not m:
        return ""
    day, month, year = m.group(1), m.group(2), m.group(3)
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            y = year or str(date.today().year)
            d = datetime.strptime(f"{day} {month} {y}", fmt).date()
            # No year given and the date already passed -> it means next year.
            if not year and d < date.today() - timedelta(days=30):
                d = d.replace(year=d.year + 1)
            return d.isoformat()
        except ValueError:
            continue
    return ""


# Countries and cities that show up in Brussels EU-affairs listings. Used to
# tell a location field from a category field when a card omits one of them.
PLACES = (
    "brussels", "bruxelles", "brussel", "belgium", "belgique", "belgië",
    "luxembourg", "france", "paris", "germany", "berlin", "netherlands",
    "amsterdam", "the hague", "spain", "madrid", "italy", "rome", "portugal",
    "lisbon", "ireland", "dublin", "poland", "warsaw", "austria", "vienna",
    "sweden", "denmark", "finland", "greece", "czech", "hungary", "romania",
    "bulgaria", "croatia", "slovak", "sloven", "estonia", "latvia",
    "lithuania", "malta", "cyprus", "geneva", "switzerland", "united kingdom",
    "london", "remote", "hybrid", "europe", "worldwide", "strasbourg",
    "frankfurt", "milan", "barcelona", "antwerp", "leuven", "ghent", "liege",
)


def _is_place(s: str) -> bool:
    low = s.lower()
    return any(p in low for p in PLACES)


def _closing_date(text: str) -> str:
    """'Position closing date: August 15, 2026' -> ISO date."""
    m = re.search(
        r"closing date:?\s*(\w+)\s+(\d{1,2}),?\s*(\d{4})", text, re.I
    )
    if not m:
        return ""
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt
            ).date().isoformat()
        except ValueError:
            continue
    return ""


def eurobrussels() -> list[dict]:
    """EuroBrussels: li.standardJobContainer / li.highlightedJobContainer."""
    out = []
    seen_urls: set[str] = set()
    base = "https://www.eurobrussels.com"
    for page in range(1, 12):
        url = f"{base}/job_search?location=Brussels&page={page}"
        r = fetch(url)
        if not r["ok"]:
            break
        soup = BeautifulSoup(r["text"], "lxml")
        items = soup.select("li[class*=JobContainer]")
        if not items:
            break
        # The board ignores an out-of-range ?page= and re-serves page 1, so an
        # empty page never arrives -- detect the repeat and stop instead.
        page_urls = {
            a["href"] for a in soup.select('a[href*="/job_display/"]') if a.get("href")
        }
        if page_urls and page_urls <= seen_urls:
            break
        seen_urls |= page_urls
        for li in items:
            a = li.select_one('a[href*="/job_display/"]')
            if not a:
                continue
            lines = [x for x in li.get_text("\n", strip=True).split("\n") if x]
            # Layout: [Top Job]? / title / employer / location / blurb / cats...
            lines = [x for x in lines if x.lower() != "top job"]
            title = _clean(a.get_text(" ")) or (lines[0] if lines else "")
            employer = lines[1] if len(lines) > 1 else ""
            location = lines[2] if len(lines) > 2 else "Brussels"
            blob = li.get_text(" ", strip=True)
            out.append({
                "title": title,
                "employer": _clean(employer),
                "location": _clean(location),
                "url": urllib.parse.urljoin(base, a["href"]),
                "posted": _rel_date(blob),
                "deadline": _deadline(blob),
                "source": "EuroBrussels",
            })
    return out


def euractiv() -> list[dict]:
    """Euractiv Jobs: div.eu-job-card__main, listings under /jobs/<slug>/."""
    out = []
    seen: set[str] = set()
    base = "https://jobs.euractiv.com"
    for page in range(1, 12):
        url = f"{base}/browse-jobs/" if page == 1 else f"{base}/browse-jobs/page/{page}/"
        r = fetch(url)
        if not r["ok"]:
            break
        soup = BeautifulSoup(r["text"], "lxml")
        cards = soup.select("div.eu-job-card__main")
        if not cards:
            break
        new = 0
        for card in cards:
            a = card.select_one('a[href*="/jobs/"]')
            if not a:
                continue
            href = urllib.parse.urljoin(base, a["href"])
            if href in seen:
                continue
            seen.add(href)
            new += 1
            blob = card.get_text(" | ", strip=True)
            title = _clean(a.get_text(" "))
            # Cards vary: some omit the category, some the country, so parse by
            # meaning rather than position -- fixed offsets put "Position
            # closing date..." in the location field.
            parts = [
                p for p in (x.strip() for x in blob.split("|"))
                if p and p != title
                and not re.match(r"(hybrid|remote|on-?site|premium|featured)$", p, re.I)
                and not re.search(r"closing date|posted|ago", p, re.I)
            ]
            # A card may carry a category, a location, or both, in that order.
            # Tell them apart by content: locations name places, categories
            # don't.
            category, location = "", ""
            for p in parts[:2]:
                if _is_place(p) and not location:
                    location = _clean(p)
                elif not category:
                    category = _clean(p)
            out.append({
                "title": title,
                "employer": "",  # not on the card; only on the detail page
                "location": _clean(location),
                "category": _clean(category),
                "url": href,
                "posted": _rel_date(blob),
                "deadline": _closing_date(blob) or _deadline(blob),
                "source": "Euractiv Jobs",
            })
        if not new:
            break
    return out


def _dedupe(jobs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for j in jobs:
        key = j.get("url") or (j["title"], j.get("employer"))
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


BOARDS = {"eurobrussels": eurobrussels, "euractiv": euractiv}


def scrape_boards() -> list[dict]:
    out = []
    for name, fn in BOARDS.items():
        try:
            jobs = fn()
        except Exception as e:
            print(f"  ! board {name} failed: {type(e).__name__}: {e}")
            continue
        jobs = [j for j in jobs if j.get("title")]
        print(f"  {name:<16} {len(jobs):>4} jobs")
        out.extend(jobs)
    return _dedupe(out)


if __name__ == "__main__":
    for j in scrape_boards()[:10]:
        print(f"{j['source']:<14} {j['title'][:44]:<44} {j['employer'][:22]}")
