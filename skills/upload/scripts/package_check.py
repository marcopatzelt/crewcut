#!/usr/bin/env python3
"""Check an episode's upload package before the publish card (skill: skills/upload).

The package is export/upload.json in the episode folder. Paths inside it are relative to the episode folder:

  {"title": "...", "description": "...", "tags": ["..."], "video": "export/<id>-v004-final.mp4",
   "captions": [{"file": "export/<id>-en.srt", "language": "en"}], "thumbnail": "graphics/thumbnail/a.jpg",
   "category_id": 28, "default_language": "en", "default_audio_language": "en", "privacy": "private",
   "publish_at": null, "made_for_kids": false, "paid_promotion": false, "contains_synthetic_media": false,
   "synthetic_reason": "...", "playlist": null,
   "endscreen_video": null, "names": ["ToolName"], "ab_test": {"titles": ["..."], "thumbnails": ["..."]}}

The keys match what `crewcut youtube upload` sends (crewcut/youtube/upload.py). Limits come from YouTube (hard) and from the style pack (channel.json "upload", "title"). The title goes through
skills/title/scripts/title_check.py.

  python3 skills/upload/scripts/package_check.py <episode folder or id> [--online] [--json]

  --online   also fetch the description's main link (HTTP status only).

Exit: 0 = no error, 1 = at least one error, 2 = wrong call.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TITLE_CHECK = HERE.parents[1] / "title" / "scripts" / "title_check.py"

# YouTube's own limits.
MAX_DESCRIPTION = 5000      # bytes (UTF-8), YouTube API limit
MAX_TAG_CHARS = 500
MAX_HASHTAGS_HARD = 15        # more than 15 and YouTube ignores all hashtags of the video
MAX_THUMB_BYTES = 2 * 1024 * 1024
THUMB_MIN_WIDTH = 640
CHAPTER = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(\S.*)$")
DASH = re.compile(r"[–—]")
SRT_TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*$")
# Known speech-to-text inventions in silence or music (Whisper). Not taste: artefacts to delete.
HALLUCINATION = re.compile(
    r"untertitel(?:ung)?\s+(?:des|im auftrag des|von)\s+(?:zdf|wdr|swr|ndr|br|mdr|ard)|\b(?:zdf|wdr|swr|ndr|ard),?\s+20\d\d\b|"
    r"amara\.org|subtitles by|sous-titres réalisés par|sottotitoli (?:creati|a cura) |transcribed by", re.I)
ASPECT = {"landscape": 16 / 9, "portrait": 9 / 16, "square": 1.0}


def _brand():
    try:
        from crewcut import brand
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import brand
    return brand


@functools.lru_cache(maxsize=1)
def load_title_check():
    spec = importlib.util.spec_from_file_location("title_check", TITLE_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Report:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, area: str, level: str, text: str):
        self.rows.append({"area": area, "level": level, "text": text})

    def count(self, level: str) -> int:
        return sum(1 for r in self.rows if r["level"] == level)


def seconds(t: str) -> int:
    s = 0
    for x in t.split(":"):
        s = s * 60 + int(x)
    return s


def pack_level(pack, key: str, default: str = "off") -> str:
    v = pack.value(f"channel.upload.checks.{key}", default)
    return v if v in ("error", "warn", "hint") else "off"


# ---------- title ----------
def check_title(r: Report, title: str, pack, names: list[str]):
    if not title:
        r.add("title", "error", "No title.")
        return
    erg = load_title_check().check_title(title, pack, names)
    r.add("title", "ok" if erg["status"] == "ok" else "error",
          f'"{title}": {erg["chars"]} characters, {"passes" if erg["status"] == "ok" else "fails"} the title check '
          '(skills/title).')
    for f in erg["findings"]:
        if f["level"] in ("error", "warn"):
            r.add("title", f["level"], f["text"])


# ---------- description and chapters ----------
def _lines(text: str) -> list[str]:
    return [" ".join(z.split()) for z in text.splitlines() if z.strip()]


def check_footer(r: Report, text: str, pack):
    """channel.json upload.description_footer: a file in the style pack folder (about the creator and the company)
    that ends every description word for word. Blank lines and spaces may differ; words may not."""
    name = pack.value("channel.upload.description_footer")
    if not name:
        return
    p = Path(pack.dir) / name
    if not p.is_file():
        r.add("description", "error", f"The footer file {name} is missing in the style pack (channel.json "
              "upload.description_footer).")
        return
    want, have = _lines(p.read_text(encoding="utf-8")), _lines(text)
    if not want:
        return
    n = len(want)
    if any(have[i:i + n] == want for i in range(len(have) - n + 1)):
        r.add("description", "ok", f"Footer from {name} is complete.")
    else:
        miss = next((z for z in want if z not in have), want[0])
        r.add("description", "error", f'The footer from {name} is missing or changed (first difference: "{miss[:60]}"). '
              "Paste the file word for word near the end.")


def check_description(r: Report, text: str, pack, duration: float | None = None):
    n = len((text or "").encode("utf-8"))
    if not text:
        r.add("description", "error", "No description.")
        return
    if n > MAX_DESCRIPTION:
        r.add("description", "error", f"{n} bytes: YouTube allows at most {MAX_DESCRIPTION}.")
    elif n > MAX_DESCRIPTION - 500:
        r.add("description", "warn", f"{n} bytes: close to the limit of {MAX_DESCRIPTION}.")
    else:
        r.add("description", "ok", f"{n} of {MAX_DESCRIPTION} bytes.")
    if "<" in text or ">" in text:
        r.add("description", "error", 'Contains "<" or ">". YouTube rejects these characters (forgotten placeholder?).')
    lv = pack_level(pack, "dash")
    if lv != "off" and DASH.search(text):
        r.add("description", lv, "Dash in the description (channel.json upload.checks.dash).")
    lines = [z for z in text.splitlines() if z.strip()]
    main = pack.value("channel.upload.main_link")
    if main:
        within = int(pack.value("channel.upload.link_within_lines", 3))
        idx = next((i for i, z in enumerate(lines) if main in z), None)
        if idx is None:
            r.add("description", "error", f"The main link ({main}...) is missing (channel.json upload.main_link).")
        elif idx >= within:
            r.add("description", "error", f"The main link is in line {idx + 1}; it belongs in the first {within} lines. "
                  "YouTube shows about 150 characters before 'more'.")
        else:
            pos = text.find(main)
            lv2 = "hint" if pos > 150 else "ok"
            r.add("description", lv2, f"Main link in line {idx + 1}, character {pos + 1}.")
    for req in pack.value("channel.upload.required_text", []) or []:
        if req.lower() not in text.lower():
            r.add("description", "warn", f'"{req}" is missing (channel.json upload.required_text).')
    check_footer(r, text, pack)
    tags = re.findall(r"(?<!\S)#[^\W_][\w]*", text)
    hmax = int(pack.value("channel.upload.hashtags_max", 3))
    if len(tags) > MAX_HASHTAGS_HARD:
        r.add("description", "error", f"{len(tags)} hashtags: above {MAX_HASHTAGS_HARD} YouTube ignores all of them.")
    elif len(tags) > hmax:
        r.add("description", "hint", f"{len(tags)} hashtags; the pack uses {hmax} (the first 3 show above the title).")
    check_chapters(r, text, duration)


def chapters(text: str) -> list[tuple[int, str, str]]:
    out = []
    for z in (text or "").splitlines():
        m = CHAPTER.match(z)
        if m:
            out.append((seconds(m.group(1)), m.group(1), m.group(2)))
    return out


def check_chapters(r: Report, text: str, duration: float | None = None):
    kap = chapters(text)
    if not kap:
        r.add("chapters", "hint", "No chapters. For videos with parts they help viewers jump.")
        return
    problems = 0

    def bad(msg):
        nonlocal problems
        r.add("chapters", "error", msg)
        problems += 1

    if kap[0][0] != 0:
        bad(f"The first chapter starts at {kap[0][1]}. YouTube needs 0:00.")
    if len(kap) < 3:
        bad(f"Only {len(kap)} chapters. YouTube needs at least 3.")
    for a, b in zip(kap, kap[1:], strict=False):
        if b[0] <= a[0]:
            bad(f"{b[1]} does not come after {a[1]}.")
        elif b[0] - a[0] < 10:
            bad(f"The chapter at {a[1]} is {b[0] - a[0]} s long. YouTube needs at least 10 s.")
    if duration is not None:
        if kap[-1][0] >= duration:
            bad(f"The last chapter {kap[-1][1]} starts after the end of the video ({duration:.0f} s).")
        elif duration - kap[-1][0] < 10:
            bad(f"The last chapter is {duration - kap[-1][0]:.0f} s long. YouTube needs at least 10 s.")
    if not problems:
        r.add("chapters", "ok", f"{len(kap)} chapters, start 0:00, each at least 10 s"
              + ("." if duration else " (video length not checked)."))


# ---------- tags ----------
def youtube_tag_length(tags: list[str]) -> int:
    """YouTube counts a tag with a space as if it had quotes around it, plus one comma between tags."""
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def check_tags(r: Report, tags: list[str], title: str, names: list[str], pack):
    tags = [t.strip() for t in tags or [] if t and t.strip()]
    if not tags:
        r.add("tags", "warn", "No tags. They help a little, mostly for misspelled searches.")
        return
    n = youtube_tag_length(tags)
    if n > MAX_TAG_CHARS:
        r.add("tags", "error", f"{n} characters by YouTube's count: the limit is {MAX_TAG_CHARS}.")
    else:
        r.add("tags", "ok", f"{len(tags)} tags, {n} of {MAX_TAG_CHARS} characters by YouTube's count.")
    lo, hi = int(pack.value("channel.upload.tags_min", 5)), int(pack.value("channel.upload.tags_max", 15))
    if len(tags) < lo:
        r.add("tags", "warn", f"Only {len(tags)} tags; the pack wants {lo} to {hi}.")
    elif len(tags) > hi:
        r.add("tags", "hint", f"{len(tags)} tags; the pack wants {lo} to {hi}. More rarely helps.")
    seen, double = set(), []
    for t in tags:
        if t.lower() in seen:
            double.append(t)
        seen.add(t.lower())
    if double:
        r.add("tags", "warn", f"Duplicate tags: {', '.join(double)}.")
    if any("<" in t or ">" in t for t in tags):
        r.add("tags", "error", 'A tag contains "<" or ">". YouTube rejects that.')
    for name in names:
        if name and name.lower() in (title or "").lower() and not any(name.lower() in t.lower() for t in tags):
            r.add("tags", "warn", f'"{name}" is in the title but in no tag.')


# ---------- captions ----------
def check_srt_text(r: Report, text: str, duration: float | None = None, names: list[str] = (), area="captions"):
    blocks = [b for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()) if b.strip()]
    errors, cues, last = 0, [], -1.0
    for i, b in enumerate(blocks, 1):
        z = b.split("\n")
        if len(z) < 3 or not z[0].strip().isdigit() or not SRT_TIME.match(z[1].strip()):
            r.add(area, "error", f"Block {i} is not a valid SRT block: {z[0][:40]!r}")
            errors += 1
            if errors > 5:
                break
            continue
        if int(z[0]) != i:
            r.add(area, "error", f"Block {i} has the number {z[0].strip()}.")
            errors += 1
        g = [int(x) for x in SRT_TIME.match(z[1].strip()).groups()]
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        if e <= a:
            r.add(area, "error", f"Block {i}: the end is not after the start.")
            errors += 1
        if a < last - 0.001:
            r.add(area, "warn", f"Block {i} starts before block {i - 1} ends (overlap).")
        last = e
        cues.append((a, e, " ".join(z[2:]).strip()))
    if not cues:
        r.add(area, "error", "No readable captions.")
        return
    if duration is not None and cues[-1][1] > duration + 1.0:
        r.add(area, "error", f"The last caption ends at {cues[-1][1]:.1f} s, the video at {duration:.1f} s.")
        errors += 1
    if cues[0][0] > 10:
        r.add(area, "warn", f"The first caption starts at {cues[0][0]:.1f} s.")
    for a_, _e, t_ in cues:
        if HALLUCINATION.search(t_):
            r.add(area, "error", f'Speech-to-text invention at {a_:.1f} s: "{t_[:60]}". Delete the block.')
            errors += 1
    allt = " ".join(c[2] for c in cues)
    for name in names:
        if name and name not in allt:
            r.add(area, "warn", f'"{name}" is not written exactly like this in the captions. Check the spelling.')
    if not errors:
        r.add(area, "ok", f"{len(cues)} blocks, times ascending, end {cues[-1][1]:.1f} s"
              + (f" (video {duration:.1f} s)." if duration is not None else "."))


# ---------- thumbnail ----------
def image_size(path: Path) -> tuple[str | None, tuple[int, int] | None]:
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return "PNG", struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return "GIF", struct.unpack("<HH", head[6:10])
        if head[:2] != b"\xff\xd8":
            return None, None
        f.seek(2)
        while True:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            while b == b"\xff":
                b = f.read(1)
            if not b:
                return "JPEG", None
            marker = b[0]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            length = struct.unpack(">H", f.read(2))[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                f.read(1)
                h, w = struct.unpack(">HH", f.read(4))
                return "JPEG", (w, h)
            f.seek(length - 2, 1)


def check_thumbnail(r: Report, path: Path):
    size = path.stat().st_size
    kind, wh = image_size(path)
    if kind is None:
        r.add("thumbnail", "error", "Not a JPG, PNG or GIF.")
        return
    if wh is None:
        r.add("thumbnail", "error", "Image size not readable.")
        return
    ok = True
    if size >= MAX_THUMB_BYTES:
        r.add("thumbnail", "error", f"{size / 1e6:.2f} MB: YouTube needs less than 2 MB.")
        ok = False
    if wh[0] < THUMB_MIN_WIDTH:
        r.add("thumbnail", "error", f"{wh[0]} px wide: YouTube needs at least {THUMB_MIN_WIDTH}.")
        ok = False
    elif abs(wh[0] / wh[1] - 16 / 9) > 0.02:
        r.add("thumbnail", "warn", f"{wh[0]}x{wh[1]} is not 16:9. YouTube recommends 1280x720.")
        ok = False
    elif tuple(wh) != (1280, 720):
        r.add("thumbnail", "hint", f"{wh[0]}x{wh[1]}: YouTube recommends 1280x720.")
    if ok:
        r.add("thumbnail", "ok", f"{kind} {wh[0]}x{wh[1]}, {size / 1024:.0f} KB.")


# ---------- video ----------
def check_video(r: Report, path: Path, pack) -> float | None:
    if not shutil.which("ffprobe"):
        r.add("video", "warn", "ffprobe is missing. Video not checked.")
        return None
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if p.returncode:
        r.add("video", "error", f"ffprobe cannot read the file: {p.stderr.strip()[:200]}")
        return None
    info = json.loads(p.stdout)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    if not v:
        r.add("video", "error", "No video stream.")
        return duration
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    fmt = pack.value("edit_style.format", "landscape")
    want = ASPECT.get(fmt)
    if want and h and abs(w / h - want) > 0.02:
        r.add("video", "error", f"{w}x{h} does not match the format {fmt} (edit-style.json).")
    if min(w, h) < 720:
        r.add("video", "warn", f"{w}x{h}: below 720p.")
    if not a:
        r.add("video", "error", "No audio stream.")
    if v.get("codec_name") not in ("h264", "hevc", "vp9", "av1"):
        r.add("video", "hint", f"Video codec {v.get('codec_name')}: H.264 is the safe choice.")
    if a and v and w and h:
        r.add("video", "ok", f"{w}x{h}, {v.get('codec_name')}, audio {a.get('codec_name')}, {duration:.1f} s.")
    return duration


# ---------- settings and schedule ----------
def check_settings(r: Report, up: dict, pack, now: dt.datetime | None = None):
    now = now or dt.datetime.now(dt.UTC)
    if not isinstance(up.get("made_for_kids"), bool):
        r.add("settings", "error", "made_for_kids is not set. YouTube needs this declaration on every upload.")
    if not isinstance(up.get("contains_synthetic_media"), bool) or not (up.get("synthetic_reason") or "").strip():
        r.add("settings", "error", "contains_synthetic_media needs an answer (true or false) and synthetic_reason one "
              "sentence why. The publish card shows both.")
    if not isinstance(up.get("paid_promotion"), bool):
        r.add("settings", "warn", "paid_promotion is not set.")
    cat = up.get("category_id", pack.value("channel.category_id"))
    if not isinstance(cat, int):
        r.add("settings", "error", "category_id is missing (channel.json category_id).")
    if not (up.get("default_language") and up.get("default_audio_language")):
        lang = pack.value("channel.language")
        r.add("settings", "warn", "default_language or default_audio_language is missing"
              + (f" (channel.json says {lang!r})." if lang else "."))
    privacy = up.get("privacy", pack.value("channel.default_privacy", "private"))
    if privacy not in ("private", "unlisted", "public"):
        r.add("settings", "error", f"privacy {privacy!r} must be private, unlisted or public.")
    at = up.get("publish_at")
    if at:
        try:
            when = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        except ValueError:
            r.add("schedule", "error", f"publish_at {at!r} is not an ISO time.")
            return
        if when.tzinfo is None:
            r.add("schedule", "error", "publish_at has no time zone.")
            return
        if when <= now:
            r.add("schedule", "error", f"publish_at {at} is in the past.")
        if privacy != "private":
            r.add("schedule", "hint", "With publish_at the video is uploaded as private and YouTube makes it public "
                  "at that time; privacy is ignored.")
        want = pack.value("channel.upload.publish_time")
        if want and when.strftime("%H:%M") != want:
            r.add("schedule", "hint", f"publish_at is {when.strftime('%H:%M')}; the channel's fixed time is {want} "
                  f"({pack.value('channel.upload.timezone') or 'its time zone'}).")
        if not [x for x in r.rows if x["area"] == "schedule"]:
            r.add("schedule", "ok", f"Scheduled for {at}.")


def http_status(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "crewcut-package-check"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:  # noqa: BLE001
        return f"unreachable ({e.__class__.__name__})"


# ---------- whole package ----------
def resolve_episode(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        return p
    try:
        from crewcut import paths
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import paths
    return paths.episode_dir(arg)


def check_package(ep: Path, up: dict, pack, online: bool = False, now: dt.datetime | None = None) -> Report:
    r = Report()
    names = [n for n in up.get("names") or [] if n]

    def file_of(key_path: str | None, area: str, required: bool = True) -> Path | None:
        if not key_path:
            if required:
                r.add("files", "error", f"{area}: no file named in upload.json.")
            return None
        p = (ep / key_path).resolve()
        if ep.resolve() not in p.parents:
            r.add("files", "error", f"{area}: {key_path} is outside the episode folder.")
            return None
        if not p.is_file():
            r.add("files", "error", f"{area}: {key_path} does not exist.")
            return None
        return p

    video = file_of(up.get("video"), "video")
    duration = check_video(r, video, pack) if video else None
    check_title(r, up.get("title", ""), pack, names)
    check_description(r, up.get("description", ""), pack, duration)
    check_tags(r, up.get("tags") or [], up.get("title", ""), names, pack)
    caps = up.get("captions") or []
    if not caps:
        r.add("captions", "warn", "No own captions. Automatic captions often misspell names.")
    for c in caps:
        p = file_of(c.get("file"), "captions")
        if p:
            try:
                check_srt_text(r, p.read_text(encoding="utf-8-sig"), duration, names)
            except UnicodeDecodeError:
                r.add("captions", "error", f"{c.get('file')} is not UTF-8.")
    thumb = file_of(up.get("thumbnail"), "thumbnail")
    if thumb:
        check_thumbnail(r, thumb)
    check_settings(r, up, pack, now)
    ab = up.get("ab_test") or {}
    want = int(pack.value("channel.title.variants", 3))
    if not ab.get("titles") and not ab.get("thumbnails"):
        r.add("a/b test", "hint", f"No test variants. The pack plans {want} for every video.")
    for t in ab.get("titles") or []:
        erg = load_title_check().check_title(t, pack, names)
        if erg["errors"]:
            r.add("a/b test", "error", f'Variant "{t}" fails the title check.')
    if online:
        main = pack.value("channel.upload.main_link")
        m = re.search(re.escape(main) + r"\S*", up.get("description", "")) if main else None
        if m:
            st = http_status(m.group(0).rstrip(".,)"))
            r.add("online", "ok" if st == "200" else "error", f"{m.group(0)}: HTTP {st}.")
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check an episode's upload package (export/upload.json).")
    ap.add_argument("episode", help="episode folder or episode id")
    ap.add_argument("--file", default="export/upload.json", help="package file inside the episode folder")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--online", action="store_true", help="fetch the main link of the description")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        ep = resolve_episode(a.episode)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    pf = ep / a.file
    if not pf.is_file():
        print(f"No package: {pf} does not exist.", file=sys.stderr)
        return 1
    up = json.loads(pf.read_text(encoding="utf-8"))
    pack = _brand().load(a.pack)
    r = check_package(ep, up, pack, a.online)
    if a.json:
        print(json.dumps(r.rows, ensure_ascii=False, indent=1))
    else:
        area = None
        for row in r.rows:
            if row["area"] != area:
                print(f"\n== {row['area']}")
                area = row["area"]
            print(f"  {row['level']:<5} {row['text']}")
        print(f"\nResult: {r.count('error')} errors, {r.count('warn')} warnings. "
              + ("Not ready for the publish card." if r.count("error") else "Ready for the publish card."))
    return 1 if r.count("error") else 0


if __name__ == "__main__":
    sys.exit(main())
