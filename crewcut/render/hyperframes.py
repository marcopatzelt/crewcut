"""HyperFrames building blocks: HTML compositions rendered to transparent frames by HeyGen's HyperFrames (Apache-2.0).

A HyperFrames template is a folder in ``templates/hyperframes/<name>/`` (a style pack may hold its own in
``brand/templates/hyperframes/<name>/``, which wins): ``index.html`` (a HyperFrames composition), ``template.json``
(title, graphic type, kind, formats, params with defaults, cues) and optional files it needs. The edit plan uses one
as a 2D insert whose scene is ``hf-<name>``:

    {"id": "k1", "kind": "2d", "scene": "hf-keyword", "transparent": true, "start": {"word": "Kosten"}, "end": 14.2,
     "cues": {"land": {"word": "dreißig"}}, "data": {"words": ["30 Cent"], "accent": 0}}

What Crewcut does per insert (``render_insert``):

1. a project folder ``render/hyperframes-work/<id>-<hash>/``: the template's files, the pack's font files in
   ``assets/fonts/``, and ``index.html`` with the composition's size and length set to the insert's (its frames plus
   the two extra frames every 2D insert renders) and one inlined head block: the studio style as CSS variables
   (``crewcut.motion.studio_style``: four colours, the display and body font with ``@font-face`` rules for the files,
   the entrance curve), ``window.CC_DATA`` (params, cues in seconds, format, size, fps, face box, safe areas) and the
   helper ``templates/hyperframes/_lib/cc.js``;
2. ``hyperframes render <project> --format png-sequence --fps <plan fps>`` (RGBA PNGs; Chrome screenshots with a
   transparent page background), telemetry and update checks off, the Chrome sandbox off (a container), the browser
   from ``HYPERFRAMES_BROWSER_PATH`` or the image's pinned ``/opt/hyperframes/chrome-headless-shell``;
3. the frames, renamed ``0000.png`` ... into ``render/inserts/<id>-<hash>/`` like every 2D insert, checked for count
   and size; the 2D encoder then makes the clip (QuickTime Animation with alpha for overlays, H.264 for full frame).

The HyperFrames version is pinned in ``tools/hyperframes/package.json`` (and its lock file); the image installs it
with ``npm ci``. Without the program a HyperFrames insert stops with one sentence; every other insert still renders.
Nothing here downloads at render time: GSAP comes from the copy inside the HyperFrames package, fonts from the pack.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import brand, paths
from ..motion import studio_style
from . import media

PREFIX = "hf-"
LIB = "_lib"
KINDS = ("overlay", "full")
TYPES = {"a": "keyword or number beside the speaker", "b": "card (definition, name)", "c": "chapter card",
         "d": "calm diagram", "e": "chat or code snippet"}
IMAGE_BROWSER = Path("/opt/hyperframes/chrome-headless-shell")
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
_HEAD = "<!--CC:HEAD-->"


class HyperFramesError(RuntimeError):
    """A HyperFrames insert cannot render. The message is one sentence for the user."""


class HyperFramesMissing(HyperFramesError):
    def __init__(self) -> None:
        super().__init__("HyperFrames is not installed here, so HyperFrames inserts (scene hf-...) cannot render "
                         "(everything else works): use the Crewcut image, or run `npm ci` in tools/hyperframes.")


# ---- the program --------------------------------------------------------------------------------------------------
def tool_dir() -> Path:
    return paths.tools_dir() / "hyperframes"


def pinned_version() -> str:
    """The HyperFrames version in tools/hyperframes/package.json (an exact version, never a range)."""
    try:
        deps = json.loads((tool_dir() / "package.json").read_text(encoding="utf-8")).get("dependencies") or {}
    except (OSError, ValueError):
        return "unknown"
    return str(deps.get("hyperframes") or "unknown")


def cli() -> str:
    """The ``hyperframes`` program: env CREWCUT_HYPERFRAMES, else tools/hyperframes/node_modules/.bin/hyperframes."""
    env = os.environ.get("CREWCUT_HYPERFRAMES")
    if env:
        return env
    p = tool_dir() / "node_modules" / ".bin" / "hyperframes"
    if p.exists():
        return str(p)
    found = shutil.which("hyperframes")
    if found:
        return found
    raise HyperFramesMissing()


def available() -> bool:
    try:
        cli()
        return True
    except HyperFramesMissing:
        return False


def browser() -> str | None:
    """Chrome for HyperFrames: env HYPERFRAMES_BROWSER_PATH, the image's pinned headless shell, else Playwright's
    headless shell in PLAYWRIGHT_BROWSERS_PATH; None lets HyperFrames look for itself."""
    env = os.environ.get("HYPERFRAMES_BROWSER_PATH")
    if env and Path(env).exists():
        return env
    if IMAGE_BROWSER.exists():
        return str(IMAGE_BROWSER)
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "/opt/ms-playwright")
    if root.is_dir():
        for name in ("chrome-headless-shell", "headless_shell"):
            hits = sorted(root.glob(f"*/*/{name}")) + sorted(root.glob(f"*/{name}"))
            for h in hits:
                if h.is_file() and os.access(h, os.X_OK):
                    return str(h)
    return None


def env() -> dict[str, str]:
    """The environment of every HyperFrames process: no telemetry, no update check, no Chrome sandbox (Crewcut runs it
    in a container or a CI runner), our ffmpeg, and the browser when one is known."""
    out = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
           "HYPERFRAMES_CHROME_SANDBOX": os.environ.get("HYPERFRAMES_CHROME_SANDBOX", "0"),
           "HYPERFRAMES_FFMPEG_PATH": media.ffmpeg(), "HYPERFRAMES_FFPROBE_PATH": media.ffprobe(), "CI": "1"}
    b = browser()
    if b:
        out["HYPERFRAMES_BROWSER_PATH"] = b
    cache = paths.state_dir() / "cache" / "hyperframes-fonts"
    out.setdefault("HYPERFRAMES_FONT_CACHE_DIR", str(cache))
    return out


def runner_with_env(runner: media.Runner) -> media.Runner:
    """``media.run`` with the HyperFrames environment (tests pass their own runner and get the plain call)."""
    if runner is not media.run:
        return runner

    def run(cmd: list[str], timeout: float = 600, cwd: Path | str | None = None) -> tuple[int, str]:
        import subprocess
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd, env=env())
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout:.0f} s"
        except OSError as e:
            return 127, str(e)
        out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
        return p.returncode, out
    return run


# ---- templates ----------------------------------------------------------------------------------------------------
def template_dirs(pack: brand.Pack | None = None) -> list[Path]:
    """Where templates live: the pack's brand/templates/hyperframes/ first (it wins), then the app's."""
    pack = pack or brand.load()
    out = [] if pack.is_neutral else [Path(pack.dir) / "templates" / "hyperframes"]
    return [*out, paths.templates_dir() / "hyperframes"]


def lib_files() -> list[Path]:
    d = paths.templates_dir() / "hyperframes" / LIB
    return sorted(p for p in d.iterdir() if p.is_file()) if d.is_dir() else []


def name_of(scene: str) -> str | None:
    """``hf-keyword`` -> ``keyword``; None for a scene that is no HyperFrames template."""
    if not isinstance(scene, str) or not scene.startswith(PREFIX):
        return None
    n = scene[len(PREFIX):]
    return n if _NAME.match(n) and n != LIB else None


def find(name: str, pack: brand.Pack | None = None) -> Path:
    for d in template_dirs(pack):
        f = d / name / "index.html"
        if f.is_file() and (d / name / "template.json").is_file():
            return f.parent
    names = sorted(x["name"] for x in listing(pack))
    raise HyperFramesError(f"no HyperFrames template '{name}'. Available: "
                           f"{', '.join(PREFIX + n for n in names) or 'none'}")


def manifest(folder: Path) -> dict:
    try:
        m = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HyperFramesError(f"{folder.name}/template.json cannot be read: {e}") from e
    if not isinstance(m, dict) or m.get("kind") not in KINDS or not isinstance(m.get("params"), dict):
        raise HyperFramesError(f"{folder.name}/template.json needs kind (overlay or full) and params")
    return m


def template_files(name: str, pack: brand.Pack | None = None) -> tuple[Path, tuple[Path, ...]]:
    """index.html and every other file the template needs (its folder and the shared lib), for the cache hash."""
    folder = find(name, pack)
    own = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "index.html")
    return folder / "index.html", (*own, *lib_files())


def listing(pack: brand.Pack | None = None) -> list[dict]:
    """Every template (the pack's win over the app's of the same name), with its manifest."""
    seen: dict[str, dict] = {}
    app = (paths.templates_dir() / "hyperframes").resolve()
    for d in template_dirs(pack):
        if not d.is_dir():
            continue
        origin = "app" if d.resolve() == app else "pack"
        for f in sorted(d.glob("*/template.json")):
            if f.parent.name == LIB or f.parent.name in seen:
                continue
            try:
                m = manifest(f.parent)
            except HyperFramesError:
                continue
            seen[f.parent.name] = {"name": f.parent.name, "scene": PREFIX + f.parent.name, "origin": origin,
                                   "folder": str(f.parent), **{k: m.get(k) for k in
                                   ("title", "type", "kind", "formats", "description", "params", "cues",
                                    "length_s")}}
    return list(seen.values())


def merge_params(m: dict, data: dict) -> dict:
    """The template's defaults with the plan's data over them. Unknown keys are refused (a typo never goes silent);
    the workbench's own keys (format, frames, fps, cues, scene_contract) pass."""
    own = {"format", "frames", "fps", "cues", "scene_contract", "example"}
    bad = sorted(k for k in data if k not in m["params"] and k not in own)
    if bad:
        raise HyperFramesError(f"{', '.join(bad)} is not a parameter of this HyperFrames template "
                               f"(parameters: {', '.join(sorted(m['params'])) or 'none'})")
    return {**json.loads(json.dumps(m["params"])), **{k: v for k, v in data.items() if k not in own}}


# ---- one project ----------------------------------------------------------------------------------------------------
def _js(obj: Any) -> str:
    """JSON that is safe inside a <script> element."""
    return (json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def safe_box(fmt: str, size: tuple[int, int], right_free: float | None = None,
             pack: brand.Pack | None = None, transparent: bool = False) -> dict:
    """The box inside the safe areas in pixels. An overlay over the speaker keeps 8 % free at the bottom of a 16:9
    frame (the player bar); in a Short the right strip is at least the plan's ``right_free``."""
    areas = studio_style.safe_area(pack)
    s = dict(areas.get(fmt if fmt in areas else "landscape"))
    if fmt == "portrait" and right_free is not None:
        s["right"] = max(s["right"], float(right_free))
    if fmt == "landscape" and transparent:
        s["bottom"] = max(s["bottom"], 0.08)
    w, h = size
    x, y = round(s["left"] * w), round(s["top"] * h)
    return {"x": x, "y": y, "w": round(w - x - s["right"] * w), "h": round(h - y - s["bottom"] * h)}


def context(*, fmt: str, size: tuple[int, int], fps: int, frames: int, transparent: bool,
            cues: dict[str, float] | None = None, face: dict | None = None, right_free: float | None = None,
            pack: brand.Pack | None = None) -> dict:
    """What a template reads as ``window.CC_DATA`` besides its params (also part of the cache key)."""
    pack = pack or brand.load()
    st = studio_style.resolve(pack)
    portrait = int(size[1]) > int(size[0])
    short_min = pack.value("edit_style.graphics.text.min_px_short")
    min_px = int(short_min) if portrait and isinstance(short_min, (int, float)) and not isinstance(short_min, bool) \
        else st["min_text_px"]
    shapes = ((pack.motion_graphics().get("background") or {}).get("layouts") or {}).get(fmt) or []
    return {"format": fmt, "size": [int(size[0]), int(size[1])], "fps": int(fps), "frames": int(frames),
            "duration": round(frames / fps, 6), "transparent": bool(transparent), "cues": cues or {},
            "face": face, "safe": safe_box(fmt, size, right_free, pack, transparent), "palette": st["palette"],
            "fonts": {r: {"family": v["family"], "weight": v["weight"]} for r, v in st["fonts"].items()},
            "motion": st["motion"], "min_text_px": min_px, "shapes": shapes if isinstance(shapes, list) else []}


def _patch_root(html: str, w: int, h: int, seconds: float) -> str:
    """Set the root composition's (and its clips') size and length; the viewport follows."""
    sec = f"{seconds:.6f}".rstrip("0").rstrip(".")
    html = re.sub(r'data-width="\d+"', f'data-width="{w}"', html)
    html = re.sub(r'data-height="\d+"', f'data-height="{h}"', html)
    html = re.sub(r'(data-duration=")[0-9.]+(")', rf"\g<1>{sec}\g<2>", html)
    html = re.sub(r'<meta name="viewport"[^>]*>', f'<meta name="viewport" content="width={w}, height={h}" />', html)
    return html


def build_project(folder: Path, out: Path, params: dict, ctx: dict, pack: brand.Pack | None = None) -> Path:
    """Write a renderable HyperFrames project for one insert into ``out`` (cleared first). Returns ``out``."""
    pack = pack or brand.load()
    if out.exists():
        shutil.rmtree(out)
    (out / "assets" / "fonts").mkdir(parents=True)
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_file() and rel.name not in ("index.html", "template.json"):
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    urls = {}
    for role, spec in studio_style.fonts(pack).items():
        if spec["files"]:
            f = spec["files"][0]
            shutil.copy2(f, out / "assets" / "fonts" / f.name)
            urls[role] = f"assets/fonts/{f.name}"
    lib = "\n".join(p.read_text(encoding="utf-8") for p in lib_files() if p.suffix == ".js")
    base = "\n".join(p.read_text(encoding="utf-8") for p in lib_files() if p.suffix == ".css")
    head = (f"<style id=\"cc-theme\">\n{studio_style.css(pack, urls)}{base}</style>\n"
            f"<script id=\"cc-data\">window.CC_DATA = {_js({**ctx, 'data': params})};</script>\n"
            f"<script id=\"cc-lib\">\n{lib}\n</script>")
    html = (folder / "index.html").read_text(encoding="utf-8")
    if _HEAD not in html:
        raise HyperFramesError(f"{folder.name}/index.html needs the line {_HEAD} in its <head>")
    html = _patch_root(html, ctx["size"][0], ctx["size"][1], ctx["duration"]).replace(_HEAD, head)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "hyperframes.json").write_text(json.dumps({"crewcut": True, "template": folder.name}) + "\n",
                                          encoding="utf-8")
    return out


def render_cmd(project: Path, frames_out: Path, fps: int, workers: int = 1, start: float | None = None,
               end: float | None = None) -> list[str]:
    cmd = [cli(), "render", str(project), "--format", "png-sequence", "-o", str(frames_out), "--fps", str(fps),
           "--quality", "high", "--workers", str(max(1, workers))]
    if start is not None:
        cmd += ["--start", f"{start:.4f}"]
    if end is not None:
        cmd += ["--end", f"{end:.4f}"]
    return cmd


def lint_cmd(project: Path) -> list[str]:
    return [cli(), "lint", str(project), "--json"]


_FRAME = re.compile(r"(\d+)\.png$")


def collect(src: Path, dst: Path, want: int, size: tuple[int, int], first: int = 0) -> list[int]:
    """HyperFrames' ``frame_000001.png`` ... (in order) into ``dst`` as ``0000.png`` ...; only valid PNGs of the
    right size. Returns the frame numbers written."""
    files = sorted((f for f in src.rglob("*.png") if _FRAME.search(f.name)), key=lambda f: int(_FRAME.search(f.name)[1]))
    dst.mkdir(parents=True, exist_ok=True)
    got = []
    for i, f in enumerate(files[:want]):
        n = first + i
        if not media.valid_png(f, size):
            continue
        f.replace(dst / f"{n:04d}.png")
        got.append(n)
    return got


def workers() -> int:
    """Browsers at the same time: one per 4 cores, at most 4 (each Chrome takes about 0.5 to 1 GB)."""
    from .motion import cpu_count
    return max(1, min(4, cpu_count() // 4))


def render_project(project: Path, out_dir: Path, *, fps: int, frames: int, size: tuple[int, int],
                   runner: media.Runner = media.run, log: Callable = print, first: int = 0,
                   start: float | None = None, end: float | None = None, label: str = "hyperframes") -> bool:
    """Render a built project into ``out_dir`` as ``NNNN.png`` (from ``first``). True when every frame is there."""
    tmp = project.parent / f"{project.name}-frames"
    if tmp.exists():
        shutil.rmtree(tmp)
    run = runner_with_env(runner)
    rc, text = run(render_cmd(project, tmp, fps, workers(), start, end), timeout=max(600, frames * 6))
    got = collect(tmp, out_dir, frames, size, first) if tmp.is_dir() else []
    if len(got) == frames - 1 and got:                 # a renderer that drops the very last frame: hold the one before
        shutil.copy2(out_dir / f"{got[-1]:04d}.png", out_dir / f"{got[-1] + 1:04d}.png")
        got.append(got[-1] + 1)
    shutil.rmtree(tmp, ignore_errors=True)
    if rc or len(got) < frames:
        log(f"{label}: failed ({len(got)} of {frames} frames): {media.tail(text, 600)}")
        return False
    return True


# ---- inserts of an edit plan ----------------------------------------------------------------------------------------
def is_hf(ins: Any) -> bool:
    return getattr(ins, "kind", None) == "2d" and name_of(getattr(ins, "scene", "") or "") is not None


def hash_extra(pack: brand.Pack) -> list[str]:
    """Cache key parts of every HyperFrames insert: the pinned version and the resolved studio style."""
    st = studio_style.resolve(pack)
    fonts = []
    for spec in studio_style.fonts(pack).values():
        for f in spec["files"]:
            fonts.append(f"{f.name}:{f.stat().st_size}")
    return [f"hyperframes:{pinned_version()}", json.dumps(st, sort_keys=True, ensure_ascii=False), *fonts]


def insert_context(plan: Any, ins: Any) -> dict:
    """CC_DATA of one insert: the plan's format and size, the insert's frames, cues in seconds, the face box on overlays."""
    face = None
    if ins.transparent:
        x, y, w, h = plan.face_box()
        face = {"x": x, "y": y, "w": w, "h": h}
    cues = {k: round(v / plan.fps, 4) for k, v in (ins.cues or {}).items()}
    ctx = context(fmt=plan.format, size=tuple(plan.size), fps=plan.fps, frames=ins.render_frames,
                  transparent=ins.transparent, cues=cues, face=face, right_free=plan.right_free, pack=plan.pack)
    ctx["backdrop_luma"] = None
    if ins.transparent:
        try:
            from .motion import speaker_luma
            ctx["backdrop_luma"] = speaker_luma(plan, ins)
        except Exception:  # noqa: BLE001 - without the picture the template takes light type
            ctx["backdrop_luma"] = None
    return ctx


def work_dir(plan: Any, ins: Any) -> Path:
    return plan.episode_dir / "render" / "hyperframes-work" / f"{ins.id}-{ins.hash}"


def render_insert(plan: Any, ins: Any, runner: media.Runner = media.run, log: Callable = print) -> bool:
    """Render the frames of one HyperFrames insert (all of them when any is missing)."""
    if not plan.missing(ins):
        return True
    try:
        folder = find(name_of(ins.scene), plan.pack)
        params = merge_params(manifest(folder), ins.data)
        project = build_project(folder, work_dir(plan, ins) / "project", params, insert_context(plan, ins), plan.pack)
        ok = render_project(project, ins.out_dir, fps=plan.fps, frames=ins.render_frames, size=tuple(plan.size),
                            runner=runner, log=log, label=f"2d {ins.id} ({ins.scene})")
    except HyperFramesError as e:
        log(f"2d {ins.id} ({ins.scene}): {e}")
        return False
    if ok:
        log(f"2d {ins.id} ({ins.scene}): {ins.render_frames} frames (HyperFrames {pinned_version()})")
    return ok and not plan.missing(ins)


def still(plan: Any, ins: Any, frame: int, out_dir: Path, runner: media.Runner = media.run,
          scale: float = 0.5) -> Path | None:
    """One frame of a HyperFrames insert into out_dir as <id>-<frame>.png (probe and style frame)."""
    try:
        folder = find(name_of(ins.scene), plan.pack)
        params = merge_params(manifest(folder), ins.data)
        work = out_dir / f".{ins.id}-{frame:04d}-hf"
        project = build_project(folder, work / "project", params, insert_context(plan, ins), plan.pack)
    except HyperFramesError:
        return None
    t = frame / plan.fps
    tmp = work / "out"
    src = tmp / f"{frame:04d}.png"
    dst = out_dir / f"{ins.id}-{frame:04d}.png"
    try:
        ok = render_project(project, tmp, fps=plan.fps, frames=1, size=tuple(plan.size), runner=runner,
                            log=lambda *_: None, first=frame, start=t, end=t + 1 / plan.fps)
        if not ok or not src.is_file():
            return None
        from PIL import Image
        with Image.open(src) as im:
            im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS).save(dst)
        return dst
    except Exception:
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def sample(name: str, out: Path, *, fmt: str = "landscape", seconds: float | None = None, fps: int | None = None,
           data: dict | None = None, transparent: bool | None = None, at: float | None = None,
           pack: brand.Pack | None = None, runner: media.Runner = media.run, log: Callable = print) -> dict:
    """Render one template outside a plan: frames into ``out/frames`` (or one still at ``at`` seconds into
    ``out/still.png``). The studio style comes from the active pack."""
    pack = pack or brand.load()
    folder = find(name, pack)
    m = manifest(folder)
    fps = int(fps or studio_style.fps(pack))
    secs = float(seconds or (m.get("length_s") or [3.0])[-1])
    size = (1920, 1080) if fmt == "landscape" else (1080, 1920)
    transp = m["kind"] == "overlay" if transparent is None else bool(transparent)
    frames = max(1, round(secs * fps))
    cues = {k: float(v) for k, v in (m.get("example_cues") or {}).items()}
    for k, v in ((data or {}).pop("cues", None) or {}).items():
        cues[k] = float(v)
    params = merge_params(m, data or {})
    ctx = context(fmt=fmt, size=size, fps=fps, frames=frames, transparent=transp, cues=cues,
                  face={"x": 0.34, "y": 0.36, "w": 0.30, "h": 0.30} if transp else None, pack=pack)
    out.mkdir(parents=True, exist_ok=True)
    project = build_project(folder, out / "project", params, ctx, pack)
    if at is not None:
        n = min(frames - 1, max(0, round(at * fps)))
        ok = render_project(project, out / "still", fps=fps, frames=1, size=size, runner=runner, log=log,
                            first=n, start=n / fps, end=(n + 1) / fps, label=f"hf-{name}")
        f = out / "still" / f"{n:04d}.png"
        if ok and f.is_file():
            f.replace(out / "still.png")
            shutil.rmtree(out / "still", ignore_errors=True)
        return {"ok": ok and (out / "still.png").is_file(), "still": str(out / "still.png"), "frame": n,
                "project": str(project), "size": list(size), "transparent": transp}
    ok = render_project(project, out / "frames", fps=fps, frames=frames, size=size, runner=runner, log=log,
                        label=f"hf-{name}")
    return {"ok": ok, "frames": str(out / "frames"), "count": frames, "project": str(project), "size": list(size),
            "transparent": transp, "fps": fps}


def alpha_report(png: Path) -> dict:
    """Size, mode and alpha of one frame: share of fully transparent and of opaque pixels."""
    from PIL import Image
    with Image.open(png) as im:
        mode = im.mode
        size = im.size
        if "A" not in im.getbands():
            return {"size": list(size), "mode": mode, "alpha": False, "transparent_share": 0.0, "opaque_share": 1.0}
        a = im.getchannel("A")
        hist = a.histogram()
        n = sum(hist)
        return {"size": list(size), "mode": mode, "alpha": True, "transparent_share": round(hist[0] / n, 4),
                "opaque_share": round(hist[255] / n, 4)}


def digest(project: Path) -> str:
    h = hashlib.sha1()
    for p in sorted(project.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(project).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]
