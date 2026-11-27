"""The HTTP server: the API from docs/api.md, live events (SSE), the built web UI, and the teleprompter on its own port."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, approvals, brand, db, engines, episodes, events, ledger, media, paths, prompter, team
from ..conductor import flow, queue

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}

# The web app manifest (install as an app): browsers expect this type, and not every system's mime table knows it.
mimetypes.add_type("application/manifest+json", ".webmanifest")


class TextIn(BaseModel):
    text: str


class NewEpisodeIn(BaseModel):
    """New Episode: the pasted tool, link, tweet or idea; long, short or auto; optionally a show format id."""
    text: str
    length: Literal["long", "short", "auto"] = "auto"
    show_format: str | None = None


class IdeaStartIn(BaseModel):
    length: Literal["long", "short", "auto"] | None = None
    show_format: str | None = None


class AcceptIn(BaseModel):
    choice: int | None = None


class FullAutoIn(BaseModel):
    mode: str


class InterviewIn(BaseModel):
    action: str        # "skip" or "done"


class DeclineIn(BaseModel):
    reason: str | None = None


class OnboardIn(BaseModel):
    links: list[str] = []
    text: str | None = None


class StrikeIn(BaseModel):
    row: str
    struck: bool = True


def _allowed_hosts() -> set[str]:
    extra = {h.strip() for h in os.environ.get("CREWCUT_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return LOCAL_HOSTS | extra


def _host_only(h: str) -> str:
    h = h.strip().lower()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def _guard(request: Request) -> JSONResponse | None:
    """Only this machine may drive the studio: refuse foreign Host headers (DNS rebinding) and cross-site writes."""
    host = _host_only(request.headers.get("host", ""))
    if host not in _allowed_hosts():
        return JSONResponse({"error": "This studio only answers on localhost."}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            o = _host_only(re.sub(r"^https?://", "", origin).split("/")[0])
            if o not in _allowed_hosts():
                return JSONResponse({"error": "Cross-site requests are refused."}, status_code=403)
    return None


_ENGINE_CACHE: dict = {}
_LOGIN: dict = {}  # the running sign-ins: "claude" -> ClaudeSignIn, "codex" -> {"status", "url", "code", "text"}
_LOGIN_LOCK = __import__("threading").Lock()


class CodeIn(BaseModel):
    code: str


def _engine_changed(ok: bool | None) -> None:
    """After a connect or disconnect: forget the start's probe and the cache, so the screen shows the new state."""
    _ENGINE_CACHE.clear()
    if ok is None:
        db.kv_set("engine_probe", "")
    else:
        db.kv_set("engine_probe", json.dumps({"ok": ok, "engine": "claude", "detail": "connected in Crewcut" if ok
                                              else "disconnected in Crewcut", "at": db.now()}))


def _login_view() -> dict:
    from ..engines import connect
    claude = engines.get("claude")
    codex = engines.get("codex")
    cx = _LOGIN.get("codex") if isinstance(_LOGIN.get("codex"), dict) else None
    codex_ok = codex.installed() and codex.login_status()[0]
    return {
        "claude": {"installed": claude.installed(), "connected": claude.login_status()[0],
                   "source": connect.token_source(), "signing_in": "claude" in _LOGIN},
        "codex": {"installed": codex.installed(), "connected": codex_ok,
                  **({k: v for k, v in cx.items() if k in ("status", "url", "code", "text")} if cx else {})},
        "chosen": engines.current_name(),
    }


def _engine_ok() -> bool:
    """The chosen engine has a current login. Never use an old probe to hide a missing credential."""
    import time
    name = engines.current_name()
    hit = _ENGINE_CACHE.get(name)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    eng = engines.current()
    ok = eng.installed() and eng.login_status()[0]
    _ENGINE_CACHE[name] = (time.time(), ok)
    return ok


def _gpu_local() -> bool:
    return bool(shutil.which("nvidia-smi")) and os.path.exists("/dev/nvidia0")


def _onboarded() -> bool:
    """True after the user accepted the profile card (the pack folder alone appears while Brand is still working)."""
    return db.kv_get("onboarded") == "1"


def _card_view(c: dict) -> dict:
    return approvals.view(c)


def money() -> dict:
    t = ledger.totals()
    return {"today_usd": t["today_usd"], "episode_usd": ledger.by_episode(), "month_usd": t["month_usd"],
            "cap_month_usd": t["cap_month_usd"]}


def state() -> dict:
    eps = []
    for eid in episodes.list_ids():
        try:
            eps.append(episodes.summary(eid))
        except (OSError, ValueError, KeyError):
            continue
    return {
        "app": {"version": __version__, "engine": engines.current_name(), "engine_ok": _engine_ok(),
                "gpu_local": _gpu_local(),
                "onboarded": _onboarded()},
        "team": [team.public(x) for x in team.all_identities()],
        "episodes": eps,
        "activity": queue.active() + [dict(j, status=j["status"]) for j in queue.done_today()],
        "money": money(),
    }


def create_app(start_worker: bool = True) -> FastAPI:
    from ..engines import connect
    connect.load_stored_token()  # a Claude login made in the web UI, unless the environment (.env, desktop app) has one
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            app.state.worker = queue.Worker()
            app.state.worker.start_background()
            from ..conductor import inbox
            inbox.start_background()
            from .. import ideas
            ideas.start_background()
            from ..youtube import connect as youtube_connect
            youtube_connect.start_background()
            try:
                from ..compute import guard as compute_guard
                compute_guard.start_background()
            except (ImportError, AttributeError):
                pass
        yield
        if start_worker:
            app.state.worker.stop.set()

    app = FastAPI(title="Crewcut", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        refused = _guard(request)
        if refused is not None:
            return refused
        return await call_next(request)

    # ---- state and episodes ----------------------------------------------------------------------------------------
    @app.get("/api/state")
    def get_state():
        return state()

    @app.get("/api/episodes/{eid}")
    def get_episode(eid: str):
        try:
            s = episodes.summary(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        return {**s, "project": episodes.read(eid), "files": episodes.files(eid)}

    @app.get("/api/episodes/{eid}/imported-files")
    def get_imported_files(eid: str, folder: str = "", offset: int = Query(0, ge=0),
                           limit: int = Query(100, ge=1, le=100)):
        try:
            episodes.read(eid)
            return episodes.imported_files(eid, folder, offset, limit)
        except ValueError:
            raise HTTPException(403, "Only imported folders can be listed.") from None
        except FileNotFoundError:
            raise HTTPException(404, "Imported folder not found.") from None

    @app.get("/api/episodes/{eid}/media")
    def get_media(eid: str):
        try:
            episodes.read(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        return media.episode_media(eid)

    @app.post("/api/episodes/{eid}/gpu/{rental}/stop")
    def stop_gpu(eid: str, rental: int):
        """The GPU card's Stop: delete the rented machines of this render now; frames that are home stay."""
        from ..compute import rentals as crentals
        from ..compute.errors import ComputeError
        from ..compute.session import stop_rental
        row = crentals.get(rental)
        if row is None or row.get("episode") != eid:
            raise HTTPException(404, "No such rented machine in this episode.")
        try:
            res = stop_rental(rental, "stopped by you on the GPU card")
        except ComputeError as e:
            raise HTTPException(502, f"Couldn't stop it: {e}") from None
        flow.post(eid, f"Stopped the rented GPU: {res['stopped']} machine(s) deleted, ${res['cost_usd']:.2f} in all. "
                  "The frames that came home stay.", author="editor")
        return res

    @app.post("/api/episodes/{eid}/shorts")
    def make_short(eid: str):
        """"Make a Short": a Short in clip mode from this episode; the Scout starts on the passages."""
        from .. import shorts
        try:
            res = shorts.start_clip(eid)
        except FileNotFoundError:
            raise HTTPException(404, "No such episode.") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        flow.post(eid, f"Started a Short from this episode ({res['episode']}). The Scout looks for passages that stand "
                  "on their own.", author="showrunner")
        return res

    @app.post("/api/episodes")
    def post_episode(body: NewEpisodeIn):
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "Say the idea in one sentence.")
        try:
            project = flow.new_episode(text, length=body.length, show_format=body.show_format or None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return episodes.summary(project["id"])

    # ---- the format system: formats, ideas, scoreboard (docs/formats.md) -----------------------------------------
    @app.get("/api/formats")
    def get_formats():
        from .. import showformats
        lib, problems = showformats.report()
        return {"formats": [showformats.public(f) for f in sorted(lib.values(), key=lambda f: (f["length"], f["id"]))],
                "problems": problems, "enabled": showformats.settings()["enabled"]}

    @app.get("/api/ideas")
    def get_ideas(status: str | None = None):
        from .. import ideas
        ideas.load()
        return ideas.list_ideas(status=status)

    @app.post("/api/ideas/{iid}/start")
    def start_idea(iid: str, body: IdeaStartIn | None = None):
        from .. import ideas
        body = body or IdeaStartIn()
        ideas.load()
        try:
            res = ideas.start(iid, length=body.length, show_format=body.show_format)
        except KeyError:
            raise HTTPException(404, "No such idea.") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"idea": res["idea"], "episode": episodes.summary(res["episode"])}

    @app.post("/api/ideas/{iid}/dismiss")
    def dismiss_idea(iid: str):
        from .. import ideas
        ideas.load()
        try:
            return ideas.dismiss(iid)
        except KeyError:
            raise HTTPException(404, "No such idea.") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/scoreboard")
    def get_scoreboard():
        from .. import scoreboard
        return scoreboard.build()

    @app.get("/api/episodes/{eid}/messages")
    def get_messages(eid: str, after: int = 0):
        return flow.messages(eid, after=after)

    @app.get("/api/channel/messages")
    def channel_messages(after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500)):
        return flow.messages("_channel", after=after, limit=limit)

    @app.post("/api/channel/messages")
    def channel_message(body: TextIn):
        from .. import channel
        try:
            return channel.user_message(body.text)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.get("/api/channel/context")
    def channel_context():
        from .. import channel
        return channel.context()

    @app.post("/api/episodes/{eid}/messages")
    def post_message(eid: str, body: TextIn):
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "Empty message.")
        if eid != flow.ONBOARDING:
            try:
                episodes.read(eid)
            except (FileNotFoundError, ValueError):
                raise HTTPException(404, "No such episode.") from None
        return flow.user_message(eid, text)

    @app.post("/api/episodes/{eid}/upload")
    def upload(eid: str, file: list[UploadFile] = File(...)):  # noqa: B008 - FastAPI pattern
        try:
            episodes.read(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        inbox = paths.studio_root() / "inbox" / eid
        inbox.mkdir(parents=True, exist_ok=True)
        saved = []
        for f in file:
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(f.filename or "file").name).lstrip(".") or "file"
            target = inbox / name
            n = 1
            while target.exists():
                target = inbox / f"{Path(name).stem}-{n}{Path(name).suffix}"
                n += 1
            with open(target, "wb") as out:
                shutil.copyfileobj(f.file, out, length=1 << 20)
            saved.append({"path": str(target.relative_to(paths.studio_root())), "size": target.stat().st_size})
        if saved:
            seen = set(json.loads(db.kv_get(f"inbox_seen:{eid}") or "[]"))
            db.kv_set(f"inbox_seen:{eid}", json.dumps(sorted(seen | {s["path"] for s in saved})))
            flow.on_upload(eid, [s["path"] for s in saved])
        return saved

    @app.get("/api/episodes/{eid}/crew")
    def crew_messages(eid: str):
        from .. import crewtalk
        return {"enabled": crewtalk.settings()["enabled"], "messages": [crewtalk.view(m) for m in crewtalk.messages(eid)]}

    @app.get("/api/episodes/{eid}/prompter")
    def prompter_info(eid: str):
        try:
            url = prompter.url_for(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        return {"url": url, "qr_svg": prompter.qr_svg(url)}

    @app.post("/api/episodes/{eid}/interview")
    def interview_action(eid: str, body: InterviewIn):
        """The interview bar: "Skip interview", or "Done answering" after answers in several messages."""
        from .. import interview
        try:
            project = episodes.read(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        status = interview.state(project).get("status")
        if body.action == "skip":
            if status in ("done", "skipped"):
                raise HTTPException(400, f"The interview is already {status}.")
            interview.skip(eid, "the creator pressed Skip interview")
        elif body.action == "done":
            if status != "waiting":
                raise HTTPException(400, "The interview is not waiting for answers.")
            interview.finish(eid)
        else:
            raise HTTPException(400, 'action must be "skip" or "done".')
        return interview.summary(episodes.read(eid))

    @app.get("/api/episodes/{eid}/full-auto")
    def full_auto_status(eid: str):
        from .. import full_auto
        episodes.read(eid)
        return full_auto.policy(eid)

    @app.post("/api/episodes/{eid}/full-auto")
    def full_auto_configure(eid: str, body: FullAutoIn):
        from .. import full_auto
        try:
            return full_auto.configure(eid, body.mode)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/episodes/{eid}/desktop-prompter")
    def desktop_prompter_info(eid: str):
        from ..desktop_prompter import launch_info
        try:
            return launch_info(eid)
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(409, str(error)) from None

    @app.get("/api/files/{eid}/{rel:path}")
    def get_file(eid: str, rel: str, download: bool = False):
        try:
            if eid == flow.ONBOARDING:
                if not rel.startswith("brand/"):
                    raise ValueError
                p = paths.inside(paths.studio_root() / "brand", rel[len("brand/"):])
            else:
                p = paths.inside(paths.episode_dir(eid), rel)
        except ValueError:
            raise HTTPException(403, "Only files inside the episode can be shown.") from None
        if not p.is_file():
            raise HTTPException(404, "File not found.")
        if download or p.suffix.lower() in {".html", ".htm", ".svg", ".js"}:
            return FileResponse(p, filename=p.name, media_type="application/octet-stream")
        return FileResponse(p)

    # ---- cards ------------------------------------------------------------------------------------------------------
    @app.get("/api/cards")
    def get_cards(episode: str | None = None, status: str | None = None):
        return [_card_view(c) for c in approvals.list_cards(episode=episode, status=status)]

    @app.post("/api/cards/{cid}/accept")
    def accept(cid: int, body: AcceptIn | None = None):
        try:
            return _card_view(approvals.decide(cid, True, choice=(body.choice if body else None)))
        except KeyError:
            raise HTTPException(404, "No such card.") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/cards/{cid}/decline")
    def decline(cid: int, body: DeclineIn | None = None):
        try:
            return _card_view(approvals.decide(cid, False, reason=(body.reason if body else None)))
        except KeyError:
            raise HTTPException(404, "No such card.") from None

    @app.post("/api/cards/{cid}/strike")
    def strike(cid: int, body: StrikeIn):
        """Tap to strike (or bring back) one row of an open motion plan card; writes the next plan version."""
        from ..motion import director
        try:
            return _card_view(director.strike(cid, body.row, body.struck))
        except KeyError:
            raise HTTPException(404, "No such card.") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    # ---- motion: the plan, the pieces, the shelf, the bar ------------------------------------------------------------
    @app.get("/api/episodes/{eid}/motion")
    def get_motion(eid: str):
        from ..motion import views
        try:
            episodes.read(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        return views.episode(eid)

    @app.get("/api/motion/library")
    def motion_library():
        from ..motion import library
        return {"templates": library.shelf()}

    @app.get("/api/motion/ratchet")
    def motion_ratchet():
        from ..motion import ratchet
        return ratchet.brand_snapshot()

    @app.get("/api/motion/app/samples/{rel:path}")
    def motion_app_sample(rel: str):
        from ..motion import templates as mtemplates
        try:
            p = paths.inside(mtemplates.app_dir() / "samples", rel)
        except ValueError:
            raise HTTPException(403, "Only the app's motion samples can be shown here.") from None
        if not p.is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(p)

    # ---- crew and jobs ------------------------------------------------------------------------------------------------
    @app.get("/api/team")
    def get_team():
        return [team.public(x, with_soul=True) for x in team.all_identities()]

    @app.get("/api/jobs")
    def get_jobs(episode: str | None = None, status: str | None = None):
        q, args = "SELECT * FROM jobs WHERE 1=1", []
        if episode:
            q += " AND episode = ?"
            args.append(episode)
        if status:
            q += " AND status = ?"
            args.append(status)
        with db.conn() as c:
            return [queue.job_view(j) for j in db.rows(c.execute(q + " ORDER BY id DESC LIMIT 200", args))]

    @app.get("/api/jobs/{jid}/log")
    def job_log(jid: int):
        j = queue.get(jid)
        if not j:
            raise HTTPException(404, "No such job.")
        p = Path(j.get("log_path") or "")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-400:] if p.is_file() else []
        return {"job": queue.job_view(j), "lines": [engines.scrub(x) for x in lines]}

    # ---- brand and onboarding ----------------------------------------------------------------------------------------
    @app.get("/api/profile")
    def profile():
        pack = brand.load()
        prev = paths.user_brand_dir() / "preview.mp4"
        rules = [{"step": step, **r} for step, rs in pack.all_rules().items() for r in rs]
        from .. import approvals, shorts, voice
        rows = brand.profile_rows(pack)
        n_voice = len(voice.samples())
        rows.append({"label": "Voice sample", "value": f"{n_voice} of your own videos" if n_voice else
                     "none yet", "kind": "text", "source": "brand/voice/"})
        rows.append({"label": "Shorts", "value": shorts.standing_line(), "kind": "text",
                     "source": "your yes on a card" if approvals.standing("shorts") else "Crewcut default"})
        return {"source": "neutral" if pack.is_neutral else "brand", "rows": rows,
                "preview": f"/api/files/{flow.ONBOARDING}/brand/preview.mp4" if prev.is_file() else None,
                "rules": rules}

    @app.post("/api/onboarding")
    def onboarding(body: OnboardIn):
        text = " ".join([*(body.links or []), body.text or ""]).strip()
        if not text:
            raise HTTPException(400, "Paste your links.")
        flow.post(flow.ONBOARDING, text, author="user")
        return {"job": flow.start_onboarding(text)}

    # ---- money --------------------------------------------------------------------------------------------------------
    @app.get("/api/money")
    def get_money():
        return {**money(), "rows": ledger.rows()}

    @app.get("/api/compute/estimate")
    def estimate(kind: str = "blender", frames: int = 75):
        try:
            from .. import compute
        except ImportError:
            raise HTTPException(501, "The compute module is not installed.") from None
        return compute.estimate(kind=kind, frames=frames)

    # ---- live events ----------------------------------------------------------------------------------------------------
    @app.get("/api/events")
    async def stream(request: Request):
        last = int(request.headers.get("last-event-id") or events.last_id())

        async def gen():
            nonlocal last
            idle = 0.0
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                batch = events.since(last)
                for ev in batch:
                    last = ev["id"]
                    yield f"id: {ev['id']}\nevent: {ev['kind']}\ndata: {json.dumps(ev.get('data') or {})}\n\n"
                if batch:
                    idle = 0.0
                else:
                    idle += 0.5
                    if idle >= 15:
                        idle = 0.0
                        yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    # ---- Connect Claude and Codex from the web UI (engines/connect.py): the CLIs' own sign-in, no terminal ----------
    @app.get("/api/engine/login")
    def engine_login():
        return _login_view()

    @app.post("/api/engine/{name}/use")
    def engine_use(name: str):
        try:
            eng = engines.get(name)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if not eng.installed() or not eng.login_status()[0]:
            raise HTTPException(409, f"Connect {eng.label} before switching.")
        engines.use(eng.name)
        _engine_changed(ok=None)
        events.emit("activity", text=f"New work uses {eng.label}. Running work keeps its engine.")
        return _login_view()

    @app.post("/api/engine/claude/connect")
    def claude_connect():
        from ..engines import connect
        eng = engines.get("claude")
        if not eng.installed():
            raise HTTPException(409, "Claude Code is still being installed. Try again in a minute.")
        with _LOGIN_LOCK:
            old = _LOGIN.pop("claude", None)
            if old:
                old.close()
            session = connect.ClaudeSignIn(eng.binary() or "claude")
            try:
                url = session.start()
            except RuntimeError as e:
                raise HTTPException(502, str(e)) from None
            _LOGIN["claude"] = session
        return {"url": url}

    @app.post("/api/engine/claude/code")
    def claude_code(body: CodeIn):
        from ..engines import connect
        with _LOGIN_LOCK:
            session = _LOGIN.pop("claude", None)
        if not session:
            raise HTTPException(409, "The sign-in has ended. Press Connect Claude again.")
        try:
            token = session.finish(body.code)
        except ValueError as e:
            with _LOGIN_LOCK:
                _LOGIN.setdefault("claude", session)  # a typo: the same sign-in takes the code again
            raise HTTPException(400, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from None
        finally:
            if "claude" not in _LOGIN:
                session.close()
        connect.store_token(token)
        _engine_changed(ok=True)
        return {"connected": True, "account": connect.claude_account(token, engines.get("claude").binary())}

    @app.post("/api/engine/claude/disconnect")
    def claude_disconnect():
        from ..engines import connect
        if not connect.forget_token():
            raise HTTPException(409, "This Claude login comes from the environment (.env or the desktop app); "
                                     "remove it there.")
        _engine_changed(ok=False)
        return _login_view()

    @app.post("/api/engine/codex/connect")
    def codex_connect():
        import threading
        import time as _time
        eng = engines.get("codex")
        state: dict = {"status": "starting"}
        _LOGIN["codex"] = state

        def run():
            if not eng.installed():
                state["status"] = "installing"
                ok, out = eng.install()
                if not ok:
                    state.update(status="failed", text=f"Codex could not be installed: {out}")
                    return
            ok, why = eng.device_login(lambda url, code: state.update(status="waiting", url=url, code=code))
            state.update(status="connected" if ok else "failed", text=why)
            _engine_changed(ok=None)

        threading.Thread(target=run, daemon=True).start()
        end = _time.monotonic() + 60
        while _time.monotonic() < end and state["status"] in ("starting", "installing"):
            _time.sleep(0.3)
        return {k: v for k, v in state.items() if k in ("status", "url", "code", "text")}

    @app.post("/api/engine/codex/disconnect")
    def codex_disconnect():
        eng = engines.get("codex")
        if eng.installed():
            import subprocess as _sp
            _sp.run([eng.binary() or "codex", "logout"], env={**os.environ, **eng.env()}, capture_output=True,
                    timeout=30)
        _LOGIN.pop("codex", None)
        _engine_changed(ok=None)
        return _login_view()

    # ---- YouTube sign-in (the redirect comes back to this local server) -------------------------------------------
    @app.get("/api/youtube/auth")
    def youtube_auth():
        from ..youtube import auth
        try:
            return {"url": auth.start(), "connected": auth.connected()}
        except FileNotFoundError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/oauth/youtube", include_in_schema=False)
    def youtube_callback(code: str = "", state: str = "", error: str = ""):
        from ..youtube import auth
        if error or not code:
            return HTMLResponse(f"<p>YouTube was not connected ({error or 'no code'}). Close this tab and try again.</p>",
                                status_code=400)
        try:
            auth.finish(code, state)
        except PermissionError as e:
            return HTMLResponse(f"<p>{e}</p>", status_code=403)
        flow.post(flow.ONBOARDING, "YouTube is connected. Uploads go through the official API from now on.",
                  author="publisher")
        return HTMLResponse("<p>YouTube is connected. You can close this tab.</p>")

    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    dist = paths.web_dist_dir()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{rest:path}", include_in_schema=False)
    def spa(rest: str):
        if rest.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = dist / rest
        if rest and candidate.is_file() and dist.resolve() in candidate.resolve().parents:
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse("<p>The web UI is not built. Run <code>npm run build</code> in <code>web/</code>.</p>")


def create_prompter_app() -> FastAPI:
    """The teleprompter: its own port, reachable from a phone, every route behind the episode's token."""
    app = FastAPI(title="Crewcut teleprompter", docs_url=None, redoc_url=None)
    dist = paths.web_dist_dir()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    known: dict[str, str] = {}  # token -> episode, checked again on every request

    def episode_of(token: str) -> str:
        if len(token) < 12:
            raise HTTPException(404, "Unknown teleprompter link.")
        eid = known.get(token)
        if eid:
            try:
                if secrets.compare_digest(episodes.read(eid).get("prompter_token", ""), token):
                    return eid
            except (OSError, ValueError):
                pass
        eid = episodes.by_prompter_token(token)
        if not eid:
            raise HTTPException(404, "Unknown teleprompter link.")
        if len(known) > 64:
            known.clear()
        known[token] = eid
        return eid

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        p = dist / "favicon.svg"
        if not p.is_file():
            raise HTTPException(404, "Not found.")
        return FileResponse(p)

    @app.get("/p/{token}")
    def page(token: str):
        episode_of(token)
        p = dist / "prompter.html"
        if p.is_file():
            return FileResponse(p)
        return HTMLResponse("<p>The teleprompter page is not built.</p>")

    @app.get("/p/{token}/script")
    def script(token: str):
        return prompter.script(episode_of(token))

    @app.get("/p/{token}/control")
    async def get_control(token: str, after: int | None = None, wait: float = 0.0):
        """The shared state. With `after` (the seq a screen has) and `wait` (seconds, at most 25) the answer waits until
        the state changes, so every screen hears a command at once. `waited` (ms) lets the screen set its clock."""
        eid = episode_of(token)
        started = time.monotonic()
        if after is not None and wait > 0:
            await prompter.wait_change(eid, after, min(wait, 25.0))
        state = prompter.control(eid)
        state["waited"] = round((time.monotonic() - started) * 1000)
        return state

    @app.post("/p/{token}/control")
    async def post_control(token: str, request: Request):
        eid = episode_of(token)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Send JSON.") from None
        return prompter.set_control(eid, body if isinstance(body, dict) else {})

    return app


def serve(host: str = "127.0.0.1", port: int = 4747, prompter_host: str = "0.0.0.0", prompter_port: int = 4748) -> None:
    import uvicorn

    async def main():
        s1 = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, log_level="warning"))
        s2 = uvicorn.Server(uvicorn.Config(create_prompter_app(), host=prompter_host, port=prompter_port,
                                           log_level="warning"))
        await asyncio.gather(s1.serve(), s2.serve())

    asyncio.run(main())
