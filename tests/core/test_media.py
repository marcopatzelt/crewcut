"""GET /api/episodes/{id}/media, Episode.needs and .seconds, Activity.preview (crewcut/media.py).

A tiny episode is built in the test studio: a 4-second video made with ffmpeg, thumbnail rounds, a cut check, an edit
plan with 3D inserts and rendered frames, a running job and a rented GPU. The answers are compared field by field with
the shapes in web/src/api/types.ts.
"""

import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crewcut import db, episodes, media
from crewcut.compute import state
from crewcut.conductor import queue
from crewcut.render.plan import Plan
from crewcut.server.app import create_app

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
TYPES = Path(__file__).resolve().parents[2] / "web" / "src" / "api" / "types.ts"
NOW = 1_800_000_000  # a fixed clock for the rental


# ---- the TypeScript contract -----------------------------------------------------------------------------------------
def _fields(body: str) -> dict:
    """Field names of a TypeScript object body; an inline object type maps to its own fields, others to None."""
    out, i, depth = {}, 0, 0
    pat = re.compile(r"(\w+)\??\s*:\s*")
    while i < len(body):
        m = pat.match(body, i) if depth == 0 and (i == 0 or body[i - 1] in " \t\n;{") else None
        if m:
            j = m.end()
            if body.startswith("{", j):
                k, d = j + 1, 1
                while d:
                    d += {"{": 1, "}": -1}.get(body[k], 0)
                    k += 1
                out[m.group(1)] = _fields(body[j + 1:k - 1])
                i = k
            else:
                out[m.group(1)] = None
                i = j
            continue
        depth += {"{": 1, "}": -1}.get(body[i], 0)
        i += 1
    return out


def ts(name: str) -> dict:
    """The fields of `export interface <name>` in web/src/api/types.ts (the image ships only the built UI: skip there)."""
    if not TYPES.is_file():
        pytest.skip("web/src/api/types.ts is not here (inside the image only web/dist is shipped)")
    text = TYPES.read_text(encoding="utf-8")
    m = re.search(rf"export interface {name}\b[^{{]*\{{", text)
    assert m, f"interface {name} not in types.ts"
    i, d = m.end(), 1
    while d:
        d += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return _fields(re.sub(r"/\*.*?\*/|//[^\n]*", "", text[m.end():i - 1], flags=re.S))


def keys(d: dict | None) -> set:
    return set((d or {}).keys())


# ---- building the episode ----------------------------------------------------------------------------------------------
def ffmpeg(*args) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


def make_video(path: Path, seconds: float = 4.0) -> Path:
    """A moving test picture; the sound is quiet in the first half and eight times louder in the second."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"testsrc=s=160x90:r=25:d={seconds}", "-f", "lavfi", "-i",
           f"aevalsrc=0.1*sin(2*PI*440*t)*(1+7*gt(t\\,{seconds / 2})):s=48000:d={seconds}",
           "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path)
    return path


def png(path: Path, color=(200, 40, 40), age: float = 0.0) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), color).save(path)
    if age:
        t = time.time() - age
        os.utime(path, (t, t))
    return path


def card(eid: str, kind: str, status: str = "open", **extra) -> int:
    return db.insert("cards", episode=eid, step=extra.pop("step", "edit"), kind=kind, title=extra.pop("title", kind),
                     status=status, created=db.now(), options=extra.pop("options", []), data={}, **extra)


def thumbnails_round(ep: Path) -> Path:
    """An old round v1 and the newest round v2 with three variants, inputs, an upload copy and a preview sheet."""
    png(ep / "graphics/thumbnail/v1-first/A-old/thumbnail-v001.png", age=1000)
    r = ep / "graphics/thumbnail/v2-face"
    png(r / "A-face-right/thumbnail-v001.png")
    png(r / "A-face-right/1-photo.jpg")                       # an input, never a variant
    png(r / "A-face-right/thumbnail-v001-1280x720.jpg")       # the upload copy
    png(r / "B-result-left/thumbnail-v001.png", (40, 200, 40))
    png(r / "C-progress/thumbnail-v001.png", age=50)
    png(r / "C-progress/thumbnail-v002.png", (40, 40, 200))
    png(r / "check/preview-320.png")
    (r / "variants.json").write_text(json.dumps(
        [{"id": "A", "label": "Face right", "note": "Title left, four sites", "recommended": True}]))
    return r


def edit_plan(ep: Path, eid: str, scene: str = "stack") -> Path:
    plan = {"title": "Intro, the stack at night", "base": "work/speaker-v002.mov",
            "output": f"export/{eid}-v002-preview.mp4",
            "inserts": [{"id": "k1", "kind": "2d", "scene": "keyword", "start": 0.2, "end": 0.8, "transparent": True,
                         "data": {"text": "LOCAL"}},
                        {"id": "d1", "kind": "3d", "scene": scene, "start": 1.0, "end": 1.4, "data": {"n": 1}},
                        {"id": "d2", "kind": "3d", "scene": scene, "start": 2.0, "end": 2.4, "data": {"n": 2},
                         "name": "Tower"},
                        {"id": "d3", "kind": "3d", "scene": scene, "start": 3.0, "end": 3.4, "data": {"n": 3}}]}
    p = ep / "edit" / "plan-v002.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan))
    return p


def render_frames(ep: Path, plan_path: Path) -> dict:
    """d1 fully rendered and encoded, d2 three frames in, d3 only a probe still. Returns the frame folders."""
    plan = Plan(plan_path)
    d1, d2 = plan.by_id("d1"), plan.by_id("d2")
    for i in range(d1.render_frames):
        png(d1.out_dir / f"{i:04d}.png", age=100 - i)
    d1.clip.write_bytes(b"encoded")
    for i in range(3):
        png(d2.out_dir / f"{i:04d}.png", age=10 - i)
    png(ep / "render/probe/d3-0020.png")
    return {"d1": d1, "d2": d2}


@pytest.fixture
def client():
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


@pytest.fixture
def eid():
    return episodes.create("Local LLMs on a laptop")["id"]


@pytest.fixture
def ep(studio, eid):
    return studio / "episodes" / eid


def wait_for_strip(client, eid: str, timeout: float = 60.0) -> dict:
    t0 = time.time()
    while True:
        cut = client.get(f"/api/episodes/{eid}/media").json()["cut"]
        if not cut["pending"]:
            return cut
        assert time.time() - t0 < timeout, "the strip was not made in time"
        time.sleep(0.1)


# ---- the whole answer -------------------------------------------------------------------------------------------------
@needs_ffmpeg
def test_media_matches_the_contract(client, eid, ep, monkeypatch):
    monkeypatch.setattr(state, "clock", lambda: NOW)
    thumbnails_round(ep)
    make_video(ep / "export" / f"{eid}-v002-preview.mp4")
    (ep / "export" / f"{eid}-v001-preview.mp4").write_bytes(b"older version, newer file")
    (ep / "edit" / "cut-plan-v002.json").write_text(json.dumps({"cuts": [{"id": f"c{i}"} for i in range(5)]}))
    plan_path = edit_plan(ep, eid)
    frames = render_frames(ep, plan_path)
    findings = [{"area": "Output", "level": "ERROR", "id": "gap", "text": "Black frame", "time": 1.0},
                {"area": "Output", "level": "CHECK", "id": "loud", "text": "Listen here", "time": 2.5},
                {"area": "Plan", "level": "NOTE", "id": "length", "text": "100 frames", "time": None},
                {"area": "Plan", "level": "OK", "id": "fine", "text": "Fine", "time": 3.0},
                {"area": "Picture", "level": "NOTE", "id": "zoom", "text": "Zoom", "time": 0.5}]
    (ep / "review" / "cut-check-v002.json").write_text(json.dumps({"findings": findings}))
    (ep / "review" / "cut-check-v001.json").write_text(json.dumps(
        {"findings": [{"level": "ERROR", "text": "old", "time": 0.1}]}))
    thumb_card = card(eid, "thumbnail", step="thumbnail")
    job = db.insert("jobs", episode=eid, step="edit", identity="editor", kind="agent", task="Render the 3D scenes",
                    status="running", doing="Rendering 3D on 1 rented GPU: 30 of 81 frames", progress=0.37,
                    created=db.now(), started=db.now())
    rid = db.insert("rentals", provider="vast", instance="123", label="crewcut-test", episode=eid, job=job,
                    price_per_hour=0.6, started=state.iso(NOW - 1800), deadline=state.iso(NOW + 2700),
                    status="ready", detail=json.dumps({"session": "abc123", "gpu": "RTX_4090", "step": "edit"}))
    state.save_session({"id": "abc123", "episode": eid, "cap_usd": 1.5, "rentals": [rid], "closed": None})

    r = client.get(f"/api/episodes/{eid}/media")
    assert r.status_code == 200
    m = r.json()
    assert keys(m) == keys(ts("EpisodeMedia"))

    # thumbnails: the newest round, one image per variant folder, the Designer's note, the open card
    assert [t["id"] for t in m["thumbnails"]] == ["A", "B", "C"]
    for t in m["thumbnails"]:
        assert keys(t) == keys(ts("MediaThumb"))
    a, b, c = m["thumbnails"]
    assert (a["label"], a["note"], a["recommended"]) == ("Face right", "Title left, four sites", True)
    assert (b["label"], b["note"], b["recommended"]) == ("Result left", None, False)
    assert a["url"] == f"/api/files/{eid}/graphics/thumbnail/v2-face/A-face-right/thumbnail-v001.png"
    assert c["url"].endswith("C-progress/thumbnail-v002.png")
    assert {t["card"] for t in m["thumbnails"]} == {thumb_card} and not any(t["picked"] for t in m["thumbnails"])
    assert client.get(a["url"]).status_code == 200

    # the cut: version 2 (not the newer file of version 1), frames and peaks still being made
    cut = m["cut"]
    assert keys(cut) == keys(ts("MediaCut"))
    assert cut["version"] == "v2" and abs(cut["seconds"] - 4.0) < 0.2
    assert cut["shots"] == 5 + 3                      # five speaker pieces, three full-frame 3D inserts
    assert cut["markers"] == [{"t": 0.5, "level": "note", "text": "Zoom"},
                              {"t": 1.0, "level": "error", "text": "Black frame"},
                              {"t": 2.5, "level": "warning", "text": "Listen here"}]
    for mk in cut["markers"]:
        assert keys(mk) == keys(ts("MediaCut")["markers"])
    assert cut["facts"] == ["Keywords only", "8 cuts a minute", "-14 LUFS"]
    assert cut["pending"] is True and cut["frames"] == [] and cut["peaks"] == []   # the request never waits

    # 3D scenes: d1 done, d2 rendering (frames come in, the rented GPU is live), d3 queued with its probe still
    sc = m["scenes"]
    assert keys(sc) == keys(ts("MediaScenes"))
    assert (sc["title"], sc["done"], sc["total"]) == ("Intro, the stack at night", 1, 3)
    items = {i["id"]: i for i in sc["items"]}
    for i in sc["items"]:
        assert keys(i) == keys(ts("MediaScenes")["items"])
    n = frames["d1"].render_frames
    assert items["d1"]["status"] == "done" and items["d1"]["progress"] == 1.0 and items["d1"]["seconds"] == 0.4
    assert items["d1"]["url"].endswith(f"{frames['d1'].out_dir.name}/{n - 1:04d}.png")   # the newest frame
    assert (items["d2"]["status"], items["d2"]["progress"], items["d2"]["name"]) == ("rendering", round(3 / n, 3),
                                                                                     "Tower")
    assert items["d3"]["status"] == "queued" and items["d3"]["progress"] is None
    assert items["d3"]["url"] == f"/api/files/{eid}/render/probe/d3-0020.png" and items["d3"]["name"] == "Stack"

    # the rented GPU
    g = m["gpu"]
    assert keys(g) == keys(ts("MediaGpu"))
    assert g == {"name": "RTX 4090", "started": state.iso(NOW - 1800), "minutes_left": 45, "so_far_usd": 0.3,
                 "cap_usd": 1.5, "progress": 0.37, "delete_note": "Deleted when done, frames come home",
                 "session": rid, "price_per_hour": 0.6, "cap_per_gpu_hour": 0.6}

    # the strip arrives in the background: ten frames 320 px wide and about 240 peaks, louder in the second half
    cut = wait_for_strip(client, eid)
    assert len(cut["frames"]) == 10 and all(keys(f) == keys(ts("MediaCut")["frames"]) for f in cut["frames"])
    ts_ = [f["t"] for f in cut["frames"]]
    assert ts_ == sorted(ts_) and 0 < ts_[0] < ts_[-1] < 4.0
    from PIL import Image
    shot = client.get(cut["frames"][0]["url"])
    assert shot.status_code == 200 and Image.open(io.BytesIO(shot.content)).size[0] == 320
    peaks = cut["peaks"]
    assert len(peaks) == 240 and min(peaks) >= 0 and max(peaks) == 1.0
    assert sum(peaks[:100]) / 100 < 0.3 < sum(peaks[-100:]) / 100
    assert (ep / "work" / f"strip-{eid}-v002-preview" / "peaks.json").is_file()


def test_missing_folders_give_nulls(client, eid, ep):
    for d in list(ep.iterdir()):
        if d.is_dir():
            shutil.rmtree(d)
    assert client.get(f"/api/episodes/{eid}/media").json() == {"thumbnails": [], "cut": None, "scenes": None,
                                                                 "gpu": None, "cover_preview": None, "imported": False}
    s = episodes.summary(eid)
    assert s["needs"] is None and s["seconds"] is None
    assert client.get("/api/episodes/999-nothing/media").status_code == 404


def test_a_plan_that_does_not_load_still_shows_its_frames(client, eid, ep):
    """A scene the renderer does not know: the newest render/inserts/<id>-<hash>/ folder still counts."""
    edit_plan(ep, eid, scene="no-such-scene")
    for i in range(12):                                   # 0.4 s at 25 fps = 10 frames + 2
        png(ep / "render/inserts/d1-0123456789/" / f"{i:04d}.png", age=12 - i)
    png(ep / "render/inserts/d2-abcdefabcd/0000.png")
    png(ep / "render/inserts/d2x-abcdefabcd/0000.png")    # another insert whose id starts the same way
    sc = client.get(f"/api/episodes/{eid}/media").json()["scenes"]
    items = {i["id"]: i for i in sc["items"]}
    assert (sc["done"], sc["total"]) == (1, 3)
    assert items["d1"]["status"] == "done" and items["d1"]["url"].endswith("d1-0123456789/0011.png")
    assert items["d2"]["status"] == "queued" and items["d2"]["progress"] == round(1 / 12, 3)   # nothing renders now
    assert items["d3"] == {"id": "d3", "name": "No such scene", "status": "queued", "progress": None,
                           "seconds": 0.4, "url": None}


def test_picked_comes_from_the_accepted_card(eid, ep):
    thumbnails_round(ep)
    card(eid, "thumbnail", "accepted", options=["Thumbnail A", "Thumbnail B", "Thumbnail C"], choice=1,
         file="graphics/thumbnail/v2-face/check/preview-320.png")
    assert [t["picked"] for t in media.thumbnails(eid)] == [False, True, False]
    assert {t["card"] for t in media.thumbnails(eid)} == {None}
    card(eid, "thumbnail", options=["A", "B"])            # a newer question: the old answer no longer counts
    assert not any(t["picked"] for t in media.thumbnails(eid))


def test_an_answer_about_an_older_round_is_not_picked(eid, ep):
    thumbnails_round(ep)
    card(eid, "thumbnail", "accepted", options=["A"], choice=0, file="graphics/thumbnail/v1-first/A-old/thumbnail-v001.png")
    assert not any(t["picked"] for t in media.thumbnails(eid))


def test_flat_thumbnails_take_letters_in_file_order(eid, ep):
    for i in (2, 1):
        png(ep / "graphics" / "thumbnail" / f"20261116-1010{i}0-codex-{i}.png")
    got = media.thumbnails(eid)
    assert [(t["id"], t["label"]) for t in got] == [("A", "Variant A"), ("B", "Variant B")]
    assert got[0]["url"].endswith("codex-1.png")


# ---- the strip: background, once per video, cached ---------------------------------------------------------------------
@needs_ffmpeg
def test_strip_is_made_once_per_video_and_cached(eid, ep, monkeypatch):
    video = make_video(ep / "work" / "speaker-v001.mov", seconds=2.0)
    assert media.cut_source(ep) == video
    real, gate, calls = media.make_strip, threading.Event(), []

    def slow(v, d):
        calls.append(v)
        gate.wait(10)
        return real(v, d)

    monkeypatch.setattr(media, "make_strip", slow)
    assert media.strip(ep, video) is None and media.strip(ep, video) is None   # one thread, never a second
    gate.set()
    t0 = time.time()
    while media.strip(ep, video) is None:
        assert time.time() - t0 < 30
        time.sleep(0.05)
    assert len(calls) == 1
    data = media.strip(ep, video)
    assert len(data["frames"]) == 10 and len(data["peaks"]) == 240 and data["seconds"] == pytest.approx(2.0, abs=0.1)
    monkeypatch.setattr(media, "make_strip", lambda v, d: calls.append(v) or {})
    assert media.strip(ep, video) == data and len(calls) == 1               # cached: nothing runs again
    st = video.stat()
    os.utime(video, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))    # a rebuilt video is made again
    assert media.strip(ep, video) is None
    t0 = time.time()
    while len(calls) < 2:
        assert time.time() - t0 < 10
        time.sleep(0.05)


def test_a_broken_video_is_not_tried_on_every_request(eid, ep):
    bad = ep / "export" / f"{eid}-v001-final.mp4"
    bad.write_bytes(b"not a video")
    data = media.make_strip(bad, media.strip_dir(ep, bad))
    assert data["frames"] == [] and data["peaks"] == [] and data["errors"]
    assert media.strip(ep, bad) == data


# ---- the episode card -------------------------------------------------------------------------------------------------
def test_summary_needs_and_cached_seconds(eid, ep, monkeypatch):
    from crewcut.cut import media as cutmedia
    probes = []

    def fake_run(argv, **kw):
        probes.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"format": {"duration": "12.5"}}', stderr="")

    monkeypatch.setattr(cutmedia, "run", fake_run)
    video = ep / "export" / f"{eid}-v001-preview.mp4"
    video.write_bytes(b"fake")
    for _ in range(3):
        s = episodes.summary(eid)
    assert s["seconds"] == 12.5 and len(probes) == 1                       # ffprobe once, not on every call
    st = video.stat()
    os.utime(video, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    assert episodes.summary(eid)["seconds"] == 12.5 and len(probes) == 2

    assert s["needs"] is None
    for i, letter in enumerate("ABCD"):
        png(ep / "graphics" / "thumbnail" / "v1-test" / f"{letter}-m{i}" / "thumbnail-v001.png")
    tc = card(eid, "thumbnail", title="Thumbnail A, test B", step="thumbnail")
    needs = episodes.summary(eid)["needs"]
    assert keys(needs) == keys(ts("Episode")["needs"])
    assert needs["card"] == tc and needs["kind"] == "thumbnail" and needs["title"] == "Thumbnail A, test B"
    assert [u.split("/")[-2] for u in needs["images"]] == ["A-m0", "B-m1", "C-m2"]

    db.update("cards", tc, status="accepted")
    plan_path = edit_plan(ep, eid)
    render_frames(ep, plan_path)
    sc = card(eid, "spend", title="Rent a GPU for the 3D scenes")
    needs = episodes.summary(eid)["needs"]
    assert needs["card"] == sc and len(needs["images"]) == 3
    assert needs["images"][2] == f"/api/files/{eid}/render/probe/d3-0020.png"

    db.update("cards", sc, status="declined")
    png(ep / "review" / "frame-231.png")
    pc = card(eid, "proof", file="review/frame-231.png")
    assert episodes.summary(eid)["needs"]["images"] == [f"/api/files/{eid}/review/frame-231.png"]
    db.update("cards", pc, status="accepted")
    card(eid, "script", file="brief/SCRIPT-v001.md")
    assert episodes.summary(eid)["needs"]["images"] == []


# ---- the job's picture --------------------------------------------------------------------------------------------------
def test_job_preview_shows_the_newest_picture_since_the_job_started(eid, ep, monkeypatch):
    assert "preview" in ts("Activity")
    png(ep / "render" / "inserts" / "d1-0123456789" / "0000.png", age=300)     # from before the job
    jid = db.insert("jobs", episode=eid, step="edit", identity="editor", kind="agent", task="x", status="running",
                    doing="Rendering", created=db.now(), started=db.now())
    assert queue.job_view(queue.get(jid))["preview"] is None
    png(ep / "render" / "inserts" / "d1-0123456789" / "0001.png")
    png(ep / "graphics" / "thumbnail" / "A-x" / "thumbnail-v001.png", age=-5)   # another step's picture
    assert queue.job_view(queue.get(jid))["preview"] == f"/api/files/{eid}/render/inserts/d1-0123456789/0001.png"

    scans = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda p: scans.append(p) or real(p))
    assert queue.job_view(queue.get(jid))["preview"].endswith("0001.png") and scans == []   # cached by folder mtime
    png(ep / "render" / "inserts" / "d1-0123456789" / "0002.png", age=-10)
    assert queue.job_view(queue.get(jid))["preview"].endswith("0002.png") and len(scans) == 1
    monkeypatch.setattr(os, "scandir", real)

    designer = db.insert("jobs", episode=eid, step="thumbnail", identity="designer", kind="agent", task="x",
                         status="waiting", created=db.now(), started=db.now())
    assert queue.job_view(queue.get(designer))["preview"].endswith("A-x/thumbnail-v001.png")
    db.update("jobs", jid, status="done", ended=db.now())
    assert queue.job_view(queue.get(jid))["preview"] is None
