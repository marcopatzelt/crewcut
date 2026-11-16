"""Make thumbnail images from one complete prompt and the reference images.

Way A, Codex: runs the user's own Codex CLI (its image tool, on the user's ChatGPT plan). Untested inside the
container; see the README roadmap.
Way B, image API: the user's OpenAI key, paid per image, always behind a spend card.
The method (layouts, one complete new prompt per image, never an edit, checks) lives in skills/thumbnail/.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import time
from pathlib import Path

from .. import approvals, config, ledger, paths


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


def codex_command(prompt: str, refs: list[Path], out: Path) -> list[str]:
    instr = ("Create exactly one image with your image generation tool. Use the attached reference images as "
             "described in the prompt. Do not edit an earlier image; generate a new one from the complete prompt. "
             f"Save it as {out.name} in the current folder and reply with the file name only.\n\nPROMPT:\n{prompt}")
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "-c", 'approval_policy="never"']
    for r in refs:
        cmd += ["--image", str(r)]  # untested: attach reference images to the first prompt
    return cmd + [instr]


def make_codex(prompt: str, refs: list[Path], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(config.get("thumbnail", "codex_timeout_minutes", 10)) * 60
    from ..engines.codex import Codex
    r = subprocess.run(codex_command(prompt, refs, out), cwd=str(out.parent), capture_output=True, text=True,
                       timeout=timeout, stdin=subprocess.DEVNULL, env={**os.environ, **Codex().env()})
    if not out.is_file():
        last = (r.stdout or r.stderr).strip()[-300:]
        raise RuntimeError(f"Codex did not save an image (exit {r.returncode}). Its last words: {last}")
    return out


def make_api(prompt: str, refs: list[Path], out: Path, client=None) -> Path:
    import httpx
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise NoWay("OPENAI_API_KEY is not set.")
    model = config.get("thumbnail", "api_model", "gpt-image-1")
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


def cli(a) -> int:
    episode = a.episode or os.environ.get("CREWCUT_EPISODE")
    if not episode:
        print("crewcut thumbnail make: which episode? Use --episode.")
        return 2
    ep = paths.episode_dir(episode)
    prompt = paths.inside(ep, a.prompt).read_text(encoding="utf-8").strip()
    refs = [paths.inside(ep, r) for r in a.ref]
    for r in refs:
        if not r.is_file():
            print(f"Reference image not found: {r.relative_to(ep)}")
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
