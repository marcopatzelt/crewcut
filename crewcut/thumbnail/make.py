"""Make thumbnail images from one complete prompt and the reference images.

Way A, Codex: runs the user's own Codex CLI image tool, one new session per image (like a new ChatGPT
chat), with the reference images attached and the prompt on stdin. Generated artifacts are recovered
from Codex's image folder when its workspace sandbox cannot copy them to the requested output.
Way B, image API: the user's OpenAI key, paid per image, always behind a spend card.
The method (layouts, one complete new prompt per image, never an edit, checks) lives in skills/thumbnail/.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .. import approvals, brand, config, ledger, paths


class NoWay(RuntimeError):
    pass


def available_ways() -> list[str]:
    from ..engines.codex import Codex
    ways = []
    if shutil.which("codex") and Codex().login_status()[0]:
        ways.append("codex")
    if os.environ.get("OPENAI_API_KEY"):
        ways.append("api")
    return ways


def choose_way(asked: str | None) -> str:
    want = asked or config.get("thumbnail", "way", "auto")
    ways = available_ways()
    if want != "auto":
        if want not in ways:
            raise NoWay(f"The {want} way is not set up: " + ("install and log in to Codex" if want == "codex" else
                        "put OPENAI_API_KEY into .env") + ".")
        return want
    if not ways:
        raise NoWay("No image way is set up. Log in to Codex in the container, or put OPENAI_API_KEY into .env.")
    return ways[0]


def codex_instruction(prompt: str, out: Path) -> str:
    return ("Create exactly one image with your image generation tool, in a new image, never an edit of an earlier "
            "one, and never drawn with code. Use the attached reference images as described in the prompt. Format: "
            "16:9 landscape (wide, like 1672x941), a YouTube thumbnail; state this format in your image prompt, "
            "unless the prompt below names another format. "
            f"Save it as {out.name} in the current folder and reply with the file name only.\n\nPROMPT:\n{prompt}")


def codex_command(refs: list[Path]) -> list[str]:
    """The prompt goes through stdin: `--image` takes several values and would swallow a trailing prompt."""
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write",
           "-c", 'approval_policy="never"']
    for r in refs:
        cmd += ["--image", str(r)]
    return cmd


def make_codex(prompt: str, refs: list[Path], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(config.get("thumbnail", "codex_timeout_minutes", 10)) * 60
    from ..engines.codex import Codex
    started = time.time()
    r = subprocess.run(codex_command(refs), cwd=str(out.parent), capture_output=True, text=True, timeout=timeout,
                       input=codex_instruction(prompt, out), env={**os.environ, **Codex().env()})
    if not out.is_file():
        recover_codex_image(r.stdout or "", out, started)
    if not out.is_file():
        last = (last_codex_message(r.stdout or "") or r.stderr or "").strip()[-300:]
        raise RuntimeError(f"Codex did not save an image (exit {r.returncode}). Its last words: {last}")
    return out


def codex_events(output: str) -> list[dict]:
    events = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def last_codex_message(output: str) -> str:
    texts = [e["item"].get("text", "") for e in codex_events(output)
             if e.get("type") == "item.completed" and isinstance(e.get("item"), dict)
             and e["item"].get("type") == "agent_message"]
    return texts[-1] if texts else output


def recover_codex_image(output: str, out: Path, started: float) -> bool:
    """Retrieve only a new generated-image artifact of this Codex run.

    Codex saves generated images under CODEX_HOME/generated_images/<thread id>/. Its workspace sandbox often cannot
    copy them out (inside a container it cannot start at all), and it does not print the path, so the thread id
    from `--json` finds the folder. A Markdown link in the reply still works as before."""
    from PIL import Image

    from ..engines.codex import codex_home
    root = (Path(codex_home()) / "generated_images").resolve()
    candidates = [Path(link.strip("<>")) for link in re.findall(r"\]\(([^)]+)\)", last_codex_message(output))]
    for event in codex_events(output):
        thread = str(event.get("thread_id") or "") if event.get("type") == "thread.started" else ""
        if re.fullmatch(r"[A-Za-z0-9-]+", thread) and (root / thread).is_dir():
            candidates += sorted((f for f in (root / thread).iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg",
                                                                                           ".webp")),
                                 key=lambda f: f.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if not candidate.is_absolute():
            continue
        candidate = candidate.resolve()
        if root not in candidate.parents or not candidate.is_file() or candidate.stat().st_mtime < started - 2:
            continue
        with Image.open(candidate) as image:
            image.verify()
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(candidate) as image:
            image.save(out, format="PNG")
        return True
    return False


def make_api(prompt: str, refs: list[Path], out: Path, client=None) -> Path:
    import httpx
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise NoWay("OPENAI_API_KEY is not set.")
    model = config.get("thumbnail", "api_model", "gpt-image-2")
    size = config.get("thumbnail", "size", "1536x1024")
    quality = config.get("thumbnail", "api_quality", "high")
    headers = {"Authorization": f"Bearer {key}"}
    own = client is None
    client = client or httpx.Client(timeout=300)
    try:
        if refs:
            files = [("image[]", (r.name, r.read_bytes(), "image/png" if r.suffix == ".png" else "image/jpeg"))
                     for r in refs]
            resp = client.post("https://api.openai.com/v1/images/edits", headers=headers, files=files,
                               data={"model": model, "prompt": prompt, "size": size, "quality": quality, "n": "1"})
        else:
            resp = client.post("https://api.openai.com/v1/images/generations", headers=headers,
                               json={"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1})
        if resp.status_code >= 400:
            raise RuntimeError(f"Image API answered {resp.status_code}: {resp.text[:300]}")
        b64 = resp.json()["data"][0]["b64_json"]
    finally:
        if own:
            client.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(b64))
    return out


def reference_images(episode: str, references: list[str]) -> list[Path]:
    pack = brand.load()
    images = []
    for key in ("reference_photo", "style_reference"):
        if key == "reference_photo" and pack.value("thumbnail.face", True) is False:
            continue
        relative = pack.value(f"thumbnail.{key}")
        if relative:
            image = paths.inside(paths.brand_dir(), relative)
            if not image.is_file():
                raise FileNotFoundError(f"The style pack's {key} image is missing.")
            images.append(image)
    for relative in references:
        image = paths.inside(paths.episode_dir(episode), relative)
        if not image.is_file():
            raise FileNotFoundError("An episode reference image is missing.")
        images.append(image)
    return list(dict.fromkeys(images))


def cli(a) -> int:
    episode = a.episode or os.environ.get("CREWCUT_EPISODE")
    if not episode:
        print("crewcut thumbnail make: which episode? Use --episode.")
        return 2
    ep = paths.episode_dir(episode)
    prompt = paths.inside(ep, a.prompt).read_text(encoding="utf-8").strip()
    try:
        refs = reference_images(episode, a.ref)
    except (FileNotFoundError, ValueError) as error:
        print(str(error))
        return 1
    try:
        way = choose_way(a.way)
    except NoWay as e:
        print(str(e))
        return 4
    n = max(1, min(4, a.variants))
    if way == "api":
        price = float(config.get("thumbnail", "api_price_per_image_usd", 0.2)) * n
        ok, card, reason = approvals.require_spend(
            episode, price, f"Make {n} thumbnail image(s) with the image API for about ${price:.2f}?",
            body="Paid per image with your OpenAI key. Codex on your ChatGPT plan is the free way when it is set up.",
            data={"step": "thumbnail", "kind": "api", "cap_usd": round(price * 1.5, 2)})
        if not ok:
            print(reason + (f" (card #{card})" if card else ""))
            return 3
    outdir = paths.inside(ep, a.out or "graphics/thumbnail")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    made = []
    for i in range(n):
        out = outdir / f"{stamp}-{way}-{i + 1}.png"
        try:
            (make_codex if way == "codex" else make_api)(prompt, refs, out)
        except (RuntimeError, subprocess.TimeoutExpired, NoWay) as e:
            print(f"Image {i + 1} failed: {e}")
            continue
        made.append(out)
        if way == "api":
            ledger.add("api", float(config.get("thumbnail", "api_price_per_image_usd", 0.2)), "thumbnail image (API)",
                       episode=episode, step="thumbnail", ref=str(out.relative_to(ep)))
    for m in made:
        print(m.relative_to(ep))
    return 0 if made else 1
