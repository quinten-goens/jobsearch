"""Ingest organisations from the EU Transparency Register.

The Register lists ~17,500 entities that engage with EU policymaking -- a
goldmine of off-board employers: NGOs, trade associations, think tanks, unions,
most with their own careers page and few of which ever post on the saturated
boards. Crucially each record carries a webSiteURL, so we skip Brave discovery
and go straight to finding the careers page on the known domain.

    python -m jobsearch.register --download   # refresh the 108MB XML
    python -m jobsearch.register --limit 100  # parse a filtered slice

Filtered to Belgium-based orgs in the categories that fit Sarah's profile
(policy/IR): NGOs, associations, unions, think tanks, public/mixed bodies --
not companies, law firms or lone consultancies.
"""
import json
import sys

import requests
from lxml import etree

from .config import DATA, HEADERS

REGISTER_XML = DATA / "transparency_register.xml"
REGISTER_JSON = DATA / "register_orgs.json"
EXPORT_URL = "https://transparency-register.europa.eu/odplastorganisationxml_en"

# Categories worth keeping for a policy/IR profile. Register spellings vary
# ("Companies groups" vs "Companies & groups"), so match loosely.
KEEP_CATEGORIES = (
    "non-governmental", "platforms and net", "trade and business",
    "trade unions", "professional associations", "think tanks",
    "research institutions", "public or mixed", "academic institutions",
    "associations and networks of public",
)
# The map to our own sector names.
SECTOR_MAP = [
    ("non-governmental", "NGO & civil society"),
    ("platforms and net", "NGO & civil society"),
    ("trade and business", "Trade association & federation"),
    ("trade unions", "Trade union & employer body"),
    ("professional associations", "Trade union & employer body"),
    ("think tanks", "Think tank"),
    ("research institutions", "Think tank"),
    ("academic", "University & research"),
    ("public or mixed", "Belgian public sector"),
    ("public authorities", "Belgian public sector"),
]


def _localname(el) -> str:
    return etree.QName(el).localname


def _first(el, tag: str) -> str:
    for e in el.iter():
        if _localname(e) == tag and (e.text or "").strip():
            return e.text.strip()
    return ""


def _sector_for(category: str) -> str:
    low = category.lower()
    for key, sector in SECTOR_MAP:
        if key in low:
            return sector
    return "NGO & civil society"


def download() -> None:
    print("Downloading the Transparency Register (~108MB)…", flush=True)
    with requests.get(EXPORT_URL, headers=HEADERS, timeout=300, stream=True) as r:
        r.raise_for_status()
        with open(REGISTER_XML, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print(f"  saved -> {REGISTER_XML}")


def _is_larger(el) -> bool:
    """Does this org actually employ people / engage seriously with the EU?

    Small associations (< 1 FTE, no EP badge) rarely have a careers page, which
    is why the unfiltered hit rate is poor. Keep orgs with at least one
    full-time-equivalent staff member OR a European Parliament access badge.
    """
    try:
        if float(_first(el, "membersFTE") or 0) >= 1:
            return True
    except ValueError:
        pass
    try:
        if int(_first(el, "EPAccreditedNumber") or 0) > 0:
            return True
    except ValueError:
        pass
    return False


def parse(country: str = "BELGIUM", limit: int = 0,
          larger_only: bool = True) -> list[dict]:
    """Filtered slice of the Register as catalogue-shaped records."""
    if not REGISTER_XML.exists():
        raise FileNotFoundError(
            f"{REGISTER_XML} missing — run: python -m jobsearch.register --download")

    out = []
    ctx = etree.iterparse(str(REGISTER_XML), events=("end",),
                          recover=True, huge_tree=True)
    for _, el in ctx:
        if _localname(el) != "interestRepresentative":
            continue
        cat = _first(el, "registrationCategory")
        ctry = _first(el, "country")
        if country and ctry != country:
            el.clear()
            continue
        if not any(k in cat.lower() for k in KEEP_CATEGORIES):
            el.clear()
            continue
        if larger_only and not _is_larger(el):
            el.clear()
            continue

        name = _first(el, "originalName")
        acronym = _first(el, "acronym")
        website = _first(el, "webSiteURL")
        city = _first(el, "city")
        display = f"{name} ({acronym})" if acronym and acronym.lower() not in name.lower() else name
        try:
            size = round(float(_first(el, "membersFTE") or 0))
        except ValueError:
            size = None
        out.append({
            "organisation": display,
            "sector": _sector_for(cat),
            "category": cat,
            "type": cat,
            "base": city.title() if city else "Belgium",
            "homepage": website,
            "size": size or None,
            "description": (_first(el, "goals") or "")[:400],
            "sources": ["EU Transparency Register"],
            "register_id": _first(el, "identificationCode"),
        })
        el.clear()
        if limit and len(out) >= limit:
            break
    return out


def main() -> None:
    if "--download" in sys.argv:
        download()
        if len(sys.argv) == 2:
            return
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    orgs = parse(limit=limit)
    REGISTER_JSON.write_text(json.dumps(orgs, indent=2, ensure_ascii=False))
    from collections import Counter

    print(f"{len(orgs)} Belgium-based, relevant-category orgs -> {REGISTER_JSON}")
    print("with a website given:",
          sum(1 for o in orgs if o["homepage"]), f"/ {len(orgs)}")
    for k, v in Counter(o["sector"] for o in orgs).most_common():
        print(f"  {v:>4}  {k}")


if __name__ == "__main__":
    main()
