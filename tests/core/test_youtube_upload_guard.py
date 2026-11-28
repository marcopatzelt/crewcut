"""A video never goes up twice (crewcut/youtube/guard.py). No real API calls: a fake YouTube answers.

On 24.11.2026 two Shorts went up twice: two accepted publish cards per Short queued two Publisher jobs, the
terminal uploaded as well, and two uploads of one package ran at the same time. Three guards, three groups of tests:
the upload is idempotent (record and YouTube), one upload per episode at a time (a lock in SQLite), and a second yes
starts nothing."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from crewcut import approvals, db, episodes, paths
from crewcut.youtube import guard, upload

REPO = Path(__file__).resolve().parents[2]
TITLE = "Claude checks its own work"


class FakeYT:
    """The few calls the guard and the upload make. `channel` is the uploads playlist, newest first; an insert adds
    the new video to it with its tags. `hold` (an Event) keeps the insert in flight until it is set."""

    def __init__(self, channel=(), fail=None, hold=None, entered=None, ids=("new-1", "new-2", "new-3")):
        self.channel, self.fail, self.hold, self.entered = list(channel), fail, hold, entered
        self.ids, self.calls, self.inserted = list(ids), [], []

    def videos(self):
        return _Api(self, "videos")

    def channels(self):
        return _Api(self, "channels")

    def playlistItems(self):  # noqa: N802 - the API's name
        return _Api(self, "playlistItems")

    def names(self):
        return [c[0] for c in self.calls]


class _Api:
    def __init__(self, yt, name):
        self.yt, self.name = yt, name

    def list(self, **kw):
        self.yt.calls.append((f"{self.name}.list", kw))
        if self.yt.fail:
            return _Req(error=self.yt.fail)
        if self.name == "channels":
            return _Req({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU-test"}}}]})
        if self.name == "playlistItems":
            return _Req({"items": [{"contentDetails": {"videoId": v["id"]}} for v in self.yt.channel]})
        wanted = kw["id"].split(",")
        return _Req({"items": [v for v in self.yt.channel if v["id"] in wanted]})

    def insert(self, **kw):
        self.yt.calls.append(("videos.insert", kw))
        return _Upload(self.yt, kw)


class _Req:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def execute(self):
        if self.error:
            raise self.error
        return self.value


class _Upload:
    def __init__(self, yt, kw):
        self.yt, self.kw = yt, kw

    def next_chunk(self):
        if self.yt.entered:
            self.yt.entered.set()
        if self.yt.hold:
            assert self.yt.hold.wait(10)
        vid = self.yt.ids.pop(0)
        self.yt.inserted.append(vid)
        self.yt.channel.insert(0, video(vid, self.kw["body"]["snippet"]["title"], self.kw["body"]["snippet"]["tags"]))
        return None, {"id": vid}


def video(vid, title, tags=(), state="processed"):
    return {"id": vid, "snippet": {"title": title, "tags": list(tags), "publishedAt": "2026-11-24T15:58:00Z"},
            "status": {"uploadStatus": state, "privacyStatus": "private"}}


def media(path, **kw):
    return ("media", str(path))


@pytest.fixture
def ep(crew):
    eid = episodes.create(TITLE)["id"]
    root = paths.episode_dir(eid)
    (root / "export" / "video.mp4").write_bytes(b"the final cut")
    write_package(root)
    return eid, root


def write_package(root, **extra):
    pkg = {"video": "export/video.mp4", "title": TITLE, "description": "A test.", "tags": ["claude"], **extra}
    (root / "export" / "upload.json").write_text(json.dumps(pkg))


def approve(eid):
    card = approvals.propose(eid, "upload", "publish", "Publish", file="export/upload.json")
    return approvals.decide(card["id"], True)


def result(root):
    return json.loads((root / "export" / "upload-result.json").read_text())


def publisher_jobs(eid):
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT id, status FROM jobs WHERE episode = ? AND identity = 'publisher' "
                                           "AND step = 'upload'", (eid,))]


def version(root):
    return approvals.sha256(root / "export" / "video.mp4")


# ---- 1. idempotent: the episode's record and YouTube itself ------------------------------------------------------------
def test_an_upload_carries_the_marker_and_is_recorded(ep):
    eid, root = ep
    approve(eid)
    yt = FakeYT()
    res = upload.upload(eid, youtube=yt, media=media)
    assert res["status"] == "uploaded" and res["video_id"] == "new-1" and yt.inserted == ["new-1"]
    tags = yt.calls[[n for n, _ in yt.calls].index("videos.insert")][1]["body"]["snippet"]["tags"]
    assert tags == ["claude", guard.marker(eid, version(root))] and len(tags[1]) == guard.MARKER_LEN
    assert result(root)["video_id"] == "new-1" and result(root)["version"] == version(root)
    assert [(r["video_id"], r["source"], r["version"]) for r in guard.recorded(eid)] == [
        ("new-1", "upload", version(root))]
    with db.conn() as c:   # the lock is gone after the upload
        assert c.execute("SELECT COUNT(*) FROM upload_locks").fetchone()[0] == 0


def test_the_upload_records_the_comment_word_and_its_link_as_approved(ep):
    """The comment -> link replies (crewcut/youtube/replies.py) take the word and the link from the upload result: the
    package the publish card approved."""
    eid, root = ep
    write_package(root, description="A test. Kommentier GPU für die Anleitung.", cta_keyword="GPU",
                  cta_url="striq.de/gpu", related_comment="Kommentier GPU für die Anleitung.")
    approve(eid)
    upload.upload(eid, youtube=FakeYT(), media=media)
    assert (result(root)["cta_keyword"], result(root)["cta_url"]) == ("GPU", "striq.de/gpu")
    errs = upload.validate(eid, {"video": "export/video.mp4", "title": TITLE, "description": "A test.",
                                 "cta_keyword": "gpu", "cta_url": "striq.de/gpu"})
    assert any("capitals" in e for e in errs)


def test_a_second_upload_of_a_recorded_video_reports_it_and_uploads_nothing(ep):
    eid, root = ep
    approve(eid)
    yt = FakeYT()
    upload.upload(eid, youtube=yt, media=media)
    again = upload.upload(eid, youtube=yt, media=media)
    assert again["status"] == "exists" and again["video_id"] == "new-1" and "Nothing was uploaded" in again["message"]
    assert yt.inserted == ["new-1"]


def test_the_result_file_alone_counts_as_the_record(ep):
    """The Shorts of 24.11. have only export/upload-result.json; it stops a new upload without any card."""
    eid, root = ep
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "recorded-id", "at": "x"}))
    yt = FakeYT(channel=[video("recorded-id", TITLE)])
    res = upload.upload(eid, youtube=yt, media=media)
    assert res["status"] == "exists" and res["video_id"] == "recorded-id"
    assert "videos.insert" not in yt.names() and "channels.list" not in yt.names()


def test_a_recorded_video_that_was_deleted_on_youtube_does_not_block(ep):
    eid, root = ep
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "deleted-one", "at": "x"}))
    approve(eid)
    yt = FakeYT(channel=[video("old", "Another video")])
    res = upload.upload(eid, youtube=yt, media=media)
    assert res["status"] == "uploaded" and yt.inserted == ["new-1"]
    with db.conn() as c:
        assert c.execute("SELECT status FROM uploads WHERE video_id = 'deleted-one'").fetchone()[0] == "gone"
    assert [r["video_id"] for r in guard.recorded(eid)] == ["new-1"]


def test_the_marker_on_youtube_finds_the_video_when_the_record_is_lost(ep):
    """Two uploads ran at once on 24.11. and the later one overwrote upload-result.json: the first video was lost to
    Crewcut. The marker tag finds it on the channel."""
    eid, root = ep
    approve(eid)
    yt = FakeYT(channel=[video("other", "Something else"),
                         video("lost-one", "Old title", ["claude", guard.marker(eid, version(root))])])
    res = upload.upload(eid, youtube=yt, media=media)
    assert res["status"] == "exists" and res["video_id"] == "lost-one" and "exact video file" in res["why"]
    assert yt.inserted == [] and result(root)["video_id"] == "lost-one" and result(root)["at"]
    assert [(r["video_id"], r["source"]) for r in guard.recorded(eid)] == [("lost-one", "youtube")]


def test_another_version_and_a_legacy_title_count_unless_the_person_wants_a_second_video(ep, monkeypatch):
    eid, root = ep
    approve(eid)
    other_version = guard.marker(eid, "f" * 64)
    yt = FakeYT(channel=[video("v1", "Old title", [other_version])])
    assert upload.upload(eid, youtube=yt, media=media)["why"].endswith("(another version of the video file)")
    with db.conn() as c:
        c.execute("DELETE FROM uploads")
    yt = FakeYT(channel=[video("legacy", TITLE, ["claude"])])   # from before the marker: same title
    assert "exactly this title" in upload.upload(eid, youtube=yt, media=media)["why"] and yt.inserted == []
    with db.conn() as c:
        c.execute("DELETE FROM uploads")
    monkeypatch.setenv("CREWCUT_IDENTITY", "publisher")
    with pytest.raises(PermissionError, match="person at the terminal"):
        upload.upload(eid, youtube=FakeYT(), media=media, new_video=True)
    monkeypatch.delenv("CREWCUT_IDENTITY")
    yt = FakeYT(channel=[video("legacy", TITLE, ["claude"]), video("v1", "Old title", [other_version])])
    assert upload.upload(eid, youtube=yt, media=media, new_video=True)["status"] == "uploaded"
    # the same file never goes up twice, not even with --new-video
    assert upload.upload(eid, youtube=yt, media=media, new_video=True)["status"] == "exists"
    assert yt.inserted == ["new-1"]


def test_when_youtube_cannot_be_asked_nothing_goes_up(ep):
    eid, root = ep
    approve(eid)
    yt = FakeYT(fail=ConnectionError("network down"))
    with pytest.raises(guard.CheckFailed, match="Nothing was uploaded"):
        upload.upload(eid, youtube=yt, media=media)
    assert "videos.insert" not in yt.names()
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "known"}))
    with pytest.raises(guard.CheckFailed):   # a recorded video that cannot be checked is not taken as gone
        upload.upload(eid, youtube=yt, media=media)
    assert guard.recorded(eid)[0]["video_id"] == "known"


def test_no_card_still_means_no_upload(ep):
    eid, root = ep
    with pytest.raises(PermissionError, match="no accepted publish card"):
        upload.upload(eid, youtube=FakeYT(), media=media)


def test_verify_ignores_the_marker_and_the_package_reserves_room_for_it(ep):
    from crewcut.youtube import verify
    eid, root = ep
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "vid"}))
    body = upload.body_of(json.loads((root / "export" / "upload.json").read_text()), marker="crewcut-1234abcd-5678ef90")
    item = {"id": "vid", "snippet": {**body["snippet"]}, "status": {**body["status"]}}
    report = verify.verify(eid, youtube=FakeYT(channel=[item]))
    assert report["matches"], [c for c in report["checks"] if not c["matches"]]
    assert not upload.validate(eid, {"video": "export/video.mp4", "title": "t", "description": "d",
                                     "tags": ["x" * (500 - guard.MARKER_LEN - 1)]})
    assert "marker tag" in " ".join(upload.validate(eid, {"video": "export/video.mp4", "title": "t",
                                                          "description": "d", "tags": ["x" * 480]}))


# ---- 2. one upload per episode at a time --------------------------------------------------------------------------------
def test_the_lock_lets_one_upload_in_and_frees_itself(ep):
    eid, _ = ep
    lock = guard.claim(eid, job=7)
    with pytest.raises(guard.Busy, match="job #7"):
        guard.claim(eid)
    assert guard.holder(eid)["token"] == lock["token"]
    guard.release(lock)
    assert guard.holder(eid) is None
    guard.release(guard.claim(eid))


def test_a_lock_without_a_sign_of_life_is_taken_over(ep):
    eid, _ = ep
    lock = guard.claim(eid, now=1000.0)   # this process: alive, but quiet
    with pytest.raises(guard.Busy):
        guard.claim(eid, now=1000.0 + guard.STALE_MINUTES * 60 - 1)
    guard.beat(lock, now=5000.0)
    with pytest.raises(guard.Busy):
        guard.claim(eid, now=5000.0 + guard.STALE_MINUTES * 60 - 1)
    new = guard.claim(eid, now=5000.0 + guard.STALE_MINUTES * 60 + 1)
    assert new["took_over"]["token"] == lock["token"]


def test_the_lock_is_in_the_database_and_outlives_its_process(ep):
    """A lock taken by another process stays after that process ends (a crash, a restart). Its holder is gone, so
    after a short grace for YouTube's listing it is free."""
    eid, _ = ep
    code = f"from crewcut.youtube import guard; guard.claim({eid!r}, job=42); print('claimed')"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "claimed", out.stderr
    db._ready.clear()   # as after a restart: a fresh start of the schema code, the same file
    with pytest.raises(guard.Busy, match="job #42"):
        guard.claim(eid)
    assert guard.holder(eid)["job"] == 42
    later = time.time() + guard.DEAD_GRACE_S + 1
    assert guard.holder(eid, now=later) is None
    assert guard.claim(eid, now=later)["took_over"]["job"] == 42


def test_upload_refuses_while_another_upload_of_the_episode_runs(ep):
    eid, _ = ep
    approve(eid)
    guard.claim(eid, job=551)
    yt = FakeYT()
    with pytest.raises(guard.Busy, match="does not start a second one"):
        upload.upload(eid, youtube=yt, media=media)
    assert yt.calls == []


def test_two_uploads_at_the_same_time_make_one_video(ep):
    """24.11.: the Publisher's job and the terminal uploaded the same Short at once. Now the second one stops at the
    lock while the first is in flight, and afterwards finds the first one's video."""
    eid, root = ep
    approve(eid)
    hold, entered = threading.Event(), threading.Event()
    yt = FakeYT(hold=hold, entered=entered)
    first: dict = {}
    t = threading.Thread(target=lambda: first.update(upload.upload(eid, youtube=yt, media=media)))
    t.start()
    assert entered.wait(10)
    with pytest.raises(guard.Busy):
        upload.upload(eid, youtube=yt, media=media)
    hold.set()
    t.join(10)
    assert first["status"] == "uploaded"
    assert upload.upload(eid, youtube=yt, media=media)["status"] == "exists"
    assert yt.inserted == ["new-1"]


# ---- 3. a second yes starts nothing ------------------------------------------------------------------------------------
def test_the_first_yes_queues_the_upload(ep):
    eid, _ = ep
    approve(eid)
    assert len(publisher_jobs(eid)) == 1


def test_a_second_yes_while_the_upload_job_waits_in_the_queue_starts_nothing(ep):
    """The 24.11. case: the package changed seconds after the first card, a second card, both accepted."""
    eid, root = ep
    approve(eid)
    write_package(root, description="A test, one word more.")
    card = approve(eid)
    jobs = publisher_jobs(eid)
    assert len(jobs) == 1
    with db.conn() as c:
        said = c.execute("SELECT text FROM messages WHERE card = ? AND author = 'publisher'", (card["id"],)).fetchone()
    assert f"Job #{jobs[0]['id']} already takes care of the upload" in said[0]


def test_a_second_yes_after_the_upload_or_while_it_runs_starts_nothing(ep):
    eid, root = ep
    approve(eid)
    db.update("jobs", publisher_jobs(eid)[0]["id"], status="done")
    lock = guard.claim(eid)
    approve(eid)
    guard.release(lock)
    upload.upload(eid, youtube=FakeYT(), media=media)
    approve(eid)
    assert len(publisher_jobs(eid)) == 1
    with db.conn() as c:
        said = [r[0] for r in c.execute("SELECT text FROM messages WHERE author = 'publisher' ORDER BY id")]
    assert "An upload of this episode is running" in said[0] and "starts no second one" in said[0]
    assert "on YouTube already: https://youtu.be/new-1" in said[1] and "starts no second upload" in said[1]


def test_the_yes_on_a_card_from_the_running_job_itself_still_queues_the_upload(ep, monkeypatch):
    """The Publisher job that built the package and asked stays running for its last words; its own card is no
    reason to wait."""
    eid, _ = ep
    from crewcut.conductor import queue
    jid = queue.add(eid, "publisher", "upload", "build the package")
    db.update("jobs", jid, status="running")
    monkeypatch.setenv("CREWCUT_JOB", str(jid))
    card = approvals.propose(eid, "upload", "publish", "Publish", file="export/upload.json")
    monkeypatch.delenv("CREWCUT_JOB")
    approvals.decide(card["id"], True)
    assert len(publisher_jobs(eid)) == 2
