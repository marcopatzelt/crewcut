"""Turn the chosen sentences (edit/selects-vNNN.json) into a cut plan for `crewcut cut build`, with the cut rules.

selects file:
  takes:   {"A": {"source": "originals/<sha12>-C0795.MP4", "face": [x, y], "lock": [[from, to, "reason"]],
                  "zoom_factor": 1.0}}
           face = face centre as a share of the full source frame (0..1), measured on a grid still.
           lock = source ranges that must not be used (hand at the camera, false start).
           zoom_factor = a take recorded from further away (a pickup): head-height ratio between the takes.
  selects: [{"id", "take", "start", "end", "text", "hard_end": false, "tail": 0}]
           start/end = first and last speech sample (island edges or measured dips).
           hard_end = the next word follows without a pause: no padding (read the edge first).
           tail = seconds of picture after the last word with the voice faded out (a breath).
  optional: speed, zoom_base, zoom_punch, face_y, pad_in, pad_out, pause_gap_open, pause_gap, pause_keep, open_seconds,
            voice_filter, mic_channel (0 left, 1 right, null both), music_seconds, note, width, height, fps,
            first_content (the id of the select where the first real content starts; before it is the opening),
            per select: pause_before (seconds, 1.5 to 3: one deliberate pause before the key sentence).

Rules built in (from real previews that sounded wrong):
  - Edges reach pad_in (0.12 s) / pad_out (0.16 s) into real silence, never into the next word.
  - The opening (the selects before `first_content`, else the first open_seconds of the cut) is dense: pauses inside a
    select longer than pause_gap_open (0.7 s) shrink to about 2 x pause_keep (0.26 s); joins keep the short pads.
  - After it natural pauses up to pause_gap (1.0 s) stay: inside a select, and between two selects that follow each
    other in the same take (the cut then continues the take, `join` in the cut). Longer pauses shrink to about 0.26 s.
  - One select may set pause_before (1.5 to 3 s): the deliberate pause before the key sentence, from the take's own
    silence where there is enough, else as a held tail of the select before (`pause_before` in the cut).
  - Every second cut inside the same take punches in (zoom_punch) so the jump does not show.
  - The cut must not outlast the music: estimated length <= music_seconds + 0.2 s.
  - A one-sided microphone is put on both ears (pan) at the start of the voice filter.
"""

from __future__ import annotations

from .common import cut_settings, frame_size

EPS = 0.03


def centre(face: list[float], z: float, target_y: float) -> list[float]:
    """zoom_center for the build: crop origin as a share of the free space, face in the middle of the crop."""
    if z <= 1.0001:
        return [0.5, 0.5]
    fx, fy = face
    free = 1 - 1 / z
    cx = (fx - 0.5 / z) / free
    cy = (fy - target_y / z) / free
    return [round(min(1.0, max(0.0, cx)), 3), round(min(1.0, max(0.0, cy)), 3)]


def silence_at(sil: list[tuple[float, float]], t: float) -> tuple[float, float] | None:
    return next(((x, y) for x, y in sil if x - EPS <= t <= y + EPS), None)


def pad_start(sil: list[tuple[float, float]], a: float, pad: float = 0.12) -> float:
    s = silence_at(sil, a - 0.02)
    return max(a - pad, s[0] + EPS) if s else a - 0.02


def pad_end(sil: list[tuple[float, float]], b: float, hard: bool, pad: float = 0.16) -> float:
    if hard:
        return b + EPS
    s = silence_at(sil, b + 0.02)
    return min(b + pad, s[1] - EPS) if s else b + 0.02


def split(sil: list[tuple[float, float]], a: float, b: float, keep: float = 0.13, gap: float = 0.30,
          ) -> list[tuple[float, float]]:
    """Split a select at long inner pauses and keep a short natural pause on both sides."""
    parts, s = [], a
    for x, y in sil:
        if x > a + 0.05 and y < b - 0.05 and y - x > gap:
            parts.append((s, x + keep))
            s = y - keep
    parts.append((s, b))
    return parts


def make_plan(cfg: dict, silences: dict[str, list[tuple[float, float]]], project: dict | None = None,
              mic: int | None = None) -> tuple[dict, list[str]]:
    """Pure: selects + pause lists per take -> (cut plan, problems)."""
    s = cut_settings(cfg)
    project = project or {}
    w, h = frame_size(project)
    width, height = int(cfg.get("width") or w), int(cfg.get("height") or h)
    fps = int(cfg.get("fps") or project.get("fps") or 25)
    takes, speed = cfg["takes"], float(s["speed"])
    problems, cuts, prev, punch = [], [], None, False
    ids = [sel.get("id") for sel in cfg["selects"]]
    first = cfg.get("first_content")
    if first is not None and first not in ids:
        problems.append(f"first_content {first!r} is not a select id")
        first = None
    beats = [sel.get("id") for sel in cfg["selects"] if sel.get("pause_before")]
    if len(beats) > 1:
        problems.append(f"more than one deliberate pause (pause_before on {', '.join(map(str, beats))}): keep one, "
                        "before the key sentence")
    lo_beat, hi_beat = float(s["beat_pause_min"]), float(s["beat_pause_max"])
    t_out, opening, last_sel = 0.0, True, None
    for n, sel in enumerate(cfg["selects"]):
        if sel.get("take") not in takes:
            problems.append(f"{sel.get('id')}: unknown take {sel.get('take')!r}")
            continue
        t = takes[sel["take"]]
        sil = silences.get(sel["take"], [])
        for lo, hi, why in t.get("lock", []):
            if sel["start"] < hi and sel["end"] > lo:
                problems.append(f"{sel['id']}: lies in the locked range {lo}-{hi} s ({why})")
        if not sel["end"] > sel["start"]:
            problems.append(f"{sel['id']}: end must be after start")
            continue
        was_opening = opening
        opening = (n < ids.index(first)) if first is not None else t_out < float(s["open_seconds"])
        # the pause before the first content still belongs to the opening: no gap over pause_gap_open
        join_max = float(s["pause_gap_open"] if was_opening else s["pause_gap"])
        gap = float(s["pause_gap_open"] if opening else s["pause_gap"])
        parts = split(sil, sel["start"], sel["end"], float(sel.get("pause_keep", s["pause_keep"])), gap)
        face = t.get("face") or [0.5, 0.4]
        factor = float(t.get("zoom_factor", t.get("zoom_faktor", 1.0)) or 1.0)
        beat = sel.get("pause_before")
        if beat is not None:
            beat = float(beat)
            if not lo_beat <= beat <= hi_beat:
                problems.append(f"{sel['id']}: pause_before {beat:g} s is outside {lo_beat:g} to {hi_beat:g} s")
                beat = None
            elif opening:
                problems.append(f"{sel['id']}: a deliberate pause does not belong in the opening (no gap over "
                                f"{float(s['pause_gap_open']):g} s until the first content)")
                beat = None
            elif not cuts:
                problems.append(f"{sel['id']}: a deliberate pause needs a sentence before it")
                beat = None
        same_take = bool(cuts) and last_sel is not None and last_sel.get("take") == sel["take"] \
            and not last_sel.get("hard_end") and not last_sel.get("tail")
        between = silence_at(sil, sel["start"] - 0.02)
        contiguous = same_take and between is not None and silence_at(sil, last_sel["end"] + 0.02) == between \
            and cuts[-1]["end"] <= sel["start"]
        for k, (x, y) in enumerate(parts):
            punch = (not punch) if prev == sel["take"] else False
            z = round(float(s["zoom_punch"] if punch else s["zoom_base"]) * factor, 3)
            first_part, last = k == 0, k == len(parts) - 1
            start = max(0.0, pad_start(sil, x, float(s["pad_in"]))) if first_part else x
            join = None
            if first_part and beat is not None:
                prev_cut = cuts[-1]
                already = prev_cut["end"] - last_sel["end"] + float(prev_cut.get("tail", 0))
                lead = beat - max(0.0, already)
                floor = (between[0] + EPS) if between else x - 0.02
                start = max(0.0, min(x, max(x - lead, floor)))
                rest = round(lead - (x - start), 3)
                if rest > 0.02:
                    prev_cut["tail"] = round(float(prev_cut.get("tail", 0)) + rest, 3)
            elif first_part and contiguous and not opening and x - last_sel["end"] <= join_max:
                start = cuts[-1]["end"]                     # the take goes on: its own pause stays
                join = round(x - last_sel["end"], 2)
            end = pad_end(sil, y, bool(sel.get("hard_end", False)), float(s["pad_out"])) if last else y
            c = {"id": sel["id"] if len(parts) == 1 else f"{sel['id']}_{k + 1}", "source": t["source"],
                 "start": round(start, 3), "end": round(end, 3), "speed": speed, "expected_text": sel.get("text", ""),
                 "zoom": z, "zoom_center": centre(face, z, float(s["face_y"])), "face": face}
            if first_part and beat is not None:
                c["pause_before"] = beat
            if join is not None:
                c["join"] = join
            if last and sel.get("tail"):
                c["tail"] = float(sel["tail"])
            if t.get("audio"):
                c["audio"] = t["audio"]
            cuts.append(c)
            prev = sel["take"]
        last_sel = sel
        t_out = sum((c["end"] - c["start"] + c.get("tail", 0)) / speed for c in cuts)
    seconds = sum((c["end"] - c["start"] + c.get("tail", 0)) / speed for c in cuts)
    music = cfg.get("music_seconds")
    if music and seconds > music + 0.2:
        problems.append(f"the cut ({seconds:.1f} s) is longer than the music ({music} s). Shorten it or pick music.")
    vf = s["voice_filter"]
    if mic is not None and not vf.startswith("pan="):
        vf = f"pan=stereo|c0=c{mic}|c1=c{mic}," + vf
    plan = {"version": cfg["version"], "fps": fps, "width": width, "height": height, "voice_filter": vf,
            "voice_lufs": s["voice_lufs"], "voice_tp": s["voice_tp"], "voice_lra": s["voice_lra"],
            "sync": {"note": cfg.get("sync_note", "Sound from the camera.")}, "cuts": cuts,
            "selection_note": cfg.get("note", ""), "expected_script": " ".join(x.get("text", "") for x in cfg["selects"]),
            "estimated_seconds": round(seconds, 2),
            "pauses": {"opening_until": first or f"{float(s['open_seconds']):g} s", "open_max": s["pause_gap_open"],
                       "keep_up_to": s["pause_gap"]}}
    return plan, problems


def mic_for_takes(cfg: dict, channels: dict[str, int | None]) -> int | None:
    """The microphone channel: from the selects, else the one all takes agree on."""
    if cfg.get("mic_channel") is not None:
        return int(cfg["mic_channel"])
    found = set(channels.values())
    return next(iter(found)) if len(found) == 1 else None
