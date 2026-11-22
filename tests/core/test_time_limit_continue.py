"""A run that hits the time limit in the middle of its work continues by itself once, in the same session; the second
time a card asks the user (episode 019: the Editor stopped after the speaker cut and the episode sat waiting for
"try again")."""

import pytest

from crewcut import approvals, db, engines, episodes, paths
from crewcut.conductor import flow, queue

STARTED, ENDED = "2026-11-22T22:14:31Z", "2026-11-22T23:14:32Z"


@pytest.fixture
def episode(studio, crew):
    return episodes.create("Erst Coding, jetzt Videoschnitt")["id"]


def timed_out(ep: str, jid: int, session: str | None = "sess-460") -> None:
    db.update("jobs", jid, status="failed", started=STARTED, ended=ENDED, doing="Stopped: time limit reached",
              data={**(queue.get(jid).get("data") or {}), "engine": "claude", "session": session})
    flow.after_job(queue.get(jid), engines.RunResult(ok=False, exit_code=-9, error="time limit reached",
                                                     session=session, timed_out=True))


def editor_jobs(ep: str) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = 'editor' ORDER BY id", (ep,)))


def test_the_first_time_limit_continues_in_the_same_session(episode):
    jid = queue.add(episode, "editor", "edit", "Build the final version from plan v004.", heavy=True)
    work = paths.episode_dir(episode) / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "speaker-v014.mov").write_bytes(b"x")
    timed_out(episode, jid)
    [_, nxt] = editor_jobs(episode)
    assert nxt["status"] == "queued" and nxt["step"] == "edit" and nxt["heavy"]
    assert nxt["data"]["resume"] == {"engine": "claude", "session": "sess-460"}
    assert nxt["data"]["continues"] == jid and nxt["data"]["time_limits"] == 1
    assert "Continue where you stopped" in nxt["task"] and "work/speaker-v014.mov" in nxt["task"]
    assert "after 60 min" in nxt["task"]
    said = [m["text"] for m in flow.messages(episode)]
    assert any("continues where it stopped" in t for t in said)
    assert not any("try again" in t for t in said)


def test_without_a_session_the_task_comes_along(episode):
    jid = queue.add(episode, "editor", "edit", "Build the final version from plan v004.")
    timed_out(episode, jid, session=None)
    nxt = editor_jobs(episode)[-1]
    assert "resume" not in nxt["data"] and "Build the final version from plan v004." in nxt["task"]


def test_the_second_time_limit_asks_the_user(episode):
    jid = queue.add(episode, "editor", "edit", "Build the final version.")
    timed_out(episode, jid)
    second = editor_jobs(episode)[-1]["id"]
    timed_out(episode, second)
    assert len(editor_jobs(episode)) == 2                          # no third run on its own
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    assert card["kind"] == "other" and card["data"]["time_limit"]["continues"] == jid
    approvals.decide(card["id"], True)
    third = editor_jobs(episode)[-1]
    assert third["id"] > second and third["data"]["resume"]["session"] == "sess-460"
    assert [j for j in queue.active(episode) if j["identity"] == "editor"]


def test_no_on_the_card_leaves_it_stopped(episode):
    jid = queue.add(episode, "editor", "edit", "Build the final version.")
    timed_out(episode, jid)
    timed_out(episode, editor_jobs(episode)[-1]["id"])
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    approvals.decide(card["id"], False, reason="stop")
    assert len(editor_jobs(episode)) == 2


def test_other_failures_still_ask_for_try_again(episode):
    jid = queue.add(episode, "editor", "edit", "Build the final version.")
    db.update("jobs", jid, status="failed", started=STARTED, ended=ENDED)
    flow.after_job(queue.get(jid), engines.RunResult(ok=False, exit_code=1, error="exit 1"))
    assert len(editor_jobs(episode)) == 1
    assert any("try again" in m["text"] for m in flow.messages(episode))
