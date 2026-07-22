"""The app's view of PocketBase: read the catalogue, log checks, trigger refreshes.

PocketBase is the source of truth. This module turns its relational rows back
into the flat per-org shape the UI works with, and provides the write paths for
the two user actions: marking a link checked, and refreshing an org's URL.
"""
from datetime import datetime, timezone

from .pb import PB


def _flatten(org: dict, version: dict | None) -> dict:
    """One org row + its current url_version -> the flat record the UI uses."""
    rec = dict(org)
    v = version or {}
    rec["careers_url"] = v.get("url", "")
    rec["careers_confidence"] = v.get("confidence", "")
    rec["careers_score"] = v.get("score", 0)
    rec["careers_reasons"] = v.get("reasons") or []
    rec["last_updated"] = v.get("last_updated", "")
    rec["last_updated_trust"] = v.get("last_updated_trust", "")
    rec["last_updated_age_days"] = v.get("last_updated_age_days")
    rec["version_id"] = v.get("id", "")
    return rec


def load_catalogue(pb: PB | None = None) -> list[dict]:
    """Every org with its current URL, plus the latest check verdict per org."""
    pb = pb or PB()
    orgs = pb.list_records("organisations")
    versions = {v["id"]: v for v in
                pb.list_records("url_versions", filter="superseded=false")}
    # Latest check per org, so the UI can show "you marked this good on <date>".
    last_check: dict[str, dict] = {}
    for c in sorted(pb.list_records("url_checks"),
                    key=lambda r: r.get("checked_at") or r.get("created") or ""):
        last_check[c["org"]] = c

    out = []
    for o in orgs:
        v = versions.get(o.get("current_url"))
        rec = _flatten(o, v)
        chk = last_check.get(o["id"])
        rec["last_check_verdict"] = chk.get("verdict", "") if chk else ""
        rec["last_check_at"] = (chk.get("checked_at") or chk.get("created", "")) if chk else ""
        out.append(rec)
    return out


def log_check(org_id: str, version_id: str, verdict: str, url: str,
              note: str = "", pb: PB | None = None) -> dict:
    """Record that the user checked a link in the GUI."""
    pb = pb or PB()
    return pb.create_record("url_checks", {
        "org": org_id,
        "url_version": version_id or None,
        "verdict": verdict,
        "checked_url": url,
        "note": note,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


def version_history(org_id: str, pb: PB | None = None) -> list[dict]:
    """All URLs ever found for an org, newest first."""
    pb = pb or PB()
    vs = pb.list_records("url_versions", filter=f'org="{org_id}"')
    return sorted(vs, key=lambda v: v.get("discovered_at") or v.get("created", ""),
                  reverse=True)


def refresh_org(org_id: str, org_name: str, base: str = "",
                existing_url: str = "", category: str = "",
                pb: PB | None = None) -> dict:
    """Re-run discovery for one org and, if the URL changed, append a version.

    Returns the new (or unchanged) current version record.
    """
    from .discover import discover_one
    from .freshness import last_updated

    pb = pb or PB()
    res = discover_one({
        "id": org_id, "organisation": org_name, "category": category,
        "priority": None, "existing_url": existing_url, "base": base,
    })

    current = pb.find_one("url_versions", f'org="{org_id}" && superseded=false')
    new_url = res.get("careers_url") or ""

    # No URL found, or same as current: log the refresh attempt, change nothing.
    if not new_url or (current and current.get("url") == new_url):
        return current or {}

    if current:
        pb.update_record("url_versions", current["id"], {"superseded": True})
    fresh = last_updated(new_url) if new_url else {}
    new = pb.create_record("url_versions", {
        "org": org_id,
        "url": new_url,
        "confidence": res.get("confidence") or "none",
        "score": int(res.get("score") or 0),
        "reasons": res.get("reasons") or [],
        "method": "refresh",
        "last_updated": fresh.get("date", ""),
        "last_updated_source": fresh.get("source", ""),
        "last_updated_trust": fresh.get("trust", ""),
        "last_updated_age_days": fresh.get("age_days"),
        "run_id": "refresh-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "superseded": False,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    })
    pb.update_record("organisations", org_id, {"current_url": new["id"]})
    return new
