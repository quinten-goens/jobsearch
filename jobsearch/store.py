"""The app's view of PocketBase: read the catalogue, log checks, trigger refreshes.

PocketBase is the source of truth. This module turns its relational rows back
into the flat per-org shape the UI works with, and provides the write paths for
the two user actions: marking a link checked, and refreshing an org's URL.
"""
from datetime import datetime, timezone

from .pb import PB

# Reads use the regular account (open list/view rules). Writes that touch the
# organisations table -- repointing current_url on a refresh -- need superuser,
# since organisations stays read-only to the public so the catalogue can't be
# corrupted. One cached admin client, reused so we don't re-auth per action.
_admin: PB | None = None


def _admin_pb() -> PB:
    global _admin
    if _admin is None:
        _admin = PB(admin=True)
    return _admin


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
    rec["current_page_date"] = v.get("last_updated", "")
    rec["openings_state"] = v.get("openings_state", "")
    rec["openings_count"] = v.get("openings_count") or 0
    rec["openings_titles"] = v.get("openings_titles") or []
    rec["openings_new_titles"] = v.get("openings_new_titles") or []
    rec["openings_new_at"] = v.get("openings_new_at", "")
    # Review state comes straight off the org row.
    rec["reviewed"] = bool(org.get("reviewed"))
    rec["reviewed_url"] = org.get("reviewed_url", "")
    rec["reviewed_page_date"] = org.get("reviewed_page_date", "")
    rec["reviewed_at"] = org.get("reviewed_at", "")
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


def set_reviewed(org_id: str, reviewed: bool, current_url: str = "",
                 page_date: str = "") -> dict:
    """Tick/untick 'reviewed'. On tick, record what was reviewed against so a
    later refresh can tell whether the page has changed."""
    admin = _admin_pb()
    body: dict = {"reviewed": reviewed}
    if reviewed:
        body["reviewed_url"] = current_url
        body["reviewed_page_date"] = page_date or ""
        body["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        body["reviewed_url"] = ""
        body["reviewed_page_date"] = ""
        body["reviewed_at"] = None
    return admin.update_record("organisations", org_id, body)


def clear_new_openings(version_id: str) -> None:
    """Dismiss the 'new openings' flag once Sarah has seen it."""
    _admin_pb().update_record("url_versions", version_id,
                              {"openings_new_titles": [], "openings_new_at": None})


def version_history(org_id: str, pb: PB | None = None) -> list[dict]:
    """All URLs ever found for an org, newest first."""
    pb = pb or PB()
    vs = pb.list_records("url_versions", filter=f'org="{org_id}"')
    return sorted(vs, key=lambda v: v.get("discovered_at") or v.get("created", ""),
                  reverse=True)


def refresh_org(org: dict, pb: PB | None = None) -> dict:
    """Re-run discovery for one org. Append a url_version if the URL changed,
    and auto-untick 'reviewed' if the page has been updated since she checked.

    `org` is a flat record from load_catalogue (has id, organisation, base,
    careers_url, category, reviewed, reviewed_url, reviewed_page_date).

    Returns {changed, new_url, unreviewed, page_date} for the UI to report.
    """
    from .discover import discover_one
    from .freshness import last_updated

    pb = pb or _admin_pb()  # writes to organisations require superuser
    org_id = org["id"]
    res = discover_one({
        "id": org_id, "organisation": org["organisation"],
        "category": org.get("category", ""), "priority": None,
        "existing_url": org.get("careers_url", ""), "base": org.get("base", ""),
    })
    new_url = res.get("careers_url") or ""
    current = pb.find_one("url_versions", f'org="{org_id}" && superseded=false')
    url_changed = bool(new_url) and (not current or current.get("url") != new_url)

    # Always re-check freshness of the live page, even when the URL is unchanged
    # -- "same URL, but the page was updated" is the common case.
    fresh = last_updated(new_url) if new_url else {}
    page_date = fresh.get("date", "")

    # --- append a new version if the URL moved --------------------------
    if url_changed:
        if current:
            pb.update_record("url_versions", current["id"], {"superseded": True})
        new = pb.create_record("url_versions", {
            "org": org_id, "url": new_url,
            "confidence": res.get("confidence") or "none",
            "score": int(res.get("score") or 0),
            "reasons": res.get("reasons") or [],
            "method": "refresh",
            "last_updated": page_date,
            "last_updated_source": fresh.get("source", ""),
            "last_updated_trust": fresh.get("trust", ""),
            "last_updated_age_days": fresh.get("age_days"),
            "run_id": "refresh-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
            "superseded": False,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })
        pb.update_record("organisations", org_id, {"current_url": new["id"]})
    elif current and page_date and page_date != current.get("last_updated"):
        # URL unchanged but the page's own date moved: keep the freshness on
        # the current version up to date.
        pb.update_record("url_versions", current["id"], {
            "last_updated": page_date,
            "last_updated_source": fresh.get("source", ""),
            "last_updated_trust": fresh.get("trust", ""),
            "last_updated_age_days": fresh.get("age_days"),
        })

    # --- re-detect openings and diff against what we had ---------------
    # A title present now that wasn't present at the last scan is genuinely
    # new -- the early-warning signal for an off-board vacancy.
    new_titles: list[str] = []
    if new_url:
        from .openings import detect

        # The version we'll write openings onto: the freshly-created one if the
        # URL moved, else the existing current version.
        target = pb.find_one("url_versions",
                             f'org="{org_id}" && superseded=false')
        prev_titles = [t.lower().strip()
                       for t in ((target or {}).get("openings_titles") or [])]
        od = detect(new_url)
        now_titles = od["titles"]
        # Only meaningful when we can actually read the page.
        if od["state"] == "has_openings":
            new_titles = [t for t in now_titles
                          if t.lower().strip() not in prev_titles]
        if target:
            body = {
                "openings_state": od["state"],
                "openings_count": od["count"],
                "openings_titles": now_titles,
                "openings_checked_at": datetime.now(timezone.utc).isoformat(),
            }
            # Keep the new-titles flag sticky until she visits What's new and
            # it's re-scanned with nothing newer; only overwrite when we found
            # something (don't wipe a prior 'new' on an unreadable re-scan).
            if new_titles:
                body["openings_new_titles"] = new_titles
                body["openings_new_at"] = datetime.now(timezone.utc).isoformat()
            pb.update_record("url_versions", target["id"], body)

    # --- auto-untick 'reviewed' if the page has been updated ------------
    unreviewed = False
    if org.get("reviewed"):
        prev_date = org.get("reviewed_page_date") or ""
        # Updated == the careers URL moved, or the page's trustworthy
        # last-updated date is now newer than when she reviewed it.
        page_is_newer = bool(page_date and prev_date and page_date > prev_date)
        if url_changed or page_is_newer:
            pb.update_record("organisations", org_id, {
                "reviewed": False, "reviewed_url": "",
                "reviewed_page_date": "", "reviewed_at": None,
            })
            unreviewed = True

    return {
        "changed": url_changed,
        "new_url": new_url,
        "unreviewed": unreviewed,
        "page_date": page_date,
        "new_titles": new_titles,
    }
