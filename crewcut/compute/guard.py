"""The local guard (delete-safeguard 3 of 3). It never touches a machine without our label.

`sweep()` once:
  1. every open session: machines past their deadline go, a session at its cap stops, a session whose process is
     gone is closed (its machines destroyed, proof written);
  2. every machine with our label: destroyed when it has no rental record, its deadline (plus grace) passed, its
     session is not live, or an earlier destroy was not confirmed;
  3. rental rows whose machine vanished (the watchdog or the host ended it) are booked until then.
The server calls `start_background()` at startup: a daemon thread that sweeps at once and then every few minutes.
`crewcut compute guard` runs it once (`--once`) or in a loop.
"""

from __future__ import annotations

import json
import threading

from .. import db, events
from . import rentals, settings, state, vast
from .errors import ComputeError
from .session import Session

_thread: threading.Thread | None = None
_halt = threading.Event()


def _adopt(inst: dict, label: str) -> int:
    """A labelled machine without a rental row (for example after a lost database): book it from its start."""
    t = state.now()
    started = float(inst.get("start_date") or t)
    return db.insert("rentals", provider="vast", instance=str(int(inst["id"])), label=label, episode=None, job=None,
                     price_per_hour=float(inst.get("dph_total") or 0), started=state.iso(started),
                     deadline=state.iso(t), status="starting",
                     detail=json.dumps({"adopted": True, "gpu": inst.get("gpu_name")}))


def sweep(provider=None) -> dict:
    """One pass. Returns {ok, ours, foreign, destroyed: [instance ids], kept, booked_gone, proof} or a skip/error."""
    if provider is None and not vast.has_key():
        return {"ok": True, "skipped": "no Vast key: nothing can be rented, nothing to guard"}
    prov = provider or vast.from_env()
    label = state.label()
    now = state.now()
    grace = rentals.grace_s()
    destroyed: list[int] = []

    # 1. sessions
    state.prune_sessions()
    for rec in state.open_sessions():
        try:
            s = Session.attach(rec["id"], provider=prov)
            before = {r["id"] for r in s.live_rows()}
            if not rec.get("detached") and not state.session_live(rec["id"]):
                s.close("the process that rented it is gone")
            else:
                s.check()
                if rec.get("detached") and rec.get("rentals") and not s.live_rows() and not s.closed:
                    s.close("all machines ended")
            after = {r["id"] for r in s.live_rows()}
            for rid in before - after:
                row = rentals.get(rid)
                if row and row.get("instance"):
                    destroyed.append(int(row["instance"]))
        except ComputeError as e:
            events.emit("log", episode=rec.get("episode"), text=f"compute guard: session {rec.get('id')}: {e}")

    # 2. labelled machines
    try:
        alle = prov.instances()
    except ComputeError as e:
        return {"ok": False, "error": f"Vast instance list not readable ({e}); nothing was changed"}
    ids = {int(i["id"]) for i in alle if i.get("id") is not None}
    ours = {int(i["id"]): i for i in alle if i.get("id") is not None and (i.get("label") or "") == label}
    creating = any(r["status"] == "creating" and now - rentals.started_ts(r) < 300 for r in rentals.live(label))
    kept = []
    for iid, inst in ours.items():
        row = rentals.by_instance(iid)
        reason = None
        if row is None:
            if creating:
                kept.append(iid)  # a rent call may be writing its row right now; the next sweep decides
                continue
            reason = "labelled machine without a rental record"
            row = rentals.get(_adopt(inst, label))
        elif row["status"] in ("destroyed", "failed"):
            reason = "booked as destroyed but still listed"
        elif row["status"] == "lost":
            reason = "an earlier destroy was not confirmed"
        elif now > rentals.deadline_ts(row) + grace:
            reason = "deadline passed"
        elif not state.session_live(rentals.detail(row).get("session")):
            reason = "no live session"
        if reason is None:
            kept.append(iid)
            continue
        if row["status"] in ("destroyed", "failed"):
            try:
                prov.destroy(iid)
            except ComputeError:
                pass
        else:
            rentals.destroy(row["id"], f"guard: {reason}", prov)
        destroyed.append(iid)
        events.emit("log", episode=row.get("episode"), text=f"compute guard destroyed rented GPU {iid}: {reason}")

    # 3. rows whose machine is gone
    booked_gone = []
    for row in rentals.live(label):
        if row.get("instance") and int(row["instance"]) not in ids and now - rentals.started_ts(row) > 120:
            rentals.book(row["id"], "machine gone (watchdog or host)", end=min(now, rentals.deadline_ts(row) + grace))
            booked_gone.append(int(row["instance"]))

    out = {"ok": True, "label": label, "ours": len(ours), "foreign": len(alle) - len(ours),
           "destroyed": sorted(set(destroyed)), "kept": sorted(kept), "booked_gone": booked_gone}
    if destroyed:
        n, text = rentals.proof(prov, label)
        out["proof"] = text
        out["left"] = n
    return out


def run_forever(every: float | None = None) -> None:
    every = every or settings.num("limits.guard_every_minutes") * 60
    while True:
        try:
            r = sweep()
            if r.get("destroyed") or r.get("error"):
                events.emit("log", text=f"compute guard: {r}")
        except Exception as e:  # the guard must keep running
            events.emit("log", text=f"compute guard failed: {type(e).__name__}")
        if _halt.wait(every):
            return


def start_background(every: float | None = None) -> threading.Thread:
    """Start the guard thread once per process (the server calls this at startup). It sweeps at once."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread
    _halt.clear()
    _thread = threading.Thread(target=run_forever, args=(every,), name="crewcut-compute-guard", daemon=True)
    _thread.start()
    return _thread


def stop_background(timeout: float = 5) -> None:
    _halt.set()
    if _thread is not None:
        _thread.join(timeout=timeout)
