from crewcut import db, engines, episodes, paths
from crewcut.conductor import queue
from crewcut.engines.base import RunResult
from crewcut.motion import dispatch


def test_each_insert_gets_an_independent_session_and_repeated_dispatch_is_deduplicated(crew):
    eid = episodes.create("Parallel inserts")["id"]
    cards = [{"id": i, "episode": eid, "data": {"insert": name}} for i, name in enumerate(("path", "barrier"), 1)]
    a, b = [dispatch.dispatch(card) for card in cards]
    assert dispatch.dispatch(cards[0]) == a
    assert a != b
    for jid, name in ((a, "path"), (b, "barrier")):
        job = queue.get(jid)
        data = {**job["data"], "resume": {"engine": "codex", "session": "must-not-be-shared"}}
        task = queue.build_task(job, engines.get("codex"), data)
        assert task.resume is None
        assert task.cwd == paths.episode_dir(eid) / "motion" / name
        assert task.name == f"designer · {name}"
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2


def test_builder_hands_its_insert_to_critic(crew):
    eid = episodes.create("Parallel review")["id"]
    cid = db.insert("cards", episode=eid, step="edit", kind="style-frame", title="Frame", status="accepted", created=db.now(), data={"insert": "one"})
    jid = dispatch.dispatch({"id": cid, "episode": eid, "data": {"insert": "one"}})
    db.update("jobs", jid, status="done", ended=db.now())
    assert dispatch.after_job(queue.get(jid), RunResult(True, 0))
    with db.conn() as con:
        reviewer = db.row(con.execute("SELECT * FROM jobs WHERE identity='critic'").fetchone())
    assert reviewer["data"]["motion_insert"] == "one"
    assert reviewer["data"]["motion_phase"] == "review"


def test_assembly_waits_for_other_work_then_runs_once(crew):
    eid = episodes.create("Assembly waits")["id"]
    cid = db.insert("cards", episode=eid, step="edit", kind="style-frame", title="Frame", status="accepted", created=db.now(), data={"insert": "one"})
    review = queue.add(eid, "critic", "edit", "Review insert", data={"motion_insert": "one", "motion_card": cid, "motion_phase": "review"})
    other = queue.add(eid, "designer", "edit", "Another task")
    db.update("jobs", review, status="done", ended=db.now())
    dispatch.after_job(queue.get(review), RunResult(True, 0))
    dispatch.tick()
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='editor'").fetchone()[0] == 0
    db.update("jobs", other, status="done", ended=db.now())
    dispatch.tick()
    dispatch.tick()
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='editor'").fetchone()[0] == 1
