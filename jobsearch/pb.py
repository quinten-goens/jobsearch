"""Thin PocketBase client for the hosted instance on PocketHost.

Two credential pairs live in .env, by design:
  PH_ADMIN_USR / PH_ADMIN_PWD  -- superuser; used only to create/alter schema.
  PH_USR       / PH_PWD        -- regular auth; used for day-to-day read/write.

We talk to the REST API directly rather than pull in an SDK: the surface we
need (auth, list, create, update) is small and the SDKs lag PocketBase's
frequent breaking changes.
"""
import re
import time

import requests

from .config import ROOT

try:
    from dotenv import dotenv_values

    _ENV = dotenv_values(ROOT / ".env")
except Exception:  # pragma: no cover
    _ENV = {}


def _base() -> str:
    """API origin, even if PH_URL was pasted as the admin-UI deep link."""
    raw = _ENV.get("PH_URL") or ""
    m = re.match(r"(https?://[^/]+)", raw)
    if not m:
        raise RuntimeError("PH_URL missing or malformed in .env")
    return m.group(1)


BASE = _base()


class PBError(RuntimeError):
    pass


class PB:
    def __init__(self, admin: bool = False):
        self.base = BASE
        self._admin = admin
        self._token = ""
        self._token_at = 0.0

    # ------------------------------------------------------------------ auth
    def _creds(self) -> tuple[str, str]:
        if self._admin:
            u, p = _ENV.get("PH_ADMIN_USR"), _ENV.get("PH_ADMIN_PWD")
        else:
            u, p = _ENV.get("PH_USR"), _ENV.get("PH_PWD")
        if not u or not p:
            raise RuntimeError(
                f"Missing {'PH_ADMIN_*' if self._admin else 'PH_*'} in .env"
            )
        return u, p

    def token(self) -> str:
        # Tokens are valid well beyond this; re-auth hourly to be safe.
        if self._token and time.time() - self._token_at < 3000:
            return self._token
        u, p = self._creds()
        # Superusers and regular users authenticate against different
        # collections; a regular account may live in `users` or another
        # auth collection, so try the common ones.
        colls = ["_superusers"] if self._admin else ["users", "_superusers"]
        last = ""
        for coll in colls:
            r = requests.post(
                f"{self.base}/api/collections/{coll}/auth-with-password",
                json={"identity": u, "password": p}, timeout=20,
            )
            if r.ok:
                self._token = r.json()["token"]
                self._token_at = time.time()
                return self._token
            last = r.text[:160]
        raise PBError(f"PocketBase auth failed ({'admin' if self._admin else 'user'}): {last}")

    def _headers(self) -> dict:
        return {"Authorization": self.token()}

    # ------------------------------------------------------------- requests
    def _req(self, method: str, path: str, **kw) -> dict:
        r = requests.request(method, f"{self.base}{path}",
                             headers=self._headers(), timeout=30, **kw)
        if not r.ok:
            raise PBError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.text else {}

    # ------------------------------------------------------------- schema
    def list_collections(self) -> list[dict]:
        return self._req("GET", "/api/collections?perPage=200").get("items", [])

    def collection_exists(self, name: str) -> bool:
        return any(c["name"] == name for c in self.list_collections())

    def create_collection(self, spec: dict) -> dict:
        return self._req("POST", "/api/collections", json=spec)

    def update_collection(self, cid: str, spec: dict) -> dict:
        return self._req("PATCH", f"/api/collections/{cid}", json=spec)

    # ------------------------------------------------------------- records
    def list_records(self, coll: str, *, filter: str = "", per_page: int = 500,
                     expand: str = "") -> list[dict]:
        """All records across pages."""
        out, page = [], 1
        while True:
            q = f"?perPage={per_page}&page={page}"
            if filter:
                q += f"&filter={requests.utils.quote(filter)}"
            if expand:
                q += f"&expand={expand}"
            data = self._req("GET", f"/api/collections/{coll}/records{q}")
            out.extend(data.get("items", []))
            if page >= data.get("totalPages", 1):
                break
            page += 1
        return out

    def create_record(self, coll: str, body: dict) -> dict:
        return self._req("POST", f"/api/collections/{coll}/records", json=body)

    def update_record(self, coll: str, rid: str, body: dict) -> dict:
        return self._req("PATCH", f"/api/collections/{coll}/records/{rid}", json=body)

    def find_one(self, coll: str, filter: str) -> dict | None:
        items = self.list_records(coll, filter=filter, per_page=1)
        return items[0] if items else None
