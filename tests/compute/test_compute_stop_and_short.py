"""The GPU card's Stop (a real stop: the machines of that render are deleted, the frames at home stay) and the title
bar's Make a Short (a clip Short of this episode, the Scout's job shows up in Working now). Fake Vast, no money."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crewcut import db, episodes
from crewcut.compute import rentals, state
from crewcut.compute import session as session_fn
from crewcut.compute.errors import NeedsApproval
from crewcut.server.app import create_app

EP = "002-stop"


def accept(card_id: int) -> None:
    db.update("cards", card_id, status="accepted", decided_at=db.now())


def client():
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def rent(gpus=2):
    s = session_fn(episode=EP, step="edit", purpose="final render", cap_usd=3.0, monitor=False, detached=True).open()
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=gpus, max_minutes=60, final=gpus > 1)
    accept(e.value.card_id)
    return s, s.rent(gpus=gpus, max_minutes=60, final=gpus > 1)


def test_stop_deletes_every_machine_of_the_render_and_keeps_the_frames(fake, fssh, clock, studio):
    s, machines = rent(2)
    for m in machines:
        state.touch(m.rental, busy=True)
    home = studio / "episodes" / EP / "render" / "d1"
    home.mkdir(parents=True)
    (home / "0001.png").write_bytes(b"frame")
    clock.advance(minutes=10)
    r = client().post(f"/api/episodes/{EP}/gpu/{machines[0].rental}/stop")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stopped"] == 2 and sorted(body["rentals"]) == sorted(m.rental for m in machines)
    assert body["cost_usd"] > 0
    assert all(rentals.get(m.rental)["status"] == "destroyed" for m in machines)
    assert not fake.by_label(state.label())
    assert (home / "0001.png").read_bytes() == b"frame"          # what came home stays
    with db.conn() as c:
        texts = [x["text"] for x in c.execute("SELECT text FROM messages WHERE episode = ?", (EP,))]
    assert any("Stopped the rented GPU" in t for t in texts)
    again = client().post(f"/api/episodes/{EP}/gpu/{machines[0].rental}/stop")
    assert again.status_code == 200 and again.json()["stopped"] == 0


def test_stop_only_for_a_machine_of_this_episode(fake, fssh, clock):
    s, (m,) = rent(1)
    assert client().post(f"/api/episodes/999-other/gpu/{m.rental}/stop").status_code == 404
    assert rentals.get(m.rental)["status"] == "ready"


def test_make_a_short_starts_a_clip_and_the_scout(studio, crew):
    src = episodes.create("Claude improves a website 100 times")["id"]
    r = client().post(f"/api/episodes/{src}/shorts")
    assert r.status_code == 200, r.text
    res = r.json()
    short = episodes.read(res["episode"])
    assert short["kind"] == "short" and short["mode"] == "clip" and short["source_episode"] == src
    job = db.get("jobs", res["job"])
    assert job["identity"] == "scout" and job["status"] == "queued" and job["episode"] == res["episode"]
    jobs = client().get("/api/jobs").json()
    assert any(j["job"] == res["job"] for j in jobs)                 # it shows up in Working now
    assert client().post(f"/api/episodes/{res['episode']}/shorts").status_code == 400   # not from a Short
    assert client().post("/api/episodes/999-none/shorts").status_code == 404
