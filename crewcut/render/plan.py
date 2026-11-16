"""The edit plan (episodes/<id>/edit/plan-vNNN.json): parse it, resolve cues to frames, decide what is rendered where.

Pure Python: nothing here runs ffmpeg, Chromium or Blender. The schema is in docs/architecture.md ("Edit plan").
Values the plan leaves out or sets to null come from the active style pack.

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
import hashlib
import json
import os
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from .. import brand, paths

FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
KINDS = ("2d", "3d", "clip")
EXTRA_FRAMES = 2                                    # every 2D/3D insert renders 2 frames more than it shows
PATH_KEYS = ("image", "folder", "avatar")           # data keys that carry a path, relative to the episode folder
LIST_PATH_KEYS = {"cards": ("image", "folder")}
SHARED = {"2d": ("base.css", "motion.js", "scene.js"), "3d": ("stage.py",)}
EXT = {"2d": ".html", "3d": ".py"}
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
_COLORS = re.compile(r"^#?[0-9A-Fa-f]{6}$")


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

    @property
    def frames(self) -> int:
        return self.end - self.start

    @property
    def render_frames(self) -> int:
        return self.frames + EXTRA_FRAMES if self.kind in ("2d", "3d") else 0

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
            start_s, end_s = float(e["start"]), float(e["end"])
        except (KeyError, TypeError, ValueError) as ex:
            raise PlanError(f"insert {iid}: start and end (seconds) are required") from ex
        start, end = round(start_s * self.fps), round(end_s * self.fps)
        if end <= start:
            raise PlanError(f"insert {iid}: end must be after start")
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

    def _placed(self, ins: Insert) -> Insert:
        """Where a full-frame insert goes (place, fit, anchor). Overlays always lie over the whole picture."""
        e = ins.raw
        place = e.get("place") or ("top" if self.layout == "proof-top" and not ins.transparent else "full")
        if place not in PLACES:
            raise PlanError(f"insert {ins.id}: place must be one of {', '.join(PLACES)}")
        if place == "top" and (self.layout != "proof-top" or ins.transparent):
            raise PlanError(f"insert {ins.id}: place 'top' needs layout proof-top and a full-frame insert")
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
        f = self.p.get("face") or [0.5, 0.38]
        return float(f[0]), float(f[1])

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
        return out

    def summary(self) -> dict:
        return {
            "plan": self.path.name, "episode": self.episode, "format": self.format, "fps": self.fps,
            "layout": self.layout,
            "output": str(self.output), "shown": self.shown_path.is_file(), "warnings": self.warnings,
            "inserts": [{"id": x.id, "kind": x.kind, "scene": x.scene or (x.clip.name if x.clip else None),
                         "start": x.start_s, "end": x.end_s, "frames": x.frames, "cues": x.cues,
                         "transparent": x.transparent, "place": x.place, "missing": len(self.missing(x)),
                         "clip": str(x.clip) if x.clip else None} for x in self.inserts],
        }
