"""`crewcut compute …`: estimate, rent, put, run, fetch, destroy, guard, ledger.

Exit codes: 0 ok, 1 error, 2 usage, 3 waiting for or refused by the user (card open, cap reached), 4 missing key.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from .. import ledger
from . import guard, rentals, state, vast
from .errors import ComputeError, MissingKey, NeedsApproval, Refused
from .estimate import estimate, local_is_fine
from .rentals import plural
from .scrub import scrub_text
from .session import Machine, Session


def _out(args, data: dict, text: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        print(text)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="crewcut compute", description="Rented GPUs (optional). See docs/compute.md.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("estimate", help="time here and on rented GPUs, price, and whether renting is worth it")
    p.add_argument("--kind", default="blender")
    p.add_argument("--frames", type=int, required=True)
    p.add_argument("--local-sec-per-frame", type=float)
    p.add_argument("--gpu-sec-per-frame", type=float)
    p.add_argument("--gpus", type=int)
    p.add_argument("--scene")
    p.add_argument("--episode")
    p.add_argument("--job")
    p.add_argument("--local-fine", action="store_true", help="the user said local is fine: no more suggestions in "
                                                                 "this episode (needs --episode)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("rent", help="rent GPUs for an episode (a spend card first, then within its budget)")
    p.add_argument("--episode", required=True)
    p.add_argument("--gpus", type=int, default=1)
    p.add_argument("--final", action="store_true", help="the final render of an approved scene: the only case for "
                                                         "more than one GPU; deleted right after")
    p.add_argument("--gpu", help="a GPU model the user asked for by name, e.g. \"RTX 5090\" (never chosen otherwise)")
    p.add_argument("--minutes", type=float, help="deadline per machine (default limits.default_max_minutes)")
    p.add_argument("--max-usd", type=float, help="cap of this session (default limits.session_cap_usd)")
    p.add_argument("--step", default="edit")
    p.add_argument("--purpose", default="")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("put", help="upload code, fonts and scene files to a machine")
    p.add_argument("machine", type=int)
    p.add_argument("paths", nargs="+", help="local files or folders, then the remote folder")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run", help="run a command on a machine: crewcut compute run <machine> -- <command>")
    p.add_argument("machine", type=int)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--doing", help="what the right column shows, e.g. rendering")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("fetch", help="fetch files from a machine (secrets are removed before they land)")
    p.add_argument("machine", type=int)
    p.add_argument("remote")
    p.add_argument("local")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("destroy", help="destroy one machine, or every machine with this studio's label")
    p.add_argument("machine", type=int, nargs="?")
    p.add_argument("--all-ours", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("guard", help="destroy our labelled machines without a live session or past their deadline")
    p.add_argument("--once", action="store_true")
    p.add_argument("--every", type=float, help="seconds between sweeps (default limits.guard_every_minutes)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("ledger", help="the cost book of rented GPUs and the machines running now")
    p.add_argument("--episode")
    p.add_argument("--json", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 2
    try:
        return _dispatch(args, command)
    except NeedsApproval as e:
        _out(args, {"ok": False, "waiting": True, "card": e.card_id, "reason": e.reason},
             f"Waiting for a yes on spend card {e.card_id}. Then run the same command again "
             f"(crewcut card wait {e.card_id}).")
        return 3
    except Refused as e:
        _out(args, {"ok": False, "refused": True, "reason": e.reason}, f"Refused: {e.reason}")
        return 3
    except MissingKey as e:
        _out(args, {"ok": False, "missing_key": True, "reason": str(e), "keys_page": vast.KEYS_PAGE}, str(e))
        return 4
    except (ComputeError, ValueError) as e:
        _out(args, {"ok": False, "error": scrub_text(str(e))}, f"Error: {scrub_text(str(e))}")
        return 1


def _machine(rid: int) -> Machine:
    row = rentals.get(rid)
    if row is None:
        raise ComputeError(f"no rented machine {rid}; see crewcut compute ledger")
    sid = rentals.detail(row).get("session")
    s = Session.attach(sid) if sid and state.get_session(sid) else None
    if s is not None:
        stopped = s.check()
        if stopped:
            raise Refused(stopped)
    return Machine(rid, s)


def _close_if_done(row: dict) -> str:
    sid = rentals.detail(row).get("session")
    if not sid or not state.get_session(sid):
        return ""
    s = Session.attach(sid)
    if s.detached and not s.closed and not s.live_rows():
        return s.close("all machines destroyed")
    return ""


def _dispatch(args, command: list[str]) -> int:
    c = args.cmd
    if c == "estimate":
        if args.local_fine:
            if not args.episode:
                raise ValueError("--local-fine needs --episode")
            local_is_fine(args.episode)
        e = estimate(args.kind, args.frames, args.local_sec_per_frame, args.gpus, scene=args.scene,
                     gpu_sec_per_frame=args.gpu_sec_per_frame, episode=args.episode, job=args.job)
        lines = [e["sentence"], f"Suggest renting: {'yes' if e['suggest_rent'] else 'no'} ({e['reason']}).",
                 f"Worst case on rented GPUs: ${e['rented_usd_worst']:.2f}. Price from {e['price_source']}."]
        if e["referral"]:
            lines.append(f"Link: {e['referral']['url']}  ({e['referral']['note']})")
        _out(args, e, "\n".join(lines))
        return 0

    if c == "rent":
        s = Session(args.episode, args.step, args.purpose, args.max_usd, detached=True, monitor=False).open()
        try:
            machines = s.rent(gpus=args.gpus, max_minutes=args.minutes, final=args.final, gpu=args.gpu)
        except BaseException:
            s.close("rent did not finish")
            raise
        rows = [{"machine": m.rental, "instance": m.instance, "gpu": m.gpu, "price_per_hour": m.price_per_hour,
                 "deadline": state.iso(m.deadline), "name": m.name} for m in machines]
        text = [f"Rented {len(machines)} GPU{'s' if len(machines) > 1 else ''} (session {s.id}, cap "
                f"${s.cap_usd:.2f}):"]
        text += [f"  machine {r['machine']}: {r['gpu']}, ${r['price_per_hour']:.2f}/h, deadline "
                 f"{state.hhmm(m.deadline)}" for r, m in zip(rows, machines, strict=True)]
        first = machines[0].rental
        text.append(f"Next: crewcut compute put {first} <files> /work/ | crewcut compute run {first} -- <command> | "
                    f"crewcut compute fetch {first} /work/out/ <folder> | crewcut compute destroy {first}")
        text.append("The guard destroys them at their deadline or when the cap is reached.")
        _out(args, {"ok": True, "session": s.id, "cap_usd": s.cap_usd, "machines": rows}, "\n".join(text))
        return 0

    if c == "put":
        if len(args.paths) < 2:
            raise ValueError("put needs at least one local path and the remote folder")
        *local, dest = args.paths
        n = _machine(args.machine).put([Path(p) for p in local], dest)
        _out(args, {"ok": True, "files": n, "dest": dest}, f"Uploaded {n} files to {dest}.")
        return 0

    if c == "run":
        if not command:
            raise ValueError("run needs a command after --")
        cmd = command[0] if len(command) == 1 else shlex.join(command)
        rc, out = _machine(args.machine).run(cmd, timeout=args.timeout, doing=args.doing)
        _out(args, {"ok": rc == 0, "exit": rc, "output": out}, out.rstrip() + ("" if rc == 0 else
                                                                                f"\n(remote exit code {rc})"))
        return 0 if rc == 0 else 1

    if c == "fetch":
        r = _machine(args.machine).get(args.remote, Path(args.local))
        text = f"Fetched {r['files']} files ({r['bytes'] / 1e6:.1f} MB) to {r['dest']}."
        if r["scrubbed"]:
            text += f" Removed secrets from {len(r['scrubbed'])} of them."
        _out(args, {"ok": True, **r}, text)
        return 0

    if c == "destroy":
        if args.all_ours:
            return _destroy_all(args)
        if args.machine is None:
            raise ValueError("name a machine or pass --all-ours")
        row = rentals.get(args.machine)
        if row is None:
            raise ComputeError(f"no rented machine {args.machine}")
        cost = rentals.destroy(args.machine, "destroyed by command")
        proof = _close_if_done(rentals.get(args.machine))
        if cost is None:
            _out(args, {"ok": False, "machine": args.machine}, f"Machine {args.machine} is still there after the "
                 "delete calls. The guard keeps trying; check again with crewcut compute destroy --all-ours.")
            return 1
        _out(args, {"ok": True, "machine": args.machine, "cost_usd": cost, "proof": proof},
             f"Destroyed machine {args.machine} (${cost:.2f})." + (f" {proof}" if proof else ""))
        return 0

    if c == "guard":
        if args.once:
            r = guard.sweep()
            _out(args, r, _guard_text(r))
            return 0 if r.get("ok") else 1
        print("Compute guard running (Ctrl+C stops it).", flush=True)
        every = args.every or None
        try:
            while True:
                r = guard.sweep()
                print(_guard_text(r), flush=True)
                state.sleep(every or 180)
        except KeyboardInterrupt:
            return 0

    if c == "ledger":
        return _ledger(args)
    raise ValueError(f"unknown command {c}")


def _guard_text(r: dict) -> str:
    if r.get("skipped"):
        return f"Guard: skipped ({r['skipped']})."
    if not r.get("ok"):
        return f"Guard: {r.get('error')}"
    t = (f"Guard {state.hhmm(state.now())}: {plural(r['ours'], 'own machine')}, "
         f"{plural(r['foreign'], 'other machine')} in the account (not touched). Destroyed: {len(r['destroyed'])}.")
    if r.get("proof"):
        t += " " + r["proof"]
    return t


def _destroy_all(args) -> int:
    prov = vast.from_env()
    label = state.label()
    for row in rentals.live(label):
        rentals.destroy(row["id"], "destroy --all-ours", prov)
    for inst in prov.instances():
        if (inst.get("label") or "") == label and rentals.by_instance(inst["id"]) is None:
            prov.destroy(int(inst["id"]))
    for rec in state.open_sessions():
        if rec.get("detached"):
            s = Session.attach(rec["id"], provider=prov)
            if not s.live_rows():
                s.close("destroy --all-ours")
    n, text = rentals.proof(prov, label)
    ledger.add("gpu", 0.0, text, ref="proof:all-ours")
    _out(args, {"ok": n == 0, "left": n, "proof": text}, text)
    return 0 if n == 0 else 1


def _ledger(args) -> int:
    rows = [r for r in ledger.rows(args.episode) if r["kind"] == "gpu"]
    t = ledger.totals(args.episode)
    running = []
    for r in rentals.live():
        if args.episode and r.get("episode") != args.episode:
            continue
        running.append({"machine": r["id"], "instance": r.get("instance"), "episode": r.get("episode"),
                        "gpu": rentals.detail(r).get("gpu"), "price_per_hour": r.get("price_per_hour"),
                        "so_far_usd": round(rentals.cost_so_far(r), 4), "deadline": r.get("deadline"),
                        "status": r["status"]})
    lines = [f"Cost book, rented GPUs{' for ' + args.episode if args.episode else ''}:"]
    lines += [f"  {r['at']}  ${r['amount_usd']:.2f}  {r['detail']}" for r in rows] or ["  (nothing yet)"]
    total = f"Total: today ${t['today_usd']:.2f} | month ${t['month_usd']:.2f} of ${t['cap_month_usd']:.2f}"
    if args.episode:
        total = f"Total: episode ${t.get('episode_usd', 0):.2f} | " + total[7:]
    lines.append(total)
    for r in running:
        lines.append(f"Running now: machine {r['machine']} ({r['gpu']}, ${float(r['price_per_hour'] or 0):.2f}/h, "
                     f"${r['so_far_usd']:.2f} so far, deadline {r['deadline']}, {r['status']})")
    _out(args, {"rows": rows, "totals": t, "running": running}, "\n".join(lines))
    return 0
