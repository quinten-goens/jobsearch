"""Build jobs.json from the boards and the per-organisation careers pages.

    python -m jobsearch.pipeline            # boards + every discovered org
    python -m jobsearch.pipeline --boards   # boards only (fast)
    python -m jobsearch.pipeline --limit 20

Each job records how it was found (`method`) and how much to trust it
(`confidence`), because the layers differ enormously in reliability: an ATS API
is exact, a heuristic scrape of a hand-built NGO page is not.
"""
import json
import sys
from datetime import datetime

from .boards import scrape_boards
from .config import DATA, JOBS_JSON
from .discover import DISCOVERED_JSON

DISCOVERY_HINT = (
    "No data/discovered.json yet - run `python -m jobsearch.discover` first, "
    "or use --boards to skip the per-org scrape."
)

# How much to trust each extraction method.
CONFIDENCE = {
    "board": "high",       # hand-written adapter for a known board
    "ats": "high",         # documented JSON API
    "jsonld": "high",      # schema.org JobPosting
    "rendered": "medium",  # heuristics over browser-rendered HTML
    "generic": "medium",   # heuristics over static HTML
}


def _confidence(method: str) -> str:
    root = method.split(":")[0]
    return CONFIDENCE.get(root, "low")


def scrape_orgs(limit: int = 0) -> list[dict]:
    """Scrape every organisation whose careers page we resolved."""
    from .scrape import scrape_page

    if not DISCOVERED_JSON.exists():
        print(DISCOVERY_HINT)
        return []

    orgs = [
        o for o in json.loads(DISCOVERED_JSON.read_text())
        if o.get("careers_url")
    ]
    if limit:
        orgs = orgs[:limit]

    out, stats = [], {}
    for i, org in enumerate(orgs, 1):
        try:
            jobs, method = scrape_page(org["careers_url"])
        except Exception as e:
            jobs, method = [], f"error:{type(e).__name__}"
        stats[method.split(":")[0]] = stats.get(method.split(":")[0], 0) + 1
        for j in jobs:
            out.append({
                **j,
                "employer": j.get("employer") or org["organisation"],
                "org_id": org["id"],
                "category": j.get("category") or org.get("category", ""),
                "priority": org.get("priority"),
                "source": org["organisation"],
                "source_url": org["careers_url"],
                "method": method,
                "confidence": _confidence(method),
            })
        print(f"{i:>3}/{len(orgs)} [{method:<18}] {len(jobs):>2}  "
              f"{org['organisation'][:44]}", flush=True)

    print("\n  method tally: " + "  ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return out


def main() -> None:
    args = sys.argv[1:]
    boards_only = "--boards" in args
    limit = 0
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    print("Scraping boards...")
    jobs = [
        {
            **j,
            "org_id": None,
            "source_url": j["url"],
            "method": "board",
            "confidence": "high",
        }
        for j in scrape_boards()
    ]
    print(f"  -> {len(jobs)} board jobs\n")

    if not boards_only:
        print("Scraping organisation careers pages...")
        jobs += scrape_orgs(limit)
        try:
            from .render import close_browser

            close_browser()
        except Exception:
            pass

    # Normalise every record to the same shape so the UI can rely on it.
    for j in jobs:
        j.setdefault("location", "")
        j.setdefault("posted", "")
        j.setdefault("deadline", "")
        j.setdefault("category", "")
        j.setdefault("priority", None)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(jobs),
        "jobs": jobs,
    }
    JOBS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    by_conf: dict = {}
    for j in jobs:
        by_conf[j["confidence"]] = by_conf.get(j["confidence"], 0) + 1
    print(f"\n{'='*70}")
    print(f"  {len(jobs)} jobs -> {JOBS_JSON}")
    print("  confidence: " + "  ".join(f"{k}={v}" for k, v in sorted(by_conf.items())))
    print(f"  with a publication date: "
          f"{sum(1 for j in jobs if j['posted'])}/{len(jobs)}")


if __name__ == "__main__":
    main()
