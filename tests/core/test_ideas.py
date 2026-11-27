"""Idea cards: the host exporter, the loader, Start episode and Dismiss."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crewcut import episodes, ideas
from crewcut.conductor import queue

ROOT = Path(__file__).resolve().parents[2]


def exporter():
    spec = importlib.util.spec_from_file_location("ideas_export", ROOT / "host" / "ideas-export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scout_file(tmp_path):
    p = tmp_path / "scout.json"
    p.write_text(json.dumps({"date": "2030-01-02", "ranked": [
        {"key": "gh:example/free-tool", "kind": "repo", "name": "example/free-tool", "url": "https://example.com/a",
         "desc": "A free tool that claims to replace a paid subscription app", "sources": ["search"],
         "sig": {"stars": 900, "velocity_day": 80.5, "gap": {"gap": "empty"}}, "score": {"viral": 4}, "total": 4.5},
        {"key": "gh:example/excluded", "name": "excluded", "url": "https://example.com/x", "excluded": "too old",
         "total": 5},
        {"key": "yt:abc", "kind": "youtube", "name": "A video", "url": "https://example.com/v", "desc": "",
         "sig": {"yt": [{"title": "A video", "channel": "C", "views": 1000, "x_median": 3.1}]}, "total": 3.0},
        {"key": "gh:example/low", "name": "low", "url": "https://example.com/l", "total": 1.0},
    ]}))
    return p


def braindump_dir(tmp_path):
    root = tmp_path / "links"
    for name, projects in (("2030-01-01-a", ["crewcut", "other"]), ("2030-01-01-b", ["other"])):
        d = root / name
        d.mkdir(parents=True)
        (d / "eintrag.json").write_text(json.dumps({
            "id": name, "url": f"https://example.com/{name}", "zeit": 1893456000.0, "zahlen": {"views": 5},
            "ergebnis": {"titel": f"Saved link {name}", "was": "Someone's agent rebuilt an app.",
                         "warum": "fits", "prioritaet": "hoch", "tags": ["agent"],
                         "projekte": [{"id": p, "idee": f"idea for {p}", "wo": "here"} for p in projects]}}))
    (root / "broken").mkdir()
    (root / "broken" / "eintrag.json").write_text("{")
    return root


def test_the_exporter_writes_scout_and_braindump_ideas(tmp_path, studio):
    ex = exporter()
    assert ex.main(["--studio", str(studio), "--scout", str(scout_file(tmp_path)), "--top", "2",
                    "--braindump", str(braindump_dir(tmp_path))]) == 0
    files = sorted(p.name for p in (studio / "inbox" / "ideas").glob("*.json"))
    assert files == ["braindump-2030-01-01-a.json", "scout-gh-example-free-tool.json", "scout-yt-abc.json"]
    s = json.loads((studio / "inbox" / "ideas" / "scout-gh-example-free-tool.json").read_text())
    assert s["source"] == "scout" and s["topic_type"] == "trending" and s["created"] == "2030-01-02"
    assert s["signals"]["stars"] == 900 and s["signals"]["gap"] == "empty" and s["signals"]["total"] == 4.5
    b = json.loads((studio / "inbox" / "ideas" / "braindump-2030-01-01-a.json").read_text())
    assert b["source"] == "braindump" and b["topic_type"] == "present" and "idea for crewcut" in b["summary"]
    assert "idea for other" not in b["summary"] and b["signals"]["priority"] == "hoch"
    assert b["created"].startswith("2030-01-01")


def test_the_exporter_dedupes_and_never_rewrites_decided_ideas(tmp_path, studio):
    ex = exporter()
    sf = scout_file(tmp_path)
    ex.main(["--studio", str(studio), "--scout", str(sf), "--top", "1"])
    p = studio / "inbox" / "ideas" / "scout-gh-example-free-tool.json"
    d = json.loads(p.read_text())
    d["status"] = "dismissed"
    p.write_text(json.dumps(d))
    ex.main(["--studio", str(studio), "--scout", str(sf), "--top", "1", "--refresh"])
    assert json.loads(p.read_text())["status"] == "dismissed"
    d["status"] = None
    d["title"] = "changed by hand"
    p.write_text(json.dumps(d))
    ex.main(["--studio", str(studio), "--scout", str(sf), "--top", "1"])
    assert json.loads(p.read_text())["title"] == "changed by hand"     # dedupe: kept
    ex.main(["--studio", str(studio), "--scout", str(sf), "--top", "1", "--refresh"])
    assert json.loads(p.read_text())["title"] == "example/free-tool"   # an open idea is refreshed


def test_the_exporter_needs_a_source(studio):
    with pytest.raises(SystemExit):
        exporter().main(["--studio", str(studio)])


def write_idea(studio, iid, **over):
    d = studio / "inbox" / "ideas"
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": iid, "source": "scout", "url": "https://example.com/t", "title": "A free tool replaces a paid app",
            "summary": "It claims to replace a subscription.", "signals": {"stars": 10}, "created": "2030-01-01"}
    data.update(over)
    (d / f"{iid}.json").write_text(json.dumps(data))
    return d / f"{iid}.json"


def test_the_loader_imports_suggests_and_keeps_decisions(studio):
    write_idea(studio, "scout-a")
    write_idea(studio, "braindump-b", source="braindump", title="My agent deleted the wrong folder",
               summary="The log shows it.", suggested_format="incident-file", reason="It is an incident.")
    write_idea(studio, "bad id", title="x")
    (studio / "inbox" / "ideas" / "mismatch.json").write_text(json.dumps({"id": "other", "title": "x"}))
    assert ideas.load() == {"new": 2, "updated": 0, "skipped": 2}
    rows = {r["id"]: r for r in ideas.list_ideas()}
    a, b = rows["scout-a"], rows["braindump-b"]
    assert a["status"] == "open" and a["suggested_format"] == "tool-test" and a["suggestion"] == "rule"
    assert a["signals"] == {"stars": 10}
    assert b["suggested_format"] == "incident-file" and b["suggestion"] == "exporter"
    write_idea(studio, "scout-a", title="A newer title")
    assert ideas.load()["updated"] == 1 and ideas.get("scout-a")["title"] == "A newer title"
    ideas.dismiss("scout-a")
    assert json.loads((studio / "inbox" / "ideas" / "scout-a.json").read_text())["status"] == "dismissed"
    write_idea(studio, "scout-a", title="Back again")
    ideas.load()
    assert ideas.get("scout-a")["status"] == "dismissed" and ideas.get("scout-a")["title"] == "A newer title"
    with pytest.raises(ValueError, match="dismissed already"):
        ideas.dismiss("scout-a")
    with pytest.raises(KeyError):
        ideas.get("nope")


@pytest.fixture
def client(crew, monkeypatch):
    added = []
    monkeypatch.setattr(queue, "add", lambda *a, **k: added.append((a, k)) or len(added))
    from crewcut.server.app import create_app
    c = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    c.added = added
    return c


def test_start_and_dismiss_through_the_api(client, studio):
    write_idea(studio, "scout-a")
    write_idea(studio, "scout-b", title="Another tool")
    body = client.get("/api/ideas").json()
    assert {i["id"] for i in body} == {"scout-a", "scout-b"} and all(i["status"] == "open" for i in body)
    r = client.post("/api/ideas/scout-a/start", json={})
    assert r.status_code == 200
    eid = r.json()["episode"]["id"]
    p = episodes.read(eid)
    assert p["show_format"] == "tool-test" and p["length"] == "long" and p["source"] == "https://example.com/t"
    assert p["title"] == "A free tool replaces a paid app"
    (args, kw) = client.added[-1]
    assert args[1:3] == ("scout", "idea") and kw["data"] == {"plan": 1} and "https://example.com/t" in args[3]
    assert ideas.get("scout-a")["status"] == "started" and ideas.get("scout-a")["episode"] == eid
    assert json.loads((studio / "inbox" / "ideas" / "scout-a.json").read_text())["episode"] == eid
    assert client.post("/api/ideas/scout-a/start", json={}).status_code == 400
    assert client.post("/api/ideas/scout-b/dismiss").json()["status"] == "dismissed"
    assert client.post("/api/ideas/nope/dismiss").status_code == 404
    assert client.get("/api/ideas?status=open").json() == []


def test_start_with_the_other_length_lets_the_scout_pick(client, studio):
    write_idea(studio, "scout-a")
    eid = client.post("/api/ideas/scout-a/start", json={"length": "short"}).json()["episode"]["id"]
    p = episodes.read(eid)
    assert p["kind"] == "short" and p["mode"] == "original" and "show_format" not in p


def test_a_failed_start_leaves_the_idea_open(crew, studio, monkeypatch):
    from crewcut.conductor import flow
    write_idea(studio, "scout-a")
    ideas.load()

    def boom(*a, **k):
        raise ValueError("no")
    monkeypatch.setattr(flow, "new_episode", boom)
    with pytest.raises(ValueError):
        ideas.start("scout-a")
    assert ideas.get("scout-a")["status"] == "open"
