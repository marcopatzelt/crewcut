"""A bounded, durable request for the desktop app, never a host command or URL."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid

from . import db, episodes, paths


def launch_info(episode: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode):
        raise ValueError("Invalid episode.")
    project = episodes.read(episode)
    with db.conn() as connection:
        card = connection.execute("SELECT file,sha256 FROM cards WHERE episode=? AND kind='script' "
                                  "AND status='accepted' ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if not card or not card["file"] or not card["sha256"]:
        raise ValueError("Approve the script before opening it on the selected screen.")
    source = paths.inside(paths.episode_dir(episode), card["file"])
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != card["sha256"]:
        raise ValueError("The approved script changed or is missing. Review it again first.")
    token = project["prompter_token"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid teleprompter token.")
    return {"episode": episode, "token": token, "sha256": card["sha256"]}


def request_open(episode: str) -> dict:
    launch_info(episode)
    directory = paths.inside(paths.state_dir(), "desktop-prompter")
    directory.mkdir(exist_ok=True)
    request = {"id": uuid.uuid4().hex, "episode": episode, "created": time.time(), "status": "pending"}
    target = directory / f"{request['id']}.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(request, handle)
    return {**request, "message": "Requested, not opened yet. Keep the desktop app open and select a screen in Teleprompter."}


def status(request_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("Invalid request id.")
    target = paths.inside(paths.state_dir(), f"desktop-prompter/{request_id}.json")
    value = json.loads(target.read_text())
    if value.get("status") == "pending" and time.time() - value.get("created", 0) > 120:
        return {**value, "status": "failed", "message": "Desktop did not answer within two minutes. Open the app and request again."}
    return value
