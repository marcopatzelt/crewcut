#!/usr/bin/env python3
"""Check finished thumbnails before they go to YouTube, and show them at feed size.

  python3 skills/thumbnail/scripts/thumb_check.py IMAGE [IMAGE2 IMAGE3] [--title "Title"] [--text "text of image 1"]
          [--text "text of image 2"] … [--out DIR] [--convert] [--compare IMG …] [--pack DIR] [--no-faces]

Per image:
  ERROR  not JPG or PNG; not 16:9; smaller than 1280x720 (YouTube then scales every image of a test down to
         854x480); upload file not exactly 1280x720 or 2 MB and more; with --text: far more words than max_words
  CHECK  a colour from thumbnail.avoid_colors over 0.5 %; edge colour far from thumbnail.background; face position,
         size or count against thumbnail.json; with --text: more words than max_words, more numbers than max_numbers
  NOTE   accent colour share; no face found; text without a title word
  OK     everything else that was measured
Limits come from the style pack (thumbnail.json, colours from brand.json). The face check needs OpenCV and the YuNet
model (see SKILL.md); without them it says so and goes on.
--convert writes an upload copy <name>-1280x720.jpg next to the image (cover crop, JPEG) and checks it. Never overwrites.
Preview: DIR/preview-320.png and preview-160.png (320 px = home feed on a computer, 160 px = suggestions on a phone),
each image in a row with the --compare images (for example the channel's own best thumbnails).
Then the checklist from SKILL.md and the rules from rules/thumbnail.md. Exit 1 on any ERROR, 2 on usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
APP_ROOT = HERE.parents[2]
MAX_BYTES = 2 * 1024 * 1024
MONEY = re.compile(r"[€$£¥₹]")
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
YUNET = ["face_detection_yunet_2023mar.onnx", "yunet.onnx"]


def load_pack(pack_dir=None):
    try:
        from crewcut import brand
    except ImportError:
        sys.path.insert(0, str(APP_ROOT))
        from crewcut import brand
    return brand.load(pack_dir) if pack_dir else brand.load()


def font(size: int):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def hex_rgb(v: str) -> tuple[int, int, int]:
    v = v.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def colour_value(name_or_hex, pack) -> tuple[int, int, int] | None:
    """A brand colour name ('accent', 'ink') or a #RRGGBB value."""
    if not name_or_hex:
        return None
    if isinstance(name_or_hex, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", name_or_hex):
        return hex_rgb(name_or_hex)
    v = pack.value(f"brand.colors.{name_or_hex}") if pack is not None else None
    return hex_rgb(v) if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None


def limits(pack) -> dict:
    t = lambda k, d=None: pack.value(f"thumbnail.{k}", d)  # noqa: E731
    return {
        "face": t("face", True),
        "face_position": t("face_position", "any"),
        "face_min_area": t("face_min_area", 0.0),
        "max_faces": t("max_faces", 1),
        "max_words": t("max_words", 4),
        "max_numbers": t("max_numbers", 1),
        "avoid": t("avoid_colors", []) or [],
        "background": colour_value(t("background"), pack),
        "accent": colour_value("accent", pack),
    }


# ---------------------------------------------------------------- pure functions


def size_findings(w: int, h: int, nbytes: int, fmt: str | None) -> list[tuple[str, str]]:
    out = []
    if fmt not in ("JPEG", "PNG"):
        out.append(("ERROR", f"Format {fmt}. Upload only JPG or PNG."))
    if abs(w / h - 16 / 9) > 0.01 * 16 / 9:
        out.append(
            (
                "ERROR",
                f"{w}x{h} is not 16:9 ({w / h:.3f} instead of 1.778). Generate again in 16:9; cropping "
                "cuts text or the head.",
            )
        )
    if w < 1280 or h < 720:
        out.append(
            ("ERROR", f"{w}x{h} is smaller than 1280x720. In a test YouTube then scales every image down to 854x480.")
        )
    if not ((w, h) == (1280, 720) and nbytes < MAX_BYTES and fmt in ("JPEG", "PNG")):
        out.append(
            (
                "ERROR",
                f"Upload file must be 1280x720 and under 2 MB (is {w}x{h}, {nbytes / 1024 / 1024:.2f} MB). "
                "Use --convert for an upload copy.",
            )
        )
    return out


def colour_shares(img: Image.Image, avoid: list, accent: tuple | None) -> dict:
    """Shares of avoided colours and of the accent colour, and the mean edge brightness and colour (320x180)."""
    small = img.convert("RGB").resize((320, 180), Image.LANCZOS)
    rgb = np.asarray(small, dtype=np.float32)
    hsv = np.asarray(small.convert("HSV"), dtype=np.float32)
    hue, sat, val = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    shares = {}
    for a in avoid:
        if isinstance(a, dict) and a.get("hue"):
            lo, hi = a["hue"]
            shares[a.get("name", f"hue {lo}-{hi}")] = float(
                ((hue >= lo) & (hue <= hi) & (sat >= 0.55) & (val >= 0.55)).mean()
            )
        elif isinstance(a, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", a):
            shares[a] = float((np.linalg.norm(rgb - np.array(hex_rgb(a), np.float32), axis=2) < 70).mean())
    acc = float((np.linalg.norm(rgb - np.array(accent, np.float32), axis=2) < 70).mean()) if accent else None
    r = 14
    edge = np.concatenate(
        [rgb[:r].reshape(-1, 3), rgb[-r:].reshape(-1, 3), rgb[:, :r].reshape(-1, 3), rgb[:, -r:].reshape(-1, 3)]
    )
    return {
        "avoid": shares,
        "accent": acc,
        "edge_rgb": edge.mean(0).tolist(),
        "edge_luma": float((edge @ np.array([0.299, 0.587, 0.114], np.float32)).mean()),
    }


def text_words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_][\w'-]*", text)


def text_findings(text: str, title: str | None, max_words: int, max_numbers: int) -> list[tuple[str, str]]:
    out = []
    numbers = re.findall(r"\d+(?:[.,:]\d+)?", text)
    n = len(text_words(text))
    if n >= max_words + 3:
        out.append(("ERROR", f'{n} words ("{text}"), far over the pack limit of {max_words}.'))
    elif n > max_words:
        out.append(("CHECK", f'{n} words ("{text}"), the pack allows {max_words}.'))
    elif n:
        out.append(("OK", f"{n} words (at most {max_words})."))
    if len(numbers) > max_numbers:
        out.append(
            ("CHECK", f"{len(numbers)} numbers ({', '.join(numbers)}); at most {max_numbers}, and only measured ones.")
        )
    if MONEY.search(text):
        out.append(("NOTE", "Money or a price in the image."))
    if title:
        tw = {w.lower() for w in text_words(title) if len(w) >= 4}
        shared = sorted(tw & {w.lower() for w in text_words(text)})
        out.append(("NOTE", f"Text repeats title words: {', '.join(shared)}." if shared else "Text has no title word."))
    return out


def face_findings(faces: list[dict] | None, L: dict) -> list[tuple[str, str]]:
    """Faces as [{"cx", "cy", "area", "height"}] (shares of the image), largest first. None = not measured."""
    if faces is None:
        return [
            (
                "NOTE",
                "Face check not possible (OpenCV or the YuNet model missing). Check face size and position by hand.",
            )
        ]
    if not faces:
        return [
            (
                "CHECK" if L["face"] else "OK",
                "No face found." + (" The pack wants a face in the first layout." if L["face"] else ""),
            )
        ]
    out = []
    if not L["face"]:
        out.append(("CHECK", f"{len(faces)} face(s), but the pack says no face."))
    if len(faces) > L["max_faces"]:
        out.append(("CHECK", f"{len(faces)} faces (at most {L['max_faces']})."))
    f = faces[0]
    area, cx = f["area"], f["cx"]
    if area < L["face_min_area"]:
        out.append(
            (
                "CHECK",
                f"Face small: {area:.0%} of the image (forehead to chin {f.get('height', 0):.0%} of the "
                f"height); the pack wants at least {L['face_min_area']:.0%}.",
            )
        )
    else:
        out.append(("OK", f"Face {area:.0%} of the image (at least {L['face_min_area']:.0%})."))
    side = "left" if cx < 0.38 else ("right" if cx > 0.62 else "center")
    want = L["face_position"]
    ok = want in (None, "any") or want == side or (want == "side" and side != "center")
    out.append(("OK" if ok else "CHECK", f"Face {side} (at {cx:.0%} of the width); the pack wants {want}."))
    return out


def cover_resize(img: Image.Image, w: int = 1280, h: int = 720) -> Image.Image:
    """Scale to cover w x h, then crop the centre."""
    s = max(w / img.width, h / img.height)
    big = img.convert("RGB").resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (big.width - w) // 2, (big.height - h) // 2
    return big.crop((x, y, x + w, y + h))


def preview_sheet(own: list[tuple[str, Image.Image]], compare: list[Image.Image], width: int) -> Image.Image:
    """One row per own image: the image in third place between the compare images (like in a feed)."""
    h = round(width * 9 / 16)
    gap = 14 if width >= 240 else 8
    cols = 1 + len(compare)
    sheet = Image.new("RGB", (gap + cols * (width + gap) + 260, gap + len(own) * (h + gap)), (15, 15, 15))
    d = ImageDraw.Draw(sheet)
    for r, (name, img) in enumerate(own):
        y = gap + r * (h + gap)
        row = list(compare)
        row.insert(min(2, len(row)), img)
        for c, im in enumerate(row):
            sheet.paste(im.convert("RGB").resize((width, h), Image.LANCZOS), (gap + c * (width + gap), y))
        d.text((gap + cols * (width + gap), y + h // 2 - 8), name[:34], fill=(170, 170, 170), font=font(13))
    return sheet


def checklist(skill_md: str) -> list[str]:
    m = re.search(r"^## Checklist\n(.*?)(?=^## |\Z)", skill_md, re.S | re.M)
    return [ln for ln in (m.group(1).strip().splitlines() if m else []) if re.match(r"\d+\.", ln)]


# ---------------------------------------------------------------- faces (optional, OpenCV + YuNet)


def detect_faces(path: str) -> list[dict] | None:
    """Faces with YuNet at 640x360, score 0.7, faces under 0.4 % of the image ignored. None when not possible."""
    try:
        import cv2
    except ImportError:
        return None
    cands = [os.environ.get("CREWCUT_YUNET", "")] + [str(SKILL / "models" / n) for n in YUNET]
    model = next((c for c in cands if c and os.path.isfile(c)), None)
    if not model:
        return None
    img = cv2.imread(path)
    if img is None:
        return None
    img = cv2.resize(img, (640, 360))
    det = cv2.FaceDetectorYN.create(model, "", (640, 360), 0.7, 0.3, 50)
    _, faces = det.detect(img)
    out = []
    for x in faces if faces is not None else []:
        fx, fy, fw, fh = (float(v) for v in x[:4])
        if fw * fh >= 0.004 * 640 * 360:
            out.append(
                {
                    "cx": (fx + fw / 2) / 640,
                    "cy": (fy + fh / 2) / 360,
                    "area": fw * fh / (640 * 360),
                    "height": fh / 360,
                }
            )
    return sorted(out, key=lambda f: -f["area"])


# ---------------------------------------------------------------- main


def check_image(
    path: str, L: dict, title: str | None, text: str | None, faces: bool
) -> tuple[Image.Image | None, list]:
    try:
        img = Image.open(path)
        img.load()
    except OSError as e:
        return None, [("ERROR", f"not a readable image ({e})")]
    w, h = img.size
    out = size_findings(w, h, os.path.getsize(path), img.format)
    cs = colour_shares(img, L["avoid"], L["accent"])
    for name, share in cs["avoid"].items():
        if share > 0.005:
            out.append(("CHECK", f"{name} covers {share:.1%} of the image; the pack avoids it."))
    if L["background"]:
        dist = float(np.linalg.norm(np.array(cs["edge_rgb"]) - np.array(L["background"])))
        out.append(
            (
                "CHECK" if dist > 80 else "OK",
                f"Edge colour is {dist:.0f} away from the pack background "
                "(more than 80 counts as a different background).",
            )
        )
    if cs["accent"] is not None:
        out.append(("NOTE", f"Accent colour {cs['accent']:.1%} of the image."))
    out += face_findings(detect_faces(path) if faces else None, L)
    if text:
        out += text_findings(text, title, L["max_words"], L["max_numbers"])
    return img, out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check thumbnails and show them at feed size.")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--title", help="video title (title words and the preview)")
    ap.add_argument("--text", action="append", default=[], help="text in the image, once per image, in image order")
    ap.add_argument("--out", help="folder for the preview (default: check/ next to the first image)")
    ap.add_argument("--convert", action="store_true", help="write an upload copy 1280x720 JPG next to the image")
    ap.add_argument("--compare", action="append", default=[], help="images to show next to yours in the preview")
    ap.add_argument("--pack", help="style pack folder (default: studio/brand, else packs/neutral)")
    ap.add_argument("--no-faces", action="store_true", help="skip the face check")
    a = ap.parse_args(argv)
    pack = load_pack(a.pack)
    L = limits(pack)
    errors, own = 0, []
    for i, path in enumerate(a.images):
        text = a.text[i] if i < len(a.text) else None
        img, found = check_image(path, L, a.title, text, not a.no_faces)
        upload = any(t.startswith("Upload file") for _, t in found)
        other = [t for s, t in found if s == "ERROR" and not t.startswith("Upload file")]
        if a.convert and img is not None and upload:
            if other:
                print(f"\n{path}: not converted, fix these first: " + " ".join(other))
            else:
                target = f"{os.path.splitext(path)[0]}-1280x720.jpg"
                if os.path.exists(target):
                    print(f"\n{target} exists, not overwritten.")
                else:
                    cover_resize(img).save(target, "JPEG", quality=90)
                    print(f"\n{path} ({img.width}x{img.height}): converted to {target}")
                path = target
                img, found = check_image(path, L, a.title, text, not a.no_faces)
        print(
            f"\n{path}"
            + (f"  ({img.width}x{img.height}, {os.path.getsize(path) / 1024:.0f} KB, {img.format})" if img else "")
        )
        for level, t in found:
            print(f"   {level:<6} {t}")
        errors += sum(1 for s, _ in found if s == "ERROR")
        if img is not None:
            own.append((os.path.basename(path), img))
    if own:
        out = Path(a.out) if a.out else Path(a.images[0]).resolve().parent / "check"
        out.mkdir(parents=True, exist_ok=True)
        comp = [Image.open(p) for p in a.compare if os.path.isfile(p)]
        for wpx in (320, 160):
            preview_sheet(own, comp, wpx).save(out / f"preview-{wpx}.png")
        print(f"\nPreview: {out / 'preview-320.png'} and preview-160.png")
    items = checklist((SKILL / "SKILL.md").read_text(encoding="utf-8")) if (SKILL / "SKILL.md").is_file() else []
    rules = pack.rules("thumbnail")
    if items or rules:
        print("\nBy hand (look at the preview too):")
        for ln in items:
            print("   " + ln)
        for r in rules:
            print(f"   [ ] {r['rule']} ({r['date']})")
    print(f"\n{len(a.images)} image(s), {errors} ERROR.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
