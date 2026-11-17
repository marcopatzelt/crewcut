#!/usr/bin/env python3
"""Build the sample media of the CI pictures (README, docs, landing page) from the author's own channel.

Reads two source folders (never writes there):

  mock    the design mock: assets/3d/, assets/frames/, assets/thumbs/, assets/thumbs-en/, wallpapers/web/
  studio  the video studio: episodes/<key>-*/... (finished long videos and Shorts exports)

Writes (inside this repo only):

  tests/web-sample/public/media/**  web-sized JPEGs (rebuilt from scratch on every run; never in the app or image)
  web/public/wallpapers/*.jpg  wallpapers, copied unchanged (CREDITS.md there is kept)
  tests/web-sample/media.json       the manifest the sample fixtures read

Rules every picture follows (see the PLAN below for the exact crop of each one):
  - No German text in a picture. Frames come from moments with no text overlay; 3D frames of the commercial are
    cropped above their German caption and clear of the logo; thumbnails come from assets/thumbs-en/ (English).
    The German assets/thumbs/ and assets/yt/ pictures are never used. If thumbs-en/ is missing, a thumbnail falls
    back to a text-free frame (english: false, the app draws the English title over it); ab-012-C-en from
    assets/thumbs/ is the one English exception.
  - No third-party private content (no tweets, no other people, no third-party designs).
  - Sizes: thumbnails and frames 640 px wide, plus 1280 px for the big ones (never upscaled: a smaller source gives
    a smaller "large" file); Shorts covers 540x960; film-strip frames 320 px wide; JPEG quality 82, progressive,
    metadata stripped.

Needs `magick` (ImageMagick 7) and `ffmpeg` on PATH.

Usage:
  CREWCUT_SAMPLE_MOCK=<mock dir> CREWCUT_SAMPLE_STUDIO=<studio dir> python3 tools/sample/build_media.py
  python3 tools/sample/build_media.py --mock <dir> --studio <dir> [--repo <dir>] [--sheet out.jpg]
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

QUALITY = 82
MEDIA_URL = "sample/media"  # relative to the root the CI picture server serves (tools/ci/sample_server.mjs)
WALL_URL = "wallpapers"

# Crops are on the source picture: (width, height, x, y). None = the whole picture.
# The 3D frames are 1920x1080. Their German caption starts at about y=740 (facade, waterfront) or y=840 (street,
# row houses); the "Lenz & Hagen" logo sits top right (facade) or top left (row houses, living room).
CROP_WATERFRONT = (1280, 720, 320, 0)  # top part: sky, church spire, river front; caption below y=720
CROP_FACADE = (1280, 720, 0, 0)  # top left: logo (x>=1400) and caption (y>=744) are outside
CROP_STREET = (1440, 810, 240, 0)  # top part; caption below y=810
CROP_ROWHOUSES = (1440, 810, 480, 0)  # right of the logo (x<=440), above the caption (y>=840)
CROP_AVATAR = (500, 500, 670, 150)  # the author's face in episode 012 at 14 s (1920x1080)

# Long videos in the studio (relative to the studio folder).
VIDEO_012 = "episodes/012-claude-website-100-mal/05-graphics/craft-v005/012-claude-website-100-mal-v005-final.mp4"
VIDEO_010 = "episodes/010-cli-anything/05-graphics/craft-v006/010-cli-anything-v006-final.mp4"
VIDEO_008 = "episodes/008-graphify/05-graphics/craft-v007/008-graphify-v007-final.mp4"

# Film strip of episode 012 (cut v005, 4:34): seconds where the frame shows only the author, with no text overlay
# (217 s shows the English chip "Taste Skill"). Every other part of 012 shows the German demo website, German
# keyword cards or third-party designs: those parts are left out. Checked frame by frame
# (one exact frame per second, ffmpeg -ss); the last second fades in a German end card, so it is not used.
STRIP_012 = [4, 14, 18, 71, 137, 141, 196, 215, 217, 258]

# Thumbnail spec: English file in assets/thumbs-en/ (same names as assets/thumbs/), and a text-free fallback.
# A fallback is ("frame", <mock path>) or ("video", <studio path>, <seconds>) or ("thumb", <mock path>, english).
EPISODES = [
    {
        "key": "012",
        "title_en": "Claude improves a website 100 times",
        "kind": "long",
        "cover": {"en": "yt-website-100.jpg", "fallback": ("video", VIDEO_012, 137)},
        "thumbs": [
            {"id": "A", "label": "Face right", "en": "ab-012-A.jpg", "fallback": ("video", VIDEO_012, 14)},
            {"id": "B", "label": "Face centered", "en": "ab-012-B.jpg", "fallback": ("video", VIDEO_012, 196)},
            {
                "id": "C",
                "label": "Face right, title top left",
                "en": "ab-012-C-en.jpg",
                "fallback": ("thumb", "assets/thumbs/ab-012-C-en.jpg", True),
            },
        ],
        "strip": STRIP_012,
        "scenes": [
            {"id": "s1", "name": "Rhine front", "src": "assets/3d/r3-waterfront.jpg", "crop": CROP_WATERFRONT,
             "large": True},
            {"id": "s2", "name": "Lounge chair", "src": "assets/3d/r3-chair.jpg", "crop": None},
            {"id": "s3", "name": "Bridge view", "src": "assets/3d/r3-interior-bridge.jpg", "crop": None},
            {"id": "s4", "name": "Facade", "src": "assets/3d/r3-facade.jpg", "crop": CROP_FACADE},
            {"id": "s5", "name": "Evening street", "src": "assets/3d/r3-street-evening.jpg", "crop": CROP_STREET},
        ],
    },
    {
        "key": "015",
        "title_en": "Thinking levels commercial",
        "kind": "commercial",
        "cover": {"fixed": ("crop", "assets/3d/r3-rowhouses.jpg", CROP_ROWHOUSES)},
    },
    {
        "key": "014",
        "title_en": "Use local AI privately: what really stays with you",
        "kind": "long",
        "cover": {"fixed": ("crop", "assets/frames/013-weights.jpg", None)},
    },
    {
        "key": "013",
        "title_en": "One prompt, a full game",
        "kind": "long",
        "cover": {"en": "yt-ganzes-spiel.jpg", "fallback": ("frame", "assets/frames/013-game-a.jpg")},
    },
    {
        "key": "011",
        "title_en": "Local AI is enough for $0.10",
        "kind": "long",
        "cover": {"en": "yt-lokale-ki.jpg", "fallback": ("frame", "assets/frames/011-marco.jpg")},
        "thumbs": [
            {"id": "A", "label": "Published", "en": "yt-lokale-ki.jpg", "fallback": None},
            {"id": "B", "label": "Price duel", "en": "ab-011-alt.jpg", "fallback": None},
        ],
    },
    {
        "key": "010",
        "title_en": "Claude operates any software in 19 minutes",
        "kind": "long",
        "cover": {"en": "yt-jede-software.jpg", "fallback": ("video", VIDEO_010, 7)},
    },
    {
        "key": "008",
        "title_en": "Graphify, measured: −20%, not −99%",
        "kind": "long",
        "cover": {"en": "yt-graphify.jpg", "fallback": ("video", VIDEO_008, 7)},
    },
]

# Shorts: the frame (seconds into the export) shows no text overlay at all; the app draws the English title.
SHORTS = [
    {"key": "S014", "t": 38, "from": "008", "title_en": "Graphify promises 71 times fewer tokens. I measured it"},
    {"key": "S013", "t": 5.5, "from": "013", "title_en": "Claude writes like an aircraft manual"},
    {"key": "S012", "t": 21, "from": "013", "title_en": "My old rules slowed Claude down"},
    {"key": "S011", "t": 28, "from": "013", "title_en": "What does a game by Claude cost?"},
    {"key": "S010", "t": 30, "from": "012", "title_en": "More rounds, worse website?"},
    {"key": "S009", "t": 10, "from": "012", "title_en": "Make it better, 100 times"},
    {"key": "S008", "t": 17, "from": "012", "title_en": "You can spot a Claude website at once"},
    {"key": "S007", "t": 4, "from": "012", "title_en": "This design skill impressed me"},
    {"key": "S005", "t": 29, "from": "011", "title_en": "Claude costs 78 cents, GLM only 10 cents"},
]

WALLPAPERS = ["green-dusk", "mint-dawn", "meadow-day", "golden-hills", "rhine-evening"]
WALL_DARK, WALL_LIGHT = "green-dusk", "mint-dawn"


def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{res.stderr.strip()}")


class Builder:
    def __init__(self, mock: Path, studio: Path, repo: Path):
        self.mock, self.studio, self.repo = mock, studio, repo
        self.media = repo / "tests/web-sample/public/media"
        self.tmp = Path(tempfile.mkdtemp(prefix="crewcut-sample-media-"))
        self.done: dict[str, str] = {}  # (source hash + operation) -> url, so a picture used twice is written once
        self.outputs: list[tuple[str, str]] = []  # (label, url) for the contact sheet
        self.thumbs_en = mock / "assets/thumbs-en"

    # -- primitives --------------------------------------------------------------------------------------------
    def _src_key(self, path: Path) -> str:
        return hashlib.sha1(path.read_bytes()).hexdigest()

    def image(self, src: Path, rel: str, width: int | None, crop=None, height: int | None = None,
              label: str = "") -> str:
        """Write src (optionally cropped) as a JPEG of the given width (or exact width x height) to media/rel."""
        if not src.is_file():
            sys.exit(f"missing source: {src}")
        key = f"{self._src_key(src)}|{crop}|{width}|{height}"
        if key in self.done:
            return self.done[key]
        out = self.media / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["magick", str(src)]
        if crop:
            w, h, x, y = crop
            cmd += ["-crop", f"{w}x{h}+{x}+{y}", "+repage"]
        if width and height:
            cmd += ["-resize", f"{width}x{height}^", "-gravity", "center", "-extent", f"{width}x{height}"]
        elif width:
            cmd += ["-resize", f"{width}x>"]  # never upscale
        cmd += ["-strip", "-interlace", "JPEG", "-sampling-factor", "4:2:0", "-quality", str(QUALITY), str(out)]
        run(cmd)
        url = f"{MEDIA_URL}/{rel}"
        self.done[key] = url
        self.outputs.append((label or rel, url))
        return url

    def video_frame(self, video_rel: str, t: float) -> Path:
        video = self.studio / video_rel
        if not video.is_file():
            sys.exit(f"missing video: {video}")
        out = self.tmp / f"{hashlib.sha1(f'{video_rel}@{t}'.encode()).hexdigest()}.png"
        if not out.exists():
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t}", "-i", str(video), "-frames:v", "1", str(out)])
        return out

    def short_video(self, key: str) -> str:
        for pattern in ("*-preview.mp4", "*-klein.mp4"):
            hits = sorted(glob.glob(str(self.studio / f"episodes/{key}-*/08-export/{pattern}")))
            if hits:
                return str(Path(hits[0]).relative_to(self.studio))
        sys.exit(f"no export found for Short {key}")

    # -- sources -----------------------------------------------------------------------------------------------
    def resolve(self, spec):
        """Return (source path, crop, english) for a thumbnail or cover spec."""
        if "fixed" in spec:
            _, rel, crop = spec["fixed"]
            return self.mock / rel, crop, False
        en = self.thumbs_en / spec["en"] if spec.get("en") else None
        if en and en.is_file():
            return en, None, True
        fb = spec.get("fallback")
        if fb is None:
            return None, None, False
        if fb[0] == "frame":
            return self.mock / fb[1], None, False
        if fb[0] == "thumb":
            return self.mock / fb[1], None, fb[2]
        if fb[0] == "video":
            return self.video_frame(fb[1], fb[2]), None, False
        raise ValueError(fb)

    # -- build -------------------------------------------------------------------------------------------------
    def build(self) -> dict:
        if self.media.exists():
            shutil.rmtree(self.media)
        notes: list[str] = []
        missing_en = [s for s in self._all_en_names() if not (self.thumbs_en / s).is_file()]
        if missing_en:
            notes.append("English thumbnails missing in assets/thumbs-en/: " + ", ".join(missing_en)
                         + ". Those covers and thumbnails are text-free frames (english: false; ab-012-C-en comes"
                         " from assets/thumbs/), or are left out (011 thumbs); rerun after they exist.")
        if len(missing_en) < len(self._all_en_names()):
            notes.append("The English thumbnails keep small German website text inside their embedded screenshots"
                         " (012 A/B/C, 010 task list): it comes from the thumbnails themselves.")

        manifest: dict = {"wallpapers": self.wallpapers(), "channel": self.channel()}
        episodes = []
        for ep in EPISODES:
            k = ep["key"]
            src, crop, english = self.resolve(ep["cover"])
            entry = {
                "key": k,
                "title_en": ep["title_en"],
                "kind": ep["kind"],
                "cover": self.image(src, f"episodes/{k}-cover.jpg", 640, crop, label=f"{k} cover"),
                "cover_large": self.image(src, f"episodes/{k}-cover-1280.jpg", 1280, crop, label=f"{k} cover 1280"),
                "cover_english": english,
            }
            if "thumbs" in ep:
                thumbs = []
                for th in ep["thumbs"]:
                    src, crop, english = self.resolve(th)
                    if src is None:
                        continue
                    thumbs.append({
                        "id": th["id"],
                        "label": th["label"],
                        "url": self.image(src, f"thumbs/{k}-{th['id']}.jpg", 640, crop, label=f"{k} thumb {th['id']}"),
                        "url_large": self.image(src, f"thumbs/{k}-{th['id']}-1280.jpg", 1280, crop,
                                                label=f"{k} thumb {th['id']} 1280"),
                        "english": english,
                    })
                entry["thumbs"] = thumbs
            if "strip" in ep:
                entry["frames"] = [
                    {"t": t, "url": self.image(self.video_frame(VIDEO_012, t), f"strip/{k}-{t:04d}.jpg", 320,
                                               label=f"{k} strip {t // 60}:{t % 60:02d}")}
                    for t in ep["strip"]
                ]
            if "scenes" in ep:
                scenes = []
                for sc in ep["scenes"]:
                    slug = sc["name"].lower().replace(" ", "-")
                    item = {
                        "id": sc["id"],
                        "name": sc["name"],
                        "url": self.image(self.mock / sc["src"], f"scenes/{sc['id']}-{slug}.jpg", 640, sc["crop"],
                                          label=f"{sc['id']} {sc['name']}"),
                    }
                    if sc.get("large"):
                        item["url_large"] = self.image(self.mock / sc["src"], f"scenes/{sc['id']}-{slug}-1280.jpg",
                                                       1280, sc["crop"], label=f"{sc['id']} {sc['name']} 1280")
                    scenes.append(item)
                entry["scenes"] = scenes
            episodes.append(entry)
        manifest["episodes"] = episodes

        shorts = []
        for sh in SHORTS:
            frame = self.video_frame(self.short_video(sh["key"]), sh["t"])
            shorts.append({
                "key": sh["key"],
                "title_en": sh["title_en"],
                "cover": self.image(frame, f"shorts/{sh['key']}.jpg", 540, None, height=960, label=sh["key"]),
                "from": sh["from"],
            })
        manifest["shorts"] = shorts

        notes += [
            "Only scene s1 (the hero) has url_large; s2-s5 are shown small, use url.",
            "Episode 014 cover comes from a 960 px frame, so its cover_large is 960 px wide (never upscaled).",
            "Episode 012 film strip: cut v005 (4:34); only frames of the author without German text overlays."
            " The 3D scenes are from the commercial (015), round 3.",
        ]
        manifest["notes"] = notes
        shutil.rmtree(self.tmp, ignore_errors=True)
        return manifest

    def _all_en_names(self) -> list[str]:
        names = []
        for ep in EPISODES:
            for spec in [ep["cover"], *ep.get("thumbs", [])]:
                if spec.get("en") and spec["en"] not in names:
                    names.append(spec["en"])
        return names

    def wallpapers(self) -> dict:
        dest = self.repo / "web/public" / WALL_URL
        dest.mkdir(parents=True, exist_ok=True)
        for name in WALLPAPERS:
            for size in (2560, 1280):
                src = self.mock / f"wallpapers/web/{name}-{size}.jpg"
                if not src.is_file():
                    sys.exit(f"missing wallpaper: {src}")
                shutil.copyfile(src, dest / src.name)
        return {
            "dark": f"{WALL_URL}/{WALL_DARK}-2560.jpg",
            "light": f"{WALL_URL}/{WALL_LIGHT}-2560.jpg",
            "dark_small": f"{WALL_URL}/{WALL_DARK}-1280.jpg",
            "light_small": f"{WALL_URL}/{WALL_LIGHT}-1280.jpg",
            "all": [{"name": n, "url": f"{WALL_URL}/{n}-2560.jpg", "url_small": f"{WALL_URL}/{n}-1280.jpg"}
                    for n in WALLPAPERS],
        }

    def channel(self) -> dict:
        return {
            "name": "STRIQ",
            "avatar": self.image(self.video_frame(VIDEO_012, 14), "channel/avatar.jpg", 256, CROP_AVATAR, height=256,
                                 label="channel avatar"),
        }

    def contact_sheet(self, path: Path) -> None:
        web_public = self.repo / "web/public"
        args = []
        sample_public = self.repo / "tests/web-sample/public"
        for label, url in self.outputs:
            args += ["-label", label, str(sample_public / url.removeprefix("sample/"))]
        for name in (WALL_DARK, WALL_LIGHT):
            args += ["-label", f"wallpaper {name}", str(web_public / WALL_URL / f"{name}-1280.jpg")]
        run(["magick", "montage", *args, "-tile", "6x", "-geometry", "300x300>+8+8", "-background", "#202124",
             "-fill", "white", "-pointsize", "15", str(path)])


def main() -> None:
    here = Path(__file__).resolve()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mock", default=os.environ.get("CREWCUT_SAMPLE_MOCK"), help="design mock folder")
    ap.add_argument("--studio", default=os.environ.get("CREWCUT_SAMPLE_STUDIO"), help="video studio folder")
    ap.add_argument("--repo", default=str(here.parents[2]), help="repo root (default: this script's repo)")
    ap.add_argument("--sheet", help="also write a labelled contact sheet of every output to this path")
    a = ap.parse_args()
    if not a.mock or not a.studio:
        ap.error("set --mock and --studio (or CREWCUT_SAMPLE_MOCK and CREWCUT_SAMPLE_STUDIO)")
    for tool in ("magick", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")

    b = Builder(Path(a.mock).resolve(), Path(a.studio).resolve(), Path(a.repo).resolve())
    manifest = b.build()
    out = b.repo / "tests/web-sample/media.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if a.sheet:
        b.contact_sheet(Path(a.sheet))
    total = sum(f.stat().st_size for f in b.media.rglob("*") if f.is_file())
    print(f"{len(b.outputs)} files, {total / 1e6:.2f} MB in {b.media.relative_to(b.repo)}; manifest {out.relative_to(b.repo)}")
    for n in manifest["notes"]:
        print("note:", n)


if __name__ == "__main__":
    main()
