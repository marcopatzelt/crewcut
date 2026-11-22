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


def codex_instruction(prompt: str, out: Path, edit: bool = False) -> str:
    start = ("Create exactly one image with your image generation tool by EDITING the attached EDIT BASE image (the first "
             "attached image): keep the person in it exactly as he is, same head, same face, and change what the prompt "
             "says. Never draw it with code. " if edit else
             "Create exactly one image with your image generation tool, in a new image, never an edit of an earlier "
             "one, and never drawn with code. ")
    return (start + "Use the attached reference images as described in the prompt. Format: "
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


def make_codex(prompt: str, refs: list[Path], out: Path, edit: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(config.get("thumbnail", "codex_timeout_minutes", 10)) * 60
    from ..engines.codex import Codex
    started = time.time()
    r = subprocess.run(codex_command(refs), cwd=str(out.parent), capture_output=True, text=True, timeout=timeout,
                       input=codex_instruction(prompt, out, edit), env={**os.environ, **Codex().env()})
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


REFS_FILE = "REFERENCES.json"
ROLE_TEXT = {
    "face": "FACE REFERENCE of the person: draw exactly this person (face shape, eyes, skin, hair, beard); several "
            "face references show the same person from different angles",
    "style": "STYLE REFERENCE of the channel: take only what the prompt names (light on the face, face size, type)",
    "control": "STYLE REFERENCE of the channel's proven style for the control variant: follow its look closely",
    "layout": "LAYOUT EXAMPLE of the format {format}: take the composition, placement, sizes and kind of graphics; "
              "never its person, face, text, logos or colours",
    "result": "RESULT IMAGE from the episode: show it as it is",
    "base": "EDIT BASE: the image to edit. Keep the person exactly as he is (same head, same face, same skin and "
            "hair); change background, layout, text, graphics and pose only as the prompt says",
}


def variant_of(episode_dir: Path, prompt: Path, out: Path | None) -> dict:
    """The SET.json variant a prompt belongs to (same prompt file or same variant folder), or {}."""
    for folder in [d for d in (out, prompt.parent, prompt.parent.parent) if d is not None]:
        plan = folder / "SET.json"
        if not plan.is_file():
            continue
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        for v in data.get("variants") or []:
            vp = folder / str(v.get("prompt") or "-")
            vi = folder / str(v.get("image") or "-")
            if vp.resolve() == prompt.resolve() or (out is not None and vi.parent.resolve() == out.resolve()):
                return v
    return {}


def reference_plan(episode: str, references: list[str], fmt: str | None = None, role: str | None = None,
                   pack=None, library: dict | None = None, base: Path | None = None) -> list[tuple[Path, str]]:
    """The images for one variant, in order, each with its role.

    Face references first (the reference photo plus `thumbnail.identity.references`), so the person stays the person.
    Then by the variant's format: a pro format attaches its example image(s) from the format library as the layout
    example and not the house thumbnail; a house format and the control variant attach the style reference
    (`thumbnail.control.reference` for the control when the pack names one). Then the episode's result images."""
    from . import formats as fmts
    from . import identity
    pack = pack or brand.load()
    out: list[tuple[Path, str]] = []
    if base is not None:
        out.append((base, "base"))
    if pack.value("thumbnail.face", True) is not False:
        rel = pack.value("thumbnail.reference_photo")
        if rel:
            photo = paths.inside(paths.brand_dir(), rel)
            if not photo.is_file():
                raise FileNotFoundError("The style pack's reference_photo image is missing.")
        faces = identity.reference_paths(pack)[: int(identity.settings(pack)["max_references"])]
        out += [(f, "face") for f in faces]
    f = None
    if fmt:
        library = library if library is not None else fmts.load(pack)
        f = library.get(fmt)
        if f is None:
            raise ValueError(f"Format {fmt!r} is not in the format library (crewcut thumbnail formats).")
    if role == "control":
        rel = pack.value("thumbnail.control.reference") or pack.value("thumbnail.style_reference")
        if rel:
            out.append((paths.inside(paths.brand_dir(), rel), "control"))
    elif f is not None and f.get("kind") == "pro":
        examples = [Path(f["dir"]) / r for r in (f.get("images") or [])]
        if not examples:
            raise FileNotFoundError(f"The pro format {fmt!r} has no example image in the library; add one first.")
        out += [(e, "layout") for e in examples]
    else:
        rel = pack.value("thumbnail.style_reference")
        if rel:
            out.append((paths.inside(paths.brand_dir(), rel), "style"))
    for p, r in out:
        if not p.is_file():
            raise FileNotFoundError(f"A {r} image is missing: {p.name}.")
    for rel in references:
        image = paths.inside(paths.episode_dir(episode), rel)
        if not image.is_file():
            raise FileNotFoundError("An episode reference image is missing.")
        out.append((image, "result"))
    seen, unique = set(), []
    for p, r in out:
        if p not in seen:
            seen.add(p)
            unique.append((p, r))
    return unique


def reference_images(episode: str, references: list[str], fmt: str | None = None, role: str | None = None) -> list[Path]:
    return [p for p, _ in reference_plan(episode, references, fmt, role)]


def roles_header(plan: list[tuple[Path, str]], format_name: str | None = None) -> str:
    lines = ["ATTACHED IMAGES, in this order (this list wins over any image numbers below):"]
    for i, (p, r) in enumerate(plan, 1):
        lines.append(f"{i}. {p.name}: " + ROLE_TEXT[r].format(format=format_name or "of this variant"))
    return "\n".join(lines)


def record_references(outdir: Path, made: list[Path], plan: list[tuple[Path, str]], fmt: str | None,
                      role: str | None, kind: str | None) -> Path:
    """Append this run to the variant folder's REFERENCES.json, so the set check and the card show what was used."""
    f = outdir / REFS_FILE
    data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"runs": []}
    data["runs"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "format": fmt, "kind": kind, "role": role,
                         "images": [m.name for m in made],
                         "references": [{"file": p.name, "path": str(p), "role": r} for p, r in plan]})
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return f


def cli(a) -> int:
    episode = a.episode or os.environ.get("CREWCUT_EPISODE")
    if not episode:
        print("crewcut thumbnail make: which episode? Use --episode.")
        return 2
    ep = paths.episode_dir(episode)
    prompt_file = paths.inside(ep, a.prompt)
    prompt = prompt_file.read_text(encoding="utf-8").strip()
    outdir = paths.inside(ep, a.out or "graphics/thumbnail")
    variant = variant_of(ep, prompt_file, outdir if a.out else None)
    fmt = getattr(a, "format", None) or variant.get("format")
    role = "control" if (getattr(a, "control", False) or variant.get("role") == "control") else None
    try:
        from . import formats as fmts
        library = fmts.load()
        base = paths.inside(ep, a.edit) if getattr(a, "edit", None) else None
        plan = reference_plan(episode, a.ref, fmt, role, library=library, base=base)
    except (FileNotFoundError, ValueError) as error:
        print(str(error))
        return 1
    refs = [p for p, _ in plan]
    fdef = library.get(fmt) if fmt else None
    prompt = roles_header(plan, (fdef or {}).get("name")) + "\n\n" + prompt
    print("References: " + ", ".join(f"{p.name} ({r})" for p, r in plan))
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
    gate, tries = identity_gate(a)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    made, rejected = [], []
    for i in range(n):
        for t in range(tries):
            out = outdir / f"{stamp}-{way}-{i + 1}" f"{'' if t == 0 else f'-try{t + 1}'}.png"
            try:
                if way == "codex":
                    make_codex(prompt, refs, out, edit=base is not None)
                else:
                    make_api(prompt, refs, out)
            except (RuntimeError, subprocess.TimeoutExpired, NoWay) as e:
                print(f"Image {i + 1} failed: {e}")
                break
            if way == "api":
                ledger.add("api", float(config.get("thumbnail", "api_price_per_image_usd", 0.2)),
                           "thumbnail image (API)", episode=episode, step="thumbnail", ref=str(out.relative_to(ep)))
            face = gate.measure(out) if gate else None
            if face is None or face["ok"]:
                made.append(out)
                if face:
                    print(f"Face OK ({face['similarity']:.2f}): {out.relative_to(ep)}")
                break
            moved = out.with_name(out.stem + "-wrong-face.png")
            out.replace(moved)
            rejected.append(moved)
            print(f"Face wrong ({face.get('similarity')}), try {t + 1} of {tries}: {face['problem']}")
    if made or rejected:
        record_references(outdir, made + rejected, plan, fmt, role, (fdef or {}).get("kind"))
    for m in made:
        print(m.relative_to(ep))
    if rejected and not made:
        print("Every try had the wrong face. Add a face reference close to the wanted pose and expression, try an "
              "edit of an image with the right face (--edit), or use the real-photo fallback (crewcut thumbnail face).")
    return 0 if made else 1


def identity_gate(a):
    """The identity gate for each new image, and how many tries a wrong face gets (`thumbnail.identity.tries`)."""
    from . import identity
    pack = brand.load()
    if getattr(a, "no_face_check", False) or not identity.enabled(pack):
        return None, 1
    tries = max(1, int(getattr(a, "tries", None) or identity.settings(pack)["tries"]))
    try:
        return identity.Gate.for_pack(pack), tries
    except identity.Unavailable as e:
        print(f"Face check not possible here ({e}); `crewcut thumbnail set check` checks the face later.")
        return None, 1
