"""Vast.ai through its REST API (https://console.vast.ai/api/v0/..., Bearer key from env VAST_API_KEY).

Endpoints as used by the official vast-cli (checked 16 Nov 2026):
  search offers      POST   /api/v0/bundles/            {filters..., "order", "type", "limit", "allocated_storage"}
  create instance    PUT    /api/v0/asks/{offer}/       {"client_id": "me", "image", "env", "disk", "label", "onstart",
                                                          "runtype", "cancel_unavail"} -> {"success", "new_contract"}
  list instances     GET    /api/v1/instances/          paged with next_token (the v0 list is deprecated)
  one instance       GET    /api/v0/instances/{id}/?owner=me -> {"instances": {...}}
  destroy            DELETE /api/v0/instances/{id}/
  current user       GET    /api/v0/users/current/      only the field `credit` is kept; the rest is dropped at once
  account SSH keys   GET/POST /api/v0/ssh/              {"ssh_key": "<public key>"}
  attach SSH key     POST   /api/v0/instances/{id}/ssh/ {"ssh_key": "<public key>"}

The HTTP transport can be replaced (`use_transport`), so tests run against a fake API. Error texts never contain the
key or request headers.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from . import settings, state
from .errors import ComputeError, MissingKey

API = "https://console.vast.ai"
KEY_ENV = "VAST_API_KEY"
KEYS_PAGE = "https://cloud.vast.ai/manage-keys/"
SIGNUP_PAGE = "https://cloud.vast.ai/"
REFERRAL_NOTE = ("Referral link: the author of Crewcut earns 3% of your Vast spend as credit. "
                 "It costs you nothing extra.")

_transport: httpx.BaseTransport | None = None


class VastError(ComputeError):
    pass


def use_transport(transport: httpx.BaseTransport | None) -> None:
    """Route every Vast request through this transport (tests pass an httpx.MockTransport)."""
    global _transport
    _transport = transport


def has_key() -> bool:
    return bool(os.environ.get(KEY_ENV, "").strip())


def referral_url() -> str:
    return str(settings.get("vast_referral") or "").strip()


def missing_key_text() -> str:
    """One plain sentence (plus the disclosure when a referral link is configured)."""
    ref = referral_url()
    text = (f"No Vast key: create one at {KEYS_PAGE} (new to Vast? sign up first at {ref or SIGNUP_PAGE}) "
            f"and add the line {KEY_ENV}=<your key> to the .env file of your Crewcut folder.")
    if ref:
        text += " " + REFERRAL_NOTE
    return text


class Vast:
    name = "vast"

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None, base: str = API,
                 timeout: float = 40.0, retries: int = 2):
        key = (api_key or os.environ.get(KEY_ENV, "")).strip()
        if not key:
            raise MissingKey(missing_key_text())
        self._retries = retries
        self._client = httpx.Client(base_url=base, transport=transport or _transport, timeout=timeout,
                                    headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                             "User-Agent": "crewcut-compute"})

    # ---- plumbing ------------------------------------------------------------------------------------------------
    def _req(self, method: str, path: str, *, params: dict | None = None, body: Any = None) -> Any:
        last = ""
        for attempt in range(self._retries + 1):
            try:
                r = self._client.request(method, path, params=params, json=body)
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}"
                state.sleep(2 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self._retries:
                last = f"HTTP {r.status_code}"
                state.sleep(3 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise MissingKey(f"Vast refused the key (HTTP {r.status_code}). Check {KEY_ENV} in the .env file; "
                                 f"keys are at {KEYS_PAGE}.")
            if r.status_code >= 400:
                raise VastError(f"Vast {method} {path}: HTTP {r.status_code} {_short(r.text)}")
            try:
                return r.json()
            except ValueError as e:
                raise VastError(f"Vast {method} {path}: answer is not JSON") from e
        raise VastError(f"Vast {method} {path} failed: {last}")

    def close(self) -> None:
        self._client.close()

    # ---- offers and instances ------------------------------------------------------------------------------------
    def search_offers(self, *, gpu_names: list[str], max_price: float, regions: list[str] | None = None,
                      min_reliability: float = 0.0, min_inet_down: float = 0, min_inet_up: float = 0,
                      disk_gb: float = 40, verified: bool = True, limit: int = 64) -> list[dict]:
        q: dict[str, Any] = {
            "verified": {"eq": bool(verified)}, "external": {"eq": False}, "rentable": {"eq": True},
            "rented": {"eq": False}, "num_gpus": {"eq": 1}, "gpu_name": {"in": list(gpu_names)},
            "dph_total": {"lte": float(max_price)}, "reliability": {"gte": float(min_reliability)},
            "inet_down": {"gte": float(min_inet_down)}, "inet_up": {"gte": float(min_inet_up)},
            "disk_space": {"gte": float(disk_gb)},
            "order": [["dph_total", "asc"]], "type": "on-demand", "limit": int(limit),
            "allocated_storage": float(disk_gb),
        }
        if regions:
            q["geolocation"] = {"in": list(regions)}
        d = self._req("POST", "/api/v0/bundles/", body=q)
        offers = d.get("offers") if isinstance(d, dict) else None
        if isinstance(offers, dict):
            offers = [offers]
        return [o for o in offers or [] if isinstance(o, dict)]

    def create_instance(self, offer_id: int | str, *, image: str, disk_gb: float, label: str,
                        env: dict[str, str] | None = None, onstart: str = "") -> int:
        body = {"client_id": "me", "image": image, "env": dict(env or {}), "disk": float(disk_gb), "label": label,
                "onstart": onstart, "runtype": "ssh_direc ssh_proxy", "cancel_unavail": True}
        d = self._req("PUT", f"/api/v0/asks/{int(offer_id)}/", body=body)
        if not isinstance(d, dict) or not d.get("success") or not d.get("new_contract"):
            raise VastError(f"Vast did not rent offer {offer_id}: {_short(json.dumps(d) if d else '')}")
        return int(d["new_contract"])

    def instances(self) -> list[dict]:
        """Every instance in the account. Raises VastError when the answer is unknown (never returns 'empty' then)."""
        out: list[dict] = []
        params: dict[str, Any] = {"select_filters": "{}", "order_by": json.dumps([{"col": "id", "dir": "asc"}]),
                                  "limit": 25}
        for _ in range(200):
            d = self._req("GET", "/api/v1/instances/", params=params)
            if not isinstance(d, dict) or not isinstance(d.get("instances"), list):
                raise VastError("Vast instance list has an unknown shape")
            out.extend(i for i in d["instances"] if isinstance(i, dict))
            token = d.get("next_token")
            if not token:
                return out
            params["after_token"] = token
        raise VastError("Vast instance list did not end after 200 pages")

    def instance(self, iid: int) -> dict | None:
        try:
            d = self._req("GET", f"/api/v0/instances/{int(iid)}/", params={"owner": "me"})
        except VastError as e:
            if "HTTP 404" in str(e):
                return None
            raise
        inst = d.get("instances") if isinstance(d, dict) else None
        if isinstance(inst, list):
            inst = inst[0] if inst else None
        return inst if isinstance(inst, dict) and inst.get("id") is not None else None

    def destroy(self, iid: int) -> None:
        try:
            self._req("DELETE", f"/api/v0/instances/{int(iid)}/", body={})
        except VastError as e:
            if "HTTP 404" not in str(e):
                raise

    def credit(self) -> float | None:
        """Only the field `credit`. The rest of the user record (it holds account data) is dropped right away."""
        d = self._req("GET", "/api/v0/users/current/")
        v = d.get("credit") if isinstance(d, dict) else None
        del d
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    # ---- SSH keys ------------------------------------------------------------------------------------------------
    def ssh_keys(self) -> list[str]:
        d = self._req("GET", "/api/v0/ssh/")
        rows = d if isinstance(d, list) else (d.get("ssh_keys") or d.get("keys") or []) if isinstance(d, dict) else []
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append(str(r.get("public_key") or r.get("ssh_key") or r.get("key") or ""))
            elif isinstance(r, str):
                out.append(r)
        return out

    def add_ssh_key(self, public_key: str) -> None:
        self._req("POST", "/api/v0/ssh/", body={"ssh_key": public_key.strip()})

    def attach_ssh_key(self, iid: int, public_key: str) -> None:
        self._req("POST", f"/api/v0/instances/{int(iid)}/ssh/", body={"ssh_key": public_key.strip()})


def _short(text: str, n: int = 160) -> str:
    from .scrub import scrub_text
    return scrub_text(" ".join((text or "").split()))[:n]


def from_env() -> Vast:
    """The configured provider. Raises MissingKey (exit 4) without a key."""
    p = str(settings.get("provider") or "vast")
    if p != "vast":
        raise ComputeError(f"provider {p!r} is planned, not built; use provider = \"vast\"")
    return Vast()


# ---- helpers on instance records -----------------------------------------------------------------------------------
def address(inst: dict) -> tuple[str, int] | None:
    """(host, port) for SSH: the direct port when the host maps 22/tcp, else the Vast SSH proxy."""
    ports = inst.get("ports") or {}
    p = ports.get("22/tcp") if isinstance(ports, dict) else None
    ip = str(inst.get("public_ipaddr") or "").strip()
    if ip and isinstance(p, list) and p and isinstance(p[0], dict) and p[0].get("HostPort"):
        try:
            return ip, int(p[0]["HostPort"])
        except (TypeError, ValueError):
            pass
    if inst.get("ssh_host") and inst.get("ssh_port"):
        try:
            return str(inst["ssh_host"]), int(inst["ssh_port"])
        except (TypeError, ValueError):
            return None
    return None


PULL_ERRORS = ("pull access denied", "manifest unknown", "error pulling", "failed to pull", "repository does not exist",
               "unauthorized: authentication required", "no such image")


def image_failed(inst: dict) -> bool:
    msg = str(inst.get("status_msg") or "").lower()
    return any(e in msg for e in PULL_ERRORS)
