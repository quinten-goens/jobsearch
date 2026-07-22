"""Detect whether a careers page has live openings — HTML only, no browser.

The strategic point (Sarah's insight): job boards are saturated, so the real
edge is an org with a vacancy on *its own* page that few people see. This
module answers, cheaply and at scale, "does this page have openings right now?"

It never renders JavaScript. Instead it reads three things from the raw HTML:
  1. explicit "no vacancies" copy (multilingual) -> NONE
  2. embedded job data in <script> JSON blobs / ATS payloads -> HAS + titles
  3. repeated job-posting link/heading patterns -> HAS + titles

Anything it genuinely can't read stays UNKNOWN — an honest "look yourself"
flag, not a failure. Every signal is multilingual (EN/FR/NL/DE/ES/IT), because
the catalogue is full of European institutions and foreign missions.
"""
import json
import re

from bs4 import BeautifulSoup

from .http import fetch

# Result states.
HAS = "has_openings"
NONE = "no_openings"
UNKNOWN = "unknown"

# "There is nothing open right now", across the languages the catalogue needs.
# A page saying this is the RIGHT page -- just empty today -- so it's a NONE,
# not a miss.
EMPTY_STATE = re.compile(
    r"no (current |open )?(vacanc|job|position|opening)\w*"
    r"|no vacancies (at this time|currently|right now|available)"
    r"|there are (currently )?no (open|current)?\s?(vacanc|position|job|opening)"
    r"|not? (open )?(positions?|vacanc\w*) (available|at the moment|currently)"
    # French
    r"|pas d[’']offre|aucune offre|aucun poste|pas de poste (vacant|à pourvoir)"
    r"|aucune (offre|vacance)|pas de recrutement"
    # Dutch
    r"|geen (vacature|openstaande)|momenteel geen vacature"
    r"|er zijn (momenteel |op dit moment )?geen vacature"
    # German
    r"|keine (offene[n]? )?(stelle|stellenangebote|vakanz)"
    r"|derzeit keine|zurzeit keine|aktuell keine (stelle|offene)"
    # Spanish
    r"|no hay (vacantes|ofertas|puestos)|sin (vacantes|ofertas)"
    r"|no existen (vacantes|ofertas)"
    # Italian
    r"|nessuna posizione|non ci sono posizioni|nessuna offerta"
    # generic reassurance copy
    r"|check back (later|soon|regularly)|please check back",
    re.I,
)

# Words that appear in an actual job-posting title, across languages. Used to
# tell a job link/heading from site chrome.
TITLE_WORDS = (
    # EN
    "officer", "adviser", "advisor", "manager", "coordinator", "assistant",
    "director", "analyst", "consultant", "specialist", "intern", "internship",
    "trainee", "traineeship", "researcher", "fellow", "associate", "head of",
    "policy", "programme", "program", "project", "communications", "advocacy",
    "campaign", "legal", "officer", "expert", "engineer", "editor", "lead",
    "administrator", "secretary", "representative", "liaison", "counsel",
    # FR
    "chargé", "charge de", "responsable", "conseiller", "adjoint", "attaché",
    "assistant", "stagiaire", "directeur", "coordinateur", "gestionnaire",
    # NL
    "medewerker", "adviseur", "beleids", "coördinator", "hoofd", "stagiair",
    "verantwoordelijke", "deskundige",
    # DE
    "referent", "referentin", "mitarbeiter", "leiter", "leiterin", "berater",
    "sachbearbeiter", "praktikant", "wissenschaftliche", "koordinator",
    # ES
    "responsable", "técnico", "tecnico", "coordinador", "analista", "asesor",
    "especialista", "gestor", "director", "prácticas", "practicas", "becario",
    # IT
    "responsabile", "coordinatore", "assistente", "consulente", "stagista",
    "specialista", "addetto",
)

# Link paths / classes that hint at an individual posting.
JOB_PATH = re.compile(
    r"/(job|jobs|vacanc|vacature|career|carriere|offre|emploi|stelle|"
    r"stellenangebot|position|opening|opportunit|stage|praktik|empleo|oferta|"
    r"lavora|posizione|traineeship|internship|recruit)[a-z-]*/", re.I)

NOISE = (
    "cookie", "privacy", "newsletter", "read more", "learn more", "view all",
    "see all", "all jobs", "back to", "apply now", "share", "subscribe",
    "en savoir plus", "lire la suite", "meer info", "mehr erfahren",
    "internal login", "log in", "login", "sign in", "my account", "register",
    "create an account",
)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _looks_like_title(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 5 or len(t) > 140:
        return False
    if re.search(r"\(\s*\d+\s*\)\s*$", t):  # "Internships (12)" is a facet
        return False
    if any(n in t for n in NOISE):
        return False
    return any(w in t for w in TITLE_WORDS)


def _titles_from_json(html: str) -> list[str]:
    """Postings embedded in <script> JSON — only from genuine JobPosting
    objects, to avoid scooping up page metadata."""
    titles: list[str] = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S | re.I):
        blob = m.group(1)
        # Only trust JSON-LD JobPosting -- a schema.org object that explicitly
        # says "this is a job". A bare "title" key is usually the page title,
        # which is why Protection International's empty page looked full.
        if '"@type"' in blob and "JobPosting" in blob:
            try:
                data = json.loads(blob.strip())
            except (json.JSONDecodeError, ValueError):
                # Malformed or multiple blocks: fall back to a scoped regex that
                # only reads titles sitting next to a JobPosting type.
                for chunk in re.split(r'"@type"\s*:\s*"JobPosting"', blob)[1:]:
                    mt = re.search(r'"title"\s*:\s*"([^"]{5,120})"', chunk[:400])
                    if mt:
                        titles.append(mt.group(1))
                continue
            for item in _walk_jobpostings(data):
                t = item.get("title") or item.get("name")
                if t:
                    titles.append(t)
    seen, out = set(), []
    for t in titles:
        t = _clean(t)
        # Reject URL-encoded strings and obvious chrome.
        if "%20" in t or "%2" in t:
            continue
        if t and t.lower() not in seen and 5 <= len(t) <= 140:
            seen.add(t.lower())
            out.append(t)
    return out


def _walk_jobpostings(data) -> list[dict]:
    """Every JobPosting object in a JSON-LD structure (@graph, lists, nesting)."""
    found = []
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("@type") == "JobPosting":
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _titles_from_links(soup: BeautifulSoup) -> list[str]:
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        text = _clean(a.get_text(" "))
        if not _looks_like_title(text):
            continue
        href = a["href"]
        # A job-shaped URL strengthens it, but a strong title stands alone.
        if JOB_PATH.search(href) or any(
            w in text.lower() for w in ("officer", "adviser", "manager",
                                        "coordinator", "director", "referent",
                                        "chargé", "responsable", "intern")):
            if text.lower() not in seen:
                seen.add(text.lower())
                out.append(text)
    return out


def detect(url: str) -> dict:
    """Return {state, count, titles, note}. Never raises."""
    if not url:
        return {"state": UNKNOWN, "count": 0, "titles": [], "note": "no url"}
    r = fetch(url)
    if not r["ok"]:
        # Blocked (403/429) or gone -- can't read it, so unknown.
        return {"state": UNKNOWN, "count": 0, "titles": [],
                "note": f"couldn't read page (HTTP {r['status']})"}

    html = r["text"]
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.get_text(" ", strip=True)

    # 1. Titles from embedded JSON (recovers many JS sites without a browser).
    titles = _titles_from_json(html)
    # 2. Titles from links, if JSON gave nothing.
    if not titles:
        titles = _titles_from_links(soup)

    if titles:
        return {"state": HAS, "count": len(titles), "titles": titles[:25],
                "note": ""}

    # 3. No titles found. Does the page SAY it's empty?
    if EMPTY_STATE.search(body):
        return {"state": NONE, "count": 0, "titles": [],
                "note": "page says no openings right now"}

    # 4. Couldn't find openings and no "we're empty" note: genuinely unclear
    #    (often JS-rendered with no readable payload).
    return {"state": UNKNOWN, "count": 0, "titles": [],
            "note": "couldn't tell from the page — worth a manual look"}


if __name__ == "__main__":
    import sys
    for u in sys.argv[1:]:
        d = detect(u)
        print(f"{d['state']:<12} ({d['count']:>2})  {u}")
        for t in d["titles"][:5]:
            print(f"      - {t}")
        if d["note"]:
            print(f"      … {d['note']}")
