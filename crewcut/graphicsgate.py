"""The graphics gate: the style pack's graphic system, checked on the edit plan before the video renders.

The style gate checks a script before it is recorded; this gate checks the graphics of an edit plan
(``episodes/<id>/edit/plan-vNNN.json``) before ``crewcut render all`` or ``crewcut render cut`` builds the video. It
reads only the plan, its words file, the sources of the episode's own pieces and the style pack; it renders nothing
and decodes no media.

What it measures, with the values of ``edit-style.json`` ``graphics`` (rule names as in a pack that numbers its rules
G1 to G12; a pack without a ``graphics`` block has no graphic system and the gate skips):

- types (G1): every insert is one of the pack's graphic types (``graphics.types``: key ``<letter>_<role>``, its
  templates). A library scene takes its type from the template list; a piece made for the video (``source``) or a
  finished graphic shown as a clip (a file under ``render/``) names it in ``graphic.type``. A recording from
  ``broll/`` is proof film. A keyword or card stands beside the speaker; a chapter card or explainer fills the frame.
- colours (G2): every colour of a flat graphic is one of the four palette roles (ink, paper, accent, highlight); the
  highlight only on keyword, number, chapter and card types, never as a ground, never as type on paper. 3D scenes and
  proof film keep their natural colours.
- type (G3): the pack's font family and weights, no italics, no text under ``text.min_px_landscape`` (Short:
  ``min_px_short``).
- shapes (G4): background shapes only on the types or scenes in ``shapes_background.allowed_on`` (``brand.json``
  ``motion_graphics.background.shapes_only_on`` too), at most ``max_shapes``; a logo only where ``logo.allowed_on``
  allows one.
- speaker and full screen (G5): the speaker on screen at least ``speaker_share_min`` of the video; full-screen
  graphics (``full_screen.counts``, and any full-screen graphic without a type) at most ``full_screen.share_max``;
  each full-screen graphic ``full_screen.seconds`` long (``seconds_to_read_max`` with ``graphic.read``); at least
  ``speaker_between_min_s`` of the speaker between two full-screen parts. Proof film on the full frame counts against
  the speaker only.
- density (G6, long videos): the first 60 s up to ``density.first_60s_max`` inserts (a hint), afterwards
  ``density.per_minute_after`` per minute (above the maximum fails, under the minimum is a hint).
- word sync (G7): a graphic is fully there within ``sync.arrive_tolerance_frames`` of its word and stays
  ``sync.hold_after_word_s`` after it. The word is ``graphic.on``, a cue on a word (the template lands on it), or the
  shown text found in the words file.
- elements (G9): at most ``elements_max`` elements in one graphic (one less is a hint), at most
  ``text.keyword_max_words`` words per keyword, no full sentences, never two overlays at the same time.
- sounds (G10): at most ``sound.per_graphic_max`` effect sounds per graphic (a chapter card its pair), a hint when
  every graphic of the opening has one; a Short is dry (``sound.shorts`` "dry ..."): no effect sound at all.
- safe zones (G11): ``graphic.box`` (pixels) and keyword positions inside ``safe_area`` of the format.
- shown words (G12, hint): a keyword or card the speaker never says near its time.

Fails block, hints only inform. ``[graphics_gate]`` in ``config/crewcut.toml``: ``mode`` block (a failing plan does
not render; a card on the edit step names every fix, and its yes sends the list to the Editor), warn (default: the
chat and the render log get the findings, the render goes on) or off.

What the plan cannot say, an insert declares in ``graphic`` (the plan's values win where both exist)::

    "graphic": {"type": "a", "on": "Milliarden", "text": ["2 Mrd.", "Aufrufe"], "colors": ["ink", "highlight"],
                "ground": "video", "font": "Manrope", "weights": [800, 500], "text_px": 64, "elements": 2,
                "shapes": 0, "logo": false, "sounds": ["pop"], "box": [1180, 420, 644, 260], "read": false,
                "arrive": 0.4, "joins_previous": false}

``crewcut graphics-gate <plan>`` prints the verdict (exit 0 pass, 1 fail).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config
from .motion import density

MODES = ("block", "warn", "off")
DEFAULTS = {"mode": "warn"}
ROLES = ("keyword", "card", "chapter", "explainer", "proof", "end")
ROLE_WORDS = {"keyword": "keyword", "keywords": "keyword", "number": "keyword", "word": "keyword",
              "card": "card", "cards": "card", "lower_third": "card", "definition": "card",
              "chapter": "chapter", "part": "chapter",
              "explainer": "explainer", "diagram": "explainer", "stage": "explainer",
              "proof": "proof", "film": "proof", "broll": "proof", "recording": "proof",
              "end": "end", "end_card": "end", "endcard": "end"}
# library scenes and templates by what they are (a pack's own type list wins)
SCENE_ROLE = {
    "keyword": "keyword", "keyword_pop": "keyword", "hf-keyword": "keyword", "word_reel": "keyword",
    "callout": "keyword",
    "lower_third": "card", "hf-card": "card", "quote": "card", "prompt_bar": "card",
    "chapter_card": "chapter", "hf-chapter": "chapter",
    "hf-diagram": "explainer", "counter": "explainer", "bars": "explainer", "grid": "explainer", "wave": "explainer",
    "area": "explainer", "flow": "explainer", "untangle": "explainer", "cards": "explainer", "swap": "explainer",
    "versus": "explainer", "ranking": "explainer", "card_gallery": "explainer",
    "headline": "proof", "post": "proof", "clip-card": "proof", "cursor": "proof", "hf-snippet": "proof",
    "end_lockup": "end",
}
OVERLAY_ROLES = ("keyword", "card")         # beside the speaker
FULL_ROLES = ("chapter", "explainer")       # fill the frame
HIGHLIGHT_ROLES = ("keyword", "chapter", "card")   # where the keyword and the number live
NATURAL_KINDS = ("3d",)                     # material colours are fine
KIND_WORDS = {"2d": "2d", "3d": "3d", "3d-scene": "3d", "clip": "clip", "motion": "motion"}
TEXT_KEYS = ("text", "title", "label", "name", "role", "word", "kicker", "caption", "headline", "subtitle", "sub",
             "line", "line1", "line2", "term", "definition", "source", "key")
LIST_TEXT_KEYS = ("words", "lines", "items", "rows", "points", "steps")
SIZE_KEY = re.compile(r"(?i)^(?:size|font_?size|text_?size|min_?size|font_px|text_px|px)$|[a-z](?:Size|_size|_px)$")
COLOR_KEY = re.compile(r"(?i)colou?r|fill|ground|^bg$|background|stroke|^ink$|^paper$")
HEX = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})(?![0-9A-Fa-f])")
FONT_IN_SOURCE = re.compile(r"\b(?:font|family|fontFamily|fontName|typeface|font-family)[\"']?\s*[:=]\s*"
                            r"([\"'])([^\"'\n]+)\1")
ITALIC_IN_SOURCE = re.compile(r"(?i)font-style\s*:\s*italic|fontStyle\s*[:=]\s*[\"']italic|[\"'][\w ]*\bItalic[\"']")
SENTENCE_END = re.compile(r"[.?!…]['\")\]]*$")
EMPTY = object()


class Blocked(RuntimeError):
    """A failing plan may not render. ``verdict`` is the gate's result, ``card_id`` the card that names the fixes."""

    exit_code = 3

    def __init__(self, message: str, verdict: dict | None = None, card_id: int | None = None):
        super().__init__(message)
        self.verdict = verdict or {}
        self.card_id = card_id


def settings() -> dict:
    raw = config.get("crewcut", "graphics_gate", {}) or {}
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if v is not None})
    mode = str(out.get("mode") or DEFAULTS["mode"]).lower()
    out["mode"] = mode if mode in MODES else "block"      # a typo stays strict
    return out


# ---- the pack's graphic system -------------------------------------------------------------------------------------
def _num(v: Any, default: float | None = None) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _pair(v: Any, default: tuple[float, float]) -> tuple[float, float]:
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(x) is not None for x in v):
        return float(v[0]), float(v[1])
    return default


def _hex(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{3}", s):
        s = "".join(c * 2 for c in s)
    return "#" + s.upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", s) else None


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _near(a: str, b: str, tol: int = 6) -> bool:
    return max(abs(x - y) for x, y in zip(_rgb(a), _rgb(b), strict=True)) <= tol


def _types(block: Any) -> list[dict]:
    """The pack's graphic types: ``{"key", "letter", "role", "what", "templates": [{"name", "transparent"}]}``."""
    out = []
    for key, spec in (block or {}).items() if isinstance(block, dict) else []:
        spec = spec if isinstance(spec, dict) else {}
        head, _, rest = str(key).partition("_")
        letter = head.lower() if len(head) == 1 else None
        role = spec.get("role") or ROLE_WORDS.get((rest or head).lower())
        tmpl = []
        for t in spec.get("templates") or []:
            m = re.match(r"\s*([A-Za-z0-9_-]+)", str(t))
            if m:
                tmpl.append({"name": m.group(1).lower() if m.group(1).lower() in KIND_WORDS else m.group(1),
                             "transparent": True if "(transparent)" in str(t) else None})
        out.append({"key": str(key), "letter": letter, "role": role if role in ROLES else None,
                    "what": spec.get("what"), "templates": tmpl})
    return out


def limits(pack: Any) -> dict | None:
    """Every value the gate measures against, from the style pack. None when the pack has no ``graphics`` block."""
    g = pack.value("edit_style.graphics")
    if not isinstance(g, dict) or not g:
        return None
    from .motion import studio_style
    es = pack.edit_style or {}
    text = g.get("text") if isinstance(g.get("text"), dict) else {}
    full = g.get("full_screen") if isinstance(g.get("full_screen"), dict) else {}
    dens = g.get("density") if isinstance(g.get("density"), dict) else {}
    sync = g.get("sync") if isinstance(g.get("sync"), dict) else {}
    sound = g.get("sound") if isinstance(g.get("sound"), dict) else {}
    shapes = g.get("shapes_background") if isinstance(g.get("shapes_background"), dict) else {}
    logo = g.get("logo") if isinstance(g.get("logo"), dict) else {}
    pal = g.get("palette") if isinstance(g.get("palette"), dict) else {}
    bg = (pack.value("brand.motion_graphics.background") or {})
    fonts = studio_style.fonts(pack)
    weights = text.get("weights")
    weights = sorted({int(v) for v in (weights.values() if isinstance(weights, dict) else weights or [])
                      if _num(v) is not None}) or sorted({fonts["display"]["weight"], fonts["body"]["weight"]})
    allowed_on = [str(x) for x in (shapes.get("allowed_on") or [])] + [str(x) for x in (bg.get("shapes_only_on") or [])]
    palette = studio_style.palette(pack)
    extra = [h for h in (_hex(x) for x in (pal.get("extra") or [])) if h]
    return {
        "types": _types(g.get("types")),
        "palette": palette,
        "palette_extra": extra,
        "check_palette": bool(pal) or bool(pack.value("channel.graphics.palette")),
        "font": str(text.get("font") or fonts["display"]["family"]),
        "fonts": sorted({str(text.get("font") or fonts["display"]["family"]), fonts["display"]["family"],
                         fonts["body"]["family"]}),
        "weights": weights,
        "italics": bool(text.get("italics", es.get("italics", False))),
        "min_px": {"landscape": _num(text.get("min_px_landscape"), _num(es.get("min_text_px"), 40.0)),
                   "portrait": _num(text.get("min_px_short"), _num(es.get("min_text_px"), 40.0))},
        "keyword_max_words": int(_num(text.get("keyword_max_words"), _num(es.get("keyword_max_words"), 4)) or 4),
        "full_sentences": bool(text.get("full_sentences", False)),
        "share_max": _num(full.get("share_max")),
        "full_s": _pair(full.get("seconds"), _pair((es.get("motion") or {}).get("insert_s"), (3.0, 6.0))),
        "read_s": _num(full.get("seconds_to_read_max"), _num((es.get("motion") or {}).get("insert_long_s"), 8.0)),
        "between_s": _num(full.get("speaker_between_min_s"), _num(es.get("speaker_min_seconds"), 2.5)),
        "counts": [str(x) for x in (full.get("counts") or [])],
        "speaker_share_min": _num(g.get("speaker_share_min"), _num(es.get("speaker_share_min"))),
        "first_60s_max": _num(dens.get("first_60s_max")),
        "per_minute_after": _pair(dens.get("per_minute_after"), (0.0, 0.0)) if dens.get("per_minute_after") else None,
        "elements_max": int(_num(g.get("elements_max"), 0) or 0) or None,
        "tolerance_frames": _num(sync.get("arrive_tolerance_frames")),
        "hold_after_s": _num(sync.get("hold_after_word_s"), 0.0),
        "sounds_max": int(_num(sound.get("per_graphic_max"), _num((es.get("motion") or {}).get("sounds_per_motion_max"),
                                                                 1)) or 0),
        "chapter_pair": [str(x) for x in (sound.get("chapter_change_pair") or [])],
        "sounds_per_minute": _pair(sound.get("per_minute"), (0.0, 0.0)) if sound.get("per_minute") else None,
        "shorts_dry": str(sound.get("shorts") or "").lower().startswith("dry"),
        "shapes_on": sorted(set(allowed_on)),
        "max_shapes": int(_num(bg.get("max_shapes"), _num(shapes.get("max"), 0)) or 0) or None,
        "logo_on": [str(x) for x in logo.get("allowed_on") or []] if "allowed_on" in logo else None,
        "safe": g.get("safe_area") if isinstance(g.get("safe_area"), dict) else None,
        "enter_s": float(studio_style.motion(pack)["enter_s"]),
        "entrance_frames": int(_num(pack.value("brand.motion.entrance_frames"), 10) or 10),
        "fps": int(_num(es.get("fps"), 25) or 25),
        "pack_logo": (pack.value("brand.logo") or {}),
        "decor": pack.value("brand.motion.decor"),
    }


# ---- what the plan holds -------------------------------------------------------------------------------------------
def _role_of_type(L: dict, key: str | None) -> str | None:
    return next((t["role"] for t in L["types"] if t["key"] == key), None)


def _find_type(L: dict, want: Any) -> dict | None:
    w = str(want or "").strip()
    if not w:
        return None
    lw = w.lower()
    for t in L["types"]:
        if lw in (t["key"].lower(), t["letter"] or "\0", (t["role"] or "\0")) or t["key"].lower().endswith("_" + lw):
            return t
    role = ROLE_WORDS.get(lw)
    return next((t for t in L["types"] if role and t["role"] == role), None)


def _rendered_clip(e: dict) -> bool:
    """A clip whose file is a finished graphic of this episode (render/...), not a recording."""
    f = str(e.get("file") or "").replace("\\", "/")
    return e.get("kind") == "clip" and (f.startswith("render/") or "/render/inserts/" in f)


def _scene_role(e: dict) -> str | None:
    kind, scene = e.get("kind"), str(e.get("scene") or "")
    if kind == "clip":
        return None if _rendered_clip(e) else "proof"
    if kind == "motion" and e.get("source"):
        return None
    if kind == "motion" and scene == "number_roll":
        return "keyword" if e.get("transparent") else "explainer"
    if kind == "motion" and scene == "lottie_clip":
        return None
    base = scene.split("@", 1)[0]
    if base in SCENE_ROLE:
        return SCENE_ROLE[base]
    if kind == "3d":
        return "explainer"
    if kind == "2d":
        return "keyword" if e.get("transparent") else "explainer"
    return None


def _template_match(t: dict, e: dict) -> bool:
    kind, scene = e.get("kind"), str(e.get("scene") or "").split("@", 1)[0]
    for m in t["templates"]:
        if m["transparent"] is not None and bool(e.get("transparent")) != m["transparent"]:
            continue
        name = m["name"]
        if name in KIND_WORDS:          # a whole kind ("clip", "3d-scene", "2D diagram"): any scene of it in this role
            if KIND_WORDS[name] != kind or (kind == "clip" and _rendered_clip(e)):
                continue
            if kind == "2d" and SCENE_ROLE.get(scene, t["role"]) != t["role"]:
                continue
            return True
        if name == scene and not e.get("source"):
            return True
    # the HyperFrames blocks are built from the pack's graphic system, one per type (docs/motion-libraries.md)
    return scene.startswith("hf-") and SCENE_ROLE.get(scene) == t["role"] and t["role"] is not None


def resolve_type(L: dict, e: dict, decl: dict) -> dict:
    """The insert's type: ``{"key", "role", "how", "problem"}``. ``problem`` says why it is not a type of the pack."""
    role_hint = _scene_role(e)
    if decl.get("type") is not None:
        t = _find_type(L, decl["type"])
        if t is None:
            return {"key": None, "role": ROLE_WORDS.get(str(decl["type"]).lower()), "how": "declared",
                    "problem": f"graphic.type {decl['type']!r} is not a type of the pack"}
        if role_hint and t["role"] and role_hint != t["role"] and not e.get("source") and not _rendered_clip(e):
            return {"key": t["key"], "role": t["role"], "how": "declared",
                    "problem": f"declared {t['key']}, but scene {e.get('scene') or e.get('kind')} is a {role_hint}"}
        return {"key": t["key"], "role": t["role"], "how": "declared", "problem": None}
    for t in L["types"]:
        if _template_match(t, e):
            return {"key": t["key"], "role": t["role"], "how": "template", "problem": None}
    if role_hint == "end":
        return {"key": None, "role": "end", "how": "scene", "problem": None}
    t = next((x for x in L["types"] if role_hint and x["role"] == role_hint), None)
    if t is not None:
        listed = [m["name"] for m in t["templates"]]
        if listed and e.get("kind") != "clip":
            return {"key": t["key"], "role": t["role"], "how": "scene",
                    "problem": f"{e.get('kind')} scene {e.get('scene')!r} is not a template of {t['key']} "
                               f"({', '.join(listed)})"}
        return {"key": t["key"], "role": t["role"], "how": "scene", "problem": None}
    if _rendered_clip(e):
        why = "a finished graphic shown as a clip"
    elif e.get("source"):
        why = "a piece made for this video"
    else:
        why = f"{e.get('kind')} {e.get('scene') or ''}".strip()
    return {"key": None, "role": None, "how": None, "problem": f"no type ({why})"}


def _texts(e: dict, decl: dict) -> list[str]:
    if decl.get("text") is not None:
        t = decl["text"]
        return [str(x) for x in (t if isinstance(t, list) else [t]) if str(x).strip()]
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    out: list[str] = []
    for k in ("value", "number"):
        v = d.get(k)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip():
            out.append(" ".join(str(x) for x in (d.get("prefix") or "", v, d.get("unit") or "") if str(x)).strip())
    for k in TEXT_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    for k in LIST_TEXT_KEYS:
        v = d.get(k)
        if not isinstance(v, list):
            continue
        if v and all(isinstance(x, str) for x in v):
            out.append(" ".join(x for x in v if x.strip()))
            continue
        for x in v:
            if isinstance(x, dict):
                s = x.get("text") or x.get("label") or x.get("title")
                if isinstance(s, str) and s.strip():
                    out.append(s.strip())
            elif isinstance(x, (str, int, float)) and not isinstance(x, bool) and str(x).strip():
                out.append(str(x))
    return out


def _elements(e: dict, decl: dict, texts: list[str]) -> int | None:
    if _num(decl.get("elements")) is not None:
        return int(decl["elements"])
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    n = len(texts)
    for k in ("cards", "images", "icons", "tiles", "kacheln"):
        if isinstance(d.get(k), list):
            n += len(d[k])
    if isinstance(d.get("image"), str):
        n += 1
    return n or None


def _sizes(e: dict, decl: dict) -> list[float]:
    out = []
    v = decl.get("text_px")
    for x in v if isinstance(v, list) else [v]:
        if _num(x) is not None:
            out.append(float(x))

    def walk(d: Any) -> None:
        if isinstance(d, dict):
            for k, x in d.items():
                if SIZE_KEY.search(str(k)) and _num(x) is not None and float(x) > 1.5:
                    out.append(float(x))
                elif isinstance(x, (dict, list)):
                    walk(x)
        elif isinstance(d, list):
            for x in d:
                walk(x)
    walk(e.get("data") or {})
    return out


def _colors(e: dict, decl: dict, L: dict, pack: Any) -> list[str]:
    """Every colour the plan or the declaration names for this insert, as #RRGGBB (role names resolved)."""
    names = dict(L["palette"])
    for k, v in (pack.value("brand.colors") or {}).items():
        h = _hex(v)
        if h and k not in names:
            names[k] = h
    names.update({"cream": L["palette"]["paper"], "creme": L["palette"]["paper"]})
    out: list[str] = []

    def one(v: Any) -> None:
        if isinstance(v, str):
            h = _hex(v) or names.get(v.strip().lower())
            if h:
                out.append(h)

    for v in decl.get("colors") or []:
        one(v)
    if decl.get("ground"):
        one(decl["ground"])

    def walk(d: Any, key: str = "") -> None:
        if isinstance(d, dict):
            for k, x in d.items():
                if isinstance(x, (dict, list)):
                    walk(x, str(k))
                elif isinstance(x, str) and (COLOR_KEY.search(str(k)) or (str(k) == "style" and x in names)):
                    one(x)
        elif isinstance(d, list):
            for x in d:
                walk(x, key)
    walk(e.get("data") or {})
    return list(dict.fromkeys(out))


def _ground(e: dict, decl: dict, role: str | None, L: dict) -> str | None:
    g = decl.get("ground")
    if isinstance(g, str):
        h = _hex(g)
        if h:
            for name, v in L["palette"].items():
                if _near(h, v):
                    return name
            return h
        g = g.strip().lower()
        return {"cream": "paper", "creme": "paper"}.get(g, g)
    if e.get("transparent"):
        return "video"
    if role == "chapter":
        return "ink"
    return None


def _shapes(e: dict, decl: dict, L: dict) -> int | None:
    v = decl.get("shapes", EMPTY)
    if v is not EMPTY and v is not None:
        return int(v) if _num(v) is not None else (1 if v else 0)
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    if d.get("decor") == "shapes" or (e.get("kind") == "2d" and not e.get("transparent") and "decor" not in d
                                      and L.get("decor") == "shapes"):
        return 1
    for k in ("shapes", "rings", "forms", "formen"):
        x = d.get(k)
        if isinstance(x, list) and x:
            return len(x)
        if x not in (None, False, 0, "", [], {}):
            return 1
    if d.get("background") in ("shapes", "forms"):
        return 1
    return None


def _logo(e: dict, decl: dict, L: dict) -> bool | None:
    if "logo" in decl:
        return bool(decl["logo"])
    d = e.get("data") if isinstance(e.get("data"), dict) else {}
    if isinstance(d.get("logo"), str):
        return bool(d["logo"].strip())
    if d.get("logo") is False:
        return False
    lg = L.get("pack_logo") or {}
    if e.get("kind") == "2d" and not e.get("transparent") and lg.get("file") and str(lg.get("placement") or "none") \
            not in ("none", "off", "false"):
        return True
    return None


def _source(e: dict, ep_dir: Path | None) -> Path | None:
    """The source of a piece made for this video: ``source``, or for a finished graphic shown as a clip the comp of
    the same name in ``motion/<name>/`` (``render/inserts/<name>-<hash>.mov``)."""
    if ep_dir is None:
        return None
    cands = []
    if e.get("source"):
        cands.append(ep_dir / str(e["source"]))
    if _rendered_clip(e):
        stem = Path(str(e["file"])).stem
        name = re.sub(r"-[0-9a-f]{10}$", "", stem)
        for n in dict.fromkeys((name, str(e.get("id") or ""))):
            if n:
                cands += [ep_dir / "motion" / n / "comp.jsx", ep_dir / "motion" / n / "index.html"]
    for p in cands:
        try:
            if p.is_file() and p.resolve().is_relative_to(ep_dir.resolve()):
                return p
        except OSError:
            continue
    return None


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    src = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"(?m)(^|[^:\"'\\])//.*$", r"\1", src)


def scan_source(p: Path, min_px: float) -> dict:
    """What a piece's own source writes itself: hex colours, font names, italics and text sizes under ``min_px``
    (with their lines). Templates take these from the pack; a value written in the source is the piece's own."""
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    code = _strip_comments(raw)
    colors: dict[str, list[int]] = {}
    fonts: dict[str, list[int]] = {}
    italic: list[int] = []
    small: list[dict] = []
    for n, ln in enumerate(code.splitlines(), 1):
        for m in HEX.finditer(ln):
            h = _hex(m.group(0))
            if h:
                colors.setdefault(h, []).append(n)
        for m in FONT_IN_SOURCE.finditer(ln):
            fonts.setdefault(m.group(2).split(",")[0].strip().strip("\"'"), []).append(n)
        if ITALIC_IN_SOURCE.search(ln):
            italic.append(n)
        for m in re.finditer(r"[\"']?\b(?:size|fontSize|textSize|font-size)[\"']?\s*:\s*(?:CC\.px\(\s*)?(\d+(?:\.\d+)?)"
                             r"(?:px)?", ln):
            v = float(m.group(1))
            if 1.5 < v < min_px:
                small.append({"line": n, "px": v})
    return {"file": str(p), "colors": colors, "fonts": fonts, "italic": italic, "small": small}


# ---- times ----------------------------------------------------------------------------------------------------------
def _words(plan: dict, ep_dir: Path | None) -> list[dict]:
    w = plan.get("words")
    if not w or ep_dir is None:
        return []
    try:
        return density.norm_words(json.loads((ep_dir / str(w)).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def duration(plan: dict, words: list[dict], spans: list[tuple[float, float]]) -> float:
    b = plan.get("base")
    if _num(plan.get("duration_s")):
        return float(plan["duration_s"])
    if isinstance(b, dict) and _num(b.get("seconds")):
        return float(b["seconds"]) + float(plan.get("tail") or 0)
    last = max((w["e"] for w in words), default=0.0)
    return max(last + float(plan.get("tail") or 0), max((t for _, t in spans), default=0.0))


def _union(spans: list[tuple[float, float]]) -> float:
    tot, cur = 0.0, None
    for a, b in sorted(spans):
        if cur is None or a > cur[1]:
            if cur:
                tot += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        tot += cur[1] - cur[0]
    return tot


def _tok(s: str) -> str:
    return density.normalize(s)


def _spoken(words: list[dict], text: str, lo: float, hi: float, near: float) -> dict | None:
    """The spoken word in [lo, hi] closest to ``near`` that matches a word of the shown text (endings allowed; short
    words only when the text has no longer one)."""
    want = [t for t in (_tok(x) for x in str(text).split()) if t and not t.isdigit() and len(t) > 1]
    if any(len(t) >= 4 for t in want):
        want = [t for t in want if len(t) >= 4]
    if not want:
        return None
    hits = []
    for w in words:
        if w["s"] < lo or w["s"] > hi:
            continue
        s = _tok(w["w"])
        if any(s == t or (min(len(s), len(t)) >= 4 and (s.startswith(t) or t.startswith(s))) for t in want):
            hits.append(w)
    return min(hits, key=lambda w: abs(w["s"] - near)) if hits else None


def _cue_word(e: dict, words: list[dict], start: float) -> tuple[str, dict, int] | None:
    """The first cue on a word: its name, the spoken word and the cue's offset in frames."""
    for name, c in (e.get("cues") or {}).items():
        if isinstance(c, dict) and "word" in c:
            after = float(c["after"]) if _num(c.get("after")) is not None else start
            t = density.word_time(words, str(c["word"]), after)
            if t is not None:
                w = next((x for x in words if abs(x["s"] - t) < 1e-6), {"w": c["word"], "s": t, "e": t})
                return str(name), w, int(_num(c.get("offset"), 0) or 0)
    return None


# ---- the check -----------------------------------------------------------------------------------------------------
def _add(out: list, level: str, rule: str, cid: str, text: str, insert: str | None = None, t: float | None = None,
         fix: str | None = None, measured: Any = None, target: Any = None) -> None:
    out.append({"level": level, "rule": rule, "id": cid, "insert": insert, "time": None if t is None else round(t, 2),
                "text": text, "fix": fix, "measured": measured, "target": target})


class _Check:
    """One run of the gate over one plan: the rows (what each insert is and shows), then one method per rule. Every
    method adds findings to F; the verdict is built from them."""

    def __init__(self, plan: dict, pack: Any, L: dict, ep_dir: Path | None):
        self.plan, self.pack, self.L = plan, pack, L
        self.fmt = plan.get("format") or "landscape"
        self.short = self.fmt == "portrait"
        self.fps = float(plan.get("fps") or L["fps"])
        self.W, self.H = (1080, 1920) if self.short else (1920, 1080)
        self.words = _words(plan, ep_dir)
        self.F: list[dict] = []
        self.unknown: dict[str, list[str]] = {}
        self.metrics: dict = {}
        self.counts: dict[str, int] = {}
        self.rows = self._rows(ep_dir)
        self.total = duration(plan, self.words, [(r["start"], r["end"]) for r in self.rows])
        self.minutes = self.total / 60 if self.total else 0.0

    def _rows(self, ep_dir: Path | None) -> list[dict]:
        plan, pack, L, F, fmt = self.plan, self.pack, self.L, self.F, self.fmt
        proof_top = self.short and (plan.get("layout") or pack.value("edit_style.shorts.layout")) == "proof-top"
        rows: list[dict] = []
        for e in plan.get("inserts") or []:
            if not isinstance(e, dict):
                continue
            s, t = density.span(e, self.words)
            iid = str(e.get("id"))
            if s is None or t is None:
                _add(F, "hint", "G5", f"time:{iid}", f"{iid}: start or end is a word that is not in the words file; "
                     "left out of the graphics check", iid, fix="Give seconds or fix the word anchor")
                continue
            decl = e.get("graphic") if isinstance(e.get("graphic"), dict) else (
                {"type": e["graphic"]} if isinstance(e.get("graphic"), str) else {})
            ty = resolve_type(L, e, decl)
            stage = proof_top and not e.get("transparent") and e.get("place") != "full"
            texts = _texts(e, decl)
            src = _source(e, ep_dir)
            rows.append({"id": iid, "e": e, "decl": decl, "start": s, "end": t, "type": ty["key"],
                         "role": ty["role"], "how": ty["how"], "type_problem": ty["problem"],
                         "full": not e.get("transparent") and not stage, "stage": stage, "texts": texts,
                         "elements": _elements(e, decl, texts), "sizes": _sizes(e, decl),
                         "colors": _colors(e, decl, L, pack), "ground": _ground(e, decl, ty["role"], L),
                         "shapes": _shapes(e, decl, L), "logo": _logo(e, decl, L), "source": src,
                         "scan": scan_source(src, L["min_px"][fmt]) if src is not None else {}})
        rows.sort(key=lambda r: r["start"])
        return rows

    def find(self, level: str, cid: str, text: str, r: dict | None = None, fix: str | None = None,
             measured: Any = None, target: Any = None) -> None:
        """One finding. ``cid`` starts with its rule (``G5-length``); for an insert ``r`` the id gets ``:<insert>``
        (unless it names its own) and the text starts with the insert's id."""
        rule = cid.split("-", 1)[0]
        if r is None:
            _add(self.F, level, rule, cid, text, fix=fix, measured=measured, target=target)
        else:
            _add(self.F, level, rule, cid if ":" in cid else f"{cid}:{r['id']}", f"{r['id']}: {text}", r["id"],
                 r["start"], fix, measured, target)

    RULES = ("g1_types", "g2_colours", "g3_type", "g4_shapes", "g5_full_screen", "g6_density", "g7_sync",
             "g9_elements", "g10_sounds", "g11_safe")

    def run(self) -> None:
        for name in self.RULES:
            getattr(self, name)()

    def g1_types(self) -> None:
        """G1: every insert is one of the pack's types, with its template; keywords and cards beside the speaker."""
        L, rows, unknown = self.L, self.rows, self.unknown
        if L["types"]:
            for r in rows:
                if r["type_problem"]:
                    self.find("fail", "G1-type", f"{r['type_problem']}", r,
                              fix="Use the template of one of the pack's types (" + ", ".join(
                              f"{t['key']}: {'/'.join(m['name'] for m in t['templates']) or 'any'}" for t in L["types"])
                              + "); a piece made for the video names its type in graphic.type")
                role = r["role"]
                if role in OVERLAY_ROLES and r["full"]:
                    self.find("fail", "G1-place", f"a {role} ({r['type']}) stands beside the speaker, but this one "
                              "covers the whole frame", r, fix="Make it an overlay (transparent) beside the speaker, "
                              "or use the chapter card or an explainer")
                if role in FULL_ROLES and not r["full"] and not r["stage"]:
                    self.find("hint", "G1-place", f"a {role} ({r['type']}) normally fills the "
                              "frame; this one is an overlay", r)
        else:
            unknown.setdefault("G1", []).append("the pack lists no graphics.types")

    def g2_colours(self) -> None:
        """G2: the four palette roles only; the highlight only for keyword and number, never on paper or as a ground."""
        L, rows = self.L, self.rows
        pal = L["palette"]
        allowed = list(pal.values()) + L["palette_extra"]
        for r in rows:
            natural = r["e"].get("kind") in NATURAL_KINDS or r["role"] == "proof" or bool(r["decl"].get("natural"))
            cols = list(r["colors"])
            own = (r["scan"] or {}).get("colors") or {}
            if L["check_palette"] and not natural:
                bad = [c for c in cols if not any(_near(c, a) for a in allowed)]
                if bad:
                    roles = ", ".join(f"{k} {v}" for k, v in pal.items())
                    self.find("fail", "G2-colour", f"colours outside the palette: {', '.join(bad)}", r,
                              measured=bad, target=allowed, fix=f"Only ink, paper, accent and the highlight ({roles})")
                src_bad = {c: ln for c, ln in own.items() if not any(_near(c, a) for a in allowed)}
                if src_bad and r["e"].get("kind") != "3d":
                    where = ", ".join(f"{c} (line {', '.join(str(x) for x in ln[:3])})"
                                      for c, ln in list(src_bad.items())[:6])
                    self.find("fail", "G2-source", f"its source writes colours outside the palette: {where}", r,
                              measured=sorted(src_bad), target=allowed,
                              fix=f"Take every colour from the pack in {Path(r['scan']['file']).name} (ink, paper, "
                                  "accent, highlight)")
            hi = pal["highlight"]
            if hi != pal["accent"]:
                uses_hi = any(_near(c, hi) for c in cols + list(own))
                if uses_hi and r["role"] and r["role"] not in HIGHLIGHT_ROLES and not natural:
                    self.find("fail", "G2-highlight", f"the highlight {hi} on a {r['role']}; it "
                              "is only for the keyword and the number", r,
                              fix="Use the accent or ink here; keep the highlight for the keyword and the number")
                if uses_hi and r["ground"] in ("paper",):
                    self.find("fail", "G2-highlight-paper", f"the highlight {hi} as type on paper "
                              "(unreadable); on paper the accent takes its role", r,
                              fix=f"Use the accent {pal['accent']} for the keyword or number on paper")
                if r["ground"] and (r["ground"] == "highlight" or (_hex(r["ground"]) and _near(_hex(r["ground"]), hi))):
                    self.find("fail", "G2-highlight-ground", "the highlight as a ground; it is "
                              "never a surface", r, fix="Ground on ink, paper or the video")

    def g3_type(self) -> None:
        """G3: the pack's font family and weights, no italics, no text under the smallest size."""
        L, rows, unknown, fmt, short = self.L, self.rows, self.unknown, self.fmt, self.short
        for r in rows:
            decl = r["decl"]
            fams = [str(decl["font"])] if decl.get("font") else []
            fams += [f for f in ((r["scan"] or {}).get("fonts") or {})]
            ours = [x.lower() for x in L["fonts"]]
            bad = [f for f in fams if f.split(",")[0].strip().strip("\"'").lower() not in ours]
            if bad:
                self.find("fail", "G3-font", f"font {', '.join(dict.fromkeys(bad))}; the pack's "
                          f"type is {L['font']}", r, fix=f"Set every line in {L['font']}")
            ws = [int(x) for x in (decl.get("weights") or ([decl["weight"]] if decl.get("weight") else []))
                  if _num(x) is not None]
            badw = [w for w in ws if w not in L["weights"]]
            if badw:
                self.find("fail", "G3-weight", f"weight {', '.join(map(str, badw))}; the pack "
                          f"uses {' and '.join(map(str, L['weights']))}", r,
                          fix=f"Only {' and '.join(map(str, L['weights']))}")
            data = r["e"].get("data") if isinstance(r["e"].get("data"), dict) else {}
            italic = bool(decl.get("italic")) or bool(data.get("italic")) or bool((r["scan"] or {}).get("italic"))
            if italic and not L["italics"]:
                self.find("fail", "G3-italic", "italic type; the pack has none", r, fix="Upright type only")
            mn = L["min_px"][fmt]
            small = [x for x in r["sizes"] if x < mn - 1e-6]
            if small and r["role"] != "proof":
                self.find("fail", "G3-size", f"text at {min(small):g} px; at least {mn:g} px "
                          f"in {'a Short' if short else 'the 16:9 frame'}", r, measured=min(small), target=mn,
                          fix=f"At least {mn:g} px for every line; shorten the text instead of shrinking it")
            src_small = (r["scan"] or {}).get("small") or []
            if src_small:
                sizes = ", ".join(sorted({f"{x['px']:g} px" for x in src_small}))
                lines = ", ".join(str(x["line"]) for x in src_small[:4])
                self.find("hint", "G3-source-size", f"its source sets text at {sizes} (line "
                          f"{lines}); the motion review measures the real size", r)
            if not r["sizes"] and not src_small and r["role"] not in ("proof", None) and r["how"] == "declared" \
                    and (r["source"] is not None or _rendered_clip(r["e"])):
                unknown.setdefault("G3", []).append(r["id"])

    def g4_shapes(self) -> None:
        """G4: background shapes and a logo only where the pack allows them."""
        L, rows = self.L, self.rows
        for r in rows:
            n = r["shapes"]
            names = {r["type"] or "", str(r["e"].get("scene") or "").split("@")[0], r["role"] or ""}
            if n:
                if L["shapes_on"] and not names & set(L["shapes_on"]) and not (r["role"] == "chapter" and any(
                        _role_of_type(L, x) == "chapter" for x in L["shapes_on"])):
                    self.find("fail", "G4-shapes", f"background shapes on a {r['role'] or 'graphic'};"
                              f" they belong only on {', '.join(L['shapes_on'])}", r,
                              fix="A calm ink or paper ground, the speaker or the proof itself; no shapes")
                if L["max_shapes"] and n > L["max_shapes"]:
                    self.find("fail", "G4-count", f"{n} shapes; at most {L['max_shapes']}",
                              r, measured=n, target=L["max_shapes"], fix=f"At most {L['max_shapes']} shapes")
            if r["logo"] and L["logo_on"] is not None and not names & set(L["logo_on"]):
                self.find("fail", "G4-logo", f"a logo in the graphic; the pack allows one only "
                          f"on {', '.join(L['logo_on']) or 'no graphic'}", r,
                          fix="No logo in graphics (data logo false, or brand.json logo.placement none)")

    def g5_full_screen(self) -> None:
        """G5: the speaker's share, the full-screen share, each full screen's length, the speaker between two."""
        L, rows, total, fps = self.L, self.rows, self.total, self.fps
        full = [r for r in rows if r["full"]]
        full_t = _union([(r["start"], r["end"]) for r in full])
        speaker_share = 1 - full_t / total if total else 1.0
        counted = [r for r in full if r["role"] not in ("proof", "end") and (
            not L["counts"] or r["type"] in L["counts"] or r["type"] is None or r["role"] in OVERLAY_ROLES)]
        graphics_t = _union([(r["start"], r["end"]) for r in counted])
        share = graphics_t / total if total else 0.0
        self.metrics.update(full_screen_parts=len(full), full_screen_s=round(full_t, 2),
                            speaker_share=round(speaker_share, 4), graphics_share=round(share, 4))
        if L["speaker_share_min"] is not None and total:
            ok = speaker_share >= L["speaker_share_min"] - 1e-9
            gap_s = max(0.0, (L["speaker_share_min"] - speaker_share) * total)
            self.find("pass" if ok else "fail", "G5-speaker", f"The speaker is on screen {speaker_share:.1%} of "
                      f"{total:.1f} s (at least {L['speaker_share_min']:.0%}); {len(full)} full-screen parts cover "
                      f"{full_t:.1f} s", measured=round(speaker_share, 4), target=L["speaker_share_min"],
                      fix=None if ok else f"Turn about {gap_s:.0f} s of full-screen parts into overlays or a second "
                                          "surface beside the speaker")
        if L["share_max"] is not None and total:
            ok = share <= L["share_max"] + 1e-9
            self.find("pass" if ok else "fail", "G5-full-share", f"Full-screen graphics cover {share:.1%} of the video "
                      f"({graphics_t:.1f} s in {len(counted)} parts; at most {L['share_max']:.0%} = "
                      f"{L['share_max'] * total:.0f} s)", measured=round(share, 4), target=L["share_max"],
                      fix=None if ok else f"Cut about {graphics_t - L['share_max'] * total:.0f} s of full-screen "
                                          "graphics: make the weakest ones overlays beside the speaker or drop them")
        lo, hi = L["full_s"]
        joined: list[list[dict]] = []
        for r in full:
            if joined and r["decl"].get("joins_previous") and r["start"] - joined[-1][-1]["end"] < 1 / fps + 1e-6:
                joined[-1].append(r)
            else:
                joined.append([r])
        for grp in joined:
            r = grp[0]
            if r["role"] in ("proof", "end"):
                continue
            n = grp[-1]["end"] - r["start"]
            top = L["read_s"] if any(x["decl"].get("read") or ((x["e"].get("data") or {}) if isinstance(
                x["e"].get("data"), dict) else {}).get("explainer") for x in grp) else hi
            if n < lo - 1e-6 or n > top + 1e-6:
                ids = "+".join(x["id"] for x in grp)
                self.find("fail", f"G5-length:{ids}", f"full screen for {n:.2f} s; each full-screen graphic runs "
                          f"{lo:g} to {hi:g} s" + (f" ({top:g} s to read)" if top != hi else ""), r,
                          measured=round(n, 2), target=[lo, top],
                          fix="Lengthen it to the whole thought" if n < lo else
                          "Shorten it or let the speaker carry the rest")
        for a, b in zip(joined, joined[1:], strict=False):
            gap = b[0]["start"] - a[-1]["end"]
            if gap < L["between_s"] - 1e-6 and b[0]["role"] != "end":
                self.find("fail", f"G5-between:{a[-1]['id']}-{b[0]['id']}", f"the speaker only {max(0.0, gap):.1f} "
                          f"s after {a[-1]['id']} (at least {L['between_s']:g} s between two full screens)", b[0],
                          measured=round(gap, 2), target=L["between_s"],
                          fix="Put the speaker between them, or make them one piece (graphic.joins_previous) of "
                              "the allowed length")
        for r in rows:
            if not r["full"] and r["role"] in OVERLAY_ROLES and r["end"] - r["start"] > hi + 1e-6:
                self.find("hint", "G5-overlay-length", f"an overlay stands "
                          f"{r['end'] - r['start']:.1f} s (a card {lo:g} to {hi:g} s; nothing stands long unchanged)",
                          r)

    def g6_density(self) -> None:
        """G6 (long videos): the first minute up to about N inserts, afterwards a band per minute."""
        L, rows, total, short = self.L, self.rows, self.total, self.short
        counted6 = [r for r in rows if r["role"] != "end"]
        first = [r for r in counted6 if r["start"] < 60.0]
        after = [r for r in counted6 if r["start"] >= 60.0]
        rate = len(after) / ((total - 60.0) / 60.0) if total > 90 else None
        self.metrics.update(first_60s=len(first), per_minute_after=round(rate, 2) if rate is not None else None)
        if not short:
            if L["first_60s_max"] is not None and total:
                ok = len(first) <= L["first_60s_max"]
                self.find("pass" if ok else "hint", "G6-first-60s", f"{len(first)} inserts in the first 60 s (up to "
                          f"about {L['first_60s_max']:g})", measured=len(first), target=L["first_60s_max"])
                full_first = [r for r in first if r["full"]]
                if first and len(full_first) * 2 > len(first):
                    self.find("hint", "G6-first-60s-beside", f"{len(full_first)} of {len(first)} inserts in the first "
                              "60 s cover the speaker; almost all stand beside him", measured=len(full_first))
            if L["per_minute_after"] and rate is not None:
                mn6, mx6 = L["per_minute_after"]
                lvl = "fail" if rate > mx6 + 1e-9 else ("hint" if rate < mn6 - 1e-9 else "pass")
                self.find(lvl, "G6-per-minute", f"{len(after)} inserts after the first minute = {rate:.1f} per minute "
                          f"({mn6:g} to {mx6:g})", measured=round(rate, 2), target=[mn6, mx6],
                          fix=None if lvl != "fail" else f"Drop about {len(after) - int(mx6 * (total - 60) / 60)} "
                                                         "inserts after the first minute where the speaker already "
                                                         "carries the sentence")

    def g7_sync(self) -> None:
        """G7: fully there on its word (within the tolerance) and standing after it. G12: shown words not said."""
        L, rows, unknown, words, fps = self.L, self.rows, self.unknown, self.words, self.fps
        tol = (L["tolerance_frames"] or 0) / fps + 1e-6 if L["tolerance_frames"] is not None else None
        unmeasured7 = []
        for r in rows:
            e, decl = r["e"], r["decl"]
            word = None
            how = None
            arrive = None
            on = decl.get("on")
            if on:
                ww = on.get("word") if isinstance(on, dict) else on
                given = on.get("after") if isinstance(on, dict) else None
                after = float(given) if _num(given) is not None else r["start"] - 3
                t0 = density.word_time(words, str(ww), max(0.0, after)) if words else None
                if t0 is None:
                    self.find("fail", "G7-word", f"its word {ww!r} is not spoken near "
                              f"{density.tc(r['start'])}", r, fix="Fix graphic.on or the insert's time")
                    continue
                word = next(x for x in words if abs(x["s"] - t0) < 1e-6)
                how = "graphic.on"
            cue = _cue_word(e, words, r["start"]) if word is None else None
            if cue:
                how, word = f"cue {cue[0]}", cue[1]
                arrive = word["s"] + (cue[2] - 1.5) / fps     # the template lands on its cue
            if word is None and r["role"] in ("keyword", "card", "chapter") and r["texts"] and words:
                d = e.get("data") if isinstance(e.get("data"), dict) else {}
                lw = d.get("words") if isinstance(d.get("words"), list) else []
                first_w = next((x for x in lw if isinstance(x, dict) and x.get("text")), None)
                text = first_w["text"] if first_w else r["texts"][0]
                if first_w and _num(first_w.get("from")) is not None:
                    arrive = r["start"] + (float(first_w["from"]) + L["entrance_frames"]) / fps
                near = arrive if arrive is not None else r["start"] + (L["enter_s"] if not r["full"] else 0.0)
                w = _spoken(words, text, r["start"] - 3.0, r["end"] + 1.0, near)
                if w:
                    word, how = w, f"shown text {text!r}"
                elif r["role"] in ("keyword", "card") and not any(ch.isdigit() for ch in text):
                    self.find("hint", "G12-unspoken", f"shows {text!r}, which is not said "
                              f"near {density.tc(r['start'])}", r,
                              fix="Show the word the speaker says, as he says it")
            if word is None:
                if r["role"] != "end":
                    unmeasured7.append(r["id"])
                continue
            if arrive is None:
                if _num(decl.get("arrive")) is not None:
                    arrive = r["start"] + float(decl["arrive"])
                else:
                    arrive = r["start"] + (L["enter_s"] if not r["full"] else 0.0)
            r["word"] = {"w": word["w"], "s": word["s"], "how": how, "arrive": round(arrive, 3)}
            if tol is not None:
                dt = arrive - word["s"]
                if abs(dt) > tol:
                    side = "before" if dt < 0 else "after"
                    self.find("fail", "G7-sync", f"fully there at {arrive:.2f} s, {abs(dt):.2f} s {side} "
                              f"{word['w']!r} ({word['s']:.2f} s; at most {L['tolerance_frames']:g} frames)", r,
                              measured=round(dt, 3),
                              target=L["tolerance_frames"],
                              fix=f"Start it at {word['s'] - (arrive - r['start']):.2f} s, or put a cue on the word")
            if L["hold_after_s"] and r["end"] - word["e"] < L["hold_after_s"] - 1e-6:
                left = r["end"] - word["e"]
                said = f"ends {left:.2f} s after {word['w']!r}" if left >= 0 else f"ends before {word['w']!r} is said"
                self.find("fail", "G7-hold", said + f"; it stays at least {L['hold_after_s']:g} s after its word", r,
                          fix=f"End it at {word['e'] + L['hold_after_s']:.2f} s or later")
        if unmeasured7:
            unknown["G7"] = unmeasured7

    def g9_elements(self) -> None:
        """G9: elements per graphic, words per keyword, no sentences, one overlay at a time."""
        L, rows, fps = self.L, self.rows, self.fps
        for r in rows:
            n = r["elements"]
            if L["elements_max"] and n is not None and r["role"] != "proof":
                if n > L["elements_max"]:
                    self.find("fail", "G9-elements", f"{n} elements at once (at most "
                              f"{L['elements_max']})", r, measured=n, target=L["elements_max"],
                              fix="Keep the one thing the sentence needs; split the rest or drop it")
                elif n == L["elements_max"] and n > 2:
                    self.find("hint", "G9-elements", f"{n} elements at once (the upper end)",
                              r)
            for i, txt in enumerate(r["texts"]):
                nw = len(txt.split())
                if r["role"] in ("keyword", "chapter") or (r["role"] == "card" and i == 0):
                    if nw > L["keyword_max_words"]:
                        self.find("fail", f"G9-words:{r['id']}:{i}", f"{txt!r} has {nw} words (at most "
                                  f"{L['keyword_max_words']})", r, measured=nw, target=L["keyword_max_words"],
                                  fix="One keyword or a number, never a sentence")
                sentence = nw >= 8 or (nw >= 5 and SENTENCE_END.search(txt))
                if not L["full_sentences"] and r["role"] != "proof" and sentence:
                    self.find("fail", f"G9-sentence:{r['id']}:{i}", f"{txt!r} is a whole sentence",
                              r, fix="A keyword or a short line; the speaker says the sentence")
        overlays = [r for r in rows if not r["full"] and r["role"] != "proof"]
        for i, a in enumerate(overlays):
            for b in overlays[i + 1:]:
                if b["start"] >= a["end"] - 1 / fps:
                    break
                self.find("fail", f"G9-overlap:{a['id']}-{b['id']}", f"stands over the speaker together with "
                          f"{a['id']} ({b['start']:.2f} to {min(a['end'], b['end']):.2f} s)", b,
                          fix="One overlay at a time: drop one or move it")

    def g10_sounds(self) -> None:
        """G10: effect sounds per graphic (a chapter card its pair), a dry Short."""
        L, rows, plan, short, minutes = self.L, self.rows, self.plan, self.short, self.minutes
        snd = plan.get("sound") if isinstance(plan.get("sound"), dict) else {}
        counts = {r["id"]: 0 for r in rows}
        by_id = {r["id"]: r for r in rows}
        stray = 0
        for key in ("hits", "whooshes", "typing"):
            for ref in snd.get(key) or []:
                if isinstance(ref, str):
                    iid = ref.partition("@")[0]
                    if iid in counts:
                        counts[iid] += 1
                    continue
                t = _num(ref)
                if t is None:
                    continue
                hit = [r for r in rows if r["start"] - 0.1 <= t < r["end"]]
                if hit:
                    counts[max(hit, key=lambda r: r["start"])["id"]] += 1
                else:
                    stray += 1
        tsounds: dict[str, int] | None = None
        for r in rows:
            e = r["e"]
            if e.get("kind") == "motion" and e.get("sound"):
                if tsounds is None:
                    from .motion import review as _review
                    tsounds = _review.template_sounds()
                counts[r["id"]] += int(tsounds.get(str(e.get("scene") or "").split("@")[0], 0) or 0) if e.get("scene") \
                    else 1
            ds = r["decl"].get("sounds")
            if ds is not None:
                counts[r["id"]] = max(counts[r["id"]], len(ds) if isinstance(ds, list) else int(_num(ds, 0) or 0))
        events = snd.get("events") in (True, "auto", "on")
        self.counts = counts
        self.metrics["sounds"] = sum(counts.values()) + stray
        if short and L["shorts_dry"]:
            loud = {k: v for k, v in counts.items() if v}
            if loud or stray or events:
                what = [f"{k} ({v})" for k, v in loud.items()] + ([f"{stray} more"] if stray else []) + (
                    ["the effect layer (sound.events)"] if events else [])
                self.find("fail", "G10-short-dry", f"A Short is dry, but effect sounds are set: {', '.join(what)}",
                          fix="Take every hit, whoosh and pop out of the Short's plan (and sound.events)")
        else:
            for iid, n in counts.items():
                r = by_id[iid]
                top = max(L["sounds_max"], len(L["chapter_pair"])) if r["role"] == "chapter" else L["sounds_max"]
                if n > top:
                    self.find("fail", "G10-sounds", f"{n} effect sounds (at most {top})", r, measured=n, target=top,
                              fix="One sound on the landing, or none")
            opening = [r for r in rows if r["start"] < 60.0 and r["role"] not in ("proof", "end")]
            if len(opening) >= 3 and all(counts[r["id"]] for r in opening):
                self.find("hint", "G10-every", "Every graphic of the opening has an effect sound; not every one gets "
                          "one", fix="Keep the sound on the strongest moments")
            if L["sounds_per_minute"] and minutes:
                rate10 = (sum(counts.values()) + stray) / minutes
                if rate10 > L["sounds_per_minute"][1] + 1e-9:
                    self.find("hint", "G10-per-minute", f"{rate10:.1f} effect sounds per minute (at most "
                              f"{L['sounds_per_minute'][1]:g})")

    def g11_safe(self) -> None:
        """G11: boxes and keyword positions inside the safe area of the format."""
        L, rows, unknown, fmt, W, H = self.L, self.rows, self.unknown, self.fmt, self.W, self.H
        if L["safe"]:
            sa = L["safe"].get(fmt) if isinstance(L["safe"].get(fmt), dict) else None
            if sa:
                x0, y0 = float(sa.get("left", 0)), float(sa.get("top", 0))
                x1, y1 = W - float(sa.get("right", 0)), H - float(sa.get("bottom", 0))
                for r in rows:
                    if r["role"] == "proof" and not r["decl"].get("box"):
                        continue
                    box = r["decl"].get("box")
                    pts = []
                    if isinstance(box, (list, tuple)) and len(box) == 4 and all(_num(v) is not None for v in box):
                        bx, by, bw, bh = (float(v) for v in box)
                        if not (bx >= x0 - 0.5 and by >= y0 - 0.5 and bx + bw <= x1 + 0.5 and by + bh <= y1 + 0.5):
                            self.find("fail", "G11-box", f"its box {bx:.0f},{by:.0f} {bw:.0f}x{bh:.0f} leaves the safe "
                                      f"area {x0:.0f},{y0:.0f} to {x1:.0f},{y1:.0f}", r,
                                      fix="Keep everything that matters inside the safe area")
                        continue
                    d = r["e"].get("data") if isinstance(r["e"].get("data"), dict) else {}
                    for w in d.get("words") or []:
                        if isinstance(w, dict) and _num(w.get("x")) is not None and _num(w.get("y")) is not None:
                            pts.append((float(w["x"]) * W, float(w["y"]) * H, w.get("text")))
                    bad = [p for p in pts if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1)]
                    if bad:
                        self.find("fail", "G11-point", f"{bad[0][2]!r} sits at "
                                  f"{bad[0][0]:.0f},{bad[0][1]:.0f}, outside the safe area", r,
                                  fix="Move it inside the safe area")
        else:
            unknown.setdefault("G11", []).append("the pack gives no graphics.safe_area")


def check_plan(plan_path: Path | str | None = None, plan: dict | None = None, pack: Any = None,
               episode_dir: Path | None = None) -> dict:
    """The gate's verdict on one plan: {"pass", "skipped", "findings", "fails", "hints", "metrics", "graphics",
    "not_measured"}. Nothing is written."""
    from . import brand
    pack = pack or brand.load()
    p = Path(plan_path) if plan_path else None
    if plan is None:
        plan = json.loads(p.read_text(encoding="utf-8"))
    ep_dir = episode_dir or (p.resolve().parent.parent if p else None)
    verdict: dict = {"plan": str(p) if p else None, "pass": True, "skipped": None, "findings": [], "fails": [],
                     "hints": [], "metrics": {}, "graphics": [], "not_measured": {}}
    L = limits(pack)
    if L is None:
        verdict["skipped"] = "the style pack has no graphic system (edit-style.json graphics): nothing to check"
        return verdict
    c = _Check(plan, pack, L, ep_dir)
    c.run()
    rows, counts = c.rows, c.counts
    by_type: dict[str, int] = {}
    for r in rows:
        k = r["type"] or r["role"] or "none"
        by_type[k] = by_type.get(k, 0) + 1
    verdict["findings"] = c.F
    verdict["fails"] = [f for f in c.F if f["level"] == "fail"]
    verdict["hints"] = [f for f in c.F if f["level"] == "hint"]
    verdict["pass"] = not verdict["fails"]
    verdict["not_measured"] = c.unknown
    verdict["metrics"] = {
        "format": c.fmt, "duration_s": round(c.total, 2), "inserts": len(rows), "by_type": by_type, **c.metrics,
        "untyped": sum(1 for r in rows if r["type"] is None and r["role"] not in ("proof", "end")),
    }
    verdict["graphics"] = [{"id": r["id"], "kind": r["e"].get("kind"), "scene": r["e"].get("scene"),
                            "type": r["type"], "role": r["role"], "how": r["how"], "start": round(r["start"], 2),
                            "end": round(r["end"], 2), "full": r["full"], "texts": r["texts"],
                            "elements": r["elements"], "sizes": r["sizes"], "colors": r["colors"],
                            "shapes": r["shapes"], "sounds": counts.get(r["id"], 0), "word": r.get("word"),
                            "source": str(r["source"]) if r["source"] else None} for r in rows]
    return verdict


# ---- words for people -------------------------------------------------------------------------------------------
def _groups(fails: list[dict]) -> list[tuple[str, list[dict]]]:
    out: dict[str, list[dict]] = {}
    for f in fails:
        out.setdefault(f["id"].split(":", 1)[0], []).append(f)
    return list(out.items())


def text(verdict: dict, limit: int = 8) -> str:
    """The verdict in plain lines: per failed check what is wrong and the fix, then the hints and what was not
    measured."""
    if verdict.get("skipped"):
        return f"Graphics gate skipped: {verdict['skipped']}."
    m = verdict.get("metrics") or {}
    head = (f"{Path(verdict.get('plan') or 'plan').name}: speaker {m.get('speaker_share', 0):.0%}, full-screen "
            f"graphics {m.get('graphics_share', 0):.0%}, {m.get('inserts', 0)} inserts"
            + ("" if m.get("per_minute_after") is None else f", {m['per_minute_after']:g} per minute after the first"))
    lines = [head]
    if verdict.get("pass"):
        lines.append("Graphics check passes.")
    for gid, fs in _groups(verdict.get("fails") or []):
        rule = fs[0]["rule"]
        if len(fs) == 1:
            f = fs[0]
            lines.append(f"- {rule} {f['text']}." + (f" Fix: {f['fix']}." if f.get("fix") else ""))
            continue
        same = len({f.get("fix") for f in fs}) == 1
        items = [f["text"] + ("" if same or not f.get("fix") else f" (fix: {f['fix']})") for f in fs[:limit]]
        lines.append(f"- {rule} {gid} ({len(fs)}): " + "; ".join(items)
                     + (f"; … and {len(fs) - limit} more" if len(fs) > limit else "")
                     + (f". Fix: {fs[0]['fix']}." if same and fs[0].get("fix") else "."))
    hints = verdict.get("hints") or []
    if hints:
        lines.append(f"Hints ({len(hints)}): " + "; ".join(h["text"] for h in hints[:limit])
                     + (f"; … and {len(hints) - limit} more" if len(hints) > limit else ""))
    nm = verdict.get("not_measured") or {}
    if nm:
        lines.append("Not measured: " + "; ".join(f"{k} ({len(v)}: {', '.join(v[:6])}{' …' if len(v) > 6 else ''})"
                                                  for k, v in nm.items()))
    return "\n".join(lines)


def short_line(verdict: dict) -> str:
    if verdict.get("skipped"):
        return f"Graphics gate skipped: {verdict['skipped']}."
    name = Path(verdict.get("plan") or "plan").name
    if verdict.get("pass"):
        hints = len(verdict.get("hints") or [])
        return f"Graphics check passes: {name}" + (f" ({hints} hints)." if hints else ".")
    rules = sorted({f["rule"] for f in verdict.get("fails") or []}, key=lambda x: int(x[1:]) if x[1:].isdigit() else 99)
    return f"Graphics check fails: {name}, {len(verdict['fails'])} point(s) in {', '.join(rules)}."


def summary(verdict: dict) -> dict:
    return {"plan": verdict.get("plan"), "pass": verdict.get("pass"), "skipped": verdict.get("skipped"),
            "metrics": verdict.get("metrics"), "fails": [f["id"] for f in verdict.get("fails") or []],
            "hints": len(verdict.get("hints") or [])}


def digest(verdict: dict) -> str:
    import hashlib
    return hashlib.sha1(json.dumps(sorted(f["id"] for f in verdict.get("fails") or [])).encode()).hexdigest()[:12]


# ---- in the render step -------------------------------------------------------------------------------------------
def _rel(plan_path: Path, episode_dir: Path) -> str:
    try:
        return plan_path.resolve().relative_to(episode_dir.resolve()).as_posix()
    except ValueError:
        return str(plan_path)


def _open_cards(episode: str) -> list[dict]:
    from . import approvals
    return [c for c in approvals.list_cards(episode=episode, status="open")
            if (c.get("data") or {}).get("graphics_gate")]


def _card(episode: str, plan_rel: str, verdict: dict) -> int:
    """The one card that names what to fix (an open card for the same plan and the same findings is reused)."""
    from . import approvals, db
    dg = digest(verdict)
    for c in _open_cards(episode):
        d = c["data"]["graphics_gate"]
        if d.get("plan") == plan_rel and d.get("digest") == dg:
            return c["id"]
        if d.get("plan") != plan_rel or d.get("digest") != dg:
            db.update("cards", c["id"], status="expired", decided_at=db.now(),
                      reason="a newer graphics check replaced this card")
    n = len(verdict["fails"])
    body = (f"{text(verdict, limit=12)}\n\nThe video does not render while these points fail (graphics_gate.mode "
            "block). Yes: the Editor gets this list and fixes the plan as a new version. No: it stays stopped; say in "
            "the chat what should change (a rule in the style pack, the plan, or the gate).")
    card = approvals.propose(episode, "edit", "other", f"Graphics check fails: {n} point(s) in {Path(plan_rel).name}",
                             body=body, identity="critic",
                             data={"graphics_gate": {**summary(verdict), "plan": plan_rel, "digest": dg,
                                                     "fixes": [{"id": f["id"], "rule": f["rule"], "text": f["text"],
                                                                "fix": f.get("fix")} for f in verdict["fails"]]}})
    return card["id"]


def guard(plan_path: Path | str, episode: str | None, pack: Any = None, episode_dir: Path | None = None,
          log: Any = print) -> dict | None:
    """Before the video renders: check the plan. block mode raises Blocked (with the card) on a failing plan; warn
    mode logs and tells the chat once per plan and finding set; off does nothing. Returns the verdict (None when
    off)."""
    cfg = settings()
    if cfg["mode"] == "off":
        return None
    p = Path(plan_path)
    v = check_plan(p, pack=pack, episode_dir=episode_dir)
    v["mode"] = cfg["mode"]
    if v.get("skipped"):
        return v
    ep_dir = episode_dir or p.resolve().parent.parent
    real = bool(episode) and not str(episode).startswith("_")
    if v["pass"]:
        log(short_line(v))
        if real:
            _close(str(episode), _rel(p, ep_dir))
        return v
    if cfg["mode"] == "warn":
        for line in text(v).splitlines():
            log("graphics gate (warn): " + line)
        if real:
            _tell_once(str(episode), _rel(p, ep_dir), v)
        return v
    card = _card(str(episode), _rel(p, ep_dir), v) if real else None
    raise Blocked(f"The video may not render: the graphics check fails ({len(v['fails'])} point(s))"
                  + (f"; card {card} names every fix" if card else "") + ".\n" + text(v), v, card)


def _close(episode: str, plan_rel: str) -> None:
    from . import db
    for c in _open_cards(episode):
        db.update("cards", c["id"], status="expired", decided_at=db.now(),
                  reason=f"the graphics check passes now ({plan_rel})")


def _tell_once(episode: str, plan_rel: str, verdict: dict) -> None:
    from . import db
    key = f"graphics_gate:{episode}:{plan_rel}"
    dg = digest(verdict)
    if db.kv_get(key) == dg:
        return
    db.kv_set(key, dg)
    try:
        from .conductor import flow
        flow.post(episode, short_line(verdict) + " (The gate only warns in this studio.) `crewcut graphics-gate "
                  f"{plan_rel}` lists every point.", step="edit", author="critic")
    except Exception:  # noqa: BLE001 - a warning must never stop the render
        pass


def on_card(card: dict) -> bool:
    """The user's answer on the gate's card. True when handled here."""
    d = (card.get("data") or {}).get("graphics_gate")
    if d is None:
        return False
    from .conductor import flow, queue
    episode = card["episode"]
    if card["status"] == "accepted":
        fixes = "\n".join(f"- {f['rule']} {f['text']}" + (f" Fix: {f['fix']}" if f.get("fix") else "")
                          for f in d.get("fixes") or [])
        queue.add(episode, "editor", "edit",
                  f"The graphics check fails on {d.get('plan')} (card #{card['id']}). Fix every point in a new plan "
                  f"version, keep what passes, run `crewcut graphics-gate <new plan>` until it passes, then render:\n"
                  f"{fixes}")
        flow.post(episode, "The Editor fixes the graphics points in a new plan version.", card=card["id"])
    else:
        flow.post(episode, "The video stays unrendered. Say in the chat what should change.", card=card["id"])
    return True


def editor_note() -> str:
    """The line the Editor and the Critic get in the edit step while the gate is on and the pack has a system."""
    cfg = settings()
    if cfg["mode"] == "off":
        return ""
    try:
        from . import brand
        if limits(brand.load()) is None:
            return ""
    except Exception:  # noqa: BLE001 - a broken pack must not break a prompt
        return ""
    strict = ("the video does not render and a card names every fix" if cfg["mode"] == "block"
              else "the chat gets a warning")
    return ("\nThe graphics gate is on (" + cfg["mode"] + "): before `crewcut render all|cut` it checks the plan "
            "against edit-style.json graphics (types, colours, type size, shapes, speaker and full-screen share, "
            "density, word sync, elements, sounds, safe zones). Give every insert that is not a library template "
            '`"graphic": {"type": …}` (and what the plan cannot say: on, text, colors, text_px, elements, shapes, '
            "box). "
            f"Run `crewcut graphics-gate edit/plan-vNNN.json` yourself; while it fails, {strict}.")


__all__ = ["Blocked", "DEFAULTS", "MODES", "check_plan", "digest", "editor_note", "guard", "limits", "on_card",
           "resolve_type", "scan_source", "settings", "short_line", "summary", "text"]
