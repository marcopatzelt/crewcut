"""The edit plan (episodes/<id>/edit/plan-vNNN.json): parse it, resolve cues to frames, decide what is rendered where.

Pure Python: nothing here runs ffmpeg, Chromium, Blender or EffectCraft. The schema is in docs/architecture.md ("Edit
plan"). Values the plan leaves out or sets to null come from the active style pack.

Kind "motion" (EffectCraft comps, rendered by crewcut/render/motion.py): a library template (`scene`, `name@N` pins a
version) or an episode comp (`source`); cues become template params in seconds local to the insert; `motion_context`
builds the template's CC_CTX; the hash covers params, context, template and lib files, motion tokens, the engine pin
and the pack's font files. Density warnings come from crewcut/motion/density.py.

Layouts (portrait only, `layout` in the plan, else the pack's `edit_style.shorts.layout`, else "full"):
- "full": a full-frame insert covers the whole picture (the only layout of landscape plans).
- "proof-top": a full-frame insert is the proof on a stage at the top (STAGE_HEIGHT px), the speaker is cropped
  around the face into the part below; an insert with `"place": "full"` still covers everything. The last
  `end_face` seconds of the speaker cut show the face alone (the stage stops there).
In portrait plans keyword chips default to the left of the pack's `shorts.right_free_frac`: the platform's buttons sit
on the right edge of a Short.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from .. import brand, paths
from ..motion import density
from ..motion import templates as mtemplates

FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
KINDS = ("2d", "3d", "clip", "motion")
EXTRA_FRAMES = 2                                    # every 2D/3D/motion insert renders 2 frames more than it shows
PATH_KEYS = ("image", "folder", "avatar")           # data keys that carry a path, relative to the episode folder
LIST_PATH_KEYS = {"cards": ("image", "folder")}
SHARED = {"2d": ("base.css", "motion.js", "scene.js"), "3d": ("stage.py",)}   # motion: templates.lib_files()
EXT = {"2d": ".html", "3d": ".py", "motion": ".jsx"}
TEXT_SCENES = ("headline", "post")                  # inserts the viewer has to read
LAYOUTS = ("full", "proof-top")
STAGE_HEIGHT = 960                                  # proof-top: height of the proof's stage at the top (portrait)
PLACES = ("top", "full")                            # where a full-frame insert goes in proof-top
FITS = ("cover", "contain")                         # stage: fill and crop, or the whole picture as a card
ANCHORS = ("center", "top")                         # fit cover: which part of a taller picture stays
END_FACE_S = 2.0                                    # proof-top: seconds at the end with the face alone
RIGHT_FREE_FRAC = 0.18                              # portrait: right share kept free of text (platform buttons)
KEYWORD_MARGIN = 0.04                               # keyword chips keep this share of the width to the left edge
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
_SCENE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
_MOTION_SCENE = re.compile(r"^(?P<name>[A-Za-z0-9_]{1,60})(?:@(?P<version>[1-9][0-9]{0,3}))?$")
_COLORS = re.compile(r"^#?[0-9A-Fa-f]{6}$")

# kind "motion" (motion graphics rendered by EffectCraft, crewcut/render/motion.py)
STAGE_FORMAT = "stage"                              # proof-top inserts with place "top" render at the stage size
BACKDROPS = ("speaker",)                            # "backdrop": the comp gets the speaker piece as footage
LAYERS = ("behind",)                                # "layer": an overlay that sits behind the speaker (person matte)
FACE_BOX = (0.32, 0.28)                             # face box size (fractions of the frame) when the plan gives a centre
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tif", ".tiff"}
FOOTAGE_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
SOUND_LISTS = {"whoosh": "whooshes", "hit": "hits", "pop": "hits", "click": "hits", "bell": "hits",
               "tick": "typing", "reel_tick": "typing", "typing": "typing"}
MOTION_CAP_USD = {"landscape": 2.0, "portrait": 0.5}   # rented motion work per video: long-form, Short


class PlanError(ValueError):
    """The plan cannot be used as written. The message says what to change."""


def normalize(word: Any) -> str:
    """Lower case, punctuation at both ends removed: 'Thirty,' -> 'thirty'."""
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(word).strip().lower())


def load_words(p: Path) -> list[dict]:
    """Words file of the cut step: [{"w": "...", "s": 1.23, "e": 1.5}]. Also accepts word/start/end keys."""
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise PlanError(f"words file not found: {p}") from e
    except ValueError as e:
        raise PlanError(f"words file is not valid JSON: {p} ({e})") from e
    if isinstance(raw, dict):
        raw = raw.get("words", [])
    out = []
    for w in raw:
        text = w.get("w", w.get("word"))
        start = w.get("s", w.get("start"))
        if text is None or start is None:
            continue
        out.append({"w": str(text), "s": float(start), "e": float(w.get("e", w.get("end", start)))})
    return out


def render_tokens(pack: brand.Pack) -> dict:
    """The pack's render tokens, with the 3D font resolved to a file path (or None)."""
    tokens = pack.render_tokens()
    stage = dict(tokens.get("stage3d") or {})
    font = stage.get("font")
    if isinstance(font, str) and font:
        f = pack.file(font)
        stage["font"] = str(f) if f else None
    tokens["stage3d"] = stage
    return tokens


def tokens_for_hash(tokens: dict, kind: str) -> dict:
    """The part of the tokens that changes how an insert looks. Loudness and edit style do not."""
    if kind == "3d":
        keys = ("stage3d", "colors", "fonts", "motion")
    elif kind == "motion":
        keys = ("colors", "fonts", "shape", "motion_graphics")
    else:
        keys = ("colors", "fonts", "logo", "shape", "motion", "css")
    return {k: tokens.get(k) for k in keys}


def insert_hash(data: dict, files: list[Path], tokens: dict, extra: list[str] | tuple[str, ...] = ()) -> str:
    """Cache key of a rendered insert: data, template and shared files, brand tokens. 10 hex characters."""
    h = hashlib.sha1()
    h.update(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())
    for f in files:
        h.update(b"\0" + f.name.encode() + b"\0" + f.read_bytes())
    h.update(b"\0" + json.dumps(tokens, sort_keys=True, ensure_ascii=False).encode())
    for x in extra:
        h.update(b"\0" + x.encode())
    return h.hexdigest()[:10]


def font_files(tokens: dict) -> list[Path]:
    """The pack's font files (fonts.<role>.files, resolved by render_tokens), each once, in role order."""
    out: list[Path] = []
    for spec in (tokens.get("fonts") or {}).values():
        for f in (spec or {}).get("files") or []:
            p = Path(f)
            if p.is_file() and p not in out:
                out.append(p)
    return out


def motion_context(plan: Plan, ins: Insert, draft: bool = False, backdrop: str | None = None,
                   luma: list | float | None = None) -> dict:
    """CC_CTX of a motion insert (templates/motion/README.md): format, size, fps, duration (seconds of the insert),
    transparent, face (only where the speaker is in the picture: overlays and speaker backdrops), backdrop (path of the
    speaker piece, given by the renderer), draft, right_free and the brand (colours, fonts as family and weight,
    shape, mg = the resolved motion_graphics)."""
    face = None
    if ins.transparent or ins.backdrop == "speaker":
        x, y, w, h = plan.face_box()
        face = {"x": x, "y": y, "w": w, "h": h}
    size = ins.size or plan.size
    return {"format": ins.format or plan.format, "size": [size[0], size[1]], "fps": plan.fps,
            "duration": round(ins.frames / plan.fps, 6), "transparent": ins.transparent, "face": face,
            "backdrop": backdrop, "draft": bool(draft), "right_free": plan.right_free,
            "layer": plan.layer_for(ins), "plates": _plates(plan, ins), "backdrop_luma": luma,
            "brand": brand_context(plan.tokens)}


def _plates(plan: Plan, ins: Insert) -> dict:
    """CC_CTX.plates: the Blender plates of the insert ({id: {"first", "frames", "ready"}}), see render/plates.py."""
    if not ins.plates:
        return {}
    from .plates import context_plates
    return context_plates(plan, ins)


def brand_context(tokens: dict) -> dict:
    """CC_CTX.brand from the render tokens: colours, fonts as family and weight (no file paths), shape, and mg (the
    resolved motion_graphics)."""
    fonts = {role: {"family": (spec or {}).get("family"), "weight": (spec or {}).get("weight")}
             for role, spec in (tokens.get("fonts") or {}).items()}
    return {"colors": tokens.get("colors") or {}, "fonts": fonts, "shape": tokens.get("shape") or {},
            "mg": tokens.get("motion_graphics") or {}}


@dataclass
class Insert:
    id: str
    kind: str
    scene: str | None
    start_s: float
    end_s: float
    start: int                       # first frame in the video
    end: int                         # first frame after the insert
    transparent: bool
    cues: dict[str, int]             # cue name -> frame inside the insert
    data: dict                       # what the template gets (format, frames, fps and cues added)
    raw: dict
    template: Path | None = None
    shared: tuple[Path, ...] = ()
    hash: str | None = None
    out_dir: Path | None = None      # PNG frames
    clip: Path | None = None         # encoded insert (or the clip file for kind "clip")
    at: float = 0.0                  # kind clip: seconds into the file
    speed: float = 1.0               # kind clip
    place: str = "full"              # proof-top: "top" (on the stage) or "full"; overlays are always "full"
    fit: str = "cover"               # on the stage: "cover" (fill, crop) or "contain" (whole, as a card)
    anchor: str = "center"           # fit cover: "center" or "top" (keeps the top of a tall capture)
    # kind "motion" only (data holds the params the plan gives: data, cues in seconds, resolved paths)
    format: str | None = None        # landscape | portrait | stage (proof-top, place "top")
    size: tuple[int, int] | None = None
    params: dict | None = None       # data merged over the template's header defaults: what the template gets
    header: dict | None = None       # the template's parsed header (kind, formats, sounds, version, defaults)
    source: Path | None = None       # episode-local comp (plan "source"); None for a library template ("scene")
    version: int | None = None       # pinned template version ("scene": "name@N")
    backdrop: str | None = None      # "speaker": the graded, zoomed speaker piece is the comp's footage
    layer: str | None = None         # "behind": an overlay behind the speaker (matte step, docs/motion-matte.md)
    plates: tuple = ()               # Blender plates the comp needs: kept as validated data for now
    sound: bool = False              # the template's @sounds become sound events of the cut
    beat: Any = None                 # the motion plan row this insert comes from (for the Critic)
    column: Any = None
    assets: tuple[Path, ...] = ()    # image and footage files the params reference

    @property
    def frames(self) -> int:
        return self.end - self.start

    @property
    def render_frames(self) -> int:
        return self.frames + EXTRA_FRAMES if self.kind in ("2d", "3d", "motion") else 0

    @property
    def data_file(self) -> Path | None:
        return Path(str(self.out_dir) + ".json") if self.out_dir else None


class Plan:
    def __init__(self, path: Path | str, pack: brand.Pack | None = None, episode_dir: Path | str | None = None):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise PlanError(f"plan not found: {path}")
        try:
            self.p: dict = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise PlanError(f"plan is not valid JSON: {self.path.name} ({e})") from e
        if not isinstance(self.p, dict):
            raise PlanError("the plan must be a JSON object")
        self.episode_dir = Path(episode_dir).resolve() if episode_dir else self.path.parent.parent
        self.episode = self.episode_dir.name
        self.pack = pack or brand.load()
        pj = self.episode_dir / "project.json"
        try:
            self.project = json.loads(pj.read_text(encoding="utf-8")) if pj.is_file() else {}
        except ValueError:
            self.project = {}
        fmt = self.p.get("format") or self.project.get("format") or self.pack.value("edit_style.format", "landscape")
        if fmt not in FORMATS:
            raise PlanError(f"format must be landscape or portrait, got {fmt!r}")
        self.format = fmt
        self.size = FORMATS[fmt]
        self.fps = int(self.p.get("fps") or self.project.get("fps") or self.pack.value("edit_style.fps", 25))
        self.layout = self._layout()
        self.end_face_s = max(0.0, float(self.value("end_face", "edit_style.shorts.end_face_s", END_FACE_S)))
        self.right_free = min(0.5, max(0.0, float(self.value("right_free", "edit_style.shorts.right_free_frac",
                                                              RIGHT_FREE_FRAC))))
        self.words = load_words(self.local(self.p["words"])) if self.p.get("words") else []
        self.tokens = render_tokens(self.pack)
        self.dropped: dict[str, str] = {}             # insert id -> why it is left out of this cut (see drop())
        self.inserts: list[Insert] = []
        for e in self.p.get("inserts") or []:
            ins = self._insert(e)
            if any(x.id == ins.id for x in self.inserts):
                raise PlanError(f"insert id {ins.id} is used twice")
            self.inserts.append(ins)
        self.warnings = self._check()

    def _layout(self) -> str:
        """The plan's layout; a portrait plan without one takes the pack's Shorts layout. Landscape is always full."""
        v = self.p.get("layout")
        if v is None and self.format == "portrait":
            v = self.pack.value("edit_style.shorts.layout", "full")
        v = v or "full"
        if v not in LAYOUTS:
            raise PlanError(f"layout must be one of {', '.join(LAYOUTS)}, got {v!r}")
        if v != "full" and self.format != "portrait":
            raise PlanError(f"layout {v} is for portrait plans (Shorts); this plan is {self.format}")
        return v

    @property
    def stage_size(self) -> tuple[int, int]:
        return self.size[0], STAGE_HEIGHT

    # ---- paths ------------------------------------------------------------------------------------------------
    def local(self, rel: str | os.PathLike) -> Path:
        """A path from the plan: relative to the episode folder; absolute only inside the studio or the pack."""
        p = Path(rel).expanduser()
        try:
            if not p.is_absolute():
                return paths.inside(self.episode_dir, str(rel))
        except ValueError as e:
            raise PlanError(f"{rel}: a path in the plan must stay inside the episode folder") from e
        p = p.resolve()
        for base in (self.episode_dir, paths.studio_root(), self.pack.dir):
            b = Path(base).resolve()
            if p == b or b in p.parents:
                return p
        raise PlanError(f"{rel}: absolute paths must be inside the studio folder")

    @property
    def output(self) -> Path:
        return self.local(self.p.get("output") or f"export/{self.path.stem}.mp4")

    @property
    def shown_path(self) -> Path:
        return Path(str(self.output) + ".shown")

    def template_for(self, kind: str, scene: str) -> tuple[Path, tuple[Path, ...]]:
        """The scene file and its shared files. A copy in the pack (brand/templates/<kind>/) wins over the app's."""
        dirs = []
        if not self.pack.is_neutral:
            dirs.append(Path(self.pack.dir) / "templates" / kind)
        dirs.append(paths.templates_dir() / kind)
        for d in dirs:
            p = d / f"{scene}{EXT[kind]}"
            if p.is_file():
                shared = tuple(d / n for n in SHARED[kind])
                missing = [s.name for s in shared if not s.is_file()]
                if missing:
                    raise PlanError(f"{p} needs {', '.join(missing)} in the same folder")
                return p, shared
        app = paths.templates_dir() / kind
        names = sorted(x.stem for x in app.glob(f"*{EXT[kind]}") if x.name not in SHARED[kind]) if app.is_dir() else []
        raise PlanError(f"no {kind} scene '{scene}'. Available: {', '.join(names) or 'none'}")

    # ---- cues and sound references ------------------------------------------------------------------------------
    def word_time(self, word: str, after: float = 0.0) -> float:
        """Start time of the first occurrence of a word (or a phrase of several words) at or after `after` seconds."""
        want = [t for t in (normalize(x) for x in str(word).split()) if t]
        if not want:
            raise PlanError(f"empty word in a cue: {word!r}")
        if not self.words:
            raise PlanError("a cue by word needs 'words' in the plan (the words file of the cut step)")
        W = self.words
        for i, w in enumerate(W):
            if w["s"] < after - 0.05:
                continue
            if all(i + k < len(W) and normalize(W[i + k]["w"]) == t for k, t in enumerate(want)):
                return w["s"]
        raise PlanError(f"word '{word}' not found at or after {after:.2f} s in {self.p.get('words')}")

    def cue_frame(self, cue: Any, start: int, start_s: float) -> int:
        """A cue as a frame inside the insert: a number, {"word", "after", "offset"} or {"time", "offset"}."""
        if isinstance(cue, bool):
            raise PlanError(f"bad cue {cue!r}")
        if isinstance(cue, (int, float)):
            return int(round(cue))
        if isinstance(cue, dict):
            offset = int(cue.get("offset", 0) or 0)
            if "word" in cue:
                after = float(cue["after"]) if cue.get("after") is not None else start_s
                return round(self.word_time(cue["word"], after) * self.fps) - start + offset
            if "time" in cue:
                return round(float(cue["time"]) * self.fps) - start + offset
        raise PlanError(f"bad cue {cue!r}: use a frame number, {{\"word\": ...}} or {{\"time\": ...}}")

    def anchor_time(self, v: Any, after: float = 0.0) -> float:
        """An insert's start or end: seconds, or a word anchor {"word": "costs", "offset": -0.6, "after": 12.0} (the
        first time the word is spoken at or after `after`, default: the start for an end, else 0; offset in seconds),
        or {"time": 12.4, "offset": -0.2}."""
        if isinstance(v, bool):
            raise ValueError(f"bad time {v!r}")
        if isinstance(v, dict):
            off = float(v.get("offset") or 0.0)
            if "word" in v:
                a = float(v["after"]) if v.get("after") is not None else after
                return round(self.word_time(v["word"], a) + off, 4)
            if "time" in v:
                return round(float(v["time"]) + off, 4)
            raise ValueError(f"bad time {v!r}")
        return float(v)

    def by_id(self, iid: str) -> Insert:
        for x in self.inserts:
            if x.id == iid:
                return x
        raise PlanError(f"no insert with id {iid!r}")

    def ref_frame(self, ref: Any) -> int:
        """A sound reference as a frame of the video: "s1" (start of insert s1), "s1@value" (its cue), or seconds."""
        if isinstance(ref, bool):
            raise PlanError(f"bad sound reference {ref!r}")
        if isinstance(ref, (int, float)):
            return round(float(ref) * self.fps)
        if isinstance(ref, str):
            iid, _, cue = ref.partition("@")
            ins = self.by_id(iid)
            if not cue:
                return ins.start
            if cue not in ins.cues:
                raise PlanError(f"insert {iid} has no cue '{cue}' (cues: {', '.join(ins.cues) or 'none'})")
            return ins.start + ins.cues[cue]
        raise PlanError(f"bad sound reference {ref!r}: use \"id\", \"id@cue\" or seconds")

    # ---- inserts ------------------------------------------------------------------------------------------------
    def _resolve_paths(self, data: dict) -> list[str]:
        """Turn data paths into file:// URLs (the renderer page is a file:// page). Returns stat lines for the hash."""
        stats: list[str] = []

        def one(v):
            if not isinstance(v, str) or not v or "://" in v:
                return v
            p = self.local(v)
            if p.is_file():
                st = p.stat()
                stats.append(f"{p}:{st.st_size}:{st.st_mtime_ns}")
            elif p.is_dir():
                stats.append(f"{p}:{sum(1 for _ in p.iterdir())}")
            return p.as_uri()

        for k in PATH_KEYS:
            if k in data:
                data[k] = one(data[k])
        for lk, keys in LIST_PATH_KEYS.items():
            if isinstance(data.get(lk), list):
                for item in data[lk]:
                    if isinstance(item, dict):
                        for k in keys:
                            if k in item:
                                item[k] = one(item[k])
        return sorted(stats)

    def _insert(self, e: dict) -> Insert:
        if not isinstance(e, dict):
            raise PlanError(f"an insert must be an object, got {e!r}")
        iid = str(e.get("id") or "")
        if not _ID.match(iid):
            raise PlanError(f"insert id {iid!r}: letters, digits, - and _ only")
        kind = e.get("kind")
        if kind not in KINDS:
            raise PlanError(f"insert {iid}: kind must be one of {', '.join(KINDS)}")
        try:
            start_s = self.anchor_time(e["start"], 0.0)
            end_s = self.anchor_time(e["end"], start_s)
        except PlanError as ex:
            raise PlanError(f"insert {iid}: {ex}") from ex
        except (KeyError, TypeError, ValueError) as ex:
            raise PlanError(f"insert {iid}: start and end (seconds or {{\"word\": ...}}) are required") from ex
        start, end = round(start_s * self.fps), round(end_s * self.fps)
        if end <= start:
            raise PlanError(f"insert {iid}: end must be after start")
        if kind == "motion":
            return self._motion(e, iid, start_s, end_s, start, end)
        transparent = bool(e.get("transparent"))
        if kind == "clip":
            if not e.get("file"):
                raise PlanError(f"insert {iid}: a clip needs 'file'")
            speed = float(e.get("speed") or 1.0)
            if speed <= 0:
                raise PlanError(f"insert {iid}: speed must be above 0")
            f = self.local(e["file"])
            return self._placed(Insert(iid, kind, None, start_s, end_s, start, end, transparent, {}, {}, e, clip=f,
                                       at=float(e.get("at") or 0.0), speed=speed))
        scene = str(e.get("scene") or "")
        if not _SCENE.match(scene):
            raise PlanError(f"insert {iid}: scene name {scene!r} is not valid")
        if kind == "3d" and transparent:
            raise PlanError(f"insert {iid}: 3D inserts are full frame; transparent is for 2D overlays")
        cues = {str(n): self.cue_frame(c, start, start_s) for n, c in (e.get("cues") or {}).items()}
        data = copy.deepcopy(e.get("data") or {})
        if not isinstance(data, dict):
            raise PlanError(f"insert {iid}: data must be an object")
        data.update(format=self.format, frames=end - start + EXTRA_FRAMES, fps=self.fps, cues=cues)
        if scene == "keyword" and self.format == "portrait":
            self._keyword_defaults(data)
        stats = self._resolve_paths(data)
        template, shared = self.template_for(kind, scene)
        h = insert_hash(data, [template, *shared], tokens_for_hash(self.tokens, kind), stats)
        out_dir = self.episode_dir / "render" / "inserts" / f"{iid}-{h}"
        clip = Path(str(out_dir) + (".mov" if transparent else ".mp4"))
        return self._placed(Insert(iid, kind, scene, start_s, end_s, start, end, transparent, cues, data, e,
                                   template=template, shared=shared, hash=h, out_dir=out_dir, clip=clip))

    def _place(self, iid: str, e: dict, transparent: bool) -> str:
        """Where a full-frame insert goes in proof-top ("top" on the stage, or "full"). Overlays are always "full"."""
        place = e.get("place") or ("top" if self.layout == "proof-top" and not transparent else "full")
        if place not in PLACES:
            raise PlanError(f"insert {iid}: place must be one of {', '.join(PLACES)}")
        if place == "top" and (self.layout != "proof-top" or transparent):
            raise PlanError(f"insert {iid}: place 'top' needs layout proof-top and a full-frame insert")
        return place

    # ---- kind "motion" ---------------------------------------------------------------------------------------------
    def motion_dirs(self) -> list[Path]:
        """Folders of library motion templates: the pack's brand/templates/motion/ wins over the app's."""
        dirs = [] if self.pack.is_neutral else [Path(self.pack.dir) / "templates" / "motion"]
        return [*dirs, mtemplates.app_dir()]

    def motion_template(self, name: str, version: int | None = None) -> Path:
        """The .jsx of a library template. With a version N: <name>.jsx when its @version is N (no @version counts as
        1), else <name>.vN.jsx in the same folder."""
        for d in self.motion_dirs():
            cur = d / f"{name}.jsx"
            if version is None:
                if cur.is_file():
                    return cur
                continue
            if cur.is_file():
                try:
                    v = mtemplates.parse_header(cur.read_text(encoding="utf-8")).get("version") or 1
                except mtemplates.TemplateError:
                    v = None
                if v == version:
                    return cur
            old = d / f"{name}.v{version}.jsx"
            if old.is_file():
                return old
        names = sorted({p.stem for d in self.motion_dirs() if d.is_dir() for p in d.glob("*.jsx") if "." not in p.stem})
        want = f"{name}@{version}" if version else name
        raise PlanError(f"no motion template '{want}'. Available: {', '.join(names) or 'none'}")

    def episode_file(self, rel: str, what: str) -> Path:
        """A file inside the episode folder (relative path only)."""
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
            raise PlanError(f"{what} must be a path relative to the episode folder, got {rel!r}")
        try:
            p = paths.inside(self.episode_dir, rel)
        except ValueError as e:
            raise PlanError(f"{what} {rel}: the path must stay inside the episode folder") from e
        if not p.is_file():
            raise PlanError(f"{what} not found: {rel}")
        return p

    def _motion_paths(self, params: dict) -> list[Path]:
        """Relative image and footage paths in the params (at any depth) become absolute paths inside the episode
        folder. Returns the files."""
        files: list[Path] = []

        def one(v: Any) -> Any:
            if isinstance(v, dict):
                return {k: one(x) for k, x in v.items()}
            if isinstance(v, list):
                return [one(x) for x in v]
            if not isinstance(v, str) or "://" in v or Path(v).suffix.lower() not in IMAGE_EXT | FOOTAGE_EXT:
                return v
            try:
                p = self.local(v)
            except PlanError:
                return v
            if not p.is_file():
                return v
            files.append(p)
            return str(p)

        for k in list(params):
            params[k] = one(params[k])
        return sorted(set(files))

    def _plates(self, iid: str, plates: Any) -> tuple:
        """`plates`: [{"id", "script", "args", "frames"}] (Blender jobs before the comp). Only the shape is checked."""
        if plates in (None, []):
            return ()
        if not isinstance(plates, list):
            raise PlanError(f"insert {iid}: plates must be a list of {{\"id\", \"script\", \"args\", \"frames\"}}")
        out = []
        for i, pl in enumerate(plates):
            ok = (isinstance(pl, dict) and isinstance(pl.get("id"), str) and _ID.match(pl["id"])
                  and isinstance(pl.get("script"), str) and pl["script"].endswith(".py")
                  and isinstance(pl.get("args", {}), dict) and isinstance(pl.get("frames"), int)
                  and not isinstance(pl.get("frames"), bool) and pl["frames"] > 0)
            if not ok:
                raise PlanError(f"insert {iid}: plate {i + 1} needs id (letters, digits, - and _), script (a .py "
                                "file), args (an object) and frames (a whole number above 0)")
            out.append(copy.deepcopy(pl))
        if len({pl["id"] for pl in out}) != len(out):
            raise PlanError(f"insert {iid}: plate ids must be unique")
        return tuple(out)

    def backdrop_key(self, start: int, frames: int) -> str:
        """What the speaker backdrop of a span is made of (for the hash): the base file's stat, the zoom, the span."""
        color = self.base_color()
        if color:
            src = f"color:{color}"
        else:
            if not self.p.get("base"):
                raise PlanError("a speaker backdrop needs 'base' (the speaker cut)")
            b = self.local(self.p["base"])
            st = b.stat() if b.is_file() else None
            src = f"{b}:{st.st_size}:{st.st_mtime_ns}" if st else f"{b}:missing"
        return f"backdrop:{src}:{start}:{frames}:{self.zoom_at(start):g}:{self.face}"

    def zoom_at(self, frame: int) -> float:
        """The speaker zoom shown at a frame (the last zoom mark at or before it)."""
        z = 1.0
        for at, zz in self.speaker_marks():
            if at <= frame:
                z = zz
        return z

    def _motion(self, e: dict, iid: str, start_s: float, end_s: float, start: int, end: int) -> Insert:
        scene, source = e.get("scene"), e.get("source")
        if bool(scene) == bool(source):
            raise PlanError(f"insert {iid}: a motion insert needs exactly one of scene (a library template) or "
                            "source (a comp in the episode folder)")
        version = None
        if source:
            template = self.episode_file(source, f"insert {iid}: source")
            if template.suffix != ".jsx":
                raise PlanError(f"insert {iid}: source must be a .jsx comp")
        else:
            m = _MOTION_SCENE.match(str(scene))
            if not m:
                raise PlanError(f"insert {iid}: scene {scene!r} is not a template name (name or name@version)")
            version = int(m.group("version")) if m.group("version") else None
            template = self.motion_template(m.group("name"), version)
        try:
            header = mtemplates.parse_header(template.read_text(encoding="utf-8"))
            shared = tuple(mtemplates.lib_files())
        except mtemplates.TemplateError as ex:
            raise PlanError(f"insert {iid}: {ex}") from ex
        backdrop, layer = e.get("backdrop"), e.get("layer")
        if backdrop is not None and backdrop not in BACKDROPS:
            raise PlanError(f"insert {iid}: backdrop must be null or \"speaker\"")
        if layer is not None and layer not in LAYERS:
            raise PlanError(f"insert {iid}: layer must be null or \"behind\"")
        transparent = e.get("transparent")
        transparent = (header.get("kind") == "overlay") if transparent is None else bool(transparent)
        if backdrop and transparent:
            raise PlanError(f"insert {iid}: backdrop \"speaker\" is for full-frame inserts (transparent false)")
        if layer and not transparent:
            raise PlanError(f"insert {iid}: layer \"behind\" is for overlays (transparent true)")
        place = self._place(iid, e, transparent)
        fmt = STAGE_FORMAT if place == "top" else self.format
        size = self.stage_size if place == "top" else self.size
        formats = header.get("formats")
        if formats and fmt not in formats:
            raise PlanError(f"insert {iid}: template {header['name']} has no {fmt} format (it has {', '.join(formats)})")
        defaults = header.get("defaults") or {}
        cues = {str(n): self.cue_frame(c, start, start_s) for n, c in (e.get("cues") or {}).items()}
        bad = sorted(n for n in cues if n not in defaults)
        if bad:
            raise PlanError(f"insert {iid}: cue {', '.join(bad)} is not a parameter of {header['name']} "
                            f"(parameters: {', '.join(sorted(defaults)) or 'none'})")
        data = copy.deepcopy(e.get("data") or {})
        if not isinstance(data, dict):
            raise PlanError(f"insert {iid}: data must be an object")
        both = sorted(set(data) & set(cues))
        if both:
            raise PlanError(f"insert {iid}: {', '.join(both)} is set in data and in cues; keep one")
        data.update({n: round(f / self.fps, 4) for n, f in cues.items()})
        assets = self._motion_paths(data)
        try:
            params = mtemplates.merge(defaults, data)
        except mtemplates.TemplateError as ex:
            raise PlanError(f"insert {iid}: {ex}") from ex
        plates = self._plates(iid, e.get("plates"))
        ins = Insert(iid, "motion", header["name"], start_s, end_s, start, end, transparent, cues, data, e,
                     template=template, shared=shared, format=fmt, size=size, params=params, header=header,
                     source=template if source else None, version=version, backdrop=backdrop, layer=layer,
                     plates=plates, sound=bool(e.get("sound")), beat=e.get("beat"), column=e.get("column"),
                     assets=tuple(assets))
        ins.place = place
        self._motion_hashed(ins)
        return self._placed(ins)

    def motion_hash(self, ins: Insert, draft: bool = False) -> str:
        """Cache key of a motion insert: its params, the context (the backdrop by what it is made of, not by its
        path), the .jsx and every lib file, the look tokens, the engine pin and the pack's font files."""
        extra = [f"{p}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in ins.assets] + self._engine_keys()
        if ins.backdrop or (ins.transparent and (self.p.get("base") or self.base_color())):
            extra.append(self.backdrop_key(ins.start, ins.render_frames))
        key = {"params": ins.data, "context": motion_context(self, ins, draft=draft)}
        return insert_hash(key, [ins.template, *ins.shared], tokens_for_hash(self.tokens, "motion"), extra)

    def _motion_hashed(self, ins: Insert, draft: bool = False) -> Insert:
        ins.hash = self.motion_hash(ins, draft)
        ins.out_dir = self.episode_dir / "render" / "inserts" / f"{ins.id}-{ins.hash}"
        ins.clip = Path(str(ins.out_dir) + (".mov" if ins.transparent else ".mp4"))
        return ins

    def motion_draft(self, ins: Insert) -> Insert:
        """The draft of a motion insert (8 blur samples): its own hash and folder, so the cut never uses a draft."""
        return self._motion_hashed(dataclasses.replace(ins), draft=True)

    def _engine_keys(self) -> list[str]:
        """Cache key parts every motion insert shares: the engine pin and the pack's font files (size, time)."""
        if getattr(self, "_ekeys", None) is None:
            from .. import doctor  # late: doctor pulls in the database and the engines
            keys = ["pin:" + json.dumps(doctor.read_pin(), sort_keys=True)]
            for f in font_files(self.tokens):
                st = f.stat()
                keys.append(f"font:{f.name}:{st.st_size}:{st.st_mtime_ns}")
            self._ekeys = keys
        return self._ekeys

    def _placed(self, ins: Insert) -> Insert:
        """Where a full-frame insert goes (place, fit, anchor). Overlays always lie over the whole picture."""
        e = ins.raw
        place = self._place(ins.id, e, ins.transparent)
        fit, anchor = e.get("fit") or "cover", e.get("anchor") or "center"
        if fit not in FITS:
            raise PlanError(f"insert {ins.id}: fit must be one of {', '.join(FITS)}")
        if anchor not in ANCHORS:
            raise PlanError(f"insert {ins.id}: anchor must be one of {', '.join(ANCHORS)}")
        ins.place, ins.fit, ins.anchor = place, fit, anchor
        return ins

    def _keyword_defaults(self, data: dict) -> None:
        """Portrait: keyword chips stay left of the free right strip; in proof-top they sit on the seam by default."""
        free = 1.0 - self.right_free
        data.setdefault("x", round(free / 2, 4))
        data.setdefault("max_width", round(max(0.3, free - 2 * KEYWORD_MARGIN), 4))
        if self.layout == "proof-top":
            data.setdefault("y", round(STAGE_HEIGHT / self.size[1], 4))
        for w in data.get("words") or []:
            if isinstance(w, dict):
                w.setdefault("x", data["x"])

    def done(self, ins: Insert) -> set[int]:
        """Frame numbers already rendered for this insert."""
        if ins.kind == "clip" or not ins.out_dir or not ins.out_dir.is_dir():
            return set()
        out = set()
        for name in os.listdir(ins.out_dir):
            if len(name) == 8 and name.endswith(".png") and name[:4].isdigit():
                out.add(int(name[:4]))
        return out

    def missing(self, ins: Insert) -> list[int]:
        if ins.kind == "clip":
            return [] if ins.clip and ins.clip.is_file() else [0]
        have = self.done(ins)
        return [i for i in range(ins.render_frames) if i not in have]

    def of_kind(self, kind: str, ids: list[str] | None = None) -> list[Insert]:
        out = [x for x in self.inserts if x.kind == kind]
        if ids:
            unknown = [i for i in ids if not any(x.id == i for x in self.inserts)]
            if unknown:
                raise PlanError(f"no insert with id {', '.join(unknown)}")
            out = [x for x in out if x.id in ids]
        return out

    # ---- values with pack defaults ------------------------------------------------------------------------------
    def value(self, plan_key: str, pack_key: str, default: Any = None, section: dict | None = None) -> Any:
        """A plan value; null or missing falls back to the style pack (edit-style.json), then to `default`."""
        src = self.p if section is None else section
        v = src.get(plan_key)
        return v if v is not None else self.pack.value(pack_key, default)

    @property
    def face(self) -> tuple[float, float]:
        """Face centre (fractions of the frame). The plan's `face` is [x, y], [x, y, w, h] or {"x", "y", "w", "h"}."""
        x, y, _, _ = self.face_box()
        return x, y

    # ---- behind the speaker (docs/motion-matte.md) ------------------------------------------------------------
    def matte_dir(self, ins: Insert) -> Path:
        """render/matte/<insert id>/: the person matte of the insert's span (alpha, foreground, edge check, decision)."""
        return self.episode_dir / "render" / "matte" / ins.id

    def matte_decision(self, ins: Insert) -> dict | None:
        """The matte step's decision for a "behind" overlay ({"place": "behind" | "beside", "reason", ...}) or None."""
        f = self.matte_dir(ins) / "decision.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
        except ValueError:
            return None
        return d if isinstance(d, dict) else None

    def layer_for(self, ins: Insert) -> str | None:
        """CC_CTX.layer: "behind" only after the matte passed its edge check; an overlay asked to go behind without
        a passed matte goes "beside" the person (the automatic fallback). None for every other insert."""
        if ins.layer != "behind":
            return None
        d = self.matte_decision(ins) or {}
        return "behind" if d.get("place") == "behind" else "beside"

    def behind_clip(self, ins: Insert) -> Path | None:
        """The finished full-frame picture of a "behind" overlay (speaker, graphic, person on top), when it exists."""
        if self.layer_for(ins) != "behind" or not ins.out_dir:
            return None
        p = Path(str(ins.out_dir) + "-behind.mp4")
        return p if p.is_file() else None

    def face_box(self) -> tuple[float, float, float, float]:
        """Face centre and box size (fractions of the frame); the size defaults to FACE_BOX."""
        f = self.p.get("face") or [0.5, 0.38]
        try:
            if isinstance(f, dict):
                return (float(f.get("x", 0.5)), float(f.get("y", 0.38)), float(f.get("w") or FACE_BOX[0]),
                        float(f.get("h") or FACE_BOX[1]))
            w, h = (float(f[2]), float(f[3])) if len(f) >= 4 else FACE_BOX
            return float(f[0]), float(f[1]), w, h
        except (TypeError, ValueError, IndexError, KeyError) as e:
            raise PlanError(f"face must be [x, y], [x, y, w, h] or {{\"x\", \"y\", \"w\", \"h\"}}, got {f!r}") from e

    def speaker_marks(self) -> list[tuple[int, float]]:
        """(frame, zoom) marks for the speaker, zoom limited by the pack's zoom_max."""
        zmax = float(self.pack.value("edit_style.zoom_max", 1.15))
        out = []
        for m in self.p.get("speaker") or []:
            z = max(1.0, min(zmax, float(m.get("zoom", 1.0))))
            out.append((round(float(m["at"]) * self.fps), z))
        return sorted(out)

    def color(self, name: str, what: str) -> str:
        """A pack colour name (paper, soft, ...) or #RRGGBB as #RRGGBB."""
        c = str(name)
        if not _COLORS.match(c):
            c = str(self.pack.value(f"brand.colors.{c}", "") or "")
        if not _COLORS.match(c):
            raise PlanError(f"{what} must be a pack colour name (paper, soft, ...) or #RRGGBB")
        return "#" + c.lstrip("#").upper()

    def base_color(self) -> str | None:
        """A generated base ({"color": "soft", "seconds": 12}) as #RRGGBB, or None when the base is a file."""
        b = self.p.get("base")
        if not isinstance(b, dict):
            return None
        return self.color(b.get("color") or "soft", "base.color")

    def stage_color(self) -> str:
        """proof-top: the colour around a card (fit contain) on the stage. Plan `stage_color`, default the pack's soft."""
        return self.color(self.p.get("stage_color") or "soft", "stage_color")

    # ---- motion: sound events, left-out inserts --------------------------------------------------------------------
    def motion_sounds(self) -> tuple[dict[str, list[float]], list[str]]:
        """Sound events of motion inserts with `"sound": true`, from the template's @sounds: "in" = the insert's
        start, "out" = its end minus the pack's exit_s, a number or a param name = the start plus those seconds.
        At most one sound per insert; none on a keyword_pop right after a keyword_pop. Returns ({"hits": [s, ...],
        "whooshes": [...], "typing": [...]}, notes)."""
        out: dict[str, list[float]] = {"hits": [], "whooshes": [], "typing": []}
        notes: list[str] = []
        exit_s = float((self.tokens.get("motion_graphics") or {}).get("exit_s") or 0.25)
        prev = None
        for x in sorted((i for i in self.inserts if i.kind == "motion"), key=lambda i: i.start):
            in_a_row = x.scene == "keyword_pop" and prev == "keyword_pop"
            prev = x.scene
            if not x.sound:
                continue
            if in_a_row:
                notes.append(f"{x.id}: no sound (a keyword_pop right after a keyword_pop stays silent)")
                continue
            for snd in (x.header or {}).get("sounds") or []:
                lst = SOUND_LISTS.get(snd["sound"])
                at = snd["at"]
                if lst is None:
                    notes.append(f"{x.id}: sound {snd['sound']!r} is not one of {', '.join(sorted(SOUND_LISTS))}")
                    continue
                if at == "in":
                    t = x.start / self.fps
                elif at == "out":
                    t = max(x.start, x.end - round(exit_s * self.fps)) / self.fps
                elif isinstance(at, (int, float)):
                    t = x.start / self.fps + float(at)
                elif isinstance((x.params or {}).get(at), (int, float)) and not isinstance(x.params[at], bool):
                    t = x.start / self.fps + float(x.params[at])
                else:
                    notes.append(f"{x.id}: sound at {at!r} is not in, out or a param in seconds")
                    continue
                out[lst].append(round(t, 3))
                break                                   # one sound per motion graphic
            else:
                notes.append(f"{x.id}: sound is on, but template {x.scene} names no usable sound (@sounds)")
        return out, notes

    def drop(self, ids: list[str], why: str) -> None:
        """Leave these inserts out of the cut (e.g. motion graphics without the engine and `motion_without_engine`
        "skip"). Their sound events and the plan's sound references to them go too."""
        for i in ids:
            self.dropped[i] = why
        self.inserts = [x for x in self.inserts if x.id not in self.dropped]

    def _refers_to_dropped(self, entry: Any) -> bool:
        ref = entry.get("at") if isinstance(entry, dict) else (entry[0] if isinstance(entry, list) and entry else entry)
        return isinstance(ref, str) and ref.partition("@")[0] in self.dropped

    def sound_entries(self, key: str) -> list:
        """One list of plan["sound"][key] ("hits", "typing", "whooshes") plus the motion inserts' sound events."""
        own = [x for x in (self.p.get("sound") or {}).get(key) or [] if not self._refers_to_dropped(x)]
        return own + self.motion_sounds()[0].get(key, [])

    def length_s(self) -> float:
        """Length of the video as far as the plan knows without media: generated base, last word, last insert."""
        b = self.p.get("base")
        if isinstance(b, dict) and b.get("seconds"):
            n = float(b["seconds"])
        elif self.words:
            n = max(w["e"] for w in self.words)
        else:
            n = max((x.end_s for x in self.inserts), default=0.0)
        return n + float(self.p.get("tail") or 0)

    # ---- checks ---------------------------------------------------------------------------------------------------
    def _check(self) -> list[str]:
        out = []
        full = sorted((x for x in self.inserts if not x.transparent), key=lambda x: x.start)
        for a, b in pairwise(full):
            if b.start < a.end:
                out.append(f"{a.id} and {b.id} overlap ({b.start}-{a.end}); the earlier one is shown")
        for x in self.inserts:
            for n, f in x.cues.items():
                if not 0 <= f < x.frames:
                    out.append(f"{x.id}: cue '{n}' at frame {f} lies outside the insert (0-{x.frames - 1})")
        texts = sum(1 for x in self.inserts if x.scene in TEXT_SCENES)
        limit = self.pack.value("edit_style.text_cards_max")
        if isinstance(limit, (int, float)) and texts > limit:
            out.append(f"{texts} text cards (headline, post); the style pack allows {int(limit)}")
        if self.format == "portrait":
            edge = 1.0 - self.right_free
            for x in self.inserts:
                if x.scene != "keyword":
                    continue
                xs = [x.data.get("x")] + [w.get("x") for w in x.data.get("words") or [] if isinstance(w, dict)]
                if any(isinstance(v, (int, float)) and v > edge for v in xs):
                    out.append(f"{x.id}: a keyword centre lies in the right {self.right_free:.0%} of the frame, "
                               "where the platform's buttons are")
        return out + self._motion_checks()

    def motion_limits(self) -> dict:
        """The motion limits: edit-style.json `motion` over crewcut.motion.density's neutral numbers."""
        return density.limits(self.pack.edit_style)

    def _motion_checks(self) -> list[str]:
        """Motion warnings: a template used against its @kind, one number shown twice (counter and number_roll), and
        the density report of crewcut.motion.density (lengths, big moments, motion per minute, the 6 s gap, one per
        sentence, heroes, sounds, the speaker alone at the start and end, keyword and keyword_pop together)."""
        ms = [x for x in self.inserts if x.kind == "motion"]
        if not ms:
            return []
        out = []
        for x in ms:
            kind = (x.header or {}).get("kind")
            if kind == "overlay" and not x.transparent:
                out.append(f"{x.id}: {x.scene} is an overlay template but the insert is full frame (transparent false)")
            if kind == "full" and x.transparent:
                out.append(f"{x.id}: {x.scene} is a full-frame template but the insert is an overlay")
        counters = {str(x.data.get("value")) for x in self.inserts if x.kind == "2d" and x.scene == "counter"}
        for x in ms:
            if x.scene == "number_roll" and str((x.params or {}).get("value")) in counters:
                out.append(f"{x.id}: the number {x.params.get('value')} is also a 2D counter; one statement, one form")
        rep = density.count(self.density_plan(), self.words, self.motion_limits(), total_s=self.length_s())
        out += [f["text"] for f in rep["findings"] if f["level"] in ("ERROR", "CHECK")]
        return out

    def density_plan(self) -> dict:
        """The plan as crewcut.motion.density reads it, with what parsing decided: start and end in seconds, the
        template's name and `transparent` (a motion insert without it takes its template's @kind)."""
        p = copy.deepcopy(self.p)
        by_id = {x.id: x for x in self.inserts}
        for e in p.get("inserts") or []:
            x = by_id.get(str(e.get("id"))) if isinstance(e, dict) else None
            if x is not None:
                e.update(start=x.start_s, end=x.end_s, transparent=x.transparent)
                if x.kind == "motion":
                    e["scene"] = x.scene
        p["format"] = self.format
        return p

    def summary(self) -> dict:
        return {
            "plan": self.path.name, "episode": self.episode, "format": self.format, "fps": self.fps,
            "layout": self.layout,
            "output": str(self.output), "shown": self.shown_path.is_file(), "warnings": self.warnings,
            "inserts": [{"id": x.id, "kind": x.kind, "scene": x.scene or (x.clip.name if x.clip else None),
                         "start": x.start_s, "end": x.end_s, "frames": x.frames, "cues": x.cues,
                         "transparent": x.transparent, "place": x.place, "missing": len(self.missing(x)),
                         "clip": str(x.clip) if x.clip else None, **self._motion_row(x)} for x in self.inserts],
        }

    def _motion_row(self, x: Insert) -> dict:
        if x.kind != "motion":
            return {}
        return {"format": x.format, "source": str(x.source.relative_to(self.episode_dir)) if x.source else None,
                "version": x.version, "backdrop": x.backdrop, "layer": x.layer, "sound": x.sound,
                "plates": [p["id"] for p in x.plates], "hash": x.hash}
