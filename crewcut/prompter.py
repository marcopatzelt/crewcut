"""The web teleprompter: the approved script on any phone in the same network, opened from a QR code."""

from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

from . import config, db, episodes, paths

DEFAULT_CONTROL = {"playing": False, "speed": 1.0, "position": 0.0, "mirror": False, "size": 1.0, "mode": "full"}


def lan_host() -> str:
    return os.environ.get("CREWCUT_LAN_HOST") or "localhost"


def url_for(episode: str) -> str:
    token = episodes.read(episode)["prompter_token"]
    port = int(os.environ.get("CREWCUT_PUBLIC_PROMPTER_PORT") or os.environ.get("CREWCUT_PROMPTER_PORT") or
               config.get("crewcut", "server.prompter_port", 4748))
    return f"http://{lan_host()}:{port}/p/{token}"


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding="unicode")


def script_file(episode: str) -> Path | None:
    """The approved script if there is one, else the newest script draft."""
    d = paths.episode_dir(episode)
    with db.conn() as c:
        r = c.execute("SELECT file FROM cards WHERE episode = ? AND kind = 'script' AND status = 'accepted' "
                      "ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if r and r["file"]:
        p = paths.inside(d, r["file"])
        if p.is_file():
            return p
    selected = episodes.read(episode).get("recording_script")
    if selected:
        selected_path = paths.inside(d, selected["file"])
        if not selected_path.is_file():
            raise FileNotFoundError("The selected recording script is missing. Select another script explicitly.")
        return selected_path
    drafts = sorted((d / "brief").glob("SCRIPT-v*.md"))
    return drafts[-1] if drafts else None


def select_script(episode: str, relative: str, partial: bool = False) -> dict:
    root = paths.episode_dir(episode)
    selected = paths.inside(root, relative)
    if selected.suffix.lower() not in (".md", ".txt") or not selected.is_file():
        raise ValueError("Select an existing Markdown or text script inside this episode.")
    with db.conn() as connection:
        approved = connection.execute("SELECT file FROM cards WHERE episode = ? AND kind = 'script' "
                                      "AND status = 'accepted' ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if approved and approved["file"] and paths.inside(root, approved["file"]) != selected:
        raise ValueError("Another script is approved. Request a new script review before replacing it.")
    project = episodes.read(episode)
    project["recording_script"] = {"file": selected.relative_to(root).as_posix(), "partial": partial}
    episodes.write(episode, project)
    return project["recording_script"]


def _points(par: str, n: int = 8) -> list[str]:
    bold = re.findall(r"\*\*(.+?)\*\*", par)
    if bold:
        return bold[:3]
    words = re.sub(r"[*_`#>]", "", par).split()
    return [" ".join(words[:n]) + (" …" if len(words) > n else "")]


def parse_script(text: str) -> list[dict]:
    """Blocks for the teleprompter. Everything after the first line that is only `---` is notes for the edit."""
    m = re.search(r"(?m)^---\s*$", text)
    if m and text[:m.start()].strip():
        text = text[:m.start()]
    blocks = []
    for par in re.split(r"\n\s*\n", text):
        par = par.strip()
        if not par or par.startswith("<!--"):
            continue
        if par.startswith("#"):
            heading = par.lstrip("#").strip()
            blocks.append({"text": heading, "points": [heading], "heading": True})
            continue
        clean = re.sub(r"[*_`>]", "", par)
        clean = re.sub(r"^\s*-\s+", "", clean, flags=re.M)
        blocks.append({"text": " ".join(clean.split()), "points": _points(par)})
    return blocks


def script(episode: str) -> dict:
    p = script_file(episode)
    project = episodes.read(episode)
    if p is None:
        return {"title": project.get("title"), "mode": "full", "blocks": [],
                "note": "No script yet. The Writer makes one in step 4."}
    relative = str(p.relative_to(paths.episode_dir(episode)))
    selected = project.get("recording_script") or {}
    partial = selected.get("file") == relative and selected.get("partial", False)
    return {"title": project.get("title"), "mode": control(episode).get("mode", "full"),
            "blocks": parse_script(p.read_text(encoding="utf-8")), "file": relative,
            "note": "Partial script. The remaining sections are not ready." if partial else None}


def control(episode: str) -> dict:
    raw = db.kv_get(f"prompter:{episode}")
    d = dict(DEFAULT_CONTROL)
    if raw:
        try:
            d.update(json.loads(raw))
        except ValueError:
            pass
    return d


def set_control(episode: str, values: dict) -> dict:
    d = control(episode)
    for k, v in values.items():
        if k not in DEFAULT_CONTROL:
            continue
        if k in ("playing", "mirror"):
            d[k] = bool(v)
        elif k == "mode":
            d[k] = "points" if v == "points" else "full"
        else:
            lo, hi = {"speed": (0.2, 4.0), "position": (0.0, 1.0), "size": (0.5, 3.0)}[k]
            d[k] = max(lo, min(hi, float(v)))
    db.kv_set(f"prompter:{episode}", json.dumps(d))
    return d


def terminal_qr(text: str) -> str:
    import qrcode
    q = qrcode.QRCode(border=1)
    q.add_data(text)
    q.make()
    buf = io.StringIO()
    q.print_ascii(out=buf, invert=True)
    return buf.getvalue()
