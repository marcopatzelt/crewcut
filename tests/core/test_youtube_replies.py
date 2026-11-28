"""Comment word -> link reply: a Short ends with "comment GPU", and every comment with the word gets the approved link
as a reply, once, within the hourly and daily limits, never to the channel's own comments. No network: a fake client.

Channel owner, 28.11.2026: "Wenn du das auch haben willst, dann commente das und das ... so dass man dann per DM den
Funnel verschickt." YouTube has no DMs, so the funnel is a reply under the comment."""

import json
from types import SimpleNamespace

import pytest

from crewcut import approvals, cta, db, episodes, paths
from crewcut.conductor import flow
from crewcut.youtube import replies, upload

CHANNEL = "UC-own"
URL = "striq.de/gpu"


class HttpError(Exception):
    def __init__(self, status, reason, message="refused"):
        super().__init__(message)
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps({"error": {"code": status, "message": message,
                                             "errors": [{"reason": reason, "message": message}]}}).encode()


def comment(cid, text, at, author="UC-viewer", own_reply=False, can_reply=True):
    thread = {"id": cid, "snippet": {"canReply": can_reply, "topLevelComment": {"id": cid, "snippet": {
        "textOriginal": text, "authorChannelId": {"value": author}, "publishedAt": at}}}}
    if own_reply:
        thread["replies"] = {"comments": [{"id": f"r-{cid}", "snippet": {"authorChannelId": {"value": CHANNEL}}}]}
    return thread


class FakeYT:
    """videos.list answers the video's channel and privacy; commentThreads.list serves `threads` (newest first) in
    pages of `page`; comments.insert records the reply or raises `insert_error`."""

    def __init__(self, threads=(), privacy="public", page=100, insert_error=None, list_error=None):
        self.threads, self.privacy, self.page = list(threads), privacy, page
        self.insert_error, self.list_error = insert_error, list_error
        self.calls, self.sent = [], []

    def videos(self):
        self._api = "videos"
        return self

    def commentThreads(self):  # noqa: N802 - the API's name
        self._api = "threads"
        return self

    def comments(self):
        self._api = "comments"
        return self

    def list(self, **kw):
        self.calls.append((f"{self._api}.list", kw))
        if self._api == "videos":
            self._next = {"items": [{"snippet": {"channelId": CHANNEL}, "status": {"privacyStatus": self.privacy}}]}
        else:
            if self.list_error:
                self._next = self.list_error
                return self
            start = int(kw.get("pageToken") or 0)
            items = self.threads[start:start + self.page]
            nxt = start + self.page
            self._next = {"items": items, **({"nextPageToken": str(nxt)} if nxt < len(self.threads) else {})}
        return self

    def insert(self, **kw):
        self.calls.append(("comments.insert", kw))
        if self.insert_error:
            self._next = self.insert_error
        else:
            self.sent.append(kw["body"]["snippet"])
            self._next = {"id": f"reply-{len(self.sent)}"}
        return self

    def execute(self):
        if isinstance(self._next, Exception):
            raise self._next
        return self._next

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def short(crew, studio, monkeypatch):
    monkeypatch.setattr(flow, "post", lambda *a, **kw: None)
    (studio / "brand").mkdir(exist_ok=True)
    (studio / "brand" / "brand.json").write_text("{}")
    (studio / "brand" / "channel.json").write_text(json.dumps({"upload": {"cta_reply": "Hier ist der Link: {url} "
                                                                                       "Viel Spaß!"}}))
    eid = episodes.create("GPU for 2 dollars", kind="short", mode="original")["id"]
    root = paths.episode_dir(eid)
    result = {"video_id": "vid", "package": "export/upload.json", "cta_keyword": "GPU", "cta_url": URL, "notes": []}
    (root / "export" / "upload-result.json").write_text(json.dumps(result))
    return eid, root


def config(studio, **values):
    (studio / "config").mkdir(exist_ok=True)
    lines = "\n".join(f"{k} = {json.dumps(v) if isinstance(v, str) else str(v).lower()}" for k, v in values.items())
    (studio / "config" / "crewcut.toml").write_text(f"[youtube]\n{lines}\n")


def test_the_word_counts_as_a_whole_word_in_any_case():
    assert cta.has_keyword("gpu!", "GPU") and cta.has_keyword("Bitte GPU", "GPU") and cta.has_keyword("„Gpu“", "GPU")
    assert not cta.has_keyword("GPUs please", "GPU") and not cta.has_keyword("eGPU", "GPU")
    assert cta.is_keyword("GPU") and cta.is_keyword("KI-KURS") and not cta.is_keyword("gpu")
    assert not cta.is_keyword("TWO WORDS") and not cta.is_keyword("G")


def test_every_comment_with_the_word_gets_the_link_once(short):
    eid, root = short
    yt = FakeYT([comment("c3", "GPU", "2026-11-28T12:03:00Z"), comment("c2", "nice video", "2026-11-28T12:02:00Z"),
                 comment("c1", "gpu bitte", "2026-11-28T12:01:00Z")])
    res = replies.run(youtube=yt, now=1000)
    assert [r["sent"] for r in res] == [2]
    assert [s["parentId"] for s in yt.sent] == ["c1", "c3"]           # whoever asked first gets it first
    assert yt.sent[0]["textOriginal"] == "Hier ist der Link: striq.de/gpu Viel Spaß!"
    status = json.loads((root / "export" / "cta-replies.json").read_text())
    assert status["sent_total"] == 2 and status["keyword"] == "GPU" and "gpu bitte" not in json.dumps(status)
    again = FakeYT(yt.threads)
    assert replies.run(youtube=again, now=2000)[0]["sent"] == 0 and again.sent == []
    assert json.loads((root / "export" / "cta-replies.json").read_text())["sent_total"] == 2


def test_never_the_own_channel_and_never_a_thread_the_channel_answered(short):
    yt = FakeYT([comment("own", "Kommentier GPU", "2026-11-28T12:03:00Z", author=CHANNEL),
                 comment("done", "GPU", "2026-11-28T12:02:00Z", own_reply=True),
                 comment("closed", "GPU", "2026-11-28T12:01:00Z", can_reply=False)])
    res = replies.run(youtube=yt, now=1000)[0]
    assert res["sent"] == 0 and yt.sent == []
    with db.conn() as c:
        assert [r["status"] for r in c.execute("SELECT status FROM cta_replies")] == ["found"]


def test_the_hourly_and_the_daily_limit(short, studio):
    eid, _ = short
    config(studio, cta_replies_per_video_hour=2, cta_replies_per_day=3)
    threads = [comment(f"c{i}", "GPU", f"2026-11-28T12:{i:02d}:00Z") for i in range(5, 0, -1)]
    res = replies.run(youtube=FakeYT(threads), now=10_000)[0]
    assert res["sent"] == 2 and res["waiting"] == 3
    assert replies.run(youtube=FakeYT(threads), now=10_000 + 1800)[0]["sent"] == 0     # same hour
    res = replies.run(youtube=FakeYT(threads), now=10_000 + 3700)[0]                  # next hour: the day caps at 3
    assert res["sent"] == 1 and res["waiting"] == 2
    assert replies.sent_since(0) == 3


def test_dry_run_sends_and_stores_nothing(short, studio):
    eid, root = short
    config(studio, cta_replies="dry-run")
    yt = FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")])
    res = replies.run(youtube=yt, now=1000)[0]
    assert res["would_send"] == 1 and res["sent"] == 0 and "comments.insert" not in yt.names()
    assert replies.sent_since(0) == 0 and db.kv_get(replies.CURSOR + "vid") is None
    assert json.loads((root / "export" / "cta-replies.json").read_text())["mode"] == "dry-run"


def test_off_does_nothing_and_the_tick_keeps_its_interval(short, studio):
    config(studio, cta_replies="off")
    yt = FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")])
    assert replies.run(youtube=yt, now=1000) == [] and yt.calls == []
    assert replies.tick(now=10 ** 6, youtube=yt, background=False) is False
    config(studio, cta_replies="on", cta_replies_every_minutes=15)
    replies._last["t"] = 0.0
    assert replies.tick(now=10 ** 6, youtube=yt, background=False) is True and len(yt.sent) == 1
    assert replies.tick(now=10 ** 6 + 600, youtube=yt, background=False) is False       # 10 minutes later
    assert replies.tick(now=10 ** 6 + 901, youtube=yt, background=False) is True
    assert len(yt.sent) == 1


def test_paging_stops_at_the_comments_already_handled(short):
    old = [comment(f"o{i}", "hello", f"2026-11-28T10:{i:02d}:00Z") for i in range(50, 0, -1)]
    first = FakeYT([comment("c1", "GPU", "2026-11-28T11:00:00Z"), *old], page=10)
    replies.run(youtube=first, now=1000)
    assert first.names().count("threads.list") == 6 and len(first.sent) == 1
    new = FakeYT([comment("c2", "GPU", "2026-11-28T12:00:00Z"), comment("c1", "GPU", "2026-11-28T11:00:00Z"), *old],
                 page=1)
    replies.run(youtube=new, now=2000)
    # the new comment, the one as old as the cursor (read again, known), then the first older one: stop
    assert new.names().count("threads.list") == 3 and [s["parentId"] for s in new.sent] == ["c2"]


def test_youtube_refusals_stop_the_video_and_quota_stops_the_run(short, monkeypatch):
    eid, root = short
    said = []
    monkeypatch.setattr(flow, "post", lambda episode, text, **kw: said.append(text))
    off = HttpError(403, "commentsDisabled", "comments are off")
    res = replies.run(youtube=FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")], list_error=off), now=1000)[0]
    assert "commentsDisabled" in res["error"] and len(said) == 1
    replies.run(youtube=FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")], list_error=off), now=2000)
    assert len(said) == 1                                   # the same problem is said once
    busy = HttpError(503, "backendError")
    res = replies.run(youtube=FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")], insert_error=busy), now=3000)[0]
    assert "next run" in res["error"] and replies.sent_since(0) == 0
    yt = FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")])
    assert replies.run(youtube=yt, now=4000)[0]["sent"] == 1     # tried again and sent


def test_a_private_or_scheduled_short_is_not_read(short):
    eid, root = short
    yt = FakeYT([comment("c1", "GPU", "2026-11-28T12:01:00Z")], privacy="private")
    assert replies.run(youtube=yt, now=1000)[0]["skipped"].startswith("not public")
    assert "threads.list" not in yt.names()
    res = json.loads((root / "export" / "upload-result.json").read_text())
    (root / "export" / "upload-result.json").write_text(json.dumps({**res, "publish_at": "2030-01-01T08:00:00Z"}))
    assert replies.run(youtube=FakeYT(), now=1000) == []


def test_only_an_approved_package_counts_for_an_older_upload(short):
    eid, root = short
    res = json.loads((root / "export" / "upload-result.json").read_text())
    (root / "export" / "upload-result.json").write_text(json.dumps({k: v for k, v in res.items()
                                                                     if not k.startswith("cta_")}))
    pkg = {"video": "export/v.mp4", "title": "T", "description": "Kommentier GPU.", "cta_keyword": "GPU",
           "cta_url": URL, "related_comment": "Kommentier GPU für die Anleitung."}
    (root / "export" / "upload.json").write_text(json.dumps(pkg))
    assert replies.targets() == []                             # no accepted card for this package
    card = approvals.propose(eid, "upload", "publish", "Publish", file="export/upload.json")
    approvals.decide(card["id"], True)
    assert [(t["keyword"], t["url"]) for t in replies.targets()] == [("GPU", URL)]


def test_long_videos_only_when_switched_on(short, studio):
    long = episodes.create("GPU test")["id"]
    root = paths.episode_dir(long)
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "long-vid", "cta_keyword": "GPU",
                                                                    "cta_url": URL}))
    assert [t["episode"] for t in replies.targets(long=False)] == [short[0]]
    config(studio, cta_replies_long=True)
    assert replies.settings()["long"] is True
    assert {t["episode"] for t in replies.targets(long=True)} == {short[0], long}


def test_the_package_names_the_word_in_description_and_comment():
    ok = {"description": "Kommentier GPU und du bekommst die Anleitung.", "cta_keyword": "GPU", "cta_url": URL,
          "related_comment": "Kommentier GPU, dann schicke ich dir den Link zur Anleitung."}
    assert cta.package_problems(ok) == ([], [])
    assert cta.package_problems({**ok, "cta_url": None})[0]
    assert "capitals" in cta.package_problems({**ok, "cta_keyword": "gpu"})[0][0]
    assert any("description" in e for e in cta.package_problems({**ok, "description": "Nice."})[0])
    assert any("pinned comment" in e for e in cta.package_problems({**ok, "related_comment": "Hi"})[0])
    assert any("related_comment" in e for e in cta.package_problems({k: v for k, v in ok.items()
                                                                     if k != "related_comment"})[0])
    assert "not clickable" in cta.package_problems({**ok, "cta_url": "https://striq.de/" + "x" * 40})[1][0]
    assert cta.package_problems({"description": "x"}) == ([], [])


def test_a_short_with_a_word_and_no_long_video_still_gets_its_pinned_comment():
    pkg = {"title": "T", "description": "Kommentier GPU.", "cta_keyword": "GPU", "cta_url": URL,
           "related_comment": "Kommentier GPU für die Anleitung."}
    assert upload.comment_text(pkg) == "Kommentier GPU für die Anleitung."
    yt_threads = [{"id": "mine", "snippet": {"topLevelComment": {"snippet": {
        "textOriginal": "Kommentier GPU für die Anleitung.", "authorChannelId": {"value": CHANNEL}}}}}]

    class YT:
        def commentThreads(self):  # noqa: N802
            return self

        def list(self, **kw):
            return self

        def execute(self):
            return {"items": yt_threads}

    assert upload._existing(YT(), "vid", CHANNEL, pkg) == "mine"
    yt_threads[0]["snippet"]["topLevelComment"]["snippet"]["authorChannelId"]["value"] = "UC-viewer"
    assert upload._existing(YT(), "vid", CHANNEL, pkg) is None


def test_the_worker_looks_even_while_new_jobs_are_paused(crew, studio, monkeypatch):
    from crewcut.conductor import queue
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text("[engine]\nmax_parallel_agents = 0\nmax_parallel_replies = 0\n")
    seen = []
    monkeypatch.setattr(replies, "tick", lambda: seen.append("replies"))
    monkeypatch.setattr(queue.Worker, "maybe_update_engine", lambda self: None)
    queue.Worker().tick()
    assert seen == ["replies"]


def test_a_failure_after_some_replies_keeps_the_count_and_the_quota_stops_everything(short, crew):
    eid, root = short
    other = episodes.create("Second Short", kind="short", mode="original")["id"]
    (paths.episode_dir(other) / "export" / "upload-result.json").write_text(json.dumps({
        "video_id": "vid2", "cta_keyword": "KURS", "cta_url": "striq.de/kurs"}))

    class Quota(FakeYT):
        def insert(self, **kw):
            if len(self.sent) == 1:
                self.calls.append(("comments.insert", kw))
                self._next = HttpError(403, "quotaExceeded", "quota")
                return self
            return super().insert(**kw)

    yt = Quota([comment("c2", "GPU KURS", "2026-11-28T12:02:00Z"), comment("c1", "gpu kurs", "2026-11-28T12:01:00Z")])
    first, second = replies.run(youtube=yt, now=1000)
    assert first["sent"] == 1 and "quotaExceeded" in first["error"]
    assert second["sent"] == 0 and second["error"] == first["error"]                  # not even asked
    status = json.loads((paths.episode_dir(first["episode"]) / "export" / "cta-replies.json").read_text())
    assert status["sent_total"] == 1
    assert db.kv_get(replies.CURSOR + first["video_id"]) == "2026-11-28T12:01:00Z"   # up to the answered comment
    assert {first["episode"], second["episode"]} == {eid, other}
