"""Push the local catalogue into PocketBase, using the batch API.

    python -m jobsearch.pb_sync

PocketHost caps requests at 1,000/hour, so per-record writes are out of the
question for 665 orgs. Everything goes through /api/batch: creates and updates
are grouped into a handful of HTTP calls instead of thousands.

Idempotent and resumable: orgs are keyed by normalised name, so a second run
updates rather than duplicates, and only appends a url_version when the URL
actually changed.
"""
import json
from datetime import datetime, timezone

from .catalogue import CATALOGUE_JSON, norm
from .pb import PB

ORG_FIELDS = (
    "organisation", "sector", "category", "type", "base", "languages",
    "size", "description", "target_roles", "why_fits", "priority",
    "eu_nationality", "phd_relevant", "latam_relevant", "remote_friendly",
    "homepage", "search_url",
)


def _org_body(rec: dict) -> dict:
    body = {f: rec.get(f) for f in ORG_FIELDS}
    body["org_key"] = norm(rec["organisation"])
    body["sources"] = rec.get("sources") or []
    # PocketBase rejects None for number fields; drop only None (keep 0/False).
    return {k: v for k, v in body.items() if v is not None}


def _version_body(rec: dict, org_id: str, run_id: str) -> dict:
    return {
        "org": org_id,
        "url": rec["careers_url"],
        "confidence": rec.get("careers_confidence") or "none",
        "score": int(rec.get("careers_score") or 0),
        "reasons": rec.get("careers_reasons") or [],
        "method": rec.get("careers_method") or "search+verify",
        "last_updated": rec.get("last_updated") or "",
        "last_updated_source": rec.get("last_updated_source") or "",
        "last_updated_trust": rec.get("last_updated_trust") or "",
        "last_updated_age_days": rec.get("last_updated_age_days"),
        "openings_state": rec.get("openings_state") or "unknown",
        "openings_count": int(rec.get("openings_count") or 0),
        "openings_titles": rec.get("openings_titles") or [],
        "openings_checked_at": rec.get("openings_checked_at") or None,
        "run_id": run_id,
        "superseded": False,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def _changed(existing: dict, body: dict) -> bool:
    return any(existing.get(k) != v for k, v in body.items())


def main() -> None:
    pb = PB(admin=True)
    cat = json.loads(CATALOGUE_JSON.read_text())
    run_id = "sync-" + datetime.now().strftime("%Y%m%d-%H%M%S")

    # --- read current state: 3 paginated list calls, not 665 -------------
    print("Reading current PocketBase state…", flush=True)
    orgs_by_key = {o["org_key"]: o for o in pb.list_records("organisations")}
    cur_by_org = {v["org"]: v
                  for v in pb.list_records("url_versions", filter="superseded=false")}

    # --- phase 1: create missing orgs (batched) --------------------------
    to_create = [r for r in cat if norm(r["organisation"]) not in orgs_by_key]
    to_update = [(orgs_by_key[norm(r["organisation"])], r)
                 for r in cat if norm(r["organisation"]) in orgs_by_key]

    if to_create:
        ops = [{"method": "POST",
                "path": "/api/collections/organisations/records",
                "body": _org_body(r)} for r in to_create]
        created = pb.batch(ops)
        for r, res in zip(to_create, created):
            orgs_by_key[norm(r["organisation"])] = res
        print(f"  created {len(created)} organisations", flush=True)

    # --- phase 1b: update changed orgs (batched, only real diffs) --------
    upd_ops = []
    for existing, r in to_update:
        body = _org_body(r)
        if _changed(existing, body):
            upd_ops.append({"method": "PATCH",
                            "path": f"/api/collections/organisations/records/{existing['id']}",
                            "body": body})
    if upd_ops:
        pb.batch(upd_ops)
    print(f"  updated {len(upd_ops)} organisations", flush=True)

    # --- phase 2: url_versions where the URL changed (batched) -----------
    supersede_ops, create_ops, create_meta, openings_ops = [], [], [], []
    for r in cat:
        url = r.get("careers_url") or ""
        if not url:
            continue
        org = orgs_by_key[norm(r["organisation"])]
        current = cur_by_org.get(org["id"])
        if current and current.get("url") == url:
            # URL unchanged, but openings change while the URL stays the same
            # -- that's the whole point of the off-board signal. Refresh the
            # openings snapshot on the existing version rather than skipping.
            if r.get("openings_checked_at"):
                openings_ops.append({
                    "method": "PATCH",
                    "path": f"/api/collections/url_versions/records/{current['id']}",
                    "body": {
                        "openings_state": r.get("openings_state") or "unknown",
                        "openings_count": int(r.get("openings_count") or 0),
                        "openings_titles": r.get("openings_titles") or [],
                        "openings_checked_at": r.get("openings_checked_at"),
                    }})
            continue
        if current:
            supersede_ops.append({
                "method": "PATCH",
                "path": f"/api/collections/url_versions/records/{current['id']}",
                "body": {"superseded": True}})
        create_ops.append({
            "method": "POST",
            "path": "/api/collections/url_versions/records",
            "body": _version_body(r, org["id"], run_id)})
        create_meta.append(org["id"])

    if openings_ops:
        pb.batch(openings_ops)
        print(f"  url_versions: {len(openings_ops)} openings snapshots updated")
    if supersede_ops:
        pb.batch(supersede_ops)
    new_versions = []
    if create_ops:
        new_versions = pb.batch(create_ops)

    # --- phase 3: repoint organisations.current_url (batched) ------------
    point_ops = [{
        "method": "PATCH",
        "path": f"/api/collections/organisations/records/{org_id}",
        "body": {"current_url": ver["id"]},
    } for org_id, ver in zip(create_meta, new_versions)]
    if point_ops:
        pb.batch(point_ops)

    print(f"\n  url_versions: {len(new_versions)} new")
    print(f"  run_id: {run_id}")


if __name__ == "__main__":
    main()
