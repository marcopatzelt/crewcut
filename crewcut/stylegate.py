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
            "timeout_seconds": 120}
INTERFACE = 1
NAME = re.compile(r"^(?P<kind>SCRIPT|SHORT)-v(?P<n>\d+)(?P<rest>[^/]*)\.(?:md|txt)$", re.I)
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
    highest version number; at the same number the approved script, else the newer file."""
    brief = paths.episode_dir(episode) / "brief"
    out: dict[str, Path] = {}
    approved = _approved(episode)
    for p in (sorted(brief.iterdir()) if brief.is_dir() else []):
        m = NAME.match(p.name)
        if not m or not p.is_file():
            continue
        kind = m.group("kind").upper()
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
        found[kind] = p
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


def run(p: Path, fmt: str, title: str | None = None, cfg: dict | None = None, tool: Path | None = None) -> dict:
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
    cmd = [sys.executable, str(tool), str(p), "--json", "--format", fmt]
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
    out["failed"] = [{k: c.get(k) for k in ("id", "alt", "rule", "kind", "titel", "measured", "target", "line", "fix")
                      if c.get(k) is not None} for c in checks if c.get("pass") is False]
    out["open"] = [c.get("id") for c in checks if c.get("kind") == "kritik" and c.get("pass") is None]
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


def writer_round(episode: str, verdict: dict, job: dict | None = None, why: str = "") -> dict:
    """Send the failed checks back to the Writer (bounded), or ask the user after the last round."""
    from .conductor import flow, queue
    cfg = settings()
    n = _count(episode, "style_gate_round") + 1
    most = cfg["max_rounds"]
    if n > most:
        return {"action": "card", "card": limit_card(episode, verdict, most)}
    task = (f"{why}The style check (the studio's {cfg['skill']} checker) fails on your newest script; round {n} of "
            f"{most}. Fix every failed check at its line, as its fix says, and keep what passes:\n{text(verdict)}\n\n"
            "Run the checker yourself until its automatic part passes "
            f"(`python3 {verdict.get('checker')} <file> --nur-auto`), write a new version (SCRIPT-vNNN with the next "
            "number), then ask the Critic again for the answers to its questions in `<script>.kritik.json` and its "
            "review (`crewcut job add --identity critic --step script \"…\"`) and stop. A script card is refused while "
            "the full check fails.")
    jid = queue.add(episode, "writer", "script", task,
                    data={**_resume(job), "style_gate_round": n, "style_gate": summary(verdict)})
    db.update("jobs", jid, doing=f"Style check round {n} of {most}"[:200])
    flow.post(episode, f"{short_line(verdict)} The Writer works on round {n} of {most}.", step="script")
    return {"action": "writer", "job": jid, "round": n}


def critic_round(episode: str, verdict: dict, job: dict | None = None) -> dict:
    """The automatic checks pass and only the Critic's answers are missing: the Critic answers its questions."""
    from .conductor import flow, queue
    cfg = settings()
    n = _count(episode, "style_gate_kritik") + 1
    if n > cfg["max_rounds"]:
        return {"action": "card", "card": limit_card(episode, verdict, cfg["max_rounds"])}
    files = [r for r in verdict["results"] if r["open"] and not r["failed"]]
    lines = "\n".join(f"- {r['file']}: answer {', '.join(r['open'])} in "
                      f"{str(Path(r['file']).with_suffix('.kritik.json'))}" for r in files)
    task = ("The style check's automatic part passes; your answers to its Critic questions are missing:\n" + lines +
            f"\nRun `python3 {verdict.get('checker')} <file> --json`: every check of kind kritik has its question "
            "(frage). Answer each with true or false and one sentence of reason, as JSON next to the script, "
            '{"K-…": {"antwort": true, "grund": "…"}}. In doubt: false. Then write your review report '
            "review/critic-<version>.md as usual, ending with the Verdict and Round lines. Never change the script.")
    jid = queue.add(episode, "critic", "script", task, parent=(job or {}).get("id"),
                    data={"style_gate_kritik": n, "style_gate": summary(verdict)})
    db.update("jobs", jid, doing="Answering the style check's Critic questions")
    flow.post(episode, f"{short_line(verdict)} The Critic answers its questions now.", step="script")
    return {"action": "critic", "job": jid}


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
    auto_or_no = any(r["failed"] or r.get("error") for r in v["results"])
    if auto_or_no or v.get("error"):
        return writer_round(episode, v, job)
    return critic_round(episode, v, job)


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
            f" and the script does not go to recording; the conductor sends the failed checks back (at most "
            f"{cfg['max_rounds']} rounds). The checker's rules win over the generic craft where they differ.")


__all__ = ["Blocked", "DEFAULTS", "MODES", "after_writer", "check", "checker", "failed_ids", "guard_advance",
           "latest", "limit_card", "needs_gate", "on_limit_card", "require", "run", "settings", "short_line",
           "subjects", "summary", "text", "writer_note"]
