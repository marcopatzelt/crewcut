"""A file that lands in the inbox after the record step is done still reaches the Editor, until the video is out
(episode 019: a second camera file copied a minute later was never announced)."""

import pytest

from crewcut import db, episodes
from crewcut.conductor import flow, inbox, queue


@pytest.fixture
def recorded(studio, crew):
    ep = episodes.create("Erst Coding, jetzt Videoschnitt")["id"]
    for step in ("idea", "title", "script", "record"):
        episodes.set_step(ep, step, "done")
    episodes.set_step(ep, "edit", "working")
    box = studio / "inbox" / ep
    box.mkdir(parents=True)
    return ep, box


def settle(sizes: dict) -> list:
    inbox.scan(sizes)            # first sight: maybe still copying
    return inbox.scan(sizes)     # stable now


def editor_jobs(ep: str) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = 'editor' ORDER BY id", (ep,)))


def test_a_late_file_is_announced_as_an_additional_recording(recorded):
    ep, box = recorded
    (box / "C0807.MP4").write_bytes(b"second camera")
    sizes: dict = {}
    assert settle(sizes) == [(ep, [f"inbox/{ep}/C0807.MP4"])]
    [job] = editor_jobs(ep)
    assert job["step"] == "edit" and "Additional recording" in job["task"] and "C0807.MP4" in job["task"]
    assert "Leave the record step as it is" in job["task"]
    assert episodes.read(ep)["steps"]["record"]["status"] == "done"          # not reopened
    assert any("Additional recording arrived" in m["text"] for m in flow.messages(ep))
    assert inbox.scan(sizes) == []                                          # announced once


def test_a_running_editor_gets_it_at_its_next_step(recorded):
    ep, box = recorded
    jid = queue.add(ep, "editor", "edit", "Cut v013.")
    db.update("jobs", jid, status="running", started="2026-11-22T21:00:00Z")
    (box / "C0807.MP4").write_bytes(b"second camera")
    settle({})
    assert [j["id"] for j in editor_jobs(ep)] == [jid]                     # no second Editor beside it
    relay = [m for m in flow.messages(ep) if m.get("for") == ["editor"]]
    assert relay and "C0807.MP4" in relay[0]["text"]


def test_a_queued_editor_takes_it_in_its_task(recorded):
    ep, box = recorded
    jid = queue.add(ep, "editor", "edit", "Cut v013.")
    (box / "C0807.MP4").write_bytes(b"second camera")
    settle({})
    [job] = editor_jobs(ep)
    assert job["id"] == jid and job["task"].startswith("Cut v013.") and "C0807.MP4" in job["task"]


def test_no_longer_watched_once_published_or_before_recording(recorded, studio):
    ep, box = recorded
    episodes.set_step(ep, "upload", "done")
    (box / "late.mov").write_bytes(b"x")
    assert settle({}) == []
    early = episodes.create("Next idea")["id"]                               # record step not reached yet
    (studio / "inbox" / early).mkdir(parents=True)
    (studio / "inbox" / early / "C0001.MP4").write_bytes(b"x")
    assert settle({}) == [] and editor_jobs(early) == []
