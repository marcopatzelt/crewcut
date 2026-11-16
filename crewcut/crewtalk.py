"""Crew talk: crew members message each other directly, in three narrow cases, with hard limits. Off by default.

The three cases (everything else stays files plus the Showrunner):
- fix: the Critic sends all findings of one version, bundled, to the crew member who built it;
- question: a crew member asks the author of a file it uses what the file does not answer;
- notice: the author of a changed file tells those who already read it (collected, delivered at their next start).

Delivery: when the recipient is running right now, Claude Code's own cross-session messaging reaches it (the sender
uses SendMessage to the recipient's session name; Crewcut logs it from the hook). Otherwise Crewcut resumes the
recipient's last session in this episode with the message. Codex has no tested resume yet: crew talk says so.

Limits (config [crew.talk], the user can change or switch it off with one sentence): 2 rounds per topic, 3 fix rounds per
version, 20 messages per episode; every message names a file or a time stamp. A message is never an approval and never
moves money: approvals are cards, money needs a spend card; nothing in this module creates either.
"""

from __future__ import annotations

import os
import re

from . import config, db, engines, events, team

KINDS = ("fix", "question", "notice")
TABLE = """
CREATE TABLE IF NOT EXISTS crew_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, episode TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL,
  kind TEXT NOT NULL, about TEXT NOT NULL, text TEXT NOT NULL, expects TEXT NOT NULL DEFAULT 'none',
  topic TEXT NOT NULL, reply_to INTEGER, route TEXT, status TEXT NOT NULL DEFAULT 'queued',
  job INTEGER, sender_job INTEGER, equiv_usd REAL NOT NULL DEFAULT 0
);
"""


class Refused(Exception):
    """The message was not sent; the text says what to do instead."""


def _ensure() -> None:
    with db.conn() as c:
        c.executescript(TABLE)


def settings() -> dict:
    s = {"enabled": False, "max_rounds": 2, "max_fix_rounds": 3, "max_per_episode": 20}
    s.update(config.get("crewcut", "crew.talk", {}) or {})
    override = db.kv_get("crew_talk_enabled")
    if override in ("0", "1"):
        s["enabled"] = override == "1"
    return s


def set_enabled(on: bool) -> None:
    db.kv_set("crew_talk_enabled", "1" if on else "0")


def messages(episode: str) -> list[dict]:
    _ensure()
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM crew_messages WHERE episode = ? ORDER BY id", (episode,)))


def _count(episode: str, where: str = "", args: tuple = ()) -> int:
    _ensure()
    with db.conn() as c:
        return int(c.execute(f"SELECT COUNT(*) AS n FROM crew_messages WHERE episode = ? AND status != 'refused' "
                             f"{where}", (episode, *args)).fetchone()["n"])


def topic_of(kind: str, about: str, a: str, b: str, explicit: str | None = None) -> str:
    """A topic is the pair plus the file (without its version), unless the agent names one."""
    if explicit:
        return explicit
    stem = re.sub(r"[-_.]?v\d+", "", about.split("@")[0])
    return f"{kind}:{'+'.join(sorted([a, b]))}:{stem}"


def version_of(about: str) -> str:
    m = re.search(r"v(\d+)", about)
    return m.group(0) if m else about


def check_limits(episode: str, sender: str, recipient: str, kind: str, about: str, topic: str) -> None:
    s = settings()
    total = _count(episode)
    if total >= int(s["max_per_episode"]):
        raise Refused(f"The crew talk budget of this episode ({s['max_per_episode']} messages) is used up. Write it to "
                      "the file and tell the Showrunner.")
    in_topic = _count(episode, "AND topic = ?", (topic,))
    if in_topic >= 2 * int(s["max_rounds"]):
        raise Refused(f"{s['max_rounds']} rounds on this topic without an end. Write your view to the file and tell the "
                      "Showrunner; it decides or asks the user with a card.")
    if kind == "fix":
        fixes = _count(episode, "AND kind = 'fix' AND sender = ? AND recipient = ?", (sender, recipient))
        if fixes >= int(s["max_fix_rounds"]):
            raise Refused(f"{s['max_fix_rounds']} fix rounds are done for this work. Report the open findings to the "
                          "Showrunner instead.")


def running_job(episode: str, identity: str) -> dict | None:
    with db.conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = ? AND status = 'running' ORDER BY id DESC "
                      "LIMIT 1", (episode, identity)).fetchone()
    return db.row(r)


def last_session(episode: str, identity: str, engine: str) -> dict | None:
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT data FROM jobs WHERE episode = ? AND identity = ? AND data IS NOT NULL "
                               "ORDER BY id DESC LIMIT 20", (episode, identity)))
    for r in rs:
        d = r.get("data") if isinstance(r.get("data"), dict) else {}
        if d.get("session") and d.get("engine") == engine:
            return {"engine": engine, "session": d["session"]}
    return None


def session_name(identity: str, episode: str | None) -> str:
    return f"{identity}-{episode or 'studio'}"


def reason_line(sender: str, kind: str, text: str) -> str:
    who = (team.get(sender) or {}).get("name", sender)
    if kind == "fix":
        n = len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+", text)) or text.count(";") + 1
        return f"Fixing {n} finding{'s' if n != 1 else ''} from the {who}"
    if kind == "question":
        return f"Answering a question from the {who}"
    return f"Reading a note from the {who}"


def send(episode: str, sender: str, recipient: str, kind: str, about: str, text: str, expects: str = "reply",
         topic: str | None = None, reply_to: int | None = None, sender_job: int | None = None) -> dict:
    """Log and deliver one crew message. Raises Refused with the reason when a rule says no."""
    _ensure()
    s = settings()
    if not s["enabled"]:
        raise Refused("Crew talk is off in this studio. Write it to the file and tell the Showrunner.")
    if engines.current_name() != "claude":
        raise Refused("Crew talk is not available with Codex yet (its session resume is untested). Write it to the "
                      "file and tell the Showrunner.")
    if kind not in KINDS:
        raise Refused(f"A crew message is one of: {', '.join(KINDS)}.")
    if team.get(recipient) is None or recipient == sender:
        raise Refused(f"There is no other crew member called {recipient}.")
    about = (about or "").strip()
    if not about:
        raise Refused("Every crew message names the file (or a time stamp) it is about: use --about.")
    if expects not in ("reply", "none"):
        expects = "reply"
    if reply_to:
        first = db.get("crew_messages", int(reply_to)) if reply_to else None
        topic = topic or (first or {}).get("topic")
    topic = topic_of(kind, about, sender, recipient, topic)
    check_limits(episode, sender, recipient, kind, about, topic)
    mid = db.insert("crew_messages", at=db.now(), episode=episode, sender=sender, recipient=recipient, kind=kind,
                    about=about, text=text.strip(), expects=expects, topic=topic, reply_to=reply_to,
                    status="queued", sender_job=sender_job)
    msg = db.get("crew_messages", mid)
    if kind == "notice" and not reply_to:
        db.update("crew_messages", mid, route="collected", status="collected")
    elif (live := running_job(episode, recipient)) is not None:
        db.update("crew_messages", mid, route="live", status="delivered", job=live["id"])
    else:
        jid = _resume(msg)
        db.update("crew_messages", mid, route="resume", status="delivered", job=jid)
    msg = db.get("crew_messages", mid)
    events.emit("crew", episode=episode, identity=sender, text=text[:200], data=view(msg))
    _maybe_close(msg)
    return view(msg)


def _resume(msg: dict) -> int:
    from .conductor import queue
    sender = team.get(msg["sender"]) or {}
    task = (f"A message from {sender.get('name', msg['sender'])} ({msg['kind']}, about `{msg['about']}`):\n\n"
            f"{msg['text']}\n\n"
            "This is not an approval and not a new assignment: it is about your own work. Read the file it names, act "
            "on it, write results to files. " +
            (f"Answer in one message: `crewcut say --to {msg['sender']} --reply-to {msg['id']} --about "
             f"{msg['about']} --expects none \"…\"`." if msg["expects"] == "reply" else "No answer is needed."))
    data = {"crew_message": msg["id"], "reason": reason_line(msg["sender"], msg["kind"], msg["text"])}
    res = last_session(msg["episode"], msg["recipient"], "claude")
    if res:
        data["resume"] = res
    step = None
    with db.conn() as c:
        r = c.execute("SELECT step FROM jobs WHERE id = ?", (msg.get("sender_job") or 0,)).fetchone()
        step = r["step"] if r else None
    jid = queue.add(msg["episode"], msg["recipient"], step, task, data=data)
    db.update("jobs", jid, doing=data["reason"])
    return jid


def collected_for(episode: str, identity: str) -> list[dict]:
    """Notices waiting for a crew member's next start; marks them delivered."""
    _ensure()
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT * FROM crew_messages WHERE episode = ? AND recipient = ? AND status = "
                               "'collected' ORDER BY id", (episode, identity)))
    for r in rs:
        db.update("crew_messages", r["id"], status="delivered")
    return rs


def _maybe_close(msg: dict) -> None:
    """An exchange ends with a message that expects no answer: one collapsed line in the chat."""
    if msg["expects"] != "none" or not msg.get("reply_to"):
        return
    from .conductor import flow
    thread = [m for m in messages(msg["episode"]) if m["topic"] == msg["topic"]]
    a = (team.get(thread[0]["sender"]) or {}).get("name", thread[0]["sender"])
    b = (team.get(thread[0]["recipient"]) or {}).get("name", thread[0]["recipient"])
    first, last = thread[0], thread[-1]
    summary = f"{a} and {b} · {first['kind']} about {first['about']} · {len(thread)} messages"
    flow.post(msg["episode"], summary, author="showrunner", facts=None,
              exchange={"topic": msg["topic"], "messages": [view(m) for m in thread], "result": last["text"][:200]})


def view(m: dict) -> dict:
    return {k: m.get(k) for k in ("id", "at", "episode", "sender", "recipient", "kind", "about", "text", "expects",
                                  "topic", "reply_to", "route", "status", "job", "equiv_usd")}


def log_live(payload: dict, episode: str | None, sender: str | None) -> tuple[bool, str]:
    """Called by the guard hook for Claude Code's own SendMessage: count it, refuse beyond the limits, log it."""
    if not episode or not sender:
        return True, ""
    s = settings()
    if not s["enabled"]:
        return True, ""  # not Crewcut's business: Claude Code's own messaging stays as it is
    inp = payload.get("tool_input") or {}
    to = str(inp.get("to") or inp.get("recipient") or inp.get("name") or "")
    recipient = to.split("-")[0] if to else "unknown"
    text = str(inp.get("message") or inp.get("content") or inp.get("text") or "")
    about = str(inp.get("about") or "") or (re.search(r"[\w./-]+\.(?:md|json|mp4|png|srt|txt)", text) or [""])[0]
    if not about:
        return False, ("Name the file the message is about (or use `crewcut say --to … --about …`). Crew messages "
                       "without a file are not delivered.")
    try:
        _ensure()
        topic = topic_of("question", about, sender, recipient)
        check_limits(episode, sender, recipient, "question", about, topic)
    except Refused as e:
        return False, str(e)
    db.insert("crew_messages", at=db.now(), episode=episode, sender=sender, recipient=recipient, kind="question",
              about=about, text=text[:2000], expects="reply", topic=topic, route="live", status="delivered")
    return True, ""


def parse_env() -> tuple[str | None, str | None, int | None]:
    job = os.environ.get("CREWCUT_JOB", "")
    return os.environ.get("CREWCUT_EPISODE") or None, os.environ.get("CREWCUT_IDENTITY") or None, \
        int(job) if job.isdigit() else None


__all__ = ["KINDS", "Refused", "send", "messages", "settings", "set_enabled", "collected_for", "log_live", "view",
           "session_name"]
