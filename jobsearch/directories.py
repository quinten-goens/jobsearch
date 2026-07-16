"""Harvest organisation names from umbrella-body member directories.

NGOs and civil-society groups are an unbounded set with no authoritative list,
so hand-curating them would be the same guesswork this pipeline exists to
replace. What *does* exist is a handful of federations that publish their
membership -- CNCD-11.11.11 and ngo-federatie between them cover most of
Belgium's accredited development NGOs, and the Brussels social-sector umbrellas
cover the grassroots tier.

We take names and homepages from those directories and let `discover.py` find
each one's careers page, exactly as it does for the sheet's organisations.
"""
import json
import re
import urllib.parse
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .config import DATA
from .http import fetch

DIRECTORY_JSON = DATA / "directory_orgs.json"

# Hosts that appear in every directory and are never a member organisation.
SKIP_HOSTS = (
    "facebook.", "twitter.", "x.com", "instagram.", "linkedin.", "youtube.",
    "flickr.", "vimeo.", "tiktok.", "whatsapp.", "google.", "gstatic.",
    "wikipedia.", "paypal.", "mailchimp", "wordpress.org", "creativecommons",
    "adobe.com", "apple.com", "microsoft.", "cloudflare", "jquery", "bit.ly",
    "issuu.com", "soundcloud.", "spotify.", "eventbrite.", "doodle.",
    "mastodon", "bsky.app", "threads.net", "telegram.",
    # Cookie/consent vendors, webmail and other site plumbing that appears in
    # footers and reads as an outbound link.
    "cookiedatabase.org", "cookiebot", "onetrust", "outlook.", "office.com",
    "gmail.", "hotmail.", "yahoo.", "sharepoint.", "teams.microsoft",
    "addtoany", "sharethis", "gravatar", "w3.org", "schema.org", "goo.gl",
    "maps.app", "openstreetmap", "recaptcha", "polyfill", "unpkg", "cdn.",
)

# A link's text is sometimes a whole sentence of body copy rather than a name.
MAX_NAME = 70


@dataclass
class Directory:
    key: str
    name: str
    url: str
    category: str
    org_type: str
    note: str
    render: bool = False
    # Some directories give each member its own page (/onze-leden/<slug>/)
    # rather than linking out directly. Where they do, the slug is the org.
    member_path: str | None = None


DIRECTORIES = [
    Directory(
        "cncd", "CNCD-11.11.11 member organisations",
        "https://cncd.be/-organisations-membres-du-cncd-11-11-11-",
        "Development & humanitarian", "NGO (Belgian, FR)",
        "Francophone Belgian development NGO umbrella; ~80 member organisations.",
    ),
    Directory(
        "ngofed", "ngo-federatie member organisations",
        "https://ngo-federatie.be/onze-leden/",
        "Development & humanitarian", "NGO (Belgian, NL)",
        "Flemish development NGO federation.",
        member_path="/onze-leden/",
    ),
    Directory(
        "acodev", "ACODEV member organisations",
        "https://www.acodev.be/ong/membres.html",
        "Development & humanitarian", "NGO (Belgian, FR)",
        "Francophone development NGO federation.",
    ),
    Directory(
        "cbcs", "CBCS - Brussels social sector",
        "https://www.cbcs.be/",
        "Civil society & grassroots", "NGO (Brussels, FR)",
        "Conseil bruxellois de coordination sociopolitique; Brussels social sector.",
        render=True,
    ),
    Directory(
        "bruxeo", "BRUXEO - Brussels non-profit confederation",
        "https://www.bruxeo.be/",
        "Civil society & grassroots", "Non-profit federation",
        "Confederation of Brussels non-profit employers.", render=True,
    ),
]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _is_member_link(href: str, base_host: str) -> bool:
    if not href.startswith("http"):
        return False
    host = urllib.parse.urlparse(href).netloc.lower()
    if not host or base_host in host:
        return False
    # Malformed markup can yield a "host" full of HTML; a real one is just
    # letters, digits, dots and hyphens.
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host):
        return False
    return not any(s in host for s in SKIP_HOSTS)


# Link text that is chrome rather than an organisation name.
JUNK_NAME = re.compile(
    r"^(en savoir plus|lire (la suite|plus)|cliquez|plus d[’']info|voir plus|"
    r"read more|meer info|lees meer|learn more|click here|site web|website)",
    re.I,
)


def _tidy_name(name: str, host: str) -> str:
    """Directories often use the URL as the link text; make that readable."""
    name = _clean(name)
    # Logo alt text: "Le logo de LHAC" / "Logo of Oxfam" -> the org itself.
    m = re.match(r"^(?:le\s+)?logo\s+(?:de\s+la\s+|de\s+|d[’']|of\s+|van\s+)?(.+)$",
                 name, re.I)
    if m:
        name = _clean(m.group(1))
    if JUNK_NAME.match(name):
        name = ""
    if not name or re.match(r"^https?://", name) or \
            name.lower().lstrip("w.").startswith(host[:8]):
        stem = host.split(".")[0]
        return stem.replace("-", " ").replace("_", " ").title()
    if len(name) > MAX_NAME:
        # Body copy, not a name: keep the leading clause if there is one,
        # otherwise fall back to the domain.
        head = re.split(r"\s+(?:is|est|was|-|–|,)\s+", name, maxsplit=1)[0]
        name = head if 3 < len(head) <= MAX_NAME else host.split(".")[0].title()
    return name


def _harvest_member_pages(d: Directory, soup: BeautifulSoup) -> list[dict]:
    """Directories that give each member its own page: the slug is the org."""
    out: dict[str, dict] = {}
    base = f"{urllib.parse.urlparse(d.url).scheme}://{urllib.parse.urlparse(d.url).netloc}"
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(base, a["href"])
        path = urllib.parse.urlparse(href).path
        if not path.startswith(d.member_path):
            continue
        slug = path[len(d.member_path):].strip("/")
        if not slug or "/" in slug:
            continue
        name = _clean(a.get_text(" ")) or slug.replace("-", " ").title()
        out[slug] = {
            "organisation": name,
            "homepage": href,          # the federation's page for this member
            "category": d.category,
            "type": d.org_type,
            "base": "Belgium",
            "source_directory": d.name,
        }
    return list(out.values())


def harvest(d: Directory) -> list[dict]:
    """Names + homepages of the organisations a directory page links out to."""
    if d.render:
        from .render import render

        r = render(d.url)
    else:
        r = fetch(d.url)
    if not r["ok"] or not r["text"]:
        print(f"  ! {d.key}: HTTP {r['status']}")
        return []

    soup = BeautifulSoup(r["text"], "lxml")
    if d.member_path:
        return _harvest_member_pages(d, soup)

    base_host = urllib.parse.urlparse(d.url).netloc.lower().replace("www.", "")

    found: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _is_member_link(href, base_host):
            continue
        host = urllib.parse.urlparse(href).netloc.lower().replace("www.", "")
        name = _clean(a.get_text(" "))
        # Link text is often a logo alt or empty; fall back to the domain.
        if not name or len(name) < 3:
            img = a.find("img")
            name = _clean(img.get("alt")) if img and img.get("alt") else ""
        name = _tidy_name(name, host)
        if not name or len(name) < 3:
            name = host.split(".")[0].replace("-", " ").title()
        # Keep the richest name we've seen for a given host.
        prev = found.get(host)
        if prev and len(prev["organisation"]) >= len(name):
            continue
        found[host] = {
            "organisation": name,
            "homepage": f"https://{host}",
            "category": d.category,
            "type": d.org_type,
            "base": "Belgium",
            "source_directory": d.name,
        }
    return list(found.values())


def main() -> None:
    all_orgs: dict[str, dict] = {}
    for d in DIRECTORIES:
        orgs = harvest(d)
        print(f"  {d.key:<8} {len(orgs):>4} organisations   ({d.name[:44]})")
        for o in orgs:
            all_orgs.setdefault(urllib.parse.urlparse(o["homepage"]).netloc, o)

    out = list(all_orgs.values())
    DIRECTORY_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n  {len(out)} unique organisations -> {DIRECTORY_JSON}")

    try:
        from .render import close_browser

        close_browser()
    except Exception:
        pass


if __name__ == "__main__":
    main()
