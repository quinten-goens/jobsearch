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

import os

try:
    from dotenv import dotenv_values

    _ENV = dotenv_values(ROOT / ".env")
except Exception:  # pragma: no cover
    _ENV = {}


def _secret(key: str) -> str:
    """One credential, resolved across every deployment target we run in:

      1. a local .env file            -- laptop / repo
      2. the process environment      -- Docker / Dokploy inject vars, not a file
      3. Streamlit's st.secrets       -- Streamlit Community Cloud

    So the same code works whether the value arrives as a file, an env var, or a
    Streamlit secret, with no per-environment branching.
    """
    # Process env wins over a possibly-stale .env file, so a deployment can
    # always override; then the local file; then Streamlit secrets.
    val = os.environ.get(key) or _ENV.get(key)
    if val:
        return val
    try:
        import streamlit as st

        # st.secrets raises if there's no secrets file, so guard the lookup.
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return ""


def _base() -> str:
    """API origin, even if PH_URL was pasted as the admin-UI deep link."""
    raw = _secret("PH_URL")
    m = re.match(r"(https?://[^/]+)", raw)
    if not m:
        raise RuntimeError(
            "PH_URL missing or malformed. Set it in .env (local), as an "
            "environment variable (Docker/Dokploy), or in st.secrets "
            "(Streamlit Cloud)."
        )
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
            u, p = _secret("PH_ADMIN_USR"), _secret("PH_ADMIN_PWD")
        else:
            u, p = _secret("PH_USR"), _secret("PH_PWD")
        if not u or not p:
            raise RuntimeError(
                f"Missing {'PH_ADMIN_*' if self._admin else 'PH_*'} — set them "
                "in .env, the environment, or st.secrets."
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
    # PocketHost rate-limits /api paths and answers 429 when pushed. Space
    # requests out and back off on 429 rather than failing the whole sync.
    _min_interval = 0.35
    _last_req = 0.0

    def _req(self, method: str, path: str, **kw) -> dict:
        for attempt in range(6):
            gap = time.time() - PB._last_req
            if gap < PB._min_interval:
                time.sleep(PB._min_interval - gap)
            PB._last_req = time.time()

            r = requests.request(method, f"{self.base}{path}",
                                 headers=self._headers(), timeout=30, **kw)
            if r.status_code == 429:
                wait = min(30, 2 ** attempt)
                time.sleep(wait)
                continue
            if not r.ok:
                raise PBError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
            return r.json() if r.text else {}
        raise PBError(f"{method} {path} -> 429 after retries (rate limited)")

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

    # ------------------------------------------------------------- batch
    # PocketBase runs many writes in one HTTP request via /api/batch. This is
    # the difference between a ~1,500-call sync and a ~30-call one -- essential
    # under PocketHost's 1,000-requests/hour ceiling. Must be enabled in the
    # instance settings (Settings > Batch); create_collection turns it on for
    # us in pb_schema.
    def batch(self, ops: list[dict], chunk: int = 100) -> list[dict]:
        """Run write ops in batches. Each op: {method, path, body}.

        Returns the per-op response bodies in order. Raises on any failure.
        """
        results: list[dict] = []
        for start in range(0, len(ops), chunk):
            part = ops[start:start + chunk]
            payload = {"requests": [
                {"method": o["method"], "url": o["path"], "body": o.get("body", {})}
                for o in part
            ]}
            data = self._req("POST", "/api/batch", json=payload)
            # PocketBase returns a list of {status, body} in request order.
            for item in (data if isinstance(data, list) else data.get("responses", [])):
                if item.get("status", 200) >= 400:
                    raise PBError(f"batch op failed: {item}")
                results.append(item.get("body", {}))
        return results
