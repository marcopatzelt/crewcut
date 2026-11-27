"""The Short's link comment: it waits until YouTube has processed the video, is never posted twice, keeps the full
API error, and the worker posts it later when the upload could not wait long enough.

On 24.11.2026 four Shorts got "comment not added: HttpError": the comment went out a second after the upload, while
YouTube was still processing the video. The same call worked minutes later, once the video was processed."""

import json
from types import SimpleNamespace

import pytest

from crewcut import approvals, db, episodes, paths
from crewcut.conductor import flow
from crewcut.youtube import upload

LONG = "https://youtu.be/long-video"
CHANNEL = "UC-channel"


class HttpError(Exception):
    """Shaped like googleapiclient's HttpError: resp.status and the JSON body in content."""

    def __init__(self, status, reason, message):
        super().__init__(message)
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps({"error": {"code": status, "message": message,
                                             "errors": [{"reason": reason, "message": message}]}}).encode()


class FakeYT:
    """videos().list answers the given processing states in turn; commentThreads list/insert as configured."""

    def __init__(self, states=("processed",), threads=(), insert_error=None):
        self.states, self.threads, self.insert_error = list(states), list(threads), insert_error
        self.calls, self._next = [], None

    def videos(self):
        self._api = "videos"
        return self

    def commentThreads(self):  # noqa: N802 - the API's name
        self._api = "comments"
        return self

    def list(self, **kw):
        self.calls.append((f"{self._api}.list", kw))
        if self._api == "videos":
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            self._next = {"items": [{"status": {"uploadStatus": state}, "snippet": {"channelId": CHANNEL}}]}
        else:
            self._next = {"items": self.threads}
        return self

    def insert(self, **kw):
        self.calls.append(("comments.insert", kw))
        self._next = self.insert_error or {"id": "new-comment"}
        return self

    def execute(self):
        if isinstance(self._next, Exception):
            raise self._next
        return self._next

    def names(self):
        return [c[0] for c in self.calls]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


PKG = {"title": "Five models", "description": "A test.", "related_url": LONG,
       "related_comment": f"Das ganze Video: {LONG}"}


def test_the_comment_waits_until_youtube_has_processed_the_short():
    yt, clock = FakeYT(states=["uploaded", "uploaded", "processed"]), Clock()
    res = upload.post_comment(yt, "vid", PKG, wait_s=30, sleep=clock.sleep, clock=clock)
    assert res["status"] == "added" and res["id"] == "new-comment"
    # never a comment while the video still processes: two waits, then the own-comment check, then one insert
    assert yt.names() == ["videos.list"] * 3 + ["comments.list", "comments.insert"]
    body = yt.calls[-1][1]["body"]["snippet"]
    assert body["videoId"] == "vid" and body["topLevelComment"]["snippet"]["textOriginal"] == f"Das ganze Video: {LONG}"


def test_still_processing_after_the_wait_is_pending_not_an_error():
    yt, clock = FakeYT(states=["uploaded"]), Clock()
    res = upload.post_comment(yt, "vid", PKG, wait_s=12, sleep=clock.sleep, clock=clock)
    assert res["status"] == "pending" and "still processing" in res["error"]
    assert "comments.insert" not in yt.names()


def test_the_channels_own_link_comment_is_never_posted_twice():
    mine = {"id": "old-comment", "snippet": {"topLevelComment": {"snippet": {
        "textOriginal": f"Das ganze Video: {LONG}", "authorChannelId": {"value": CHANNEL}}}}}
    stranger = {"id": "x", "snippet": {"topLevelComment": {"snippet": {
        "textOriginal": f"Look: {LONG}", "authorChannelId": {"value": "UC-someone-else"}}}}}
    yt = FakeYT(threads=[stranger, mine])
    res = upload.post_comment(yt, "vid", PKG)
    assert res == {**res, "status": "exists", "id": "old-comment"}
    assert "comments.insert" not in yt.names()
    yt = FakeYT(threads=[stranger])   # someone else's link does not count
    assert upload.post_comment(yt, "vid", PKG)["status"] == "added"


def test_the_full_api_error_is_kept_and_only_server_errors_are_tried_again():
    refused = HttpError(403, "commentsDisabled", "The video identified by the videoId parameter has disabled comments.")
    res = upload.post_comment(FakeYT(insert_error=refused), "vid", PKG)
    assert res["status"] == "failed"
    assert res["error"] == ("HttpError HTTP 403 commentsDisabled: The video identified by the videoId parameter has "
                            "disabled comments.")
    assert upload._note("e", res) == f"comment not added: {res['error']}"
    busy = HttpError(503, "backendError", "Backend Error")
    assert upload.post_comment(FakeYT(insert_error=busy), "vid", PKG)["status"] == "pending"
    assert upload.post_comment(FakeYT(states=["rejected"]), "vid", PKG)["status"] == "failed"


@pytest.fixture
def uploaded_short(crew):
    source = episodes.create("I ran five local models")["id"]
    eid = episodes.create("Five models", kind="short", mode="clip", source_episode=source)["id"]
    root = paths.episode_dir(eid)
    (root / "export" / "video.mp4").write_bytes(b"\0" * 10)
    (root / "export" / "upload.json").write_text(json.dumps({"video": "export/video.mp4", **PKG}))
    card = approvals.propose(eid, "upload", "publish", "Publish", file="export/upload.json")
    approvals.decide(card["id"], True)
    result = {"video_id": "vid", "card": card["id"], "package": "export/upload.json",
              "notes": ["comment not added: HttpError"]}
    (root / "export" / "upload-result.json").write_text(json.dumps(result))
    return eid, root


def _result(root):
    return json.loads((root / "export" / "upload-result.json").read_text())


def test_crewcut_youtube_comment_posts_the_approved_text_once(uploaded_short):
    eid, root = uploaded_short
    yt = FakeYT()
    res = upload.comment(eid, youtube=yt)
    assert res["status"] == "added" and res["text"] == f"Das ganze Video: {LONG}"
    saved = _result(root)
    assert saved["comment"]["id"] == "new-comment"
    assert saved["notes"] == [f"comment with the link to the long video added (new-comment); {upload.PIN_NOTE}"]
    again = FakeYT()
    assert upload.comment(eid, youtube=again)["id"] == "new-comment" and again.calls == []


def test_a_package_changed_after_its_card_gets_no_comment(uploaded_short):
    eid, root = uploaded_short
    pkg = json.loads((root / "export" / "upload.json").read_text())
    (root / "export" / "upload.json").write_text(json.dumps({**pkg, "related_comment": "Something unapproved"}))
    with pytest.raises(PermissionError, match="accepted publish card"):
        upload.comment(eid, youtube=FakeYT())


def test_the_worker_posts_a_waiting_comment_when_it_is_due(uploaded_short, monkeypatch):
    eid, root = uploaded_short
    said = []
    monkeypatch.setattr(flow, "post", lambda episode, text, **kw: said.append((episode, text)))
    # the upload could not wait long enough: the comment is held, then the try says "still processing"
    upload._hold_comment(eid, "vid", "export/upload.json", 105, now=1000)
    res = upload.post_comment(FakeYT(states=["uploaded"]), "vid", PKG)
    upload._record_comment(eid, _result(root), res, "export/upload.json", now=1000)
    assert _result(root)["comment"]["status"] == "pending"
    assert "crewcut youtube comment" in _result(root)["notes"][-1]
    assert upload.due_comments(now=1030) == []           # not before the next try
    assert upload.due_comments(now=1061) == [eid]
    upload.comments_tick(now=1061, youtube=FakeYT(states=["uploaded"]), background=False)
    assert said == [] and upload.due_comments(now=1100) == []   # still processing: next try later, quietly
    yt = FakeYT()
    upload.comments_tick(now=1200, youtube=yt, background=False)
    assert _result(root)["comment"]["status"] == "added" and yt.names()[-1] == "comments.insert"
    assert db.kv_get(upload.PENDING + eid) is None and upload.due_comments(now=10 ** 9) == []
    assert len(said) == 1 and "Pin it in YouTube Studio" in said[0][1]


def test_the_worker_gives_up_after_a_day(uploaded_short, monkeypatch):
    eid, root = uploaded_short
    said = []
    monkeypatch.setattr(flow, "post", lambda episode, text, **kw: said.append(text))
    upload._hold_comment(eid, "vid", "export/upload.json", 0, now=0)
    upload.comments_tick(now=upload.COMMENT_GIVE_UP_S + 1, youtube=FakeYT(states=["uploaded"]), background=False)
    assert _result(root)["comment"]["status"] == "failed" and "gave up" in _result(root)["comment"]["error"]
    assert db.kv_get(upload.PENDING + eid) is None and len(said) == 1
