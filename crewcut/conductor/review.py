"""The Critic's verdict moves the work on by itself.

A builder (the Editor, the Writer, the Designer) asks the Critic for a check and stops. When the Critic's run ends, the
conductor (this code, no tokens) reads the verdict from the report (`review/critic-*.md`) and acts:

  back  the builder gets the next round with the report named in its task;
  show  the builder proposes its card to the user, with the version the Critic checked;
  else  the builder reads the report and does what it says.

A step gets at most `critic.max_rounds` reviews (default 3, or the "of M" of the Critic's "Round N of M"). When the last
one still sends the work back, a card goes to the user instead of another round. The count starts again after the user
decided a card of that step. Nothing is queued twice: a builder that runs already gets the verdict as a relay at its
next `crewcut` call, and a builder that someone else woke already is left alone.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import config, db, episodes, paths, team

MAX_ROUNDS = 3
VERDICT_LINE = re.compile(r"(?im)^[\s#*>_-]*(?:verdict|urteil)[\s*_]*[:=][\s*_]*(back|show|user|pass|revise)\b")
BACK = re.compile(
    r"zurück an (?:den|die|das)\b|an (?:den|die|das) \w+ zurück|geht\b.{0,60}\bzurück|zurückgeben|nicht (?:zeigen|"
    r"gezeigt|freigegeben)|noch nicht (?:zeigen|an\b)|back to the (?:editor|writer|designer|builder|author)|"
    r"(?:goes|go|send|sends|sent) (?:it |this )?back\b|(?:do not|don't|not to) show|not ready for the user|"
    r"\brevise\b", re.I)
SHOW = re.compile(
    r"freigegeben|kann (?:so )?(?:gezeigt werden|an den (?:user|nutzer))|geht (?:so )?an (?!den |die |das )\w+|"
    r"\bzeigen\b|ready for the user|(?:may|can) go to the user|show (?:it )?to the user|\bpass(?:es|ed)?\b", re.I)
TO_NAME = re.compile(r"\ban [A-ZÄÖÜ][a-zäöüß]+")   # "an Marco": to the creator, by name (case matters here)
ROUND = re.compile(r"(?i)\b(?:round|runde)[:\s]+(\d+)\s+(?:of|von|/)\s+(\d+)")
PATH = re.compile(r"review/[\w.\-/]*critic[\w.\-/]*\.md")


def _step(step: str | None) -> dict:
    try:
        return episodes.step_info(step) if step else {}
    except KeyError:
        return {}


def limit() -> int:
    try:
        return max(1, int(config.get("crewcut", "critic.max_rounds", MAX_ROUNDS)))
    except (TypeError, ValueError):
        return MAX_ROUNDS


def verdict(text: str) -> str | None:
    """'back', 'show' or None from a report: the explicit `Verdict:` line wins, then the headline and the verdict
    section, then the whole text. A sentence that sends something back outweighs one that clears it."""
    m = VERDICT_LINE.search(text or "")
    if m:
        return "back" if m.group(1).lower() in ("back", "revise") else "show"
    text = text or ""
    lines = [x for x in text.splitlines() if x.strip()]
    m = re.search(r"(?ims)^#+\s*(?:urteil|verdict|ergebnis|result)\b[^\n]*$(.*?)(?=^#+\s|\Z)", text)
    for part in (lines[0] if lines else "", m.group(1) if m else ""):
        if BACK.search(part):
            return "back"
        if SHOW.search(part) or TO_NAME.search(part):
            return "show"
    return "back" if BACK.search(text[:1500]) else None   # further down only a "back" counts, never a "show"


def report_of(job: dict, text: str) -> Path | None:
    """The Critic's report of this run: a review file its last words name, else the newest review/critic-*.md written
    during the run."""
    ep = paths.episode_dir(job["episode"])
    for rel in PATH.findall(text or ""):
        p = ep / rel
        if p.is_file():
            return p
    started = db.parse_time(job.get("started")) or 0
    files = [p for p in (ep / "review").glob("*critic*.md") if p.is_file() and p.stat().st_mtime >= started - 1]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def builder_of(job: dict) -> str | None:
    """Who built what the Critic checked: the job that asked for the check, else the owner of the step."""
    parent = db.get("jobs", job["parent"]) if job.get("parent") else None
    if parent and parent.get("identity") not in (None, "critic", "showrunner") and parent.get("episode") == job["episode"]:
        return parent["identity"]
    info = _step(job.get("step"))
    return info.get("owner") if info.get("owner") not in (None, "critic") else None


def is_review(job: dict) -> bool:
    d = job.get("data") or {}
    return (job.get("identity") == "critic" and job.get("kind") == "agent" and bool(job.get("episode"))
            and not job["episode"].startswith("_") and bool(job.get("step")) and job.get("status") == "done"
            and not d.get("auto_card") and not d.get("crew_message") and not d.get("motion_insert")
            and d.get("conversation_scope", "episode") == "episode" and not d.get("origin_scope"))


def _since(episode: str, step: str) -> str:
    """The time the user last decided a card of this step: rounds count from there."""
    with db.conn() as c:
        r = c.execute("SELECT MAX(decided_at) AS t FROM cards WHERE episode = ? AND step = ? AND decided_at IS NOT NULL "
                      "AND status IN ('accepted', 'declined') AND kind NOT IN ('rule', 'spend')",
                      (episode, step)).fetchone()
    return (r["t"] if r else None) or ""


def round_of(job: dict) -> int:
    """1 for the first review of a step since the user's last decision there, 2 for the next one that follows a
    'back', and so on. Older runs without a recorded verdict count by their last words."""
    with db.conn() as c:
        rs = db.rows(c.execute(
            "SELECT * FROM jobs WHERE episode = ? AND step = ? AND identity = 'critic' AND status = 'done' AND id < ? "
            "AND created > ? ORDER BY id", (job["episode"], job["step"], job["id"], _since(job["episode"], job["step"]))))
    n = 0
    for r in rs:
        if not is_review(r):
            continue
        v = ((r.get("data") or {}).get("review") or {}).get("verdict") or verdict(r.get("result") or "")
        if v == "back":
            n += 1
    return n + 1


def _woken(job: dict, builder: str) -> dict | None:
    """A job of the builder that already carries the work on: running, queued, or made after the check began."""
    with db.conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = ? AND (status IN ('queued', 'running') OR "
                      "id > ?) ORDER BY status = 'running' DESC, id DESC LIMIT 1",
                      (job["episode"], builder, job["id"])).fetchone()
        card = c.execute("SELECT id FROM cards WHERE episode = ? AND identity = ? AND status = 'open' AND (job > ? OR "
                         "created > ?)", (job["episode"], builder, job["id"], job.get("created") or "")).fetchone()
    j = db.row(r)
    if j:
        return j
    return {"card": card["id"]} if card else None


def _resume(job: dict, builder: str) -> dict:
    from .. import crewtalk, engines
    parent = db.get("jobs", job["parent"]) if job.get("parent") else None
    d = (parent or {}).get("data") or {}
    if parent and parent.get("identity") == builder and d.get("session") and d.get("engine"):
        return {"resume": {"engine": d["engine"], "session": d["session"]}}
    res = crewtalk.last_session(job["episode"], builder, engines.current_name())
    return {"resume": res} if res else {}


def after_review(job: dict, res_text: str) -> dict | None:
    """Act on a finished Critic review. Returns what happened, or None when this run was no review to act on."""
    if not is_review(job):
        return None
    d = job.get("data") or {}
    if "transcript_review" in d:
        return None   # a review of what was said: stylegate.after_transcript_review hands its cut list to the edit
    if "style_gate_kritik" in d:
        from .. import stylegate
        if stylegate.settings()["mode"] != "off":
            return None   # the style gate asked for this review and routes it itself (stylegate.after_critic)
    builder = builder_of(job)
    if not builder or team.get(builder) is None:
        return None
    from . import flow, queue
    episode, step = job["episode"], job["step"]
    report = report_of(job, res_text)
    ep = paths.episode_dir(episode)
    rel = str(report.relative_to(ep)) if report else None
    text = report.read_text(encoding="utf-8", errors="replace") if report else ""
    v = verdict(text) or verdict(res_text)
    n = round_of(job)
    m = ROUND.search(text) or ROUND.search(res_text or "")
    most = int(m.group(2)) if m and 1 <= int(m.group(2)) <= 10 else limit()
    info = {"verdict": v, "file": rel, "round": n, "limit": most, "builder": builder}
    db.update("jobs", job["id"], data={**(job.get("data") or {}), "review": info})
    name = (team.get(builder) or {}).get("name", builder)
    where = f"`{rel}`" if rel else "its last message (`crewcut chat --last 5`)"
    card_kind = _step(step).get("card") or "other"
    other = _woken(job, builder)
    if other and other.get("status") != "running":   # someone woke it already, or it proposed its card
        return {**info, "action": "none", "by": other.get("id") or other.get("card")}
    if v == "back" and n >= most:
        return {**info, "action": "card", "card": _limit_card(job, info, text or res_text)}
    if v == "back":
        line = f"The Critic sent it back (review {n} of {most}). The {name} works on the next round."
        task = (f"The Critic checked your work and sent it back (review round {n} of {most}). The report is {where}. "
                f"Fix every blocking finding in it, run your checks, then ask the Critic for review {n + 1} of {most} "
                f"with `crewcut job add --identity critic --step {step} \"check <new version>, report "
                "review/critic-<version>.md\"` and stop. If the report says the fixed version may go to the user without "
                f"another review, propose your card of kind {card_kind} instead. Never show the user a version the "
                "Critic sent back.")
    elif v == "show":
        line = f"The Critic cleared it (review {n} of {most}). The {name} proposes the card."
        task = (f"The Critic checked your work and cleared it for the user (review round {n} of {most}). The report is "
                f"{where}. Do not change the version it checked. Propose your card of kind {card_kind} with exactly "
                "that file now, and put what the Critic could not check (for example sound to listen to) in its body.")
    else:
        line = f"The Critic finished review {n} of {most}. The {name} reads the verdict."
        task = (f"The Critic finished its review of your work (review round {n} of {most}). The report is {where}. Read "
                "its verdict. If it sends the work back, fix the findings, run your checks and ask the Critic again "
                f"with `crewcut job add --identity critic --step {step} …`" +
                (", unless this was the last round: then propose your card and list the open findings in its body. "
                 if n >= most else ". ") +
                f"If it clears the work, propose your card of kind {card_kind} with exactly the version it checked.")
    if other and other.get("status") == "running":   # it gets the verdict at its next crewcut call (deliver.py)
        flow.post(episode, f"{line} {task}", author="critic", cite=rel, step=step, relay_for=[builder])
        return {**info, "action": "relay", "job": other["id"]}
    jid = queue.add(episode, builder, step, task,
                    data={**_resume(job, builder), "review_of": job["id"], "reason": line})
    db.update("jobs", jid, doing=line[:200])
    flow.post(episode, line, cite=rel, step=step, job=None)
    return {**info, "action": "queued", "job": jid}


def _limit_card(job: dict, info: dict, text: str) -> int:
    from .. import approvals
    name = (team.get(info["builder"]) or {}).get("name", info["builder"])
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    head = lines[0].lstrip("# ").strip() if lines else "The Critic's report"
    body = (f"The Critic checked {info['round']} times and still sends it back: {head}\n\n"
            f"Yes: you see the current version now, as it is, with the open findings listed. "
            f"No, with your words: one more round for the {name}.")
    card = approvals.propose(job["episode"], job["step"], "other", f"Review limit reached: {head}"[:160], body=body,
                             file=info["file"], identity="critic", job=None,
                             data={"critic_limit": {**info, "review_job": job["id"]}})
    return card["id"]


def on_limit_card(card: dict) -> bool:
    """The user's answer to a review-limit card. True when handled here."""
    d = (card.get("data") or {}).get("critic_limit")
    if not d:
        return False
    from . import queue
    episode, step, builder = card["episode"], card.get("step") or d.get("step"), d["builder"]
    kind = _step(step).get("card")
    review_job = db.get("jobs", d.get("review_job") or 0) or {}
    data = _resume(review_job, builder) if review_job else {}
    where = f"`{d['file']}`" if d.get("file") else "the Critic's last report"
    if card["status"] == "accepted":
        task = (f"The user wants to see the current version now, after {d['round']} reviews (card #{card['id']}). Do "
                f"not change it. Propose your card of kind {kind or 'other'} with the version the Critic checked last "
                f"and list the open findings from {where} in its body.")
    else:
        task = (f"The user wants one more round after {d['round']} reviews (card #{card['id']}). Their words: "
                f"{card.get('reason') or 'see the latest chat messages'}. Fix the findings in {where} and what the user "
                f"said, run your checks, then propose your card of kind {kind or 'other'}.")
    queue.add(episode, builder, step, task, data={**data, "review_of": review_job.get("id")})
    return True
