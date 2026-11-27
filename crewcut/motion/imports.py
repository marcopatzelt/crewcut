"""Imported motion templates: Lottie files and After Effects projects made by others, turned into the channel's look.

Ready-made templates (a free Mixkit or LottieFiles download, later a bought one) may be used in videos but not passed
on. So they live only in the studio's private folder, never in the app or its repository:

    studio/library/templates-private/<name>/
        original/<file>          the download as it came (never changed)
        template.json            title, kind (lottie | aep), source link, licence, the conversion report, dates
        converted.json           Lottie: the file in the pack's palette, fonts and frame rate (what videos use)
        project.ecproj           After Effects: the EffectCraft project after a lossless import (needs adaptation)
        preview.png              one frame rendered by EffectCraft (when the engine is here)

The conversion (``convert_lottie``) is pure Python and needs no engine:

- colours: every colour of fills, strokes, gradients, solids, text and colour effects goes to a palette role
  (``studio_style.role_of``: the colour that paints the most area is the surface, paper or ink; other saturated
  colours the accent, or the highlight when they are text on a dark surface; greys ink or paper); alpha stays;
- fonts: every font goes to the pack's display font (bold styles) or body font (the rest); embedded glyph outlines
  (``chars``) and web font links are dropped, so the engine sets the text in the pack's font files;
- frame rate: ``fr`` becomes the pack's fps (25); every time given in frames (in and out points, start times,
  keyframe times, markers) is scaled, so the animation keeps its length in seconds. Expressions are reported, not
  rewritten (an expression that counts frames may shift);
- texts: ``texts`` (layer name -> new text) replaces the words of named text layers.

After Effects projects (``.aep``, ``.aepx``) go through EffectCraft's own importer: first a dry run, and only an
import that loses nothing (or one the user allows with ``--allow-losses``) is kept. Then one script sets every comp to
the pack's fps and every text layer to the pack's display font. Colours inside an After Effects project are not
rewritten automatically: the template is marked ``needs_adaptation`` and the Designer adapts it in EffectCraft.
Plugins from other vendors (Element 3D, Trapcode, Saber, ...) do not import; their templates are refused by the dry
run. ``.mogrt``, ``.ffx`` and Resolve templates have no Linux path and are refused here.

A video uses a converted Lottie through the motion template ``lottie_clip``: ``crewcut motion imports use`` copies
``converted.json`` (with the episode's texts) into ``episodes/<id>/motion/<insert>/`` and prints the plan entry.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import brand, paths
from . import studio_style

NAME = re.compile(r"^[a-z][a-z0-9_-]{1,48}$")
LOTTIE_EXT = (".json", ".lottie")
AEP_EXT = (".aep", ".aepx")
NO_LINUX_PATH = (".mogrt", ".ffx", ".drfx", ".setting", ".prproj", ".mgt")
BOLD = re.compile(r"(black|heavy|extra\s*bold|ultra\s*bold|semi\s*bold|demi|bold)", re.I)
LICENCE_OK = re.compile(r"(mixkit\s+free|lottie\s+simple|cc0|cc-by|creative\s+commons|mit|apache|ofl|own|envato\s+"
                        r"elements|motion\s+array)", re.I)


class ImportError_(ValueError):
    """The template cannot be imported as asked. The message says what to change."""


# ---- folders --------------------------------------------------------------------------------------------------------
def private_dir() -> Path:
    """The studio's private template folder (never inside the app or a git checkout of it)."""
    return paths.studio_root() / "library" / "templates-private"


def _refuse_public(target: Path) -> None:
    """Private templates never land inside the app folder or any git working tree (the app is a public repository)."""
    t = target.resolve()
    app = paths.app_root().resolve()
    if t == app or app in t.parents:
        raise ImportError_(f"{target} is inside the app folder; private templates belong in the studio "
                           "(library/templates-private/)")
    for d in (t, *t.parents):
        if (d / ".git").exists() and (d / "crewcut").is_dir() and (d / "pyproject.toml").is_file():
            raise ImportError_(f"{target} is inside a Crewcut source checkout ({d}); private templates are never "
                               "committed")


def entries() -> list[dict]:
    """Every imported template: ``template.json`` plus its folder."""
    root = private_dir()
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*/template.json")):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(e, dict):
            e["folder"] = str(f.parent)
            out.append(e)
    return out


def get(name: str) -> dict:
    for e in entries():
        if e.get("name") == name:
            return e
    raise ImportError_(f"no imported template '{name}' in {private_dir()} (crewcut motion imports list)")


# ---- Lottie: walking the file ----------------------------------------------------------------------------------------
def _is_prop(d: Any) -> bool:
    return isinstance(d, dict) and "k" in d and d.get("a") in (0, 1)


def _rgb_hex(v: list) -> str | None:
    if not isinstance(v, list) or len(v) < 3 or not all(isinstance(x, (int, float)) for x in v[:3]):
        return None
    scale = 255.0 if max(v[:3]) > 1.0 else 1.0         # a few old exporters write 0..255
    return "#" + "".join(f"{max(0, min(255, round(x / scale * 255))):02X}" for x in v[:3])


def _set_rgb(v: list, h: str) -> list:
    scale = 255.0 if max(v[:3]) > 1.0 else 1.0
    rgb = [int(h[i:i + 2], 16) / 255 * scale for i in (1, 3, 5)]
    return [round(x, 6) for x in rgb] + list(v[3:])


def _color_values(prop: dict) -> list[list]:
    """The colour arrays inside one colour property (static or every keyframe's start and end)."""
    if not _is_prop(prop):
        return []
    k = prop["k"]
    if prop.get("a") == 0:
        return [k] if isinstance(k, list) and k and not isinstance(k[0], dict) else []
    out = []
    for kf in k if isinstance(k, list) else []:
        if isinstance(kf, dict):
            out += [kf[x] for x in ("s", "e") if isinstance(kf.get(x), list)]
    return out


def _gradient_values(g: dict) -> list[tuple[list, int]]:
    """Gradient stop arrays with their colour-stop count (``p``): [offset, r, g, b, ...] then alpha stops."""
    if not isinstance(g, dict) or not _is_prop(g.get("k")):
        return []
    n = int(g.get("p") or 0)
    return [(v, n) for v in _color_values(g["k"])]


def _walk(node: Any, visit: Callable[[dict, str | None], None], parent_key: str | None = None) -> None:
    if isinstance(node, dict):
        visit(node, parent_key)
        for k, v in node.items():
            _walk(v, visit, k)
    elif isinstance(node, list):
        for v in node:
            _walk(v, visit, parent_key)


def _area(items: list) -> float:
    """The drawn area of a shape group's rectangles and ellipses (static sizes), at least 1."""
    a = 0.0
    for it in items:
        if isinstance(it, dict) and it.get("ty") in ("rc", "el") and _is_prop(it.get("s")) and it["s"].get("a") == 0:
            k = it["s"]["k"]
            if isinstance(k, list) and len(k) >= 2 and all(isinstance(x, (int, float)) for x in k[:2]):
                a += abs(k[0] * k[1]) * (0.785 if it["ty"] == "el" else 1.0)
    return max(1.0, a)


def _color_slots(doc: dict) -> list[tuple[str, Any, float]]:
    """Every place that holds a colour, with a weight (the area it paints, roughly): ("rgb", list, w) for 0..1
    arrays, ("grad", (list, n), w), ("hex", (dict, key), w)."""
    slots: list[tuple[str, Any, float]] = []

    def visit(d: dict, _key: str | None) -> None:
        ty = d.get("ty")
        items = d.get("it") if isinstance(d.get("it"), list) else d.get("shapes") if isinstance(d.get("shapes"), list) else None
        if items is not None:
            w = _area(items)
            for it in items:
                if isinstance(it, dict) and it.get("ty") in ("fl", "st") and isinstance(it.get("c"), dict):
                    k = 0.25 if it["ty"] == "st" else 1.0
                    slots.extend(("rgb", v, w * k) for v in _color_values(it["c"]))
                if isinstance(it, dict) and it.get("ty") in ("gf", "gs") and isinstance(it.get("g"), dict):
                    slots.extend(("grad", x, w) for x in _gradient_values(it["g"]))
        if ty == 1 and isinstance(d.get("sc"), str):                # solid layer
            sw, sh = d.get("sw") or 1, d.get("sh") or 1
            slots.append(("hex", (d, "sc"), float(sw) * float(sh) if isinstance(sw, (int, float)) else 1.0))
        if ty == 2 and _is_prop(d.get("v")) and "ef" not in d:      # effect value of type colour
            slots.extend(("rgb", v, 1.0) for v in _color_values(d["v"]))
        if "t" in d and "f" in d and isinstance(d.get("t"), str):   # a text document (s of t.d.k)
            size = float(d.get("s") or 40) if isinstance(d.get("s"), (int, float)) else 40.0
            for key in ("fc", "sc"):
                if isinstance(d.get(key), list):
                    slots.append(("rgb", d[key], size * size * 0.5 * max(1, len(d["t"]))))

    _walk(doc, visit)
    return slots


def colors(doc: dict, weighted: bool = False) -> Counter:
    """How often each colour is used (#RRGGBB -> count), or with ``weighted`` the area it roughly paints."""
    c: Counter = Counter()
    for kind, v, w in _color_slots(doc):
        add = w if weighted else 1
        if kind == "rgb":
            h = _rgb_hex(v)
            if h:
                c[h] += add
        elif kind == "grad":
            arr, n = v
            for i in range(n):
                h = _rgb_hex(arr[i * 4 + 1:i * 4 + 4]) if len(arr) >= i * 4 + 4 else None
                if h:
                    c[h] += add
        else:
            d, key = v
            h = studio_style._hex(d[key])
            if h:
                c[h] += add
    return c


def text_colors(doc: dict) -> set[str]:
    """Colours used by text (fill or stroke of a text document)."""
    out: set[str] = set()

    def visit(d: dict, _key: str | None) -> None:
        if "t" in d and "f" in d and isinstance(d.get("t"), str):
            for key in ("fc", "sc"):
                h = _rgb_hex(d[key]) if isinstance(d.get(key), list) else None
                if h:
                    out.add(h)

    _walk(doc, visit)
    return out


def color_map(doc: dict, pal: dict[str, str]) -> dict[str, dict]:
    """Old colour -> {"role", "to", "uses"} for every colour in the file, in the channel's grammar
    (``studio_style.role_of``): the colour that paints the most area is the surface (paper when light, ink when
    dark); other saturated colours become the accent (lines, edges, small shapes), or the highlight when they are
    text on a dark surface; greys go to ink or paper by lightness."""
    used = colors(doc)
    area = colors(doc, weighted=True)
    order = [h for h, _ in area.most_common()]
    surface = order[0] if order else None
    dark = brand.hex_to_oklch(surface)[0] < 0.6 if surface else False
    texts = text_colors(doc)
    out = {}
    for h in used:
        role = studio_style.role_of(h, surface=h == surface, text=h in texts, on_dark=dark)
        out[h] = {"role": role, "to": pal[role], "uses": used[h]}
    return out


def _recolor(doc: dict, mapping: dict[str, dict]) -> int:
    n = 0
    for kind, v, _w in _color_slots(doc):
        if kind == "rgb":
            h = _rgb_hex(v)
            if h in mapping:
                v[:] = _set_rgb(v, mapping[h]["to"])
                n += 1
        elif kind == "grad":
            arr, stops = v
            for i in range(stops):
                seg = arr[i * 4 + 1:i * 4 + 4]
                h = _rgb_hex(seg) if len(seg) == 3 else None
                if h in mapping:
                    arr[i * 4 + 1:i * 4 + 4] = _set_rgb(seg, mapping[h]["to"])
                    n += 1
        else:
            d, key = v
            h = studio_style._hex(d[key])
            if h in mapping:
                d[key] = mapping[h]["to"].lower()
                n += 1
    return n


def _refont(doc: dict, fonts: dict[str, dict]) -> dict[str, str]:
    """Every font of the file to the pack's display (bold styles) or body font. Returns old name -> new name."""
    renamed: dict[str, str] = {}
    lst = (doc.get("fonts") or {}).get("list") if isinstance(doc.get("fonts"), dict) else None
    for f in lst or []:
        if not isinstance(f, dict):
            continue
        old = str(f.get("fName") or f.get("fFamily") or "")
        style = f"{f.get('fStyle') or ''} {old}"
        role = "display" if BOLD.search(style) or not style.strip() else "body"
        fam = fonts[role]["family"]
        weight = int(fonts[role]["weight"])
        style_name = "ExtraBold" if weight >= 750 else ("Bold" if weight >= 650 else
                                                        ("SemiBold" if weight >= 550 else "Medium"))
        new = f"{fam.replace(' ', '')}-{style_name}"
        f.update({"fFamily": fam, "fName": new, "fStyle": style_name, "fWeight": str(weight), "origin": 0})
        f.pop("fPath", None)
        renamed[old] = new
    if "chars" in doc:
        doc.pop("chars")

    def visit(d: dict, _key: str | None) -> None:
        if "t" in d and "f" in d and isinstance(d.get("t"), str) and isinstance(d.get("f"), str):
            d["f"] = renamed.get(d["f"], d["f"])

    _walk(doc, visit)
    return renamed


def _retime(doc: dict, factor: float) -> int:
    """Scale every time in frames by ``factor``. Returns how many values changed."""
    n = 0

    def scale(d: dict, key: str) -> None:
        nonlocal n
        if isinstance(d.get(key), (int, float)) and not isinstance(d.get(key), bool):
            d[key] = round(d[key] * factor, 4)
            n += 1

    for key in ("ip", "op"):
        scale(doc, key)
    for m in doc.get("markers") or []:
        if isinstance(m, dict):
            scale(m, "tm")
            scale(m, "dr")

    def visit(d: dict, _key: str | None) -> None:
        if isinstance(d.get("ty"), int) and ("ip" in d or "op" in d) and "ks" in d:     # a layer
            for key in ("ip", "op", "st"):
                scale(d, key)
        if _is_prop(d) and d.get("a") == 1 and isinstance(d["k"], list):
            for kf in d["k"]:
                if isinstance(kf, dict):
                    scale(kf, "t")
        if _key == "d" and isinstance(d.get("k"), list):                                  # text document keys
            for kf in d["k"]:
                if isinstance(kf, dict) and isinstance(kf.get("s"), dict):
                    scale(kf, "t")

    _walk(doc.get("layers") or [], visit)
    _walk(doc.get("assets") or [], visit)
    return n


def _expressions(doc: dict) -> int:
    n = 0

    def visit(d: dict, _key: str | None) -> None:
        nonlocal n
        if _is_prop(d) and isinstance(d.get("x"), str) and d["x"].strip():
            n += 1

    _walk(doc, visit)
    return n


def text_layers(doc: dict) -> dict[str, str]:
    """Text layer name -> its first text (the words a template shows)."""
    out = {}

    def visit(d: dict, _key: str | None) -> None:
        if d.get("ty") == 5 and isinstance(d.get("t"), dict):
            k = ((d["t"].get("d") or {}).get("k") or [])
            first = k[0].get("s", {}).get("t") if k and isinstance(k[0], dict) else None
            if isinstance(first, str):
                out[str(d.get("nm") or f"text {len(out) + 1}")] = first

    _walk(doc, visit)
    return out


def set_texts(doc: dict, texts: dict[str, str]) -> list[str]:
    """Replace the words of named text layers (every keyframe of the text). Returns the names it found."""
    found = []

    def visit(d: dict, _key: str | None) -> None:
        if d.get("ty") == 5 and str(d.get("nm")) in texts and isinstance(d.get("t"), dict):
            for kf in (d["t"].get("d") or {}).get("k") or []:
                if isinstance(kf, dict) and isinstance(kf.get("s"), dict):
                    kf["s"]["t"] = str(texts[str(d["nm"])]).replace("\n", "\r")
            found.append(str(d["nm"]))

    _walk(doc, visit)
    return sorted(set(found))


def read_lottie(p: Path) -> dict:
    """A Lottie JSON file, or the first animation of a dotLottie (.lottie zip)."""
    if p.suffix.lower() == ".lottie":
        import zipfile
        with zipfile.ZipFile(p) as z:
            names = sorted(n for n in z.namelist() if n.startswith("animations/") and n.endswith(".json"))
            if not names:
                raise ImportError_(f"{p.name}: no animation inside the dotLottie file")
            if z.getinfo(names[0]).file_size > 50_000_000:
                raise ImportError_(f"{p.name}: the animation is larger than 50 MB")
            doc = json.loads(z.read(names[0]).decode("utf-8"))
    else:
        if p.stat().st_size > 50_000_000:
            raise ImportError_(f"{p.name}: larger than 50 MB")
        doc = json.loads(p.read_text(encoding="utf-8"))
    if not (isinstance(doc, dict) and isinstance(doc.get("layers"), list) and "fr" in doc and "op" in doc):
        raise ImportError_(f"{p.name} is not a Lottie animation (needs fr, op and layers)")
    return doc


def convert_lottie(doc: dict, pack: brand.Pack | None = None, texts: dict[str, str] | None = None,
                   fps: int | None = None) -> tuple[dict, dict]:
    """A copy of the Lottie in the pack's palette, fonts and fps, and the report of what changed."""
    pack = pack or brand.load()
    pal, fonts = studio_style.palette(pack), studio_style.fonts(pack)
    target = int(fps or studio_style.fps(pack))
    out = copy.deepcopy(doc)
    mapping = color_map(out, pal)
    recolored = _recolor(out, mapping)
    renamed = _refont(out, fonts)
    old_fps = float(out.get("fr") or target)
    factor = target / old_fps if old_fps > 0 else 1.0
    retimed = _retime(out, factor) if abs(factor - 1.0) > 1e-9 else 0
    out["fr"] = target
    found = set_texts(out, texts) if texts else []
    missing = sorted(set(texts or {}) - set(found))
    seconds = (float(out.get("op", 0)) - float(out.get("ip", 0))) / target
    report = {"palette": pal, "palette_source": studio_style.source(pack), "colors": mapping,
              "color_values_changed": recolored, "fonts": renamed, "fps": {"from": old_fps, "to": target},
              "time_values_scaled": retimed, "seconds": round(seconds, 3), "size": [out.get("w"), out.get("h")],
              "expressions": _expressions(out), "texts": text_layers(out), "texts_set": found,
              "texts_missing": missing, "warnings": []}
    if report["expressions"]:
        report["warnings"].append(f"{report['expressions']} expressions kept as they are; one that counts frames "
                                  f"may shift after the change from {old_fps:g} to {target} fps")
    if missing:
        report["warnings"].append(f"no text layer named {', '.join(missing)} (layers: "
                                  f"{', '.join(report['texts']) or 'none'})")
    if any(isinstance(a, dict) and a.get("p") and not str(a.get("p")).startswith("data:") and "layers" not in a
           for a in out.get("assets") or []):
        report["warnings"].append("the file names image files outside itself; keep them next to converted.json")
    return out, report


# ---- importing a file into the private folder ------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_meta(name: str, licence: str, source: str) -> None:
    if not NAME.match(name):
        raise ImportError_(f"name {name!r}: lower-case letters, digits, - and _ (2 to 49 characters), starting "
                           "with a letter")
    if not licence or not LICENCE_OK.search(licence):
        raise ImportError_("--licence must name the licence that allows the use (e.g. \"Mixkit Free License\", "
                           "\"Lottie Simple License\", \"CC0\"); a template without one is not imported")
    if not source:
        raise ImportError_("--source must say where the file came from (the item's page)")


def import_file(src: Path, name: str, licence: str, source: str, *, title: str | None = None,
                kind_of_insert: str = "overlay", allow_losses: bool = False, replace: bool = False,
                pack: brand.Pack | None = None, backend: Any = None, root: Path | None = None) -> dict:
    """Copy ``src`` into the private folder, convert it to the pack's look and write ``template.json``."""
    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise ImportError_(f"not found: {src}")
    ext = src.suffix.lower()
    if ext in NO_LINUX_PATH:
        raise ImportError_(f"{src.name}: {ext} templates need Adobe or Resolve on Windows or macOS; there is no "
                           "path for them here. Take a Lottie or a plugin-free After Effects project")
    if ext not in LOTTIE_EXT + AEP_EXT:
        raise ImportError_(f"{src.name}: only Lottie (.json, .lottie) and After Effects projects (.aep, .aepx)")
    if kind_of_insert not in ("overlay", "full"):
        raise ImportError_("kind must be overlay or full")
    _check_meta(name, licence, source)
    base = Path(root) if root else private_dir()
    folder = base / name
    _refuse_public(folder)
    if folder.exists():
        if not replace:
            raise ImportError_(f"{name} is already imported ({folder}); use --replace for a new version")
        shutil.rmtree(folder)
    (folder / "original").mkdir(parents=True)
    shutil.copy2(src, folder / "original" / src.name)
    pack = pack or brand.load()
    entry: dict[str, Any] = {"name": name, "title": title or name.replace("_", " ").replace("-", " "),
                             "source": source, "licence": licence, "original": f"original/{src.name}",
                             "insert_kind": kind_of_insert, "imported": _now(), "private": True,
                             "note": "Private: used in videos, never passed on or committed to a repository."}
    if ext in LOTTIE_EXT:
        doc = read_lottie(src)
        converted, report = convert_lottie(doc, pack)
        (folder / "converted.json").write_text(json.dumps(converted, ensure_ascii=False, separators=(",", ":")),
                                               encoding="utf-8")
        entry.update(kind="lottie", file="converted.json", report=report, needs_adaptation=False,
                     texts=report["texts"])
        if backend is not None:
            entry["engine_check"] = engine_check(folder, backend)
    else:
        entry.update(kind="aep", **aep_import(folder, src, backend, allow_losses, pack))
    (folder / "template.json").write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    entry["folder"] = str(folder)
    return entry


def _res(r: Any) -> Any:
    """An engine reply without the CLI's save wrapper (``{"result": ..., "saved": path}`` after --save/--save-as)."""
    return r.get("result") if isinstance(r, dict) and "saved" in r and "result" in r else r


def engine_check(folder: Path, backend: Any) -> dict:
    """Import ``converted.json`` into a scratch EffectCraft project and render one frame at 60 % (preview.png)."""
    proj = folder / ".check.ecproj"
    try:
        r = _res(backend.exec("file.importLottie", {"path": str(folder / "converted.json")}, project=None,
                              save_as=str(proj)))
        comp = r.get("comp") if isinstance(r, dict) else None
        info = _res(backend.exec("comp.info", {"comp": comp}, project=str(proj), save=False)) if comp is not None else {}
        t = round(float((info or {}).get("duration") or 1.0) * 0.6, 3)
        backend.render_frame(str(proj), str(folder / "preview.png"), comp=str((info or {}).get("name") or comp),
                             time=t, max_side=960, transparent=True)
        return {"ok": (folder / "preview.png").is_file(), "warnings": (r or {}).get("warnings") or [],
                "comp": {k: (info or {}).get(k) for k in ("name", "width", "height", "frameRate", "duration")},
                "preview": "preview.png"}
    except Exception as e:  # noqa: BLE001 - the check is a report, the import itself stands
        return {"ok": False, "error": str(e)}
    finally:
        proj.unlink(missing_ok=True)


def _aep_fix_script(fps: int, font: str) -> str:
    """After Effects-style script: every comp to ``fps``, every text layer to ``font``. Prints a JSON summary."""
    return (
        "var n = {comps: 0, texts: 0};\n"
        "for (var i = 1; i <= app.project.numItems; i++) {\n"
        "  var it = app.project.item(i);\n"
        "  if (!(it instanceof CompItem)) continue;\n"
        f"  it.frameRate = {fps}; n.comps++;\n"
        "  for (var j = 1; j <= it.numLayers; j++) {\n"
        "    var L = it.layer(j);\n"
        "    if (!(L instanceof TextLayer)) continue;\n"
        "    var p = L.property('Source Text'); var d = p.value;\n"
        f"    d.font = {json.dumps(font)}; p.setValue(d); n.texts++;\n"
        "  }\n"
        "}\n"
        "JSON.stringify(n);\n")


def aep_import(folder: Path, src: Path, backend: Any, allow_losses: bool, pack: brand.Pack) -> dict:
    """The EffectCraft path for an After Effects project: dry run, lossless import, fps and fonts. Colours stay."""
    if backend is None:
        return {"needs_adaptation": True, "report": None,
                "status": "copied only: effectcraft-cli is not here, run the import again in the Crewcut image"}
    path = str(folder / "original" / src.name)
    dry = _res(backend.exec("file.importAep", {"path": path, "dryRun": True}, project=None, save=False))
    report = (dry or {}).get("report") if isinstance(dry, dict) else None
    losses = _aep_losses(report)
    if losses and not allow_losses:
        raise ImportError_(f"{src.name} would lose parts in EffectCraft ({'; '.join(losses[:5])}). Take a template "
                           "without third-party plugins, or --allow-losses to keep the rest")
    proj = folder / "project.ecproj"
    res = _res(backend.exec("file.importAep", {"path": path, "allowLosses": bool(allow_losses)}, project=None,
                            save_as=str(proj)))
    fonts = studio_style.fonts(pack)
    fix = backend.script(_aep_fix_script(studio_style.fps(pack), fonts["display"]["family"]), project=str(proj),
                         save=True, name="crewcut-aep-fix.jsx")
    return {"needs_adaptation": True, "project": "project.ecproj", "report": report, "losses": losses,
            "comps": (res or {}).get("comps") if isinstance(res, dict) else None, "fix": fix,
            "status": "imported: fps and fonts set; colours still need the Designer (EffectCraft)"}


def _aep_losses(report: Any) -> list[str]:
    """Short lines for every category the importer says did not arrive. EffectCraft's ImportReport (docs/aep-import.md "What is reported"): ``losses`` holds per category a ``count``
    and up to 20 ``details``. ``missingFonts`` are no losses (the fix script sets the pack's font)."""
    out: list[str] = []
    losses = report.get("losses") if isinstance(report, dict) else None
    if isinstance(losses, dict):
        for cat, v in losses.items():
            count = v.get("count") if isinstance(v, dict) else v
            if isinstance(count, (int, float)) and count > 0:
                details = v.get("details") if isinstance(v, dict) else None
                first = f" ({str(details[0])[:80]})" if isinstance(details, list) and details else ""
                out.append(f"{cat}: {int(count)}{first}")
    elif isinstance(losses, list):
        out += [str(x)[:120] for x in losses if x]
    return out


# ---- using a template in an episode ----------------------------------------------------------------------------------
def use(name: str, episode: str, insert_id: str, texts: dict[str, str] | None = None,
        pack: brand.Pack | None = None) -> dict:
    """Copy a converted Lottie into ``episodes/<id>/motion/<insert>/<name>.json`` with this episode's texts, and the
    plan entry that shows it (motion template ``lottie_clip``)."""
    e = get(name)
    if e.get("kind") != "lottie":
        raise ImportError_(f"{name} is an After Effects project; adapt it in EffectCraft and save it as a custom "
                           "piece (crewcut motion new) instead")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$", insert_id):
        raise ImportError_(f"insert id {insert_id!r}: letters, digits, - and _ only")
    folder = Path(e["folder"])
    doc = json.loads((folder / e.get("file", "converted.json")).read_text(encoding="utf-8"))
    report: dict = {}
    if texts:
        doc, report = convert_lottie(doc, pack, texts=texts)
        if report["texts_missing"]:
            raise ImportError_(report["warnings"][-1])
    ep = paths.episode_dir(episode)
    if not ep.is_dir():
        raise ImportError_(f"episode not found: {episode}")
    out_dir = paths.inside(ep, f"motion/{insert_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rel = f"motion/{insert_id}/{name}.json"
    (ep / rel).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "SOURCE.md").write_text(
        f"# {e.get('title') or name}\n\nImported template `{name}` (private, never passed on).\n\n"
        f"- Source: {e.get('source')}\n- Licence: {e.get('licence')}\n- Converted: palette, fonts and fps of the "
        "style pack (crewcut motion imports)\n", encoding="utf-8")
    seconds = (float(doc.get("op", 0)) - float(doc.get("ip", 0))) / float(doc.get("fr") or 25)
    entry = {"id": insert_id, "kind": "motion", "scene": "lottie_clip", "start": 0.0, "end": round(seconds, 2),
             "transparent": e.get("insert_kind", "overlay") == "overlay", "data": {"file": rel}}
    return {"file": rel, "seconds": round(seconds, 3), "plan_entry": entry, "texts": text_layers(doc),
            "report": report or None}
