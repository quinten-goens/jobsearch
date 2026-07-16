"""Find and date-check each catalogue organisation's careers page.

    python -m jobsearch.enrich            # only rows that need it
    python -m jobsearch.enrich --all      # redo everything

Runs discovery over the catalogue rather than the sheet, then asks each
resolved page when it was last updated. Resumable: writes after every
organisation, and skips rows already carrying a careers URL.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .catalogue import CATALOGUE_JSON
from .config import BRAVE_API_KEY
from .discover import discover_one
from .freshness import last_updated


def enrich_one(rec: dict) -> dict:
    org = {
        "id": rec["organisation"],
        "organisation": rec["organisation"],
        "category": rec.get("category", ""),
        "priority": rec.get("priority"),
        # The homepage, where a directory gave us one, is a strong domain hint
        # for the scorer -- the same role the sheet's old link plays.
        "existing_url": rec.get("careers_url") or rec.get("homepage") or "",
        "base": rec.get("base", ""),
    }
    res = discover_one(org)
    rec["careers_url"] = res["careers_url"] or ""
    rec["careers_confidence"] = res["confidence"]
    rec["careers_score"] = res["score"]
    rec["careers_reasons"] = res["reasons"]
    rec["search_url"] = res["search_url"]
    if not rec.get("homepage") and rec["careers_url"]:
        from .discover import domain_of

        rec["homepage"] = f"https://{domain_of(rec['careers_url'])}"

    if rec["careers_url"]:
        f = last_updated(rec["careers_url"])
        rec["last_updated"] = f["date"]
        rec["last_updated_source"] = f["source"]
        rec["last_updated_trust"] = f["trust"]
        rec["last_updated_age_days"] = f["age_days"]
    return rec


def main() -> None:
    redo_all = "--all" in sys.argv
    cat = json.loads(CATALOGUE_JSON.read_text())

    todo = [r for r in cat if redo_all or not r.get("careers_url")]
    print(f"Enriching {len(todo)} of {len(cat)} organisations "
          f"({'Brave' if BRAVE_API_KEY else 'DuckDuckGo — slow'})\n")

    by_name = {r["organisation"]: r for r in cat}
    done = 0
    with ThreadPoolExecutor(max_workers=8 if BRAVE_API_KEY else 1) as pool:
        futures = {pool.submit(enrich_one, dict(r)): r["organisation"] for r in todo}
        for fut in as_completed(futures):
            name = futures[fut]
            done += 1
            try:
                rec = fut.result()
            except Exception as e:
                print(f"  ! {name[:44]}: {type(e).__name__}: {e}")
                continue
            by_name[name].update(rec)
            mark = {"high": "OK  ", "medium": "MED ", "none": "MISS"}[
                rec["careers_confidence"]
            ]
            age = rec.get("last_updated_age_days")
            age_s = f"{age:>4}d ago" if age is not None else "     —   "
            print(f"{done:>3}/{len(todo)} {mark} {age_s}  {name[:34]:<34} "
                  f"{str(rec['careers_url'])[:44]}", flush=True)
            CATALOGUE_JSON.write_text(json.dumps(cat, indent=2, ensure_ascii=False))

    from collections import Counter

    print("\n" + "=" * 70)
    print("  careers page: " + "  ".join(
        f"{k}={v}" for k, v in Counter(
            r.get("careers_confidence") or "not tried" for r in cat
        ).most_common()))
    dated = sum(1 for r in cat if r.get("last_updated"))
    print(f"  with a last-updated date: {dated}/{len(cat)}")

    try:
        from .render import close_browser

        close_browser()
    except Exception:
        pass


if __name__ == "__main__":
    main()
