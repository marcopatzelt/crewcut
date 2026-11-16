"""The rentals table, money per machine, destroying with proof, and choosing offers. Shared by sessions and the guard.

Statuses: creating (row written before the rent call), starting, ready, destroyed, failed (never rented), lost (a
destroy that the API did not confirm; the guard keeps trying).
"""

from __future__ import annotations

import json

from .. import db, events, ledger
from . import settings, state, vast
from .errors import ComputeError

LIVE = ("creating", "starting", "ready", "lost")


# ---- rows ----------------------------------------------------------------------------------------------------------
def detail(row: dict) -> dict:
    try:
        d = json.loads(row.get("detail") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def set_detail(rid: int, **values) -> None:
    row = db.get("rentals", rid) or {}
    d = detail(row)
    d.update(values)
    db.update("rentals", rid, detail=json.dumps(d, ensure_ascii=False))


def get(rid: int) -> dict | None:
    return db.get("rentals", int(rid))


def by_instance(iid: int | str) -> dict | None:
    with db.conn() as c:
        return db.row(c.execute("SELECT * FROM rentals WHERE instance = ? ORDER BY id DESC LIMIT 1",
                                (str(iid),)).fetchone())


def live(label: str | None = None) -> list[dict]:
    q = f"SELECT * FROM rentals WHERE status IN ({','.join('?' for _ in LIVE)})"
    args: list = list(LIVE)
    if label:
        q += " AND label = ?"
        args.append(label)
    with db.conn() as c:
        return db.rows(c.execute(q + " ORDER BY id", args))


def started_ts(row: dict) -> float:
    return db.parse_time(row.get("started")) or state.now()


def deadline_ts(row: dict) -> float:
    return db.parse_time(row.get("deadline")) or state.now()


def ended_ts(row: dict) -> float | None:
    return db.parse_time(row.get("ended"))


# ---- money ---------------------------------------------------------------------------------------------------------
def grace_s() -> float:
    return settings.num("limits.guard_grace_minutes") * 60


def cost_so_far(row: dict, at: float | None = None) -> float:
    """Price times time rented (from the rent call until destroyed, or until now)."""
    if row.get("status") == "failed" or not row.get("instance"):
        return 0.0
    end = ended_ts(row) or (at if at is not None else state.now())
    return max(0.0, end - started_ts(row)) / 3600 * float(row.get("price_per_hour") or 0)


def worst_total(row: dict) -> float:
    """What this machine costs at most: until its deadline plus the guard's grace."""
    return max(0.0, deadline_ts(row) + grace_s() - started_ts(row)) / 3600 * float(row.get("price_per_hour") or 0)


def worst_remaining(row: dict) -> float:
    return max(0.0, deadline_ts(row) + grace_s() - state.now()) / 3600 * float(row.get("price_per_hour") or 0)


def reserved(episode: str | None = None, *, remaining: bool = False) -> float:
    """Worst case of the machines still running (not yet in the cost book). For one episode, or for all."""
    rows = [r for r in live() if episode is None or r.get("episode") == episode]
    return round(sum(worst_remaining(r) if remaining else worst_total(r) for r in rows), 4)


# ---- destroy -------------------------------------------------------------------------------------------------------
def _gone(prov, iid: int) -> bool | None:
    try:
        return all(int(i.get("id", -1)) != int(iid) for i in prov.instances())
    except ComputeError:
        return None


def destroy(rid: int, reason: str, prov=None, *, tries: int = 4) -> float | None:
    """Destroy one rented machine, confirm it is gone, book its cost. Returns the cost, or None when the API did not
    confirm (the row is then 'lost' and the guard tries again)."""
    row = get(rid)
    if row is None or row["status"] in ("destroyed", "failed"):
        return 0.0
    if not row.get("instance"):
        db.update("rentals", rid, status="failed", ended=state.iso(state.now()))
        return 0.0
    prov = prov or vast.from_env()
    iid = int(row["instance"])
    gone = False
    for _ in range(tries):
        try:
            prov.destroy(iid)
        except ComputeError:
            pass
        for _ in range(10):
            g = _gone(prov, iid)
            if g:
                gone = True
                break
            state.sleep(6)
        if gone:
            break
    if not gone:
        db.update("rentals", rid, status="lost")
        set_detail(rid, last_reason=reason)
        events.emit("log", episode=row.get("episode"),
                    text=f"Rented GPU {iid} is still there after {tries} delete calls. The guard keeps trying.")
        return None
    return book(rid, reason)


def book(rid: int, reason: str, end: float | None = None) -> float:
    """Mark a machine destroyed and write its cost into the cost book (once)."""
    with state.locked():
        row = get(rid)
        if row is None or row["status"] in ("destroyed", "failed"):
            return 0.0
        end = state.now() if end is None else end
        db.update("rentals", rid, status="destroyed", ended=state.iso(end))
        set_detail(rid, end_reason=reason)
        row = get(rid)
    cost = round(cost_so_far(row), 4)
    d = detail(row)
    minutes = max(0.0, (ended_ts(row) or end) - started_ts(row)) / 60
    ledger.add("gpu", cost, f"Rented GPU ({d.get('gpu') or 'GPU'}) at ${float(row['price_per_hour'] or 0):.3f}/h for "
               f"{minutes:.0f} min, destroyed: {reason}", episode=row.get("episode"), step=d.get("step"),
               ref=f"vast:{row['instance']}")
    text = f"{d.get('name') or 'Rented GPU'}: destroyed after {minutes:.0f} min, ${cost:.2f} ({reason})"
    events.emit("activity", episode=row.get("episode"), identity=d.get("identity"), text=text,
                data={"job": row.get("job"), "step": d.get("step"), "doing": text, "status": "done",
                      "source": "compute", "rental": rid})
    return cost


def proof(prov, label: str, instance_ids: list[int] | None = None) -> tuple[int | None, str]:
    """Ask the API which machines carry our label. Returns (own machines left, proof sentence)."""
    try:
        alle = prov.instances()
    except ComputeError as e:
        return None, f"No proof: the Vast API did not answer ({e})."
    ours = [int(i["id"]) for i in alle if (i.get("label") or "") == label]
    foreign = len(alle) - len(ours)
    if instance_ids is not None:
        mine = [i for i in ours if i in set(instance_ids)]
        other = len(ours) - len(mine)
        text = (f"Proof: {plural(len(mine), 'own machine')} left from this session (Vast API, "
                f"{state.hhmm(state.now())}, label {label})")
        if other:
            text += f"; {plural(other, 'more Crewcut machine')} running for other sessions"
        n = len(mine)
    else:
        n = len(ours)
        text = f"Proof: {plural(n, 'own machine')} left (Vast API, {state.hhmm(state.now())}, label {label})"
        if ours:
            text += f": {', '.join(map(str, ours))}"
    if foreign:
        text += f"; {plural(foreign, 'other machine')} in the account, not touched"
    return n, text + "."


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---- offers --------------------------------------------------------------------------------------------------------
def search(prov) -> list[dict]:
    v = settings.get("vast") or {}
    return prov.search_offers(gpu_names=list(v.get("gpus") or []), max_price=float(v.get("max_price_per_hour", 0.8)),
                              regions=list(v.get("regions") or []), min_reliability=float(v.get("min_reliability", 0)),
                              min_inet_down=float(v.get("min_inet_down_mbps", 0)),
                              min_inet_up=float(v.get("min_inet_up_mbps", 0)), disk_gb=float(v.get("disk_gb", 40)),
                              verified=bool(v.get("verified", True)))


def usable(offers: list[dict], taken_ips: set[str] | None = None) -> list[dict]:
    """Filter and order offers: preferred GPU first, then price; one offer per host IP; never a host IP where a
    machine of this account already runs; no blocked host or machine; no host that leaves soon."""
    v = settings.get("vast") or {}
    pref = [str(g).replace("_", " ").lower() for g in v.get("gpus") or []]
    max_price = float(v.get("max_price_per_hour", 0.8))
    min_rel = float(v.get("min_reliability", 0))
    min_left = float(v.get("min_hours_left", 0)) * 3600
    taken = {t.strip() for t in taken_ips or set()}
    now = state.now()

    def rank(o):
        g = str(o.get("gpu_name") or "").replace("_", " ").lower()
        return (pref.index(g) if g in pref else len(pref), float(o.get("dph_total") or 99))

    seen: set[str] = set()
    out = []
    for o in sorted(offers, key=rank):
        ip = str(o.get("public_ipaddr") or "").strip()
        rel = o.get("reliability2", o.get("reliability"))
        end = o.get("end_date")
        if not ip or ip in seen or ip in taken or state.is_blocked(o):
            continue
        if float(o.get("dph_total") or 99) > max_price:
            continue
        if rel is not None and float(rel) < min_rel:
            continue
        if end and float(end) - now < min_left:
            continue
        seen.add(ip)
        out.append(o)
    return out


def taken_ips(prov) -> set[str]:
    return {str(i.get("public_ipaddr") or "").strip() for i in prov.instances()} - {""}


def live_prices(prov=None) -> list[float] | None:
    """Prices of the usable live offers, best first (cached a few minutes), or None without key or offers."""
    if not vast.has_key() and prov is None:
        return None
    cache = state.read_json("offers.json", {})
    ttl = settings.num("estimate.offers_cache_minutes") * 60
    if cache.get("at") and state.now() - float(cache["at"]) < ttl and cache.get("prices"):
        prices = [float(p) for p in cache["prices"]]
    else:
        try:
            prov = prov or vast.from_env()
            prices = [float(o["dph_total"]) for o in usable(search(prov)) if o.get("dph_total") is not None]
        except ComputeError:
            return None
        if not prices:
            return None
        state.write_json("offers.json", {"at": state.now(), "prices": prices[:64]})
    return prices
