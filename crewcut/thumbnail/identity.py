"""Is it the creator's face? The identity gate for thumbnails, its calibration, and the real-photo fallback.

Image models draw the person from the attached face references. With one reference, or after a few rounds, the face
can drift into a look-alike. So:

1. Every image of the person gets several face references (`thumbnail.identity.references`: the reference photo plus
   real frames or approved thumbnails from different angles); `crewcut thumbnail make` attaches them.
2. The identity gate measures the main face of each finished image against those references (a face embedding and
   its cosine similarity). Below the threshold the variant is made again with stronger references.
3. The threshold is calibrated on the creator's real thumbnails (positives) and rejected look-alikes (negatives).
4. Only when a variant keeps failing: the fallback puts a real frame of the person into the design (`frames` finds
   frames in the creator's footage, `cutout` cuts the person out, `compose` places the cutout over the background
   with light retouch only: colour match, rim light, a slight sharpen; no change of geometry).

Face detection: YuNet; face embedding: SFace. Both are from the OpenCV model zoo (MIT and Apache-2.0) and run with
OpenCV (`pip install "crewcut[faces]"`). The model files are downloaded once into the model folder (env
CREWCUT_FACE_MODELS, default ~/.cache/crewcut/models) and checked by SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "detector": {"file": "face_detection_yunet_2023mar.onnx",
                 "url": f"{ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                 "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"},
    "recognizer": {"file": "face_recognition_sface_2021dec.onnx",
                   "url": f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                   "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"},
}
DEFAULTS: dict[str, Any] = {
    # SFace's own same-person threshold is 0.363 (cosine). Look-alikes made from a reference photo score higher than
    # strangers, so a pack calibrates its own value with `crewcut thumbnail face calibrate`.
    "min_similarity": 0.5,
    "references": [],
    "max_references": 4,
    "min_face_share": 0.004,
    "tries": 3,
    "use_reference_photo": True,
}
SIDE = ".face.json"


class Unavailable(RuntimeError):
    """The identity check cannot run (OpenCV or a model missing). The gate then fails closed."""


def model_dir() -> Path:
    env = os.environ.get("CREWCUT_FACE_MODELS")
    base = Path(env) if env else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "crewcut" / "models"
    return base


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_models(download: bool = True) -> dict[str, Path]:
    d = model_dir()
    out = {}
    for key, m in MODELS.items():
        p = d / m["file"]
        if not p.is_file() and download:
            d.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".part")
            try:
                with urllib.request.urlopen(m["url"], timeout=120) as r, open(tmp, "wb") as f:  # noqa: S310
                    shutil.copyfileobj(r, f)
            except OSError as e:
                tmp.unlink(missing_ok=True)
                raise Unavailable(f"Could not download the {key} model ({e}).") from e
            if _sha256(tmp) != m["sha256"]:
                tmp.unlink(missing_ok=True)
                raise Unavailable(f"The downloaded {key} model has the wrong checksum.")
            tmp.replace(p)
        if not p.is_file():
            raise Unavailable(f"The {key} model is missing: {p}.")
        out[key] = p
    return out


def read_rgb(path: str | Path) -> np.ndarray:
    """RGB uint8; transparent parts over mid grey."""
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
            im = Image.alpha_composite(bg, im)
        return np.asarray(im.convert("RGB"))


class FaceModel:
    """YuNet finds faces, SFace turns the aligned face into a 128-number embedding."""

    def __init__(self, download: bool = True):
        try:
            import cv2
        except ImportError as e:
            raise Unavailable("OpenCV is not installed (pip install \"crewcut[faces]\").") from e
        if not hasattr(cv2, "FaceRecognizerSF"):
            raise Unavailable("This OpenCV has no FaceRecognizerSF (needs 4.5.4 or newer).")
        m = ensure_models(download)
        self.cv2 = cv2
        self.det = cv2.FaceDetectorYN.create(str(m["detector"]), "", (320, 320), 0.7, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(str(m["recognizer"]), "")

    def faces(self, rgb: np.ndarray, max_side: int = 1280) -> list[dict]:
        """Faces sorted by size, largest first: box (x, y, w, h) in pixels, share of the image, score, row."""
        h, w = rgb.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        bgr = self.cv2.cvtColor(rgb, self.cv2.COLOR_RGB2BGR)
        small = self.cv2.resize(bgr, (round(w * scale), round(h * scale))) if scale < 1 else bgr
        self.det.setInputSize((small.shape[1], small.shape[0]))
        _, rows = self.det.detect(small)
        out = []
        for row in rows if rows is not None else []:
            full = row.copy()
            full[:14] = row[:14] / scale
            x, y, fw, fh = (float(v) for v in full[:4])
            out.append({"box": [round(x), round(y), round(fw), round(fh)], "share": fw * fh / (w * h),
                        "score": float(row[14]), "row": full, "bgr": bgr})
        return sorted(out, key=lambda f: -f["share"])

    def embed(self, face: dict) -> np.ndarray:
        crop = self.rec.alignCrop(face["bgr"], face["row"])
        v = np.asarray(self.rec.feature(crop), dtype=np.float32).ravel()
        return v / (np.linalg.norm(v) + 1e-9)

    def main_embedding(self, path: str | Path, min_share: float = DEFAULTS["min_face_share"]) -> tuple[
            np.ndarray | None, dict]:
        faces = [f for f in self.faces(read_rgb(path)) if f["share"] >= min_share]
        if not faces:
            return None, {"faces": 0}
        return self.embed(faces[0]), {"faces": len(faces), "box": faces[0]["box"],
                                      "face_share": round(faces[0]["share"], 4)}


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


def score(face: np.ndarray, refs: list[np.ndarray]) -> float:
    """Mean similarity to all face references: one lucky match with one reference does not pass a look-alike."""
    return float(np.mean([cosine(face, r) for r in refs])) if refs else 0.0


# ---------------------------------------------------------------- pack settings

def settings(pack) -> dict[str, Any]:
    own = pack.value("thumbnail.identity", {}) or {}
    return {**DEFAULTS, **{k: v for k, v in own.items() if k in DEFAULTS}}


def reference_paths(pack) -> list[Path]:
    """The face references of the pack: the reference photo first, then `thumbnail.identity.references`."""
    from .. import paths
    if pack.value("thumbnail.face", True) is False:
        return []
    cfg = settings(pack)
    own = list(cfg["references"] or [])
    rels = ([pack.value("thumbnail.reference_photo")] if cfg["use_reference_photo"] or not own else []) + own
    out = []
    for rel in rels:
        if not rel:
            continue
        p = paths.inside(Path(pack.dir), rel) if not Path(rel).is_absolute() else Path(rel)
        if p.is_file():
            out.append(p)
    return list(dict.fromkeys(out))


def enabled(pack) -> bool:
    return pack is not None and pack.value("thumbnail.face", True) is not False and bool(reference_paths(pack))


class Gate:
    """Measures images against the pack's face references. `embed` replaces the model (tests)."""

    def __init__(self, refs: list[Path], min_similarity: float,
                 embed: Callable[[Path], tuple[np.ndarray | None, dict]] | None = None):
        self.min_similarity = float(min_similarity)
        self.embed = embed or FaceModel().main_embedding
        self.refs: list[np.ndarray] = []
        self.ref_names = []
        self.ref_paths: list[Path] = []
        for r in refs:
            v, _ = self.embed(r)
            if v is not None:
                self.refs.append(v)
                self.ref_names.append(Path(r).name)
                self.ref_paths.append(Path(r))
        if not self.refs:
            raise Unavailable("No face found in the face references.")

    @classmethod
    def for_pack(cls, pack, embed=None) -> Gate:
        return cls(reference_paths(pack), settings(pack)["min_similarity"], embed)

    def measure(self, image: str | Path) -> dict[str, Any]:
        v, info = self.embed(Path(image))
        if v is None:
            return {**info, "similarity": None, "ok": False, "problem": "no face found"}
        sim = round(score(v, self.refs), 3)
        ok = sim >= self.min_similarity
        out = {**info, "similarity": sim, "min_similarity": self.min_similarity, "ok": ok}
        if not ok:
            out["problem"] = (f"the face is not the person (similarity {sim:.2f} to the face references, needs "
                              f"{self.min_similarity:.2f})")
        side = Path(str(image) + SIDE)
        if side.is_file():
            out["real_photo"] = json.loads(side.read_text(encoding="utf-8")).get("source")
        return out


def face_crop(path: Path, box: list[int] | None, size: int = 360):
    """A square crop around the face box (head and a little more), or the image centre without a box."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if box:
            x, y, w, h = box
            half = max(w, h) * 0.95
            cx, cy = x + w / 2, y + h / 2
            im = im.crop((round(cx - half), round(cy - half), round(cx + half), round(cy + half)))
        else:
            side = min(im.size)
            im = im.crop(((im.width - side) // 2, 0, (im.width + side) // 2, side))
        return im.resize((size, size), Image.LANCZOS)


def face_sheet(target: Path, rows: list[tuple[str, Path, list[int] | None, float | None]], refs: list[Path],
               measure: Callable[[Path], tuple[np.ndarray | None, dict]] | None = None, size: int = 360) -> Path:
    """Each variant's face next to the first face references at the same size: subtle drift (a wider face, another
    nose) that an embedding still calls the same person is visible here at a glance."""
    from PIL import Image, ImageDraw
    cells = []
    for r in refs:
        box = (measure(r)[1].get("box") if measure else None)
        cells.append((f"Referenz {r.stem[:22]}", face_crop(r, box, size)))
    for label, img, box, sim in rows:
        cells.append((f"{label}  {'-' if sim is None else f'{sim:.2f}'}", face_crop(img, box, size)))
    sheet = Image.new("RGB", (len(cells) * (size + 8) + 8, size + 44), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (text, im) in enumerate(cells):
        sheet.paste(im, (8 + i * (size + 8), 36))
        d.text((10 + i * (size + 8), 12), text, fill=(250, 249, 245))
    sheet.save(target, quality=90)
    return target


# ---------------------------------------------------------------- calibration

def threshold(positives: list[float], negatives: list[float]) -> dict[str, Any]:
    """The threshold between the real faces and the look-alikes. Without overlap the middle of the gap; with overlap
    just above the highest look-alike (no wrong face passes), and the real images it would reject are named."""
    pos, neg = sorted(positives), sorted(negatives)
    if not pos or not neg:
        raise ValueError("Calibration needs at least one positive and one negative image.")
    lo, hi = max(neg), min(pos)
    if hi > lo:
        t = round((lo + hi) / 2, 3)
    else:
        t = round(lo + 0.01, 3)
    return {"min_similarity": t, "max_negative": round(lo, 3), "min_positive": round(hi, 3), "gap": round(hi - lo, 3),
            "separated": hi > lo, "positives_rejected": sum(p < t for p in pos),
            "negatives_accepted": sum(n >= t for n in neg)}


# ---------------------------------------------------------------- fallback: real frames, cutout, compose

def mine_frames(videos: list[Path], out_dir: Path, gate: Gate | None, model: FaceModel, step: float = 2.0,
                keep: int = 40, min_face_share: float = 0.01) -> list[dict]:
    """Keyframes every `step` seconds from the footage; keeps frames where the person's face is large and sharp.
    Writes the frames, `frames.json` and a numbered `sheet.jpg` to look at."""
    from PIL import Image, ImageDraw
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for video in videos:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-skip_frame", "nokey", "-i", str(video),
                                "-vf", f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{step})',"
                                       "scale=960:-2,showinfo", "-fps_mode", "vfr", "-q:v", "3",
                                f"{tmp}/%06d.jpg"], capture_output=True, text=True)
            times = [float(t) for t in re.findall(r"pts_time:\s*([0-9.]+)", r.stderr)]
            for i, f in enumerate(sorted(Path(tmp).glob("*.jpg"))):
                rgb = read_rgb(f)
                faces = [x for x in model.faces(rgb) if x["share"] >= min_face_share]
                if not faces:
                    continue
                face = faces[0]
                x, y, w, h = face["box"]
                gray = rgb[max(0, y):y + h, max(0, x):x + w].mean(axis=2)
                sharp = float(np.var(np.diff(gray, 2, axis=0))) if gray.size else 0.0
                sim = score(model.embed(face), gate.refs) if gate else None
                if gate and sim < gate.min_similarity:
                    continue
                lm = face["row"][4:14].reshape(5, 2)  # eyes, nose, mouth corners
                eye = np.linalg.norm(lm[1] - lm[0]) + 1e-6
                rows.append({"video": str(video), "time": times[i] if i < len(times) else None,
                             "face_share": round(face["share"], 4), "sharpness": round(sharp, 1),
                             "similarity": None if sim is None else round(sim, 3),
                             "mouth_width": round(float(np.linalg.norm(lm[4] - lm[3]) / eye), 3),
                             "turn": round(float((lm[2][0] - (lm[0][0] + lm[1][0]) / 2) / eye), 3),
                             "face_x": round((x + w / 2) / rgb.shape[1], 3), "_img": Image.fromarray(rgb)})
    rows.sort(key=lambda r: -(r["sharpness"] * r["face_share"]))
    chosen: list[dict] = []
    for r in rows:  # spread over time: at least 6 s apart within one video
        if all(c["video"] != r["video"] or r["time"] is None or abs(c["time"] - r["time"]) >= 6 for c in chosen):
            chosen.append(r)
        if len(chosen) >= keep:
            break
    thumbs = []
    for n, r in enumerate(chosen, 1):
        r["n"] = n
        r["file"] = f"frame-{n:02d}.jpg"
        r.pop("_img").save(out_dir / r["file"], quality=90)
        t = Image.open(out_dir / r["file"]).copy()
        t.thumbnail((320, 180))
        d = ImageDraw.Draw(t)
        d.rectangle((0, 0, 34, 20), fill=(0, 0, 0))
        d.text((4, 4), str(n), fill=(255, 255, 255))
        thumbs.append(t)
    if thumbs:
        cols = 6
        sheet = Image.new("RGB", (cols * 320, ((len(thumbs) + cols - 1) // cols) * 180), (20, 20, 20))
        for i, t in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * 320, (i // cols) * 180))
        sheet.save(out_dir / "sheet.jpg", quality=85)
    (out_dir / "frames.json").write_text(json.dumps(chosen, indent=1) + "\n", encoding="utf-8")
    return chosen


def save_frame(video: Path, time_s: float, target: Path) -> Path:
    if target.exists():
        raise FileExistsError(f"{target} exists; pick a new name.")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{time_s:.3f}", "-i", str(video),
                    "-frames:v", "1", str(target)], check=True)
    return target


def cutout(image: Path, target: Path, model: str = "birefnet-portrait") -> Path:
    """Cut the person out with rembg (Python package or the `rembg` command). Writes an RGBA PNG."""
    if target.exists():
        raise FileExistsError(f"{target} exists; pick a new name.")
    try:
        from PIL import Image
        from rembg import new_session, remove  # type: ignore
        with Image.open(image) as im:
            remove(im.convert("RGB"), session=new_session(model)).save(target)
    except ImportError:
        exe = os.environ.get("CREWCUT_REMBG") or shutil.which("rembg")
        if not exe:
            raise Unavailable("rembg is not installed (pip install rembg, or set CREWCUT_REMBG).") from None
        subprocess.run([exe, "i", "-m", model, str(image), str(target)], check=True)
    return target


def _ring(alpha: np.ndarray, width: float) -> np.ndarray:
    from PIL import Image, ImageFilter
    a = Image.fromarray((alpha * 255).astype(np.uint8))
    blurred = np.asarray(a.filter(ImageFilter.GaussianBlur(width)), dtype=np.float32) / 255
    return np.clip((alpha - blurred) * 2.5, 0, 1)


def compose(background: Path, person: Path, target: Path, height: float, x: float, bottom: float = 1.0,
            overlay: Path | None = None, match: float = 0.25, rim: str | None = None, rim_strength: float = 0.6,
            sharpen: float = 0.6, source: str | None = None) -> Path:
    """Place a cut-out person over a background: uniform scale to `height` (share of the image height), centre at
    `x` (share of the width), feet or chest at `bottom`. Light retouch only: `match` moves the person's mean colour
    towards the background's, `rim` adds a thin light of that colour on the edge, `sharpen` is a slight unsharp mask.
    The overlay (graphics and text in front) goes on top. Writes `<target>.face.json` with the source."""
    from PIL import Image, ImageFilter
    if target.exists():
        raise FileExistsError(f"{target} exists; pick a new name.")
    bg = Image.open(background).convert("RGB")
    W, H = bg.size
    p = Image.open(person).convert("RGBA")
    box = p.getbbox()
    if box:
        p = p.crop(box)
    s = height * H / p.height
    p = p.resize((max(1, round(p.width * s)), max(1, round(p.height * s))), Image.LANCZOS)
    if sharpen > 0:
        rgb = p.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=round(80 * sharpen), threshold=2))
        p = Image.merge("RGBA", (*rgb.split(), p.getchannel("A")))
    arr = np.asarray(p, dtype=np.float32)
    alpha = arr[..., 3] / 255
    rgb = arr[..., :3]
    if match > 0:
        bga = np.asarray(bg, dtype=np.float32).reshape(-1, 3).mean(0)
        mean = (rgb * alpha[..., None]).sum((0, 1)) / (alpha.sum() + 1e-6)
        rgb = rgb + match * 0.35 * (bga - mean)
    if rim:
        c = np.array([int(rim[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)
        ring = _ring(alpha, max(2.0, p.height / 220))[..., None] * rim_strength
        rgb = rgb * (1 - ring) + c * ring
    p = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")
    left, top = round(x * W - p.width / 2), round(bottom * H - p.height)
    canvas = bg.convert("RGBA")
    canvas.alpha_composite(p, (max(left, -p.width), max(top, -p.height))) if left >= 0 and top >= 0 else \
        canvas.paste(p, (left, top), p)
    if overlay:
        ov = Image.open(overlay).convert("RGBA").resize((W, H))
        canvas.alpha_composite(ov)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(target)
    Path(str(target) + SIDE).write_text(json.dumps({
        "source": source or str(person), "person": str(person), "person_sha256": _sha256(Path(person)),
        "background": str(background), "overlay": str(overlay) if overlay else None,
        "placement": {"height": height, "x": x, "bottom": bottom},
        "retouch": {"match": match, "rim": rim, "rim_strength": rim_strength, "sharpen": sharpen}}, indent=1) + "\n",
        encoding="utf-8")
    return target


# ---------------------------------------------------------------- command line

def cli(a) -> int:
    from .. import brand, paths
    pack = brand.load()
    cfg = settings(pack)
    base = Path.cwd()
    ep = os.environ.get("CREWCUT_EPISODE") or getattr(a, "episode", None)
    if ep:
        base = paths.episode_dir(ep)

    def p(rel: str) -> Path:
        q = Path(rel)
        return q if q.is_absolute() else base / q
    try:
        if a.facecmd == "check":
            gate = Gate.for_pack(pack)
            rows = {str(img): gate.measure(p(img)) for img in a.images}
            if a.json:
                print(json.dumps(rows, indent=1, ensure_ascii=False))
            else:
                print(f"Face references: {', '.join(gate.ref_names)}; threshold {gate.min_similarity:.2f}")
                for img, r in rows.items():
                    sim = "-" if r["similarity"] is None else f"{r['similarity']:.3f}"
                    print(f"{'OK  ' if r['ok'] else 'FAIL'} {sim}  {img}" + (f"  ({r['problem']})" if not r["ok"] else ""))
            return 0 if all(r["ok"] for r in rows.values()) else 1
        if a.facecmd == "calibrate":
            gate = Gate(reference_paths(pack), cfg["min_similarity"])
            pos = {str(i): gate.measure(p(i))["similarity"] for i in a.positive}
            neg = {str(i): gate.measure(p(i))["similarity"] for i in a.negative}
            res = threshold([v for v in pos.values() if v is not None], [v for v in neg.values() if v is not None])
            res["positives"], res["negatives"] = pos, neg
            res["references"] = gate.ref_names
            print(json.dumps(res, indent=1, ensure_ascii=False))
            if a.write:
                tj = Path(pack.dir) / "thumbnail.json"
                data = json.loads(tj.read_text(encoding="utf-8"))
                data.setdefault("identity", {})["min_similarity"] = res["min_similarity"]
                data["identity"]["calibration"] = {k: res[k] for k in (
                    "max_negative", "min_positive", "gap", "positives_rejected", "negatives_accepted")} | {
                    "positives": len(pos), "negatives": len(neg)}
                tj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"Wrote identity.min_similarity {res['min_similarity']} to {tj}")
            return 0
        if a.facecmd == "frames":
            model = FaceModel()
            gate = Gate(reference_paths(pack), cfg["min_similarity"], model.main_embedding) if enabled(pack) else None
            rows = mine_frames([p(v) for v in a.videos], p(a.out), gate, model, a.step, a.keep)
            print(f"{len(rows)} frames in {p(a.out)} (sheet.jpg, frames.json)")
            return 0 if rows else 1
        if a.facecmd == "save":
            print(save_frame(p(a.video), a.time, p(a.target)))
            return 0
        if a.facecmd == "cutout":
            print(cutout(p(a.image), p(a.target), a.model))
            return 0
        if a.facecmd == "compose":
            out = compose(p(a.background), p(a.person), p(a.target), a.height, a.x, a.bottom,
                          p(a.overlay) if a.overlay else None, a.match, a.rim, a.rim_strength, a.sharpen, a.source)
            print(out)
            return 0
    except (Unavailable, FileExistsError, FileNotFoundError, ValueError, subprocess.CalledProcessError) as e:
        print(str(e))
        return 2
    return 2


def add_parser(tsub) -> None:
    f = tsub.add_parser("face", help="the identity gate (is it the person?) and the real-photo fallback")
    fs = f.add_subparsers(dest="facecmd", required=True)
    c = fs.add_parser("check", help="similarity of each image's main face to the pack's face references")
    c.add_argument("images", nargs="+")
    c.add_argument("--episode")
    c.add_argument("--json", action="store_true")
    k = fs.add_parser("calibrate", help="threshold from real thumbnails (positives) and look-alikes (negatives)")
    k.add_argument("--positive", nargs="+", required=True)
    k.add_argument("--negative", nargs="+", required=True)
    k.add_argument("--write", action="store_true", help="write identity.min_similarity into the pack")
    fr = fs.add_parser("frames", help="fallback: find sharp, large frames of the person in footage")
    fr.add_argument("videos", nargs="+")
    fr.add_argument("--out", required=True)
    fr.add_argument("--step", type=float, default=2.0)
    fr.add_argument("--keep", type=int, default=40)
    fr.add_argument("--episode")
    sv = fs.add_parser("save", help="fallback: save one frame at full size")
    sv.add_argument("video")
    sv.add_argument("time", type=float)
    sv.add_argument("target")
    sv.add_argument("--episode")
    cu = fs.add_parser("cutout", help="fallback: cut the person out of a real frame (rembg)")
    cu.add_argument("image")
    cu.add_argument("target")
    cu.add_argument("--model", default="birefnet-portrait")
    cu.add_argument("--episode")
    co = fs.add_parser("compose", help="fallback: the real cut-out person over a designed background")
    co.add_argument("--background", required=True)
    co.add_argument("--person", required=True)
    co.add_argument("--overlay")
    co.add_argument("--height", type=float, required=True, help="person height as a share of the image height")
    co.add_argument("--x", type=float, required=True, help="person centre as a share of the width")
    co.add_argument("--bottom", type=float, default=1.0)
    co.add_argument("--match", type=float, default=0.25)
    co.add_argument("--rim")
    co.add_argument("--rim-strength", type=float, default=0.6)
    co.add_argument("--sharpen", type=float, default=0.6)
    co.add_argument("--source", help="the real frame the cutout comes from (recorded in .face.json)")
    co.add_argument("target")
    co.add_argument("--episode")
