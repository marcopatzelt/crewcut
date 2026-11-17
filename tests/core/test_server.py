import pytest
from fastapi.testclient import TestClient

from crewcut.conductor import queue
from crewcut.server.app import create_app, create_prompter_app


@pytest.fixture
def client(crew, monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def test_state_and_new_episode(client):
    s = client.get("/api/state").json()
    assert s["app"]["engine_ok"] is False and s["episodes"] == []
    assert {m["id"] for m in s["team"]} >= {"showrunner", "editor"}
    r = client.post("/api/episodes", json={"text": "I ran five local AI models on a laptop"})
    assert r.status_code == 200
    eid = r.json()["id"]
    msgs = client.get(f"/api/episodes/{eid}/messages").json()
    assert msgs[0]["author"] == "user" and msgs[-1]["author"] == "showrunner"
    assert client.get("/api/state").json()["episodes"][0]["id"] == eid


def test_foreign_host_and_cross_site_writes_are_refused(crew):
    c = TestClient(create_app(start_worker=False), base_url="http://evil.example")
    assert c.get("/api/state").status_code == 403
    c2 = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    r = c2.post("/api/episodes", json={"text": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_cards_accept_flow(client, monkeypatch):
    from crewcut import approvals
    from crewcut.conductor import flow
    seen = []
    monkeypatch.setattr(flow, "on_card_decided", lambda card: seen.append(card["id"]))
    eid = client.post("/api/episodes", json={"text": "A topic"}).json()["id"]
    card = approvals.propose(eid, "title", "title", "Pick a title", options=["A", "B"])
    open_cards = client.get(f"/api/cards?episode={eid}&status=open").json()
    assert [c["id"] for c in open_cards] == [card["id"]]
    r = client.post(f"/api/cards/{card['id']}/accept", json={"choice": 1})
    assert r.json()["status"] == "accepted" and r.json()["choice"] == 1 and seen == [card["id"]]


def test_files_stay_inside_the_episode(client, studio):
    eid = client.post("/api/episodes", json={"text": "A topic"}).json()["id"]
    (studio / "secret.txt").write_text("no")
    assert client.get(f"/api/files/{eid}/../../secret.txt").status_code in (403, 404)
    assert client.get(f"/api/files/{eid}/brief/BRIEF.md").status_code == 200


def test_prompter_needs_the_token(client):
    eid = client.post("/api/episodes", json={"text": "A topic"}).json()["id"]
    info = client.get(f"/api/episodes/{eid}/prompter").json()
    token = info["url"].rsplit("/", 1)[1]
    assert info["qr_svg"].lstrip().startswith("<?xml") or "<svg" in info["qr_svg"]
    p = TestClient(create_prompter_app(), base_url="http://192.168.1.20:4748")
    assert p.get("/p/not-a-real-token-123/script").status_code == 404
    assert p.get(f"/p/{token}/script").json()["blocks"] == []
    r = p.post(f"/p/{token}/control", json={"playing": True, "speed": 99})
    assert r.json()["playing"] is True and r.json()["speed"] == 4.0


def test_web_app_manifest_is_served_with_its_type(crew, monkeypatch, tmp_path):
    from crewcut import paths
    (tmp_path / "index.html").write_text("<!doctype html><title>Crewcut</title>")
    (tmp_path / "manifest.webmanifest").write_text('{"name": "Crewcut", "display": "standalone"}')
    monkeypatch.setattr(paths, "web_dist_dir", lambda: tmp_path)
    c = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    r = c.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["display"] == "standalone"
    assert "<title>Crewcut</title>" in c.get("/e/012").text  # any other path is the app itself
