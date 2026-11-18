"""What the episode view shows first: thumbnail variants, the cut with frames and sound peaks, 3D scenes, the GPU.

`episode_media()` answers GET /api/episodes/{id}/media (docs/api.md). It only reads the episode folder and the
database, and a missing folder gives null or an empty list, never an error. Frames and sound peaks of a video are made
once with ffmpeg in a background thread and kept in `work/strip-<video stem>/`, so a request never waits for ffmpeg.
`needs()` and `seconds()` feed the episode cards (`episodes.summary()`), `job_preview()` the "Working now" picture
(`queue.job_view()`); both are cheap enough to run on every call (small caches keyed by mtime).
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import quote

from . import db, paths

IMAGES = (".png", ".jpg", ".jpeg", ".webp")
VIDEOS = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
STRIP_FRAMES = 10            # frames per cut, evenly spaced
STRIP_WIDTH = 320            # px, JPEG
PEAKS = 240                  # sound level values per cut
PEAK_RATE = 4000             # Hz: enough for a level curve, small enough to read a long video in memory
DELETE_NOTE = "Deleted when done, frames come home"
LEVELS = {"error": "error", "check": "warning", "warning": "warning", "warn": "warning", "note": "note",
          "info": "note"}  # cut-check levels -> marker levels (OK is not a marker)
CAPTIONS = {"keywords": "Keywords only", "full": "Full captions", "none": "No captions"}
FULL_FRAME = ("2d", "3d", "clip")
LIVE_RENTALS = ("creating", "starting", "ready", "lost")    # as compute.rentals.LIVE
NOTE_FILE = "variants.json"  # the Designer's note in a thumbnail round: label, note, recommended per variant
# where a job's newest picture is looked for, per step: (folder, only subfolders starting with ...)
SCAN_ROOTS = {"thumbnail": (("graphics", None),),
              "edit": (("render", None), ("review", None), ("work", "strip-"))}
ALL_ROOTS = (("render", None), ("graphics", None), ("review", None), ("work", "strip-"))

_REF = re.compile(r"^\d{1,2}-")              # inputs of a thumbnail round: 1-photo.jpg, 3-result.png, 1-still-88.0s.png
_ROUND = re.compile(r"^v(\d+)\b", re.I)      # graphics/thumbnail/v2-face/
_VARIANT = re.compile(r"^([A-Z])(?:[-_ ](.*))?$")   # graphics/thumbnail/v2-face/A-face-right/
_VNUM = re.compile(r"(?:^|[^A-Za-z0-9])v(\d+)(?=$|[^0-9])")
_FRAME = re.compile(r"^\d{4}\.png$")
_3D = re.compile(r"\b3d\b|blender", re.I)

_lock = threading.Lock()
_durations: dict[str, tuple[int, int, float | None]] = {}
_strips: dict[str, threading.Thread] = {}
_dirs: dict[str, tuple[int, tuple[float, str] | None, tuple[str, ...]]] = {}


# ---- small helpers -------------------------------------------------------------------------------------------------
def _rel(ep: Path, p: Path) -> str:
    try:
        return p.relative_to(ep).as_posix()
    except ValueError:
        return p.resolve().relative_to(ep.resolve()).as_posix()


def url(episode: str, p: Path) -> str:
    """The URL under which the UI loads a file of the episode (GET /api/files/{episode}/{path})."""
    return f"/api/files/{episode}/{quote(_rel(paths.episode_dir(episode), Path(p)))}"


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _files(d: Path) -> list[Path]:
    try:
        return [p for p in d.iterdir() if not p.name.startswith(".") and p.is_file()]
    except OSError:
        return []


def _subdirs(d: Path) -> list[Path]:
    try:
        return sorted(p for p in d.iterdir() if not p.name.startswith(".") and p.is_dir())
    except OSError:
        return []


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def vnum(name: str) -> int | None:
    """The version number in a file name: 'x-v002-preview.mp4' -> 2 (the last vNNN wins), None without one."""
    found = _VNUM.findall(Path(name).stem)
    return int(found[-1]) if found else None


def _versions(d: Path, prefix: str) -> list[tuple[int, Path]]:
    """Files <prefix>-vNNN*.json in d, oldest version first."""
    out = [(vnum(p.name), p) for p in _files(d) if p.name.startswith(prefix + "-v") and p.suffix == ".json"]
    return sorted(((n, p) for n, p in out if n is not None), key=lambda x: (x[0], _mtime(x[1])))


# ---- thumbnails ------------------------------------------------------------------------------------------------------
def _drafts(d: Path) -> list[Path]:
    """Images in d that are thumbnails: not the inputs, preview sheets or 1280x720 upload copies."""
    return [p for p in _files(d) if p.suffix.lower() in IMAGES and not _REF.match(p.name)
            and not p.name.lower().startswith("preview-") and "-1280x720" not in p.name]


def _best(imgs: list[Path]) -> Path | None:
    """The image a variant shows: a file named thumbnail* first, then the highest version, then the newest."""
    if not imgs:
        return None
    return max(imgs, key=lambda p: (p.name.lower().startswith("thumbnail"), vnum(p.name) or 0, _mtime(p)))


def _variants_in(group: Path) -> list[tuple[str, str | None, Path]]:
    """(id, motif, image) per variant: one folder per variant (A-face-right/), else the images in file order."""
    out: list[tuple[str, str | None, Path]] = []
    for d in _subdirs(group):
        m = _VARIANT.match(d.name)
        img = _best(_drafts(d)) if m else None
        if m and img and all(v[0] != m.group(1) for v in out):
            out.append((m.group(1), m.group(2), img))
    if not out:
        flat = sorted(_drafts(group), key=lambda p: p.name)[:26]
        out = [(chr(65 + i), None, p) for i, p in enumerate(flat)]
    return out


def _thumb_group(base: Path) -> tuple[Path, list[tuple[str, str | None, Path]]] | None:
    """The newest thumbnail round (graphics/thumbnail/vN-<purpose>/, or the folder itself) and its variants."""
    best = None
    for g in [d for d in _subdirs(base) if _ROUND.match(d.name)] + [base]:
        vs = _variants_in(g)
        if vs:
            t = max(_mtime(img) for _, _, img in vs)
            if best is None or t > best[0]:
                best = (t, g, vs)
    return (best[1], best[2]) if best else None


def _note(group: Path) -> dict[str, dict]:
    """The Designer's note per variant id: a list, {"variants": [...]} or {"A": {...}} in variants.json."""
    raw = _json(group / NOTE_FILE)
    items = raw.get("variants") if isinstance(raw, dict) and "variants" in raw else raw
    if isinstance(items, dict):
        items = [{"id": k, **v} for k, v in items.items() if isinstance(v, dict)]
    return {str(e["id"]): e for e in items or [] if isinstance(e, dict) and e.get("id")}


def _label(motif: str | None, vid: str) -> str:
    if not motif:
        return f"Variant {vid}"
    t = re.sub(r"[-_]+", " ", motif).strip()
    return t[:1].upper() + t[1:] if t else f"Variant {vid}"


def _picked(card: dict | None, ids: list[str], labels: dict[str, str]) -> str | None:
    """The variant the user chose on an accepted thumbnail card: the option's letter or label, else the index."""
    if not card or card.get("choice") is None:
        return None
    choice = int(card["choice"])
    opts = card.get("options") if isinstance(card.get("options"), list) else []
    if 0 <= choice < len(opts):
        text = str(opts[choice])
        for letter in re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", text):
            if letter in ids:
                return letter
        for vid in ids:
            if labels[vid].lower() == text.strip().lower():
                return vid
    return ids[choice] if 0 <= choice < len(ids) else None


def thumbnails(episode: str) -> list[dict]:
    """The variants of the newest thumbnail round (MediaThumb in web/src/api/types.ts)."""
    ep = paths.episode_dir(episode)
    base = ep / "graphics" / "thumbnail"
    found = _thumb_group(base)
    if not found:
        return []
    group, vs = found
    note = _note(group)
    images = {vid: img for vid, _, img in vs}
    motifs = {vid: motif for vid, motif, _ in vs}
    for vid, e in note.items():
        if e.get("file"):
            try:
                p = paths.inside(group, str(e["file"]))
            except ValueError:
                continue
            if p.is_file() and p.suffix.lower() in IMAGES:
                images[vid] = p
                motifs.setdefault(vid, None)
    ids = sorted(images)
    labels = {vid: str(note.get(vid, {}).get("label") or _label(motifs.get(vid), vid)) for vid in ids}
    with db.conn() as c:
        cards = db.rows(c.execute("SELECT * FROM cards WHERE episode = ? AND kind = 'thumbnail' "
                                  "AND status IN ('open', 'accepted') ORDER BY id DESC", (episode,)))
    open_id = next((c["id"] for c in cards if c["status"] == "open"), None)
    accepted = next((c for c in cards if c["status"] == "accepted"), None)
    if accepted and open_id and open_id > accepted["id"]:
        accepted = None                         # a newer question is open: the old answer was about an older round
    if accepted and accepted.get("file"):
        try:
            f = paths.inside(ep, accepted["file"])
            if base.resolve() in f.parents and group.resolve() not in f.parents and group != base:
                accepted = None                 # the answer was about another round
        except ValueError:
            pass
    picked = _picked(accepted, ids, labels)
    return [{"id": vid, "label": labels[vid], "note": note.get(vid, {}).get("note"), "url": url(episode, images[vid]),
             "recommended": bool(note.get(vid, {}).get("recommended")), "picked": vid == picked, "card": open_id}
            for vid in ids]


# ---- the cut: source, length, frames and peaks ---------------------------------------------------------------------
def cut_source(ep: Path) -> Path | None:
    """The newest preview or final in export/ (highest version, then newest), else the newest work/speaker-vNNN.mov."""
    exp = [p for p in _files(ep / "export") if p.suffix.lower() in VIDEOS and ".tmp" not in p.name]
    if exp:
        return max(exp, key=lambda p: (vnum(p.name) or 0, _mtime(p)))
    work = [p for p in _files(ep / "work") if re.match(r"^speaker-v\d+\.mov$", p.name)]
    return max(work, key=lambda p: (vnum(p.name) or 0, _mtime(p))) if work else None


def duration(video: Path) -> float | None:
    """Length in seconds (ffprobe), cached by path, size and mtime: ffprobe runs once per version of a file."""
    try:
        st = video.stat()
    except OSError:
        return None
    key = str(video)
    with _lock:
        hit = _durations.get(key)
    if hit and hit[:2] == (st.st_mtime_ns, st.st_size):
        return hit[2]
    from .cut import media as cutmedia
    from .render import media as rmedia
    try:
        out = cutmedia.run([rmedia.ffprobe(), "-v", "error", "-show_format", "-of", "json", str(video)], timeout=30)
        secs = cutmedia.duration(json.loads(out.stdout))
    except Exception:  # noqa: BLE001 - a missing program or a file still being written has no length yet
        secs = None
    secs = round(secs, 3) if secs else None
    with _lock:
        if len(_durations) > 1024:
            _durations.clear()
        _durations[key] = (st.st_mtime_ns, st.st_size, secs)
    return secs


def seconds(episode: str) -> float | None:
    """Length of the episode's newest export or cut, for its card (Episode.seconds); None without a video."""
    try:
        v = cut_source(paths.episode_dir(episode))
    except ValueError:
        return None
    d = duration(v) if v else None
    return round(d, 2) if d else None


def strip_dir(ep: Path, video: Path) -> Path:
    return ep / "work" / f"strip-{video.stem}"


def read_strip(d: Path, video: Path) -> dict | None:
    """The cached frames and peaks of exactly this video (same size and mtime as when they were made), or None."""
    try:
        st = video.stat()
    except OSError:
        return None
    data = _json(d / "peaks.json")
    if not isinstance(data, dict) or data.get("size") != st.st_size or data.get("mtime_ns") != st.st_mtime_ns:
        return None
    return data


def sound_peaks(video: Path, n: int = PEAKS) -> list[float]:
    """About n values 0..1: the loudest sample of each slice of the sound, scaled to the loudest slice. [] if silent
    or without sound."""
    import numpy as np

    from .cut import media as cutmedia
    from .render import media as rmedia
    r = cutmedia.run([rmedia.ffmpeg(), "-nostdin", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar",
                      str(PEAK_RATE), "-f", "s16le", "-acodec", "pcm_s16le", "-"], check=False, binary=True,
                     timeout=900)
    a = np.frombuffer(r.stdout or b"", dtype=np.int16)
    if a.size == 0:
        return []
    a = np.abs(a.astype(np.int32))
    n = min(n, int(a.size))
    edges = np.linspace(0, a.size, n + 1).astype(np.int64)[:-1]
    vals = np.maximum.reduceat(a, edges)
    top = int(vals.max())
    if top <= 0:
        return [0.0] * n
    return [round(float(v) / top, 3) for v in vals]


def make_strip(video: Path, d: Path) -> dict:
    """Ten frames (JPEG, 320 px wide) and the sound peaks of a video, written into d; peaks.json comes last and marks
    the strip as complete. A failure is written too (empty lists), so a broken file is not tried on every request."""
    from .cut import media as cutmedia
    from .render import media as rmedia
    st = video.stat()
    d.mkdir(parents=True, exist_ok=True)
    secs = duration(video)
    frames, peaks, errors = [], [], []
    if secs:
        for i in range(STRIP_FRAMES):
            t = secs * (i + 0.5) / STRIP_FRAMES
            out = d / f"frame-{i + 1:02d}.jpg"
            try:
                cutmedia.run([rmedia.ffmpeg(), "-nostdin", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
                              "-frames:v", "1", "-vf", f"scale={STRIP_WIDTH}:-2", "-q:v", "5", str(out)], timeout=120)
            except Exception as e:  # noqa: BLE001 - one missing frame leaves a gap, not a broken strip
                errors.append(f"frame {i + 1}: {str(e)[:200]}")
                continue
            if out.is_file() and out.stat().st_size:
                frames.append({"t": round(t, 2), "file": out.name})
        try:
            peaks = sound_peaks(video)
        except Exception as e:  # noqa: BLE001
            errors.append(f"peaks: {str(e)[:200]}")
    else:
        errors.append("no length: ffprobe could not read the video")
    data = {"video": video.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns, "seconds": secs, "frames": frames,
            "peaks": peaks, "made": db.now()}
    if errors:
        data["errors"] = errors[:5]
    tmp = d / "peaks.json.tmp"
    tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
    tmp.replace(d / "peaks.json")
    return data


def _strip_thread(video: Path, d: Path) -> None:
    try:
        if read_strip(d, video) is None:
            make_strip(video, d)
    except Exception:  # noqa: BLE001 - a background job must never take the server down; the next request retries
        pass
    finally:
        with _lock:
            if _strips.get(str(d)) is threading.current_thread():
                del _strips[str(d)]


def strip(ep: Path, video: Path) -> dict | None:
    """The cached strip of a video, or None while it is being made: the first call starts one background thread per
    video, later calls only look."""
    d = strip_dir(ep, video)
    data = read_strip(d, video)
    if data is not None:
        return data
    with _lock:
        t = _strips.get(str(d))
        if t is None or not t.is_alive():
            t = threading.Thread(target=_strip_thread, args=(video, d), daemon=True, name=f"strip-{video.stem}")
            _strips[str(d)] = t
            t.start()
    return None


def _edit_plan_for(ep: Path, video: Path, v: int | None) -> dict | None:
    """The edit plan that built an export: the one whose output is this file, else the one of the same version."""
    if video.parent.name != "export":
        return None
    rel = _rel(ep, video)
    plans = _versions(ep / "edit", "plan")
    for _, p in reversed(plans):
        d = _json(p)
        if isinstance(d, dict) and (d.get("output") or f"export/{p.stem}.mp4") == rel:
            return d
    for n, p in plans:
        if n == v:
            d = _json(p)
            return d if isinstance(d, dict) else None
    return None


def shots(ep: Path, video: Path, v: int | None) -> int:
    """Shots of a cut: the speaker pieces of its cut plan (cuts, or pieces for a Short) plus the full-frame inserts of
    its edit plan. 0 when neither is there."""
    plan = _edit_plan_for(ep, video, v)
    base_v = v
    if plan is not None:
        base = plan.get("base")
        base_v = vnum(base) if isinstance(base, str) else None
    pieces = None
    if base_v is not None:
        for prefix, key in (("cut-plan", "cuts"), ("pieces", "pieces")):
            hit = [p for n, p in _versions(ep / "edit", prefix) if n == base_v]
            d = _json(hit[-1]) if hit else None
            if isinstance(d, dict) and isinstance(d.get(key), list):
                pieces = len(d[key])
                break
    n = pieces or 0
    if plan is not None:
        n = max(1, n) + sum(1 for e in plan.get("inserts") or []
                            if isinstance(e, dict) and e.get("kind") in FULL_FRAME and not e.get("transparent"))
    return n


def markers(ep: Path, v: int | None) -> list[dict]:
    """Findings with a time from the Critic's cut check of this version (else the newest): error, warning, note."""
    reps = _versions(ep / "review", "cut-check")
    if not reps:
        return []
    path = next((p for n, p in reversed(reps) if n == v), reps[-1][1])
    data = _json(path)
    out = []
    for f in (data.get("findings") if isinstance(data, dict) else None) or []:
        if not isinstance(f, dict):
            continue
        level = LEVELS.get(str(f.get("level") or "").lower())
        try:
            t = float(f.get("time", f.get("t")))
        except (TypeError, ValueError):
            continue
        if level:
            out.append({"t": round(t, 2), "level": level, "text": str(f.get("text") or f.get("id") or "")})
    return sorted(out, key=lambda m: m["t"])


def facts(pack, project: dict) -> list[str]:
    """Style chips from the pack: captions, cuts a minute, loudness (a Short's own values where the pack has them)."""
    short = project.get("kind") == "short"

    def val(key: str):
        v = pack.value(f"edit_style.shorts.{key}") if short else None
        return v if v is not None else pack.value(f"edit_style.{key}")

    out = []
    captions = val("captions")
    if isinstance(captions, str) and captions in CAPTIONS:
        out.append(CAPTIONS[captions])
    for key, fmt in (("pace_cuts_per_minute", "{:g} cuts a minute"), ("loudness_lufs", "{:g} LUFS")):
        try:
            out.append(fmt.format(float(val(key))))
        except (TypeError, ValueError):
            pass
    return out


def cut(episode: str, ep: Path, pack, project: dict) -> dict | None:
    """MediaCut: the newest cut with its frames and peaks (pending while they are made), markers and facts."""
    video = cut_source(ep)
    if video is None:
        return None
    v = vnum(video.name)
    data = strip(ep, video)
    d = strip_dir(ep, video)
    frames = [{"t": f["t"], "url": url(episode, d / f["file"])} for f in (data or {}).get("frames") or []
              if (d / f["file"]).is_file()]
    secs = duration(video) or (data or {}).get("seconds") or 0.0
    return {"version": f"v{v}" if v is not None else "", "seconds": round(float(secs), 2), "shots": shots(ep, video, v),
            "frames": frames, "peaks": list((data or {}).get("peaks") or []), "markers": markers(ep, v),
            "facts": facts(pack, project), "pending": data is None}


# ---- 3D scenes ------------------------------------------------------------------------------------------------------
def _insert_outputs(plan_path: Path, raw: dict, threes: list[dict], ep: Path, pack, project: dict) -> dict:
    """id -> (frames folder, clip, frames to render) of each 3D insert. The plan decides (its hash names the folder);
    a plan the renderer cannot load falls back to the newest render/inserts/<id>-<hash>/ folder."""
    try:
        from .render.plan import Plan
        plan = Plan(plan_path, pack=pack, episode_dir=ep)
        return {x.id: (x.out_dir, x.clip, x.render_frames) for x in plan.of_kind("3d")}
    except Exception:  # noqa: BLE001 - a plan with a missing template or words file still has its rendered frames
        pass
    from .render.plan import EXTRA_FRAMES
    fps = int(raw.get("fps") or project.get("fps") or 25)
    out = {}
    for e in threes:
        iid = str(e.get("id") or "")
        try:
            total = round(float(e["end"]) * fps) - round(float(e["start"]) * fps) + EXTRA_FRAMES
        except (KeyError, TypeError, ValueError):
            total = 0
        dirs = [d for d in _subdirs(ep / "render" / "inserts") if re.match(rf"^{re.escape(iid)}-[0-9a-f]{{10}}$", d.name)]
        d = max(dirs, key=_mtime) if dirs else None
        out[iid] = (d, Path(str(d) + ".mp4") if d else None, total)
    return out


def _frames(d: Path | None) -> tuple[int, Path | None]:
    """Rendered frames (NNNN.png) in a folder and the newest of them."""
    n, newest = 0, None
    if d is None:
        return 0, None
    try:
        with os.scandir(d) as it:
            for e in it:
                if _FRAME.match(e.name):
                    n += 1
                    mt = e.stat().st_mtime
                    if newest is None or mt > newest[0]:
                        newest = (mt, e.path)
    except OSError:
        return 0, None
    return n, Path(newest[1]) if newest else None


def _rendering_3d(episode: str) -> bool:
    """A running job of the episode says it renders 3D, or a rented machine of the episode is live."""
    with db.conn() as c:
        jobs = db.rows(c.execute("SELECT kind, doing, task FROM jobs WHERE episode = ? AND status = 'running'",
                                 (episode,)))
        live = c.execute(f"SELECT COUNT(*) AS n FROM rentals WHERE episode = ? AND status IN "
                         f"({','.join('?' for _ in LIVE_RENTALS)})", (episode, *LIVE_RENTALS)).fetchone()["n"]
    # an agent's task is a long prompt; only a tool job's task is the command it runs (render 3d ...)
    text = [f"{j.get('doing') or ''} {(j.get('task') or '') if j.get('kind') == 'tool' else ''}" for j in jobs]
    return bool(live) or any(_3D.search(t) for t in text)


def _scenes(episode: str, ep: Path, pack, project: dict) -> tuple[dict | None, tuple[int, int]]:
    """MediaScenes of the newest edit plan, and (frames rendered, frames to render) over its 3D inserts."""
    plans = _versions(ep / "edit", "plan")
    raw = _json(plans[-1][1]) if plans else None
    if not isinstance(raw, dict):
        return None, (0, 0)
    threes = [e for e in raw.get("inserts") or [] if isinstance(e, dict) and e.get("kind") == "3d" and e.get("id")]
    if not threes:
        return None, (0, 0)
    outs = _insert_outputs(plans[-1][1], raw, threes, ep, pack, project)
    rows = []
    for e in threes:
        iid = str(e["id"])
        out_dir, clip, total = outs.get(iid, (None, None, 0))
        have, newest = _frames(out_dir)
        done = bool(clip and clip.is_file()) or (total > 0 and have >= total)
        if newest is None:
            stills = [p for p in _files(ep / "render" / "probe") if re.match(rf"^{re.escape(iid)}-\d{{4}}\.png$", p.name)]
            newest = max(stills, key=_mtime) if stills else None
        try:
            secs = round(float(e["end"]) - float(e["start"]), 2)
        except (KeyError, TypeError, ValueError):
            secs = None
        rows.append({"e": e, "id": iid, "done": done, "have": have, "total": total, "img": newest, "secs": secs})
    active = _rendering_3d(episode)
    busy = {r["id"] for r in rows if active and not r["done"] and r["have"] > 0}
    if active and not busy:
        busy = {next((r["id"] for r in rows if not r["done"]), None)} - {None}
    items = []
    for r in rows:
        status = "done" if r["done"] else "rendering" if r["id"] in busy else "queued"
        if r["done"]:
            progress = 1.0
        elif r["total"] and (r["have"] or status == "rendering"):
            progress = round(r["have"] / r["total"], 3)
        else:
            progress = None
        e = r["e"]
        name = str(e.get("name") or str(e.get("scene") or r["id"]).replace("-", " ").capitalize())
        items.append({"id": r["id"], "name": name, "status": status, "progress": progress, "seconds": r["secs"],
                      "url": url(episode, r["img"]) if r["img"] else None})
    counts = (sum(min(r["have"], r["total"]) if not r["done"] else r["total"] for r in rows),
              sum(r["total"] for r in rows))
    return ({"title": str(raw.get("title") or "3D scenes"), "done": sum(1 for i in items if i["status"] == "done"),
             "total": len(items), "items": items}, counts)


# ---- the rented GPU -------------------------------------------------------------------------------------------------
def gpu(episode: str, frames: tuple[int, int] = (0, 0)) -> dict | None:
    """MediaGpu: the episode's open rental (all live machines of its newest compute session), or None."""
    try:
        from .compute import rentals, state
    except ImportError:
        return None
    with db.conn() as c:
        rows = db.rows(c.execute(f"SELECT * FROM rentals WHERE episode = ? AND status IN "
                                 f"({','.join('?' for _ in LIVE_RENTALS)}) ORDER BY id", (episode, *LIVE_RENTALS)))
    if not rows:
        return None
    newest = rows[-1]
    sid = rentals.detail(newest).get("session")
    rec = state.get_session(sid) if sid else None
    live = [r for r in rows if sid and rentals.detail(r).get("session") == sid] or [newest]
    every = [r for r in (rentals.get(i) for i in (rec or {}).get("rentals") or []) if r] or live
    gpus = sorted({str(rentals.detail(r).get("gpu") or "GPU").replace("_", " ") for r in live})
    name = " + ".join(gpus)
    if len(live) > 1 and len(gpus) == 1:
        name = f"{len(live)} × {name}"
    deadlines = [rentals.deadline_ts(r) for r in live if r.get("deadline")]
    minutes_left = max(0, int((max(deadlines) - state.now()) // 60)) if deadlines else None
    cap = (rec or {}).get("cap_usd")
    progress = None
    job = db.get("jobs", int(newest["job"])) if newest.get("job") else None
    if job and job.get("progress") is not None:
        progress = round(float(job["progress"]), 3)
    elif frames[1]:
        progress = round(frames[0] / frames[1], 3)
    return {"name": name, "started": min(str(r.get("started") or "") for r in live), "minutes_left": minutes_left,
            "so_far_usd": round(sum(rentals.cost_so_far(r) for r in every), 4),
            "cap_usd": round(float(cap), 4) if cap is not None else None, "progress": progress,
            "delete_note": DELETE_NOTE, "session": int(newest["id"]),
            "price_per_hour": round(sum(float(r.get("price_per_hour") or 0) for r in live), 3),
            "cap_per_gpu_hour": round(rentals.price_cap(), 2)}


# ---- the whole answer, the episode card, the job picture -------------------------------------------------------------
def episode_media(episode: str) -> dict:
    """GET /api/episodes/{id}/media: EpisodeMedia in web/src/api/types.ts."""
    from . import brand, episodes
    ep = paths.episode_dir(episode)
    try:
        project = episodes.read(episode)
    except (OSError, ValueError):
        project = {}
    pack = brand.load()
    scenes, frames = _scenes(episode, ep, pack, project)
    return {"thumbnails": thumbnails(episode), "cut": cut(episode, ep, pack, project), "scenes": scenes,
            "gpu": gpu(episode, frames), "cover_preview": episodes.cover(episode),
            "imported": bool(project.get("legacy"))}


def _image_of(episode: str, rel: str | None) -> str | None:
    if not rel or Path(rel).suffix.lower() not in IMAGES:
        return None
    try:
        p = paths.inside(paths.episode_dir(episode), rel)
    except ValueError:
        return None
    return url(episode, p) if p.is_file() else None


def needs(episode: str) -> dict | None:
    """Episode.needs: the first open card with up to three small pictures (thumbnail variants, the 3D frames of a
    spend card, else the card's own image)."""
    with db.conn() as c:
        card = db.row(c.execute("SELECT * FROM cards WHERE episode = ? AND status = 'open' ORDER BY id LIMIT 1",
                                (episode,)).fetchone())
    if not card:
        return None
    images: list[str] = []
    try:
        if card["kind"] == "thumbnail":
            images = [t["url"] for t in thumbnails(episode)]
        elif card["kind"] == "spend":
            from . import brand, episodes
            sc, _ = _scenes(episode, paths.episode_dir(episode), brand.load(), episodes.read(episode))
            images = [i["url"] for i in (sc or {}).get("items", []) if i["url"]]
    except (OSError, ValueError, KeyError):
        images = []
    if not images and isinstance(card.get("data"), dict) and isinstance(card["data"].get("images"), list):
        images = [u for u in card["data"]["images"] if isinstance(u, str)]   # motion cards name their pictures
    if not images:
        images = [u for u in (_image_of(episode, card.get("preview")) or _image_of(episode, card.get("file")),) if u]
    return {"card": int(card["id"]), "kind": card["kind"], "title": card["title"], "images": images[:3]}


def _scan(d: str) -> tuple[tuple[float, str] | None, tuple[str, ...]]:
    """(newest image, subfolders) of one folder, cached until the folder's mtime changes (a new file changes it)."""
    try:
        m = os.stat(d).st_mtime_ns
    except OSError:
        return None, ()
    hit = _dirs.get(d)
    if hit and hit[0] == m:
        return hit[1], hit[2]
    newest, subs = None, []
    try:
        with os.scandir(d) as it:
            for k, e in enumerate(it):
                if k >= 5000:
                    break
                if e.name.startswith("."):
                    continue
                if e.is_dir(follow_symlinks=False):
                    subs.append(e.path)
                elif os.path.splitext(e.name)[1].lower() in IMAGES and not _REF.match(e.name):
                    mt = e.stat().st_mtime
                    if newest is None or mt > newest[0]:
                        newest = (mt, e.path)
    except OSError:
        return None, ()
    with _lock:
        if len(_dirs) > 4096:
            _dirs.clear()
        _dirs[d] = (m, newest, tuple(sorted(subs)))
    return newest, tuple(sorted(subs))


def job_preview(j: dict) -> str | None:
    """Activity.preview: the newest image in the job's episode written since the job started (render frames,
    thumbnail drafts, strip frames), for running and waiting jobs. A bounded scan of a few folders, cached by mtime."""
    try:
        if j.get("status") not in ("running", "waiting") or not j.get("episode") or str(j["episode"]).startswith("_"):
            return None
        started = db.parse_time(j.get("started"))
        if started is None:
            return None
        ep = paths.episode_dir(j["episode"])
        best, seen = None, 0
        todo = [(str(ep / name), 0, prefix) for name, prefix in SCAN_ROOTS.get(j.get("step") or "", ALL_ROOTS)]
        while todo and seen < 300:
            d, depth, prefix = todo.pop()
            seen += 1
            newest, subs = _scan(d)
            if newest and (best is None or newest[0] > best[0]):
                best = newest
            if depth < 4:
                todo += [(s, depth + 1, None) for s in subs if prefix is None or os.path.basename(s).startswith(prefix)]
        if best is None or best[0] < started - 1:
            return None
        return url(j["episode"], Path(best[1]))
    except Exception:  # noqa: BLE001 - the activity line must show even when a folder cannot be read
        return None
