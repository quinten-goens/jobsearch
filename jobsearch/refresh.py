"""The daily refresh: re-date and re-scan every known careers page, then sync.

    python -m jobsearch.refresh              # re-check all, then push to PocketBase
    python -m jobsearch.refresh --no-sync    # local only, skip PocketBase
    python -m jobsearch.refresh --limit 50   # first N orgs (a smoke test)

This is the job the Docker container is built to run on a schedule. It is
deliberately *discovery-free*: it never searches for new careers URLs (that's
`jobsearch.enrich`, which spends Brave-search quota). It only re-fetches the
pages we already know, so it's cheap enough to run every day and safe on the
API rate limits.

What one run does, per organisation that already has a careers URL:
  - re-check freshness (metadata date, else content-hash change detection)
  - re-scan live openings
and then `pb_sync` pushes the updated snapshot to PocketBase, which is what the
app reads. Content-hash change detection means the second and later runs finally
date the ~1,400 pages that expose no last-updated metadata of their own.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .catalogue import CATALOGUE_JSON
from .enrich import recheck_page


def main() -> None:
    no_sync = "--no-sync" in sys.argv
    limit = 0
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    cat = json.loads(CATALOGUE_JSON.read_text())
    todo = [r for r in cat if r.get("careers_url")]
    if limit:
        todo = todo[:limit]
    print(f"Refreshing {len(todo)} known careers pages "
          f"(of {len(cat)} organisations)\n", flush=True)

    by_name = {r["organisation"]: r for r in cat}
    done = changed = hiring = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(recheck_page, dict(r)): r["organisation"]
                   for r in todo}
        for fut in as_completed(futures):
            name = futures[fut]
            done += 1
            try:
                rec = fut.result()
            except Exception as e:
                print(f"  ! {name[:44]}: {type(e).__name__}: {e}", flush=True)
                continue
            by_name[name].update(rec)
            if rec.get("openings_state") == "has_openings":
                hiring += 1
            src = rec.get("last_updated_source") or "—"
            if src == "hash":
                changed += 1
            if done % 100 == 0 or done == len(todo):
                print(f"  {done:>4}/{len(todo)}  "
                      f"hiring={hiring}  hash-dated={changed}", flush=True)
    # Write once at the end: the refresh is idempotent, so a mid-run crash just
    # means re-running, and we avoid thousands of disk writes.
    CATALOGUE_JSON.write_text(json.dumps(cat, indent=2, ensure_ascii=False))
    print(f"\n  wrote {CATALOGUE_JSON}", flush=True)

    if no_sync:
        print("  --no-sync: skipping PocketBase push")
        return

    print("\n=== syncing to PocketBase ===", flush=True)
    from . import pb_sync

    pb_sync.main()


if __name__ == "__main__":
    main()
