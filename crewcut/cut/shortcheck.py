"""The Critic's rule set for Shorts. The long-video rules give about ten false errors on every Short.

  crewcut cut short-check <video> [--cut work/short-cut-vNNN.json] [--plan edit/plan-vNNN.json] [--json]

<video> is the rendered Short or the rough cut (work/speaker-vNNN.mov), inside the short's episode folder. The cut
report of `crewcut cut short` (face per piece, piece edges, the voice) is found from the plan's base or the video's
version; the edit plan is the one whose output is the video. Values come from the style pack (edit-style.json
"shorts"; true_peak_db from the main block).

Rules:
  format      9:16 (error); smaller than 1080x1920 (warning)
  length      inside shorts.length_s (warning outside); over 180 s it is no Short (error)
  face        every piece's face inside the frame (error when the centre is in the outer 12 %), not under the buttons
              in the right right_free_frac (warning); a face that was only guessed (warning)
  text        no text overlay over the face (error), none reaching into the right right_free_frac (error). The
              overlay box is estimated from the plan's data (keyword chips: x, y, text length) and the face box is a
              fixed share of the frame around the face centre: an approximation, the contact sheet is the proof.
  text cards  at most shorts.text_cards_max cards that must be read (headline, post) (error)
  brightness  mean luma (8-bit, video range) of frames sampled 5 times a second >= shorts.min_mean_luma (error)
  still       no frozen picture longer than shorts.max_still_s (error); no shot longer than that without a cut, an
              insert or a zoom (warning: the pace)
  loudness    integrated within 1 LU of shorts.loudness_lufs (up to 2 LU: warning, with the headroom hint), true peak
              <= true_peak_db (error)
  edges       the level just inside every piece edge, on the Short's clean voice: sound there means a foreign
              syllable or a clipped word (warning, and on the listening list)
  end         at most end_tail_s + 0.5 s after the last word (warning)
Writes review/short-check-<video name>.json and .jpg (a contact sheet of 24 frames) and prints a "please listen" list
with times: nobody but the human hears the sound. Exit 2 when there is an error.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import audio, media
from .common import CutError, inside, read_json, rel, write_replace
from .short import edge_levels, levels_of, newest

SAMPLE_FPS = 5
SAMPLE_SIZE = (36, 64)        # tiny frames: enough for brightness and change, cheap to read
SHEET = (6, 4)                # columns, rows: 24 frames
CELL = (180, 320)
FROZEN_DIFF = 0.15            # mean absolute luma change between samples below this: the picture stands still
CUT_DIFF = 8.0                # above this: a hard change of picture
FACE_BOX = (0.32, 0.22)       # face box as a share of the 9:16 frame (head and shoulders shot)
FACE_EDGE = 0.12
SHORT_MAX_S = 180.0
TEXT_SCENES_FALLBACK = ("headline", "post")


def text_scenes() -> tuple[str, ...]:
    try:
        from ..render.plan import TEXT_SCENES
        return tuple(TEXT_SCENES)
    except ImportError:
        return TEXT_SCENES_FALLBACK


def settings() -> dict:
    from .. import brand
    try:
        pack = brand.load()
    except Exception:  # a broken pack must not stop the check; brand check reports it
        pack = None

    def v(key: str, default):
        return pack.value(key, default) if pack else default
    s = v("edit_style.shorts", {}) or {}
    return {"length_s": list(s.get("length_s") or [30, 50]), "max_still_s": float(s.get("max_still_s", 2.5)),
            "text_cards_max": int(s.get("text_cards_max", 3)),
            "loudness_lufs": float(s.get("loudness_lufs", v("edit_style.loudness_lufs", -14.0))),
            "limiter_headroom_db": float(s.get("limiter_headroom_db", 1.4)),
            "true_peak_db": float(v("edit_style.true_peak_db", -1.5)),
            "right_free_frac": float(s.get("right_free_frac", 0.18)),
            "min_mean_luma": float(s.get("min_mean_luma", 40)), "end_tail_s": float(s.get("end_tail_s", 1.0))}


# ---- pure rules --------------------------------------------------------------------------------------------------
def format_findings(w: int, h: int, seconds: float, s: dict) -> list[dict]:
    out = []
    if abs(w / h - 9 / 16) > 0.01:
        out.append(f_("error", "format", f"the picture is {w}x{h}, not 9:16"))
    elif w < 1080 or h < 1920:
        out.append(f_("warning", "format", f"the picture is {w}x{h}, smaller than 1080x1920"))
    lo, hi = s["length_s"][:2]
    if seconds > SHORT_MAX_S:
        out.append(f_("error", "length", f"{seconds:.1f} s: over {SHORT_MAX_S:g} s YouTube treats it as a long video"))
    elif not lo <= seconds <= hi:
        out.append(f_("warning", "length", f"{seconds:.1f} s, the style pack wants {lo:g}-{hi:g} s"))
    return out


def f_(level: str, area: str, text: str, at: float | None = None) -> dict:
    d = {"level": level, "area": area, "text": text}
    if at is not None:
        d["at"] = round(at, 2)
    return d


def intervals_minus(a: float, b: float, cover: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """[a, b] without the covered intervals."""
    parts = [(a, b)]
    for x, y in cover:
        nxt = []
        for p, q in parts:
            if y <= p or x >= q:
                nxt.append((p, q))
                continue
            if x > p:
                nxt.append((p, x))
            if y < q:
                nxt.append((y, q))
        parts = nxt
    return [(p, q) for p, q in parts if q - p > 0.04]


def full_frame(inserts: list[dict]) -> list[tuple[float, float]]:
    return [(float(e["start"]), float(e["end"])) for e in inserts if not e.get("transparent")]


def overlay_boxes(e: dict) -> list[dict]:
    """Estimated boxes (shares of the frame) of a text overlay, from the plan's data. Keyword chips only."""
    d = e.get("data") or {}
    fine = d.get("fine") or {}
    size = float(fine.get("size") or 82)
    items = d.get("words") or ([{"text": d["text"]}] if d.get("text") else [])
    out = []
    for it in items:
        text = str(it.get("text") or "")
        if not text:
            continue
        w = min(float(fine.get("max_width") or 0.86), (len(text) * 0.55 * size + size) / 1080)
        h = size * 1.6 / 1920
        x, y = float(it.get("x", 0.5)), float(it.get("y", fine.get("y", 0.68)))
        out.append({"text": text, "box": [x - w / 2, y - h / 2, x + w / 2, y + h / 2]})
    return out


def boxes_overlap(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def face_box(face: list[float]) -> list[float]:
    return [face[0] - FACE_BOX[0] / 2, face[1] - FACE_BOX[1] / 2, face[0] + FACE_BOX[0] / 2, face[1] + FACE_BOX[1] / 2]


def face_findings(pieces: list[dict], inserts: list[dict], s: dict) -> list[dict]:
    out = []
    cover = full_frame(inserts)
    right = 1 - s["right_free_frac"]
    for p in pieces:
        shown = intervals_minus(p["short_from"], p["short_to"], cover)
        if not shown:
            continue
        at = shown[0][0]
        fx, fy = p["face"]
        if p.get("face_from") == "default":
            out.append(f_("warning", "face", f"piece {p['id']}: the face position was guessed (centre); look at the "
                                             "contact sheet", at))
        if not (FACE_EDGE <= fx <= 1 - FACE_EDGE and 0.05 <= fy <= 0.9):
            out.append(f_("error", "face", f"piece {p['id']}: the face sits at the edge of the frame "
                                           f"(x {fx:.2f}, y {fy:.2f}); move the crop", at))
        elif fx > right:
            out.append(f_("warning", "face", f"piece {p['id']}: the face sits under YouTube's buttons (x {fx:.2f})", at))
    return out


def text_findings(pieces: list[dict], inserts: list[dict], s: dict) -> tuple[list[dict], list[str]]:
    out, manual = [], []
    cover = full_frame(inserts)
    right = 1 - s["right_free_frac"]
    for e in inserts:
        if not e.get("transparent"):
            continue
        a, b = float(e["start"]), float(e["end"])
        boxes = overlay_boxes(e)
        if not boxes:
            manual.append(f"overlay {e.get('id')} at {a:.1f} s: its text position is unknown, check it on the "
                          "contact sheet (not over the face, not in the right edge)")
            continue
        for bx in boxes:
            if bx["box"][2] > right:
                out.append(f_("error", "text", f"overlay {e.get('id')} «{bx['text']}» reaches into the right "
                                               f"{s['right_free_frac'] * 100:.0f} % where YouTube's buttons are; shorten it "
                                               "or move it left", a))
            for p in pieces:
                lo, hi = max(a, p["short_from"]), min(b, p["short_to"])
                if hi <= lo or not intervals_minus(lo, hi, cover):
                    continue
                if boxes_overlap(bx["box"], face_box(p["face"])):
                    out.append(f_("error", "text", f"overlay {e.get('id')} «{bx['text']}» lies over the face in piece "
                                                   f"{p['id']}; move it (y) or show it over a full-frame insert", lo))
    for e in inserts:
        if not e.get("transparent") and e.get("kind") == "2d":
            manual.append(f"2D scene {e.get('id')} ({e.get('scene')}) at {float(e['start']):.1f} s: nothing to read "
                          f"in the right {s['right_free_frac'] * 100:.0f} % or the bottom 20 %")
    return out, manual


def card_findings(inserts: list[dict], s: dict) -> list[dict]:
    cards = [e for e in inserts if e.get("scene") in text_scenes()]
    if len(cards) > s["text_cards_max"]:
        return [f_("error", "text cards", f"{len(cards)} text cards ({', '.join(str(e.get('id')) for e in cards)}); "
                                          f"the style pack allows {s['text_cards_max']}. Show a symbol or the proof "
                                          "instead of text")]
    return []


def luma_findings(means: list[float], s: dict, step: float = 1 / SAMPLE_FPS) -> list[dict]:
    """Dark stretches: runs of samples below min_mean_luma."""
    out, start = [], None
    for k, m in enumerate(means + [999.0]):
        if m < s["min_mean_luma"] and start is None:
            start = k
        elif m >= s["min_mean_luma"] and start is not None:
            low = min(means[start:k])
            out.append(f_("error", "brightness", f"too dark from {start * step:.1f} to {k * step:.1f} s (mean luma "
                                                 f"{low:.0f}, at least {s['min_mean_luma']:g}); brighten or replace "
                                                 "the material", start * step))
            start = None
    return out


def still_findings(diffs: list[float], changes: list[float], seconds: float, s: dict,
                   step: float = 1 / SAMPLE_FPS) -> tuple[list[dict], list[dict]]:
    """(findings, shots). Frozen picture from the samples; shots between cuts (pixels) and planned changes."""
    out, run = [], 0
    limit = s["max_still_s"]
    for k, d in enumerate(diffs + [999.0]):
        if d < FROZEN_DIFF:
            run += 1
            continue
        if run * step > limit:
            t0 = (k - run) * step
            out.append(f_("error", "still", f"the picture stands still for {run * step:.1f} s from {t0:.1f} s "
                                            f"(at most {limit:g} s)", t0))
        run = 0
    cuts = [(k + 1) * step for k, d in enumerate(diffs) if d > CUT_DIFF]
    marks = sorted({0.0, round(seconds, 3), *[round(t, 3) for t in cuts + changes if 0 < t < seconds]})
    merged: list[float] = []
    for t in marks:
        if not merged or t - merged[-1] > 0.3:
            merged.append(t)
    shots = [{"from": a, "to": b, "seconds": round(b - a, 2)} for a, b in zip(merged, merged[1:], strict=False)]
    long = [x for x in shots if x["seconds"] > limit]
    if long:
        out.append(f_("warning", "pace", f"{len(long)} shot(s) longer than {limit:g} s without a change, e.g. "
                                         + ", ".join(f"{x['from']:.1f}-{x['to']:.1f} s" for x in long[:4])
                                         + ": add an insert, a zoom or a cut", long[0]["from"]))
    return out, shots


def loudness_findings(m: dict, s: dict) -> list[dict]:
    out = []
    i, tp, target = m.get("integrated_lufs"), m.get("true_peak_dbtp"), s["loudness_lufs"]
    if i is None:
        out.append(f_("error", "loudness", "no loudness measured (no sound?)"))
    else:
        off = i - target
        hint = (f" The final limiter takes about {s['limiter_headroom_db']:g} dB: set the plan's sound lufs that much "
                "above the target." if off < 0 else "")
        if abs(off) > 2:
            out.append(f_("error", "loudness", f"{i:.1f} LUFS, target {target:g}.{hint}"))
        elif abs(off) > 1:
            out.append(f_("warning", "loudness", f"{i:.1f} LUFS, target {target:g}.{hint}"))
    if tp is not None and tp > s["true_peak_db"]:
        out.append(f_("error", "loudness", f"true peak {tp:.1f} dBTP is above {s['true_peak_db']:g} dBTP"))
    return out


def tail_findings(words: list[dict], seconds: float, s: dict) -> list[dict]:
    if not words:
        return []
    last = max(w["e"] for w in words)
    if seconds - last > s["end_tail_s"] + 0.5:
        return [f_("warning", "end", f"the last word ends at {last:.1f} s, then {seconds - last:.1f} s more; end hard "
                                     f"or after about {s['end_tail_s']:g} s", last)]
    return []


# ---- media -------------------------------------------------------------------------------------------------------
def samples_cmd(video: Path) -> list:
    w, h = SAMPLE_SIZE
    return ["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-map", "0:v:0", "-vf",
            f"fps={SAMPLE_FPS},scale={w}:{h}:flags=area,format=yuv420p", "-f", "rawvideo", "-"]


def luma_samples(video: Path):
    """Luma planes (8-bit, video range) of frames sampled SAMPLE_FPS times a second: array (n, h, w)."""
    import numpy as np
    w, h = SAMPLE_SIZE
    raw = media.run(samples_cmd(video), binary=True).stdout
    size = w * h * 3 // 2
    n = len(raw) // size
    frames = np.frombuffer(raw[:n * size], dtype=np.uint8).reshape(n, size)[:, :w * h]
    return frames.reshape(n, h, w).astype(np.float32)


def sheet_cmd(video: Path, seconds: float, count: int) -> list:
    w, h = CELL
    return ["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-map", "0:v:0", "-vf",
            f"fps={count}/{max(seconds, 0.1):.4f},scale={w}:{h}:flags=area,format=rgb24", "-frames:v", count,
            "-f", "rawvideo", "-"]


def contact_sheet(video: Path, seconds: float, out: Path) -> Path:
    """24 frames in a 6 x 4 grid, each with its time."""
    import numpy as np
    from PIL import Image, ImageDraw
    cols, rows = SHEET
    w, h = CELL
    raw = media.run(sheet_cmd(video, seconds, cols * rows), binary=True).stdout
    n = len(raw) // (w * h * 3)
    frames = np.frombuffer(raw[:n * w * h * 3], dtype=np.uint8).reshape(n, h, w, 3)
    canvas = Image.new("RGB", (cols * (w + 4) + 4, rows * (h + 4) + 4), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for k in range(n):
        x, y = 4 + (k % cols) * (w + 4), 4 + (k // cols) * (h + 4)
        canvas.paste(Image.fromarray(frames[k]), (x, y))
        draw.rectangle([x, y, x + 52, y + 16], fill=(0, 0, 0))
        draw.text((x + 3, y + 3), f"{k * seconds / (cols * rows):.1f} s", fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=88)
    return out


def video_size(info: dict) -> tuple[int, int]:
    v = media.video_stream(info)
    if not v:
        raise CutError("the file has no picture")
    w, h = int(v["width"]), int(v["height"])
    return (h, w) if media.rotation(v) % 180 else (w, h)


# ---- finding the files -------------------------------------------------------------------------------------------
def find_plan(ep_dir: Path, video: Path) -> Path | None:
    target = rel(ep_dir, video)
    for p in sorted((ep_dir / "edit").glob("plan-v*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if str(data.get("output") or "").lstrip("./") == target:
            return p
    return None


def find_cut(ep_dir: Path, video: Path, plan: dict | None) -> Path | None:
    for name in (str((plan or {}).get("base") or ""), video.name):
        m = re.search(r"v\d{3,}", Path(name).name)
        if m and (ep_dir / "work" / f"short-cut-{m.group(0)}.json").is_file():
            return ep_dir / "work" / f"short-cut-{m.group(0)}.json"
    return newest(ep_dir / "work", "short-cut")


# ---- the check ---------------------------------------------------------------------------------------------------
def check(ep_dir: Path, video: Path, cut: Path | None = None, plan: Path | None = None) -> dict:
    import numpy as np
    s = settings()
    info = media.probe(video)
    w, h = video_size(info)
    seconds = media.duration(info) or 0.0
    plan_path = plan or find_plan(ep_dir, video)
    plan_data = read_json(plan_path) if plan_path else None
    cut_path = cut or find_cut(ep_dir, video, plan_data)
    report = read_json(cut_path) if cut_path else None
    pieces = (report or {}).get("pieces") or []
    inserts = [e for e in (plan_data or {}).get("inserts") or [] if "start" in e and "end" in e]
    findings = format_findings(w, h, seconds, s)
    manual = ["Look at the contact sheet: every picture understood within two seconds, nothing important in the "
              f"right {s['right_free_frac'] * 100:.0f} % (YouTube's buttons) or the bottom 20 % (title and captions)."]
    if pieces:
        findings += face_findings(pieces, inserts, s)
    else:
        manual.append("no cut report (work/short-cut-vNNN.json): face and piece edges are not checked; look at the "
                      "contact sheet for the face")
    if plan_data:
        tf, more = text_findings(pieces, inserts, s)
        findings += tf + card_findings(inserts, s)
        manual += more
    else:
        manual.append("no edit plan for this video: text overlays and text cards are not checked")

    luma = luma_samples(video)
    means = [float(x) for x in luma.mean(axis=(1, 2))] if len(luma) else []
    diffs = [float(x) for x in np.abs(np.diff(luma, axis=0)).mean(axis=(1, 2))] if len(luma) > 1 else []
    findings += luma_findings(means, s)
    changes = [float(p["short_from"]) for p in pieces[1:]]
    changes += [float(t) for e in inserts for t in (e["start"], e["end"])]
    changes += [float(x["at"]) for x in (plan_data or {}).get("speaker") or [] if isinstance(x, dict) and "at" in x]
    sf, shots = still_findings(diffs, changes, seconds, s)
    findings += sf

    loud = audio.measure_loudness(video) if media.audio_streams(info) else {"integrated_lufs": None,
                                                                             "true_peak_dbtp": None}
    findings += loudness_findings(loud, s)

    listen = [{"at": 0.0, "what": "the whole Short once, on a phone, with sound"}]
    edges = []
    if report:
        voice = inside(ep_dir, report["voice"]["file"]) if isinstance(report.get("voice"), dict) else None
        if voice and voice.is_file() and pieces:
            levels, floor = levels_of(voice)
            edges = edge_levels(levels, floor, pieces)
            for e in edges:
                if e["loud"]:
                    findings.append(f_("warning", "edges", f"piece {e['piece']} {e['side']}: sound at the edge "
                                                           f"({e['level_db']} dB, floor {e['floor_db']} dB): a "
                                                           "foreign syllable or a clipped word is likely", e["at"]))
        listen += list(report.get("listen") or [])
        wf = (report.get("words") or {}).get("file")
        if wf and inside(ep_dir, wf).is_file():
            from .short import load_words
            findings += tail_findings(load_words(inside(ep_dir, wf)), seconds, s)
    listen += [{"at": f["at"], "what": f["text"]} for f in findings if f["area"] == "edges"]
    seen, uniq = set(), []
    for x in sorted(listen, key=lambda x: x["at"]):
        key = (round(x["at"], 1), x["what"])
        if key not in seen:
            seen.add(key)
            uniq.append(x)

    stem = video.stem
    sheet = contact_sheet(video, seconds, ep_dir / "review" / f"short-check-{stem}.jpg")
    order = {"error": 0, "warning": 1}
    findings.sort(key=lambda f: (order[f["level"]], f.get("at", 0)))
    errors = sum(1 for f in findings if f["level"] == "error")
    result = {"video": rel(ep_dir, video), "cut": rel(ep_dir, cut_path) if cut_path else None,
              "plan": rel(ep_dir, plan_path) if plan_path else None, "width": w, "height": h,
              "seconds": round(seconds, 2), "rules": s, "findings": findings, "errors": errors,
              "warnings": sum(1 for f in findings if f["level"] == "warning"),
              "loudness": loud, "mean_luma_min": round(min(means), 1) if means else None, "shots": shots,
              "edges": edges, "listen": uniq, "manual": manual, "sheet": rel(ep_dir, sheet), "ok": errors == 0}
    out = ep_dir / "review" / f"short-check-{stem}.json"
    write_replace(out, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    result["report"] = rel(ep_dir, out)
    return result


def describe(r: dict) -> str:
    lines = [f"{r['video']}: {r['width']}x{r['height']}, {r['seconds']} s"]
    for f in r["findings"]:
        at = f" at {f['at']:.1f} s" if "at" in f else ""
        lines.append(f"  {f['level'].upper():<7} [{f['area']}]{at} {f['text']}")
    lines.append("please listen:")
    lines += [f"  {x['at']:6.2f} s  {x['what']}" for x in r["listen"]]
    lines.append("look:")
    lines += [f"  {m}" for m in r["manual"]]
    lines.append(f"contact sheet: {r['sheet']}\nreport: {r['report']}")
    lines.append(f"Result: {r['errors']} errors, {r['warnings']} warnings."
                 + ("" if r["ok"] else " Fix the errors, then check again."))
    return "\n".join(lines)
