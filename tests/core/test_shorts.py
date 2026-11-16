"""Shorts as their own small episodes, the user's standing approval with its exceptions, private-first upload with read
back, the next free slot, and the results table."""

import datetime as dt
import json
import os

import pytest

from crewcut import approvals, episodes, shorts
from crewcut.youtube import upload


@pytest.fixture
def source(studio):
    return episodes.create("I ran five local models")["id"]


def test_clip_and_original_have_only_their_steps(source):
    clip = episodes.create("Five models, one laptop", kind="short", mode="clip", source_episode=source)
    s = episodes.summary(clip["id"])
    assert s["kind"] == "short" and s["mode"] == "clip" and s["source_episode"] == source
    assert [x["id"] for x in s["steps"]] == ["idea", "title", "edit", "thumbnail", "upload", "results"]
    assert [x["n"] for x in s["steps"]] == [1, 2, 3, 4, 5, 6] and clip["format"] == "portrait"
    orig = episodes.create("Claude built my site", kind="short", mode="original")
    assert len(episodes.summary(orig["id"])["steps"]) == 9
    long = episodes.summary(source)
    assert len(long["steps"]) == 10 and long["kind"] == "episode"
    episodes.set_step(clip["id"], "idea", "done")
    assert episodes.read(clip["id"])["step"] == "title"
    with pytest.raises(ValueError):
        episodes.create("x", kind="short", mode="clip")
    with pytest.raises(FileNotFoundError):
        episodes.create("x", kind="short", mode="clip", source_episode="999-nothing")


def _package(eid, studio, **extra):
    d = studio / "episodes" / eid
    (d / "export" / "video.mp4").write_bytes(b"\0" * 10)
    pkg = {"video": "export/video.mp4", "title": "Five models", "description": "A test.", "privacy": "public", **extra}
    (d / "export" / "upload.json").write_text(json.dumps(pkg))
    return d / "export" / "upload.json", pkg


def _check(eid, studio, errors):
    rev = studio / "episodes" / eid / "review"
    rev.mkdir(exist_ok=True)
    (rev / "short-check-v001.json").write_text(json.dumps({"errors": ["x"] * errors}))


def test_the_standing_approval_covers_only_checked_shorts(source, studio, crew):
    clip = episodes.create("Clip", kind="short", mode="clip", source_episode=source)["id"]
    path, pkg = _package(clip, studio)
    assert upload.approval(clip, path, pkg, "export/upload.json") is None  # nothing switched on: a card is needed
    card = approvals.propose(clip, "upload", "publish", "Publish", file="export/upload.json")
    assert card["data"]["standing_offer"] is True
    approvals.decide(card["id"], True, choice=1)   # "Publish this and all future Shorts without asking"
    assert approvals.standing("shorts")
    path, pkg = _package(clip, studio, title="Changed after the card")
    assert approvals.standing_covers(clip, pkg) == (False, "the Critic's Short check has not run on this version")
    _check(clip, studio, 2)
    assert "2 error" in approvals.standing_covers(clip, pkg)[1]
    _check(clip, studio, 0)
    assert approvals.standing_covers(clip, {**pkg, "third_party": True})[0] is False
    logged = upload.approval(clip, path, pkg, "export/upload.json")
    assert logged["status"] == "accepted" and logged["data"]["standing"] and logged["sha256"] == approvals.sha256(path)
    # never for long videos
    lpath, lpkg = _package(source, studio)
    assert approvals.standing_covers(source, lpkg)[0] is False
    assert upload.approval(source, lpath, lpkg, "export/upload.json") is None
    # a changed style pack: the first Short after it needs a card
    brand = studio / "brand"
    brand.mkdir(exist_ok=True)
    (brand / "brand.json").write_text('{"schema": 1, "name": "new look"}')
    assert "style pack changed" in approvals.standing_covers(clip, pkg)[1]
    approvals.revoke_standing("shorts")
    assert approvals.standing("shorts") is None


class FakeYT:
    def __init__(self, title):
        self.title, self.calls = title, []

    def videos(self):
        return self

    def commentThreads(self):  # noqa: N802 - the API's name
        return self

    def list(self, **kw):
        self.calls.append(("list", kw))
        return self

    def update(self, **kw):
        self.calls.append(("update", kw))
        return self

    def insert(self, **kw):
        self.calls.append(("comment", kw))
        return self

    def execute(self):
        if self.calls[-1][0] == "list":
            return {"items": [{"snippet": {"title": self.title, "description": "A test."}}]}
        return {}


def test_a_short_goes_public_only_after_reading_it_back():
    pkg = {"title": "Five models", "description": "A test.", "related_url": "https://youtu.be/long"}
    yt = FakeYT("Five models")
    out = upload.finish_short(yt, "vid", pkg, {"privacyStatus": "public"})
    assert out["read_back"] and out["privacy"] == "public"
    assert [c[0] for c in yt.calls] == ["list", "update", "comment"]
    wrong = FakeYT("Something else")
    out = upload.finish_short(wrong, "vid", pkg, {"privacyStatus": "public"})
    assert not out["read_back"] and [c[0] for c in wrong.calls] == ["list"]
    assert "stays private" in out["notes"][0]


def test_next_slot_two_a_day_and_never_the_same_message_on_one_day(source, studio):
    a = episodes.create("A", kind="short", mode="clip", source_episode=source)["id"]
    b = episodes.create("B", kind="short", mode="clip", source_episode=source)["id"]
    c = episodes.create("C", kind="short", mode="original")["id"]
    now = dt.datetime(2026, 11, 20, 8, 0, tzinfo=dt.UTC)
    first = shorts.next_slot(a, now)
    assert first == "2026-11-20T12:00:00Z"
    p = episodes.read(a)
    p["slot"] = first
    episodes.write(a, p)
    # B has the same core message (same source episode): not on the same day
    assert shorts.next_slot(b, now) == "2026-11-21T12:00:00Z"
    # C is about something else: the second slot of the day
    assert shorts.next_slot(c, now) == "2026-11-20T18:00:00Z"


def test_results_become_one_row_of_the_table(source, studio):
    clip = episodes.create("Clip", kind="short", mode="clip", source_episode=source)["id"]
    d = studio / "episodes" / clip / "export"
    (d / "upload-result.json").write_text(json.dumps({"video_id": "abc", "at": "2026-11-18T10:00:00Z"}))

    class A:
        def reports(self):
            return self

        def query(self, **kw):
            assert kw["filters"] == "video==abc"
            return self

        def execute(self):
            return {"rows": [[1234, 71.5, 27, 9]]}

    row = shorts.results(clip, analytics=A())
    assert row["views"] == 1234 and row["mode"] == "clip"
    assert shorts.table()[0]["video_id"] == "abc"


def test_a_crew_member_cannot_switch_the_standing_approval_on(studio, crew, monkeypatch, capsys):
    from crewcut import cli
    monkeypatch.setenv("CREWCUT_IDENTITY", "publisher")
    assert cli.main(["shorts", "standing", "on"]) == 0
    assert approvals.standing("shorts") is None
    assert "card #" in capsys.readouterr().out
    monkeypatch.delenv("CREWCUT_IDENTITY")
    assert os.environ.get("CREWCUT_IDENTITY") is None
    assert cli.main(["shorts", "standing", "on"]) == 0
    assert approvals.standing("shorts")
