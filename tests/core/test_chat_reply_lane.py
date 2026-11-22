"""A chat message gets its answer while long crew work runs in the same episode, and every agent run stays visible as
running until its process ends, also after it proposed a card."""

import pytest
from fastapi.testclient import TestClient

from crewcut import approvals, db, engines, episodes
from crewcut.conductor import flow, queue
from crewcut.server.app import create_app


class IdleThread:
    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def is_alive(self):
        return True


@pytest.fixture
def one_slot(studio, crew, monkeypatch):
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text("[engine]\nmax_parallel_agents = 1\n")
    worker = queue.Worker()
    monkeypatch.setattr(worker, "maybe_update_engine", lambda: None)
    monkeypatch.setattr(queue.threading, "Thread", IdleThread)
    return worker


def newest_job() -> dict:
    with db.conn() as c:
        return queue.get(c.execute("SELECT MAX(id) AS id FROM jobs").fetchone()["id"])


def rule_card(episode: str, job: int) -> dict:
    return approvals.propose(episode, "thumbnail", "rule", "New rule for thumbnail: synthetic", identity="designer",
                             data={"step": "thumbnail", "rule": "synthetic", "source": "test"}, job=job)


def test_chat_answer_runs_beside_a_long_crew_run(one_slot):
    episode = episodes.create("Synthetic episode")["id"]
    other = episodes.create("Other synthetic episode")["id"]
    long_run = queue.add(episode, "designer", "thumbnail", "Make a new version")
    one_slot.tick()
    assert queue.get(long_run)["status"] == "running"

    later_crew = queue.add(episode, "writer", "script", "Write")
    flow.user_message(episode, "D is not my face")
    reply = newest_job()
    assert queue.is_reply(reply) and reply["identity"] == "showrunner"
    flow.user_message(episode, "And C points at the wrong side")
    second = newest_job()
    flow.user_message(other, "Hello")
    elsewhere = newest_job()
    one_slot.tick()
    assert queue.get(reply["id"])["status"] == "running"        # beside the long run, not behind it
    assert queue.get(second["id"])["status"] == "queued"        # one answer per episode at a time, in order
    assert queue.get(elsewhere["id"])["status"] == "running"
    assert queue.get(later_crew)["status"] == "queued"          # crew work keeps the user's limit


def test_chat_answer_takes_a_crew_slot_when_the_reply_lane_is_full(one_slot, studio):
    (studio / "config" / "crewcut.toml").write_text("[engine]\nmax_parallel_agents = 1\nmax_parallel_replies = 0\n")
    episode = episodes.create("Synthetic episode")["id"]
    flow.user_message(episode, "Hello")
    reply = newest_job()
    one_slot.tick()
    assert queue.get(reply["id"])["status"] == "running"
    assert one_slot.replies == set()


def test_a_chat_answer_is_short(crew):
    episode = episodes.create("Synthetic episode")["id"]
    flow.user_message(episode, "Hello")
    reply = newest_job()
    crew_job = queue.get(queue.add(episode, "designer", "thumbnail", "Make a new version"))
    engine = engines.get("codex")
    assert queue.build_task(reply, engine, {}).timeout_s == 10 * 60
    assert queue.build_task(crew_job, engine, {}).timeout_s == 60 * 60


def test_a_card_mid_run_keeps_the_job_visible_as_running(crew):
    episode = episodes.create("Synthetic episode")["id"]
    job = queue.add(episode, "designer", "thumbnail", "Make a new version")
    db.update("jobs", job, status="running", started=db.now())
    card = rule_card(episode, job)
    assert queue.get(job)["status"] == "running"
    running = TestClient(create_app(start_worker=False), base_url="http://localhost:4747").get(
        "/api/jobs?status=running").json()
    assert [(j["job"], j["identity"], j["step"]) for j in running] == [(job, "designer", "thumbnail")]
    approvals.decide(card["id"], accepted=True)              # answered while the process still works
    assert queue.get(job)["status"] == "running"


@pytest.mark.parametrize("answered,status", [(False, "waiting"), (True, "done")])
def test_the_run_ends_waiting_only_while_its_card_is_open(crew, monkeypatch, answered, status):
    from crewcut.engines import versions
    episode = episodes.create("Synthetic episode")["id"]
    job = queue.get(queue.add(episode, "designer", "thumbnail", "Make a new version"))
    engine = engines.get("codex")
    monkeypatch.setattr(engines, "current", lambda: engine)
    monkeypatch.setattr(versions, "note_job", lambda *args: None)

    def run(task, **kwargs):
        card = rule_card(episode, job["id"])
        assert queue.get(job["id"])["status"] == "running"
        if answered:
            approvals.decide(card["id"], accepted=True)
        return engines.RunResult(ok=True, exit_code=0, text="Proposed.", session="synthetic-session")

    monkeypatch.setattr(engine, "run", run)
    queue._run_agent(job)
    assert queue.get(job["id"])["status"] == status


def test_a_restart_keeps_a_run_that_asked_the_user_waiting(crew):
    episode = episodes.create("Synthetic episode")["id"]
    asked = queue.add(episode, "designer", "thumbnail", "Make a new version")
    silent = queue.add(episode, "writer", "script", "Write")
    db.update("jobs", asked, status="running", started=db.now())
    db.update("jobs", silent, status="running", started=db.now())
    rule_card(episode, asked)
    queue.Worker().recover()
    assert queue.get(asked)["status"] == "waiting"
    assert queue.get(asked)["doing"].startswith("Waiting for your yes")
    assert queue.get(silent)["status"] == "failed"
