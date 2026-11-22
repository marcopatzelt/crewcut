"""The user's chat messages reach a crew member whose run is already going: once, only what came after its start, only
from its own episode, and the Showrunner says only what is true about it."""

import pytest

from crewcut import cli, db, engines, episodes
from crewcut.conductor import deliver, flow, queue

STARTED = "2026-11-22T19:37:14Z"


@pytest.fixture
def running(studio, crew, monkeypatch):
    """A running Editor job in one episode, started at STARTED, with the crewcut command acting as that job."""
    ep = episodes.create("Erst Coding, jetzt Videoschnitt")["id"]
    jid = queue.add(ep, "editor", "record", "Ingest and cut the recordings.")
    db.update("jobs", jid, status="running", started=STARTED, doing="Cutting")
    monkeypatch.setenv("CREWCUT_JOB", str(jid))
    monkeypatch.setenv("CREWCUT_EPISODE", ep)
    monkeypatch.setenv("CREWCUT_IDENTITY", "editor")
    return ep, jid


def user_says(ep: str, text: str, at: str = "2026-11-22T19:47:40Z", **kw) -> int:
    mid = flow.post(ep, text, author="user", **kw)
    db.update("messages", mid, at=at)
    return mid


def doing(capsys) -> str:
    assert cli.main(["doing", "Checking the speaker cut"]) == 0
    return capsys.readouterr().out


def test_a_message_reaches_the_running_job_once(running, capsys):
    ep, jid = running
    mid = user_says(ep, "s29 start at 56.20")
    out = doing(capsys)
    assert deliver.HEADER in out and "s29 start at 56.20" in out and f"#{mid}" in out
    assert deliver.HEADER not in doing(capsys)                       # delivered once per job
    assert deliver.take(jid) == []
    seen = flow.message(mid)["delivered"]
    assert [(d["identity"], d["job"]) for d in seen] == [("editor", jid)]


def test_only_messages_after_the_job_started(running, capsys):
    ep, jid = running
    user_says(ep, "old wish, already in the task", at="2026-11-22T19:30:00Z")
    user_says(ep, "measure and fix the camera tilt", at="2026-11-22T19:56:55Z")
    out = doing(capsys)
    assert "camera tilt" in out and "old wish" not in out


def test_only_messages_of_its_own_episode(running, capsys):
    ep, jid = running
    other = episodes.create("Another episode")["id"]
    user_says(other, "make the thumbnail blue")
    flow.post("_channel", "channel question", author="user")
    assert deliver.HEADER not in doing(capsys)


def test_showrunner_relays_only_reach_the_member_they_are_for(running, capsys):
    ep, jid = running
    flow.post(ep, "The Editor gets this at its next step.", author="showrunner")
    for_critic = flow.post(ep, "Critic: check s29 again.", author="showrunner", relay_for=["critic"])
    for_editor = flow.post(ep, "Use C0807 for s29.", author="showrunner", relay_for=["editor"])
    for mid in (for_critic, for_editor):
        db.update("messages", mid, at="2026-11-22T19:50:00Z")
    out = doing(capsys)
    assert "Use C0807 for s29." in out
    assert "Critic: check s29" not in out and "gets this at its next step" not in out


def test_say_and_card_propose_carry_it_too_and_chat_counts_as_read(running, capsys):
    ep, jid = running
    user_says(ep, "first correction")
    assert cli.main(["say", "Ingest done."]) == 0
    assert "first correction" in capsys.readouterr().out
    user_says(ep, "second correction", at="2026-11-22T19:58:00Z")
    assert cli.main(["chat", "--last", "5"]) == 0
    out = capsys.readouterr().out
    assert out.count("second correction") == 1 and deliver.HEADER not in out   # printed once, as history
    assert deliver.pending(jid) == []


def test_say_for_refuses_an_unknown_member(running, capsys):
    assert cli.main(["say", "--for", "nobody", "hello"]) == 2


def test_reply_lane_and_finished_jobs_get_nothing(running):
    ep, jid = running
    user_says(ep, "s29 start at 56.20")
    reply = queue.add(ep, "showrunner", None, "answer", data={"reply_to": 1})
    db.update("jobs", reply, status="running", started=STARTED)
    assert deliver.take(reply) == []
    db.update("jobs", jid, status="done")
    assert deliver.take(jid) == []


def test_the_task_says_new_instructions_can_arrive(running):
    ep, jid = running
    t = queue.build_task(queue.get(jid), engines.get("codex"), {})
    assert deliver.prompt_line() in t.prompt
    reply = queue.get(queue.add(ep, "showrunner", None, "answer", data={"reply_to": 1}))
    assert deliver.prompt_line() not in queue.build_task(reply, engines.get("codex"), {}).prompt


def newest_reply_task() -> str:
    with db.conn() as c:
        return c.execute("SELECT task FROM jobs WHERE identity = 'showrunner' ORDER BY id DESC LIMIT 1").fetchone()[0]


def test_showrunner_says_the_running_member_gets_it_at_its_next_step(running):
    ep, jid = running
    flow.user_message(ep, "s29 start at 56.20")
    task = newest_reply_task()
    assert '"The Editor gets this at its next step."' in task
    assert f"Editor (job {jid}, step record)" in task
    assert "never write that it reads along" in task


def test_showrunner_never_claims_delivery_when_nothing_runs(running):
    ep, jid = running
    db.update("jobs", jid, status="done")
    flow.user_message(ep, "s29 start at 56.20")
    task = newest_reply_task()
    assert "gets this at its next step" not in task
    assert "nobody reads this message by itself" in task and "Never write that a crew member reads along" in task
