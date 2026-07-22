"""Build the unified organisation catalogue.

    python -m jobsearch.catalogue

Merges three sources into one documented record per organisation:

  1. the sheet          -- 282 hand-picked targets, with Sarah's own rationale
  2. the registry       -- complete regional lists (19 communes, universities)
  3. the directories    -- NGO federation memberships

The sheet is the richest but least complete; the registry is complete but only
covers bounded sectors; the directories are broad but thin. Merging on a
normalised name keeps the sheet's rationale wherever it exists and fills the
gaps around it.
"""
import json
import re
import unicodedata

from .config import DATA, ORGS_JSON
from .directories import DIRECTORY_JSON
from .registry import (
    BELGIAN_COLLEGES,
    BELGIAN_HOSPITALS,
    BELGIAN_PUBLIC_BODIES,
    BELGIAN_UNIVERSITIES,
    BRUSSELS_COMMUNES,
    BRUSSELS_PERIPHERY,
    CULTURAL_INSTITUTES,
    EUROPEAN_INSTITUTIONS,
    INTERNATIONAL_REMOTE,
    LATAM_INSTITUTIONS,
    POLITICAL_FOUNDATIONS,
    TRADE_ASSOCIATIONS,
    TRADE_UNIONS,
)

CATALOGUE_JSON = DATA / "catalogue.json"

# Sector is the top-level facet in the UI: it answers "what kind of place is
# this?", which is the question the sheet's 15 overlapping categories didn't.
SECTOR_RULES = [
    # Order matters: these run before the generic "federation"/"foundation"
    # keywords below, which would otherwise swallow them into NGO/think tank.
    ("European & intl institution", ("intergovernmental organisation",)),
    # Before the generic keywords: "agency" otherwise pulls Frontex into
    # consultancies, and "institute"/"foundation" pull agencies into think tanks.
    ("EU institution", ("eu body / agency",)),
    ("Trade association & federation", ("trade association", "federation (",)),
    ("Political foundation", ("political foundation",)),
    ("Trade union & employer body", ("trade union", "employer federation")),
    ("Latin America institution", ("latin america body",)),
    ("Cultural institute", ("cultural institute",)),
    ("Hospital & healthcare", ("hospital", "hôpital", "hopital", "ziekenhuis",
                               "clinique", "cliniques", "chu ", "uz ", "huderf",
                               "bordet", "sciensano", "iriscare")),
    ("Commune / local government", ("commune", "gemeente", "stad brussel", "ville de")),
    ("University & research", ("universit", "hogeschool", "haute école", "college",
                               "school of arts", "academy", "institute of tropical")),
    ("EU institution", ("european commission", "european parliament", "council of the",
                        "eeas", "epso", "dg ", "eu delegation", "european external")),
    ("International organisation", ("united nations", "unhcr", "unicef", "iom ", "nato",
                                    "oecd", "world bank", "unesco", "who ", "ilo ")),
    ("Think tank", ("think tank", "institute", "foundation", "stiftung", "bruegel",
                    "ceps", "egmont")),
    ("NGO & civil society", ("ngo", "asbl", "vzw", "association", "federation",
                             "network", "platform", "collectif")),
    ("Consultancy & public affairs", ("consult", "public affairs", "communication",
                                      "agency", "partners")),
    ("Diplomatic mission", ("embassy", "mission of", "mission to the eu",
                            "permanent representation", "consulate", "diplomatic")),
]


def norm(name: str) -> str:
    """Normalised key for merging the same org across sources."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"\s*\([^)]*\)", " ", s.lower())
    s = re.sub(r"\b(asbl|vzw|npo|ngo|the|of|and|de|het|la|le|les)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# Every sheet category maps to exactly one sector. Without this, unmatched rows
# fall through to their raw category and the facet grows near-duplicate buckets
# ("International org" beside "International organisation").
CATEGORY_TO_SECTOR = {
    "EU institutions": "EU institution",
    "International org": "International organisation",
    "Belgian public": "Belgian public sector",
    "Universities & research": "University & research",
    "Think tanks": "Think tank",
    "Comms contractors": "Consultancy & public affairs",
    "Corporate & training": "Corporate",
    "Media": "Media",
    "Human rights & gender": "NGO & civil society",
    "Development & humanitarian": "NGO & civil society",
    "Migration & asylum": "NGO & civil society",
    "Peace & security": "NGO & civil society",
    "Health": "NGO & civil society",
    # Latin America is a *theme*, not a sector -- these rows are mostly
    # diplomatic missions and NGOs. It's carried as the latam_relevant flag
    # instead, which is what Sarah actually filters on.
    "Latin America": "Diplomatic mission",
    "Research & evaluation": "Consultancy & public affairs",
}

# Themes cut across sectors and matter specifically to Sarah: her Spanish makes
# the Latin America files a deliberate target, and the PhD is an anthropology
# one.
LATAM_HINTS = (
    "latin america", "latam", "mercosur", "eu-lac", "celac", "mexico", "brazil",
    "argentina", "chile", "colombia", "peru", "bolivia", "ecuador", "uruguay",
    "paraguay", "venezuela", "guatemala", "honduras", "nicaragua", "cuba",
    "el salvador", "costa rica", "panama", "dominican", "haiti", "spanish",
    "hispan", "iberoameric", "oei", "amerique latine", "america latina",
)


def classify(org: dict) -> str:
    blob = f"{org.get('organisation','')} {org.get('type','')} {org.get('category','')}".lower()
    for sector, keys in SECTOR_RULES:
        if any(k in blob for k in keys):
            return sector
    return CATEGORY_TO_SECTOR.get(org.get("category") or "", "Other")


def _record(**kw) -> dict:
    """Every catalogue row has the same shape, so the UI can rely on it."""
    base = {
        "organisation": "", "sector": "", "category": "", "type": "",
        "base": "", "languages": "", "size": None, "description": "",
        "why_fits": "", "target_roles": "", "priority": None,
        "eu_nationality": "", "homepage": "", "careers_url": "",
        "careers_confidence": "", "last_updated": "", "last_updated_source": "",
        "last_updated_trust": "", "sources": [], "phd_relevant": False,
        "latam_relevant": False, "remote_friendly": False,
        "careers_score": 0, "careers_reasons": [],
    }
    base.update(kw)
    return base


def tag_themes(rec: dict) -> dict:
    blob = " ".join(str(rec.get(f) or "") for f in
                    ("organisation", "category", "type", "description",
                     "why_fits", "languages", "base")).lower()
    if any(h in blob for h in LATAM_HINTS):
        rec["latam_relevant"] = True
    if not rec["phd_relevant"] and rec["sector"] == "University & research":
        rec["phd_relevant"] = any(
            k in blob for k in ("anthropolog", "phd", "doctoral", "research")
        )
    return rec


def from_sheet() -> list[dict]:
    orgs = json.loads(ORGS_JSON.read_text())
    out = []
    for o in orgs:
        rec = _record(
            organisation=o["organisation"],
            category=o.get("category") or "",
            type=o.get("type") or "",
            base=o.get("base") or "",
            languages=o.get("language_edge") or "",
            description=o.get("why_fits") or "",
            why_fits=o.get("why_fits") or "",
            target_roles=o.get("target_roles") or "",
            priority=o.get("priority"),
            eu_nationality=o.get("eu_nationality") or "",
            sources=["Sarah's target list"],
        )
        rec["sector"] = classify(rec)
        out.append(rec)
    return out


def from_registry() -> list[dict]:
    out = []
    for name, pop, lang, note in BRUSSELS_COMMUNES:
        out.append(_record(
            organisation=f"Commune de {name}" if "/" not in name else f"Commune {name}",
            sector="Commune / local government",
            category="Belgian public", type="Commune (Brussels-Capital)",
            base="Brussels-Capital Region", languages=lang, size=pop,
            description=note,
            target_roles="Social policy, integration, international relations, comms",
            sources=["Regional registry: 19 Brussels communes"],
        ))
    for name, pop, lang, note in BRUSSELS_PERIPHERY:
        out.append(_record(
            organisation=f"Gemeente/Commune {name}",
            sector="Commune / local government",
            category="Belgian public", type="Commune (periphery)",
            base="Brussels periphery", languages=lang, size=pop,
            description=note,
            target_roles="Local administration, social services",
            sources=["Regional registry: Brussels periphery"],
        ))
    for name, city, lang, students, note, anthro in BELGIAN_UNIVERSITIES:
        out.append(_record(
            organisation=name, sector="University & research",
            category="Universities & research", type="University",
            base=city, languages=lang, size=students, description=note,
            target_roles=("PhD / doctoral researcher, research assistant"
                          if anthro else "Research, administration, project support"),
            phd_relevant=anthro,
            sources=["Regional registry: Belgian universities"],
        ))
    for name, city, lang, students, note in BELGIAN_COLLEGES:
        out.append(_record(
            organisation=name, sector="University & research",
            category="Universities & research", type="University college",
            base=city, languages=lang, size=students, description=note,
            target_roles="Lecturing, project support, administration",
            sources=["Regional registry: Belgian university colleges"],
        ))
    for name, city, lang, staff, note in BELGIAN_HOSPITALS:
        out.append(_record(
            organisation=name, sector="Hospital & healthcare",
            category="Health", type="Hospital",
            base=city, languages=lang, size=staff, description=note,
            target_roles=("Intercultural mediation, social work, patient "
                          "services, communications, research administration"),
            sources=["Regional registry: Belgian hospitals"],
        ))
    for name, hq, lang, staff, note, remote in INTERNATIONAL_REMOTE:
        out.append(_record(
            organisation=name, sector="International organisation",
            category="International org", type="International organisation",
            base=hq, languages=lang, size=staff, description=note,
            target_roles=("Policy, programme, research; consultancy and roster "
                          "contracts" if remote else "Policy, programme, research"),
            remote_friendly=remote,
            sources=["Regional registry: international organisations"],
        ))
    # The EU/intergovernmental split is the one that matters for how you apply:
    # EU bodies mostly route through EPSO, while EUROCONTROL, NATO, the Council
    # of Europe and the UN agencies recruit directly.
    EU_BODY = (
        "european commission", "european parliament", "council of the european",
        "european council", "external action", "court of justice",
        "court of auditors", "european central bank", "investment bank",
        "investment fund", "economic and social committee", "committee of the",
        "ombudsman", "data protection supervisor", "public prosecutor", "epso",
        "executive agency", "frontex", "euaa", "europol", "eurojust", "fra (",
        "eige", "eurofound", "cedefop", "european training foundation",
        "environment agency", "ecdc", "medicines agency", "efsa", "echa",
        "eba /", "acer", "enisa", "eu-osha", "euipo", "translation centre",
        "eit (", "defence agency", "european university institute",
    )
    for name, base, lang, note, remote in EUROPEAN_INSTITUTIONS:
        low = name.lower()
        is_eu = any(k in low for k in EU_BODY)
        out.append(_record(
            organisation=name,
            sector="EU institution" if is_eu else "European & intl institution",
            category="EU institutions" if is_eu else "International org",
            type="EU body / agency" if is_eu else "Intergovernmental organisation",
            base=base, languages=lang, description=note,
            target_roles=("Policy officer, administrator, contract agent (CAST), "
                          "seconded national expert, traineeship" if is_eu else
                          "Policy, programme, political affairs — recruits "
                          "directly, no EPSO concours"),
            remote_friendly=remote,
            sources=["Regional registry: European & international institutions"],
        ))
    for name, subsector, lang, note in TRADE_ASSOCIATIONS:
        out.append(_record(
            organisation=name, sector="Trade association & federation",
            category="Trade associations", type=f"Federation ({subsector})",
            base="Brussels", languages=lang, description=note,
            target_roles="Policy Officer, Policy Adviser, Communications, "
                         "Advocacy, Project Manager",
            sources=["Regional registry: EU trade associations"],
        ))
    for name, wing, lang, note in POLITICAL_FOUNDATIONS:
        out.append(_record(
            organisation=name, sector="Political foundation",
            category="Think tanks", type=f"Political foundation ({wing})",
            base="Brussels", languages=lang, description=note,
            target_roles="Programme manager, policy officer, project coordinator",
            sources=["Regional registry: political foundations"],
        ))
    for name, lang, note in TRADE_UNIONS:
        out.append(_record(
            organisation=name, sector="Trade union & employer body",
            category="Trade unions", type="Trade union / employer federation",
            base="Brussels", languages=lang, description=note,
            target_roles="Policy adviser, international officer, campaigns",
            sources=["Regional registry: trade unions and employer bodies"],
        ))
    for name, city, lang, note in LATAM_INSTITUTIONS:
        out.append(_record(
            organisation=name, sector="Latin America institution",
            category="Latin America", type="Latin America body",
            base=city, languages=lang, description=note,
            target_roles="Programme officer, project coordinator, policy, culture",
            latam_relevant=True,
            sources=["Regional registry: Spanish/Latin American institutions"],
        ))
    for name, city, lang, note in CULTURAL_INSTITUTES:
        out.append(_record(
            organisation=name, sector="Cultural institute",
            category="Corporate & training", type="Cultural institute",
            base=city, languages=lang, description=note,
            target_roles="Programme coordinator, events, communications",
            sources=["Regional registry: cultural institutes"],
        ))
    for name, level, lang, note in BELGIAN_PUBLIC_BODIES:
        out.append(_record(
            organisation=name, sector="Belgian public sector",
            category="Belgian public", type=f"Public body ({level})",
            base="Brussels" if "Brussels" in level or level.startswith("Federal")
            else "Belgium",
            languages=lang, description=note,
            target_roles="Policy, research, international relations, comms",
            sources=["Regional registry: Belgian public bodies"],
        ))
    return out


def from_directories() -> list[dict]:
    if not DIRECTORY_JSON.exists():
        return []
    out = []
    for o in json.loads(DIRECTORY_JSON.read_text()):
        rec = _record(
            organisation=o["organisation"],
            sector="NGO & civil society",
            category=o.get("category") or "", type=o.get("type") or "",
            base=o.get("base") or "Belgium",
            homepage=o.get("homepage") or "",
            description=f"Member of {o.get('source_directory','a federation')}.",
            sources=[o.get("source_directory", "NGO directory")],
        )
        out.append(rec)
    return out


def from_register() -> list[dict]:
    """Larger Belgium-based orgs from the EU Transparency Register."""
    from .register import REGISTER_JSON

    if not REGISTER_JSON.exists():
        return []
    out = []
    for o in json.loads(REGISTER_JSON.read_text()):
        rec = _record(
            organisation=o["organisation"],
            sector=o.get("sector") or "NGO & civil society",
            category=o.get("category") or "", type=o.get("type") or "",
            base=o.get("base") or "Belgium",
            homepage=o.get("homepage") or "",
            size=o.get("size"),
            description=o.get("description") or "",
            sources=["EU Transparency Register"],
        )
        out.append(tag_themes(rec))
    return out


def merge(*groups: list[dict]) -> list[dict]:
    """Merge on a normalised name; earlier groups win on conflicts."""
    by_key: dict[str, dict] = {}
    for group in groups:
        for rec in group:
            key = norm(rec["organisation"])
            if not key:
                continue
            if key not in by_key:
                by_key[key] = rec
                continue
            # Same org from a second source: keep the richer record and merge
            # the provenance, rather than dropping either.
            cur = by_key[key]
            for field, val in rec.items():
                if field == "sources":
                    cur["sources"] = sorted(set(cur["sources"]) | set(val))
                elif field == "sector" and val and _from_registry_row(rec):
                    # The registry knows what a body actually is; the sheet's
                    # sector is inferred from free text and gets it wrong
                    # (Frontex as a "consultancy", EIGE as a "think tank").
                    cur["sector"] = val
                    cur["type"] = rec.get("type") or cur["type"]
                elif not cur.get(field) and val:
                    cur[field] = val
    return list(by_key.values())


def _from_registry_row(rec: dict) -> bool:
    return any("registry" in s.lower() for s in rec.get("sources", []))


def main() -> None:
    sheet, registry = from_sheet(), from_registry()
    directories, register = from_directories(), from_register()
    print(f"  sheet:       {len(sheet):>4}")
    print(f"  registry:    {len(registry):>4}")
    print(f"  directories: {len(directories):>4}")
    print(f"  register:    {len(register):>4}")

    # Curated sources first so they win the dedupe; the Register (broad but
    # thinner) fills the gaps around them.
    cat = [tag_themes(r) for r in merge(sheet, registry, directories, register)]
    cat.sort(key=lambda r: (r["sector"], r["organisation"]))
    CATALOGUE_JSON.write_text(json.dumps(cat, indent=2, ensure_ascii=False))

    from collections import Counter

    print(f"\n  {len(cat)} unique organisations -> {CATALOGUE_JSON}")
    print("\n  by sector:")
    for k, v in Counter(r["sector"] for r in cat).most_common():
        print(f"    {v:>4}  {k}")


if __name__ == "__main__":
    main()
