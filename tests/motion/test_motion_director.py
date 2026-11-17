"""The motion pass (motion plan 3.1): the plan skeleton from the words and the Writer's marks, its validation, the
computed density and budget lines, the motion-plan card with its three columns and struck rows, and the gate the
render path calls."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from flow_helpers import install_shelf, make_episode, ready_plan

from crewcut import approvals, paths
from crewcut.conductor import queue
from crewcut.motion import director, lessons, marks

APP = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def shelf(studio):
    return install_shelf(studio)


def checked(eid, p=None):
    _p, errors, warns = director.run_check(eid, p)
    return errors, warns


# ---------------------------------------------------------------- check 1: skeleton and validation


def test_skeleton_from_words_marks_and_shelf(shelf):
    eid, ep = make_episode()
    p = director.skeleton(eid)
    assert p.name == "motion-plan-v001.json" and director.md_of(p).is_file()
    plan = director.load(p)
    assert plan["words"] == "work/words-v001.json" and plan["script"] == "brief/SCRIPT-v001.md"
    assert len(plan["beats"]) >= 3
    assert all(b["purpose"] == "" and b["column"] == "" for b in plan["beats"])
    assert plan["beats"][0]["says"].startswith("This video shows")
    # the Writer's marks come from below the --- line and land on their beats
    assert [m["what"] for m in plan["marks"]] == ["number", "handoff"]
    assert all(m["beat"] for m in plan["marks"])
    assert any(b["wish"] and "thirty cents" in b["wish"] for b in plan["beats"])
    # the shelf is listed, with the pack's stand-ins
    assert {r["name"] for r in plan["shelf"]} >= {"number_roll", "keyword_pop"}
    assert plan["cap_usd"] == 2.0 and len(plan["upgrades"]) == 2
    md = director.md_of(p).read_text()
    for head in ("## Beats", "## (a) What we have that fits", "## (b) What we build new for this video",
                 "## (c) What would make this video clearly better than the last one", "## Budget and density"):
        assert head in md
    assert "full-frame 0 of max" in md and "cap $2" in md


def test_short_skeleton_has_the_short_cap(shelf):
    eid, _ep = make_episode()
    plan = director.load(director.skeleton(eid, short=True))
    assert plan["short"] is True and plan["format"] == "portrait" and plan["cap_usd"] == 0.5


def test_skeleton_needs_the_words(shelf):
    from crewcut import episodes
    eid = episodes.create("No words yet")["id"]
    with pytest.raises(director.PlanError, match="words"):
        director.skeleton(eid)


def test_unfilled_rows_fail_with_purpose_picture_column(shelf):
    eid, _ep = make_episode()
    director.skeleton(eid)
    errors, _w = checked(eid)
    assert any("beat 1: say what the viewer must understand" in e for e in errors)
    assert any("beat 1: describe the picture" in e for e in errors)
    assert any("beat 1: column must be a, b, c or -" in e for e in errors)


def test_filled_plan_passes_and_lines_are_computed_not_typed(shelf):
    eid, ep = make_episode()
    p = ready_plan(eid)
    plan = director.load(p)
    plan["density"] = {"line": "typed by hand: full-frame 0"}
    plan["budget"] = {"line": "free", "estimate_usd": 0, "cap_usd": 99}
    p.write_text(json.dumps(plan))
    errors, warns = checked(eid)
    assert errors == []
    plan = director.load(p)
    assert plan["density"]["line"].startswith("full-frame 2 of max ")
    assert "all motion 2 in " in plan["density"]["line"]
    assert plan["budget"]["line"] == "GPU about $0.30, cap $2" and plan["budget"]["cap_usd"] == 2.0
    md = director.md_of(p).read_text()
    assert "typed by hand" not in md and "GPU about $0.30, cap $2" in md
    assert '| 3 | ' in md and 'custom "handoff", 1 plate' in md and "number_roll {value: 30, unit: cents}" in md


def test_a_plan_without_a_chosen_upgrade_fails_with_one_sentence(shelf):
    eid, _ep = make_episode()
    ready_plan(eid, chosen=False)
    errors, _w = checked(eid)
    assert director.NO_UPGRADE in errors
    assert director.NO_UPGRADE.count(".") == 1


def test_upgrades_need_two_to_four_candidates_with_a_source(shelf):
    eid, _ep = make_episode()
    p = ready_plan(eid)
    plan = director.load(p)
    plan["upgrades"][1]["source"] = {"kind": "", "ref": ""}
    p.write_text(json.dumps(plan))
    errors, _w = checked(eid)
    assert any(e.startswith("upgrade u2: name its source") for e in errors)
    plan["upgrades"] = plan["upgrades"][:1]
    p.write_text(json.dumps(plan))
    errors, _w = checked(eid)
    assert any("column (c) holds 2 to 4 candidates; it has 1" in e for e in errors)


def test_lessons_exist_and_none_cited_warns_then_citing_clears_it(shelf):
    eid, _ep = make_episode()
    lesson = lessons.append("Every exit is caused by a motion", {"episode": "000-old", "time": 72,
                                                                  "frame": "review/motion-v002/m3/sheet.jpg"}, "review")
    ready_plan(eid)
    _e, warns = checked(eid)
    assert any("lessons exist" in w and "no upgrade cites one" in w for w in warns)
    ready_plan(eid, lesson=lesson["id"])
    errors, warns = checked(eid)
    assert errors == [] and not any("lessons exist" in w for w in warns)


def test_every_beat_with_motion_and_a_template_as_picture_are_refused(shelf):
    eid, _ep = make_episode()
    p = ready_plan(eid)
    plan = director.load(p)
    plan["beats"][1]["picture"] = "number_roll"
    for b in plan["beats"]:
        if b["column"] == "-":
            b.update(column="a", piece="keyword_pop", length_s=2.0, picture="two words pop beside the face")
    p.write_text(json.dumps(plan))
    errors, _w = checked(eid)
    assert "every beat has motion: leave the beats the speaker carries without it" in errors
    assert "beat 2: the picture only names a template; say what happens on screen first" in errors


def test_cost_over_the_cap_is_an_error(shelf):
    eid, _ep = make_episode()
    p = ready_plan(eid)
    plan = director.load(p)
    plan["new"][0]["cost_usd"] = 2.5
    p.write_text(json.dumps(plan))
    errors, _w = checked(eid)
    assert any("over the cap $2" in e for e in errors)


# ---------------------------------------------------------------- check 3: the card, its columns, striking a row


@pytest.fixture
def client(crew):
    from crewcut.server.app import create_app
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def test_card_shows_three_columns_and_striking_writes_a_new_version(shelf, client):
    eid, ep = make_episode()
    ready_plan(eid)
    card = director.propose_card(eid)
    assert card["kind"] == "motion-plan" and card["file"] == "edit/motion-plan-v001.md"
    mp = card["data"]["motion_plan"]
    assert [r["piece"] for r in mp["columns"]["a"]] == ["number_roll"]
    assert [r["id"] for r in mp["columns"]["b"]] == ["handoff"] and mp["columns"]["b"][0]["beats"][0]["beat"] == 3
    assert [r["id"] for r in mp["columns"]["c"]] == ["u1", "u2"]
    assert mp["quiet"] and mp["density"].startswith("full-frame 2") and mp["cap_usd"] == 2.0
    # tap to strike the shelf row: a new plan version, the same card points at it
    r = client.post(f"/api/cards/{card['id']}/strike", json={"row": "beat:2"})
    assert r.status_code == 200, r.text
    c2 = r.json()
    assert c2["id"] == card["id"] and c2["status"] == "open" and c2["file"] == "edit/motion-plan-v002.md"
    v2 = director.load(ep / "edit" / "motion-plan-v002.json")
    assert v2["beats"][1]["struck"] is True and v2["based_on"] == "motion-plan-v001.json"
    assert v2["struck_rows"] == ["beat:2"]
    assert c2["data"]["motion_plan"]["columns"]["a"][0]["struck"] is True
    assert "~~" in (ep / "edit" / "motion-plan-v002.md").read_text()
    assert (ep / "edit" / "motion-plan-v001.json").is_file(), "the old version stays"
    # the only chosen upgrade cannot be struck
    r = client.post(f"/api/cards/{card['id']}/strike", json={"row": "upgrade:u1"})
    assert r.status_code == 409 and "only chosen upgrade" in r.json()["detail"]
    # striking a new piece strikes its beat too
    r = client.post(f"/api/cards/{card['id']}/strike", json={"row": "new:handoff"})
    v3 = director.load(ep / "edit" / "motion-plan-v003.json")
    assert r.status_code == 200 and v3["new"][0]["struck"] and v3["beats"][2]["struck"]
    # the yes approves exactly the version the card shows
    acc = client.post(f"/api/cards/{card['id']}/accept").json()
    assert acc["status"] == "accepted"
    assert client.post(f"/api/cards/{card['id']}/strike", json={"row": "beat:2", "struck": False}).status_code == 409


def test_a_changed_plan_json_cannot_be_approved(shelf):
    eid, ep = make_episode()
    p = ready_plan(eid)
    card = director.propose_card(eid)
    plan = director.load(p)
    plan["beats"][0]["picture"] = "something else"
    p.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="changed after this card"):
        approvals.decide(card["id"], True)
    assert approvals.get(card["id"])["status"] == "open"


# ---------------------------------------------------------------- check 2: the gate for `crewcut render plan`


def _edit_plan(*inserts):
    return {"format": "landscape", "inserts": list(inserts)}


M_A = {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 7.0, "end": 11.0, "beat": 2, "column": "a"}
M_B = {"id": "m2", "kind": "motion", "source": "motion/handoff/comp.jsx", "start": 12.0, "end": 17.0, "beat": 3,
       "column": "b"}


def test_gate_refuses_motion_without_an_approved_row(shelf):
    eid, ep = make_episode()
    assert director.motion_gate(ep, _edit_plan({"id": "k1", "kind": "2d", "scene": "keyword"})) == []
    out = director.motion_gate(ep, _edit_plan({**M_A, "beat": None}))
    assert out and "no beat and column" in out[0]
    out = director.motion_gate(ep, _edit_plan(M_A))
    assert out and "no approved motion plan" in out[0]
    ready_plan(eid)
    card = director.propose_card(eid)
    # while the card is open: column a may be built, b waits
    out = director.motion_gate(ep, _edit_plan(M_A, M_B))
    assert out == [f"m2: column b waits for your yes on the motion plan card #{card['id']} (only shelf pieces, "
                   "column a, may be built meanwhile)"]
    approvals.decide(card["id"], True)
    assert director.motion_gate(ep, _edit_plan(M_A, M_B)) == []
    # rows that do not match are refused
    assert "says number_roll" in director.motion_gate(ep, _edit_plan({**M_A, "scene": "keyword_pop"}))[0]
    assert "has a for beat 2" in director.motion_gate(ep, _edit_plan({**M_A, "column": "b"}))[0]
    assert "beat 9 is not in motion plan v001" in director.motion_gate(ep, _edit_plan({**M_A, "beat": 9}))[0]
    # a plan changed after the yes is not trusted
    p = ep / "edit" / "motion-plan-v001.json"
    p.write_text(p.read_text().replace("believe the number", "believe it"))
    assert "changed after card" in director.motion_gate(ep, _edit_plan(M_A))[0]


def test_gate_refuses_a_struck_row(shelf):
    eid, ep = make_episode()
    ready_plan(eid)
    card = director.propose_card(eid)
    director.strike(card["id"], "beat:2")
    approvals.decide(card["id"], True)
    assert director.motion_gate(ep, _edit_plan(M_A)) == ["m1: beat 2 was struck on the card"]


def test_a_new_card_replaces_the_open_one(shelf):
    eid, _ep = make_episode()
    ready_plan(eid)
    first = director.propose_card(eid)
    ready_plan(eid)
    second = director.propose_card(eid)
    assert approvals.get(first["id"])["status"] == "declined" and second["status"] == "open"


# ---------------------------------------------------------------- check 4 as data: the demo plan


def test_demo_plan_leaves_a_beat_without_motion_and_names_pictures_first(studio):
    install_shelf(studio)
    ep = paths.episodes_dir() / "demo"
    shutil.copytree(APP / "examples" / "demo", ep)
    p = ep / "edit" / "motion-plan-v001.json"
    plan = director.load(p)
    errors, _w = director.check(plan, ep)
    assert errors == []
    quiet = [b for b in plan["beats"] if b["column"] == "-"]
    assert quiet, "at least one beat is deliberately left without motion"
    shelf_names = {"number_roll", "keyword_pop"}
    for b in director.moving(plan):
        assert b["picture"] and b["picture"].split()[0] not in shelf_names
    assert any(u["chosen"] for u in plan["upgrades"])
    assert director.md_of(p).is_file()


# ---------------------------------------------------------------- the Writer's marks


def test_marks_are_parsed_below_the_line_only():
    text = "Spoken words.\n[[motion: number | \"x\"]]\n---\n[[motion: number | \"thirty cents\"]]\n" + \
           "".join(f"[[motion: word | \"w{i}\"]]\n" for i in range(5))
    found = marks.parse(text)
    assert found[0] == {"n": 1, "what": "number", "quote": "thirty cents", "line": 4}
    probs = marks.problems(text)
    assert any("in the spoken text" in x for x in probs) and any("6 motion marks; at most 5" in x for x in probs)
    assert marks.parse("No line here [[motion: a | \"b\"]]") == []


def test_the_new_card_kinds_are_known():
    assert set(approvals.MOTION_KINDS) <= set(approvals.KINDS)
    assert approvals.MOTION_KINDS == ("motion-plan", "style-frame", "template", "baseline")
