#!/usr/bin/env python3
"""Check an edit plan and the video built from it: picture, plan and output, against the active style pack.

  python3 skills/cut-check/scripts/style_check.py <episode>/edit/plan-vNNN.json
          [--video FILE] [--exceptions FILE] [--report FILE] [--pack DIR] [--no-media]

General checks (any style):
  face        a face at the start and end of every speaker shot (skin share in the face window of the plan)
  waits       a full-screen insert that stands still until its first cue (1.5 s or more, 80 % still)
  empty       a full-screen insert that starts with an almost empty first frame
  music       music at least as long as the video; its source and rights note exists (sound.music_source)
  grade       a measured colour grade for this episode (review/grade*)
  fresh       the video is newer than the plan
  shown       a shown file was not changed after it was shown (<output>.shown holds the sha256)
  loudness    integrated loudness and true peak around the pack target; voice on both sides
Taste checks (values from edit-style.json and brand.json of the style pack):
  flash       speaker never shorter than speaker_min_seconds between two full-screen parts
  open-close  speaker at the start and in the last 30 s at least speaker_open_close_seconds
  share       speaker share between speaker_share_min and speaker_share_max
  text-share  text cards (headline, post) at most text_share_max of the full-screen inserts
  text-sources at most text_cards_max different text sources
  keywords    captions mode, at most keywords_max keywords, each at most keyword_max_words words
  italic      no italic type in the scene templates when italics is false
  small-text  no font size under min_text_px in the scene templates
  logo        a logo in the logo corner of every full-screen 2D insert (only when brand.json has a logo)
  end-card    the last full-screen part starts at the sentence with an end-card cue word (cut_words.end_card_cue)
  mix, pace   3D share and shots per minute against graphics_mix and pace_cuts_per_minute (NOTE only)
  motion-*    motion density (plans with motion inserts or full-frame 2D/3D scenes): every full-frame graphic,
              whatever its kind, counts as a full-frame and a motion moment; lengths, 6 s gaps, one per sentence,
              heroes, sounds, first and last seconds stay on motion inserts (edit-style.json motion, else neutral);
              keywords_max counts keyword and keyword_pop together
  slide       every full-frame insert, measured on the video (crewcut.render.slide): a camera that stands still
              for most of the hold is an ERROR ("slide" when the frame is also flat: one ground colour, a text
              window or boxes, an icon far from its label, one block in the middle); a recording gets a CHECK
The rules in rules/cut.md of the style pack are printed as the manual list.

Writes review/cut-check-vNNN.json. Exit 0 = no ERROR, 1 = at least one ERROR, 2 = usage.
--no-media skips everything that decodes the video or the music (plan checks only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checklib as cl  # noqa: E402

TEXT_SCENES = {"headline", "post"}
WAIT_MIN, WAIT_STILL = 1.5, 0.8
MANUAL = [
    "Contact sheet of the video looked at (one frame every 10 s).",
    "Listening list given to the user with times (this session cannot hear).",
    "Every scene beside the reference (brand/references or the baseline video): nothing looks like a slide deck.",
    "Inserts animated, not overdone; background and text stay calm.",
    "Third-party material: real, with a visible source, never invented.",
]


# ---------------------------------------------------------------- pure functions: plan


def normalize_words(raw) -> list[dict]:
    """Word times as [{"word", "start"}] from the usual transcript shapes."""
    if isinstance(raw, dict):
        raw = raw.get("words") or raw.get("segments") or []
    out = []
    for w in raw or []:
        if isinstance(w, dict) and isinstance(w.get("words"), list):  # caption groups
            out += normalize_words(w["words"])
            continue
        text = w.get("word", w.get("w", w.get("text", "")))
        start = w.get("start", w.get("s"))
        if start is not None:
            out.append({"word": str(text).strip(), "start": float(start)})
    return out


def word_time(words: list[dict], word: str, after: float = 0.0) -> float | None:
    key = str(word).strip(".,?!").lower()
    for w in words:
        if w["start"] >= after - 0.05 and w["word"].strip(".,?!").lower() == key:
            return w["start"]
    return None


def cue_frames(insert: dict, words: list[dict], fps: float) -> dict:
    """Cue name -> frame inside the insert. A cue is a frame number, {"word", "after", "offset"} or {"time"}."""
    out = {}
    start = insert.get("start", 0.0)
    for name, c in (insert.get("cues") or {}).items():
        if isinstance(c, bool):
            continue
        if isinstance(c, (int, float)):
            out[name] = int(c)
        elif isinstance(c, dict) and "word" in c:
            t = word_time(words, c["word"], c.get("after", start))
            if t is not None:
                out[name] = round(t * fps) - round(start * fps) + int(c.get("offset", 0))
        elif isinstance(c, dict) and "time" in c:
            out[name] = round(c["time"] * fps) - round(start * fps)
    return out


def seconds(v, words: list[dict], after: float = 0.0) -> float | None:
    """A plan time in seconds: a number, or a word anchor {"word", "offset" (s), "after"} (motion inserts)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, dict) and "word" in v:
        t = word_time(words, v["word"], float(v["after"]) if v.get("after") is not None else after)
        return None if t is None else t + float(v.get("offset") or 0.0)
    if isinstance(v, dict) and "time" in v:
        return float(v["time"]) + float(v.get("offset") or 0.0)
    return None


def plan_inserts(plan: dict, words: list[dict], fps: float) -> list[dict]:
    """Inserts with frames. An insert whose start or end word cannot be found is left out (the motion check
    names it)."""
    out = []
    for e in plan.get("inserts", []):
        a = seconds(e.get("start"), words)
        b = seconds(e.get("end"), words, a or 0.0)
        if a is None or b is None:
            continue
        s, t = round(a * fps), round(b * fps)
        out.append(
            {
                **e,
                "start_f": s,
                "end_f": t,
                "frames": t - s,
                "cue_f": cue_frames({**e, "start": a}, words, fps),
                "full": not e.get("transparent"),
            }
        )
    return out


def merge(iv: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def speaker_runs(inserts: list[dict], total_f: int, base_until_f: int | None = None) -> list[tuple[int, int]]:
    """Stretches where the speaker is on screen: the timeline minus full-screen inserts (and minus the tail)."""
    covered = [(i["start_f"], i["end_f"]) for i in inserts if i["full"]]
    if base_until_f is not None and base_until_f < total_f:
        covered.append((base_until_f, total_f))
    runs, t = [], 0
    for a, b in merge(covered):
        if a > t:
            runs.append((t, a))
        t = max(t, b)
    if total_f > t:
        runs.append((t, total_f))
    return runs


def flashes(runs: list[tuple[int, int]], total_f: int, min_f: float) -> list[tuple[int, int]]:
    """Speaker runs between two full-screen parts that are shorter than min_f frames."""
    return [(a, b) for a, b in runs if a > 0 and b < total_f and b - a < min_f]


def open_close(runs: list[tuple[int, int]], total_f: int, fps: float) -> tuple[float, float]:
    """Speaker seconds at the start, and the longest speaker stretch inside the last 30 s."""
    first = (runs[0][1] - runs[0][0]) / fps if runs and runs[0][0] == 0 else 0.0
    w0 = max(0, total_f - 30 * fps)
    last = max([(min(b, total_f) - max(a, w0)) / fps for a, b in runs if b > w0] or [0.0])
    return first, last


def keyword_texts(insert: dict) -> list[str]:
    """Keywords of an overlay: each chip of a 2D keyword; a motion keyword_pop is one keyword of its words; other
    motion overlays have none."""
    d = insert.get("data") or {}
    if insert.get("kind") == "motion":
        if insert.get("scene") != "keyword_pop":
            return []
        ws = [w["text"] if isinstance(w, dict) else str(w) for w in d.get("words") or []]
        return [" ".join(ws) if ws else str(d.get("text") or "")]
    out = [d["text"]] if isinstance(d.get("text"), str) else []
    for w in d.get("words") or []:
        out.append(w["text"] if isinstance(w, dict) else str(w))
    return out


def mix_counts(inserts: list[dict], fps: float) -> dict:
    full = [i for i in inserts if i["full"]]
    text = [i for i in full if i.get("scene") in TEXT_SCENES]
    sources = {
        json.dumps({k: (i.get("data") or {}).get(k) for k in ("title", "text", "name")}, sort_keys=True) for i in text
    }
    keywords = [t for i in inserts if not i["full"] for t in keyword_texts(i)]
    sec3d = sum(i["frames"] for i in inserts if i.get("kind") == "3d") / fps
    return {"full": len(full), "text": len(text), "sources": len(sources), "keywords": keywords, "sec3d": sec3d}


def scan_italics(src: str) -> list[int]:
    """Line numbers with italic type that is in use (comments removed, unused CSS classes ignored)."""
    src = re.sub(r"<!--.*?-->|/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    lines = src.splitlines()
    code = [(n, ln) for n, ln in enumerate(lines, 1) if not ln.strip().startswith("//") and "@font-face" not in ln]
    out = []
    for n, ln in code:
        if not re.search(r"font-style\s*:\s*italic|<i>|<em>", ln):
            continue
        m = re.match(r"\s*\.([\w-]+)\s*\{", ln)
        if m and not any(re.search(rf"\b{re.escape(m.group(1))}\b", x) for k, x in code if k != n):
            continue  # a class nobody uses
        out.append(n)
    return out


def scan_small_px(src: str, min_px: float) -> list[tuple[int, int]]:
    return [
        (n, int(px))
        for n, ln in enumerate(src.splitlines(), 1)
        for px in re.findall(r"font-size\s*:\s*(\d+)px", ln)
        if int(px) < min_px
    ]


def sentence_start(words: list[dict], k: int) -> float:
    while k > 0 and not re.search(r"[.?!]$", words[k - 1]["word"].strip()):
        k -= 1
    return words[k]["start"]


def end_card_offset(words: list[dict], cues: list[str], inserts: list[dict], total_s: float, fps: float):
    """Seconds between the start of the last full-screen part and the start of the end-card sentence.
    None when there is no cue word in the last 40 % of the video or no full-screen part there."""
    pat = [c.lower() for c in cues]
    hits = [
        k for k, w in enumerate(words) if re.sub(r"[^\w]", "", w["word"].lower()) in pat and w["start"] > 0.6 * total_s
    ]
    full = [i for i in inserts if i["full"] and i["start_f"] / fps > 0.6 * total_s]
    if not hits or not full:
        return None
    return full[-1]["start_f"] / fps - sentence_start(words, hits[-1])


# ---------------------------------------------------------------- pure functions: pixels


def skin_share(px: np.ndarray) -> float:
    """Share of skin-coloured pixels (YCbCr rule) in an RGB array."""
    p = px.astype(float)
    r, g, b = p[..., 0], p[..., 1], p[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cr, cb = (r - y) * 0.713 + 128, (b - y) * 0.564 + 128
    return float(((cr > 135) & (cr < 180) & (cb > 80) & (cb < 130) & (y > 50)).mean())


def face_outliers(values: dict, ratio: float = 0.6) -> list:
    """Keys whose skin share is under `ratio` times the median: back of the head, head turned away, no face."""
    if not values:
        return []
    med = float(np.median(list(values.values())))
    return [k for k, v in values.items() if v < ratio * med]


def content_share(px: np.ndarray, threshold: int = 40) -> float:
    """Share of pixels that differ from the background (the pixel near the top-left corner)."""
    p = px.astype(int)
    return float((np.abs(p - p[2, 2]).sum(-1) > threshold).mean())


def still_share(frames: list[np.ndarray], eps: float = 0.12) -> float:
    """Share of frame steps without visible change."""
    if len(frames) < 2:
        return 0.0
    still = sum(
        1 for u, v in zip(frames, frames[1:], strict=False) if float(np.abs(u.astype(int) - v.astype(int)).mean()) < eps
    )
    return still / (len(frames) - 1)


def corner_box(placement: str, size: int, w: int = 1920, h: int = 1080) -> tuple[int, int, int, int] | None:
    """x, y, width, height of the logo corner (logo plus word mark) in a w x h frame."""
    bw, bh, m = min(w // 3, int(size * 5)), int(size * 1.7), 16
    pos = {
        "top-right": (w - bw - m, m),
        "top-left": (m, m),
        "bottom-right": (w - bw - m, h - bh - m),
        "bottom-left": (m, h - bh - m),
    }.get(placement)
    return (pos[0], pos[1], bw, bh) if pos else None


def logo_found(px: np.ndarray, min_share: float = 0.02) -> bool:
    """Something other than flat background in the logo corner."""
    p = px.astype(int)
    bg = np.median(p.reshape(-1, p.shape[-1]), axis=0)
    return float((np.abs(p - bg).sum(-1) > 60).mean()) >= min_share


def shown_changed(output: Path) -> bool | None:
    """True when <output>.shown names a sha256 that the output no longer has. None when it was never shown."""
    mark = output.with_name(output.name + ".shown")
    if not mark.is_file() or not output.is_file():
        return None
    txt = mark.read_text(encoding="utf-8")
    try:
        want = json.loads(txt).get("sha256")
    except (ValueError, AttributeError):
        m = re.search(r"\b[0-9a-f]{64}\b", txt)
        want = m.group(0) if m else None
    if not want:
        return None
    h = hashlib.sha256()
    with output.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() != want


def limits(pack) -> dict:
    es = lambda k, d=None: pack.value(f"edit_style.{k}", d)  # noqa: E731
    return {
        "fps": es("fps", 25),
        "speaker_min": es("speaker_min_seconds", 2.0),
        "open_close": es("speaker_open_close_seconds", 3.0),
        "share_min": es("speaker_share_min", 0.0),
        "share_max": es("speaker_share_max", 1.0),
        "captions": es("captions", "keywords"),
        "keyword_max_words": es("keyword_max_words", 4),
        "keywords_max": es("keywords_max"),
        "text_cards_max": es("text_cards_max", 3),
        "text_share_max": es("text_share_max", 1.0),
        "italics": es("italics", True),
        "min_text_px": es("min_text_px", 0),
        "music": es("music", "none"),
        "lufs": es("loudness_lufs", -14.0),
        "window": es("loudness_window_lu", [-2.0, 0.5]),
        "peak": es("true_peak_db", -1.0),
        "mix_3d": (es("graphics_mix", {}) or {}).get("3d"),
        "pace": es("pace_cuts_per_minute"),
        "end_card_cue": (es("cut_words", {}) or {}).get("end_card_cue") or [],
        "logo_placement": pack.value("brand.logo.placement", "none"),
        "logo_file": pack.value("brand.logo.file"),
        "logo_size": pack.value("brand.logo.size", 54),
    }


# ---------------------------------------------------------------- media (needs ffmpeg; takes paths)


def frame(video, t: float, w: int, h: int, crop: str = "") -> np.ndarray | None:
    vf = f"scale={w}:{h}" if not crop else f"scale={w}:{h},crop={crop}"
    cw, ch = (int(x) for x in crop.split(":")[:2]) if crop else (w, h)
    raw = cl.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, t):.3f}",
            "-i",
            video,
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        text=False,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(ch, cw, 3) if len(raw) == cw * ch * 3 else None


def frames(video, t0: float, dur: float, fps: float, w: int = 320, h: int = 180) -> list[np.ndarray]:
    raw = cl.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, t0):.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            video,
            "-vf",
            f"fps={fps},scale={w}:{h}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        text=False,
    ).stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw[k * w * h * 3 : (k + 1) * w * h * 3], np.uint8).reshape(h, w, 3) for k in range(n)]


def frame_count(video) -> int:
    p = cl.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            video,
        ]
    )
    try:
        return int(p.stdout.strip().split(",")[0])
    except ValueError:
        return 0


# ---------------------------------------------------------------- the check


def template_sources(pack) -> list[Path]:
    roots = [cl.APP_ROOT / "templates" / "2d", Path(pack.dir) / "templates"]
    return [f for r in roots if r.is_dir() for f in r.rglob("*") if f.suffix in (".html", ".css", ".js")]


def check(plan_path: Path, video: Path | None, pack, rep: cl.Report, media: bool = True) -> None:
    L = limits(pack)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    ep = plan_path.resolve().parent.parent
    fps = plan.get("fps") or L["fps"]
    words = (
        normalize_words(json.loads((ep / plan["words"]).read_text(encoding="utf-8")))
        if plan.get("words") and (ep / plan["words"]).is_file()
        else []
    )
    ins = plan_inserts(plan, words, fps)
    have_video = bool(media and video and video.is_file())
    if have_video:
        total_f = frame_count(video) or round((cl.duration(video) or 0) * fps)
    else:
        total_f = max([i["end_f"] for i in ins] + [round((words[-1]["start"] if words else 0) * fps)]) + round(
            (plan.get("tail") or 0) * fps
        )
    total_s = total_f / fps if fps else 0
    base_until = round(plan["base_until"] * fps) if plan.get("base_until") is not None else None
    runs = speaker_runs(ins, total_f, base_until)

    # ---- picture: speaker
    A = "Picture"
    fl = flashes(runs, total_f, L["speaker_min"] * fps)
    for a, b in fl:
        rep.add(
            A,
            "ERROR",
            f"flash:{cl.tc(a / fps)}",
            f"Speaker only {(b - a) / fps:.2f} s on screen between two "
            f"full-screen parts (at least {L['speaker_min']} s)",
            a / fps,
            fix="Join the two inserts, or start the second later",
        )
    between = [b - a for a, b in runs if a > 0 and b < total_f]
    if not fl:
        rep.add(
            A,
            "OK",
            "flash",
            f"Shortest speaker run between inserts {min(between) / fps:.1f} s"
            if between
            else "No speaker run between two full-screen parts",
        )
    first, last = open_close(runs, total_f, fps)
    rep.add(
        A,
        "OK" if first >= L["open_close"] else "ERROR",
        "open",
        f"Speaker at the start {first:.1f} s (at least {L['open_close']})",
    )
    rep.add(
        A,
        "OK" if last >= L["open_close"] else "ERROR",
        "close",
        f"Longest speaker run in the last 30 s: {last:.1f} s (at least {L['open_close']})",
    )
    share = sum(b - a for a, b in runs) / total_f if total_f else 0
    rep.add(
        A,
        "OK" if L["share_min"] <= share <= L["share_max"] else "CHECK",
        "share",
        f"Speaker on screen {share:.0%} of the video (pack: {L['share_min']:.0%} to {L['share_max']:.0%})",
    )
    mc = mix_counts(ins, fps)
    if L["mix_3d"] is not None and total_s:
        d3 = mc["sec3d"] / max(1e-6, sum(i["frames"] for i in ins if i["full"]) / fps)
        rep.add(
            A, "NOTE", "mix", f"3D is {d3:.0%} of the full-screen insert time (pack graphics_mix 3d: {L['mix_3d']:.0%})"
        )
    if L["pace"] and total_s:
        shots = len(runs) + sum(1 for i in ins if i["full"]) + len(plan.get("speaker") or [])
        rep.add(
            A,
            "NOTE",
            "pace",
            f"{shots} shots in {total_s:.0f} s = {shots / total_s * 60:.1f} per minute (pack: {L['pace']})",
        )

    # ---- plan: mix and text
    P = "Plan"
    ts = mc["text"] / max(1, mc["full"])
    rep.add(
        P,
        "ERROR" if ts > L["text_share_max"] else "OK",
        "text-share",
        f"{mc['text']} of {mc['full']} full-screen inserts are text cards ({ts:.0%}, at most {L['text_share_max']:.0%})",
        fix="Replace a text card by a scene that shows something happening, or by real material",
    )
    rep.add(
        P,
        "CHECK" if mc["sources"] > L["text_cards_max"] else "OK",
        "text-sources",
        f"{mc['sources']} different text sources (at most {L['text_cards_max']}; each must be a real source to read)",
    )
    kw = mc["keywords"]
    if L["captions"] == "none" and kw:
        rep.add(P, "CHECK", "keywords", f"The pack says captions none, but the plan has {len(kw)} keywords")
    elif L["captions"] == "keywords":
        too_long = [k for k in kw if len(k.split()) > L["keyword_max_words"]]
        rep.add(
            P,
            "ERROR" if too_long else "OK",
            "keyword-words",
            f"{len(kw)} keywords, longest {max([len(k.split()) for k in kw] or [0])} words "
            f"(at most {L['keyword_max_words']})" + (f": too long {too_long}" if too_long else ""),
        )
        if L["keywords_max"] is not None:
            rep.add(
                P,
                "CHECK" if len(kw) > L["keywords_max"] else "OK",
                "keyword-count",
                f"{len(kw)} keywords over the speaker (at most {L['keywords_max']}; only a number or a name)",
            )
    srcs = template_sources(pack)
    if L["italics"] is False:
        ital = [(f, n) for f in srcs for n in scan_italics(f.read_text(encoding="utf-8", errors="ignore"))]
        rep.add(
            P,
            "ERROR" if ital else "OK",
            "italic",
            "No italic type in the scene templates"
            if not ital
            else "Italic type in " + ", ".join(f"{f.name}:{n}" for f, n in ital[:6]),
            fix="Emphasis by colour and weight",
        )
    if L["min_text_px"]:
        small = [
            (f, n, px)
            for f in srcs
            for n, px in scan_small_px(f.read_text(encoding="utf-8", errors="ignore"), L["min_text_px"])
        ]
        rep.add(
            P,
            "CHECK" if small else "OK",
            "small-text",
            f"No font size under {L['min_text_px']} px"
            if not small
            else f"Font size under {L['min_text_px']} px: "
            + ", ".join(f"{f.name}:{n} ({px} px)" for f, n, px in small[:8]),
        )
    if L["end_card_cue"] and words:
        off = end_card_offset(words, L["end_card_cue"], ins, total_s, fps)
        if off is None:
            rep.add(
                P,
                "NOTE",
                "end-card",
                "No end-card cue word in the last 40 % of the video, or no full-screen part there",
            )
        else:
            rep.add(
                P,
                "ERROR" if off > 0.5 or off < -1.5 else "OK",
                "end-card",
                f"Last full-screen part starts {off:+.1f} s from the end-card sentence (allowed -1.5 to +0.5)",
            )
    if any(e.get("kind") == "motion" for e in plan.get("inserts") or []) or any(
        e.get("kind") in ("2d", "3d") and not e.get("transparent") for e in plan.get("inserts") or []
    ):
        motion_density(plan, ep, pack, rep, P, total_s)
    grade = list((ep / "review").glob("grade*")) if (ep / "review").is_dir() else []
    rep.add(
        P,
        "OK" if grade else "CHECK",
        "grade",
        "Measured grade found: " + grade[0].name
        if grade
        else "No grade measurement in review/: was this episode graded with its own measured values?",
        fix="crewcut cut grade (measure, then apply)",
    )
    snd = plan.get("sound") or {}
    if snd.get("music"):
        mp = ep / snd["music"]
        src = snd.get("music_source")
        rep.add(
            P,
            "OK" if src and (ep / src).is_file() else "ERROR",
            "music-rights",
            f"Music source and rights note: {src or 'missing (sound.music_source)'}",
            fix="Write the source note (model or library, licence, prompts) and point sound.music_source at it",
        )
        if media and mp.is_file():
            md = cl.duration(mp) or 0
            rep.add(P, "OK" if md >= total_s - 0.5 else "ERROR", "music", f"Music {md:.1f} s, video {total_s:.1f} s")
    elif L["music"] not in (None, "none"):
        rep.add(P, "CHECK", "music", f"The pack wants music ({L['music']}), the plan has none")

    # ---- picture from the video
    if have_video:
        g = plan.get("face") or [0.5, 0.38]
        w, h = 640, 360
        x0, y0 = max(0, min(w - 140, int(g[0] * w) - 70)), max(0, min(h - 140, int(g[1] * h) - 70))
        vals = {}
        for a, b in runs:
            if (b - a) / fps < L["speaker_min"]:
                continue
            for f in (a + 3, b - 4):
                px = frame(video, f / fps, w, h, crop=f"140:140:{x0}:{y0}")
                if px is not None:
                    vals[f] = skin_share(px)
        bad = face_outliers(vals)
        for f in bad:
            rep.add(
                A,
                "ERROR",
                f"face:{cl.tc(f / fps)}",
                f"No face at {cl.tc(f / fps)} (skin share {vals[f]:.2f}, "
                f"median {np.median(list(vals.values())):.2f}): back of the head or head turned away?",
                f / fps,
                fix="Move the cut, or measure 'face' in the plan again",
            )
        if vals and not bad:
            rep.add(A, "OK", "face", f"Face at {len(vals)} speaker starts and ends")
        lw, lh = 1920, 1080
        box = corner_box(L["logo_placement"], L["logo_size"], lw, lh) if L["logo_file"] else None
        for i in ins:
            if not i["full"]:
                continue
            slide_check(video, i, fps, rep, A)
            if i.get("kind") == "clip":
                continue
            first = frame(video, i["start_f"] / fps + 0.5 / fps, 480, 270)
            if first is not None:
                c = content_share(first)
                rep.add(
                    A,
                    "OK" if c > 0.003 else "CHECK",
                    f"empty:{i['id']}",
                    f"{i['id']} first frame {c:.1%} content",
                    i["start_f"] / fps,
                    fix="Start the scene a few frames into its build",
                )
            cue = min([c for c in i["cue_f"].values() if c > 0] or [0])
            if cue / fps >= WAIT_MIN:
                fr = frames(video, i["start_f"] / fps, cue / fps, fps)
                s = still_share(fr)
                rep.add(
                    A,
                    "ERROR" if s > WAIT_STILL else "OK",
                    f"waits:{i['id']}",
                    f"{i['id']} waits {cue / fps:.1f} s for its first cue, {s:.0%} of it without motion",
                    i["start_f"] / fps,
                    fix="Fill the wait with action, or start the insert later",
                )
            if box and i.get("kind") == "2d":
                mid = (i["start_f"] + i["end_f"]) / 2 / fps
                crop = f"{box[2]}:{box[3]}:{box[0]}:{box[1]}"
                px = frame(video, mid, lw, lh, crop=crop)
                if px is not None:
                    ok = logo_found(px)
                    rep.add(
                        A,
                        "OK" if ok else "ERROR",
                        f"logo:{i['id']}",
                        f"Logo {L['logo_placement']} in {i['id']}: {'found' if ok else 'missing'}",
                        mid,
                        fix="A shape covers the logo corner, or the scene skips the logo",
                    )

    # ---- output
    OUT = "Output"
    if not media and (not video or not video.is_file()):
        rep.add(OUT, "NOTE", "video", "Plan checks only (--no-media); the video is not checked.")
        return
    if not video or not video.is_file():
        rep.add(OUT, "ERROR", "video", f"Video not found: {video}. Build it first (crewcut render cut).")
        return
    fresh = video.stat().st_mtime >= plan_path.stat().st_mtime
    rep.add(
        OUT,
        "OK" if fresh else "ERROR",
        "fresh",
        f"{video.name} is " + ("newer than the plan" if fresh else "older than the plan: build again"),
    )
    ch = shown_changed(video)
    if ch is not None:
        rep.add(
            OUT,
            "ERROR" if ch else "OK",
            "shown",
            f"{video.name} was shown; "
            + ("it changed since: every change is a new plan version" if ch else "unchanged since"),
        )
    if media:
        lufs, peak = cl.loudness(video)
        lvl, txt = cl.loudness_verdict(lufs, peak, L["lufs"], L["window"], L["peak"])
        rep.add(OUT, lvl, "loudness", txt)
        lv = cl.channel_levels(video)
        if len(lv) >= 2:
            rep.add(
                OUT,
                "OK" if abs(lv[0] - lv[1]) <= 10 else "ERROR",
                "channels",
                f"Sound left {lv[0]} dB, right {lv[1]} dB",
            )
        rep.add(OUT, "NOTE", "length", f"{total_f} frames, {cl.tc(total_s)}")
        # camera roll on frames with only the speaker on screen (no insert, no overlay): the card gate reads the result
        tilt = cl.app_module("crewcut.cut.tilt")
        clean = speaker_runs([{**i, "full": True} for i in ins], total_f, base_until)
        roll = tilt.measure(video, ep, tilt.speaker_times(clean, fps), tilt.declared(tilt.read(tilt.cut_plan_for(ep, plan))))
        rep.add(
            A,
            roll["level"],
            "roll",
            roll["text"],
            fix="Rotate the speaker frames by the cut plan's camera_roll_correction and render again"
            if roll["level"] == "ERROR"
            else None,
        )


def slide_check(video: Path, i: dict, fps: float, rep: cl.Report, area: str) -> None:
    """The slide check of one full-frame insert (crewcut.render.slide), measured on the video."""
    slide = cl.app_module("crewcut.render.slide")
    found = slide.check(
        str(video),
        [{"id": i["id"], "kind": i.get("kind"), "start": i["start_f"] / fps, "end": i["end_f"] / fps, "full": True}],
    )
    for f in found:
        rep.add(area, f["level"], f["id"], f["text"], f["time"], f["fix"])


def motion_density(plan: dict, ep: Path, pack, rep: cl.Report, area: str, total_s: float) -> None:
    """The motion density counts (crewcut.motion.density) as findings. keyword-count above already counts
    keyword_pop, so the density's own keyword line is left out here."""
    md = cl.app_module("crewcut.motion.density")
    raw = json.loads((ep / plan["words"]).read_text(encoding="utf-8")) if plan.get("words") and (
        ep / plan["words"]).is_file() else []
    tmpl = {}
    try:
        tp = cl.app_module("crewcut.motion.templates")
        tmpl = {n: len(h.get("sounds") or []) for n, h in tp.discover().items()}
    except (ImportError, OSError):
        pass
    es = dict(pack.value("edit_style", {}) or {})
    res = md.count(plan, md.norm_words(raw), md.limits(es), tmpl, total_s=total_s or None)
    for f in res["findings"]:
        if f["id"] != "motion-keywords":
            rep.add(area, f["level"], f["id"], f["text"], f["time"], f["fix"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check an edit plan and its video against the style pack.")
    ap.add_argument("plan", help="edit/plan-vNNN.json")
    ap.add_argument("--video", help="default: 'output' of the plan")
    ap.add_argument("--exceptions", help="default: <episode>/review/cut-check-exceptions.json")
    ap.add_argument("--report", help="default: <episode>/review/cut-check-vNNN.json")
    ap.add_argument("--pack", help="style pack folder (default: studio/brand, else packs/neutral)")
    ap.add_argument("--no-media", action="store_true", help="plan checks only, no ffmpeg")
    a = ap.parse_args(argv)
    plan_path = Path(a.plan)
    if not plan_path.is_file():
        ap.error(f"plan not found: {plan_path}")
    ep = plan_path.resolve().parent.parent
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    video = Path(a.video) if a.video else (ep / plan["output"] if plan.get("output") else None)
    pack = cl.load_pack(a.pack)
    exc = Path(a.exceptions) if a.exceptions else ep / "review" / "cut-check-exceptions.json"
    rep = cl.Report(cl.load_exceptions(exc))
    check(plan_path, video, pack, rep, media=not a.no_media)
    v = cl.version_of(plan_path)
    print(
        f"Style check {ep.name}, plan {plan_path.name}, video {video.name if video else '-'}, "
        f"style pack {'neutral' if pack.is_neutral else pack.dir.name}"
    )
    rep.print(["Picture", "Plan", "Output"])
    print("\nBy hand:")
    for line in cl.manual_list(MANUAL, pack, "cut"):
        print("  " + line)
    n = rep.count()
    print(f"\nResult: {n['ERROR']} ERROR, {n['CHECK']} CHECK, {n['OK']} OK, {n['NOTE']} NOTE")
    out = Path(a.report) if a.report else ep / "review" / f"cut-check-{v}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "episode": ep.name,
                "plan": plan_path.name,
                "video": str(video) if video else None,
                "counts": n,
                "findings": rep.items,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Report: {out}")
    if n["ERROR"]:
        print(
            "NOT PASSED: unchecked, do not show. Fix the errors, build a new plan version, check again.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
