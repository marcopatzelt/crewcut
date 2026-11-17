"""The Critic's review bundle for motion inserts: ``review/motion-vNNN/<id>/`` from an edit plan.

One call builds what the Critic reads and looks at (motion plan 3.5); ``main`` is the command line
(``crewcut render motion-review <plan> [--ids m1,m2] [--ref refs/x.mp4 --ref-offset S]``).

Per insert, from the rendered PNG frames (``<episode>/render/inserts/<id>-<hash>/NNNN.png``, newest folder) and the
``.jsx`` text, without the engine:

    sheet.jpg      every 0.25 s of the insert
    compare.jpg    ours next to the reference at matched times; else the library sample or the baseline's frames
    hue.json       hue shares at 5 times (limit 0.30; "natural": true in the data or an end lockup is exempt)
    text.json      text layers with their smallest size on screen (engine), overlay pixels on the face box or
                   outside the safe box (frames), text sizes written in the .jsx (no engine)
    sharp.json     Laplace variance per frame, frame differences, empty frames, frozen holds
    web-look.md    8 frames with the four web-look questions as an empty form (web-look/NN.jpg)
    lint.json      static look at the .jsx (web-look rules are candidates, the Critic decides)
    density.json   the density counts over the whole plan, and this insert's neighbours

With ``effectcraft-cli`` (the Crewcut image or a rented machine): ``strip-in.jpg``, ``strip-out.jpg`` and one strip
per inner transition and cue (60 fps, 30 frames, every 2nd), rendered from the comp at 60 fps; text layer sizes
measured in the engine project. Without the engine these are skipped with a line in the bundle.

At the bundle root: ``critic.md`` (the form the Critic fills: one sentence per big moment on what the reference still
does better, the ratchet, what cannot be checked: sound, with a listening list) and ``bundle.json`` (files, skipped
steps, every machine finding). ``skills/cut-check/scripts/motion_check.py`` prints the findings as ERROR / CHECK
lines and exits 1 on any ERROR.

Nothing here edits the plan or renders the video; the engine is only used for the review strips and text sizes.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .. import brand, paths
from . import density as dens
from . import export, palette
from . import project as proj
from . import templates as tp
from .backend import Backend, BackendError
from .jsx import js, parse_result, wrap_program

LEVELS = ("ERROR", "CHECK", "NOTE", "OK")
FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920), "stage": (1080, 960)}
SHEET_STEP = 0.25                 # s between sheet frames
HUE_AT = (0.1, 0.3, 0.5, 0.7, 0.9)
HUE_LIMIT = 0.30
SHARP_RATIO = 0.35                # a frame below 35 % of the mean Laplace variance is blurry
SHARP_RUN = 3                     # more than 3 blurry frames in a row: error
HOLD_S = 0.5                      # frame difference 0 over 0.5 s: the camera stopped
FROZEN_EPS = 0.01                 # mean absolute difference (0..255) that counts as "no change"
EMPTY_SHARE = 0.003               # under 0.3 % content: an empty frame
OVERLAY_EDGE_S = 0.5              # overlays may be empty this long at the start and the end
FACE_SHARE = 0.01                 # overlay pixels covering more than 1 % of the face box: error
OUTSIDE_SAFE_SHARE = 0.02         # more than 2 % of an overlay's pixels outside the safe box: look at it
STRIP_FPS, STRIP_FRAMES, STRIP_EVERY = 60, 30, 2
WEB_FRAMES = 8
ANALYSIS_SIDE = 640               # frames are measured at this longest side
CELL_W = 480
MAX_ROUNDS = 3
GREY = np.array([128.0, 128.0, 128.0], np.float32)
RATCHET = "A video that is not better than the bar in at least one named way goes back."
WEB_QUESTIONS = (
    "Could it be a screenshot of a web page or an app?",
    "Is there a rounded rectangle with text in it?",
    "Does a word stand in a filled box?",
    "Do all shadows share one shape although the depths differ?",
)
ENGINE_SKIP = ("skipped: effectcraft-cli not found. The 60 fps strips (strip-in, strip-out, one per transition and "
               "cue) and the text sizes from the engine project need it: run the review in the Crewcut image or on "
               "a rented machine.")
LINT_NOTE = ("The web-look rules (rounded-text, box-behind-text) are heuristics: their hits are candidates and the "
             "Critic decides. Size literals, font names, Shatter and Temporal Motion Blur are errors.")


class ReviewError(ValueError):
    """The plan or the arguments cannot be used. The message says what to change."""


# ---------------------------------------------------------------- plan and inserts


@dataclass
class Ctx:
    plan_path: Path
    plan: dict
    episode: Path
    pack: Any
    words: list[dict]
    fps: float
    format: str
    layout: str
    right_free: float
    min_text_px: float
    enter_s: float
    exit_s: float
    limits: dict
    face: Any


@dataclass
class Moment:
    id: str
    raw: dict
    scene: str | None
    source: str | None
    start: float | None
    end: float | None
    transparent: bool
    data: dict
    cues: dict[str, float]
    fmt: str
    size: tuple[int, int]
    frames_dir: Path | None = None
    frames: list[Path] = field(default_factory=list)
    jsx: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def dur(self) -> float:
        if self.start is not None and self.end is not None and self.end > self.start:
            return self.end - self.start
        return 0.0

    @property
    def full(self) -> bool:
        return not self.transparent

    def at(self, local: float) -> float:
        """Video time of a time local to the insert (local time when the start is not known)."""
        return (self.start or 0.0) + local


def load(plan_path: Path | str, pack: Any = None) -> Ctx:
    p = Path(plan_path).resolve()
    if not p.is_file():
        raise ReviewError(f"plan not found: {plan_path}")
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ReviewError(f"plan is not valid JSON: {p.name} ({e})") from e
    if not isinstance(plan, dict):
        raise ReviewError("the plan must be a JSON object")
    ep = p.parent.parent
    pack = pack or brand.load()
    project: dict = {}
    pj = ep / "project.json"
    if pj.is_file():
        try:
            project = json.loads(pj.read_text(encoding="utf-8"))
        except ValueError:
            project = {}
    words: list[dict] = []
    if plan.get("words"):
        wf = ep / plan["words"]
        if wf.is_file():
            try:
                words = dens.norm_words(json.loads(wf.read_text(encoding="utf-8")))
            except ValueError:
                words = []
    es = pack.value("edit_style", {}) or {}
    fmt = plan.get("format") or project.get("format") or es.get("format") or "landscape"
    layout = plan.get("layout") or ((es.get("shorts") or {}).get("layout") if fmt == "portrait" else None) or "full"
    mg = pack.value("brand.motion_graphics", {}) or {}
    return Ctx(
        plan_path=p, plan=plan, episode=ep, pack=pack, words=words,
        fps=float(plan.get("fps") or project.get("fps") or es.get("fps") or 25), format=fmt, layout=layout,
        right_free=float(plan.get("right_free") or (es.get("shorts") or {}).get("right_free_frac") or 0.18),
        min_text_px=float(es.get("min_text_px") or 40), enter_s=float(mg.get("enter_s") or 0.4),
        exit_s=float(mg.get("exit_s") or 0.25), limits=dens.limits(es), face=plan.get("face"),
    )


def newest_frames(episode: Path, iid: str) -> tuple[Path | None, list[Path]]:
    """The newest ``render/inserts/<id>-<hash>/`` folder that holds NNNN.png frames, and its frames in order."""
    root = episode / "render" / "inserts"
    if not root.is_dir():
        return None, []
    best: tuple[float, Path, list[Path]] | None = None
    for d in root.iterdir():
        if not d.is_dir() or not re.fullmatch(re.escape(iid) + r"-[0-9a-f]{6,40}", d.name):
            continue
        files = sorted(f for f in d.iterdir() if re.fullmatch(r"\d{4}\.png", f.name))
        if not files:
            continue
        t = max(f.stat().st_mtime for f in files)
        if best is None or t > best[0]:
            best = (t, d, files)
    return (best[1], best[2]) if best else (None, [])


def _format_of(ctx: Ctx, e: dict, frames: list[Path]) -> tuple[str, tuple[int, int]]:
    if frames:
        from PIL import Image
        with Image.open(frames[0]) as im:
            w, h = im.size
        r = w / h
        return ("landscape" if r >= 1.5 else "portrait" if r <= 0.67 else "stage"), (w, h)
    if ctx.format == "portrait" and ctx.layout == "proof-top" and not e.get("transparent") and e.get("place") != "full":
        return "stage", FORMATS["stage"]
    fmt = ctx.format if ctx.format in FORMATS else "landscape"
    return fmt, FORMATS[fmt]


def jsx_of(ctx: Ctx, e: dict) -> Path | None:
    """The comp source of an insert: the template on the search path (pack copy wins) or the episode's own file."""
    if e.get("source"):
        try:
            p = paths.inside(ctx.episode, str(e["source"]))
        except ValueError:
            return None
        return p if p.is_file() else None
    if e.get("scene"):
        try:
            return tp.template_path(str(e["scene"]))
        except tp.TemplateError:
            return None
    return None


def moments(ctx: Ctx, ids: list[str] | None = None) -> list[Moment]:
    """The plan's motion inserts (``"kind": "motion"``), in plan order, optionally only ``ids``."""
    raw = [e for e in ctx.plan.get("inserts") or [] if isinstance(e, dict) and e.get("kind") == "motion"]
    if ids:
        have = {str(e.get("id")) for e in raw}
        unknown = [i for i in ids if i not in have]
        if unknown:
            raise ReviewError(f"no motion insert with id {', '.join(unknown)} (motion inserts: "
                              f"{', '.join(sorted(have)) or 'none'})")
        raw = [e for e in raw if str(e.get("id")) in ids]
    out = []
    for e in raw:
        iid = str(e.get("id"))
        s, t = dens.span(e, ctx.words)
        d, files = newest_frames(ctx.episode, iid)
        fmt, size = _format_of(ctx, e, files)
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        m = Moment(id=iid, raw=e, scene=e.get("scene"), source=e.get("source"), start=s, end=t,
                   transparent=bool(e.get("transparent")), data=data,
                   cues=dens.cue_seconds(e, ctx.words, s) if s is not None else {}, fmt=fmt, size=size,
                   frames_dir=d, frames=files, jsx=jsx_of(ctx, e))
        if s is None or t is None:
            m.notes.append("start or end cannot be resolved from the words file: times are local to the insert")
        if not files:
            m.notes.append(f"no rendered frames in render/inserts/{iid}-<hash>/: run the motion render first")
        if m.jsx is None:
            m.notes.append("comp source not found (" + (f"source {e.get('source')}" if e.get("source")
                                                          else f"template {e.get('scene')}") + ")")
        out.append(m)
    return out


def frame_dur(ctx: Ctx, m: Moment) -> float:
    """Length of the insert: the plan's span, else the rendered frames."""
    return m.dur or (len(m.frames) / ctx.fps if m.frames else 0.0)


def transitions(m: Moment) -> list[tuple[float, float]]:
    """Declared inner transitions (local seconds): ``"transitions"`` in the insert or its data, as seconds
    (a window of +-0.25 s), ``[a, b]`` or ``{"at", "len"}``."""
    out = []
    for t in m.raw.get("transitions") or m.data.get("transitions") or []:
        if isinstance(t, (int, float)) and not isinstance(t, bool):
            out.append((float(t) - 0.25, float(t) + 0.25))
        elif isinstance(t, (list, tuple)) and len(t) == 2:
            out.append((float(t[0]), float(t[1])))
        elif isinstance(t, dict) and "at" in t:
            half = float(t.get("len") or 0.5) / 2
            out.append((float(t["at"]) - half, float(t["at"]) + half))
    return out


def quiet_windows(ctx: Ctx, m: Moment, dur: float) -> list[tuple[float, float]]:
    """Times where blur and small sizes are expected: the entrance, the exit and the declared transitions."""
    return [(0.0, ctx.enter_s + 0.1), (max(0.0, dur - ctx.exit_s - 0.1), dur + 1.0), *transitions(m)]


def _in(t: float, windows: list[tuple[float, float]]) -> bool:
    return any(a - 1e-9 <= t <= b + 1e-9 for a, b in windows)


# ---------------------------------------------------------------- geometry (fractions of the frame)


def safe_box(fmt: str, transparent: bool, right_free: float = 0.18) -> tuple[float, float, float, float]:
    """The safe box as fractions (x, y, w, h), the same numbers as ``CC.safe`` in lib/cc_frame.jsx."""
    if fmt == "portrait":
        return 0.06, 0.10, 1 - 0.06 - right_free, 1 - 0.10 - 0.20
    if fmt == "stage":
        return 0.05, 0.05, 0.90, 1 - 0.05 - 0.06
    return 0.05, 0.05, 0.90, 1 - 0.05 - (0.08 if transparent else 0.05)


def face_box(face: Any) -> tuple[float, float, float, float] | None:
    """The face box to keep free as fractions: the plan's face centre grown to at least +-0.16 of the width and
    +-0.14 of the height (``CC.frame``). ``face`` is ``[x, y]`` or ``{"x", "y", "w", "h"}``."""
    if face is None:
        return None
    if isinstance(face, dict):
        x, y, w, h = (float(face.get(k) or 0.0) for k in ("x", "y", "w", "h"))
    elif isinstance(face, (list, tuple)) and len(face) >= 2:
        x, y, w, h = float(face[0]), float(face[1]), 0.0, 0.0
    else:
        return None
    hw, hh = max(w / 2, 0.16), max(h / 2, 0.14)
    return x - hw, y - hh, 2 * hw, 2 * hh


def overlap(a: tuple, b: tuple) -> bool:
    return not (a[0] + a[2] <= b[0] or a[0] >= b[0] + b[2] or a[1] + a[3] <= b[1] or a[1] >= b[1] + b[3])


def inside(a: tuple, b: tuple, tol: float = 0.0) -> bool:
    return (a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[0] + a[2] <= b[0] + b[2] + tol
            and a[1] + a[3] <= b[1] + b[3] + tol)


def _px(box: tuple, shape: tuple) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x0, y0 = max(0, int(round(box[0] * w))), max(0, int(round(box[1] * h)))
    x1, y1 = min(w, int(round((box[0] + box[2]) * w))), min(h, int(round((box[1] + box[3]) * h)))
    return x0, y0, x1, y1


# ---------------------------------------------------------------- pixels (numpy)


def load_frame(path: Path | str, side: int = ANALYSIS_SIDE) -> np.ndarray:
    """A frame as uint8 RGBA (H, W, 4), longest side at most ``side``."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGBA")
        if max(im.size) > side:
            im.thumbnail((side, side))
        return np.asarray(im, np.uint8).copy()


def flat(rgba: np.ndarray) -> np.ndarray:
    """RGB over mid grey (an overlay's transparent parts show grey), float32."""
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return rgba[..., :3].astype(np.float32) * a + GREY * (1.0 - a)


def gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def laplace_var(g: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian: high = sharp edges, low = blur or nothing."""
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]) - 4.0 * g[1:-1, 1:-1]
    return float(lap.var())


def frame_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference of two RGBA frames (0..255)."""
    if a.shape != b.shape:
        return 255.0
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def content_share(rgba: np.ndarray, transparent: bool) -> float:
    """Overlay: share of visible pixels. Full frame: share of pixels that differ from the ground (the pixel near
    the top-left corner), like style_check's empty check."""
    if transparent:
        return float((rgba[..., 3] > 12).mean())
    p = rgba[..., :3].astype(np.int16)
    return float((np.abs(p - p[2, 2]).sum(-1) > 40).mean())


def frozen_runs(diffs: list[float], usable: list[bool], fps: float, hold_s: float = HOLD_S,
                eps: float = FROZEN_EPS) -> list[tuple[int, int]]:
    """Frame ranges (first, last) where nothing changes for ``hold_s`` or longer. ``diffs[i]`` compares frame i with
    frame i + 1; ``usable[i]`` is False for frames that show nothing (an overlay before it enters)."""
    need = max(1, math.ceil(hold_s * fps - 1e-9))
    out, run = [], 0
    for i, d in enumerate(diffs + [math.inf]):
        still = d <= eps and i + 1 < len(usable) and usable[i] and usable[i + 1]
        if still:
            run += 1
            continue
        if run >= need:
            out.append((i - run, i))
        run = 0
    return out


def low_runs(values: list[float | None], mask: list[bool], ratio: float = SHARP_RATIO) -> tuple[float, list]:
    """Mean Laplace variance of the usable frames and the runs (first, last) of frames below ``ratio`` of it that lie
    where ``mask`` is True (outside the declared transitions)."""
    good = [v for v in values if v is not None]
    mean = float(np.mean(good)) if good else 0.0
    if mean <= 0:
        return mean, []
    runs, start = [], None
    for i, v in enumerate(values + [None]):
        low = v is not None and i < len(mask) and mask[i] and v < ratio * mean
        if low and start is None:
            start = i
        elif not low and start is not None:
            runs.append((start, i - 1))
            start = None
    return mean, runs


def box_share(rgba: np.ndarray, box: tuple) -> float:
    """Share of a box (fractions) covered by visible overlay pixels."""
    x0, y0, x1, y1 = _px(box, rgba.shape)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float((rgba[y0:y1, x0:x1, 3] > 12).mean())


def outside_share(rgba: np.ndarray, box: tuple) -> float:
    """Share of an overlay's visible pixels that lie outside a box (fractions)."""
    vis = rgba[..., 3] > 12
    total = int(vis.sum())
    if not total:
        return 0.0
    x0, y0, x1, y1 = _px(box, rgba.shape)
    return 1.0 - int(vis[y0:y1, x0:x1].sum()) / total


# ---------------------------------------------------------------- lint of the .jsx


def strip_comments(src: str) -> str:
    """The source without comments (strings kept, line breaks kept, so line numbers stay)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * src.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _call_args(code: str, open_at: int) -> str:
    """The text between the parenthesis at ``open_at`` and its partner."""
    depth, i = 0, open_at
    while i < len(code):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return code[open_at + 1:i]
        elif code[i] in "\"'`":
            q = code[i]
            i += 1
            while i < len(code) and code[i] != q:
                i += 2 if code[i] == "\\" else 1
        i += 1
    return code[open_at + 1:]


SHAPE_CALL = re.compile(r"(?:\bvar\s+|\blet\s+|\bconst\s+)?(?:(?P<var>[A-Za-z_$][\w$]*)\s*=\s*)?"
                        r"(?P<call>EC\.shape|EC\.solid|(?:EC|app)\.run\(\s*[\"']layer\.newS(?:hape|olid)[\"']\s*,)\s*")
TEXT_CALL = re.compile(r"(?:(?P<var>[A-Za-z_$][\w$]*)\s*=\s*)?(?:EC\.text|(?:EC|app)\.run\(\s*[\"']layer\.newText[\"']\s*,)")
BOXY = re.compile(r"chip|pill|badge|tag|box|plate|backing|bg|label|button|card|bubble", re.I)
ROUND = re.compile(r"\b(?:roundness|radius|cornerRadius|rounded|round)\s*[:=]\s*(?!0\b|0\.0*\b|false\b|null\b)")


def _line(code: str, pos: int) -> int:
    return code.count("\n", 0, pos) + 1


def lint_jsx(src: str, defaults: dict | None = None) -> list[dict]:
    """Static look at a comp's source. Each hit: ``{"rule", "line", "text", "level", "candidate"}``.

    Errors: hard-coded 1920/1080, a quoted font family name (Manrope or any other), Temporal Motion Blur, Shatter.
    Candidates (the Critic decides): a rounded rect parented to or sized from a text layer, a filled rect or solid
    behind a text layer. Glass plates through ``CC.glass`` are allowed."""
    code = strip_comments(src)
    lines = code.splitlines()
    hits: list[dict] = []

    def hit(rule: str, line: int, text: str, candidate: bool = False) -> None:
        hits.append({"rule": rule, "line": line, "text": text, "level": "CHECK" if candidate else "ERROR",
                     "candidate": candidate})

    for n, ln in enumerate(lines, 1):
        if "CC.glass" in ln:
            continue
        for m in re.finditer(r"(?<![\w.])(1920|1080)(?:\.0+)?(?![\w.])", ln):
            hit("size-literal", n, f"hard-coded {m.group(1)}: position through CC.frame (W, H, u, safe)")
        for m in re.finditer(r"\b(font|family|fontFamily|fontName|typeface)[\"']?\s*[:=]\s*([\"'])([^\"'\n]+)\2", ln):
            hit("font-name", n, f"font name {m.group(3)!r} in the source: take it from CC.font(role)")
        if re.search(r"[\"'`][^\"'`\n]*\bManrope\b", ln) and not any(h["rule"] == "font-name" and h["line"] == n
                                                                     for h in hits):
            hit("font-name", n, "Manrope by name: take the font from CC.font(role)")
        if re.search(r"temporal[\s_-]*motion[\s_-]*blur", ln, re.I):
            hit("temporal-blur", n, "Temporal Motion Blur: use the comp's motion blur switches instead")
        if re.search(r"\bshatter\b", ln, re.I):
            hit("shatter", n, "Shatter: not for in-video templates (Blender plates do hero breaks)")
    for k, v in (defaults or {}).items():
        if re.search(r"font|family|typeface", k, re.I) and isinstance(v, str) and v.strip():
            hit("font-name", 0, f"@params default {k}={v!r}: fonts come from the pack (CC.font)")
        if v in (1920, 1080) and not isinstance(v, bool):
            hit("size-literal", 0, f"@params default {k}={v}: sizes come from CC.frame")

    texts: dict[str, int] = {}
    for m in TEXT_CALL.finditer(code):
        if m.group("var"):
            texts[m.group("var")] = m.start()
    measured = set()                    # variables that hold a text layer's size: var d = EC.dims(c, t)
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=\s*[^;\n]*?(?:EC\.dims\(\s*[^,]+,\s*|\b)([A-Za-z_$][\w$]*)"
                         r"(?:\s*\)|\.sourceRectAtTime)", code):
        if m.group(2) in texts and m.group(1) not in texts:
            measured.add(m.group(1))
    shapes = []
    for m in SHAPE_CALL.finditer(code):
        args = _call_args(code, code.find("(", m.start("call")))
        line_txt = lines[_line(code, m.start()) - 1] if lines else ""
        if "CC.glass" in line_txt:
            continue
        solid = "olid" in m.group("call")
        filled = solid or (re.search(r"\bfill\b\s*:", args) is not None
                           and not re.search(r"\bfillOpacity\s*:\s*0(?:\.0*)?\b", args))
        rounded = bool(ROUND.search(args)) or "roundedRect" in args or re.search(r"kind\s*:\s*[\"']rrect", args)
        is_rect = solid or not re.search(r"kind\s*:\s*[\"'](?:ellipse|star|polygon|path)", args)
        shapes.append({"var": m.group("var"), "pos": m.start(), "args": args, "filled": filled, "solid": solid,
                       "rounded": bool(rounded), "rect": is_rect, "line": _line(code, m.start())})
    parents = [(a, b) for a, b in re.findall(r"EC\.parent\(\s*[^,]+,\s*([\w$]+)\s*,\s*([\w$]+)\s*\)", code)]
    for s in shapes:
        if not s["rect"]:
            continue
        linked = None
        pm = re.search(r"\bparent\s*:\s*([\w$]+)", s["args"])
        if pm and pm.group(1) in texts:
            linked = f"parented to text layer {pm.group(1)}"
        for child, par in parents:
            if child == s["var"] and par in texts:
                linked = f"parented to text layer {par}"
            if par == s["var"] and child in texts:
                linked = f"text layer {child} parented to it"
        if not linked:
            used = [t for t in [*texts, *measured] if re.search(r"(?<![\w$.])" + re.escape(t) + r"(?![\w$])",
                                                                s["args"])]
            if used:
                linked = f"sized or placed from text layer {used[0]}"
            elif re.search(r"EC\.dims|sourceRect|textWidth|measure", s["args"]):
                linked = "sized from a measured text"
        if not linked and s["var"] and BOXY.search(s["var"]) and texts:
            near = [t for t, pos in texts.items() if abs(_line(code, pos) - s["line"]) <= 4]
            if near:
                linked = f"named {s['var']!r} next to text layer {near[0]}"
        if not linked:
            continue
        if s["rounded"]:
            hit("rounded-text", s["line"], f"rounded rect {s['var'] or ''} {linked}: a chip or pill look",
                candidate=True)
        elif s["filled"]:
            hit("box-behind-text", s["line"], f"filled {'solid' if s['solid'] else 'rect'} "
                f"{s['var'] or ''} {linked}: a word in a box", candidate=True)
    return sorted(hits, key=lambda h: (h["line"], h["rule"]))


def static_text_sizes(src: str, min_px: float) -> list[dict]:
    """Text sizes written in the source (``size: 30``, ``size: CC.px(30)``, ``"size": 30`` in @params) below
    ``min_px``: candidates only, the engine measures the real size after every scale."""
    out = []
    for n, ln in enumerate(src.splitlines(), 1):
        for m in re.finditer(r"[\"']?\b(?:size|fontSize|textSize)[\"']?\s*:\s*(?:CC\.px\(\s*)?(\d+(?:\.\d+)?)", ln):
            v = float(m.group(1))
            if 0 < v < min_px:
                out.append({"line": n, "size": v, "text": ln.strip()[:120]})
    return out


# ---------------------------------------------------------------- the engine (review strips and text sizes)


TEXT_PROBE = """
var COMP = %(comp)s, TIMES = %(times)s;
var comp = null;
for (var i = 1; i <= app.project.numItems; i++) {
  var it = app.project.item(i);
  if (it && (it.name === COMP || it.id === COMP)) { comp = it; break; }
}
if (!comp) return {error: "comp not found: " + COMP, layers: []};
function dist(a, b) { return Math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1])); }
var out = [], precomps = 0;
for (var j = 1; j <= comp.numLayers; j++) {
  var l = comp.layer(j);
  if (l.source && l.source.numLayers !== undefined) precomps++;
  if (!(l instanceof TextLayer)) continue;
  var rec = {name: l.name, text: "", samples: []};
  for (var k = 0; k < TIMES.length; k++) {
    var t = TIMES[k];
    if (t < l.inPoint || t >= l.outPoint) continue;
    try {
      comp.time = t;
      var doc = l.text.sourceText.valueAtTime(t, false);
      rec.text = doc.text;
      var r = l.sourceRectAtTime(t, false);
      if (!r || r.width <= 0 || r.height <= 0) continue;
      var c = [l.sourcePointToComp([r.left, r.top]), l.sourcePointToComp([r.left + r.width, r.top]),
               l.sourcePointToComp([r.left, r.top + r.height]), l.sourcePointToComp([r.left + r.width, r.top + r.height])];
      var xs = [c[0][0], c[1][0], c[2][0], c[3][0]], ys = [c[0][1], c[1][1], c[2][1], c[3][1]];
      var x0 = Math.min.apply(null, xs), y0 = Math.min.apply(null, ys);
      var px = dist(l.sourcePointToComp([0, 0]), l.sourcePointToComp([0, doc.fontSize]));
      rec.samples.push({t: t, px: px, opacity: l.transform.opacity.valueAtTime(t, false),
                        box: [x0, y0, Math.max.apply(null, xs) - x0, Math.max.apply(null, ys) - y0]});
    } catch (e) { rec.error = String(e); }
  }
  out.push(rec);
}
return {comp: COMP, size: [comp.width, comp.height], precomps: precomps, layers: out};
"""


def cc_context(ctx: Ctx, m: Moment, fps: float, dur: float) -> dict:
    """``CC_CTX`` for a review build of the comp (the speaker backdrop is left out of review strips)."""
    b = ctx.pack.value("brand", {}) or {}
    fonts = {r: {"family": (s or {}).get("family"), "weight": (s or {}).get("weight")}
             for r, s in (b.get("fonts") or {}).items()}
    face = m.raw.get("face", ctx.face)
    if isinstance(face, (list, tuple)) and len(face) >= 2:
        face = {"x": float(face[0]), "y": float(face[1]), "w": 0.0, "h": 0.0}
    return {"format": m.fmt, "size": list(m.size), "fps": fps, "duration": dur, "transparent": m.transparent,
            "face": face if isinstance(face, dict) else None, "backdrop": None, "draft": False,
            "right_free": ctx.right_free,
            "brand": {"colors": b.get("colors") or {}, "fonts": fonts, "shape": b.get("shape") or {},
                      "mg": b.get("motion_graphics") or {}}}


def source_program(path: Path, params: dict, context: dict) -> str:
    """Script for an episode-local comp: like a template when it has a template header, else the file as it is."""
    src = path.read_text(encoding="utf-8")
    try:
        h = tp.parse_header(src)
        merged = tp.merge(h["defaults"], params, strict=False)
        body = f"{src}\nreturn {h['name']}({js(merged)});"
    except tp.TemplateError:
        body = src
    assets = str(tp.assets_dir())
    return wrap_program(body, tp.context_source(context) + tp.lib_source() + f"\nvar EC_ASSETS = {js(assets)};\n")


class Engine:
    """Review renders through ``effectcraft-cli``: the comp built at 60 fps in a scratch project, single frames for
    the strips, and the text layer probe. ``backend`` is a :class:`Backend` or anything with the same methods."""

    def __init__(self, backend: Any, work: Path):
        self.b = backend
        self.work = work

    def build(self, ctx: Ctx, m: Moment, dur: float, fps: float = STRIP_FPS) -> str:
        """Build the insert's comp at ``fps`` in a scratch project; returns the comp name."""
        project = self.project(m)
        comp = proj.comp_params(name="Main", profile=None, width=m.size[0], height=m.size[1], fps=fps,
                                duration=max(dur, 1.0 / fps))
        proj.create(self.b, str(project), comp, overwrite=True)
        context = cc_context(ctx, m, fps, dur)
        params = {**m.data, **m.cues}
        if m.scene and not m.source:
            defaults = tp.discover().get(m.scene, {}).get("defaults") or {}
            if "comp" in defaults:
                params.setdefault("comp", "Main")
            res = tp.run(self.b, str(project), m.scene, params, context=context)["result"]
        else:
            if m.jsx is None:
                raise BackendError(f"comp source not found: {m.source}")
            res = parse_result(self.b.script(source_program(m.jsx, params, context), project=str(project), save=True,
                                             name=f"{m.id}.jsx"))
        return str(res.get("comp")) if isinstance(res, dict) and res.get("comp") else "Main"

    def project(self, m: Moment) -> Path:
        return self.work / f"{m.id}-review.ecproj"

    def frames(self, m: Moment, comp: str, times: list[float], out_dir: Path, max_side: int = CELL_W) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i, t in enumerate(times):
            f = out_dir / f"{i:03d}.png"
            self.b.render_frame(str(self.project(m)), str(f), comp=comp, time=t, max_side=max_side,
                                transparent=m.transparent)
            if not f.is_file():
                raise BackendError(f"the engine wrote no frame for {t:.3f} s")
            files.append(f)
        return files

    def text_layers(self, m: Moment, comp: str, times: list[float]) -> dict:
        code = wrap_program(TEXT_PROBE % {"comp": js(comp), "times": js([round(t, 4) for t in times])})
        r = parse_result(self.b.script(code, project=str(self.project(m)), save=False, name="text-probe.jsx"))
        return r if isinstance(r, dict) else {"layers": [], "error": f"unexpected reply {r!r}"}


def engine_for(backend: Any) -> tuple[Any, str | None]:
    """The backend to use and a note: ``False`` = do not use the engine, ``None`` = find ``effectcraft-cli``."""
    if backend is False:
        return None, "skipped: the engine is not used for this bundle (--no-engine)."
    if backend is None:
        b = Backend()
        try:
            b.binary  # noqa: B018 (finds the binary or raises)
        except BackendError:
            return None, ENGINE_SKIP
        return b, None
    return backend, None


# ---------------------------------------------------------------- text check


def text_check(probe: dict, min_px: float, size: tuple[int, int], safe: tuple, face: tuple | None,
               overlay: bool, quiet: list[tuple[float, float]]) -> tuple[list[dict], list[dict]]:
    """Text layers from the engine probe: smallest size on screen (outside the entrance, exit and transitions when
    there are such samples), union box in fractions, and the three failures."""
    W, H = size
    if probe.get("size"):
        W, H = probe["size"][0] or W, probe["size"][1] or H
    layers, bad = [], []
    for lay in probe.get("layers") or []:
        ss = [s for s in lay.get("samples") or [] if (s.get("opacity") if s.get("opacity") is not None else 100) >= 50]
        if not ss:
            layers.append({"name": lay.get("name"), "text": lay.get("text"), "min_px": None,
                           "note": lay.get("error") or "no visible sample"})
            continue
        held = [s for s in ss if not _in(float(s["t"]), quiet)] or ss
        low = min(held, key=lambda s: float(s["px"]))
        xs = [s["box"] for s in ss if s.get("box")]
        if xs:
            x0, y0 = min(b[0] for b in xs), min(b[1] for b in xs)
            x1, y1 = max(b[0] + b[2] for b in xs), max(b[1] + b[3] for b in xs)
            box = (x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H)
        else:
            box = None
        e = {"name": lay.get("name"), "text": lay.get("text"), "min_px": round(float(low["px"]), 1),
             "min_at": float(low["t"]), "box": [round(v, 4) for v in box] if box else None,
             "below_min": float(low["px"]) < min_px - 1e-6,
             "outside_safe": bool(box and not inside(box, safe, tol=2.0 / max(W, H))),
             "over_face": bool(overlay and box and face and overlap(box, face))}
        layers.append(e)
        if e["below_min"]:
            bad.append({"rule": "text-small", "layer": e, "at": e["min_at"]})
        if e["outside_safe"]:
            bad.append({"rule": "text-safe", "layer": e, "at": e["min_at"]})
        if e["over_face"]:
            bad.append({"rule": "text-face", "layer": e, "at": e["min_at"]})
    return layers, bad


# ---------------------------------------------------------------- one insert


class Review:
    """Machine checks and (with ``out``) the files of one insert."""

    def __init__(self, ctx: Ctx, m: Moment, out: Path | None, engine: Engine | None, engine_note: str | None,
                 ref: Path | None, ref_offset: float, plan_density: dict, tmp: Path, log: Callable):
        self.ctx, self.m, self.out, self.engine, self.engine_note = ctx, m, out, engine, engine_note
        self.ref, self.ref_offset, self.density, self.tmp, self.log = ref, ref_offset, plan_density, tmp, log
        self.findings: list[dict] = []
        self.files: list[str] = []
        self.skipped: list[str] = []
        self.dur = frame_dur(ctx, m)
        self.safe = safe_box(m.fmt, m.transparent, ctx.right_free)
        self.face = face_box(m.raw.get("face", ctx.face if ctx.face is not None else [0.5, 0.38]))
        self.quiet = quiet_windows(ctx, m, self.dur)
        self.kept: dict[int, np.ndarray] = {}
        self.comp: str | None = None
        self.overlay_pixels: dict | None = None
        self.compare_note: str | None = None

    # -- helpers
    def add(self, area: str, level: str, cid: str, text: str, local: float | None = None, fix: str | None = None):
        assert level in LEVELS, level
        self.findings.append({"insert": self.m.id, "area": area, "level": level, "id": cid, "text": text,
                              "time": None if local is None else round(self.m.at(local), 3), "fix": fix})

    def write_json(self, name: str, data: Any) -> None:
        if self.out is None:
            return
        (self.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        self.files.append(name)

    def idx(self, t: float) -> int:
        return max(0, min(len(self.m.frames) - 1, int(round(t * self.ctx.fps))))

    def grid(self) -> list[float]:
        n = int(math.floor(self.dur / SHEET_STEP + 1e-9)) + 1
        ts = [round(k * SHEET_STEP, 3) for k in range(n)]
        return [t for t in ts if t < self.dur - 1e-9] or [0.0]

    def web_times(self) -> list[float]:
        return [round(self.dur * (k + 0.5) / WEB_FRAMES, 3) for k in range(WEB_FRAMES)]

    def hue_times(self) -> list[float]:
        return [round(self.dur * f, 3) for f in HUE_AT]

    def compare_times(self) -> list[float]:
        d = self.dur
        ts = {round(min(self.ctx.enter_s + 0.1, d * 0.2), 3), round(d / 2, 3),
              round(max(0.0, d - self.ctx.exit_s - 0.1), 3)}
        ts |= {round(c, 3) for c in self.m.cues.values() if 0 <= c < d}
        return sorted(ts)[:6]

    def image(self, i: int, width: int = CELL_W) -> Path:
        """Frame ``i`` composited over grey, as a small JPEG in the scratch folder."""
        from PIL import Image
        f = self.tmp / f"{self.m.id}-{i:05d}-{width}.jpg"
        if not f.is_file():
            a = self.kept.get(i)
            if a is None:
                a = load_frame(self.m.frames[i])
            im = Image.fromarray(np.clip(flat(a), 0, 255).astype(np.uint8))
            if im.width > width:
                im = im.resize((width, max(1, round(im.height * width / im.width))))
            im.save(f, quality=90)
        return f

    # -- the checks
    def run(self) -> dict:
        m = self.m
        for name, c in m.cues.items():
            if self.dur and not 0 <= c < self.dur:
                self.add("Picture", "CHECK", f"cue:{m.id}:{name}", f"{m.id}: cue {name!r} at {c:.2f} s lies outside "
                         f"the insert (0 to {self.dur:.2f} s)", fix="Move the cue word or the insert")
        if m.frames:
            self.pixels()
        else:
            self.skipped.append(f"{m.id}: no rendered frames (render/inserts/{m.id}-<hash>/): sheet, compare, hue, "
                                "sharp and web-look need them")
            self.add("Picture", "CHECK", f"frames:{m.id}", f"{m.id}: no rendered frames; the pixel checks did not run",
                     fix="crewcut render motion <plan>, then build the bundle again")
        self.text()
        self.lint()
        self.write_density()
        self.strips()
        return {"id": m.id, "scene": m.scene, "source": m.source, "start": m.start, "end": m.end,
                "duration": round(self.dur, 3), "transparent": m.transparent, "format": m.fmt, "size": list(m.size),
                "frames_dir": str(m.frames_dir) if m.frames_dir else None, "frames": len(m.frames),
                "jsx": str(m.jsx) if m.jsx else None, "cues": m.cues, "notes": m.notes, "files": self.files,
                "skipped": self.skipped, "findings": self.findings}

    def pixels(self) -> None:
        m, fps = self.m, self.ctx.fps
        sheet = [self.idx(t) for t in self.grid()]
        need = set(sheet) | {self.idx(t) for t in self.hue_times() + self.web_times() + self.compare_times()}
        lap: list[float | None] = []
        diffs: list[float] = []
        content: list[float] = []
        prev = None
        for i, f in enumerate(m.frames):
            a = load_frame(f)
            c = content_share(a, m.transparent)
            content.append(c)
            lap.append(laplace_var(gray(flat(a))) if c >= EMPTY_SHARE else None)
            if prev is not None:
                diffs.append(frame_diff(prev, a))
            prev = a
            if i in need:
                self.kept[i] = a
        n = len(m.frames)
        usable = [c >= EMPTY_SHARE for c in content]
        times = [i / fps for i in range(n)]

        # empty frames
        empty = [i for i in range(n) if not usable[i]]
        if m.transparent:
            bad = [i for i in empty if OVERLAY_EDGE_S <= times[i] <= self.dur - OVERLAY_EDGE_S]
        else:
            bad = empty
        for a, b in _runs(bad):
            lvl = "CHECK" if (not m.transparent and a == 0 and b <= 1) else "ERROR"
            self.add("Picture", lvl, f"empty:{m.id}@{times[a]:.2f}",
                     f"{m.id}: {'frame' if a == b else 'frames'} {a}-{b} ({times[a]:.2f}-{times[b]:.2f} s) "
                     "show nothing", times[a], fix="Start a few frames into the build, or fill the gap with motion")
        # frozen holds
        frozen = frozen_runs(diffs, usable, fps)
        for a, b in frozen:
            self.add("Picture", "ERROR", f"frozen:{m.id}@{times[a]:.2f}",
                     f"{m.id}: the camera stopped: no change from {times[a]:.2f} to {times[b]:.2f} s "
                     f"({(b - a) / fps:.2f} s)", times[a], fix="Keep a slow push in every hold (1.5 to 3 % per second)")
        if not frozen:
            self.add("Picture", "OK", f"frozen:{m.id}", f"{m.id}: no hold stands still for {HOLD_S:g} s")
        # sharpness
        mask = [not _in(t, self.quiet) for t in times]
        mean, runs = low_runs(lap, mask)
        for a, b in runs:
            long = b - a + 1 > SHARP_RUN
            self.add("Picture", "ERROR" if long else "CHECK", f"sharp:{m.id}@{times[a]:.2f}",
                     f"{m.id}: {b - a + 1} blurry {'frame' if a == b else 'frames in a row'} at "
                     f"{times[a]:.2f}-{times[b]:.2f} s (Laplace variance under {SHARP_RATIO:.0%} of the mean, "
                     "outside the declared transitions)", times[a],
                     fix="Motion blur only while moving; declare the transition in the plan if it is one")
        if not runs and mean > 0:
            self.add("Picture", "OK", f"sharp:{m.id}", f"{m.id}: no blurry frames outside the transitions")
        self.write_json("sharp.json", {
            "fps": fps, "frames": n, "mean_laplace": round(mean, 2), "limit": round(SHARP_RATIO * mean, 2),
            "ratio": SHARP_RATIO, "run_max": SHARP_RUN, "transitions": [list(w) for w in self.quiet],
            "low_runs": [{"first": a, "last": b, "from": round(times[a], 3), "to": round(times[b], 3)} for a, b in runs],
            "frozen": [{"first": a, "last": b, "from": round(times[a], 3), "to": round(times[b], 3)} for a, b in frozen],
            "empty": [{"first": a, "last": b} for a, b in _runs(empty)],
            "per_frame": [{"i": i, "t": round(times[i], 3), "laplace": None if lap[i] is None else round(lap[i], 2),
                           "diff_next": round(diffs[i], 3) if i < len(diffs) else None,
                           "content": round(content[i], 4)} for i in range(n)],
        })
        # overlay placement from pixels
        if m.transparent:
            fs = [(self.idx(t), t) for t in self.grid()]
            on_face = [(box_share(self.kept[i], self.face), t) for i, t in fs] if self.face else []
            out_safe = [(outside_share(self.kept[i], self.safe), t) for i, t in fs]
            self.overlay_pixels = {
                "face_share_max": round(max([s for s, _ in on_face] or [0.0]), 4),
                "face_at": max(on_face)[1] if on_face else None,
                "outside_safe_max": round(max([s for s, _ in out_safe] or [0.0]), 4),
                "outside_safe_at": max(out_safe)[1] if out_safe else None,
            }
            if on_face and max(on_face)[0] > FACE_SHARE:
                s, t = max(on_face)
                self.add("Text", "ERROR", f"face:{m.id}", f"{m.id}: the overlay covers {s:.0%} of the face box at "
                         f"{t:.2f} s", t, fix="Put it on the free side next to the face (CC.frame sideBox)")
            if out_safe and max(out_safe)[0] > OUTSIDE_SAFE_SHARE:
                s, t = max(out_safe)
                self.add("Text", "CHECK", f"safe:{m.id}", f"{m.id}: {s:.0%} of the overlay lies outside the safe box "
                         f"at {t:.2f} s", t, fix="Keep overlays inside CC.frame().safe")
        self.sheet(sheet)
        self.hue()
        self.compare()
        self.web_look()

    def sheet(self, idx: list[int]) -> None:
        if self.out is None:
            return
        export.tile([str(self.image(i)) for i in idx], str(self.out / "sheet.jpg"), cols=4,
                    labels=[f"{i / self.ctx.fps:.2f}s" for i in idx], cell_w=CELL_W)
        self.files.append("sheet.jpg")

    def hue(self) -> None:
        m = self.m
        exempt = None
        if m.data.get("natural") or m.raw.get("natural"):
            exempt = "natural content"
        elif m.scene == "end_lockup":
            exempt = "end lockup"
        rows = []
        for t in self.hue_times():
            r = palette.hue_report(str(self.image(self.idx(t), ANALYSIS_SIDE)), HUE_LIMIT)
            r.pop("image", None)
            rows.append({"t": t, **r})
            if not r["ok"]:
                if exempt:
                    self.add("Colour", "NOTE", f"hue:{m.id}@{t:.2f}",
                             f"{m.id}: one hue holds {r['dominant_share']:.0%} at {t:.2f} s (exempt: {exempt})", t)
                else:
                    self.add("Colour", "ERROR", f"hue:{m.id}@{t:.2f}",
                             f"{m.id}: hue {r['dominant_hue']}° holds {r['dominant_share']:.0%} of the coloured pixels "
                             f"at {t:.2f} s (at most {HUE_LIMIT:.0%})", t,
                             fix="Colours from the palette in order; the accent only for the one thing that matters")
        if all(r["ok"] for r in rows):
            self.add("Colour", "OK", f"hue:{m.id}", f"{m.id}: no hue above {HUE_LIMIT:.0%} at {len(rows)} times")
        self.write_json("hue.json", {"limit": HUE_LIMIT, "exempt": exempt, "times": rows})

    def compare(self) -> None:
        if self.out is None:
            return
        from PIL import Image
        ts = self.compare_times()
        ours = [self.image(self.idx(t)) for t in ts]
        bar: list[tuple[Path, str]] = []
        note = None
        if self.ref is not None:
            for t in ts:
                f = self.tmp / f"ref-{self.m.id}-{t:.3f}.png"
                if ref_frame(self.ref, t + self.ref_offset, f):
                    bar.append((f, f"ref {t + self.ref_offset:.2f}s"))
            if not bar:
                note = f"reference {self.ref} gave no frames (ffmpeg missing or times outside the file)"
        else:
            for f, label in library_frames(self.ctx, self.m)[:len(ts)]:
                bar.append((f, label))
            if not bar:
                note = ("no reference, no library sample and no baseline frame: compare against a reference with "
                        "--ref FILE --ref-offset S")
        cells, labels = [], []
        with Image.open(ours[0]) as im:
            w, h = im.size
        for k, (o, t) in enumerate(zip(ours, ts, strict=True)):
            if k < len(bar):
                cells.append(str(bar[k][0]))
                labels.append(bar[k][1])
            else:
                blank = self.tmp / f"blank-{w}x{h}.jpg"
                if not blank.is_file():
                    Image.new("RGB", (w, h), (40, 40, 40)).save(blank)
                cells.append(str(blank))
                labels.append("no reference" if note else "-")
            cells.append(str(o))
            labels.append(f"ours {t:.2f}s")
        export.tile(cells, str(self.out / "compare.jpg"), cols=2, labels=labels, cell_w=CELL_W)
        self.files.append("compare.jpg")
        if note:
            self.skipped.append(f"{self.m.id}: compare.jpg shows ours only: {note}")
        self.compare_note = note

    def web_look(self) -> None:
        if self.out is None:
            return
        d = self.out / "web-look"
        d.mkdir(exist_ok=True)
        lines = [f"# Web look: {self.m.id} ({self.m.scene or self.m.source})", "",
                 "Answer every question for every frame with yes or no. Any yes sends the piece back to the builder "
                 "with the frame named. The lint (lint.json) lists candidates from the source; they are hints, "
                 "you decide.", ""]
        for k, t in enumerate(self.web_times(), 1):
            name = f"{k:02d}.jpg"
            shutil.copyfile(self.image(self.idx(t), ANALYSIS_SIDE), d / name)
            lines += [f"## Frame {k}: {t:.2f} s (video {dens.tc(self.m.at(t))})", "", f"![frame {k}](web-look/{name})",
                      ""]
            lines += [f"- {q} Answer: " for q in WEB_QUESTIONS]
            lines.append("")
        (self.out / "web-look.md").write_text("\n".join(lines), encoding="utf-8")
        self.files += ["web-look.md", "web-look/"]

    def text(self) -> None:
        m = self.m
        entry: dict[str, Any] = {"engine": False, "min_text_px": self.ctx.min_text_px, "format": m.fmt,
                                 "size": list(m.size), "safe": [round(v, 4) for v in self.safe],
                                 "face": [round(v, 4) for v in self.face] if self.face else None,
                                 "overlay": m.transparent, "layers": [], "static": [],
                                 "pixels": self.overlay_pixels}
        src = m.jsx.read_text(encoding="utf-8") if m.jsx else ""
        if self.engine is not None and self.comp:
            try:
                times = [round(k * SHEET_STEP / 2, 3) for k in range(int(self.dur / (SHEET_STEP / 2)) + 1)
                         if k * SHEET_STEP / 2 < self.dur]
                probe = self.engine.text_layers(m, self.comp, times)
                layers, bad = text_check(probe, self.ctx.min_text_px, m.size, self.safe, self.face, m.transparent,
                                         self.quiet)
                entry.update(engine=True, layers=layers, precomps=probe.get("precomps", 0))
                if probe.get("error"):
                    entry["note"] = probe["error"]
                if probe.get("precomps"):
                    entry["note"] = f"{probe['precomps']} precomp layer(s): text inside them is not measured"
                for b in bad:
                    lay = b["layer"]
                    what = {"text-small": f"is {lay['min_px']:g} px on screen (at least {self.ctx.min_text_px:g})",
                            "text-safe": "leaves the safe box", "text-face": "lies on the face box"}[b["rule"]]
                    self.add("Text", "ERROR", f"{b['rule']}:{m.id}:{lay['name']}",
                             f"{m.id}: text {lay['text'] or lay['name']!r} {what} at {b['at']:.2f} s", b["at"],
                             fix={"text-small": "Hero 120 to 160 px, labels at least min_text_px after every scale",
                                  "text-safe": "Position through CC.frame().safe",
                                  "text-face": "Free side next to the face (CC.frame sideBox)"}[b["rule"]])
                if layers and not bad:
                    self.add("Text", "OK", f"text:{m.id}", f"{m.id}: {len(layers)} text layer(s), smallest "
                             f"{min((x['min_px'] for x in layers if x.get('min_px')), default=0):g} px")
            except (BackendError, tp.TemplateError, OSError, ValueError, KeyError, TypeError) as e:
                entry["note"] = f"text probe failed: {e}"
                self.add("Text", "NOTE", f"text:{m.id}", f"{m.id}: text sizes not measured ({e})")
        else:
            entry["note"] = self.engine_note or "the comp was not built"
            static = static_text_sizes(src, self.ctx.min_text_px) if src else []
            entry["static"] = static
            for s in static:
                self.add("Text", "CHECK", f"text-static:{m.id}:L{s['line']}",
                         f"{m.id}: size {s['size']:g} below {self.ctx.min_text_px:g} written in line {s['line']} of "
                         f"the source (candidate: the engine measures the real size after every scale)")
        self.write_json("text.json", entry)

    def lint(self) -> None:
        m = self.m
        if m.jsx is None:
            self.write_json("lint.json", {"file": None, "note": "comp source not found", "hits": []})
            self.add("Lint", "CHECK", f"lint:{m.id}", f"{m.id}: comp source not found, no lint")
            return
        src = m.jsx.read_text(encoding="utf-8")
        try:
            defaults = tp.parse_header(src)["defaults"]
        except tp.TemplateError:
            defaults = {}
        hits = lint_jsx(src, defaults)
        for h in hits:
            where = f"line {h['line']}" if h["line"] else "header"
            self.add("Lint", h["level"], f"lint-{h['rule']}:{m.id}:{h['line']}",
                     f"{m.id}: {h['text']} ({m.jsx.name} {where})" + (" [candidate: the Critic decides]"
                                                                       if h["candidate"] else ""))
        if not hits:
            self.add("Lint", "OK", f"lint:{m.id}", f"{m.id}: {m.jsx.name} has no lint hit")
        self.write_json("lint.json", {"file": str(m.jsx), "note": LINT_NOTE, "hits": hits,
                                      "errors": sum(1 for h in hits if not h["candidate"]),
                                      "candidates": sum(1 for h in hits if h["candidate"])})

    def write_density(self) -> None:
        d = dict(self.density)
        L = self.ctx.limits
        me = re.escape(self.m.id)
        mine = [f for f in d.get("findings", []) if re.search(r"[:-]" + me + r"(?:-|$)", f["id"])
                or re.search(r"(?<![\w-])" + me + r"(?![\w-])", f["text"])]
        d["this"] = {"id": self.m.id, "neighbours_within_gap": dens.neighbours(d, self.m.id, L["min_gap_s"]),
                     "length": next((x for x in d.get("lengths", []) if x["id"] == self.m.id), None),
                     "findings": mine}
        self.write_json("density.json", d)

    def strips(self) -> None:
        m = self.m
        if self.engine is None:
            self.skipped.append(f"{m.id}: strips: {self.engine_note}")
            return
        if not self.comp:
            return
        plan: list[tuple[str, float]] = [("in", 0.0), ("out", max(0.0, self.dur - STRIP_FRAMES / STRIP_FPS))]
        for k, (a, b) in enumerate(transitions(m), 1):
            plan.append((f"t{k}", max(0.0, (a + b) / 2 - STRIP_FRAMES / STRIP_FPS / 2)))
        for name, c in m.cues.items():
            plan.append((f"cue-{re.sub(r'[^A-Za-z0-9_-]', '_', name)}", max(0.0, c - STRIP_FRAMES / STRIP_FPS / 2)))
        for name, t0 in plan:
            f0 = int(round(t0 * STRIP_FPS))           # on the 60 fps frame grid, exact frame times
            times = [(f0 + k) / STRIP_FPS for k in range(0, STRIP_FRAMES, STRIP_EVERY)]
            times = [t for t in times if t < self.dur] or [0.0]
            try:
                files = self.engine.frames(m, self.comp, times, self.tmp / f"strip-{m.id}-{name}")
            except (BackendError, OSError) as e:
                self.skipped.append(f"{m.id}: strip-{name}: {e}")
                continue
            if self.out is not None:
                files = [flat_file(f) for f in files] if m.transparent else files
                export.tile([str(f) for f in files], str(self.out / f"strip-{name}.jpg"), cols=5,
                            labels=[f"{t:.3f}s" for t in times], cell_w=360)
                self.files.append(f"strip-{name}.jpg")

    def build_comp(self) -> None:
        """Build the comp at 60 fps once (strips and text probe use it)."""
        if self.engine is None:
            return
        if self.m.jsx is None:
            self.skipped.append(f"{self.m.id}: engine steps: comp source not found")
            return
        try:
            self.comp = self.engine.build(self.ctx, self.m, self.dur)
        except (BackendError, tp.TemplateError, OSError, ValueError) as e:
            self.skipped.append(f"{self.m.id}: the comp could not be built at {STRIP_FPS} fps: {e}")
            self.add("Picture", "NOTE", f"build:{self.m.id}", f"{self.m.id}: review build failed ({e})")


def flat_file(path: Path) -> Path:
    """An RGBA frame composited over mid grey, as a JPEG next to it (overlay strips show the grey, not black)."""
    from PIL import Image
    out = path.with_suffix(".flat.jpg")
    Image.fromarray(np.clip(flat(load_frame(path, 4096)), 0, 255).astype(np.uint8)).save(out, quality=90)
    return out


def _runs(idx: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for i in idx:
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def ref_frame(ref: Path, t: float, out: Path) -> bool:
    """One frame of the reference video at ``t`` seconds (ffmpeg). False when it could not be read."""
    ff = shutil.which("ffmpeg")
    if not ff or t < 0:
        return False
    r = subprocess.run([ff, "-v", "error", "-y", "-ss", f"{t:.4f}", "-i", str(ref), "-frames:v", "1",
                        "-vf", f"scale={CELL_W}:-2", str(out)], capture_output=True, text=True)
    return r.returncode == 0 and out.is_file()


def library_frames(ctx: Ctx, m: Moment) -> list[tuple[Path, str]]:
    """Frames to compare with when there is no reference: the library sample of the template (pack, then app,
    ``templates/motion/samples/<scene>*.png|jpg`` or ``library.json`` ``sample``), else the baseline's motion frames
    (``baseline.json`` ``motion.frames``)."""
    out: list[tuple[Path, str]] = []
    if m.scene:
        for d in (tp.pack_dir(), tp.app_dir()):
            lib = d / "library.json"
            if lib.is_file():
                try:
                    entry = (json.loads(lib.read_text(encoding="utf-8")) or {}).get(m.scene) or {}
                except ValueError:
                    entry = {}
                s = entry.get("sample") if isinstance(entry, dict) else None
                if isinstance(s, str) and (d / s).is_file() and (d / s).suffix.lower() in (".png", ".jpg", ".jpeg"):
                    out.append((d / s, f"library {m.scene}"))
            sd = d / "samples"
            if sd.is_dir():
                for f in sorted(sd.glob(f"{m.scene}*")):
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                        out.append((f, f"sample {f.stem}"))
            if out:
                return out
    base = ctx.pack.value("baseline.motion", {}) or {}
    for fr in base.get("frames") or []:
        rel = fr.get("file") or fr.get("frame") if isinstance(fr, dict) else fr
        if not isinstance(rel, str):
            continue
        for root in (Path(ctx.pack.dir), paths.studio_root()):
            p = root / rel
            if p.is_file():
                label = (fr.get("label") if isinstance(fr, dict) else None) or f"baseline {p.stem}"
                out.append((p, f"bar: {label}"[:40]))
                break
    return out


# ---------------------------------------------------------------- the bundle


def next_version(review_dir: Path) -> int:
    """The next free NNN of ``review/motion-vNNN``."""
    have = [int(m.group(1)) for d in review_dir.glob("motion-v*") if (m := re.fullmatch(r"motion-v(\d{3,})", d.name))]
    return max(have, default=0) + 1


def round_of(review_dir: Path, iid: str, version: int) -> int:
    """The review round of an insert: 1 + earlier bundles that hold a folder for it."""
    n = 0
    for d in review_dir.glob("motion-v*"):
        m = re.fullmatch(r"motion-v(\d{3,})", d.name)
        if m and int(m.group(1)) < version and (d / iid).is_dir():
            n += 1
    return n + 1


def template_sounds() -> dict[str, int]:
    try:
        return {n: len(h.get("sounds") or []) for n, h in tp.discover().items()}
    except OSError:
        return {}


def plan_density(ctx: Ctx) -> dict:
    return dens.count(ctx.plan, ctx.words, ctx.limits, template_sounds())


def _density_findings(rep: dict) -> list[dict]:
    return [{"insert": None, "area": "Density", **f} for f in rep["findings"]]


def counts(findings: list[dict]) -> dict:
    return {k: sum(1 for f in findings if f["level"] == k) for k in LEVELS}


def analyze(plan_path: Path | str, ids: list[str] | None = None, pack: Any = None,
            log: Callable = lambda *_: None) -> dict:
    """The machine checks only (no files, no engine): what ``motion_check.py`` prints for a plan."""
    ctx = load(plan_path, pack)
    ms = moments(ctx, ids)
    rep = plan_density(ctx)
    findings = _density_findings(rep)
    with tempfile.TemporaryDirectory(prefix="motion-check-") as tmp:
        for m in ms:
            r = Review(ctx, m, None, None, "the engine is not used by the machine check", None, 0.0, rep, Path(tmp),
                       log)
            findings += r.run()["findings"]
    return {"plan": str(ctx.plan_path), "episode": ctx.episode.name, "inserts": [m.id for m in ms],
            "density": {k: v for k, v in rep.items() if k != "findings"}, "findings": findings,
            "counts": counts(findings)}


def critic_md(ctx: Ctx, version: int, results: list[dict], rounds: dict[str, int], rep: dict,
              engine_note: str | None, has_ref: bool) -> str:
    c = counts([f for r in results for f in r["findings"]] + _density_findings(rep))
    base = ctx.pack.value("baseline", {}) or {}
    bar = (base.get("motion") or {}).get("episode") or base.get("video") or "no baseline yet"
    L = [f"# Motion review v{version:03d}: {ctx.episode.name}, plan {ctx.plan_path.name}", "",
         "Reviewer: ______ (a crew member who did not build these pieces; the builder never reviews its own work)",
         f"Bar: {bar}",
         f"Machine checks: {c['ERROR']} ERROR, {c['CHECK']} CHECK "
         f"(`python3 skills/cut-check/scripts/motion_check.py review/motion-v{version:03d}`). The web-look lint gives "
         "candidates; you decide.",
         "", f"**The ratchet.** {RATCHET}", "",
         "Rounds: at most 3 per piece. After the third round the Showrunner asks the user instead of a fourth.", ""]
    if engine_note:
        L += [f"Engine: {engine_note}", ""]
    for r in results:
        big = not r["transparent"]
        who = r["scene"] or r["source"] or "custom"
        span = (f"{dens.tc(r['start'])}-{dens.tc(r['end'])}" if r["start"] is not None and r["end"] is not None
                else "time unknown")
        rd = rounds.get(r["id"], 1)
        L += [f"## {r['id']} · {who} · {'full frame (big moment)' if big else 'overlay'} · {span} · round {rd}"
              + (" (over 3: the Showrunner asks the user)" if rd > MAX_ROUNDS else ""), ""]
        L.append("Files: " + ", ".join(f"`{r['id']}/{f}`" for f in r["files"]))
        errs = [f for f in r["findings"] if f["level"] in ("ERROR", "CHECK")]
        if errs:
            L += ["", "Machine findings:"] + [f"- {f['level']} {f['text']}" for f in errs]
        for s in r["skipped"]:
            L.append(f"- skipped: {s}")
        L += ["", "- [ ] sheet.jpg looked at: no empty frame, no hold that stands still",
              "- [ ] strips: no stutter, motion blur while moving, no hold longer than planned, glyphs complete "
              "1 to 2 frames before their cue",
              "- [ ] web-look.md answered for all 8 frames (any yes: back)",
              "- [ ] compare.jpg: side by side with " + ("the reference" if has_ref else "the bar")]
        if big:
            L.append("- What the reference still does better (required, one sentence): ______")
        else:
            L.append("- What the reference still does better (one sentence, if it applies): ______")
        L += ["- Verdict: pass / back to the builder with: ______", ""]
    L += ["## Better than the bar", "",
          "At least one named way this video is better than the bar (time, frame, against which strength of the "
          "baseline). None: the version goes back.", "", "- ______", "",
          "## What I cannot check: sound", "",
          "I cannot hear. The user listens to these spots, from 5 s before to 5 s after each:", ""]
    for t, what in listening_list(ctx, results):
        L.append(f"- {dens.tc(t)}  {what}")
    L.append("")
    return "\n".join(L)


def listening_list(ctx: Ctx, results: list[dict]) -> list[tuple[float, str]]:
    """Times to listen to: every motion moment's start, cues and end, and its sound events."""
    snd = ctx.plan.get("sound") or {}
    out: list[tuple[float, str]] = []
    for r in results:
        s = r["start"]
        if s is None:
            continue
        sound = " (sound)" if (_raw_by_id(ctx, r["id"]) or {}).get("sound") else ""
        out.append((s, f"{r['id']} in{sound}"))
        for name, c in (r["cues"] or {}).items():
            out.append((s + c, f"{r['id']} cue {name}"))
        if r["end"] is not None:
            out.append((r["end"], f"{r['id']} out"))
        for key in ("hits", "typing", "whooshes"):
            for ref in snd.get(key) or []:
                if isinstance(ref, str) and ref.partition("@")[0] == r["id"]:
                    cue = ref.partition("@")[2]
                    t = s + (r["cues"] or {}).get(cue, 0.0) if cue else s
                    out.append((t, f"{r['id']} {key[:-1] if key != 'typing' else key} {ref}"))
    return sorted(set(out))


def _raw_by_id(ctx: Ctx, iid: str) -> dict | None:
    for e in ctx.plan.get("inserts") or []:
        if isinstance(e, dict) and str(e.get("id")) == iid:
            return e
    return None



def build_bundle(plan_path: Path | str, ids: list[str] | str | None = None, ref: str | Path | None = None,
                 ref_offset: float = 0.0, out_root: Path | str | None = None, backend: Any = None,
                 log: Callable = print, pack: Any = None) -> dict:
    """Write ``review/motion-vNNN/<id>/`` for the plan's motion inserts (or ``ids``) and return the bundle summary.

    ``out_root`` is the review folder (default ``<episode>/review``). ``backend``: None finds ``effectcraft-cli``
    (skipped with a line when missing), False never uses the engine, anything else is used as the engine backend."""
    ctx = load(plan_path, pack)
    if isinstance(ids, str):
        ids = [x.strip() for x in ids.split(",") if x.strip()]
    ms = moments(ctx, ids or None)
    if not ms:
        raise ReviewError(f"{ctx.plan_path.name} has no motion inserts (\"kind\": \"motion\")")
    refp = None
    if ref:
        refp = Path(ref).expanduser()
        if not refp.is_absolute() and not refp.is_file():
            refp = ctx.episode / refp
        if not refp.is_file():
            raise ReviewError(f"reference not found: {ref}")
    review_dir = Path(out_root) if out_root else ctx.episode / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(review_dir)
    bundle = review_dir / f"motion-v{version:03d}"
    bundle.mkdir()
    eng_backend, engine_note = engine_for(backend)
    rep = plan_density(ctx)
    results, rounds = [], {}
    with tempfile.TemporaryDirectory(prefix="motion-review-") as tmp:
        engine = Engine(eng_backend, Path(tmp)) if eng_backend is not None else None
        for m in ms:
            log(f"{m.id}: {m.scene or m.source}, {len(m.frames)} frames")
            out = bundle / m.id
            out.mkdir()
            r = Review(ctx, m, out, engine, engine_note, refp, ref_offset, rep, Path(tmp), log)
            r.build_comp()
            res = r.run()
            res["compare_note"] = r.compare_note
            results.append(res)
            rounds[m.id] = round_of(review_dir, m.id, version)
            if rounds[m.id] > MAX_ROUNDS:
                res["findings"].append({"insert": m.id, "area": "Bundle", "level": "CHECK", "id": f"rounds:{m.id}",
                                        "text": f"{m.id}: review round {rounds[m.id]} (at most {MAX_ROUNDS}): the "
                                        "Showrunner asks the user now", "time": None, "fix": None})
    findings = [f for r in results for f in r["findings"]] + _density_findings(rep)
    (bundle / "critic.md").write_text(critic_md(ctx, version, results, rounds, rep, engine_note, refp is not None),
                                      encoding="utf-8")
    summary = {"bundle": str(bundle), "version": f"v{version:03d}", "plan": str(ctx.plan_path),
               "episode": ctx.episode.name, "engine": engine_note is None, "engine_note": engine_note,
               "reference": str(refp) if refp else None, "ref_offset": ref_offset, "rounds": rounds,
               "inserts": results, "density": {k: v for k, v in rep.items() if k != "findings"},
               "findings": findings, "counts": counts(findings)}
    (bundle / "bundle.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    """``crewcut render motion-review``: build the bundle. Exit 0 when it was built (the findings are for the Critic;
    ``motion_check.py`` is the gate), 2 when the plan or the arguments cannot be used."""
    ap = argparse.ArgumentParser(prog="crewcut render motion-review",
                                 description="Build the Critic's review bundle for the plan's motion inserts.")
    ap.add_argument("plan", help="edit/plan-vNNN.json")
    ap.add_argument("--ids", help="only these inserts, comma separated")
    ap.add_argument("--ref", help="reference video (refs/x.mp4, relative to the episode or the current folder)")
    ap.add_argument("--ref-offset", type=float, default=0.0, help="reference time = insert time + this (seconds)")
    ap.add_argument("--out", help="review folder (default <episode>/review)")
    ap.add_argument("--no-engine", action="store_true", help="never use effectcraft-cli (no strips, no text sizes)")
    ap.add_argument("--json", action="store_true", help="print the bundle summary as JSON")
    a = ap.parse_args(argv)
    say = (lambda *_: None) if a.json else print
    try:
        s = build_bundle(a.plan, a.ids, a.ref, a.ref_offset, a.out, False if a.no_engine else None, log=say)
    except (ReviewError, tp.TemplateError) as e:
        print(f"motion-review: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    print(f"\nBundle {s['bundle']}")
    if s["engine_note"]:
        print(f"  {s['engine_note']}")
    for r in s["inserts"]:
        print(f"  {r['id']}/: {', '.join(r['files'])}")
    order = {k: n for n, k in enumerate(LEVELS)}
    for f in sorted(s["findings"], key=lambda f: (order[f["level"]], f["time"] or 0)):
        if f["level"] in ("ERROR", "CHECK"):
            at = f" [{dens.tc(f['time'])}]" if f["time"] is not None else ""
            print(f"  {f['level']:<6}{at} {f['text']}")
            if f.get("fix"):
                print(f"         -> {f['fix']}")
    n = s["counts"]
    print(f"\nResult: {n['ERROR']} ERROR, {n['CHECK']} CHECK, {n['OK']} OK, {n['NOTE']} NOTE. "
          f"The Critic fills {Path(s['bundle']).name}/critic.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
