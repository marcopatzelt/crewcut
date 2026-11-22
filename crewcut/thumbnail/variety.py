"""Real A/B variety: one test set, different formats, visibly different images.

A YouTube "Test & compare" set has up to 3 variants. A set where every variant is the same picture with small
changes measures nothing. This module checks a round's plan (`SET.json`) and its finished images:

- the plan: as many variants as the pack asks for (`thumbnail.formats.per_set`, default 3), each a different format
  from the format library, at least `min_house` of the channel's own style and at least `min_pro` outside formats,
  and every pair differs in each hook field (focal object, text idea, emotion, composition, colour);
- the images: a perceptual hash (DCT, 64 bits), a layout similarity (brightness and edge structure on a coarse grid)
  and a colour similarity (hue, saturation and value histogram). A pair is too similar when the hashes are close
  (nearly the same picture), when the layouts correlate (the same composition), or when the colour histograms nearly
  match (the same colours). The later variant of such a pair must be made again with a new complete prompt.

- the person: the main face of every variant with a person is measured against the pack's face references
  (`identity.py`); a look-alike fails and is made again with stronger references;
- the references: which images each variant was made from (`REFERENCES.json` of `crewcut thumbnail make`); a pro
  format made from the house thumbnail instead of its format example fails.

A set may hold up to `max_candidates` variants; YouTube tests `per_set` at a time, so the plan names the finalists and
the rest is the reserve for a second round. One variant may be the control (`"role": "control"`): the channel's
current proven style, exempt from the new palette rules, but checked for face, words and near-duplicates.

`SET.json`:
    {"schema": 1, "title": "...", "finalists": ["A", "C", "E"], "variants": [
      {"label": "A", "format": "house-face-result", "image": "A-x/thumbnail-v001.png", "prompt": "A-x/prompt.txt",
       "hook": {"focal_object": "...", "text": "...", "emotion": "...", "composition": "...", "colour": "..."}},
      {"label": "E", "role": "control", "format": "house-face-result", "image": "E-x/thumbnail-v001.png", ...}]}
"""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

HOOK_FIELDS = ("focal_object", "text", "emotion", "composition", "colour")
DEFAULTS: dict[str, Any] = {
    "per_set": 3,
    "min_house": 1,
    "min_pro": 1,
    # Calibrated on 22 Nov 2026: four generated variants that differed only in the result card had layout
    # similarities of 0.69 to 0.80 and hash distances of 8 to 20; 528 pairs of real thumbnails in different formats
    # stayed at or below 0.44 layout, 0.79 colour and at or above 18 bits.
    "phash_min_distance": 16,
    "layout_max": 0.60,
    "colour_max": 0.90,
    "same_words": 0.6,
    "max_candidates": 5,
    "max_control": 1,
}
SET_FILE = "SET.json"
CHECK_FILE = "SET-CHECK.json"
FACES_FILE = "SET-FACES.jpg"   # each variant's face next to the face references, for the eye


def settings(pack=None) -> dict[str, Any]:
    if pack is None:
        from .. import brand
        pack = brand.load()
    own = pack.value("thumbnail.formats", {}) or {}
    return {**DEFAULTS, **{k: v for k, v in own.items() if k in DEFAULTS}}


# ---------------------------------------------------------------- images

def _load(path: str | Path, size: tuple[int, int]) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB").resize(size, Image.BILINEAR), dtype=np.float32) / 255.0


def _gray(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * np.sqrt(2 / n)
    m[0] /= np.sqrt(2)
    return m


def phash(path: str | Path) -> int:
    """64-bit perceptual hash: the 8x8 lowest frequencies of a 32x32 DCT, each bit above or below their median."""
    g = _gray(_load(path, (32, 32)))
    c = _dct_matrix(32)
    low = (c @ g @ c.T)[:8, :8].ravel()
    bits = low > np.median(low[1:])
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def layout_vector(path: str | Path) -> np.ndarray:
    """Where the bright, dark and busy parts sit: a 32x18 brightness grid and a 16x9 edge grid, each standardised."""
    g = _gray(_load(path, (128, 72)))
    small = g.reshape(18, 4, 32, 4).mean(axis=(1, 3))
    gy, gx = np.gradient(g)
    edges = np.hypot(gx, gy).reshape(9, 8, 16, 8).mean(axis=(1, 3))

    def z(v: np.ndarray) -> np.ndarray:
        v = v.ravel()
        return (v - v.mean()) / (v.std() + 1e-6)
    return np.concatenate([z(small), z(edges)])


def layout_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(max(0.0, np.corrcoef(a, b)[0, 1]))


def colour_histogram(path: str | Path) -> np.ndarray:
    """12 hues x 3 saturations x 3 values; grey pixels (low saturation) go into 3 value bins of their own."""
    rgb = _load(path, (160, 90)).reshape(-1, 3)
    mx, mn = rgb.max(1), rgb.min(1)
    d = mx - mn
    sat = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb.T
    hue = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    hue[rm] = ((g - b)[rm] / d[rm]) % 6
    hue[gm] = (b - r)[gm] / d[gm] + 2
    hue[bm] = (r - g)[bm] / d[bm] + 4
    hue = hue / 6.0
    vbin = np.minimum((mx * 3).astype(int), 2)
    grey = sat < 0.15
    hbin = np.minimum((hue * 12).astype(int), 11)
    sbin = np.minimum(((sat - 0.15) / 0.85 * 3).astype(int), 2)
    idx = np.where(grey, 108 + vbin, (hbin * 3 + sbin) * 3 + vbin)
    hist = np.bincount(idx, minlength=111).astype(np.float64)
    return hist / hist.sum()


def colour_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.minimum(a, b).sum())


def fingerprint(path: str | Path) -> dict[str, Any]:
    return {"phash": phash(path), "layout": layout_vector(path), "colour": colour_histogram(path)}


def compare(a: dict, b: dict, cfg: dict | None = None) -> dict[str, Any]:
    cfg = {**DEFAULTS, **(cfg or {})}
    dist = hamming(a["phash"], b["phash"])
    lay = layout_similarity(a["layout"], b["layout"])
    col = colour_similarity(a["colour"], b["colour"])
    reasons = []
    if dist < cfg["phash_min_distance"]:
        reasons.append(f"nearly the same picture (hashes {dist} of 64 bits apart, needs {cfg['phash_min_distance']})")
    if lay >= cfg["layout_max"]:
        reasons.append(f"the same composition (layout {lay:.2f}, at most {cfg['layout_max']:.2f})")
    if col >= cfg["colour_max"]:
        reasons.append(f"the same colours (colour {col:.2f}, at most {cfg['colour_max']:.2f})")
    return {"phash_distance": dist, "layout": round(lay, 3), "colour": round(col, 3), "too_similar": bool(reasons),
            "reasons": reasons}


def _pack_colour(pack, name):
    if isinstance(name, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", name):
        return name
    v = pack.value(f"brand.colors.{name}") if name else None
    return v if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None


def palette_report(path: str | Path, pack) -> dict[str, Any] | None:
    """Main colour share and brand marker share of one image (`thumbnail.palette`); None when the pack sets none."""
    from PIL import Image

    from ..render.measure import accent_mask
    main = _pack_colour(pack, pack.value("thumbnail.palette.main"))
    marker = _pack_colour(pack, pack.value("thumbnail.palette.marker"))
    span = pack.value("thumbnail.palette.marker_share")
    limits = [x for x in (pack.value("thumbnail.palette.limits") or []) if isinstance(x, dict)]
    if not main and not marker and not limits:
        return None
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB").resize((320, 180), Image.BILINEAR), dtype=np.float32)
    out: dict[str, Any] = {"problems": []}
    if main:
        out["main_share"] = round(float(accent_mask(arr, main, 14.0, 0.5).mean()), 4)
    if marker:
        share = float(accent_mask(arr, marker, 16.0, 0.45).mean())
        out["marker_share"] = round(share, 4)
        if isinstance(span, (list, tuple)) and len(span) == 2:
            lo, hi = float(span[0]), float(span[1])
            if share < lo:
                out["problems"].append(f"the brand marker ({marker}) is missing ({share:.2%}, at least {lo:.1%})")
            elif share > hi:
                out["problems"].append(f"the brand marker colour covers {share:.1%}; it stays a small marker "
                                       f"(at most {hi:.0%})")
    out["warnings"] = []
    for x in limits:
        colour = _pack_colour(pack, x.get("colour"))
        if not colour:
            continue
        share = float(accent_mask(arr, colour, 16.0, 0.45).mean())
        most = float(x.get("max_share", 0.01))
        if share > most:
            out["warnings"].append(f"{x.get('name') or colour} covers {share:.1%} (at most {most:.0%})")
    return out


# ---------------------------------------------------------------- plan

def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", str(text).lower()))


def same_idea(a: str, b: str, threshold: float) -> bool:
    """Two hook values count as the same idea when their word sets overlap by `threshold` or more (Jaccard)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= threshold


def is_control(v: dict) -> bool:
    return str(v.get("role") or "").lower() == "control"


def finalists(plan: dict, cfg: dict) -> tuple[list[str], list[str]]:
    """The finalists for one YouTube test and the reserve. Without a list: the control first, then in order."""
    variants = plan.get("variants") or []
    labels = [str(v.get("label") or i + 1) for i, v in enumerate(variants)]
    fin = [str(x) for x in plan.get("finalists") or []]
    if not fin:
        ctrl = [lbl for lbl, v in zip(labels, variants, strict=True) if is_control(v)]
        fin = (ctrl + [lbl for lbl in labels if lbl not in ctrl])[: cfg["per_set"]]
        fin = [lbl for lbl in labels if lbl in fin]
    return fin, [lbl for lbl in labels if lbl not in fin]


def check_plan(plan: dict, library: dict[str, dict], cfg: dict | None = None) -> list[str]:
    cfg = {**DEFAULTS, **(cfg or {})}
    problems: list[str] = []
    variants = plan.get("variants") or []
    most = max(cfg["per_set"], cfg["max_candidates"])
    if not cfg["per_set"] <= len(variants) <= most:
        problems.append(f"The set has {len(variants)} variants; it needs {cfg['per_set']}"
                        + (f" to {most}" if most > cfg["per_set"] else " exactly") + ".")
    labels = [str(v.get("label") or i + 1) for i, v in enumerate(variants)]
    controls = [lbl for lbl, v in zip(labels, variants, strict=True) if is_control(v)]
    if len(controls) > cfg["max_control"]:
        problems.append(f"{len(controls)} control variants ({', '.join(controls)}); at most {cfg['max_control']}.")
    fin = plan.get("finalists")
    if fin is not None:
        if len(fin) != min(cfg["per_set"], len(variants)) or not set(map(str, fin)) <= set(labels):
            problems.append(f"finalists must name {cfg['per_set']} of the variants ({', '.join(labels)}).")
    elif len(variants) > cfg["per_set"]:
        problems.append(f"The set has more than {cfg['per_set']} variants: name the {cfg['per_set']} finalists "
                        "for the test in SET.json (\"finalists\"); the rest is the reserve.")
    kinds = []
    for label, v in zip(labels, variants, strict=True):
        fid = v.get("format")
        f = library.get(fid) if fid else None
        if not f and not (is_control(v) and not fid):
            problems.append(f"{label}: format {fid!r} is not in the format library (crewcut thumbnail formats).")
        kinds.append(None if is_control(v) else (f or {}).get("kind"))
        hook = v.get("hook") or {}
        missing = [k for k in HOOK_FIELDS if not str(hook.get(k) or "").strip()]
        if missing:
            problems.append(f"{label}: the hook needs {', '.join(missing)}.")
    formats = [v.get("format") for v in variants if not is_control(v)]
    if len(set(formats)) != len(formats):
        problems.append("Two variants use the same format; every variant needs its own format.")
    if kinds.count("house") < cfg["min_house"]:
        problems.append(f"At least {cfg['min_house']} variant(s) must use a house format (the channel's own style).")
    if kinds.count("pro") < cfg["min_pro"]:
        problems.append(f"At least {cfg['min_pro']} variant(s) must use a pro format from the library.")
    for (la, va), (lb, vb) in combinations(zip(labels, variants, strict=True), 2):
        ha, hb = va.get("hook") or {}, vb.get("hook") or {}
        same = [k for k in HOOK_FIELDS if ha.get(k) and hb.get(k) and same_idea(ha[k], hb[k], cfg["same_words"])]
        if same:
            problems.append(f"{la} and {lb} share the same {', '.join(same)}; change the hook, not only details.")
    return problems


# ---------------------------------------------------------------- the round

def read_plan(round_dir: Path) -> dict:
    p = round_dir / SET_FILE
    if not p.is_file():
        raise FileNotFoundError(f"No {SET_FILE} in {round_dir.name}.")
    return json.loads(p.read_text(encoding="utf-8"))


def references_used(round_dir: Path, v: dict) -> dict[str, Any] | None:
    """Which images a variant was made from: SET.json `references`, else the run of `crewcut thumbnail make` in the
    variant folder (REFERENCES.json) that made this image, else its last run."""
    if v.get("references"):
        return {"source": "SET.json", "references": v["references"]}
    img = round_dir / str(v.get("image") or "")
    f = img.parent / "REFERENCES.json"
    if not f.is_file():
        return None
    runs = json.loads(f.read_text(encoding="utf-8")).get("runs") or []
    run = next((r for r in reversed(runs) if img.name in (r.get("images") or [])), runs[-1] if runs else None)
    if not run:
        return None
    return {"source": "make" if img.name in (run.get("images") or []) else "make (last run, image renamed)",
            "format": run.get("format"), "references": run.get("references") or []}


def reference_problem(label: str, v: dict, used: dict | None, library: dict[str, dict]) -> str | None:
    f = library.get(v.get("format")) or {}
    if used is None or is_control(v) or f.get("kind") != "pro":
        return None
    roles = {r.get("role") for r in used.get("references") or [] if isinstance(r, dict)}
    if "layout" not in roles:
        return (f"{label}: made without the example image of its pro format {v.get('format')!r}"
                + (" (with the house style reference instead)" if roles & {"style", "control"} else "")
                + "; make it again with `crewcut thumbnail make` so the format example is attached")
    return None


def check_round(round_dir: Path, library: dict[str, dict], cfg: dict | None = None,
                images: bool = True, pack=None, gate=None) -> dict[str, Any]:
    """Check plan and images of one round; write SET-CHECK.json next to SET.json. Images may be missing while the
    round is only planned: then `ok` covers the plan and `images_ready` is false. With a pack that has face
    references the identity gate runs on every variant with a person (`gate` replaces it in tests)."""
    cfg = {**DEFAULTS, **(cfg or {})}
    plan = read_plan(round_dir)
    problems = check_plan(plan, library, cfg)
    variants = plan.get("variants") or []
    labels = [str(v.get("label") or i + 1) for i, v in enumerate(variants)]
    pairs, redo, missing = [], [], []
    prints: dict[str, dict] = {}
    palette: dict[str, dict] = {}
    faces: dict[str, dict] = {}
    refs: dict[str, Any] = {}
    warnings: list[str] = []
    gate_error = None
    if images and gate is None and pack is not None:
        from . import identity
        if identity.enabled(pack):
            try:
                gate = identity.Gate.for_pack(pack)
            except identity.Unavailable as e:
                gate_error = str(e)

    def mark(label):
        if label not in redo:
            redo.append(label)
    if images:
        for label, v in zip(labels, variants, strict=True):
            img = round_dir / str(v.get("image") or "")
            refs[label] = references_used(round_dir, v)
            why = reference_problem(label, v, refs[label], library)
            if why:
                problems.append(why + ".")
                mark(label)
            if v.get("image") and img.is_file():
                prints[label] = fingerprint(img)
                rep = palette_report(img, pack) if pack is not None and not is_control(v) else None
                if rep:
                    palette[label] = rep
                    problems += [f"{label}: {p}." for p in rep["problems"]]
                    warnings += [f"{label}: {w}." for w in rep.get("warnings", [])]
                    if rep["problems"]:
                        mark(label)
                if v.get("face", True) is not False and (gate is not None or gate_error):
                    if gate_error:
                        faces[label] = {"ok": False, "problem": f"the identity check could not run: {gate_error}"}
                    else:
                        faces[label] = gate.measure(img)
                    if not faces[label]["ok"]:
                        problems.append(f"{label}: {faces[label]['problem']}. Make it again with more face "
                                        "references; after repeated failures use the real-photo fallback.")
                        mark(label)
            else:
                missing.append(label)
        shown = [(lbl, round_dir / str(v.get("image")), faces[lbl].get("box"), faces[lbl].get("similarity"))
                 for lbl, v in zip(labels, variants, strict=True) if faces.get(lbl, {}).get("box")]
        if shown and gate is not None and getattr(gate, "ref_paths", None):
            from . import identity
            try:
                identity.face_sheet(round_dir / FACES_FILE, shown, gate.ref_paths[:2], gate.embed)
            except OSError:
                pass
        for la, lb in combinations([lbl for lbl in labels if lbl in prints], 2):
            c = compare(prints[la], prints[lb], cfg)
            pairs.append({"a": la, "b": lb, **c})
            if c["too_similar"]:
                problems.append(f"{la} and {lb} look too similar: {'; '.join(c['reasons'])}. Make {lb} again with a "
                                "new complete prompt in another format and hook.")
                if lb not in redo:
                    redo.append(lb)
    fin, reserve = finalists(plan, cfg)
    result = {"ok": not problems, "images_ready": images and not missing, "missing_images": missing,
              "problems": problems, "warnings": warnings, "redo": redo, "pairs": pairs, "palette": palette,
              "identity": faces,
              "references": refs,
              "formats": {lbl: v.get("format") for lbl, v in zip(labels, variants, strict=True)},
              "control": [lbl for lbl, v in zip(labels, variants, strict=True) if is_control(v)],
              "finalists": fin, "reserve": reserve,
              "settings": {k: cfg[k] for k in DEFAULTS}}
    (round_dir / CHECK_FILE).write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _round_dir(a) -> tuple[str, Path]:
    import os

    from .. import paths
    episode = a.episode or os.environ.get("CREWCUT_EPISODE")
    if not episode:
        raise ValueError("Which episode? Use --episode.")
    return episode, paths.inside(paths.episode_dir(episode), a.round)


def card_variants(round_dir: Path, plan: dict, library: dict[str, dict], episode_dir: Path,
                  check: dict | None = None, control_name: str = "control") -> list[dict]:
    """What the thumbnail card shows: each image with its label, format name, role, references and face score."""
    check = check or {}
    fin = set(check.get("finalists") or finalists(plan, {**DEFAULTS})[0])
    out = []
    for i, v in enumerate(plan.get("variants") or []):
        label = str(v.get("label") or i + 1)
        f = library.get(v.get("format"), {})
        img = round_dir / str(v.get("image") or "")
        name = f.get("name", v.get("format")) or ""
        if is_control(v):
            name = f"{control_name}: {name}" if name else control_name
        used = (check.get("references") or {}).get(label) or {}
        out.append({"label": label, "format": v.get("format"), "format_name": name,
                    "kind": "control" if is_control(v) else f.get("kind"),
                    "role": "control" if is_control(v) else "variant", "finalist": label in fin,
                    "image": img.relative_to(episode_dir).as_posix() if img.is_file() else None,
                    "text": (v.get("hook") or {}).get("text"),
                    "references": [f"{r.get('file')} ({r.get('role')})" for r in used.get("references") or []
                                   if isinstance(r, dict)],
                    "face_similarity": ((check.get("identity") or {}).get(label) or {}).get("similarity")})
    return out


def cli(a) -> int:
    from .. import approvals, brand, paths
    from . import formats
    try:
        episode, round_dir = _round_dir(a)
        pack = brand.load()
        library = formats.load(pack)
        result = check_round(round_dir, library, settings(pack), images=not getattr(a, "plan_only", False),
                             pack=pack)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(str(e))
        return 2
    if a.setcmd == "check":
        if getattr(a, "json", False):
            print(json.dumps(result, indent=1, ensure_ascii=False))
        else:
            for label, rep in result["palette"].items():
                print(f"{label}: main colour {rep.get('main_share', 0):.1%}, brand marker {rep.get('marker_share', 0):.2%}")
            for label in result["control"]:
                print(f"{label}: control variant (proven channel style), palette rules not applied")
            for label, rep in result["identity"].items():
                sim = rep.get("similarity")
                print(f"{label}: face " + ("-" if sim is None else f"{sim:.2f}") + (" OK" if rep["ok"] else " WRONG"))
            for label, used in result["references"].items():
                if used:
                    print(f"{label}: made from " + ", ".join(f"{r.get('file')} ({r.get('role')})"
                                                             for r in used["references"] if isinstance(r, dict)))
                else:
                    print(f"{label}: references unknown (no REFERENCES.json)")
            for p in result["pairs"]:
                print(f"{p['a']}-{p['b']}: hash distance {p['phash_distance']}, layout {p['layout']:.2f}, colour "
                      f"{p['colour']:.2f}" + ("  TOO SIMILAR" if p["too_similar"] else ""))
            for line in result["problems"]:
                print(f"PROBLEM {line}")
            for line in result["warnings"]:
                print(f"WARNING {line}")
            if result["missing_images"]:
                print(f"Not made yet: {', '.join(result['missing_images'])} (the plan was checked).")
            print("OK: real variety." if result["ok"] else f"NOT OK. Redo: {', '.join(result['redo']) or 'the plan'}.")
        return 0 if result["ok"] else 1
    # card: only for a complete set that passed
    if not result["ok"] or not result["images_ready"]:
        print("No card: the set must pass `crewcut thumbnail set check` with all images made.")
        for line in result["problems"]:
            print(f"PROBLEM {line}")
        return 1
    ep = paths.episode_dir(episode)
    plan = read_plan(round_dir)
    variants = card_variants(round_dir, plan, library, ep, result,
                             str(pack.value("thumbnail.control.name") or "control"))
    title = a.title or "Thumbnail test: " + ", ".join(f"{v['label']} {v['format_name']}" for v in variants)
    body = a.body or ""
    if result["reserve"]:
        body = (body + "\n\n" if body else "") + (f"Suggested for the test: {', '.join(result['finalists'])}. "
                                                    f"Reserve for a second round: {', '.join(result['reserve'])}.")
    card = approvals.propose(episode, "thumbnail", "thumbnail", title, body=body,
                             file=(round_dir / SET_FILE).relative_to(ep).as_posix(),
                             options=[f"{v['label']} · {v['format_name']}" + ("" if v["finalist"] else " (reserve)")
                                      for v in variants],
                             data={"variants": variants, "finalists": result["finalists"], "reserve": result["reserve"],
                                   "set_check": (round_dir / CHECK_FILE).relative_to(ep).as_posix()},
                             preview=a.preview)
    print(f"card #{card['id']}")
    return 0
