"""Find each organisation's careers page.

For every org: run a search, take the top N results, fetch each one, and score
it. The score combines cheap signals (does the URL path look like a careers
page? does the domain resemble the org name?) with evidence from the fetched
page itself (does it actually contain job-listing language?). Highest scorer
above a threshold wins; everything else is left for a human to check.
"""
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from .config import BRAVE_API_KEY, DATA, ORGS_JSON
from .http import fetch
from .search import search

DISCOVERED_JSON = DATA / "discovered.json"

# Path patterns that signal a careers page, weighted by how specific they are.
# Regexes rather than substrings because Belgian sites decorate these words
# freely -- "werken-voor-fod-buitenlandse-zaken", "offres-d-emploi",
# "travailler-chez-nous" -- and a fixed list of literals misses most of them.
PATH_HINTS = [
    (r"vacanc|vacature", 5),
    (r"career|carriere|carrière", 5),
    (r"/jobs?\b|/jobs?/|job-?(openings?|offers?|board)", 5),
    (r"werken[-_]?(bij|voor)|werk-bij", 5),
    (r"offres?[-_]?d?[-_]?emploi|emploi", 4),
    (r"travailler[-_]?(chez|pour)", 4),
    (r"work[-_]?(with|for)[-_]?us|join[-_]?(us|our[-_]team)", 4),
    (r"recruit|rekrut", 4),
    (r"empleo|trabaja", 4),
    (r"openings?|hiring|employment", 4),
    (r"opportunit", 3),
    (r"rejoignez|solliciteren", 3),
    (r"human[-_]?resources|ressources[-_]?humaines", 3),
]

# Text that should appear on a real careers page.
BODY_HINTS = [
    "apply now", "job description", "deadline", "full-time", "part-time",
    "we are hiring", "open position", "current vacanc", "job opening",
    "apply by", "closing date", "cv and cover letter", "motivation letter",
    "postuler", "candidature", "solliciteren", "vacature",
]

# Aggregators: real pages, but not the org's own careers page.
AGGREGATORS = (
    "linkedin.com", "glassdoor", "indeed.", "facebook.com", "twitter.com",
    "x.com", "youtube.com", "instagram.com", "wikipedia.org", "crunchbase",
    "jooble", "neuvoo", "talent.com", "jobrapido", "trovit", "adzuna",
)

# Known ATS platforms - if a search lands here it's almost certainly correct,
# and the scraper has an exact adapter for it.
ATS_HOSTS = (
    "greenhouse.io", "lever.co", "workday", "myworkdayjobs.com",
    "smartrecruiters.com", "bamboohr.com", "recruitee.com", "teamtailor.com",
    "personio.", "jobvite.com", "taleo.net", "successfactors",
    "workable.com", "ashbyhq.com", "join.com", "softgarden",
)

# This is a Brussels job search. An org's overseas office often has its own
# perfectly real careers page (Belgian embassy in Washington, Oxfam's Nairobi
# office) that scores just as well as the Brussels one on every other signal.
# Geography is the only thing that separates them.
FOREIGN_HINTS = (
    "unitedstates", "newyorkun", "washington", "london", "paris", "berlin",
    "madrid", "geneva", "newyork", "tokyo", "beijing", "moscow", "ottawa",
    "canberra", "delhi", "nairobi", "dakar", "kinshasa", "rabat", "tunis",
    "ankara", "vienna", "rome", "lisbon", "warsaw", "prague", "dublin",
    "stockholm", "copenhagen", "oslo", "helsinki", "athens", "budapest",
    "bucharest", "sofia", "zagreb", "bogota", "mexico", "lima", "santiago",
    "brasilia", "buenosaires", "/us/", "/uk/", "-usa", "usa.", "amsterdam",
    "thehague", "luxembourg", "strasbourg", "frankfurt", "milan", "barcelona",
)
BRUSSELS_HINTS = ("brussels", "bruxelles", "brussel", ".be/", ".be", "eu.", "europa.eu")

STOPWORDS = {
    "the", "of", "and", "for", "de", "des", "du", "la", "le", "les", "een",
    "international", "european", "belgium", "belgian", "brussels", "eu",
    "group", "office", "association", "federation", "institute", "centre",
    "center", "network", "council", "committee", "organisation", "organization",
}


def tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def domain_of(url: str) -> str:
    """Bare hostname, no scheme, no www."""
    m = re.match(r"https?://([^/]+)", url.lower())
    return re.sub(r"^www\.", "", m.group(1)) if m else ""


def score_candidate(cand: dict, org: dict) -> tuple[int, list[str]]:
    """Score a search result as the org's careers page. Returns (score, reasons)."""
    low = cand["url"].lower()
    score, why = 0, []

    if any(a in low for a in AGGREGATORS):
        return -100, ["aggregator/social, not the org's own page"]

    domain = domain_of(low)
    path_part = low.split(domain, 1)[-1] if domain else low
    old = str(org.get("existing_url") or "").lower()
    old_domain = domain_of(old)

    # 1. Path shape
    for pat, pts in PATH_HINTS:
        if re.search(pat, path_part):
            score += pts
            why.append(f"careers-shaped path (+{pts})")
            break

    # An archive of closed/expired vacancies is a careers-shaped page that
    # will never contain an applyable job.
    if re.search(r"/(closed|expired|archive[sd]?|past|previous)\b", path_part):
        score -= 6
        why.append("archive of closed vacancies (-6)")

    # 2. ATS platform is a strong positive
    on_ats = any(h in low for h in ATS_HOSTS)
    if on_ats:
        score += 6
        why.append("hosted on a known ATS (+6)")

    # 3. Does this domain belong to this org at all?
    org_toks = tokens(org["organisation"])
    dom_flat = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
    name_match = bool(org_toks and any(t in dom_flat for t in org_toks))
    # Check the acronym of each name form: the bare name's initials, and the
    # initials of any parenthetical expansion.
    acro_match = False
    for variant in name_variants(org["organisation"]):
        acro = "".join(w[0] for w in variant.split() if w[:1].isalpha()).lower()
        if len(acro) >= 3 and acro == dom_flat:
            acro_match = True
            break
    domain_known = bool(old_domain) and (
        old_domain == domain
        or old_domain.split(".")[-2:] == domain.split(".")[-2:]
    )

    if name_match or acro_match:
        score += 4
        why.append("domain matches org name (+4)")
    if domain_known:
        # The sheet's existing links are unreliable on the *path* (the /jobs/
        # vs /vacancies/ problem this pipeline exists to fix) but the *domain*
        # was usually right, and it disambiguates orgs whose names collide
        # across countries ("FPS Foreign Affairs" vs the UK FCO).
        pts = 5 if old_domain == domain else 3
        score += pts
        why.append(f"matches the sheet's known domain (+{pts})")
    if not (name_match or acro_match or domain_known or on_ats):
        # An unrelated domain with a careers-shaped path is the classic false
        # positive: a real jobs page belonging to somebody else entirely.
        score -= 6
        why.append("domain unrelated to this org (-6)")

    # 4. Geography. A foreign-office careers page is a real page for the wrong
    # city, and scores identically on every other signal - so penalise it hard
    # enough to lose to the org's main site.
    if any(f in domain or f in path_part[:40] for f in FOREIGN_HINTS):
        # ...unless the org is genuinely based there (e.g. a LatAm mission).
        org_base = str(org.get("base") or "").lower()
        if not any(f in org_base for f in FOREIGN_HINTS):
            score -= 8
            why.append("looks like a non-Brussels office (-8)")
    if any(b in low for b in BRUSSELS_HINTS):
        score += 2
        why.append("Brussels/EU domain signal (+2)")

    # 5. Search-result title/snippet language
    blob = (cand.get("title", "") + " " + cand.get("snippet", "")).lower()
    if any(k in blob for k in ("job", "vacanc", "career", "emploi", "recruit")):
        score += 2
        why.append("search snippet mentions jobs (+2)")

    # 6. Rank position (top results are better)
    rank_bonus = max(0, 3 - cand.get("rank", 0))
    if rank_bonus:
        score += rank_bonus
        why.append(f"search rank #{cand.get('rank', 0) + 1} (+{rank_bonus})")

    return score, why


def verify_page(url: str) -> tuple[int, list[str], str]:
    """Fetch the page and score the evidence actually on it."""
    r = fetch(url)
    if not r["ok"]:
        return -50, [f"fetch failed (HTTP {r['status']})"], ""

    soup = BeautifulSoup(r["text"], "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True).lower()

    score, why = 0, []
    hits = [h for h in BODY_HINTS if h in text]
    if hits:
        pts = min(6, len(hits) * 2)
        score += pts
        why.append(f"page text has {len(hits)} job signal(s) (+{pts})")

    title = (soup.title.get_text(strip=True) if soup.title else "").lower()
    if any(k in title for k in ("job", "vacanc", "career", "emploi", "work with us",
                                "vacature", "empleo", "recruit")):
        score += 4
        why.append("page title says careers (+4)")

    # A careers page that says it has nothing right now is still the right page.
    if any(p in text for p in ("no current vacanc", "no open position",
                               "no vacancies at this time", "pas d'offre")):
        score += 2
        why.append("explicitly lists zero openings — still the right page (+2)")

    return score, why, r["url"]


def clean_name(name: str) -> str:
    """Strip parenthetical asides that derail a search query."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def name_variants(name: str) -> list[str]:
    """Search-worthy forms of an org name, best first.

    Sheet names mix an acronym with an expansion and sometimes a parent body --
    "DGD (Belgian Development Cooperation, FPS Foreign Affairs)". Searching the
    bare acronym is too thin to find the right site, and searching the whole
    string is too specific to match anything, so try both plus the expansion.
    """
    out = [clean_name(name)]
    m = re.search(r"\(([^)]*)\)", name)
    if m:
        # The expansion, minus any trailing parent-body clause.
        expansion = m.group(1).split(",")[0].strip()
        if len(expansion) > 4:
            out.append(expansion)
            # Acronym + expansion together disambiguates best of all.
            out.append(f"{clean_name(name)} {expansion}")
    # Drop an "X / Y" bilingual pair down to its first half.
    if " / " in out[0]:
        out.append(out[0].split(" / ")[0].strip())
    seen: set[str] = set()
    return [v for v in out if v and not (v in seen or seen.add(v))]


def discover_one(org: dict) -> dict:
    name = org["organisation"]
    short = clean_name(name)

    # Several query shapes. One query per org is a single point of failure: the
    # generic one can surface an overseas office while never showing the
    # Brussels HQ, so the second anchors on the city explicitly.
    variants = name_variants(name)
    queries = [
        f"{short} Brussels jobs vacancies careers",
        f"{short} careers page Brussels Belgium",
    ]
    # A compound name ("DGD (Belgian Development Cooperation, ...)") searches
    # badly in either direction; the expansion often finds what the acronym
    # can't.
    for v in variants[1:]:
        queries.append(f"{v} Brussels jobs vacancies careers")
    # If the sheet already knows the org's domain, ask the engine directly for
    # careers pages on that domain. This rescues orgs whose name is ambiguous
    # enough that a plain name search never surfaces the right site at all.
    old = str(org.get("existing_url") or "")
    if "//" in old:
        old_domain = re.sub(r"^www\.", "", old.lower().split("/")[2])
        if old_domain:
            queries.insert(0, f"site:{old_domain} jobs OR vacancies OR careers")

    pooled: dict[str, dict] = {}
    for q in queries:
        for i, cand in enumerate(search(q, count=5)[:3]):  # top 3 per query
            url = cand["url"]
            if url in pooled:
                pooled[url]["rank"] = min(pooled[url]["rank"], i)
            else:
                cand["rank"] = i
                pooled[url] = cand
        # Stop once we have a decent pool, but never before the plain-name
        # query has run -- a site: query alone can return one weak hit.
        if len(pooled) >= 4 and not q.startswith("site:"):
            break

    scored = []
    for cand in pooled.values():
        s1, why1 = score_candidate(cand, org)
        if s1 <= -100:
            continue
        s2, why2, final_url = verify_page(cand["url"])
        scored.append(
            {
                "url": final_url or cand["url"],
                "title": cand.get("title", ""),
                "score": s1 + s2,
                "reasons": why1 + why2,
                "engine": cand.get("engine", ""),
            }
        )

    scored.sort(key=lambda c: -c["score"])
    best = scored[0] if scored else None

    # Threshold: below this we don't trust it enough to call it found.
    THRESHOLD = 10
    if best and best["score"] >= THRESHOLD:
        confidence = "high" if best["score"] >= 18 else "medium"
        chosen, method = best["url"], "search+verify"
    else:
        confidence, chosen, method = "none", None, "search+verify"

    return {
        "id": org["id"],
        "organisation": name,
        "category": org["category"],
        "priority": org["priority"],
        "old_url": org["existing_url"],
        "careers_url": chosen,
        "confidence": confidence,
        "score": best["score"] if best else 0,
        "reasons": best["reasons"] if best else ["no viable candidate"],
        "candidates": scored,
        "search_url": "https://www.google.com/search?q="
        + urllib.parse.quote_plus(queries[0]),
        "method": method,
    }


def main() -> None:
    orgs = json.loads(ORGS_JSON.read_text())
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        orgs = orgs[:limit]

    # Resume: an overnight DDG sweep runs for hours and may be interrupted or
    # banned partway. Keep whatever already resolved and only redo the rest.
    done: dict = {}
    if DISCOVERED_JSON.exists():
        try:
            for r in json.loads(DISCOVERED_JSON.read_text()):
                # Retry misses on a later run; keep the hits.
                if r.get("confidence") != "none":
                    done[str(r["id"])] = r
        except json.JSONDecodeError:
            pass

    todo = [o for o in orgs if str(o["id"]) not in done]
    print(f"Discovering careers pages: {len(todo)} to do, "
          f"{len(done)} already resolved\n")

    out = list(done.values())
    # Workers help when Brave is answering (the page fetches dominate) and are
    # harmless when it isn't: the DDG fallback serialises itself on its own
    # lock regardless.
    workers = 8 if BRAVE_API_KEY else 1
    done_n = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(discover_one, o): o for o in todo}
        for fut in as_completed(futures):
            org = futures[fut]
            done_n += 1
            try:
                res = fut.result()
            except Exception as e:  # never lose the whole run to one bad page
                print(f"  ! {org['organisation'][:40]}: {type(e).__name__}: {e}")
                continue
            out.append(res)
            mark = {"high": "OK  ", "medium": "MED ", "none": "MISS"}[res["confidence"]]
            changed = "" if res["careers_url"] == res["old_url"] else "  [CHANGED]"
            print(f"{done_n:>3}/{len(todo)} {mark} {res['score']:>3}  "
                  f"{res['organisation'][:38]:<38} "
                  f"{str(res['careers_url'])[:52]}{changed}", flush=True)
            # Save as we go so an interrupted run never costs more than the
            # requests still in flight.
            DISCOVERED_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    tally: dict = {}
    for r in out:
        tally[r["confidence"]] = tally.get(r["confidence"], 0) + 1
    print(f"\n{'='*70}\n  " + "  ".join(f"{k}: {v}" for k, v in sorted(tally.items())))
    print(f"  Written: {DISCOVERED_JSON}")


if __name__ == "__main__":
    main()
