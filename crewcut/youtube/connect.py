"""Connect YouTube once: Claude in Chrome sets up the YouTube Data API for the user, then the normal sign-in.

Uploads always go through the API (`upload.py`). What is hard for people is the one-time setup in the Google Cloud
console (project, two APIs, consent screen with themselves as test user, a Desktop OAuth client, the JSON file). With
Claude Code that is one card:

1. "Connect YouTube" card (`propose()`): the user presses **Set it up in my Chrome**.
2. On the yes, Crewcut writes a signed request for the host helper (`host/crewcut-host.sh`, started by `./start.sh`).
   The container cannot start programs on the computer; the helper can, and only this one job: it checks the HMAC
   signature (CREWCUT_HOST_TOKEN), the age, that the request is new, and that its own setup prompt has the checksum the
   request names, then starts the user's own Claude Code with `--chrome` on that fixed prompt, in a visible window.
3. The user signs in to Google when asked and watches. Claude creates everything and downloads the client file; the
   helper moves it to `studio/config/youtube-client.json`.
4. Crewcut posts the "Sign in with Google" link (`auth.start()`); after the user allows it, YouTube is connected.

Claude in Chrome needs Claude Code on the computer signed in with `/login` (not the token of `claude setup-token`) and
Chrome or Edge with the "Claude in Chrome" extension. With Codex as the engine this setup is planned (untested on a
Mac); the card then links the manual steps in docs/youtube.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from .. import approvals, config, events, paths
from . import auth

KIND = "youtube-setup"
STALE_S = 15


def box() -> Path:
    return paths.state_dir() / "host"


def prompt_file() -> Path:
    return paths.app_root() / "host" / "prompts" / "youtube-setup.md"


def prompt_sha256() -> str:
    return hashlib.sha256(prompt_file().read_bytes()).hexdigest()


def token() -> str:
    return os.environ.get("CREWCUT_HOST_TOKEN", "")


def sign(fields: dict) -> str:
    msg = ";".join(f"{k}={fields[k]}" for k in ("kind", "id", "at", "nonce", "prompt_sha256"))
    return hmac.new(token().encode(), msg.encode(), hashlib.sha256).hexdigest()


def helper() -> dict | None:
    """The host helper's heartbeat, or None when it is not running."""
    try:
        h = json.loads((box() / "helper.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return h if time.time() - float(h.get("at", 0)) < STALE_S else None


def state() -> dict:
    h = helper()
    return {
        "connected": auth.connected(),
        "client_file": auth.client_file().is_file(),
        "helper": bool(h),
        "claude_on_host": bool(h and h.get("claude")),
        "chrome_on_host": bool(h and h.get("chrome")),
        "token": bool(token()),
        "engine": _engine(),
    }


def _engine() -> str:
    from .. import engines
    return engines.current_name()


def why_not() -> str | None:
    """Why the Chrome setup cannot start now, in one sentence with what to do; None when it can."""
    s = state()
    if s["engine"] != "claude":
        return ("Setting up YouTube through Chrome works with Claude Code; with Codex it is planned. Follow the five "
                "steps in docs/youtube.md instead.")
    if not s["token"]:
        return "Start Crewcut with ./start.sh once more: it creates the key the helper needs (CREWCUT_HOST_TOKEN)."
    if not s["helper"]:
        return "The host helper is not running. Start Crewcut with ./start.sh (it starts the helper next to Docker)."
    if not s["claude_on_host"]:
        return "Claude Code is not installed on this computer. Install it, run `claude` once and sign in with /login."
    if not s["chrome_on_host"]:
        return "Chrome or Edge is needed for Claude in Chrome. Install one, then press the button again."
    return None


def propose(episode: str | None = None) -> dict:
    """The one card. Its body says what will happen and what the user does."""
    body = ("Claude sets up the YouTube API in your own Chrome: a Google Cloud project, YouTube Data API and Analytics, "
            "the consent screen with you as test user, and a Desktop client. You sign in to Google when it asks and "
            "watch; it never types a password. Then you allow Crewcut once. Uploads always go through the API.")
    blocker = why_not()
    if blocker:
        body += f"\n\nBefore that: {blocker}"
    return approvals.propose(episode, "upload", "other", "Connect YouTube", body=body,
                             data={"connect": "youtube", "button": "Set it up in my Chrome", "blocker": blocker})


def request_setup() -> dict:
    """Write the signed request for the host helper. Only after the user's yes on the Connect card."""
    blocker = why_not()
    if blocker:
        raise RuntimeError(blocker)
    rid = f"yt-{int(time.time())}-{secrets.token_hex(3)}"
    fields = {"kind": KIND, "id": rid, "at": str(int(time.time())), "nonce": secrets.token_hex(16),
              "prompt_sha256": prompt_sha256()}
    fields["sig"] = sign(fields)
    d = box() / "requests"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{rid}.tmp"
    tmp.write_text("".join(f"{k}={v}\n" for k, v in fields.items()), encoding="utf-8")
    tmp.rename(d / f"{rid}.req")
    return {"id": rid}


def statuses(since: int = 0) -> list[dict]:
    """What the helper reported (status.jsonl), newer than `since`."""
    out = []
    try:
        lines = (box() / "status.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            s = json.loads(line)
        except ValueError:
            continue
        if int(s.get("at", 0)) >= since:
            out.append(s)
    return out


class Watcher:
    """Turns the helper's status lines into chat lines; once the client file is there, posts the sign-in link."""

    def __init__(self) -> None:
        self.seen: set[tuple] = set()
        self.started = int(time.time())
        self.linked = False

    def tick(self, episode: str | None) -> None:
        from ..conductor import flow
        for s in statuses(self.started):
            key = (s.get("id"), s.get("state"), s.get("text"))
            if key in self.seen:
                continue
            self.seen.add(key)
            if episode:
                flow.post(episode, str(s.get("text") or ""), author="publisher")
            events.emit("log", episode=episode, identity="publisher", text=f"YouTube setup: {s.get('text')}")
        if not self.linked and auth.client_file().is_file() and not auth.connected():
            try:
                url = auth.start()
            except Exception as e:  # noqa: BLE001 - the YouTube libraries are optional
                if episode:
                    flow.post(episode, f"The client file is there, but the sign-in could not start: {e}",
                              author="publisher")
                self.linked = True
                return
            self.linked = True
            if episode:
                flow.post(episode, f"Last step: allow Crewcut to upload to your channel. Open this link and choose your "
                          f"channel: {url}", author="publisher")


def start_background():
    """In the server: turn the helper's status lines into chat lines of the chat that asked for the setup."""
    import threading
    import traceback

    from .. import db

    def loop() -> None:
        w = Watcher()
        while True:
            try:
                ep = db.kv_get("youtube_connect_episode") or None
                if ep:
                    w.tick(ep)
            except Exception:  # noqa: BLE001 - the watcher must keep running
                traceback.print_exc()
            time.sleep(2)

    t = threading.Thread(target=loop, daemon=True, name="crewcut-youtube-connect")
    t.start()
    return t


def enabled() -> bool:
    return bool(config.get("crewcut", "youtube.chrome_setup", True))


__all__ = ["propose", "request_setup", "state", "why_not", "helper", "Watcher", "sign", "prompt_sha256"]
