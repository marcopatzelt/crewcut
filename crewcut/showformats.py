"""Show formats: named video formats that a new episode is built from, again and again.

A show format is a recipe for a whole episode, not a picture: what input fits it, which of Hormozi's five topic types
it serves, the ordered units of the video, a full-script template, an optional cue sheet template and test plan, the
packaging rules and title formulas, and which thumbnail formats (crewcut/thumbnail/formats.py) go with it. The word
"format" is taken in project.json (landscape or portrait), so an episode keeps its pick in `show_format` (and in
`form`, which the Shorts table reads).

The library is the neutral pack's `show-formats/formats.json` (a few generic examples in Crewcut's own words) merged
with the studio's `brand/show-formats/formats.json`; a studio format with the same id replaces the example. Template
paths are relative to the folder of the formats.json that names them. `[formats]` in config/crewcut.toml:
`enabled` (default true) and `include_examples` (default true).

    {"schema": 1, "formats": [
      {"id": "tool-test", "name": "Tool test", "length": "long", "kinds": [{"id": "free", "name": "…", "when": "…"}],
       "when": "…", "topic_types": ["manufactured"], "structure": [{"name": "Opening", "purpose": "…"}],
       "script_template": "templates/tool-test.script.md", "cue_template": "templates/tool-test.cues.md",
       "testplan_template": "templates/tool-test.testplan.md", "packaging_rules": ["…"], "title_formulas": ["…"],
       "thumbnail_formats": ["house-face-result"], "checker_format": "lang", "gate_on": "script", "cadence": "weekly",
       "strong": "…"}]}

`crewcut formats [list|show <id>|check|choose <episode> <id>|score]`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import paths

DIR = "show-formats"
LENGTHS = ("long", "short")
CHOICES = ("long", "short", "auto")
TOPIC_TYPES = ("far_past", "recent_past", "present", "trending", "manufactured")
TOPIC_NAMES = {"far_past": "far past", "recent_past": "recent past", "present": "present", "trending": "trending",
               "manufactured": "manufactured"}
CHECKER_FORMATS = ("lang", "short")
GATE_ON = ("script", "cues")   # what the style gate checks first: the full script, or (a studio whose checker takes
                               # only cue sheets for long videos) the cue sheet derived from it in the same run
INPUT_KINDS = ("tool", "link", "tweet", "idea")
TRAFFIC_TYPES = ("browse", "search")   # how viewers find the format: home page and feed, or search (judged at 28 days)
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
TEMPLATE_KEYS = ("script_template", "cue_template", "testplan_template")
STUDIO_REFERENCE = "references/HORMOZI-NIE-OHNE-CONTENT.md"   # read when a studio has it (where ideas come from)
FORMAT_FILE = re.compile(r"^FORMAT-v(\d{3,})\.md$")


def settings() -> dict:
    from . import config
    cfg = config.get("crewcut", "formats", {}) or {}
    return {"enabled": cfg.get("enabled", True) is not False,
            "include_examples": cfg.get("include_examples", True) is not False}


def library_dirs() -> list[tuple[str, Path]]:
    """(source, folder): the neutral examples first, then the studio's own library (the later one wins)."""
    out = []
    if settings()["include_examples"]:
        out.append(("neutral", paths.neutral_pack_dir() / DIR))
    out.append(("studio", paths.user_brand_dir() / DIR))
    return out


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def problems_of(f: Any, folder: Path | None = None) -> list[str]:
    """Everything wrong with one format, in plain words. Empty: the format is usable."""
    if not isinstance(f, dict):
        return ["a format must be an object"]
    fid = f.get("id")
    name = f"format {fid!r}"
    out = []
    if not isinstance(fid, str) or not ID.match(fid):
        out.append(f"{name}: id must be lower-case letters, digits and dashes")
    for key in ("name", "when", "script_template"):
        if not isinstance(f.get(key), str) or not f[key].strip():
            out.append(f"{name} needs {key}")
    if f.get("length") not in LENGTHS:
        out.append(f"{name}: length must be long or short")
    tt = f.get("topic_types")
    if not _str_list(tt) or not tt:
        out.append(f"{name} needs topic_types (one or more of {', '.join(TOPIC_TYPES)})")
    else:
        out += [f"{name}: unknown topic type {t!r} (use {', '.join(TOPIC_TYPES)})" for t in tt if t not in TOPIC_TYPES]
    st = f.get("structure")
    if not isinstance(st, list) or not st:
        out.append(f"{name} needs structure (the ordered units, each with name and purpose)")
    else:
        for i, u in enumerate(st, 1):
            if not isinstance(u, dict) or not str(u.get("name") or "").strip() or not str(u.get("purpose") or "").strip():
                out.append(f"{name}: structure unit {i} needs name and purpose")
    kinds = f.get("kinds", [])
    if not isinstance(kinds, list):
        out.append(f"{name}: kinds must be a list")
    else:
        for i, k in enumerate(kinds, 1):
            if not isinstance(k, dict) or not all(str(k.get(x) or "").strip() for x in ("id", "name", "when")):
                out.append(f"{name}: kind {i} needs id, name and when")
    for key in ("packaging_rules", "title_formulas", "thumbnail_formats", "keywords"):
        if key in f and not (_str_list(f[key]) or f[key] == []):
            out.append(f"{name}: {key} must be a list of texts")
    if "title_patterns" in f:
        if not (_str_list(f["title_patterns"]) or f["title_patterns"] == []):
            out.append(f"{name}: title_patterns must be a list of regular expressions")
        else:
            for pat in f["title_patterns"]:
                try:
                    re.compile(pat)
                except re.error as e:
                    out.append(f"{name}: title pattern {pat!r} is not a valid regular expression ({e})")
    if f.get("traffic_type") is not None and f["traffic_type"] not in TRAFFIC_TYPES:
        out.append(f"{name}: traffic_type must be browse or search")
    if f.get("checker_format") is not None and f["checker_format"] not in CHECKER_FORMATS:
        out.append(f"{name}: checker_format must be lang or short")
    if f.get("gate_on") is not None and f["gate_on"] not in GATE_ON:
        out.append(f"{name}: gate_on must be script or cues")
    if f.get("gate_on") == "cues" and not f.get("cue_template"):
        out.append(f"{name}: gate_on cues needs a cue_template")
    for key in ("cadence", "strong"):
        if key in f and f[key] is not None and not isinstance(f[key], str):
            out.append(f"{name}: {key} must be a text")
    for key in TEMPLATE_KEYS:
        rel = f.get(key)
        if rel is None or (key != "script_template" and rel == ""):
            continue
        if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            out.append(f"{name}: {key} must be a path inside its library folder")
        elif folder is not None and not (folder / rel).is_file():
            out.append(f"{name}: {key} {rel} is missing")
    return out


def _read(folder: Path) -> tuple[list, list[str]]:
    p = folder / "formats.json"
    if not p.is_file():
        return [], []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], [f"{p}: not readable JSON ({e})"]
    fs = data.get("formats") if isinstance(data, dict) else None
    if not isinstance(fs, list):
        return [], [f"{p}: needs a list \"formats\""]
    return fs, []


def report() -> tuple[dict[str, dict], list[str]]:
    """(formats by id, problems). A broken format is left out and named in the problems."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    for source, folder in library_dirs():
        fs, errs = _read(folder)
        errors += errs
        seen: set[str] = set()
        for f in fs:
            probs = problems_of(f, folder)
            if isinstance(f, dict) and f.get("id") in seen:
                probs.append(f"format {f.get('id')!r} appears twice in {folder / 'formats.json'}")
            if probs:
                errors += [f"{source}: {p}" for p in probs]
                continue
            seen.add(f["id"])
            out[f["id"]] = {**f, "checker_format": f.get("checker_format") or ("lang" if f["length"] == "long" else "short"),
                            "gate_on": f.get("gate_on") or "script",
                            "dir": str(folder), "source": source}
    return out, errors


def load() -> dict[str, dict]:
    return report()[0]


def enabled() -> bool:
    """The format system is on: switched on and at least one usable format."""
    return settings()["enabled"] and bool(load())


def get(fid: str | None) -> dict | None:
    return load().get(fid) if fid else None


def template(f: dict, key: str) -> Path | None:
    rel = f.get(key)
    if not rel:
        return None
    p = Path(f["dir"]) / rel
    return p if p.is_file() else None


def public(f: dict) -> dict:
    """What the API and `--json` show: the format without its folder, template paths as names."""
    out = {k: v for k, v in f.items() if k != "dir"}
    out["templates"] = {k: str(template(f, k)) for k in TEMPLATE_KEYS if template(f, k)}
    return out


def studio_reference() -> Path | None:
    p = paths.user_brand_dir() / STUDIO_REFERENCE
    return p if p.is_file() else None


# ---- a first guess without a model: keyword rules ------------------------------------------------------------------
STOP = set("""a an and are as at be but by for from has have how in into is it its of on or that the this to was what
when where which who why will with you your der die das und ist ein eine einen mit von für auf den dem des nicht sich
auch wie was wenn oder aus bei nur noch zum zur über ich du er sie wir ihr""".split())
TOPIC_WORDS = {
    "trending": ("trend", "trending", "viral", "release", "released", "launch", "launched", "announces", "announced",
                 "just shipped", "new model", "neu", "neue", "news", "heute", "today", "this week"),
    "recent_past": ("my agent", "mein agent", "yesterday", "gestern", "last week", "letzte woche", "happened",
                    "passiert", "incident", "fehler", "bug", "broke", "kaputt", "instead"),
    "manufactured": ("test", "tested", "getestet", "compare", "vergleich", "benchmark", "build", "baut", "replace",
                     "ersetzt", "free", "gratis", "alternative", "experiment"),
    "far_past": ("years ago", "jahren", "back then", "damals", "lesson", "lektion", "story", "geschichte"),
    "present": ("idea", "idee", "thought", "gedanke", "question", "frage"),
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-ZäöüÄÖÜß0-9]{3,}", (text or "").lower()) if w not in STOP}


def guess_topic_type(text: str, source: str | None = None) -> str | None:
    """Hormozi's topic type from words in the text; a scout hit without other words is trending."""
    low = (text or "").lower()
    hits = {t: sum(1 for w in ws if re.search(rf"\b{re.escape(w)}\b", low)) for t, ws in TOPIC_WORDS.items()}
    best = max(hits, key=lambda t: (hits[t], t == "manufactured"))
    if hits[best]:
        return best
    return "trending" if source == "scout" else None


def suggest(text: str, length: str | None = None, source: str | None = None,
            lib: dict[str, dict] | None = None) -> dict | None:
    """A deterministic first guess (no model): the format whose `when`, `keywords`, kinds and name share the most
    words with the text, preferring formats that serve the guessed topic type. A suggestion, never a decision."""
    lib = load() if lib is None else lib
    if not lib:
        return None
    words = _words(text)
    topic = guess_topic_type(text, source)
    scored = []
    for f in lib.values():
        if length in LENGTHS and f["length"] != length:
            continue
        hay = " ".join([f.get("when", ""), f.get("name", ""), " ".join(f.get("keywords") or [])]
                       + [f"{k.get('name', '')} {k.get('when', '')}" for k in f.get("kinds") or []])
        shared = sorted(words & _words(hay))
        keyword_hits = [k for k in f.get("keywords") or []
                        if re.search(rf"\b{re.escape(k.lower())}\b", (text or "").lower())]
        score = len(shared) + 2 * len(keyword_hits) + (2 if topic and topic in f["topic_types"] else 0)
        scored.append((score, f["source"] == "studio", f["id"], f, shared, keyword_hits))
    if not scored:
        return None
    scored.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    score, _, fid, f, shared, keyword_hits = scored[0]
    if score <= 0:
        return None
    why = []
    if keyword_hits:
        why.append("keywords " + ", ".join(keyword_hits[:4]))
    if shared:
        why.append("shares " + ", ".join(shared[:5]))
    if topic and topic in f["topic_types"]:
        why.append(f"topic type {TOPIC_NAMES[topic]}")
    return {"format": fid, "length": f["length"], "topic_type": topic if topic in f["topic_types"] else None,
            "reason": f"Rule guess: {'; '.join(why)}.", "score": score, "kind": "rule"}


# ---- the episode's pick ---------------------------------------------------------------------------------------------
def _to_short(project: dict) -> None:
    from . import episodes
    ids = episodes.SHORT_STEPS["original"]
    project.update(kind="short", mode="original", source_episode=None, step_ids=ids, format="portrait")
    for sid in episodes.STEP_IDS:
        if sid not in ids:
            project["steps"][sid] = {"status": "skipped", "absent": True}


def _to_long(project: dict) -> None:
    from . import brand, episodes
    project.update(kind="episode", format=brand.load().value("edit_style.format", "landscape") or "landscape")
    for k in ("mode", "source_episode", "step_ids"):
        project.pop(k, None)
    for s in episodes.STEPS:
        st = project["steps"].get(s["id"], {})
        if st.get("absent"):
            project["steps"][s["id"]] = {"status": "skipped" if s.get("planned") else "open"}
    episodes.skip_switched_off(project["steps"])


def _started(project: dict) -> bool:
    return any(project.get("steps", {}).get(s, {}).get("status") in ("working", "waiting", "done")
               for s in ("title", "script", "record", "edit"))


def choose(episode: str, fid: str, length: str | None = None, topic_type: str | None = None,
           input_kind: str | None = None) -> dict:
    """Write the pick into project.json: show_format, form, length, topic_type. A short format turns an episode into
    an original Short (and back) while no later step has started."""
    from . import episodes
    f = get(fid)
    if f is None:
        raise ValueError(f"no format {fid!r}; list them with: crewcut formats")
    if length is not None and length not in LENGTHS:
        raise ValueError("length must be long or short")
    if length and length != f["length"]:
        raise ValueError(f"format {fid} is {f['length']}, not {length}")
    if topic_type is not None and topic_type not in TOPIC_TYPES:
        raise ValueError(f"topic type must be one of {', '.join(TOPIC_TYPES)}")
    if input_kind is not None and input_kind not in INPUT_KINDS:
        raise ValueError(f"input must be one of {', '.join(INPUT_KINDS)}")
    p = episodes.read(episode)
    if p.get("kind") == "short" and p.get("mode") == "clip":
        raise ValueError("a clip Short is cut from a finished episode; it has no show format")
    want_short = f["length"] == "short"
    is_short = p.get("kind") == "short"
    if want_short != is_short:
        if _started(p):
            raise ValueError(f"{episode} has started later steps; it stays a {'Short' if is_short else 'long video'}")
        _to_short(p) if want_short else _to_long(p)
    p.update(show_format=fid, form=fid, length=f["length"])
    if topic_type:
        p["topic_type"] = topic_type
    if input_kind:
        p["input_kind"] = input_kind
    episodes.write(episode, p)
    return p


def _section(text: str, *names: str) -> str:
    """Text of a `key: value` line or a `## Heading` section with one of these names."""
    for n in names:
        m = re.search(rf"(?im)^\s*[-*]?\s*{re.escape(n)}\s*:\s*(.+)$", text)
        if m:
            return m.group(1).strip()
    for n in names:
        m = re.search(rf"(?ims)^#+\s*{re.escape(n)}\b[^\n]*\n(.*?)(?=^#|\Z)", text)
        if m and m.group(1).strip():
            return " ".join(m.group(1).split())
    return ""


def choice_file(episode: str) -> Path | None:
    brief = paths.episode_dir(episode) / "brief"
    files = [p for p in brief.glob("FORMAT-v*.md") if FORMAT_FILE.match(p.name)] if brief.is_dir() else []
    return max(files, key=lambda p: int(FORMAT_FILE.match(p.name).group(1))) if files else None


def read_choice(episode: str) -> dict | None:
    """The newest brief/FORMAT-vNNN.md: {format, name, length, topic_type, input, reason, runner_up, file}."""
    p = choice_file(episode)
    if p is None:
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    text = text.split("\n---\n")[0]
    fid = _section(text, "format", "Format").strip("`* ")
    fid = fid.split()[0].strip("`*,.") if fid else ""
    f = get(fid)
    return {"format": fid, "name": (f or {}).get("name") or fid, "known": f is not None,
            "length": _section(text, "length", "Länge").split(" ")[0].strip("`*,.") or (f or {}).get("length"),
            "topic_type": _section(text, "topic_type", "topic type", "Themenart").split(" ")[0].strip("`*,.") or None,
            "input": _section(text, "input", "Eingabe").split(" ")[0].strip("`*,.") or None,
            "reason": _section(text, "reason", "why", "Warum", "Begründung"),
            "runner_up": _section(text, "runner_up", "runner-up", "Runner-up", "Zweitbeste Wahl", "Zweitbeste"),
            "file": f"brief/{p.name}"}


def prompt_block(episode: str | None) -> str:
    """The format block of the system prompt while an episode has a show format."""
    if not episode or episode.startswith("_"):
        return ""
    from . import episodes
    try:
        p = episodes.read(episode)
    except (FileNotFoundError, ValueError):
        return ""
    fid = p.get("show_format")
    f = get(fid)
    if f is None:
        return ""
    lines = [f"SHOW FORMAT of this episode: {f['name']} ({f['id']}, {f['length']}"
             + (f", {f['cadence']}" if f.get("cadence") else "") + ")",
             f"When it fits: {f['when']}"]
    if p.get("topic_type"):
        lines.append(f"Topic type: {TOPIC_NAMES.get(p['topic_type'], p['topic_type'])}")
    if f.get("kinds"):
        lines.append("Kinds: " + "; ".join(f"{k['id']} ({k['name']}): {k['when']}" for k in f["kinds"]))
    lines.append("Structure, in this order:")
    lines += [f"  {i}. {u['name']}: {u['purpose']}" + (f" (about {u['seconds']} s)" if u.get("seconds") else "")
              for i, u in enumerate(f["structure"], 1)]
    for key, label in (("packaging_rules", "Packaging rules"), ("title_formulas", "Title formulas"),
                       ("thumbnail_formats", "Thumbnail formats (crewcut thumbnail formats show <id>)")):
        if f.get(key):
            lines.append(f"{label}: " + "; ".join(f[key]))
    for key, label in (("script_template", "Full-script template"), ("cue_template", "Cue sheet template"),
                       ("testplan_template", "Test plan template")):
        t = template(f, key)
        if t:
            lines.append(f"{label}: {t}")
    lines.append(f"Style checker format: {f['checker_format']}; the gate checks the "
                 + ("cue sheet derived from the full script." if f["gate_on"] == "cues" else "full script first."))
    if f.get("strong"):
        lines.append(f"Evidence for this format: {f['strong']}")
    ref = studio_reference()
    if ref:
        lines.append(f"Where topics come from and the five topic types (read it): {ref}")
    return "\n".join(lines) + "\n"


def catalogue(lib: dict[str, dict] | None = None) -> str:
    """The short list of all formats for the plan task."""
    lib = load() if lib is None else lib
    out = []
    for f in sorted(lib.values(), key=lambda f: (f["length"], f["id"])):
        kinds = f" Kinds: {', '.join(k['id'] for k in f.get('kinds') or [])}." if f.get("kinds") else ""
        out.append(f"- {f['id']} ({f['length']}, {f['name']}; topic types {', '.join(f['topic_types'])}): "
                   f"{f['when']}{kinds}" + (f" Evidence: {f['strong']}" if f.get("strong") else ""))
    return "\n".join(out)


# ---- command line ---------------------------------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crewcut formats", description="Show formats: the library new episodes use.")
    p.add_argument("cmd", nargs="?", default="list", choices=["list", "show", "check", "choose", "score"])
    p.add_argument("args", nargs="*", help="show <id> | choose <episode> <id>")
    p.add_argument("--length", choices=LENGTHS)
    p.add_argument("--topic-type", choices=TOPIC_TYPES)
    p.add_argument("--input", choices=INPUT_KINDS)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if a.cmd == "score":
        from . import scoreboard
        return scoreboard.cli(as_json=a.json)
    lib, errors = report()
    if a.cmd == "check":
        for e in errors:
            print(e)
        print(f"{len(lib)} usable formats, {len(errors)} problems.")
        return 1 if errors else 0
    if a.cmd == "show":
        if not a.args:
            print("Which format? crewcut formats show <id>", file=sys.stderr)
            return 2
        f = lib.get(a.args[0])
        if f is None:
            print(f"No format {a.args[0]!r}. List them with: crewcut formats", file=sys.stderr)
            return 1
        print(json.dumps(public(f), indent=1, ensure_ascii=False))
        return 0
    if a.cmd == "choose":
        if len(a.args) != 2:
            print("crewcut formats choose <episode> <format-id> [--length] [--topic-type] [--input]", file=sys.stderr)
            return 2
        try:
            p = choose(a.args[0], a.args[1], length=a.length, topic_type=a.topic_type, input_kind=a.input)
        except (ValueError, FileNotFoundError) as e:
            print(f"crewcut formats choose: {e}", file=sys.stderr)
            return 1
        print(f"{p['id']}: format {p['show_format']} ({p['length']}, kind {p.get('kind')}"
              + (f", topic type {p['topic_type']}" if p.get("topic_type") else "") + ")")
        return 0
    if a.json:
        print(json.dumps([public(f) for f in lib.values()], indent=1, ensure_ascii=False))
        return 0
    for e in errors:
        print(f"problem: {e}", file=sys.stderr)
    if not lib:
        print("The show format library is empty. Put formats.json into the studio's brand/show-formats/.")
        return 1
    print(f"{len(lib)} show formats (studio formats replace examples with the same id):")
    for f in sorted(lib.values(), key=lambda f: (f["length"], f["id"])):
        print(f"  {f['id']:<26} {f['length']:<5} {f['source']:<7} {f['name']}")
    return 0


__all__ = ["CHOICES", "INPUT_KINDS", "LENGTHS", "TOPIC_TYPES", "catalogue", "choice_file", "choose", "enabled", "get",
           "guess_topic_type", "library_dirs", "load", "main", "problems_of", "prompt_block", "public", "read_choice",
           "report", "settings", "studio_reference", "suggest", "template"]
