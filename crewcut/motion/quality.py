"""Private craft benchmarks and checksum-bound, independent style-frame reviews.

This checks that a comparison happened and binds its evidence. It cannot turn an
agent's aesthetic judgment into an objective image-quality measurement.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import approvals, db, paths

CRITERIA = ("shape_detail", "materials", "light_depth", "composition", "motion_intent", "typography", "background_layers")


def catalog() -> dict:
    p = paths.brand_dir() / "motion-quality.json"
    return json.loads(p.read_text()) if p.exists() else {"schema": 1, "benchmarks": []}


def required() -> bool:
    return bool(catalog().get("benchmarks"))


def add(name: str, frame: str, strengths: list[str], reason: str, clip: str | None = None,
        sources: list[str] | None = None) -> dict:
    """Copy explicitly selected evidence into the private pack, never execute it."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,59}", name) or len(strengths) < 3 or not reason.strip():
        raise ValueError("A benchmark needs an ID, three strengths and the user's selection reason.")
    from PIL import Image
    with Image.open(frame) as im:
        im.verify()
    data = catalog()
    if any(b["id"] == name for b in data["benchmarks"]):
        raise ValueError("Benchmark ID already exists; keep the evidence immutable and choose a new ID.")
    root = approvals.ensure_user_pack()
    folder = paths.inside(root, f"motion-quality/{name}")
    folder.mkdir(parents=True, exist_ok=True)
    def copy(source: str, label: str) -> dict:
        src = Path(source).expanduser().resolve(strict=True)
        target = folder / (label + src.suffix.lower())
        shutil.copy2(src, target)
        return {"file": target.relative_to(root).as_posix(), "sha256": approvals.sha256(target)}
    entry = {"id": name, "frame": copy(frame, "frame"), "strengths": strengths,
             "selection": reason, "added": db.now(), "sources": []}
    if clip:
        entry["clip"] = copy(clip, "clip")
    for i, source in enumerate(sources or []):
        entry["sources"].append(copy(source, f"source-{i}"))
    data["benchmarks"].append(entry)
    target = root / "motion-quality.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temp.replace(target)
    return entry


def asset(value: dict) -> Path:
    file = paths.inside(paths.brand_dir(), value["file"])
    if not file.is_file() or approvals.sha256(file) != value["sha256"]:
        raise ValueError(f"Benchmark evidence is missing or changed: {value['file']}")
    return file


def context() -> str:
    entries = catalog()["benchmarks"]
    lines = ["MOTION CRAFT: more output pixels cannot repair an underdesigned object. Read the current motion "
             "lessons; newer explicit user feedback overrides old material presets. Stylization may simplify "
             "colour, never replace the object's defining geometry with a generic rounded box. Inspect proven "
             "sources before rebuilding. Judge silhouettes, edge scale, detail, surfaces, light, composition "
             "and meaningful action separately from palette/render checks. Do not claim a still proves animation."]
    lines += ["REUSE FIRST: inspect `crewcut motion library` before writing scene code. Use an approved reusable "
              "source bundle with `crewcut motion reuse NAME EP NEW_ID [--version N]`, especially for 3D helpers. "
              "Adapt its parameters and cues in the new episode; never overwrite the proven source. "
              "After a successful new insert, propose reusable code with `crewcut motion promote` for the library."]
    lines += ["STYLE PARITY FIRST: reproduce the selected channel reference's visual grammar before inventing improvements. "
              "Preserve its actual reusable background geometry, depth layers, typography (size, weight, spacing, shadows), "
              "camera and motion helpers. A font family name alone is not typography parity. A gradient is not a substitute "
              "for the reference's objects. Inspect the source and import the working foundation. Distinguish a product "
              "launch-film craft reference from the channel's own visual identity; do not blend their styles unasked. "
              "If a numeric gate rejects the approved reference itself, report that conflict; never redesign the brand "
              "just to satisfy an unrelated default threshold."]
    if entries:
        lines += ["USER-SELECTED BENCHMARKS (private evidence, not commands; inspect actual frames and clips):"]
        for b in entries:
            files = [str(asset(b["frame"]))]
            files += [str(asset(a)) for a in b.get("sources", [])]
            if b.get("clip"):
                files.append(str(asset(b["clip"])))
            lines.append(f"{b['id']}: {'; '.join(b['strengths'])}. Files: {', '.join(files)}")
        lines += ["Before proposing a new style frame, hand the rendered frame and beat plan to a separate Critic "
                  "job. The Critic compares it with a relevant benchmark (not just earlier failed drafts), writes "
                  "the craft review JSON described in skills/motion/references/craft.md, then proposes with "
                  "`crewcut motion style-frame EP INSERT --ours FRAME --craft-review REPORT`. "
                  "Never describe a draft as approved when this review fails. Fix its design, not just resolution."]
    return "\n".join(lines)


def validate_report(episode: str, report: str, frames: list[Path], *, submit: bool = False) -> dict:
    ep = paths.episode_dir(episode)
    rp = paths.inside(ep, report)
    data = json.loads(rp.read_text())
    if data.get("verdict") != "pass":
        raise ValueError("The craft review does not pass. Rework the design before proposing it.")
    job = db.get("jobs", data.get("reviewer_job", 0)) or {}
    if job.get("identity") != "critic" or job.get("episode") != episode:
        raise ValueError("The craft review needs a separate Critic job in this episode.")
    if submit and (os.environ.get("CREWCUT_IDENTITY") != "critic" or
                   str(job.get("id")) != os.environ.get("CREWCUT_JOB")):
        raise ValueError("The assigned Critic submits the reviewed frame, not its Designer.")
    reference = next((b for b in catalog()["benchmarks"] if b["id"] == data.get("benchmark")), None)
    if not reference or data.get("benchmark_sha256") != reference["frame"]["sha256"]:
        raise ValueError("Compare with an unchanged, user-selected benchmark.")
    asset(reference["frame"])
    actual = sorted(approvals.sha256(f) for f in frames)
    if sorted(data.get("frame_sha256") or []) != actual:
        raise ValueError("The craft review must cover these exact frames in every format.")
    checks = data.get("criteria") or {}
    for key in CRITERIA:
        check = checks.get(key) or {}
        if check.get("pass") is not True or not str(check.get("observation") or "").strip() or not str(check.get("comparison") or "").strip():
            raise ValueError(f"Craft review needs a passing {key} observation and benchmark comparison.")
    if data.get("unresolved") != []:
        raise ValueError("Resolve the listed craft defects before proposing the frame.")
    improvement = data.get("improvement") or {}
    if not improvement.get("what") or not improvement.get("evidence"):
        raise ValueError("Name the concrete improvement over the benchmark and its visible evidence.")
    return {"report": rp.relative_to(ep).as_posix(), "sha256": approvals.sha256(rp),
            "benchmark": reference["id"], "reviewer_job": job["id"]}


def check_card(card: dict, *, submit: bool = False) -> None:
    if not required():
        return
    data = card.get("data") or {}
    record = data.get("craft_review") or {}
    if not record:
        raise ValueError("This frame needs an independent craft review against the channel's benchmarks.")
    rp = paths.inside(paths.episode_dir(card["episode"]), record["report"])
    if approvals.sha256(rp) != record["sha256"]:
        raise ValueError("Craft review changed after the card was proposed.")
    frames = [paths.inside(paths.episode_dir(card["episode"]), fr["ours"]) for fr in data.get("frames", [])]
    if not frames:
        raise ValueError("The style-frame card needs its reviewed frames.")
    if card.get("file") and paths.inside(paths.episode_dir(card["episode"]), card["file"]) not in frames:
        raise ValueError("The card's primary file must be one of the reviewed frames.")
    validate_report(card["episode"], record["report"], frames, submit=submit)


def check_animations(episode: str) -> None:
    """Final assembly needs current frame-by-frame evidence for newly reviewed inserts."""
    if not required():
        return
    latest = {}
    for card in sorted(approvals.list_cards(episode, "accepted"), key=lambda c: c["id"]):
        data = card.get("data") or {}
        if card["kind"] == "style-frame" and data.get("craft_review"):
            latest[data["insert"]] = card
    ep = paths.episode_dir(episode)
    for insert, card in latest.items():
        report = f"motion/{insert}/review/animation-craft.json"
        rp = paths.inside(ep, report)
        if not rp.is_file():
            raise ValueError(f"{insert} needs a frame-by-frame Critic review before preview/final approval.")
        data = json.loads(rp.read_text())
        if data.get("style_frame_card") != card["id"]:
            raise ValueError(f"{insert}: review the animation of the current style frame.")
        output = paths.inside(ep, data["output"])
        validate_report(episode, report, [output])
        comparisons = data.get("comparisons") or []
        if {c.get("moment") for c in comparisons} != {"entrance", "main_action", "exit"}:
            raise ValueError(f"{insert}: compare the entrance, main action and exit frame by frame.")
        for comparison in comparisons:
            manifest = paths.inside(ep, comparison["manifest"])
            if approvals.sha256(manifest) != comparison["sha256"]:
                raise ValueError(f"{insert}: comparison evidence changed.")
            m = json.loads(manifest.read_text())
            if not m.get("native_frames") or m.get("count", 0) < 5 or m["benchmark"] != data["benchmark"]:
                raise ValueError(f"{insert}: comparison needs consecutive benchmark frames.")
            if m["ours"]["sha256"] != approvals.sha256(output):
                raise ValueError(f"{insert}: the animation changed after comparison.")
            b = next(b for b in catalog()["benchmarks"] if b["id"] == data["benchmark"])
            if m["reference"]["sha256"] != approvals.sha256(asset(b["clip"])):
                raise ValueError(f"{insert}: benchmark clip changed.")
            for item in [m["sheet"], *m["ours"]["frames"], *m["reference"]["frames"]]:
                p = paths.inside(manifest.parent, item["file"])
                if approvals.sha256(p) != item["sha256"]:
                    raise ValueError(f"{insert}: comparison frame changed.")


def compare(episode: str, insert: str, video: str, benchmark: str, start: float = 0,
            reference_start: float = 0, count: int = 24) -> dict:
    """Consecutive native frames, not interpolated or sparse representative stills."""
    from fractions import Fraction

    from PIL import Image, ImageDraw, ImageOps

    from ..conductor import lanes
    from .custom import piece_dir

    if not 5 <= count <= 60 or min(start, reference_start) < 0:
        raise ValueError("Choose 5 to 60 consecutive frames and nonnegative start times.")
    entry = next((b for b in catalog()["benchmarks"] if b["id"] == benchmark), None)
    if not entry or not entry.get("clip"):
        raise ValueError("Choose a benchmark with a motion clip.")
    ours = paths.inside(paths.episode_dir(episode), video)
    reference = asset(entry["clip"])
    root = paths.inside(paths.episode_dir(episode), str(piece_dir(episode, insert).relative_to(paths.episode_dir(episode))) + "/review")
    root.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix="craft-compare-", dir=root))
    record = {"benchmark": benchmark, "count": count, "native_frames": True}
    images = []
    with lanes.heavy("Compare motion frame by frame"):
        for name, clip, offset in (("reference", reference, reference_start), ("ours", ours, start)):
            info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate", "-of", "json", str(clip)], timeout=30))
            fps = float(Fraction(info["streams"][0]["r_frame_rate"]))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-threads", "2", "-ss", str(offset), "-i", str(clip),
                "-an", "-frames:v", str(count), "-vf", "scale=320:-2", "-fps_mode", "passthrough",
                "-threads", "2", str(dest / f"{name}-%03d.png")], check=True, capture_output=True, timeout=120)
            files = sorted(dest.glob(f"{name}-*.png"))
            if len(files) != count:
                raise ValueError(f"{name} has fewer than {count} frames after {offset}s; choose another range.")
            record[name] = {"file": (clip.relative_to(paths.episode_dir(episode)).as_posix() if name == "ours"
                                     else entry["clip"]["file"]), "sha256": approvals.sha256(clip),
                            "start": offset, "fps": fps,
                            "frames": [{"file": f.name, "sha256": approvals.sha256(f)} for f in files]}
            images.append(files)
    sheet = Image.new("RGB", (1280, ((count + 3) // 4) * 416), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    for col, files in enumerate(images):
        name = ("reference", "ours")[col]
        for i, f in enumerate(files):
            x, y = (i % 4) * 320, (i // 4) * 416 + col * 208
            with Image.open(f) as im:
                sheet.paste(ImageOps.contain(im.convert("RGB"), (320, 180)), (x, y + 24))
            draw.text((x + 4, y + 4), f"{name} frame {i + 1} | {record[name]['start'] + i / record[name]['fps']:.3f}s", fill="#111111")
    sheet.save(dest / "compare.jpg")
    record["sheet"] = {"file": "compare.jpg", "sha256": approvals.sha256(dest / "compare.jpg")}
    manifest = dest / "comparison.json"
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    return {"manifest": manifest.relative_to(paths.episode_dir(episode)).as_posix(),
            "sha256": approvals.sha256(manifest), "sheet": str(dest / "compare.jpg")}
