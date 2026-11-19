"""Custom motion: a graphic made for one video, the way the launch film was made (motion plan 3.3).

``crewcut motion new <episode> <insert-id> --from brief.md`` makes the piece's folder in the episode::

    motion/<insert-id>/
      brief.md     the sentence(s), what must be understood in 2 s, format(s), length (from --from)
      beats.md     beat sheet in local seconds: | beat | time | content | exit motion |
      refs/        reference clips or stills (timing and look only; never in the output, never uploaded)
      review/      review bundles of this piece
      notes.md     per round: what the reference still does better, what was changed
      comp.jsx     the comp: a template header and one function; it starts as a ground with a slow push

The plan names it with ``"source": "motion/<insert-id>/comp.jsx"`` and it renders through the same code as a library
template. ``crewcut motion style-frame`` opens the ``style-frame`` card (our frame next to the reference, per format);
nothing animated is built before its yes (``style_frame_gate``).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .. import brand, paths
from . import library

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
FORMAT_OF = (("landscape", 1.5), ("portrait", 0.67))
IMAGES = (".png", ".jpg", ".jpeg", ".webp")


class CustomError(ValueError):
    """The custom piece cannot be made. The message says what to change."""


def piece_dir(episode: str, insert_id: str) -> Path:
    if not ID.match(insert_id):
        raise CustomError(f"insert id {insert_id!r}: lower case letters, digits, - and _ (up to 40)")
    return paths.episode_dir(episode) / "motion" / insert_id


def function_name(insert_id: str) -> str:
    """A JavaScript name for the comp's function: ``gpu-handoff`` -> ``gpu_handoff``, ``3d`` -> ``c_3d``."""
    n = re.sub(r"[^A-Za-z0-9_]", "_", insert_id)
    return n if re.match(r"[A-Za-z_]", n) else f"c_{n}"


def skeleton_source(insert_id: str, episode: str, brief_line: str = "") -> str:
    """The comp skeleton: the full header and a valid empty piece (the pack's ground and a slow push) in both
    formats. Sizes come from ``CC.frame()``, colours from ``CC.*``; nothing is written for one format."""
    fn = function_name(insert_id)
    desc = " ".join((brief_line or f"Custom motion for {episode}, insert {insert_id}").split())[:160]
    return f"""/* @template {fn}
 * @description {desc}
 * @kind full
 * @formats ["landscape", "portrait"]
 * @version 1
 * @params {{"comp": "Main"}}
 * @end */
// Custom motion for {episode}, insert {insert_id}. Brief: brief.md. Beat sheet: beats.md (local seconds).
// Every size comes from CC.frame() (u = short side / 1080), every colour and font from CC.*, times are seconds local
// to the insert. Texts, numbers and cue times arrive as @params with a default, so the piece can join the library
// later (crewcut motion promote) without a rewrite.
function {fn}(P) {{
  var c = P.comp, F = CC.frame(), K = CC.ctx();
  // the stage: one null in the middle of the frame carries everything, so one slow push moves it all
  var stage = EC.nul(c, {{name: "stage"}});
  EC.set(c, stage, "transform/position", [F.W / 2, F.H / 2]);
  function onStage(id, x, y) {{
    EC.run("layer.setParent", {{comp: c, layers: [id], parent: stage, compensate: false}});
    EC.set(c, id, "transform/position", [x - F.W / 2, y - F.H / 2]);
    return id;
  }}
  // the ground from the pack, larger than the frame so the push never shows an edge
  var ground = onStage(EC.solid(c, {{name: "ground", color: CC.ground(), w: Math.ceil(F.W * 1.3),
                                     h: Math.ceil(F.H * 1.3)}}), F.W / 2, F.H / 2);
  // one soft light from the palette, so the push reads on the empty ground; the piece replaces it
  var d = Math.round(Math.max(F.W, F.H) * 0.8);
  var light = onStage(EC.shape(c, {{kind: "ellipse", name: "light", size: [d, d], fill: CC.pastel(1)}}),
                      F.W * 0.68, F.H * 0.36);
  EC.set(c, light, "transform/opacity", 60);
  // the camera never stops: a slow linear push over the whole insert (the pack's drift per second)
  var end = 100 * (1 + CC.mg().drift_pct_per_s / 100 * K.duration);
  EC.keys(c, stage, "transform/scale", [[0, [100, 100]], [K.duration, [end, end]]], "linear");
  return {{comp: c, layers: [stage, ground, light]}};
}}
"""


BEATS_MD = """# Beat sheet: {iid}

Local seconds (0 = the first frame of the insert). Every transition is caused by a motion; the camera never stops.
Reference timing measured at 60 fps when a reference exists (refs/).

| beat | time | content | exit motion |
|---|---|---|---|
| 1 | 0.0 | | |
"""

NOTES_MD = """# Notes: {iid}

Per review round: what the reference still does better, what was changed.
"""


def _read_brief(src: str | Path, ep_dir: Path) -> str:
    p = Path(src).expanduser()
    for cand in (p, ep_dir / p, paths.studio_root() / p):
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    raise CustomError(f"brief not found: {src}")


def new(episode: str, insert_id: str, brief_from: str | Path) -> Path:
    """Make ``motion/<insert-id>/`` with the brief, the beat sheet, refs/, review/, notes and the comp skeleton.
    Refuses when the piece exists already. Returns the folder."""
    d = piece_dir(episode, insert_id)
    ep_dir = d.parent.parent
    if not (ep_dir / "project.json").is_file():
        raise CustomError(f"no episode {episode}")
    if (d / "comp.jsx").exists():
        raise CustomError(f"motion/{insert_id}/comp.jsx exists already; it is never overwritten")
    brief = _read_brief(brief_from, ep_dir)
    if not brief.strip():
        raise CustomError("the brief is empty: the sentence(s), what must be understood in 2 s, formats, length")
    first = next((x.strip("# ").strip() for x in brief.splitlines() if x.strip()), "")
    for sub in ("refs", "review"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "brief.md").write_text(brief if brief.endswith("\n") else brief + "\n", encoding="utf-8")
    for name, text in (("beats.md", BEATS_MD), ("notes.md", NOTES_MD)):
        if not (d / name).exists():
            (d / name).write_text(text.format(iid=insert_id), encoding="utf-8")
    (d / "comp.jsx").write_text(skeleton_source(insert_id, episode, first), encoding="utf-8")
    return d


# ---------------------------------------------------------------- the style frame card


def image_format(p: Path) -> str:
    from PIL import Image
    with Image.open(p) as im:
        w, h = im.size
    r = w / h
    return "landscape" if r >= FORMAT_OF[0][1] else ("portrait" if r <= FORMAT_OF[1][1] else "stage")


def _find(src: str | Path, ep_dir: Path) -> Path:
    p = Path(src).expanduser()
    for cand in (p, ep_dir / p, paths.studio_root() / p):
        if cand.is_file():
            return cand.resolve()
    raise CustomError(f"not found: {src}")


def _inside(p: Path, root: Path) -> bool:
    return root.resolve() in p.resolve().parents


def _fallback_refs(ep_dir: Path, d: Path) -> list[tuple[Path, str]]:
    """Without ``--ref``: the newest still in the piece's refs/, else the bar's motion frames."""
    stills = sorted((f for f in (d / "refs").glob("*") if f.suffix.lower() in IMAGES), key=lambda f: f.stat().st_mtime)
    if stills:
        return [(stills[-1], "reference")]
    from .. import brand
    pack = brand.load()
    out = []
    for fr in ((pack.value("baseline.motion", {}) or {}).get("frames") or []):
        rel = fr.get("file") if isinstance(fr, dict) else fr
        if isinstance(rel, str):
            for root in (Path(pack.dir), paths.studio_root()):
                if (root / rel).is_file():
                    out.append((root / rel, "the bar"))
                    break
    return out


def style_frame(episode: str, insert_id: str, ours: list[str], refs: list[str] | None = None,
                natural: bool = False, identity: str | None = None, craft_review: str | None = None) -> dict:
    """Open the ``style-frame`` card: our frame of the strongest moment next to the reference (or the library
    sample, or the bar), per format. Our frames are kept as ``frame-v<N>-<format>.png`` in the piece's folder;
    references from outside the episode are copied into its ``refs/``. Refuses a frame that fails the hue check
    (one hue above 30 % of the coloured pixels) unless ``natural``."""
    from .. import approvals
    from . import palette
    d = piece_dir(episode, insert_id)
    ep_dir = d.parent.parent
    if not d.is_dir():
        raise CustomError(f"no custom piece {insert_id}: run `crewcut motion new {episode} {insert_id} --from <brief>`")
    if not ours:
        raise CustomError("give our frame with --ours (one per format the piece needs)")
    from . import quality
    craft = None
    if quality.required() or craft_review:
        if not craft_review:
            raise CustomError("Have a separate Critic compare the frame with the channel benchmarks; supply --craft-review.")
        craft = quality.validate_report(episode, craft_review, [_find(src, ep_dir) for src in ours], submit=True)
        benchmark = next(b for b in quality.catalog()["benchmarks"] if b["id"] == craft["benchmark"])
        refs = [str(quality.asset(benchmark["frame"])), *(refs or [])]
    rnd = 1 + max([int(m.group(1)) for f in d.glob("frame-v*") if (m := re.match(r"frame-v(\d+)", f.name))], default=0)
    frames: dict[str, dict] = {}
    for src in ours:
        p = _find(src, ep_dir)
        fmt = image_format(p)
        if fmt in frames:
            raise CustomError(f"two of our frames are {fmt}; give one per format")
        hue = palette.hue_report(str(p), accent_area_limit=brand.load().motion_graphics().get("accent_area_limit", 0.0))
        if not hue["ok"] and not natural:
            raise CustomError(f"{p.name}: one hue holds {hue['dominant_share']:.0%} of the coloured pixels (at most "
                              "30 %); rework the colours, or pass --natural for grass, sky or footage")
        target = d / f"frame-v{rnd}-{fmt}{p.suffix.lower()}"
        if p != target.resolve():
            shutil.copy2(p, target)
        frames[fmt] = {"format": fmt, "ours": target.relative_to(ep_dir).as_posix(),
                       "hue": {k: hue[k] for k in ("dominant_share", "ok", "coloured_share", "accent_area_limit", "sparse_accent") if k in hue}}
    ref_list: list[tuple[Path, str]] = []
    for src in refs or []:
        p = _find(src, ep_dir)
        if not _inside(p, ep_dir):
            target = d / "refs" / p.name
            if not target.exists():
                shutil.copy2(p, target)
            p = target
        ref_list.append((p, "reference"))
    if not ref_list:
        ref_list = _fallback_refs(ep_dir, d)
    for fr in frames.values():
        match = [r for r in ref_list if r[0].suffix.lower() in IMAGES and image_format(r[0]) == fr["format"]]
        pick = (match or ref_list or [None])[0]
        if pick is None:
            fr.update(ref=None, ref_label="no reference: say what it should beat")
            continue
        rp, label = pick
        fr["ref"] = rp.relative_to(ep_dir).as_posix() if _inside(rp, ep_dir) else None
        fr["ref_url"] = library.file_url(rp)
        fr["ref_label"] = label
    for fr in frames.values():
        fr["ours_url"] = f"/api/files/{episode}/{fr['ours']}"
        if fr.get("ref"):
            fr["ref_url"] = f"/api/files/{episode}/{fr['ref']}"
    order = [f for f in ("landscape", "portrait", "stage") if f in frames]
    first = frames[order[0]]
    images = [u for fr in (frames[f] for f in order) for u in (fr["ours_url"], fr.get("ref_url")) if u][:3]
    return approvals.propose(
        episode, "edit", "style-frame", f"Style frame of {insert_id}, round {rnd}",
        body=("Our frame of the strongest moment next to the reference" + (", per format" if len(order) > 1 else "")
              + ". Nothing animated is built before your yes; a note goes back to the Designer."),
        file=first["ours"], data={"insert": insert_id, "round": rnd, "frames": [frames[f] for f in order],
                                  "images": images, **({"craft_review": craft} if craft else {})},
        identity=identity or "designer")


def style_frame_gate(episode_dir: Path | str, insert_id: str) -> str | None:
    """Exit-3 reason while the style frame of custom insert ``insert_id`` is not accepted (None: it may be built).
    The render path calls it for inserts with ``source`` (custom pieces) before rendering the animation; tests skip
    it with ``--no-gate``."""
    from .. import approvals
    ep = Path(episode_dir).name
    cards = [c for c in approvals.list_cards(episode=ep) if c["kind"] == "style-frame"
             and (c.get("data") or {}).get("insert") == insert_id]
    if not cards:
        return (f"{insert_id}: no style frame card yet. One real frame of the strongest moment first "
                f"(`crewcut motion style-frame {ep} {insert_id} --ours <frame>`); nothing animated before its yes.")
    last = cards[-1]
    if last["status"] == "accepted":
        return None
    if last["status"] == "open":
        return f"{insert_id}: waiting for your yes on the style frame (card #{last['id']}); nothing animated before it."
    return (f"{insert_id}: the style frame got a note (card #{last['id']}): make a new frame and a new card first. "
            f"Note: {last.get('reason') or 'see the chat'}")


def pieces_state(ep_dir: Path) -> dict[str, str]:
    """State of each custom piece of the episode: planned, style frame, building, in review, done."""
    from .. import approvals
    out: dict[str, str] = {}
    cards = approvals.list_cards(episode=ep_dir.name)
    for d in sorted((ep_dir / "motion").glob("*/comp.jsx")) if (ep_dir / "motion").is_dir() else []:
        iid = d.parent.name
        sf = [c for c in cards if c["kind"] == "style-frame" and (c.get("data") or {}).get("insert") == iid]
        bundle, errors = library.last_bundle(ep_dir, iid)
        if not sf:
            out[iid] = "planned"
        elif sf[-1]["status"] != "accepted":
            out[iid] = "style frame"
        elif bundle is not None and not errors:
            out[iid] = "done"
        elif bundle is not None:
            out[iid] = "in review"
        else:
            out[iid] = "building"
    return out
