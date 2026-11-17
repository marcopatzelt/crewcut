"""What the web UI and the crew read about the motion workflow: ``GET /api/episodes/{id}/motion``, the shelf and
the bar over HTTP, and the ``crewcut motion`` workflow commands (plan, library, new, style-frame, report,
reference, lessons)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from flow_helpers import bundle, image, install_shelf, make_episode, ready_plan

from crewcut import approvals
from crewcut.conductor import queue
from crewcut.motion import cli as mcli
from crewcut.motion import director


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def client(crew):
    from crewcut.server.app import create_app
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def test_motion_view_for_the_ui(studio, client, tmp_path):
    install_shelf(studio)
    eid, ep = make_episode()
    assert client.get(f"/api/episodes/{eid}/motion").json() == {"plan": None, "pieces": [], "report": None,
                                                               "retention": None}
    ready_plan(eid)
    card = director.propose_card(eid)
    v = client.get(f"/api/episodes/{eid}/motion").json()
    assert v["plan"]["version"] == 1 and v["plan"]["card"] == {"id": card["id"], "status": "open"}
    assert not v["plan"]["approved"] and set(v["plan"]["columns"]) == {"a", "b", "c"}
    assert v["plan"]["md_url"] == f"/api/files/{eid}/edit/motion-plan-v001.md"
    approvals.decide(card["id"], True)
    # a custom piece with its style frame, and the edit plan's inserts on the film strip
    brief = tmp_path / "b.md"
    brief.write_text("Four jobs leave the laptop.\n")
    assert mcli.main(["new", eid, "handoff", "--from", str(brief)]) == 0
    (ep / "edit" / "plan-v001.json").write_text(json.dumps({"inserts": [
        {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 3.5, "end": 7.5, "beat": 2, "column": "a"},
        {"id": "handoff", "kind": "motion", "source": "motion/handoff/comp.jsx", "start": 9, "end": 14, "beat": 3,
         "column": "b"}]}))
    frames = ep / "render" / "inserts" / "m1-0123456789"
    frames.mkdir(parents=True)
    image(frames / "0001.png")
    bundle(ep, "m1")
    v = client.get(f"/api/episodes/{eid}/motion").json()
    pieces = {p["id"]: p for p in v["pieces"]}
    assert pieces["m1"]["state"] == "done" and pieces["m1"]["poster"].endswith("/render/inserts/m1-0123456789/0001.png")
    assert pieces["handoff"]["kind"] == "custom" and pieces["handoff"]["state"] == "planned"
    assert pieces["handoff"]["brief"] == "Four jobs leave the laptop."
    lib = client.get("/api/motion/library").json()["templates"]
    assert {t["name"] for t in lib} >= {"number_roll", "keyword_pop", f"{eid}/handoff"}
    rat = client.get("/api/motion/ratchet").json()
    assert rat["bar"] is None and rat["lessons"] == [] and rat["references"] == []
    assert client.get("/api/motion/app/samples/../../../etc/passwd").status_code in (403, 404)
    assert client.get(f"/api/episodes/{eid}x/motion").status_code == 404


def test_needs_shows_the_pictures_a_motion_card_names(studio, tmp_path):
    from crewcut import media
    from crewcut.motion import custom
    eid, ep = make_episode()
    brief = tmp_path / "b.md"
    brief.write_text("A piece.\n")
    custom.new(eid, "m3", brief)
    card = custom.style_frame(eid, "m3", [str(image(tmp_path / "o.png"))], [str(image(tmp_path / "r.png"))])
    n = media.needs(eid)
    assert n["card"] == card["id"] and n["kind"] == "style-frame" and len(n["images"]) == 2


def test_cli_plan_check_card(studio, capsys):
    install_shelf(studio)
    eid, ep = make_episode()
    assert mcli.main(["plan", eid]) == 0
    out = capsys.readouterr().out
    assert "edit/motion-plan-v001.json:" in out and "Writer mark(s)" in out and "number_roll" in out
    assert mcli.main(["plan", eid, "--check"]) == 1
    assert "error: beat 1: say what the viewer must understand" in capsys.readouterr().out
    ready_plan(eid)
    assert mcli.main(["plan", eid, "--check", "--card"]) == 0
    out = capsys.readouterr().out
    assert "0 error(s)" in out and "card #" in out and "GPU about $0.30, cap $2" in out
    assert mcli.main(["--json", "library"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["name"] for r in rows} >= {"number_roll", "keyword_pop"}


def test_cli_report_skeleton_then_from(studio, capsys):
    install_shelf(studio)
    eid, ep = make_episode()
    ready_plan(eid)
    approvals.decide(director.propose_card(eid)["id"], True)
    assert mcli.main(["report", eid, "--skeleton"]) == 0
    form = ep / "review" / "motion-report-input.json"
    d = json.loads(form.read_text())
    assert [u["id"] for u in d["upgrades"]] == ["u1"] and d["bar"] is None
    assert mcli.main(["report", eid, "--from", "review/motion-report-input.json"]) == 1
    assert "at least one lesson" in capsys.readouterr().err
    d["upgrades"][0].update(landed=True, evidence="0:12 frame review/x.jpg")
    d["lessons"] = [{"rule": "Numbers land on the spoken word", "time": "0:07", "frame": "review/x.jpg",
                     "source": "review"}]
    form.write_text(json.dumps(d))
    assert mcli.main(["report", eid, "--from", "review/motion-report-input.json"]) == 0
    out = capsys.readouterr().out
    assert "review/motion-report-v001.json: the first motion report" in out and "lessons: " in out
    assert mcli.main(["lessons"]) == 0
    assert "Numbers land on the spoken word" in capsys.readouterr().out


def test_cli_reference_and_style_frame(studio, capsys, tmp_path):
    eid, _ep = make_episode()
    assert mcli.main(["reference", "add", "https://example.org/reel", "--reason", "the cut is caused by a click",
                      "--no-download"]) == 0
    assert "ref-001: https://example.org/reel (link only)" in capsys.readouterr().out
    assert mcli.main(["reference", "list"]) == 0
    assert "ref-001" in capsys.readouterr().out
    brief = tmp_path / "b.md"
    brief.write_text("A piece.\n")
    assert mcli.main(["new", eid, "m3", "--from", str(brief)]) == 0
    capsys.readouterr()
    assert mcli.main(["style-frame", eid, "m3", "--ours", str(image(tmp_path / "o.png"))]) == 0
    assert "card #" in capsys.readouterr().out
    assert mcli.main(["promote", eid, "m3", "--name", "piece_one"]) == 1
    assert "no Critic bundle" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["motion-plan", "style-frame", "template", "baseline"])
def test_motion_cards_only_come_from_their_commands(studio, capsys, kind):
    from crewcut import cli
    eid, _ep = make_episode()
    rc = cli.main(["card", "propose", "--episode", eid, "--kind", kind, "--title", "x", "--data",
                   '{"new": {"episode": "' + eid + '"}}'])
    assert rc == 2 and "Motion cards come from their commands" in capsys.readouterr().err
    assert approvals.list_cards(episode=eid) == []
