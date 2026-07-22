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

    print("\n  Schema ready.")


if __name__ == "__main__":
    main()
