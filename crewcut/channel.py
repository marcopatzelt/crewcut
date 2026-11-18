"""Durable channel conversation and bounded context, separate from episode work."""

from __future__ import annotations

import json

from . import db, engines, episodes, events, ledger

TRANSPORT = "_channel"


def is_channel(job: dict) -> bool:
    return (job.get("data") or {}).get("conversation_scope") == "channel" and not job.get("episode")


def context(limit: int = 50) -> dict:
    index = []
    identifiers = episodes.list_ids()
    for episode in identifiers[:limit]:
        try:
            project = episodes.read(episode)
        except (FileNotFoundError, ValueError):
            continue
        history = project.get("history") or {}
        distribution = project.get("distribution") or {
            "status": history.get("distribution", "unknown"),
            **{key: history.get(key) for key in ("scheduled_at", "published_at", "url", "video_id")}}
        index.append({"id": episode, "title": str(project.get("title", episode))[:160],
                      "step": project.get("step"), "lifecycle": project.get("lifecycle", "active"),
                      "distribution": {key: distribution.get(key) for key in
                                       ("status", "scheduled_at", "published_at", "url", "video_id")}
                      if isinstance(distribution, dict) else {"status": "unknown"}})
    with db.conn() as connection:
        jobs = db.rows(connection.execute(
            "SELECT id, episode, identity, step, status, parent, substr(doing,1,160) AS doing FROM jobs "
            "WHERE status IN ('queued','running','waiting') ORDER BY id DESC LIMIT ?", (limit,)))
        cards = db.rows(connection.execute(
            "SELECT id, episode, step, kind, substr(title,1,160) AS title FROM cards "
            "WHERE status = 'open' ORDER BY id DESC LIMIT ?", (limit,)))
    return {"scope": "channel", "episodes": index, "episode_count": len(identifiers),
            "limit": limit, "jobs": jobs, "approvals": cards, "costs": ledger.totals()}


def user_message(text: str) -> dict:
    from .conductor import flow, prompts, queue
    text = text.strip()
    if not text:
        raise ValueError("Empty message.")
    with db.conn() as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT m.id FROM messages m JOIN jobs j ON m.job = j.id "
            "WHERE m.scope = 'channel' AND m.author = 'user' AND m.text = ? "
            "AND j.status IN ('queued','running','waiting') ORDER BY m.id DESC LIMIT 1", (text,)).fetchone()
        if previous:
            return flow.message(previous["id"])
        job = connection.execute(
            "INSERT INTO jobs (episode,identity,task,created,doing,data) VALUES (NULL,?,?,?,?,?)",
            ("showrunner", prompts.channel_task(text), db.now(), "Queued",
             json.dumps({"conversation_scope": "channel"}))).lastrowid
        mid = connection.execute(
            "INSERT INTO messages (at,episode,scope,author,text,job) VALUES (?, '', 'channel', 'user', ?, ?)",
            (db.now(), text, job)).lastrowid
        connection.commit()
    message = flow.message(mid)
    events.emit("message", episode=TRANSPORT, text=text, data=message)
    events.emit("activity", data=queue.job_view(queue.get(job)))
    return message


def resume(identity: str, engine: str) -> str | None:
    with db.conn() as connection:
        jobs = db.rows(connection.execute(
            "SELECT * FROM jobs WHERE episode IS NULL AND identity = ? "
            "AND status IN ('done','failed') ORDER BY id DESC", (identity,)))
    for job in jobs:
        data = job.get("data") or {}
        if is_channel(job) and data.get("engine") == engine and data.get("session"):
            return data["session"]
    return None


def recent(limit: int = 12) -> list[dict]:
    from .conductor import flow
    with db.conn() as connection:
        rows = connection.execute("SELECT id FROM messages WHERE scope = 'channel' ORDER BY id DESC LIMIT ?",
                                  (max(1, min(limit, 500)),)).fetchall()
    return [flow.message(row["id"]) for row in reversed(rows)]


def after_job(job: dict, result) -> None:
    from .conductor import flow
    with db.conn() as connection:
        said = connection.execute("SELECT id FROM messages WHERE scope = 'channel' AND job = ? AND author != 'user'",
                                  (job["id"],)).fetchone()
    if not result.ok:
        flow.post(TRANSPORT, f"Showrunner stopped: {engines.scrub(result.error)[:200]}", job=job["id"])
    elif not said:
        flow.post(TRANSPORT, engines.scrub(result.text).strip()[:2000] or "The channel check is complete.", job=job["id"])


def child_result(job: dict, result) -> None:
    from .conductor import flow
    with db.conn() as connection:
        if connection.execute("SELECT id FROM messages WHERE scope = 'channel' AND job = ?",
                              (job["id"],)).fetchone():
            return
    status = "waiting for approval" if job.get("status") == "waiting" else "finished" if result.ok else "stopped"
    text = engines.scrub(result.text if result.ok else result.error).strip()[:800]
    flow.post(TRANSPORT, f"{job['identity']} {status} for episode {job['episode']} (job #{job['id']}). {text}",
              job=job["id"], facts=[{"label": "episode", "value": job["episode"]}])
