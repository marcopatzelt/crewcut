"""Media browsing and copying through the desktop, with no arbitrary host commands."""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid

from . import episodes, paths


def status(request_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("Invalid request ID.")
    target = paths.inside(paths.state_dir(), f"desktop-media/{request_id}.json")
    value = json.loads(target.read_text())
    if value.get("status") == "pending" and time.time() - value.get("created", 0) > 120:
        return {**value, "status": "failed", "message": "Open the Crewcut desktop app and submit the request again."}
    return value


def request(action: str, **fields) -> dict:
    if action not in {"sources", "list", "import"}:
        raise ValueError("Unknown media action.")
    if action == "import":
        episodes.read(fields["episode"])
    directory = paths.inside(paths.state_dir(), "desktop-media")
    directory.mkdir(exist_ok=True)
    item = {**fields, "id": uuid.uuid4().hex, "action": action, "created": time.time(), "status": "pending"}
    target = directory / f"{item['id']}.json"
    temporary = target.with_suffix(".tmp")
    with temporary.open("x") as handle:
        json.dump(item, handle)
    temporary.rename(target)
    return item


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crewcut media")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("sources", help="find media folders and connected cards")
    listing = sub.add_parser("list")
    listing.add_argument("source")
    listing.add_argument("--path", default="")
    listing.add_argument("--offset", type=int, default=0)
    importing = sub.add_parser("import", help="copy one media file into an episode inbox")
    importing.add_argument("episode")
    importing.add_argument("source")
    importing.add_argument("path")
    checking = sub.add_parser("status")
    checking.add_argument("id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = vars(build_parser().parse_args(argv))
    action = args.pop("action")
    try:
        item = status(args["id"]) if action == "status" else request(action, **args)
        if action != "status":
            until = time.monotonic() + 5
            while item["status"] in {"pending", "running"} and time.monotonic() < until:
                time.sleep(0.1)
                item = status(item["id"])
        if item["status"] == "pending":
            item["message"] = "Waiting for the desktop app. Keep it open and check this request ID."
        print(json.dumps(item, ensure_ascii=False))
        return 1 if item["status"] == "failed" else 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}))
        return 1
