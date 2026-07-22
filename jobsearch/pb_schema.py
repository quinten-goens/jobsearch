"""Create the PocketBase collections that back the catalogue.

    python -m jobsearch.pb_schema          # create anything missing
    python -m jobsearch.pb_schema --show   # just print what exists

Three collections (see the module docstring in pb.py for why relational):

  organisations  -- stable identity + metadata; one row per org.
  url_versions   -- every careers URL a discovery run has found for an org.
                    Each refresh appends a new row; the newest has
                    superseded=false. Nothing is ever deleted, so the full
                    history of how a URL changed is preserved.
  url_checks     -- a log of the user's actions in the GUI: opened, marked
                    good/wrong/dead, applied. This is the "when was this link
                    checked" record.

Idempotent: skips collections that already exist, so it's safe to re-run.
"""
import sys

from .pb import PB


def _text(name, **kw):
    return {"name": name, "type": "text", "required": False, **kw}


def _bool(name):
    return {"name": name, "type": "bool", "required": False}


def _num(name):
    return {"name": name, "type": "number", "required": False}


def _json(name):
    return {"name": name, "type": "json", "required": False, "maxSize": 200000}


def _date(name):
    return {"name": name, "type": "date", "required": False}


def _rel(name, target_id, *, required=False, max_one=True):
    return {
        "name": name, "type": "relation", "required": required,
        "collectionId": target_id, "cascadeDelete": False,
        "minSelect": 0, "maxSelect": 1 if max_one else 999,
    }


def _select(name, values):
    return {"name": name, "type": "select", "required": False,
            "maxSelect": 1, "values": values}


def _ensure_fields(pb: "PB", name: str, spec_fields: list[dict]) -> None:
    """Add any spec field the live collection is missing, without touching the
    existing ones. Makes the schema self-healing: new fields (content_hash,
    openings_new_*) land on a collection that already holds data, instead of
    silently failing to write."""
    coll = next(c for c in pb.list_collections() if c["name"] == name)
    have = {f["name"] for f in coll.get("fields", coll.get("schema", []))}
    missing = [f for f in spec_fields if f["name"] not in have]
    if not missing:
        return
    fields = list(coll.get("fields", coll.get("schema", []))) + missing
    pb.update_collection(coll["id"], {"fields": fields})
    print(f"  {name}: added {', '.join(f['name'] for f in missing)}")


def organisations_spec() -> dict:
    return {
        "name": "organisations",
        "type": "base",
        "fields": [
            _text("org_key", required=True),  # normalised unique key
            _text("organisation", required=True),
            _text("sector"), _text("category"), _text("type"), _text("base"),
            _text("languages"), _num("size"),
            _text("description", maxSize=5000),
            _text("target_roles", maxSize=2000),
            _text("why_fits", maxSize=5000),
            _num("priority"), _text("eu_nationality"),
            _bool("phd_relevant"), _bool("latam_relevant"), _bool("remote_friendly"),
            _text("homepage", maxSize=1000), _text("search_url", maxSize=1000),
            _json("sources"),
            # "Reviewed" state. reviewed=true means Sarah has looked at the
            # current careers page. reviewed_url / reviewed_page_date capture
            # what she reviewed against, so a refresh can tell whether the page
            # has since changed and auto-untick.
            _bool("reviewed"),
            _text("reviewed_url", maxSize=1000),
            _text("reviewed_page_date"),   # page last_updated at review time
            _date("reviewed_at"),
            # current_url is added in a second pass, once url_versions exists.
        ],
        "indexes": [
            "CREATE UNIQUE INDEX idx_org_key ON organisations (org_key)",
        ],
    }


def url_versions_spec(org_cid: str) -> dict:
    return {
        "name": "url_versions",
        "type": "base",
        "fields": [
            _rel("org", org_cid, required=True),
            _text("url", required=True, maxSize=1000),
            _select("confidence", ["high", "medium", "none"]),
            _num("score"),
            _json("reasons"),
            _text("method"),
            _text("last_updated"),
            _text("last_updated_source"),
            _text("last_updated_trust"),
            _num("last_updated_age_days"),
            # Live-openings snapshot for this page (HTML-only detection).
            _select("openings_state",
                    ["has_openings", "no_openings", "unknown"]),
            _num("openings_count"),
            _json("openings_titles"),
            _date("openings_checked_at"),
            # Titles that appeared since the last scan -- the "What's new" flag.
            _json("openings_new_titles"),
            _date("openings_new_at"),
            # Content fingerprint: lets us date metadata-less pages by change.
            _text("content_hash", maxSize=64),
            _date("content_hash_at"),
            _text("run_id"),          # which discovery sweep produced it
            _bool("superseded"),      # false only for the newest per org
            _date("discovered_at"),
        ],
        "indexes": [
            "CREATE INDEX idx_uv_org ON url_versions (org)",
            "CREATE INDEX idx_uv_current ON url_versions (org, superseded)",
        ],
    }


def url_checks_spec(org_cid: str, uv_cid: str) -> dict:
    return {
        "name": "url_checks",
        "type": "base",
        "fields": [
            _rel("org", org_cid, required=True),
            _rel("url_version", uv_cid),
            _select("verdict", ["opened", "good", "wrong", "dead",
                                "applied", "not_relevant"]),
            _text("note", maxSize=2000),
            _text("checked_url", maxSize=1000),  # snapshot, survives version churn
            _date("checked_at"),
        ],
        "indexes": [
            "CREATE INDEX idx_check_org ON url_checks (org)",
        ],
    }


def _cid(pb: PB, name: str) -> str:
    for c in pb.list_collections():
        if c["name"] == name:
            return c["id"]
    raise RuntimeError(f"collection {name} not found")


def main() -> None:
    pb = PB(admin=True)

    if "--show" in sys.argv:
        for c in pb.list_collections():
            if not c["name"].startswith("_"):
                fields = [f["name"] for f in c.get("fields", c.get("schema", []))]
                print(f"  {c['name']}: {', '.join(fields)}")
        return

    # 1. organisations
    if pb.collection_exists("organisations"):
        print("  organisations: exists")
    else:
        pb.create_collection(organisations_spec())
        print("  organisations: created")
    org_cid = _cid(pb, "organisations")

    # 2. url_versions (needs the org collection id for its relation)
    if pb.collection_exists("url_versions"):
        print("  url_versions: exists")
        _ensure_fields(pb, "url_versions", url_versions_spec(org_cid)["fields"])
    else:
        pb.create_collection(url_versions_spec(org_cid))
        print("  url_versions: created")
    uv_cid = _cid(pb, "url_versions")

    # 3. url_checks
    if pb.collection_exists("url_checks"):
        print("  url_checks: exists")
    else:
        pb.create_collection(url_checks_spec(org_cid, uv_cid))
        print("  url_checks: created")

    # 3b. API access rules. Base collections are superuser-only by default,
    # which blocks the app's regular PH_USR account. These rules are
    # deliberately open (""), i.e. public read/write without auth: the data is
    # public Brussels org names and careers URLs, and it keeps the app simple.
    # Schema and the organisations table's writes stay superuser-only, so the
    # catalogue itself can't be corrupted through the open rules.
    RULES = {
        "organisations": {"listRule": "", "viewRule": ""},
        "url_versions": {"listRule": "", "viewRule": "",
                         "createRule": "", "updateRule": ""},
        "url_checks": {"listRule": "", "viewRule": "", "createRule": ""},
    }
    for c in pb.list_collections():
        if c["name"] in RULES:
            pb.update_collection(c["id"], RULES[c["name"]])
    print("  API access rules: set")

    # 4. back-reference: organisations.current_url -> url_versions
    org = next(c for c in pb.list_collections() if c["name"] == "organisations")
    have = {f["name"] for f in org.get("fields", org.get("schema", []))}
    if "current_url" not in have:
        fields = org.get("fields", org.get("schema", []))
        fields.append(_rel("current_url", uv_cid))
        pb.update_collection(org["id"], {"fields": fields})
        print("  organisations.current_url: added")
    else:
        print("  organisations.current_url: exists")

    # 5. Enable the batch API so the sync can write many records per request
    # (PocketHost caps requests at 1,000/hour; per-record writes blow through
    # that). The settings key has moved across versions, so try the current one
    # and fall back quietly.
    try:
        pb._req("PATCH", "/api/settings",
                json={"batch": {"enabled": True, "maxRequests": 200,
                                "timeout": 30, "maxBodySize": 0}})
        print("  batch API: enabled")
    except Exception as e:
        print(f"  batch API: could not enable automatically ({str(e)[:60]});"
              " enable it in Settings > Batch")

    print("\n  Schema ready.")


if __name__ == "__main__":
    main()
