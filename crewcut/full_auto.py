"""Episode-scoped delegation: the Critic reviews production cards, not a blanket yes."""
from __future__ import annotations

import argparse
import json
import os
import uuid

from . import approvals, db, episodes, paths

MODES = {"off", "ready", "private", "publish"}
KINDS = {"title", "mix", "motion-plan", "style-frame", "preview", "final", "thumbnail", "publish"}


def policy(episode: str) -> dict:
    return json.loads(db.kv_get(f"full_auto:{episode}") or '{"mode":"off"}')


def active(episode: str) -> bool:
    p = policy(episode)
    return p.get("mode") != "off" and not p.get("blocked") and not p.get("complete")


def save(episode: str, value: dict) -> None:
    db.kv_set(f"full_auto:{episode}", json.dumps(value))


def configure(episode: str, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError("Choose off, ready, private or publish.")
    project = episodes.read(episode)
    p = {"mode": mode, "revision": uuid.uuid4().hex, "changed": db.now()}
    save(episode, p)
    if mode != "off":
        for step in ("edit", "title", "thumbnail", "upload"):
            if project["steps"].get(step, {}).get("status") == "skipped":
                project["steps"][step]["status"] = "open"
        episodes.write(episode, project)
    from .conductor import flow
    flow.post(episode, f"Full auto: {mode}. Production decisions go to the Critic. New paid work still needs your budget.")
    return p


def block(episode: str, reason: str) -> None:
    p = policy(episode)
    p["blocked"] = reason
    save(episode, p)
    from .conductor import flow
    flow.post(episode, f"Full auto needs attention: {reason}")


def instructions(episode: str) -> str:
    if not active(episode):
        return ""
    mode = policy(episode)["mode"]
    return (f"\nFULL AUTO is on for this episode, ending at {mode}. Finish the complete production step. "
            "Use the usual production cards; the Critic reviews them automatically. Do not ask the user to choose "
            "routine edit, graphics or thumbnail decisions. Recommend the strongest variant. After proposing a card, "
            "finish this job; the conductor continues the next job. Run quality checks, repair defects, and report "
            "real missing recordings or authentication errors honestly. Use cheap local probes to judge the design. "
            "Use rented compute for final quality and speed inside the approved budget, with no silent quality "
            "downgrade when budget or compute is unavailable. Use the connected Codex image tool; never silently "
            "switch to a paid API. Existing spending limits remain. Check the title against the finished video; "
            "use a title card for a new title. Make three distinct "
            "thumbnail variants and choose the strongest; prepare their files for YouTube Studio A/B testing. "
            "Do not claim a live A/B test is running without confirmation from YouTube Studio. "
            + ("The upload package must be private and must have no publish_at. " if mode == "private" else "")
            + ("Prepare the upload package, then stop before uploading. " if mode == "ready" else ""))


def publish_allowed(card: dict, allow_prepare: bool = False) -> None:
    from .youtube.upload import load_package, validate
    episode = card["episode"]
    mode = policy(episode)["mode"]
    if mode == "ready" and not allow_prepare:
        raise ValueError("Full auto stops before upload.")
    _, pkg = load_package(episode, card["file"])
    errors = validate(episode, pkg)
    if errors:
        raise ValueError("; ".join(errors))
    if mode == "private" and (pkg.get("privacy", "private") != "private" or pkg.get("publish_at")):
        raise ValueError("This episode permits only a private upload without a publication date.")
    video = paths.inside(paths.episode_dir(episode), pkg["video"])
    digest = approvals.sha256(video)
    finals = [c for c in approvals.list_cards(episode, "accepted") if c["kind"] == "final"]
    if not any(c.get("sha256") == digest for c in finals):
        raise ValueError("Upload video must match a reviewed final cut.")


def review(card_id: int, report: str, choice: int | None = None) -> dict:
    from .conductor import queue
    card = approvals.get(card_id)
    if not card or card["kind"] not in KINDS or card["status"] != "open":
        raise ValueError("Not an open production card.")
    episode = card["episode"]
    p = policy(episode)
    job = queue.get(int(os.environ.get("CREWCUT_JOB") or 0)) or {}
    context = job.get("data") or {}
    if (not active(episode) or os.environ.get("CREWCUT_IDENTITY") != "critic" or job.get("identity") != "critic"
            or job.get("episode") != episode or context.get("auto_card") != card_id
            or context.get("auto_revision") != p["revision"]):
        raise PermissionError("Only the assigned Critic may review under the current Full-auto setting.")
    evidence = paths.inside(paths.episode_dir(episode), report)
    result = json.loads(evidence.read_text())
    if result.get("card_sha256") != card.get("sha256") or not card.get("sha256"):
        raise ValueError("Review must name the exact card checksum.")
    if result.get("verdict") not in {"pass", "revise"} or not result.get("checks") or not result.get("reason"):
        raise ValueError("Review needs verdict, checks and reason.")
    accepted = result["verdict"] == "pass"
    if accepted and (not isinstance(result["checks"], list) or not all(
            isinstance(check, dict) and check.get("name") and check.get("passed") is True for check in result["checks"])):
        raise ValueError("Every check in a passing review must have a name and passed: true.")
    if accepted and card.get("options") and choice is None:
        raise ValueError("Choose the strongest option explicitly.")
    if accepted:
        artifact = paths.inside(paths.episode_dir(episode), card["file"])
        if not artifact.is_file() or approvals.sha256(artifact) != card["sha256"]:
            raise ValueError("The reviewed file has changed; propose a new card.")
    if accepted and card["kind"] in ("final", "publish"):
        with db.conn() as connection:
            running = db.rows(connection.execute("SELECT * FROM jobs WHERE episode=? AND status IN ('running','queued')", (episode,)))
        if any((j.get("data") or {}).get("motion_insert") for j in running):
            raise ValueError("Wait for the parallel insert work and reviews before accepting the final video.")
    if accepted and card["kind"] == "publish":
        publish_allowed(card, allow_prepare=p["mode"] == "ready")
    if not accepted:
        count = sum(1 for c in approvals.list_cards(episode) if c["kind"] == card["kind"] and
                    c["status"] == "declined" and (c.get("data") or {}).get("auto_revision") == p["revision"])
        if count >= 2:
            block(episode, "Three reviews found unresolved problems. See the Critic's report.")
            return {"status": "blocked", "report": report}
    data = {**(card.get("data") or {}), "auto_revision": p["revision"], "auto_mode": p["mode"],
            "auto_report": report, "auto_report_sha256": approvals.sha256(evidence)}
    db.update("cards", card_id, data=data)
    if accepted and card["kind"] == "publish" and p["mode"] == "ready":
        # This is preparation, not an automatic publish approval. A later user click
        # must remain an ordinary manual decision, independent of this finished run.
        data.pop("auto_revision", None)
        data.pop("auto_mode", None)
        data["prepared_revision"] = p["revision"]
        db.update("cards", card_id, data=data)
        p["complete"] = True
        save(episode, p)
        from .conductor import flow
        flow.post(episode, "Full auto finished. The Critic checked the final cut, thumbnails and upload package. Upload awaits your decision.")
        return {"status": "ready", "card": card_id, "report": report}
    return approvals.decide(card_id, accepted, choice=choice, reason=f"Full auto / Critic: {result['reason']}")


def tick() -> None:
    """Runs in the existing worker. No separate service or concurrent episode owner."""
    from .conductor import flow, queue
    with db.conn() as connection:
        rows = list(connection.execute("SELECT k FROM kv WHERE k LIKE 'full_auto:%'"))
    for row in rows:
        episode = row["k"].removeprefix("full_auto:")
        if not active(episode):
            continue
        p = policy(episode)
        cards = [c for c in approvals.list_cards(episode, "open")
                 if c.get("step") in ("record", "edit", "title", "thumbnail", "upload") or c["kind"] == "spend"]
        for card in cards:
            if card["kind"] == "spend":
                # A budget decision must stay visible, never become a silent low-quality local fallback.
                continue
            if card["kind"] not in KINDS or card.get("step") not in ("record", "edit", "title", "thumbnail", "upload"):
                continue
            key = f"auto_review:{p['revision']}:{card['id']}"
            previous = db.kv_get(key)
            if previous:
                old = queue.get(int(previous)) if previous.isdigit() else None
                if not old or old["status"] in ("running", "queued", "waiting"):
                    continue
                tries = int(db.kv_get(key + ":retries") or 0)
                if tries >= 2:
                    block(episode, "The Critic could not finish a production review after three attempts.")
                    break
                db.kv_set(key + ":retries", str(tries + 1))
                with db.conn() as connection:
                    connection.execute("DELETE FROM kv WHERE k=?", (key,))
            with db.conn() as connection:
                if connection.execute("INSERT OR IGNORE INTO kv(k,v) VALUES (?,?)", (key, "queued")).rowcount != 1:
                    continue
            jid = queue.add(episode, "critic", card.get("step"),
                f"Full-auto review of card #{card['id']}. Read the card and inspect its exact file. "
                "Run the relevant edit/thumbnail/package checks and inspect the actual media. "
                "Do not accept merely because a file exists. Write review/auto-card-" + str(card["id"]) + ".json "
                "with card_sha256, verdict (pass or revise), checks (a nonempty list of {name, passed} objects), and reason. "
                f"Then run `crewcut full-auto review {card['id']} --report review/auto-card-{card['id']}.json` "
                "with --choice N if the card offers options. Never use ordinary card accept. "
                "A revise result goes back to the author automatically. Stop after submitting this review.",
                data={"auto_card": card["id"], "auto_revision": p["revision"]})
            db.kv_set(key, str(jid))
        if not active(episode):
            continue
        with db.conn() as connection:
            busy = connection.execute("SELECT id FROM jobs WHERE episode=? AND (status IN ('running','queued') OR "
                                      "(status='waiting' AND ended IS NULL)) LIMIT 1", (episode,)).fetchone()
        if busy or cards:
            continue
        project = episodes.read(episode)
        if project["steps"].get("upload", {}).get("status") == "done":
            p["complete"] = True
            save(episode, p)
            continue
        # Recording must already exist; enabling the mode never starts a recording.
        if not any((paths.episode_dir(episode) / "originals").glob("*")):
            continue
        step = next((s for s in ("edit", "title", "thumbnail", "upload") if project["steps"].get(s, {}).get("status") != "done"), None)
        if step:
            n = int(p.get(f"starts_{step}", 0))
            if n >= 3:
                block(episode, f"{step} stopped repeatedly without a review card. Check the job log.")
                continue
            p[f"starts_{step}"] = n + 1
            save(episode, p)
            flow.start_step(episode, step)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crewcut full-auto")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("episode")
    check = sub.add_parser("review")
    check.add_argument("card", type=int)
    check.add_argument("--report", required=True)
    check.add_argument("--choice", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = policy(args.episode) if args.command == "status" else review(args.card, args.report, args.choice)
        print(json.dumps(result))
        return 0
    except (ValueError, PermissionError, OSError) as error:
        print(str(error))
        return 1
