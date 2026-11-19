"""A compute session: rent machines, use them, destroy them, book the cost, prove that none is left.

    with compute.session(episode="003-x", step="edit", purpose="3D scenes", cap_usd=1.5) as s:
        machines = s.rent(gpus=2, max_minutes=60)   # NeedsApproval(card_id) while the spend card is open
        m = machines[0]
        m.put([Path("scene.py")], "/work/")
        rc, out = m.run("blender -b ...", timeout=600, doing="rendering")
        m.get("/work/out/", Path("render/"))
    # leaving the block destroys every machine of the session, books the cost and records the proof

Three delete safeguards per machine: (1) the session (leaving the block, the cap, the deadline), (2) the watchdog on
the machine (Vast onstart hook, instance key), (3) the local guard (`guard.sweep`, every few minutes in the server).

The CLI uses detached sessions: `crewcut compute rent` leaves the machines running for later `run` / `fetch` calls;
the cap and the deadlines are then enforced by every CLI call and by the guard.

`picture=` (graphics behind the speaker only): the session may upload the picture of named shots, and only after a yes
on a spend card that says so in plain words (see privacy.py). `blender=False` skips the Blender install in the setup.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import approvals, db, events, ledger, paths
from . import privacy, remote, rentals, scrub, settings, ssh, state, vast
from .errors import ComputeError, NeedsApproval, NoMachine, Refused

BILLING_PAGE = "https://cloud.vast.ai/billing/"
MIN_USEFUL_MINUTES = 15  # an approved budget smaller than this much renting time is not used up silently


def _say(episode: str | None, identity: str | None, text: str) -> None:
    """A line in the episode's main chat (or the log without an episode)."""
    if not episode:
        events.emit("log", identity=identity, text=text)
        return
    at = db.now()
    author = identity or "showrunner"
    mid = db.insert("messages", at=at, episode=episode, author=author, text=text)
    events.emit("message", episode=episode, identity=identity, text=text,
                data={"id": mid, "at": at, "author": author, "text": text, "card": None})


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def picture_sentence(picture: dict) -> str:
    """The plain words on the spend card when a session sends the picture of shots (no sound) to the rented machine."""
    files = list(picture.get("files") or [])
    ids = [str(f.get("shot") or "?") for f in files]
    secs = sum(float(f.get("seconds") or 0) for f in files)
    which = f"shot {ids[0]}" if len(ids) == 1 else f"{len(ids)} shots ({', '.join(ids)})"
    why = str(picture.get("why") or "to separate the speaker from the background")
    return (f"The picture of {which}, {secs:.1f} s, without sound, goes to the rented machine {why}; it is deleted "
            "with the machine. Nothing else from the recording goes up.")


def _picture_files(picture: dict | None) -> dict[str, dict]:
    return {str(f["sha256"]): f for f in (picture or {}).get("files") or [] if f.get("sha256")}


def _card_pictures(card: dict) -> set[str]:
    """sha256 of the shot pictures an accepted spend card allows: only when its text says so in plain words."""
    pic = (card.get("data") or {}).get("picture") or {}
    sentence = str(pic.get("sentence") or "")
    if card.get("kind") != "spend" or card.get("status") != "accepted" or not sentence or \
            sentence not in str(card.get("body") or ""):
        return set()
    return set(_picture_files(pic))


class Machine:
    """One rented machine, ready (it passed SSH, the upload probe and the setup)."""

    def __init__(self, rental_id: int, session: Session | None = None):
        row = rentals.get(rental_id)
        if row is None or not row.get("instance"):
            raise ComputeError(f"no rented machine {rental_id}")
        d = rentals.detail(row)
        self.rental = int(rental_id)
        self.instance = int(row["instance"])
        self.host = str(d.get("host") or "")
        self.port = int(d.get("port") or 0)
        self.gpu = d.get("gpu") or "GPU"
        self.price_per_hour = float(row.get("price_per_hour") or 0)
        self.started = rentals.started_ts(row)
        self.deadline = rentals.deadline_ts(row)
        self.name = d.get("name") or f"Rented GPU {rental_id}"
        self._session = session

    def __repr__(self) -> str:
        return f"<Machine {self.rental} vast:{self.instance} {self.gpu} ${self.price_per_hour:.3f}/h>"

    def _check(self) -> None:
        if self._session is not None:
            stopped = self._session.check()
            if stopped:
                raise Refused(stopped)
        row = rentals.get(self.rental)
        if row is None or row["status"] != "ready":
            raise Refused(f"{self.name} is {row['status'] if row else 'gone'}; rent a new one")
        if not (self.host and self.port):
            raise ComputeError(f"{self.name} has no SSH address")

    def _doing(self, text: str) -> None:
        if self._session is not None:
            self._session.doing(f"{self.name}: {text}", rental=self.rental)

    def _after(self) -> None:
        if self._session is not None and self._session.stopped:
            raise Refused(self._session.stopped)

    def put(self, sources: list[Path | str], dest: str = "/work/", timeout: float = 900) -> int:
        """Upload code, fonts and scene files (rsync over SSH). Recordings, keys and studio state are refused."""
        self._check()
        srcs = [Path(s) for s in sources]
        n = privacy.check_upload(srcs, self._session.picture_ok() if self._session is not None else ())
        self._doing("uploading the shot's picture" if any(p.suffix.lower() in privacy.RAW_MEDIA for p in srcs)
                    else "uploading code")
        state.touch(self.rental, busy=True)
        try:
            rc, _, err = ssh.run(ssh.rsync_up_argv(srcs, self.host, self.port, self.instance, dest), timeout)
        finally:
            state.touch(self.rental, busy=False)
        self._after()
        if rc != 0:
            raise ComputeError(f"upload to {self.name} failed (rsync {rc}): {scrub.scrub_text(err).strip()[-160:]}")
        return n

    def run(self, command: str, timeout: float = 600, doing: str | None = None) -> tuple[int, str]:
        """Run a command over SSH. Returns (exit code, output with secrets removed)."""
        self._check()
        self._doing(doing or "running a command")
        state.touch(self.rental, busy=True)
        try:
            rc, out, err = ssh.run(ssh.ssh_argv(self.host, self.port, self.instance, command), timeout)
        finally:
            state.touch(self.rental, busy=False)
        self._after()
        return rc, scrub.scrub_text(out + err)

    def get(self, remote_path: str, local: Path | str, timeout: float = 1800) -> dict:
        """Fetch files (rsync). They land in a temporary folder, are scanned for secrets, then copied to `local`."""
        self._check()
        self._doing("fetching results")
        local = Path(local)
        tmp = Path(tempfile.mkdtemp(prefix="crewcut-fetch-"))
        try:
            rc, _, err = ssh.run(ssh.rsync_down_argv(self.host, self.port, self.instance, remote_path, tmp), timeout)
            self._after()
            if rc not in (0, 23, 24):
                raise ComputeError(f"fetch from {self.name} failed (rsync {rc}): "
                                   f"{scrub.scrub_text(err).strip()[-160:]}")
            changed = scrub.scrub_dir(tmp)
            files = [p for p in tmp.rglob("*") if p.is_file()]
            size = sum(p.stat().st_size for p in files)
            local.mkdir(parents=True, exist_ok=True)
            shutil.copytree(tmp, local, dirs_exist_ok=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if changed:
            text = (f"Removed secrets from {_plural(len(changed), 'fetched file')} before they reached the studio: "
                    f"{', '.join(changed[:5])}{' …' if len(changed) > 5 else ''}.")
            ep = self._session.episode if self._session else None
            _say(ep, self._session.identity if self._session else None, text)
        return {"files": len(files), "bytes": size, "scrubbed": changed, "dest": str(local), "partial": rc != 0}

    def destroy(self, reason: str = "done") -> float | None:
        prov = self._session.provider() if self._session else None
        return rentals.destroy(self.rental, reason, prov)


class Session:
    def __init__(self, episode: str | None, step: str | None = None, purpose: str = "", cap_usd: float | None = None,
                 *, identity: str | None = None, job: int | str | None = None, provider=None, detached: bool = False,
                 monitor: bool = True, sid: str | None = None, picture: dict | None = None, blender: bool = True):
        self.episode = episode
        self.step = step
        self.purpose = purpose or "rented GPU work"
        self.cap_usd = float(cap_usd) if cap_usd is not None else settings.num("limits.session_cap_usd")
        if self.cap_usd <= 0:
            raise ValueError("cap_usd must be above 0")
        self.identity = identity or os.environ.get("CREWCUT_IDENTITY") or None
        env_job = os.environ.get("CREWCUT_JOB", "")
        self.job = int(job) if job not in (None, "") else (int(env_job) if env_job.isdigit() else None)
        self.detached = detached
        self.id = sid or secrets.token_hex(6)
        self.label = state.label()
        self.stopped: str | None = None
        self.closed = False
        self.proof_text = ""
        self._prov = provider
        self._own = sid is None          # attached sessions never beat another process's heartbeat
        self._monitor_on = monitor and not detached
        self._lock = threading.RLock()
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None
        self._pub = ""
        self.picture = picture if picture and _picture_files(picture) else None
        self.blender = bool(blender)
        if picture and self.picture is None:
            raise ValueError("picture= needs files with a sha256 each")

    # ---- lifecycle -----------------------------------------------------------------------------------------------
    @classmethod
    def attach(cls, sid: str, provider=None) -> Session:
        """Rebuild a session from its record (CLI calls and the guard)."""
        rec = state.get_session(sid)
        if rec is None:
            raise ComputeError(f"no compute session {sid}")
        s = cls(rec.get("episode"), rec.get("step"), rec.get("purpose", ""), rec.get("cap_usd"),
                identity=rec.get("identity"), job=rec.get("job"), provider=provider,
                detached=bool(rec.get("detached")), monitor=False, sid=sid, picture=rec.get("picture"),
                blender=rec.get("blender", True))
        s.label = rec.get("label") or s.label
        s.stopped = rec.get("stopped")
        s.closed = bool(rec.get("closed"))
        s.proof_text = rec.get("proof", "")
        return s

    def open(self) -> Session:
        if state.get_session(self.id) is None:
            state.save_session({
                "id": self.id, "episode": self.episode, "step": self.step, "purpose": self.purpose,
                "identity": self.identity, "job": self.job, "cap_usd": self.cap_usd, "detached": self.detached,
                "label": self.label, "pid": os.getpid(), "host": socket.gethostname(), "heartbeat": state.now(),
                "created": state.iso(state.now()), "closed": None, "stopped": None, "rentals": [],
                "credit_before": None, "picture": self.picture, "blender": self.blender, "picture_card": None,
            })
        if self._monitor_on and self._thread is None:
            self._thread = threading.Thread(target=self._monitor, name=f"crewcut-compute-{self.id}", daemon=True)
            self._thread.start()
        return self

    def __enter__(self) -> Session:
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close("session ended")

    def _monitor(self) -> None:
        every = max(1.0, settings.num("limits.check_seconds"))
        while not self._halt.wait(every):
            try:
                self.check()
            except Exception as e:  # never let the money check die silently
                events.emit("log", episode=self.episode, text=f"compute session {self.id}: check failed "
                            f"({type(e).__name__}: {scrub.scrub_text(str(e))[:160]})")

    def provider(self):
        if self._prov is None:
            self._prov = vast.from_env()
        return self._prov

    def record(self) -> dict:
        return state.get_session(self.id) or {}

    def rental_rows(self) -> list[dict]:
        return [r for r in (rentals.get(i) for i in self.record().get("rentals", [])) if r]

    def live_rows(self) -> list[dict]:
        return [r for r in self.rental_rows() if r["status"] in rentals.LIVE]

    @property
    def machines(self) -> list[Machine]:
        return [Machine(r["id"], self) for r in self.rental_rows() if r["status"] == "ready"]

    def spent(self) -> float:
        return round(sum(rentals.cost_so_far(r) for r in self.rental_rows()), 4)

    def doing(self, text: str, rental: int | None = None, status: str = "running") -> None:
        data = {"job": self.job, "step": self.step, "doing": text, "status": status, "source": "compute",
                "session": self.id, "rental": rental, "spent_usd": self.spent(), "cap_usd": self.cap_usd}
        events.emit("activity", episode=self.episode, identity=self.identity, text=text, data=data)
        if self.job:
            try:
                db.update("jobs", self.job, doing=text)
            except Exception:  # the job row is the conductor's; a missing row must not stop the work
                pass

    # ---- money and deadlines -------------------------------------------------------------------------------------
    def check(self) -> str | None:
        """Destroy machines past their deadline; stop everything at 100 % of the cap. Returns the stop reason."""
        with self._lock:
            if self.closed:
                return self.stopped or "this compute session is closed"
            if self._own and not self.detached:
                state.update_session(self.id, heartbeat=state.now())
            rec = self.record()
            if rec.get("stopped") and not self.stopped:
                self.stopped = rec["stopped"]
            if self.stopped:
                return self.stopped
            idle_s = settings.num("limits.idle_minutes_final" if rec.get("final") else "limits.idle_minutes") * 60
            for r in self.live_rows():
                if state.now() >= rentals.deadline_ts(r) and r.get("instance"):
                    rentals.destroy(r["id"], "deadline reached", self.provider())
                elif r.get("instance") and r.get("status") == "ready" and idle_s > 0:
                    # Build cheap, render expensive: a ready machine that runs nothing costs full price. Destroy it.
                    a = state.activity(r["id"])
                    last = float(a["at"]) if a else rentals.started_ts(r) + settings.num("limits.setup_minutes") * 60
                    if not (a and a.get("busy")) and state.now() - last > idle_s:
                        rentals.destroy(r["id"], f"idle for {idle_s / 60:g} min", self.provider())
                        _say(self.episode, self.identity, f"Rented GPU {r['id']} ran nothing for {idle_s / 60:g} min "
                             "and was deleted. Build and test on this machine or one GPU; rent again for the render.")
            spent = self.spent()
            if spent >= self.cap_usd - 1e-9:
                self.stop(f"the session reached its cap: ${spent:.2f} of ${self.cap_usd:.2f}")
            return self.stopped

    def stop(self, reason: str) -> None:
        with self._lock:
            self.stopped = reason
            state.update_session(self.id, stopped=reason)
            rows = self.live_rows()
            for r in rows:
                rentals.destroy(r["id"], reason, self.provider())
            _say(self.episode, self.identity,
                 f"Stopped renting: {reason}. {_plural(len(rows), 'rented GPU')} of this session destroyed.")
            if self.detached:
                self.close(reason)

    def close(self, reason: str = "session ended") -> str:
        with self._lock:
            self._halt.set()
            if self.closed:
                return self.proof_text
            rows = self.rental_rows()
            if rows:
                prov = self.provider()
                for r in self.live_rows():
                    rentals.destroy(r["id"], reason, prov)
                ids = [int(r["instance"]) for r in self.rental_rows() if r.get("instance")]
                n, text = rentals.proof(prov, self.label, ids)
                before = self.record().get("credit_before")
                try:
                    after = prov.credit()
                except ComputeError:
                    after = None
                if before is not None and after is not None:
                    text += f" Vast credit before ${float(before):.2f}, after ${after:.2f}."
                ledger.add("gpu", 0.0, text, episode=self.episode, step=self.step, ref=f"proof:{self.id}")
                total = self.spent()
                status = "done" if n == 0 else "failed"
                self.doing(f"Rented GPUs: {_plural(len(rows), 'machine')}, ${total:.2f}. {text}", status=status)
                if n != 0:
                    _say(self.episode, self.identity, f"Warning: {text} The guard keeps trying to destroy them.")
                self.proof_text = text
            self.closed = True
            state.update_session(self.id, closed=state.iso(state.now()), proof=self.proof_text)
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        return self.proof_text

    # ---- the picture of shots (graphics behind the speaker) -------------------------------------------------------
    def _picture_card(self) -> dict | None:
        """An accepted spend card of this episode that names every picture file of this session (by sha256)."""
        need = set(_picture_files(self.picture))
        if not need or not self.episode:
            return None
        for c in reversed(approvals.list_cards(episode=self.episode, status="accepted")):
            if c.get("episode") == self.episode and need <= _card_pictures(c):
                state.update_session(self.id, picture_card=int(c["id"]))
                return c
        return None

    def picture_ok(self) -> frozenset[str]:
        """sha256 of the shot pictures this session may upload: those named on its accepted card, else nothing."""
        if not self.picture or self.closed or self.stopped:
            return frozenset()
        cid = self.record().get("picture_card")
        card = approvals.get(int(cid)) if cid else None
        if not card or card.get("episode") != self.episode:
            return frozenset()
        return frozenset(set(_picture_files(self.picture)) & _card_pictures(card))

    # ---- renting -------------------------------------------------------------------------------------------------
    def _open_spend_card(self) -> int | None:
        """Any open spend card of this episode (also one a tool proposed from an estimate): one money question at a
        time."""
        for c in approvals.list_cards(episode=self.episode, status="open"):
            if c["kind"] == "spend" and c.get("episode") == self.episode:
                return int(c["id"])
        return None

    def _fit_budget(self, amount: float, prices: list[float]) -> float:
        """A first rent inside an approved episode budget: lower the session cap to what is left of the budget instead
        of asking again (when at least MIN_USEFUL_MINUTES of the planned machines fit)."""
        if self.rental_rows():
            return amount
        left = (approvals.budget_for(self.episode, self.purpose) - approvals.spent_for(self.episode, self.purpose)
                - rentals.reserved(self.episode, purpose=self.purpose))
        if amount <= left + 1e-9 or left < sum(prices) * MIN_USEFUL_MINUTES / 60:
            return amount
        self.cap_usd = round(left, 4)
        state.update_session(self.id, cap_usd=self.cap_usd)
        self.doing(f"Inside the budget you approved: this session stops at ${self.cap_usd:.2f}")
        return self.cap_usd

    def _image(self) -> str:
        v = settings.get("vast") or {}
        main = str(v.get("image") or "").strip()
        if main and not state.image_failed_recently():
            return main
        return str(v.get("fallback_image") or settings.DEFAULTS["vast"]["fallback_image"])

    def rent(self, gpus: int = 1, max_minutes: float | None = None, estimate: dict | None = None, *,
             final: bool = False, gpu: str | None = None) -> list[Machine]:
        """Rent `gpus` machines with one GPU each. Each gets a deadline and passes SSH, a 5 MB upload probe and the
        setup before it is returned. Raises NeedsApproval, Refused, MissingKey or NoMachine.

        Build cheap, render expensive: more than `limits.build_max_gpus` GPUs only with `final=True` (the final render
        of an approved scene; those machines are deleted after `limits.idle_minutes_final` without work). `gpu` names
        one model the user asked for (e.g. "RTX 5090"); without it premium GPUs are never rented."""
        if state.get_session(self.id) is None:
            self.open()
        if self.closed:
            raise Refused("this compute session is closed")
        stopped = self.check()
        if stopped:
            raise Refused(stopped)
        gpus = int(gpus)
        if not 1 <= gpus <= int(settings.num("limits.max_gpus")):
            raise ValueError(f"gpus must be 1 to {int(settings.num('limits.max_gpus'))}")
        if gpus > int(settings.num("limits.build_max_gpus")) and not final:
            raise Refused(f"{gpus} GPUs only for the final render of an approved scene (--final). Build the scene, "
                          "previews and tests on this machine or one GPU: several GPUs would wait at full price.")
        if final:
            state.update_session(self.id, final=True)
        max_minutes = float(max_minutes or settings.num("limits.default_max_minutes"))
        if max_minutes <= 0:
            raise ValueError("max_minutes must be above 0")
        try:
            approvals.require_right("spend", self.identity)
        except approvals.RightsError as e:
            raise Refused(str(e)) from e
        if self.picture and not self.episode:
            raise Refused("the picture of a shot goes to a rented machine only inside an episode")
        prov = self.provider()

        self.doing(f"Renting {_plural(gpus, 'GPU')}: looking for offers")
        try:
            offers = rentals.usable(rentals.search(prov, gpu), rentals.taken_ips(prov), gpu)
        except vast.VastError as e:
            raise NoMachine(f"could not read offers from Vast ({e})") from e
        if not offers:
            raise NoMachine("no matching offer right now; see [vast] in config/compute.toml (GPUs, price, regions)")
        plan = offers[:gpus] + [offers[min(gpus, len(offers)) - 1]] * max(0, gpus - len(offers))
        prices = [float(o["dph_total"]) for o in plan]
        hours = (max_minutes * 60 + rentals.grace_s()) / 3600
        worst_new = sum(prices) * hours

        session_left = self.cap_usd - self.spent() - sum(rentals.worst_remaining(r) for r in self.live_rows())
        if session_left <= 0.005:
            raise Refused(f"this session's cap of ${self.cap_usd:.2f} is used up")
        amount = round(min(worst_new, session_left), 4)
        reserved_all = rentals.reserved()
        if ledger.month_left() - reserved_all < amount:
            raise Refused(f"The month cap of ${ledger.month_cap():.2f} is reached or too close "
                          f"(${ledger.month_left():.2f} left, ${reserved_all:.2f} held by running machines). "
                          "Renting stops. Raise money.cap_month_usd in studio/config/crewcut.toml to continue.")
        card = self._open_spend_card()
        if card:
            raise NeedsApproval(card)
        amount = self._fit_budget(amount, prices)
        title = f"Rent {_plural(gpus, 'GPU')} for up to {max_minutes:.0f} min (at most ${amount:.2f})"
        goes_up = picture_sentence(self.picture) if self.picture else "Only code and fonts go to the rented machines."
        body = (f"For: {self.purpose}. Price now: {', '.join(f'${p:.2f}' for p in prices)} per GPU and hour. "
                f"Worst case until every deadline: ${worst_new:.2f}. The session stops and destroys its machines "
                f"at ${self.cap_usd:.2f}. {goes_up}")
        if estimate and estimate.get("sentence"):
            body = estimate["sentence"] + " " + body
        data = {"source": "compute", "step": self.step, "cap_usd": self.cap_usd, "gpus": gpus,
                "max_minutes": max_minutes, "prices_per_hour": prices, "worst_usd": round(worst_new, 4),
                "purpose": self.purpose, "session": self.id}
        if estimate:
            data["estimate"] = {k: estimate.get(k) for k in ("local_seconds", "local_measured", "local_source", "rented_seconds",
                                                               "rented_usd", "rented_usd_worst", "gpus", "sentence")}
        if self.picture:
            data["picture"] = {"files": list(_picture_files(self.picture).values()),
                               "sentence": picture_sentence(self.picture)}
        try:
            ok, card_id, reason = approvals.require_spend(self.episode, amount, title, body, data, self.identity,
                                                          reserved_usd=rentals.reserved(self.episode, purpose=self.purpose),
                                                          total_reserved_usd=rentals.reserved(self.episode))
        except approvals.RightsError as e:
            raise Refused(str(e)) from e
        if not ok:
            if card_id:
                self.doing(f"Waiting for your yes: {title}", status="waiting")
                raise NeedsApproval(card_id, reason)
            raise Refused(reason)
        if self.picture and not self._picture_card():
            # Inside the budget no spend card is needed, but the picture of a shot never goes up without a yes that
            # names it. This card adds nothing to the budget.
            ptitle = f"Send the picture of {_plural(len(data['picture']['files']), 'shot')} to a rented GPU"
            card = approvals.propose(self.episode, self.step, "spend", ptitle, body=body,
                                     data={**data, "amount_usd": round(amount, 4), "budget_usd": 0.0},
                                     identity=self.identity)
            self.doing(f"Waiting for your yes: {ptitle}", status="waiting")
            raise NeedsApproval(int(card["id"]), "waiting for a yes to send the shot's picture")

        try:
            credit = prov.credit()
        except vast.VastError as e:
            raise Refused(f"Vast credit not readable ({e}); nothing is rented without a credit check") from e
        if credit is None:
            raise Refused("Vast credit not readable; nothing is rented without a credit check")
        need = rentals.reserved(remaining=True) + worst_new
        if credit < need:
            raise Refused(f"Vast credit ${credit:.2f} does not cover the worst case ${need:.2f}. "
                          f"Top up at {BILLING_PAGE}.")
        if self.record().get("credit_before") is None:
            state.update_session(self.id, credit_before=credit)

        self._pub = ssh.ensure_key()
        try:
            if not any(self._pub.split()[1] in k for k in prov.ssh_keys()):
                prov.add_ssh_key(self._pub)
        except (vast.VastError, IndexError) as e:
            raise ComputeError(f"could not register the studio's SSH key with Vast ({e})") from e

        machines = self._bring_up_many(prov, offers, gpus, max_minutes)
        for i, m in enumerate(machines, 1):
            m.name = f"Rented GPU {i} of {len(machines)}"
            rentals.set_detail(m.rental, name=m.name)
            self.doing(f"{m.name}: ready ({m.gpu}, ${m.price_per_hour:.2f}/h)", rental=m.rental)
        if len(machines) < gpus:
            _say(self.episode, self.identity, f"Got {len(machines)} of {gpus} rented GPUs; the others failed their "
                 "checks and were destroyed.")
        return machines

    def _bring_up_many(self, prov, offers: list[dict], gpus: int, max_minutes: float) -> list[Machine]:
        queue = list(offers)
        machines: list[Machine] = []
        tries, max_tries = 0, gpus + 4
        image = self._image()
        systematic = ""
        ssh_failures = 0
        last_failure = ""
        while len(machines) < gpus and queue and tries < max_tries and not self.stopped:
            need = gpus - len(machines)
            batch = [queue.pop(0) for _ in range(min(need, len(queue)))]
            tries += len(batch)
            created = []
            for o in batch:
                slot = len(machines) + len(created) + 1
                rid = self._create(prov, o, max_minutes, image, slot, gpus)
                if rid:
                    created.append((rid, o))
            if not created:
                continue
            with ThreadPoolExecutor(max_workers=len(created)) as ex:
                results = list(ex.map(lambda x, img=image: self._bring_up(prov, x[0], x[1], img), created))
            for (rid, _), (res, info) in zip(created, results, strict=True):
                if res != "ok":
                    last_failure = info
                if res == "ok":
                    machines.append(Machine(rid, self))
                elif res == "ssh":
                    ssh_failures += 1
                    if ssh_failures >= 2 and image != self._fallback():
                        self.doing("Two machines failed SSH startup; trying the fallback image inside the same budget")
                        state.mark_image_failed()
                        image = self._fallback()
                        ssh_failures = 0
                elif res == "image" and image != self._fallback():
                    state.mark_image_failed()
                    image = self._fallback()
                    tries -= 1  # an image problem is not the host's fault
                elif res == "systematic":
                    systematic = info
            if systematic:
                break
        if not machines:
            if systematic:
                raise ComputeError(f"setup failed in a way that a new machine will not fix: {systematic}")
            raise NoMachine(f"no usable machine after {tries} attempts; last failure: {last_failure or 'rent call failed'}")
        return machines

    def _fallback(self) -> str:
        v = settings.get("vast") or {}
        return str(v.get("fallback_image") or settings.DEFAULTS["vast"]["fallback_image"])

    def _create(self, prov, o: dict, max_minutes: float, image: str, slot: int, of: int) -> int | None:
        t = state.now()
        deadline = t + max_minutes * 60
        name = f"Renting GPU {slot} of {of}"
        d = {"session": self.id, "step": self.step, "identity": self.identity, "purpose": self.purpose,
             "gpu": o.get("gpu_name"), "host_ip": str(o.get("public_ipaddr") or "").strip(),
             "machine_id": o.get("machine_id"), "offer": o.get("id"), "geolocation": o.get("geolocation"),
             "image": image, "name": name}
        rid = db.insert("rentals", provider="vast", instance=None, label=self.label, episode=self.episode,
                        job=self.job, price_per_hour=float(o["dph_total"]), started=state.iso(t),
                        deadline=state.iso(deadline), status="creating", detail=json.dumps(d, ensure_ascii=False))
        state.add_session_rental(self.id, rid)
        env = {"NVIDIA_DRIVER_CAPABILITIES": "all", "CREWCUT_DEADLINE": str(int(deadline))}
        v = settings.get("vast") or {}
        try:
            iid = prov.create_instance(o["id"], image=image, disk_gb=float(v.get("disk_gb", 40)), label=self.label,
                                       env=env, onstart=remote.onstart(deadline))
        except ComputeError as e:
            db.update("rentals", rid, status="failed", ended=state.iso(state.now()))
            rentals.set_detail(rid, end_reason=f"rent call failed: {e}"[:300])
            return None
        db.update("rentals", rid, instance=str(iid), status="starting")
        try:
            prov.attach_ssh_key(iid, self._pub)
        except ComputeError:
            pass  # the account key usually reaches new machines anyway; SSH below decides
        self.doing(f"{name}: booting ({o.get('gpu_name')}, ${float(o['dph_total']):.2f}/h, deadline "
                   f"{state.hhmm(deadline)})", rental=rid)
        return rid

    def _fail(self, prov, rid: int, o: dict, reason: str, block: bool) -> None:
        rentals.destroy(rid, reason, prov)
        if block:
            state.block(o, reason)
        events.emit("log", episode=self.episode, identity=self.identity,
                    text=f"Rented GPU dropped ({o.get('gpu_name')}): {reason}" + ("; host blocked" if block else ""))

    def _ssh(self, rid: int, host: str, port: int, command: str, timeout: float) -> tuple[int, str]:
        rc, out, err = ssh.run(ssh.ssh_argv(host, port, rentals.get(rid)["instance"], command), timeout)
        return rc, scrub.scrub_text(out + err)

    def _bring_up(self, prov, rid: int, o: dict, image: str) -> tuple[str, str]:
        """SSH within the time limit, upload probe, setup. Returns (ok | fail | ssh | image | systematic, info)."""
        row = rentals.get(rid)
        iid = int(row["instance"])
        name = rentals.detail(row).get("name", "Rented GPU")
        main_image = image == str((settings.get("vast") or {}).get("image") or "")
        ssh_limit = settings.num("limits.ssh_wait_minutes") * 60
        image_limit = settings.num("limits.image_wait_minutes") * 60 if main_image else ssh_limit
        t0 = state.now()
        addr = None
        last_ssh = "SSH endpoint not available"
        while True:
            if self.stopped:
                self._fail(prov, rid, o, "session stopped", block=False)
                return "fail", "session stopped"
            try:
                inst = prov.instance(iid)
            except ComputeError:
                inst = {}
            if inst is None and state.now() - t0 > 60:  # a new machine may be missing from the API for a moment
                self._fail(prov, rid, o, "the machine disappeared while booting", block=False)
                return "fail", "gone"
            inst = inst or {}
            if inst and vast.image_failed(inst):
                self._fail(prov, rid, o, f"the image {image} could not be pulled", block=False)
                return "image", "pull failed"
            status = str(inst.get("actual_status") or "")
            a = vast.address(inst) if inst else None
            if status == "running" and a:
                rc, out = self._ssh(rid, a[0], a[1], "echo ok", 25)
                last_ssh = f"exit {rc}: {scrub.scrub_text(out.strip())[-600:]}"
                if rc == 0 and "ok" in out:
                    addr = a
                    break
            limit = image_limit if status in ("", "loading", "created", "scheduling") else ssh_limit
            if state.now() - t0 > limit:
                reason = f"not reachable by SSH after {limit / 60:.0f} min (status {status or 'unknown'})"
                rentals.set_detail(rid, ssh_failure=last_ssh)
                reason += f"; {last_ssh}"
                self._fail(prov, rid, o, reason, block=status == "running")
                return "ssh", reason
            state.sleep(8)
        rentals.set_detail(rid, host=addr[0], port=addr[1])
        self.doing(f"{name}: reachable after {state.now() - t0:.0f} s, upload check", rental=rid)

        rc, out = self._ssh(rid, addr[0], addr[1], remote.PREPARE, 240)
        if "ok" not in out:
            self._fail(prov, rid, o, "rsync is missing and could not be installed", block=True)
            return "fail", "no rsync"
        ok, what = self._probe(rid, addr)
        if not ok:
            self._fail(prov, rid, o, f"upload probe failed: {what}", block=True)
            return "fail", "probe"

        self.doing(f"{name}: setting up", rental=rid)
        tmp = Path(tempfile.mkdtemp(prefix="crewcut-setup-"))
        try:
            shutil.copy2(remote.setup_file(), tmp / "crewcut-setup.sh")
            remote.write_watchdog(tmp)
            rc, _, err = ssh.run(ssh.rsync_up_argv([tmp / "crewcut-setup.sh", tmp / "crewcut-watchdog.sh"],
                                                   addr[0], addr[1], iid, "/tmp/"), 120)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if rc != 0:
            self._fail(prov, rid, o, "setup upload failed", block=True)
            return "fail", "setup upload"
        deadline = int(rentals.deadline_ts(rentals.get(rid)))
        blender = str((settings.get("vast") or {}).get("blender_version") or "5.0.1") if self.blender else "none"
        cmd = f"bash {remote.SETUP_REMOTE} --deadline {deadline} --blender {blender}"
        rc, out = self._ssh(rid, addr[0], addr[1], cmd, settings.num("limits.setup_minutes") * 60)
        if "SETUP_OK" not in out:
            last = [x for x in out.splitlines() if x.strip()][-1:] or [f"exit {rc}"]
            info = f"setup failed: {last[0][:200]}"
            self._fail(prov, rid, o, info, block=rc != 2)
            return ("systematic" if rc == 2 else "fail"), info
        if "app: missing" in out and self.blender:
            t3d = paths.templates_dir() / "3d"
            if t3d.is_dir():
                self._ssh(rid, addr[0], addr[1], "mkdir -p /app/templates", 30)
                ssh.run(ssh.rsync_up_argv([t3d], addr[0], addr[1], iid, "/app/templates/"), 600)
        gpu_line = next((x for x in out.splitlines() if x.startswith("GPU 0:")), "")
        rentals.set_detail(rid, setup=[x for x in out.splitlines() if x.startswith(("blender:", "watchdog:",
                                                                                     "WARNING", "instance key"))][:6],
                           gpu_seen=gpu_line[:120])
        db.update("rentals", rid, status="ready")
        return "ok", ""

    def _probe(self, rid: int, addr: tuple[str, int]) -> tuple[bool, str]:
        mb = int(settings.num("limits.probe_mb"))
        size = mb * 1024 * 1024
        p = state.compute_dir() / f"probe-{mb}mb.bin"
        if not p.is_file() or p.stat().st_size != size:
            p.write_bytes(os.urandom(size))
        iid = rentals.get(rid)["instance"]
        rc, _, err = ssh.run(ssh.rsync_up_argv([p], addr[0], addr[1], iid, "/tmp/crewcut-probe.bin"), 120)
        rc2, out = self._ssh(rid, addr[0], addr[1], "stat -c %s /tmp/crewcut-probe.bin && rm -f /tmp/crewcut-probe.bin",
                             30)
        return str(size) in out, (scrub.scrub_text(err) + out).strip()[-160:]


def session(episode: str | None = None, step: str | None = None, purpose: str = "", cap_usd: float | None = None,
            **kw) -> Session:
    """A compute session for `with`. See the module text."""
    episode = episode if episode is not None else (os.environ.get("CREWCUT_EPISODE") or None)
    return Session(episode, step, purpose, cap_usd, **kw)


def stop_rental(rental_id: int, reason: str = "stopped by the user", provider=None) -> dict:
    """The user's Stop on the GPU card: stop the session this machine belongs to and delete its machines now.

    Frames that already came home stay in the episode; the render workbench sees the stop, ends its batches and keeps
    what is done. Returns {stopped, rentals: [ids], cost_usd}. Stopping never spends money."""
    row = rentals.get(int(rental_id))
    if row is None:
        raise ComputeError(f"no rented machine {rental_id}")
    sid = rentals.detail(row).get("session")
    if sid and state.get_session(sid):
        s = Session.attach(sid, provider=provider)
        ids = [r["id"] for r in s.live_rows()]
        s.stop(reason)
        if not s.closed:
            s.close(reason)
    else:
        ids = [row["id"]] if row["status"] not in ("destroyed", "failed") else []
        for rid in ids:
            rentals.destroy(rid, reason, provider)
    cost = sum(rentals.cost_so_far(rentals.get(rid)) for rid in ids if rentals.get(rid))
    return {"stopped": len(ids), "rentals": ids, "cost_usd": round(cost, 4)}
