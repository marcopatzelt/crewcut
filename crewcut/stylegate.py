"""The style gate: a studio's own style checker decides whether a script may go on to recording.

A studio can bring a script style of its own as a skill with a checker (by default the skill `deutscher-hormozi` with
`scripts/stil_check.py`, the studio owns both). The gate runs that checker, the same way every time, and nothing in the
app moves a failing script on:

1. After the Writer's run in the script step, the conductor checks the newest `brief/SCRIPT-vNNN*.md` and the newest
   `brief/SHORT-vNNN*.md` (`--json`, `--format lang|short`, the Critic's answers `<script>.kritik.json` via
   `--kritik`). Failed automatic checks and Critic questions answered "no" go back to the Writer with their id, line
   and fix, for at most `max_rounds` rounds; then a card asks the user. When only the Critic's answers are missing,
   the Critic gets the script to answer its questions.
2. A script card is refused while its file fails (`approvals.propose`), and a yes on a script card is refused (the
   card goes back to the Writer) when the check fails by then (`approvals.decide`).
3. The way to recording and the cut refuses a failing script: `flow.start_step` for record (and for edit while nothing
   is recorded), `crewcut episode step <id> script done|skipped`, `... record working|waiting`, `crewcut job add
   --step edit` before a recording.

Cue sheets (`crewcut/cuesheet.py`, brief/CUES-vNNN.md or DREHZETTEL-vNNN.md) are long scripts too; when an episode has
one, its newest cue sheet is the long script the gate checks. A checker may add three things to a check, and the gate
acts on them: `points` (the open findings, each with `text`), `instructions` (a file the Critic follows for that
check, for example a sentence-by-sentence review) and `second_opinion: true` with `answer_file` (the gate asks a
second model on the host computer once everything else passes; crewcut/second_opinion.py).

Rounds (`loop`): "rounds" sends the Writer back at most `max_rounds` times, then a card asks the user. "until_pass"
goes on while each round changes what is open, and stops with a card "Not approved: <point>" ("Nicht freigegeben" in a
German studio) as soon as the same open point stays unchanged for two rounds in a row, or after `safety_rounds`. A
script that the checker does not pass never goes to the user as approved.

Settings (`config/crewcut.toml` `[style_gate]`, the style pack's `channel.json` `script.style_gate` wins): `mode`
block (default), warn (the findings go to the chat and the card, nothing is refused) or off; `max_rounds` (3); `skill`
and `checker` (the script inside the skill folder); `timeout_seconds`. Without the skill in the studio the gate is
skipped with a warning. The checker's interface is its version 1 JSON: {"version": 1, "pass", "auto_pass",
"kritik_offen": [...], "checks": [{"id", "rule", "kind": "auto"|"kritik", "pass", "line", "fix", ...}], ...}; exit 0
pass, 1 a failed check or an open or negative Critic answer, 2 unreadable input.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from . import config, db, paths

MODES = ("block", "warn", "off")
DEFAULTS = {"mode": "block", "max_rounds": 3, "skill": "deutscher-hormozi", "checker": "scripts/stil_check.py",
            "timeout_seconds": 120, "loop": "rounds", "safety_rounds": 10}
LOOPS = ("rounds", "until_pass")
INTERFACE = 1
NAME = re.compile(r"^(?P<kind>SCRIPT|SHORT|CUES|DREHZETTEL)-v(?P<n>\d+)(?P<rest>[^/]*)\.(?:md|txt)$", re.I)
CUE_KINDS = ("CUES", "DREHZETTEL")
TITLE_LINE = re.compile(r"(?im)^\W*(?:titel|title)\b")


class Blocked(ValueError):
    """A failing script may not go on. `verdict` holds the gate's result."""

    def __init__(self, message: str, verdict: dict | None = None):
        super().__init__(message)
        self.verdict = verdict or {}


def settings() -> dict:
    out = dict(DEFAULTS)
    toml = config.get("crewcut", "style_gate", {}) or {}
    pack: dict = {}
    try:
        from . import brand
        pack = brand.load().value("channel.script.style_gate", {}) or {}
    except Exception:  # noqa: BLE001 - a broken pack must not switch the gate off
        pack = {}
    for src in (toml, pack):
        if isinstance(src, dict):
            out.update({k: v for k, v in src.items() if v is not None})
    mode = str(out.get("mode") or "block").lower()
    out["mode"] = mode if mode in MODES else "block"      # a typo stays strict
    try:
        out["max_rounds"] = max(1, int(out.get("max_rounds") or DEFAULTS["max_rounds"]))
    except (TypeError, ValueError):
        out["max_rounds"] = DEFAULTS["max_rounds"]
    try:
        out["safety_rounds"] = max(1, int(out.get("safety_rounds") or DEFAULTS["safety_rounds"]))
    except (TypeError, ValueError):
        out["safety_rounds"] = DEFAULTS["safety_rounds"]
    out["loop"] = out["loop"] if out.get("loop") in LOOPS else "rounds"
    return out


def checker(cfg: dict | None = None) -> Path | None:
    """The studio's checker: in the folder of the own skill of that name (its configured path), else
    <studio>/skills/<skill>/. None when the studio has no such skill."""
    cfg = cfg or settings()
    folder = None
    try:
        from . import ownskills
        for s in ownskills.configured():
            if s.get("name") == cfg["skill"] and s.get("folder"):
                folder = Path(s["folder"])
                break
    except Exception:  # noqa: BLE001 - fall back to the plain folder
        folder = None
    folder = folder or paths.studio_root() / "skills" / str(cfg["skill"])
    p = folder / str(cfg["checker"])
    return p if p.is_file() else None


def _version(p: Path) -> tuple[int, float]:
    m = NAME.match(p.name)
    try:
        t = p.stat().st_mtime
    except OSError:
        t = 0.0
    return (int(m.group("n")) if m else -1, t)


def _approved(episode: str) -> Path | None:
    with db.conn() as c:
        r = c.execute("SELECT file FROM cards WHERE episode = ? AND kind = 'script' AND status = 'accepted' "
                      "ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if r and r["file"]:
        try:
            p = paths.inside(paths.episode_dir(episode), r["file"])
        except ValueError:
            return None
        return p if p.is_file() else None
    return None


def latest(episode: str) -> dict[str, Path]:
    """The newest long script and the newest Short script in brief/ ({"SCRIPT": path, "SHORT": path}). Newest is the
    highest version number; at the same number the approved script, else the newer file. Once an episode has a cue
    sheet, its newest cue sheet is the long script (cue sheets replace full texts)."""
    brief = paths.episode_dir(episode) / "brief"
    out: dict[str, Path] = {}
    approved = _approved(episode)
    files = [p for p in (sorted(brief.iterdir()) if brief.is_dir() else []) if NAME.match(p.name) and p.is_file()]
    cues = any(NAME.match(p.name).group("kind").upper() in CUE_KINDS for p in files)
    for p in files:
        m = NAME.match(p.name)
        kind = m.group("kind").upper()
        if kind in CUE_KINDS:
            kind = "SCRIPT"
        elif kind == "SCRIPT" and cues:
            continue
        cur = out.get(kind)
        if cur is None:
            out[kind] = p
            continue
        a, b = _version(p), _version(cur)
        if a[0] > b[0] or (a[0] == b[0] and (p == approved or (cur != approved and a[1] > b[1]))):
            out[kind] = p
    return out


def _kind(episode: str) -> str:
    from . import episodes
    try:
        return episodes.read(episode).get("kind") or "episode"
    except FileNotFoundError:
        return "episode"


def fmt_of(episode: str, p: Path) -> str:
    """lang or short: a SHORT file, or any script of a Short episode, is a Short."""
    if re.match(r"(?i)^short", p.name) or _kind(episode) == "short":
        return "short"
    return "lang"


def subjects(episode: str, file: str | Path | None = None) -> list[Path]:
    """What the gate checks: the given file plus the newest script of the other kind, else the newest of both."""
    found = latest(episode)
    if file is not None:
        p = Path(file)
        p = p if p.is_absolute() else paths.inside(paths.episode_dir(episode), str(file))
        m = NAME.match(p.name)
        kind = m.group("kind").upper() if m else ("SHORT" if re.match(r"(?i)^short", p.name) else "SCRIPT")
        found["SCRIPT" if kind in CUE_KINDS else kind] = p
    return [found[k] for k in ("SCRIPT", "SHORT") if k in found]


def _title(episode: str, p: Path, fmt: str) -> str | None:
    """The approved episode title, for a long script whose notes do not name the title themselves."""
    if fmt != "lang":
        return None
    if p.suffix.lower() in (".md", ".txt"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            return None
        _, _, notes = text.partition("\n---\n")
        if TITLE_LINE.search(notes):
            return None
    from . import episodes
    try:
        project = episodes.read(episode)
    except FileNotFoundError:
        return None
    if project.get("steps", {}).get("title", {}).get("status") != "done":
        return None
    return project.get("title") or None


def _rel(episode: str, p: Path) -> str:
    try:
        return p.resolve().relative_to(paths.episode_dir(episode).resolve()).as_posix()
    except ValueError:
        return str(p)


def run(p: Path, fmt: str, title: str | None = None, cfg: dict | None = None, tool: Path | None = None,
        extra: list[str] | None = None) -> dict:
    """Run the checker on one file. Returns {"pass", "auto_pass", "failed", "open", "error", ...}."""
    cfg = cfg or settings()
    tool = tool or checker(cfg)
    out: dict = {"file": str(p), "format": fmt, "pass": False, "auto_pass": False, "failed": [], "open": [],
                 "error": None, "exit": None, "kritik": None}
    if tool is None:
        out["error"] = "no checker"
        return out
    if not p.is_file():
        out["error"] = f"{p.name} not found"
        return out
    cmd = [sys.executable, str(tool), str(p), "--json", "--format", fmt] + list(extra or [])
    if title:
        cmd += ["--titel", title]
    kritik = p.with_suffix(".kritik.json")
    if kritik.is_file():
        cmd += ["--kritik", str(kritik)]
        out["kritik"] = str(kritik)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=float(cfg.get("timeout_seconds") or 120),
                           cwd=str(tool.parent))
    except (OSError, subprocess.TimeoutExpired) as e:
        out["error"] = f"the checker did not finish: {e}"
        return out
    out["exit"] = r.returncode
    if r.returncode == 2:
        out["error"] = "the checker could not read the file: " + (r.stderr.strip()[:300] or "no reason given")
        return out
    try:
        data = json.loads(r.stdout)
    except ValueError:
        out["error"] = "the checker gave no JSON: " + (r.stderr.strip() or r.stdout.strip())[:300]
        return out
    if data.get("version") != INTERFACE:
        out["error"] = f"the checker speaks interface version {data.get('version')!r}; the gate reads {INTERFACE}"
        return out
    checks = data.get("checks") or []
    keep = ("id", "alt", "rule", "kind", "titel", "measured", "target", "line", "fix", "points", "instructions")
    out["failed"] = [{k: c.get(k) for k in keep if c.get(k) is not None} for c in checks if c.get("pass") is False]
    out["open"] = [c.get("id") for c in checks if c.get("kind") == "kritik" and c.get("pass") is None]
    out["fresh"] = [{"id": c.get("id"), "answer_key": c.get("answer_key"), "frage": c.get("frage")}
                    for c in checks if c.get("fresh_context") and c.get("kind") == "kritik" and c.get("pass") is None]
    out["second_opinion"] = [{"id": c.get("id"), "answer_file": c.get("answer_file"), "measured": c.get("measured"),
                              "checksum": c.get("pruefsumme") or c.get("checksum")}
                             for c in checks if c.get("second_opinion") and c.get("pass") is None and c.get("answer_file")]
    out["instructions"] = sorted({str(c["instructions"]) for c in checks if c.get("instructions")})
    out["hints"] = sum(1 for c in checks if c.get("kind") == "hinweis")
    out["notes"] = [f"Second opinion: {c.get('measured')}" for c in checks
                    if c.get("second_opinion") and c.get("pass") is True]
    out["notes"] += [str(n) for c in checks for n in (c.get("notes") or [])]   # what only the user decides
    out["instructions_used"] = out["instructions"]
    out["pruefstuecke"] = len(data.get("pruefstuecke") or [])
    out["auto_pass"] = bool(data.get("auto_pass"))
    out["pass"] = bool(data.get("pass")) and r.returncode == 0 and not out["failed"] and not out["open"]
    out["words"], out["seconds"], out["times"] = data.get("woerter"), data.get("dauer_s"), data.get("zeiten")
    out["title"] = data.get("titel")
    return out


def check(episode: str, file: str | Path | None = None, files: list[Path] | None = None) -> dict:
    """The gate's verdict for an episode: every subject passes, or the gate is skipped (no skill) or off."""
    cfg = settings()
    verdict: dict = {"mode": cfg["mode"], "pass": True, "skipped": None, "checker": None, "results": [],
                     "at": db.now(), "max_rounds": cfg["max_rounds"]}
    if cfg["mode"] == "off":
        verdict["skipped"] = "the style gate is off (style_gate.mode)"
        return verdict
    tool = checker(cfg)
    if tool is None:
        verdict["skipped"] = (f"the studio has no {cfg['skill']} skill with {cfg['checker']} "
                              f"({paths.studio_root() / 'skills' / str(cfg['skill'])}): the style gate is skipped")
        return verdict
    verdict["checker"] = str(tool)
    todo = files if files is not None else subjects(episode, file)
    if not todo:
        verdict.update({"pass": False, "error": "no script yet: no brief/SCRIPT-vNNN.md or SHORT-vNNN.md"})
        return verdict
    for p in todo:
        fmt = fmt_of(episode, p)
        r = run(p, fmt, _title(episode, p, fmt), cfg, tool)
        r["file"] = _rel(episode, p)
        if r.get("kritik"):
            r["kritik"] = _rel(episode, Path(r["kritik"]))
        verdict["results"].append(r)
    verdict["pass"] = all(r["pass"] for r in verdict["results"])
    return verdict


def failed_ids(verdict: dict) -> list[str]:
    return [f"{x.get('id')}" for r in verdict.get("results", []) for x in r.get("failed", [])]


def text(verdict: dict, limit: int = 14) -> str:
    """The verdict in plain sentences: per file the failed checks with line and fix, the open Critic questions."""
    if verdict.get("skipped"):
        return f"Style gate skipped: {verdict['skipped']}."
    if verdict.get("error"):
        return f"Style check: {verdict['error']}."
    parts = []
    for r in verdict.get("results", []):
        if r.get("error"):
            parts.append(f"{r['file']}: {r['error']}.")
            continue
        if r["pass"]:
            parts.append(f"{r['file']} ({r['format']}): passes.")
            continue
        lines = []
        for x in r["failed"][:limit]:
            where = f" at {x['line']}" if x.get("line") else ""
            what = f" ({x['titel']}: {x.get('measured')}, target {x.get('target')})" if x.get("titel") else ""
            lines.append(f"{x.get('id')}{where}{what}. Fix: {x.get('fix') or 'see the rule'}")
        more = len(r["failed"]) - limit
        head = f"{r['file']} ({r['format']}) fails {len(r['failed'])} check(s)"
        if r["open"]:
            head += f"; open Critic questions: {', '.join(r['open'])} (answers in {Path(r['file']).stem}.kritik.json)"
        parts.append(head + (":\n- " + "\n- ".join(lines) if lines else ".") + (f"\n- … and {more} more" if more > 0
                                                                                  else ""))
    return "\n".join(parts) or "Style check: nothing checked."


def short_line(verdict: dict) -> str:
    """One line for the chat: which file, which ids."""
    if verdict.get("skipped"):
        return f"Style gate skipped: {verdict['skipped']}."
    if verdict.get("error"):
        return f"Style check: {verdict['error']}."
    bad = [r for r in verdict.get("results", []) if not r["pass"]]
    if not bad:
        return "Style check passes: " + ", ".join(r["file"] for r in verdict.get("results", [])) + "."
    out = []
    for r in bad:
        ids = [str(x.get("id")) for x in r["failed"]]
        bits = ([f"{len(ids)} failed ({', '.join(ids[:10])}{' …' if len(ids) > 10 else ''})"] if ids else []) + \
               ([f"{len(r['open'])} Critic question(s) open"] if r["open"] else []) + \
               ([r["error"]] if r.get("error") else [])
        out.append(f"{r['file']}: " + "; ".join(bits))
    return "Style check fails: " + " · ".join(out) + "."


def summary(verdict: dict) -> dict:
    """What a card or a job keeps of a verdict."""
    return {"mode": verdict.get("mode"), "pass": verdict.get("pass"), "skipped": verdict.get("skipped"),
            "at": verdict.get("at"),
            "files": [{"file": r["file"], "format": r["format"], "pass": r["pass"],
                       "failed": [x.get("id") for x in r["failed"]], "open": r["open"], "error": r.get("error")}
                      for r in verdict.get("results", [])]}


def require(episode: str, file: str | Path | None = None, what: str = "go on") -> dict:
    """The verdict; raises Blocked when the mode is block and the script fails."""
    v = check(episode, file)
    if v["mode"] == "block" and not v["pass"] and not v.get("skipped"):
        raise Blocked(f"The script may not {what}: the style check fails.\n" + text(v), v)
    return v


def _recorded(episode: str, project: dict) -> bool:
    if project.get("steps", {}).get("record", {}).get("status") in ("done", "skipped"):
        return True
    originals = paths.episode_dir(episode) / "originals"
    return originals.is_dir() and any(originals.iterdir())


def needs_gate(episode: str, step: str) -> bool:
    """Does moving into `step` (record, edit) or finishing the script step pass the gate? Not for episodes without a
    script step, not for the cut of something already recorded."""
    from . import episodes
    try:
        project = episodes.read(episode)
    except FileNotFoundError:
        return False
    script = project.get("steps", {}).get("script", {})
    if script.get("absent"):
        return False
    if step == "edit":
        return not _recorded(episode, project)
    return step in ("record", "script")


def guard_advance(episode: str, step: str, what: str | None = None) -> dict | None:
    """Raise Blocked when a failing script would move on to `step`. None when this move needs no gate."""
    if not needs_gate(episode, step):
        return None
    return require(episode, what=what or {"record": "go to recording", "edit": "go to the cut",
                                          "script": "leave the script step"}.get(step, "go on"))


# ---- the rounds with the Writer ------------------------------------------------------------------------------------
def _since(episode: str) -> str:
    from .conductor import review
    return review._since(episode, "script")


def _count(episode: str, key: str) -> int:
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT data FROM jobs WHERE episode = ? AND step = 'script' AND created > ?",
                               (episode, _since(episode))))
    return sum(1 for r in rs if (r.get("data") or {}).get(key))


def _busy(episode: str) -> bool:
    """A Writer or a Critic already carries the script on, or a script card waits for the user."""
    with db.conn() as c:
        job = c.execute("SELECT id FROM jobs WHERE episode = ? AND identity IN ('writer', 'critic') AND status IN "
                        "('queued', 'running')", (episode,)).fetchone()
        card = c.execute("SELECT id FROM cards WHERE episode = ? AND step = 'script' AND status = 'open'",
                         (episode,)).fetchone()
    return bool(job or card)


def _resume(job: dict | None) -> dict:
    d = (job or {}).get("data") or {}
    if d.get("session") and d.get("engine"):
        return {"resume": {"engine": d["engine"], "session": d["session"]}}
    return {}


def _german() -> bool:
    try:
        from . import brand
        return str(brand.load().value("channel.language", "") or "").lower().startswith("de")
    except Exception:  # noqa: BLE001 - a broken pack must not stop the gate
        return False


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(text or "").lower()).split())


def points(verdict: dict) -> list[dict]:
    """The open findings of a verdict, each with a stable key: the check id and the text of the point (the sentence a
    Critic marked, or the measured value of an automatic check). Rounds compare these keys."""
    out = []
    for r in verdict.get("results", []):
        if r.get("error"):
            out.append({"key": f"{r.get('format')}::error::{_norm(r['error'])}", "text": r["error"], "id": "error"})
        for x in r.get("failed", []):
            pts = [p for p in (x.get("points") or []) if isinstance(p, dict) and p.get("text")]
            if pts:
                for p in pts:
                    out.append({"key": f"{r.get('format')}::{x.get('id')}::{_norm(p['text'])}", "id": x.get("id"),
                                "text": str(p["text"]), "why": p.get("grund") or p.get("why"),
                                "rewrite": p.get("neu") or p.get("rewrite")})
            else:
                out.append({"key": f"{r.get('format')}::{x.get('id')}::{_norm(x.get('measured'))}", "id": x.get("id"),
                            "text": f"{x.get('titel') or x.get('id')}: {x.get('measured')}", "why": x.get("fix")})
    return out


def _previous_points(episode: str) -> list[dict] | None:
    """The open points the gate sent back last time in this script round (None before the first round)."""
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT data FROM jobs WHERE episode = ? AND step = 'script' AND created > ? "
                               "ORDER BY id DESC", (episode, _since(episode))))
    for r in rs:
        d = r.get("data") or {}
        if "style_gate_points" in d:
            return d["style_gate_points"]
    return None


def stuck(episode: str, verdict: dict) -> dict | None:
    """In until_pass mode: the first open point that was open, unchanged, in the round before too."""
    before = _previous_points(episode)
    if not before:
        return None
    old = {p["key"] for p in before}
    return next((p for p in points(verdict) if p["key"] in old), None)


def _too_many(episode: str, cfg: dict, n: int) -> bool:
    return n > (cfg["safety_rounds"] if cfg["loop"] == "until_pass" else cfg["max_rounds"])


def writer_round(episode: str, verdict: dict, job: dict | None = None, why: str = "") -> dict:
    """Send the open findings back to the Writer, or put them on a card: after max_rounds rounds ("rounds"), or, in
    "until_pass", as soon as the same point stayed open for two rounds in a row (or after safety_rounds)."""
    from .conductor import flow, queue
    cfg = settings()
    n = _count(episode, "style_gate_round") + 1
    if cfg["loop"] == "until_pass":
        same = stuck(episode, verdict)
        if same:
            return {"action": "card", "card": stuck_card(episode, verdict, same)}
    if _too_many(episode, cfg, n):
        return {"action": "card", "card": limit_card(episode, verdict, n - 1)}
    most = cfg["max_rounds"] if cfg["loop"] == "rounds" else None
    of = f"round {n} of {most}" if most else f"round {n} (until the checker and the Critic pass)"
    pts = points(verdict)
    rewrites = "\n".join(f"- \"{p['text'][:160]}\"" + (f" -> {p['rewrite']}" if p.get("rewrite") else "")
                          + (f" ({p['why']})" if p.get("why") else "") for p in pts if p.get("id") not in (None,)
                          and (p.get("rewrite") or p.get("why")))[:6000]
    task = (f"{why}The style check (the studio's {cfg['skill']} checker) fails on your newest script; {of}. Fix every "
            f"open point, as its fix or the Critic's rewrite says, and keep what passes:\n{text(verdict)}\n"
            + (f"\nThe points one by one (sentence -> rewrite):\n{rewrites}\n" if rewrites else "") +
            "\nRun the checker yourself until its automatic part passes "
            f"(`python3 {verdict.get('checker')} <file> --nur-auto`), write a new version (the next number of the same "
            "kind of file), then ask the Critic again for its review and answers in `<script>.kritik.json` "
            "(`crewcut job add --identity critic --step script \"…\"`) and stop. A script card is refused while the "
            "full check fails. A point that stays the same for two rounds stops the loop and goes to the user as not "
            "approved." if cfg["loop"] == "until_pass" else
            f"{why}The style check (the studio's {cfg['skill']} checker) fails on your newest script; {of}. Fix every "
            f"failed check at its line, as its fix says, and keep what passes:\n{text(verdict)}\n\n"
            "Run the checker yourself until its automatic part passes "
            f"(`python3 {verdict.get('checker')} <file> --nur-auto`), write a new version (SCRIPT-vNNN with the next "
            "number), then ask the Critic again for the answers to its questions in `<script>.kritik.json` and its "
            "review (`crewcut job add --identity critic --step script \"…\"`) and stop. A script card is refused while "
            "the full check fails.")
    jid = queue.add(episode, "writer", "script", task,
                    data={**_resume(job), "style_gate_round": n, "style_gate": summary(verdict),
                          "style_gate_points": pts})
    db.update("jobs", jid, doing=f"Style check {of}"[:200])
    flow.post(episode, f"{short_line(verdict)} The Writer works on {of}.", step="script")
    return {"action": "writer", "job": jid, "round": n}


def _open_for_critic(r: dict) -> list[str]:
    """Open Critic checks for the Critic's own review: not the second opinion, not the fresh second review."""
    skip = {s["id"] for s in r.get("second_opinion", [])} | {f["id"] for f in r.get("fresh", [])}
    return [o for o in r.get("open", []) if o not in skip]


def critic_round(episode: str, verdict: dict, job: dict | None = None) -> dict:
    """The automatic checks pass and the Critic's answers or review are missing (or out of date): the Critic does
    them, following the checker's instructions file where a check names one."""
    from .conductor import flow, queue
    cfg = settings()
    n = _count(episode, "style_gate_kritik") + 1
    if _too_many(episode, cfg, n):
        return {"action": "card", "card": limit_card(episode, verdict, n - 1)}
    files = [r for r in verdict["results"] if _open_for_critic(r) and not r["failed"]]
    lines = "\n".join(f"- {r['file']}: answer {', '.join(_open_for_critic(r))} in "
                      f"{str(Path(r['file']).with_suffix('.kritik.json'))}" for r in files)
    guides = sorted({g for r in files for g in r.get("instructions", [])})
    guide = ("\nFor checks that name instructions, follow them exactly; they say what to read, which questions to ask "
             "of every sentence and unit, how to cite, and what to write: " + ", ".join(f"`{g}`" for g in guides) + "."
             if guides else "")
    task = ("The style check's automatic part passes; your review and answers are missing or out of date:\n" + lines +
            f"\nRun `python3 {verdict.get('checker')} <file> --json`: every check of kind kritik has its question "
            "(frage), and checks of kind hinweis are measurements that point you to places to look (never rules)." +
            guide + " Answer each plain question with true or false and one sentence of reason, as JSON next to the "
            'script, {"K-…": {"antwort": true, "grund": "…"}}. In doubt: false. Then write your review report '
            "review/critic-<version>.md as usual, ending with the Verdict and Round lines. Never change the script.")
    jid = queue.add(episode, "critic", "script", task, parent=(job or {}).get("id"),
                    data={"style_gate_kritik": n, "style_gate": summary(verdict)})
    db.update("jobs", jid, doing="Reviewing the script for the style check")
    flow.post(episode, f"{short_line(verdict)} The Critic reviews it now.", step="script")
    return {"action": "critic", "job": jid}


def fresh_round(episode: str, verdict: dict) -> dict:
    """The Critic approved; a second Critic reads the script again with a fresh context: a new session, no chat, no
    crew notes, told not to read the notes below `---` or earlier reviews (checks with `fresh_context`)."""
    from .conductor import flow, queue
    cfg = settings()
    n = _count(episode, "style_gate_kritik") + 1
    if _too_many(episode, cfg, n):
        return {"action": "card", "card": limit_card(episode, verdict, n - 1)}
    rs = [r for r in verdict["results"] if r.get("fresh")]
    lines = "\n".join(f"- {r['file']}: {f.get('frage') or f['id']}" + (f" Write it under `{f['answer_key']}` in "
                      f"{str(Path(r['file']).with_suffix('.kritik.json'))}." if f.get("answer_key") else "")
                      for r in rs for f in r["fresh"])
    guides = sorted({g for r in rs for g in r.get("instructions", [])})
    task = ("A second review with a fresh context. Read only the script above its line `---`, the instructions "
            + (", ".join(f"`{g}`" for g in guides) if guides else "of the studio's checker")
            + " and the episode's material. Do not read the notes below `---`, earlier reviews (review/critic-*.md, "
            "other keys in the .kritik.json) or the chat; judge as if you saw this script for the first time. Run "
            f"`python3 {verdict.get('checker')} <file> --json` for the checksum and the pieces to judge.\n" + lines +
            "\nThen write your report review/critic-fresh-<version>.md, ending with the Verdict and Round lines. Never "
            "change the script.")
    jid = queue.add(episode, "critic", "script", task, data={"style_gate_kritik": n, "fresh_context": True,
                                                            "style_gate": summary(verdict)})
    db.update("jobs", jid, doing="Second review with a fresh context")
    flow.post(episode, "The Critic approves. A second Critic reads the script once more, with a fresh context.",
              step="script")
    return {"action": "fresh", "job": jid}


def second_opinion_round(episode: str, verdict: dict) -> dict:
    """Everything passes but the second opinion: ask it (or note why it cannot be had) and go on."""
    from . import second_opinion
    from .conductor import flow
    asked = []
    for r in verdict.get("results", []):
        for s in r.get("second_opinion", []):
            script = paths.inside(paths.episode_dir(episode), r["file"])
            res = second_opinion.request(episode, script, Path(s["answer_file"]),
                                         script.with_suffix(".kritik.json"), checksum=s.get("checksum"))
            asked.append(res)
    if any(a.get("status") == "requested" for a in asked):
        flow.post(episode, "The Critic approves. A second opinion from another model is asked now; the card waits "
                  "for it.", step="script")
        return {"action": "second_opinion", "asked": asked}
    return after_second_opinion(episode)


def ready(episode: str, verdict: dict, why: str) -> dict:
    """The checker passes: the Writer proposes the card with exactly this version."""
    from .conductor import flow, queue
    notes = [s for r in verdict.get("results", []) for s in r.get("notes", [])]
    jid = queue.add(episode, "writer", "script", f"{why} The style check passes now ({short_line(verdict)}). Propose "
                    "your script card with exactly the version that was checked" + (", and put this in its body: "
                    + "; ".join(notes) if notes else "") + ".")
    flow.post(episode, short_line(verdict) + " The Writer proposes the card.", step="script")
    return {"action": "ready", "job": jid}


def after_second_opinion(episode: str) -> dict:
    v = check(episode)
    if v.get("skipped") or v["pass"]:
        return ready(episode, v, "The Critic approved and the second opinion is in.")
    if any(r["failed"] or r.get("error") for r in v["results"]):
        return writer_round(episode, v, why="The second opinion found open points. ")
    return {"action": "waiting"}


def stuck_card(episode: str, verdict: dict, point: dict) -> int:
    from . import approvals
    de = _german()
    head = ("Nicht freigegeben: " if de else "Not approved: ") + point["text"]
    body = ((f"Derselbe Punkt war zwei Runden hintereinander offen und ist unverändert:\n\n\"{point['text']}\""
             + (f"\nGrund: {point['why']}" if point.get("why") else "")
             + (f"\nVorschlag des Critic: {point['rewrite']}" if point.get("rewrite") else "")
             + f"\n\n{short_line(verdict)}\n\nDas Skript geht so nicht in die Aufnahme. Ja: der Writer bekommt weitere "
             "Runden, mit deinen Worten. Nein: es bleibt stehen; sag im Chat, was sich ändern soll.") if de else
            (f"The same point stayed open, unchanged, for two rounds in a row:\n\n\"{point['text']}\""
             + (f"\nWhy: {point['why']}" if point.get("why") else "")
             + (f"\nThe Critic's rewrite: {point['rewrite']}" if point.get("rewrite") else "")
             + f"\n\n{short_line(verdict)}\n\nThe script does not go to recording like this. Yes: the Writer gets "
             "more rounds, with your words. No: it stays stopped; say in the chat what should change."))
    card = approvals.propose(episode, "script", "other", head[:160], body=body, identity="showrunner", job=None,
                             data={"style_gate_limit": summary(verdict), "style_gate_stuck": point})
    return card["id"]


def limit_card(episode: str, verdict: dict, rounds: int) -> int:
    from . import approvals
    card = approvals.propose(
        episode, "script", "other", f"The style check still fails after {rounds} rounds",
        body=(f"{short_line(verdict)}\n\nThe script does not go to recording while it fails.\n\nYes: the Writer gets "
              f"{rounds} more rounds. No: it stays stopped; say in the chat what should change (a rule, the "
              "script, or the gate in style_gate.mode)."),
        identity="showrunner", job=None, data={"style_gate_limit": summary(verdict)})
    return card["id"]


def on_limit_card(card: dict) -> bool:
    """The user's answer to the gate's limit card. True when handled here."""
    d = (card.get("data") or {}).get("style_gate_limit")
    if d is None:
        return False
    from .conductor import flow
    episode = card["episode"]
    if card["status"] == "accepted":
        v = check(episode)
        if v["pass"] or v.get("skipped"):
            flow.post(episode, "The style check passes now. The Writer proposes the script card.", card=card["id"])
            from .conductor import queue
            queue.add(episode, "writer", "script", "The style check passes now (" + short_line(v) + "). Propose your "
                      "script card with the newest version.")
        else:
            writer_round(episode, v, why=f"The user gave more rounds (card #{card['id']}). ")
    else:
        flow.post(episode, "The script stays where it is. Say in the chat what should change.", card=card["id"])
    return True


def after_writer(job: dict, res) -> dict | None:
    """After a run of the Writer in the script step: run the gate on the newest scripts and act. None when there was
    nothing to do."""
    d = job.get("data") or {}
    episode = job.get("episode")
    if (not episode or episode.startswith("_") or job.get("step") != "script" or job.get("identity") != "writer"
            or job.get("kind") != "agent" or not getattr(res, "ok", False) or d.get("interview")
            or d.get("conversation_scope", "episode") != "episode" or d.get("origin_scope")):
        return None
    cfg = settings()
    if cfg["mode"] == "off":
        return None
    from . import interview
    if interview.waiting(episode) or _busy(episode) or not latest(episode):
        return None
    v = check(episode)
    db.update("jobs", job["id"], data={**d, "style_gate_after": summary(v)})
    if v.get("skipped") or v["pass"]:
        return None
    if cfg["mode"] == "warn":
        from .conductor import flow
        flow.post(episode, short_line(v) + " (The gate only warns in this studio.)", step="script")
        return {"action": "warned"}
    return route(episode, v, job)


def route(episode: str, v: dict, job: dict | None = None, why: str = "") -> dict:
    """What a failing verdict needs next: the Writer (a finding), the Critic (its review is missing or out of date),
    or the second opinion (everything else passes)."""
    if any(r["failed"] or r.get("error") for r in v["results"]) or v.get("error"):
        return writer_round(episode, v, job, why=why)
    if any(_open_for_critic(r) for r in v["results"]):
        return critic_round(episode, v, job)
    if any(r.get("fresh") for r in v["results"]):
        return fresh_round(episode, v)
    if any(r.get("second_opinion") for r in v["results"]):
        return second_opinion_round(episode, v)
    return writer_round(episode, v, job, why=why)


def after_critic(job: dict, res) -> dict | None:
    """After a Critic run that the gate asked for (data style_gate_kritik): check again and route. The review routing in
    conductor/review.py leaves these runs to the gate."""
    d = job.get("data") or {}
    episode = job.get("episode")
    if (not episode or job.get("identity") != "critic" or job.get("step") != "script" or "style_gate_kritik" not in d
            or not getattr(res, "ok", False)):
        return None
    cfg = settings()
    if cfg["mode"] == "off":
        return None
    v = check(episode)
    db.update("jobs", job["id"], data={**d, "style_gate_after": summary(v)})
    if v.get("skipped"):
        return None
    if v["pass"]:
        return ready(episode, v, "The Critic approves.")
    if cfg["mode"] == "warn":
        from .conductor import flow
        flow.post(episode, short_line(v) + " (The gate only warns in this studio.)", step="script")
        return {"action": "warned"}
    return route(episode, v, job, why="The Critic reviewed your script. ")


# ---- after the recording: the same review on what was said -------------------------------------------------------
WORDS = re.compile(r"^words-(v\d{3,})\.json$")


def plan_of(episode: str) -> Path | None:
    """The cue sheet the recording followed: the approved script card's file if it is a cue sheet, else the newest."""
    from . import cuesheet
    a = _approved(episode)
    if a is not None and cuesheet.is_cue_sheet(a):
        return a
    s = latest(episode).get("SCRIPT")
    return s if s is not None and cuesheet.is_cue_sheet(s) else None


def after_transcript(episode: str, words: Path) -> dict | None:
    """The words of a finished voice cut (work/words-vNNN.json) are in: the Critic reviews what was said against the
    cue sheet, so the edit gets a list of sentences without value (edit/<cut list>). Nothing is blocked."""
    cfg = settings()
    if cfg["mode"] == "off" or not WORDS.match(words.name):
        return None
    plan = plan_of(episode)
    tool = checker(cfg)
    if plan is None or tool is None:
        return None
    from .conductor import flow, queue
    ep = paths.episode_dir(episode)
    version = WORDS.match(words.name).group(1)
    cut = ep / "edit" / f"cutlist-{version}.json"
    material = sorted((ep / "work").glob("material-v*.md"))
    mat = f" --material {_rel(episode, material[-1])}" if material else ""
    cmd = (f"python3 {tool} {_rel(episode, words)} --drehzettel {_rel(episode, plan)}{mat} --json")
    v = run(words, "lang", cfg=cfg, tool=tool, extra=["--drehzettel", str(plan)] + (
        ["--material", str(material[-1])] if material else []))
    guides = ", ".join(f"`{g}`" for g in v.get("instructions", [])) or "the checker's questions"
    task = (f"Review what was said in the finished voice cut {version} against the cue sheet {_rel(episode, plan)}. "
            f"Run `{cmd}` (from the episode folder): its pruefstuecke are the spoken sentences. Follow {guides} for "
            f"the review and write it to {_rel(episode, words.with_suffix('.kritik.json'))}. Every sentence that gives "
            "the viewer nothing is marked; a broken hook or punch line is a blocker (that unit is recorded again). "
            "Then run the same command with `--schnittliste "
            f"{_rel(episode, cut)}` so the Editor gets the cut list with times, and write your report "
            f"review/critic-transcript-{version}.md. Never change the recording or the plan.")
    jid = queue.add(episode, "critic", "edit", task, data={"transcript_review": _rel(episode, words),
                                                           "cut_list": _rel(episode, cut), "plan": _rel(episode, plan)})
    db.update("jobs", jid, doing=f"Reviewing what was said in {version}")
    flow.post(episode, f"The words of {version} are in. The Critic reviews what was said against the cue sheet and "
              "writes a cut list for the edit.", step="edit")
    return {"action": "critic", "job": jid}


def after_transcript_review(job: dict, res) -> dict | None:
    d = job.get("data") or {}
    if job.get("identity") != "critic" or "transcript_review" not in d or not getattr(res, "ok", False):
        return None
    from .conductor import flow
    episode = job["episode"]
    cut = paths.inside(paths.episode_dir(episode), d["cut_list"])
    if cut.is_file():
        try:
            n = len(json.loads(cut.read_text(encoding="utf-8")).get("saetze") or [])
        except (OSError, ValueError):
            n = None
        flow.post(episode, f"Cut list for the edit: {d['cut_list']} ({n if n is not None else '?'} sentences without "
                  "value, with times). The Editor listens to each one and cuts at islands, never at word times.",
                  step="edit", relay_for=["editor"])
        return {"action": "cut_list", "file": d["cut_list"], "sentences": n}
    flow.post(episode, f"The Critic's review of {d['transcript_review']} wrote no cut list ({d['cut_list']}).",
              step="edit")
    return {"action": "none"}


def writer_note(episode: str | None) -> str:
    """The lines the Writer and the Critic get in the script step while the gate is on."""
    cfg = settings()
    if cfg["mode"] == "off":
        return ""
    tool = checker(cfg)
    if tool is None:
        return ""
    strict = "a script card is refused" if cfg["mode"] == "block" else "the chat gets a warning"
    return (f"\nThe style gate is on ({cfg['mode']}): the studio's checker `python3 {tool} <script> [--nur-auto] "
            "[--json]` decides. Write every draft to pass it: run it with --nur-auto until no automatic check fails, "
            "then the Critic answers every question of kind kritik in `<script>.kritik.json` next to the script "
            '({"K-…": {"antwort": true|false, "grund": "…"}}). While the full run fails, ' + strict +
            " and the script does not go to recording; the conductor sends the failed checks back ("
            + (f"at most {cfg['max_rounds']} rounds)" if cfg["loop"] == "rounds" else "rounds go on until the checker and the "
               "Critic pass; a point that stays the same for two rounds goes to the user as not approved)")
            + ". The checker's rules win over the generic craft where they differ. When the studio writes cue sheets "
            "(brief/CUES-vNNN.md or DREHZETTEL-vNNN.md, see docs/cue-sheets.md), the long script is a cue sheet: fixed "
            "opening, per unit a fixed hook and punch line, bullets in between, and the checker says so if a full text "
            "is not allowed.")


__all__ = ["Blocked", "DEFAULTS", "LOOPS", "MODES", "after_critic", "after_second_opinion", "after_transcript",
           "after_transcript_review", "after_writer", "check", "checker", "critic_round", "failed_ids", "guard_advance",
           "latest", "limit_card", "needs_gate", "on_limit_card", "plan_of", "points", "require", "route", "run",
           "second_opinion_round", "settings", "short_line", "stuck", "stuck_card", "subjects", "summary", "text",
           "writer_note", "writer_round"]
