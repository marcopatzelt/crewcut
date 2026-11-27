"""One fresh designer session per approved insert; final assembly stays with the Editor."""
from __future__ import annotations

import hashlib

from .. import approvals, db, paths
from .custom import piece_dir


def dispatch(card: dict) -> int:
    """After the yes on a style frame: a custom piece gets its own designer session; a shelf template, a 2D or a 3D
    scene of the edit plan (``"shelf": true`` on the card) needs no new build, so the Editor renders it with the rest
    once no other style frame is open (the fan-in in ``tick``). Returns the designer job, or 0."""
    from ..conductor import queue
    episode = card["episode"]
    data = card.get("data") or {}
    insert = data.get("insert")
    if not isinstance(insert, str):
        raise ValueError("Style-frame card needs an insert ID.")
    if data.get("shelf"):
        from ..conductor import flow
        names = ", ".join([insert, *(data.get("covers") or [])])
        flow.post(episode, f"Style frame of {names} approved (card #{card['id']}): the Editor renders it with the "
                  "other approved inserts.")
        db.kv_set(f"motion_assembly_pending:{episode}", "1")
        return 0
    folder = piece_dir(episode, insert)
    paths.inside(paths.episode_dir(episode), folder.relative_to(paths.episode_dir(episode)))
    folder.mkdir(parents=True, exist_ok=True)
    # A repeated callback must never launch the same frame twice.
    key = f"motion_dispatch:{card['id']}"
    with db.conn() as con:
        if con.execute("INSERT OR IGNORE INTO kv(k,v) VALUES (?,?)", (key, "pending")).rowcount != 1:
            return int(db.kv_get(key) or 0) if (db.kv_get(key) or "").isdigit() else 0
    jid = queue.add(episode, "designer", "edit",
        f"Build only the approved insert '{insert}', style-frame card #{card['id']}. "
        f"Your working folder is motion/{insert}/ in this episode. Read its brief, beats and approved frame. "
        "First run `crewcut motion libraries` and start from a ready-made block when one shows the picture (a "
        "HyperFrames template hf-*, a private imported template via `crewcut motion imports use`, a CC0 HDRI or "
        "material for Blender via `import crewcut_assets`); build from scratch only when none fits and say why in "
        "your handoff. Use the edit/motion skills for 2D or Blender for 3D as the brief requires. Do not change another insert, "
        "the shared edit plan, timing of the speaker cut or the episode's step. Save source, renders and a clear "
        "handoff in your insert folder. Use Crewcut render commands so heavy renders keep their resource limits. "
        "No new paid work without an existing spend approval. Check the approved card still matches before finalizing. "
        "Report exact output paths with `crewcut say`; the Critic checks this insert and the Editor assembles it.",
        data={"motion_insert": insert, "motion_card": card["id"], "motion_phase": "build"})
    db.kv_set(key, str(jid))
    return jid


def after_job(job: dict, result) -> bool:
    data = job.get("data") or {}
    if not data.get("motion_insert"):
        return False
    from ..conductor import flow, queue
    episode, insert = job["episode"], data["motion_insert"]
    if not result.ok:
        flow.post(episode, f"Motion designer for {insert} stopped. Other inserts continue.", job=job["id"])
        return True
    card = approvals.get(data["motion_card"])
    if not card or card["status"] != "accepted":
        flow.post(episode, f"{insert} needs a current approved style frame before it can be assembled.")
        return True
    if data.get("motion_phase") == "build":
        queue.add(episode, "critic", "edit",
            f"Review only motion/{insert}/ against approved style-frame card #{card['id']}. "
            "Inspect the render, checks and source. Save findings in that insert's review/ folder. "
            "If the style frame has a craft_review, follow skills/motion/references/craft.md: compare native frames "
            "at entrance, main action and exit against the selected benchmark, and write animation-craft.json "
            "with exact output hash, current style_frame_card and the three comparison manifests. "
            "If changes are needed, assign a focused repair to the designer with that insert ID. "
            "Do not change the shared edit plan or approve the whole video. Report exact reviewed output paths to the Editor.",
            data={"motion_insert": insert, "motion_card": card["id"], "motion_phase": "review"})
    else:
        flow.post(episode, f"Critic finished the review for {insert}. The Editor can read its report before assembly.", job=job["id"])
        db.kv_set(f"motion_assembly_pending:{episode}", "1")
    return True


def tick() -> None:
    """Finish the fan-in once unrelated episode jobs have also released the plan."""
    from ..conductor import queue
    with db.conn() as con:
        pending = list(con.execute("SELECT k FROM kv WHERE k LIKE 'motion_assembly_pending:%'"))
    for row in pending:
        episode = row["k"].removeprefix("motion_assembly_pending:")
        with db.conn() as con:
            busy = con.execute("SELECT id FROM jobs WHERE episode=? AND (status IN ('running','queued') "
                               "OR (status='waiting' AND ended IS NULL)) LIMIT 1", (episode,)).fetchone()
        open_frames = [c for c in approvals.list_cards(episode, "open") if c["kind"] == "style-frame"]
        if busy or open_frames:
            continue
        frames = sorted(c["id"] for c in approvals.list_cards(episode, "accepted") if c["kind"] == "style-frame")
        digest = hashlib.sha256(str(frames).encode()).hexdigest()[:16]
        key = f"motion_assembly:{episode}:{digest}"
        if not db.kv_get(key):
            jid = queue.add(episode, "editor", "edit",
                "The parallel motion reviews are ready. Read each insert's report. Repair unresolved findings, "
                "then integrate the reviewed outputs into the shared edit plan. Check that every planned insert "
                "is present. Assemble the complete video, run the Critic checks and propose the normal preview/final cards.")
            db.kv_set(key, str(jid))
        with db.conn() as con:
            con.execute("DELETE FROM kv WHERE k=?", (row["k"],))
