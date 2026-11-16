"""The job queue. Jobs live in SQLite; a worker thread in the server starts them.

Agent jobs run a crew member through the engine. At most `engine.max_parallel_agents` agents run at once. Heavy tools
take the heavy lane themselves (lanes.py), so a render never competes with another render.
"""

from __future__ import annotations

import os
import threading
import time
import traceback

from .. import config, db, engines, events, paths, team
from . import prompts


def add(episode: str | None, identity: str, step: str | None, task: str, kind: str = "agent", heavy: bool = False,
        parent: int | None = None, data: dict | None = None) -> int:
    if team.get(identity) is None:
        raise ValueError(f"unknown crew member {identity}")
    jid = db.insert("jobs", episode=episode, step=step, identity=identity, kind=kind, task=task, heavy=int(heavy),
                    status="queued", doing="Queued", created=db.now(), parent=parent, data=data or {})
    events.emit("activity", episode=episode, identity=identity, text="queued", data=job_view(get(jid)))
    return jid


def get(jid: int) -> dict | None:
    return db.get("jobs", jid)


def set_doing(jid: int, doing: str, progress: float | None = None) -> None:
    vals = {"doing": doing[:200]}
    if progress is not None:
        vals["progress"] = max(0.0, min(1.0, float(progress)))
    db.update("jobs", jid, **vals)
    j = get(jid)
    events.emit("activity", episode=j["episode"], identity=j["identity"], text=doing, data=job_view(j))


def job_view(j: dict) -> dict:
    started = db.parse_time(j.get("started"))
    ended = db.parse_time(j.get("ended"))
    secs = int((ended or time.time()) - started) if started else 0
    return {"job": j["id"], "episode": j["episode"], "identity": j["identity"], "step": j["step"],
            "doing": j.get("doing") or "", "progress": j.get("progress"), "status": j["status"],
            "started": j.get("started"), "ended": j.get("ended"), "seconds": secs,
            "cost_usd": round(float(j.get("cost_usd") or 0), 4), "equiv_usd": round(float(j.get("equiv_usd") or 0), 4)}


def active(episode: str | None = None) -> list[dict]:
    q = "SELECT * FROM jobs WHERE status IN ('queued', 'running', 'waiting')"
    args: list = []
    if episode:
        q += " AND episode = ?"
        args.append(episode)
    with db.conn() as c:
        return [job_view(j) for j in db.rows(c.execute(q + " ORDER BY id", args))]


def done_today(limit: int = 12) -> list[dict]:
    today = db.now()[:10]
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT * FROM jobs WHERE status IN ('done', 'failed') AND substr(ended, 1, 10) = ? "
                               "ORDER BY id DESC LIMIT ?", (today, limit)))
    return [job_view(j) for j in rs]


def cancel(jid: int) -> None:
    db.update("jobs", jid, status="cancelled", ended=db.now(), doing="Cancelled")
    _stops.setdefault(jid, threading.Event()).set()


_stops: dict[int, threading.Event] = {}


def _run_agent(j: dict) -> None:
    from . import flow
    ident = team.get(j["identity"])
    eng = engines.current()
    models = engines.models(eng.name)
    model = models["plan"] if ident.get("model") == "plan" else models["work"]
    cwd = paths.episode_dir(j["episode"]) if j["episode"] else paths.studio_root()
    cwd.mkdir(parents=True, exist_ok=True)
    log_path = paths.logs_dir() / f"job-{j['id']}.log"
    data = dict(j.get("data") or {})
    resume = data.get("resume") or {}
    db.update("jobs", j["id"], status="running", started=db.now(), doing="Starting", log_path=str(log_path))
    events.emit("activity", episode=j["episode"], identity=j["identity"], data=job_view(get(j["id"])))
    env = {"CREWCUT_STUDIO": str(paths.studio_root()), "CREWCUT_APP": str(paths.app_root()),
           "CREWCUT_EPISODE": j["episode"] or "", "CREWCUT_IDENTITY": j["identity"], "CREWCUT_JOB": str(j["id"])}

    def on_event(ev: engines.Event) -> None:
        if ev.kind in ("tool", "step"):
            cur = get(j["id"])
            if not cur or cur["status"] != "running" or (cur.get("doing") or "").startswith("Waiting"):
                return
            # a plan step always shows; a single tool call only fills in until the crew member says what it does
            if ev.kind == "step" or (cur.get("doing") or "") in ("Starting", ""):
                set_doing(j["id"], ev.text)
        elif ev.kind == "session":
            data.update(engine=eng.name, session=ev.data.get("session"))
            db.update("jobs", j["id"], data=data)
        elif ev.kind == "usage":
            data["usage"] = ev.data.get("usage")
            db.update("jobs", j["id"], data=data)

    stop = _stops.setdefault(j["id"], threading.Event())
    cfg = config.load("crewcut").get("engine", {})
    task = engines.Task(prompt=j["task"], system=prompts.system_prompt(ident, j["episode"], j["step"]), cwd=cwd,
                        env=env, model=model,
                        resume=resume.get("session") if resume.get("engine") == eng.name else None,
                        timeout_s=int(cfg.get("agent_timeout_minutes", 60)) * 60, log_path=log_path,
                        extra_dirs=[str(paths.app_root())])
    res = eng.run(task, on_event=on_event, stop=stop)
    cur = get(j["id"])
    if cur and cur["status"] == "cancelled":
        return
    status = "done" if res.ok else "failed"
    if cur and cur["status"] == "waiting" and res.ok:
        status = "waiting"  # it proposed a card and stopped; the conductor wakes the owner on the answer
    data.update(engine=eng.name, session=res.session or data.get("session"), usage=res.usage or data.get("usage"))
    db.update("jobs", j["id"], status=status, ended=db.now(), equiv_usd=res.cost_usd, result=res.text[:4000],
              data=data, doing=("Waiting for your answer" if status == "waiting" else
                                "Done" if res.ok else f"Stopped: {res.error[:160]}"))
    events.emit("activity", episode=j["episode"], identity=j["identity"], data=job_view(get(j["id"])))
    flow.after_job(get(j["id"]), res)


def _run_tool(j: dict) -> None:
    import shlex
    import subprocess
    log_path = paths.logs_dir() / f"job-{j['id']}.log"
    db.update("jobs", j["id"], status="running", started=db.now(), doing=j["task"][:200], log_path=str(log_path))
    env = {**os.environ, "CREWCUT_EPISODE": j["episode"] or "", "CREWCUT_IDENTITY": j["identity"],
           "CREWCUT_JOB": str(j["id"])}
    with open(log_path, "a", encoding="utf-8") as log:
        code = subprocess.call(["crewcut", *shlex.split(j["task"])], stdout=log, stderr=subprocess.STDOUT, env=env,
                               cwd=str(paths.studio_root()))
    db.update("jobs", j["id"], status="done" if code == 0 else ("waiting" if code == 3 else "failed"), ended=db.now(),
              doing="Done" if code == 0 else f"Exit {code}")
    events.emit("activity", episode=j["episode"], identity=j["identity"], data=job_view(get(j["id"])))


def _start(j: dict) -> None:
    try:
        (_run_agent if j["kind"] == "agent" else _run_tool)(j)
    except Exception as e:  # noqa: BLE001 - a crashed job must never take the worker down
        db.update("jobs", j["id"], status="failed", ended=db.now(), doing=f"Crashed: {type(e).__name__}: {e}"[:200])
        with open(paths.logs_dir() / f"job-{j['id']}.log", "a", encoding="utf-8") as log:
            log.write(traceback.format_exc())
        events.emit("activity", episode=j["episode"], identity=j["identity"], data=job_view(get(j["id"])))


class Worker:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.threads: dict[int, threading.Thread] = {}

    def recover(self) -> None:
        """After a restart, jobs that were running are interrupted; say so instead of pretending."""
        with db.conn() as c:
            c.execute("UPDATE jobs SET status = 'failed', ended = ?, doing = 'Interrupted by a restart' "
                      "WHERE status = 'running'", (db.now(),))

    def tick(self) -> None:
        self.threads = {k: t for k, t in self.threads.items() if t.is_alive()}
        limit = int(config.get("crewcut", "engine.max_parallel_agents", 3))
        free = limit - len(self.threads)
        if free <= 0:
            return
        with db.conn() as c:
            queued = db.rows(c.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT ?", (free,)))
        for j in queued:
            db.update("jobs", j["id"], status="running", started=db.now(), doing="Starting")
            t = threading.Thread(target=_start, args=(get(j["id"]),), daemon=True, name=f"job-{j['id']}")
            self.threads[j["id"]] = t
            t.start()

    def run_forever(self, every: float = 1.0) -> None:
        self.recover()
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            self.stop.wait(every)

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, daemon=True, name="crewcut-worker")
        t.start()
        return t
