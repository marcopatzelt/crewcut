"""The HTTP server: the API from docs/api.md, live events (SSE), the built web UI, and the teleprompter on its own port."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, approvals, brand, db, engines, episodes, events, ledger, paths, prompter, team
from ..conductor import flow, queue

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


class TextIn(BaseModel):
    text: str


class AcceptIn(BaseModel):
    choice: int | None = None


class DeclineIn(BaseModel):
    reason: str | None = None


class OnboardIn(BaseModel):
    links: list[str] = []
    text: str | None = None


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


def _engine_ok() -> bool:
    """The chosen engine is installed and logged in (a probe at start counts most). Cached for 30 s."""
    import time
    name = engines.current_name()
    hit = _ENGINE_CACHE.get(name)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    ok = None
    probe = db.kv_get("engine_probe")
    if probe:
        try:
            d = json.loads(probe)
            if d.get("engine", "claude") == name:
                ok = bool(d.get("ok"))
        except ValueError:
            pass
    if ok is None:
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
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            app.state.worker = queue.Worker()
            app.state.worker.start_background()
            from ..conductor import inbox
            inbox.start_background()
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

    @app.post("/api/episodes")
    def post_episode(body: TextIn):
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "Say the idea in one sentence.")
        project = flow.new_episode(text)
        return episodes.summary(project["id"])

    @app.get("/api/episodes/{eid}/messages")
    def get_messages(eid: str, after: int = 0):
        return flow.messages(eid, after=after)

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

    @app.get("/api/episodes/{eid}/prompter")
    def prompter_info(eid: str):
        try:
            url = prompter.url_for(eid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No such episode.") from None
        return {"url": url, "qr_svg": prompter.qr_svg(url)}

    @app.get("/api/files/{eid}/{rel:path}")
    def get_file(eid: str, rel: str):
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
        return {"source": "neutral" if pack.is_neutral else "brand", "rows": brand.profile_rows(pack),
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

    def episode_of(token: str) -> str:
        eid = episodes.by_prompter_token(token) if len(token) >= 12 else None
        if not eid:
            raise HTTPException(404, "Unknown teleprompter link.")
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
    def get_control(token: str):
        return prompter.control(episode_of(token))

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
