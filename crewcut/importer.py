"""Bring work that started outside Crewcut into a Crewcut episode, and a ready style pack into the studio.

`crewcut episode import` copies a script and B-roll (never recordings of other episodes, never logs or secrets) from a
folder the container can read (the read-only /import mount), marks the steps that were already done as done, switches
off the steps the user does not want (upload by default) and starts the first open step.
`crewcut brand init --from <pack>` makes a pack the user's own, with private font and logo files copied in.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import approvals, brand, db, episodes, paths

VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
STILL = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
SKIP_PARTS = {".claude", ".git", "harness", "zwischen", "arbeit", "claude-sitzung", "__pycache__", "node_modules"}
SCRIPT_NAMES = ("SCRIPT-*.md", "SKRIPT-*.md", "SCRIPT*.md")

# German studio plan keys -> Crewcut edit plan keys (docs/architecture.md, "Edit plan")
PLAN_KEYS = {"worte": "words", "einschuebe": "inserts", "basis": "base", "basis_bis": "base_until", "nachlauf": "tail",
             "stimme": "voice", "stimme_db": "voice_db", "sprecher": "speaker", "gesicht": "face", "ton": "sound",
             "ausgabe": "output", "format": "format", "crf": "crf"}
INSERT_KEYS = {"art": "kind", "baustein": "scene", "von": "start", "bis": "end", "daten": "data", "cues": "cues",
               "datei": "file", "ab": "at", "tempo": "speed", "id": "id", "transparent": "transparent"}
SOUND_KEYS = {"musik": "music", "musik_db": "music_db", "loecher": "gaps", "ducken": "duck", "schlaege": "hits",
              "tippen": "typing", "wusche": "whooshes", "lufs": "lufs", "schlag_datei": "hit_file",
              "schlag_db": "hit_db", "tipp_datei": "typing_file", "wusch_datei": "whoosh_file"}
SCENES = {"zaehler": "counter", "schlagzeile": "headline", "stichwort": "keyword", "karten": "cards", "balken": "bars",
          "raster": "grid", "tweet": "post", "clipkarte": "clip-card", "flaeche": "area", "fluss": "flow",
          "welle": "wave", "tausch": "swap", "entwirren": "untangle", "kiste": "box", "objekt_wort": "object-word",
          "raster3d": "grid3d", "reihe": "row", "rutsche": "slide", "stapel": "stack", "waage": "scale"}
FORMATS = {"hoch": "portrait", "quer": "landscape"}


def convert_plan(p: dict) -> dict:
    """Translate a studio plan with German keys into the Crewcut edit plan. Unknown keys are kept as they are."""
    out: dict = {}
    for k, v in p.items():
        key = PLAN_KEYS.get(k, k)
        if key == "format":
            v = FORMATS.get(v, v)
        elif key == "speaker" and isinstance(v, list):
            v = [{("at" if kk == "ab" else kk): vv for kk, vv in m.items()} for m in v]
        elif key == "sound" and isinstance(v, dict):
            v = {SOUND_KEYS.get(kk, kk): vv for kk, vv in v.items()}
            if isinstance(v.get("gaps"), list):
                v["gaps"] = [{("before" if kk == "vor" else "frames" if kk == "bilder" else kk): vv
                              for kk, vv in g.items()} for g in v["gaps"]]
        elif key == "inserts" and isinstance(v, list):
            v = [_insert(i) for i in v]
        out[key] = v
    return out


def _insert(i: dict) -> dict:
    o = {INSERT_KEYS.get(k, k): v for k, v in i.items()}
    if "scene" in o:
        o["scene"] = SCENES.get(o["scene"], o["scene"])
    if isinstance(o.get("cues"), dict):
        o["cues"] = {name: ({("word" if kk == "wort" else "after" if kk == "ab" else "offset" if kk == "versatz"
                              else "time" if kk == "zeit" else kk): vv for kk, vv in c.items()}
                            if isinstance(c, dict) else c) for name, c in o["cues"].items()}
    return o


def _skipped(p: Path) -> bool:
    return any(part in SKIP_PARTS or part.startswith(".") for part in p.parts)


def find_script(src: Path) -> Path | None:
    cands: list[Path] = []
    for pat in SCRIPT_NAMES:
        cands += [p for p in src.rglob(pat) if p.is_file() and not _skipped(p.relative_to(src))]
    return sorted(set(cands), key=lambda p: (p.stat().st_mtime, p.name))[-1] if cands else None


def find_broll(src: Path) -> list[Path]:
    """B-roll candidates: media in a b-roll folder of the source (04-broll, broll)."""
    out = []
    for d in ("04-broll", "broll"):
        base = src / d
        if base.is_dir():
            out += sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO | STILL
                          and not _skipped(p.relative_to(src)))
    return out


GENERIC_DIRS = {"out", "export", "08-export", "render", "broll", "04-broll", "media", "files"}


def _label(f: Path) -> str:
    """The nearest folder name that says something (".../opus-low/out/spot.mp4" -> "opus-low")."""
    for parent in f.parents:
        if parent.name and parent.name.lower() not in GENERIC_DIRS:
            return parent.name
    return "file"


def broll_names(files: list[Path]) -> list[str]:
    """Target names: the file name, or "<folder>-<name>" for every file whose name occurs more than once."""
    counts: dict[str, int] = {}
    for f in files:
        counts[f.name] = counts.get(f.name, 0) + 1
    out, used = [], set()
    for f in files:
        name = f.name if counts[f.name] == 1 else re.sub(r"[^A-Za-z0-9._-]+", "-", f"{_label(f)}-{f.name}")
        base, n = name, 2
        while name in used:
            name = f"{Path(base).stem}-{n}{Path(base).suffix}"
            n += 1
        used.add(name)
        out.append(name)
    return out


def import_episode(src: Path, title: str, fmt: str | None = None, script: Path | None = None,
                   broll: list[Path] | None = None, plan: Path | None = None, skip: list[str] | None = None,
                   done: list[str] | None = None, start: bool = True) -> dict:
    """Create a Crewcut episode from earlier work. Returns the project dict."""
    src = src.resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"import folder not found: {src}")
    project = episodes.create(title, source=f"imported from {src.name}", fmt=fmt)
    eid = project["id"]
    ep = paths.episode_dir(eid)
    report: list[str] = []

    script = script or find_script(src)
    if script:
        shutil.copy2(script, ep / "brief" / "SCRIPT-v001.md")
        report.append(f"script: {script.name} -> brief/SCRIPT-v001.md")
    files = broll if broll is not None else find_broll(src)
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f"B-roll file not found: {f}")
    for f, name in zip(files, broll_names(files), strict=True):
        shutil.copy2(f, ep / "broll" / name)
        report.append(f"b-roll: {f.relative_to(src) if src in f.parents else f.name} -> broll/{name}")
    if plan:
        data = convert_plan(json.loads(plan.read_text(encoding="utf-8")))
        (ep / "edit" / "plan-v001.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
        report.append(f"plan: {plan.name} -> edit/plan-v001.json (keys translated; the Editor checks it)")
    (ep / "brief" / "IMPORT.md").write_text(
        f"# Imported\n\nFrom `{src.name}` on {db.now()[:10]}.\n\n" + "\n".join(f"- {r}" for r in report) + "\n",
        encoding="utf-8")

    done = done if done is not None else (["idea", "title", "proof", "script"] if script else ["idea", "title", "proof"])
    skip = skip if skip is not None else ["upload"]
    p = episodes.read(eid)
    for s in episodes.STEPS:
        st = p["steps"].setdefault(s["id"], {})
        if s["id"] in done:
            st.update(status="done", note="done before Crewcut (imported)")
        elif s["id"] in skip or s.get("planned"):
            st.update(status="skipped", note="switched off for this episode" if s["id"] in skip else st.get("note"))
        else:
            st["status"] = "open"
    p["imported"] = {"from": src.name, "files": report}
    p["step"] = next((s["id"] for s in episodes.STEPS if p["steps"][s["id"]]["status"] == "open"), p.get("step"))
    episodes.write(eid, p)
    if start and p.get("step"):
        from .conductor import flow
        flow.post(eid, f"Imported {src.name}: " + "; ".join(report[:6]) + (" …" if len(report) > 6 else "") +
                  ". Steps switched off: " + (", ".join(skip) or "none") + ".")
        flow.start_step(eid, p["step"])
    return episodes.read(eid)


def init_pack(src: Path | None, fonts: dict[str, Path] | None = None, logo: Path | None = None,
              accept: bool = False) -> Path:
    """Make a pack the user's own: copy it to studio/brand, add private font and logo files, optionally accept it."""
    dst = paths.user_brand_dir()
    if src is not None:
        src = src.resolve()
        if not (src / "brand.json").is_file():
            raise FileNotFoundError(f"not a style pack (no brand.json): {src}")
        if (dst / "brand.json").is_file():
            backup = dst.with_name(f"brand.before-{db.now().replace(':', '').replace('-', '')[:15]}")
            shutil.move(str(dst), str(backup))
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("README.md", "*.png", "*.jpg"))
    else:
        approvals.ensure_user_pack()
    bj = dst / "brand.json"
    b = json.loads(bj.read_text(encoding="utf-8"))
    sources = b.setdefault("sources", {})
    if fonts:
        (dst / "fonts").mkdir(exist_ok=True)
        for role, f in fonts.items():
            if not f.is_file():
                raise FileNotFoundError(f"font file not found: {f}")
            shutil.copy2(f, dst / "fonts" / f.name)
            spec = b.setdefault("fonts", {}).setdefault(role, {})
            spec["files"] = sorted(set((spec.get("files") or []) + [f"fonts/{f.name}"]))
            sources[f"fonts.{role}.files"] = "copied from the user's own studio"
    if logo:
        if not logo.is_file():
            raise FileNotFoundError(f"logo file not found: {logo}")
        shutil.copy2(logo, dst / f"logo{logo.suffix.lower()}")
        b.setdefault("logo", {})["file"] = f"logo{logo.suffix.lower()}"
        sources["logo.file"] = "copied from the user's own studio"
    bj.write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    problems = brand.check(brand.load(dst))
    if problems:
        raise ValueError("the pack has problems: " + "; ".join(problems))
    if accept:
        db.kv_set("onboarded", "1")
    return dst
