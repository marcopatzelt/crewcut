"""New chat messages reach a crew member whose run is already going.

A run's task is fixed when it starts. When the user writes in the episode chat later ("s29 starts at 56.20"), the
running crew member would not know. So every frequent `crewcut` call of a running job (`doing`, `say`, `chat`,
`card propose`) prints the messages that arrived after the job started and that it has not had yet: the user's
messages, and the Showrunner's relays meant for this crew member (`crewcut say --for <id>`). Each message reaches a
job once; the delivery is recorded, and the chat shows "Delivered to the Editor at 20:05" under the message.

Only agent runs of an episode receive messages, never the Showrunner's short chat answers (the reply lane): those
answer one message and end.
"""

from __future__ import annotations

from .. import db, events, paths, team

TABLE = """
CREATE TABLE IF NOT EXISTS chat_deliveries (
  job INTEGER NOT NULL, message INTEGER NOT NULL, identity TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (job, message)
);
CREATE INDEX IF NOT EXISTS chat_deliveries_message ON chat_deliveries(message);
"""
HEADER = "NEW FROM THE USER (follow before you continue; it overrides your plan and earlier instructions):"
MAX_CHARS = 4000


_ready: set[str] = set()


def _ensure(c) -> None:
    key = str(paths.db_path())
    if key not in _ready:
        c.executescript(TABLE)
        _ready.add(key)


def receives(job: dict | None) -> bool:
    """Whether new chat messages are delivered to this job while it runs."""
    from . import queue
    if not job or job.get("kind") != "agent" or job.get("status") != "running" or not job.get("started"):
        return False
    episode = job.get("episode") or ""
    if not episode or episode.startswith("_") or queue.is_reply(job):
        return False
    return (job.get("data") or {}).get("conversation_scope", "episode") == "episode"


def receivers(episode: str) -> list[dict]:
    """The runs in this episode that get the user's next message at their next `crewcut` call."""
    with db.conn() as c:
        jobs = db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND status = 'running' ORDER BY id",
                                 (episode,)))
    return [j for j in jobs if receives(j)]


def _for(m: dict) -> list[str]:
    d = m.get("data") if isinstance(m.get("data"), dict) else {}
    return [str(x) for x in d.get("for") or []]


def pending(jid: int) -> list[dict]:
    """Messages for this running job that it has not had yet (oldest first)."""
    from . import queue
    job = queue.get(jid)
    if not receives(job):
        return []
    with db.conn() as c:
        _ensure(c)
        rs = db.rows(c.execute(
            "SELECT * FROM messages WHERE scope = 'episode' AND episode = ? AND at >= ? AND (job IS NULL OR job != ?) "
            "AND id NOT IN (SELECT message FROM chat_deliveries WHERE job = ?) ORDER BY id",
            (job["episode"], job["started"], jid, jid)))
    return [m for m in rs if m["author"] == "user" or job["identity"] in _for(m)]


def take(jid: int) -> list[dict]:
    """The pending messages, marked as delivered to this job. A message counts once, also with parallel calls."""
    from . import flow, queue
    msgs = pending(jid)
    if not msgs:
        return []
    job = queue.get(jid)
    out = []
    with db.conn() as c:
        for m in msgs:
            cur = c.execute("INSERT OR IGNORE INTO chat_deliveries (job, message, identity, at) VALUES (?,?,?,?)",
                            (jid, m["id"], job["identity"], db.now()))
            if cur.rowcount:
                out.append(m)
    for m in out:   # the chat shows the delivery under the message at once
        events.emit("message", episode=job["episode"], text="delivered", data=flow.message(m["id"]))
    return out


def deliveries(mid: int) -> list[dict]:
    with db.conn() as c:
        _ensure(c)
        return db.rows(c.execute("SELECT identity, job, at FROM chat_deliveries WHERE message = ? ORDER BY at, job",
                                 (mid,)))


def block(msgs: list[dict]) -> str:
    if not msgs:
        return ""
    lines = [HEADER]
    for m in msgs:
        who = "user" if m["author"] == "user" else (team.get(m["author"]) or {}).get("name", m["author"])
        text = m["text"] if len(m["text"]) <= MAX_CHARS else m["text"][:MAX_CHARS] + " … (rest: crewcut chat)"
        lines.append(f"- message #{m['id']} at {m['at']} from {who}: {text}")
    return "\n".join(lines)


def prompt_line() -> str:
    """One line for the task of a run that receives messages."""
    return ("New messages from the user can arrive while you work: Crewcut prints them under \"NEW FROM THE USER\" in "
            "the output of `crewcut doing`, `crewcut say`, `crewcut chat` and `crewcut card propose`. They override "
            "your plan and earlier instructions: follow them before you continue.")


def reply_note(episode: str) -> str:
    """What the Showrunner may truthfully say about who gets the user's message (flow.user_message)."""
    runs = receivers(episode)
    if not runs:
        return ("No crew member is running in this episode right now, so nobody reads this message by itself. Never "
                "write that a crew member reads along or will see it. If it asks for work, give the work with "
                "`crewcut job add` and put the user's words into its task.")
    names = []
    for j in runs:
        name = (team.get(j["identity"]) or {}).get("name", j["identity"])
        names.append((name, f"{name} (job {j['id']}, step {j['step'] or '-'})"))
    first = names[0][0]
    return (f"Running now in this episode: {', '.join(n for _, n in names)}. Crewcut delivers this message to "
            f"{'it' if len(names) == 1 else 'each of them'} by itself at the next `crewcut doing`, `say`, `chat` or "
            "`card propose` call, and the chat shows when it was delivered. It has not read it yet: never write that "
            f"it reads along or already knows. Say it like this: \"The {first} gets this at its next step.\" Do not "
            "add a job for work a running crew member already does. To pass on something the user did not write "
            "(a decision or a file), use `crewcut say --for <crew member id> \"…\"`; it is delivered the same way.")
