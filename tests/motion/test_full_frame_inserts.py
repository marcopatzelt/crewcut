"""Every full-frame insert counts, whatever renders it: a 2D or 3D scene that fills the frame is a full-frame moment
in the density, a row of the motion plan, a gated render, a style frame next to a launch film frame, and a number in
the ratchet. A video of flat 2D windows can no longer pass as "2 motion moments"."""

from __future__ import annotations

import json

import pytest
from flow_helpers import image, install_shelf, make_episode, ready_plan

from crewcut import approvals, db
from crewcut.conductor import queue
from crewcut.motion import custom, density, director, dispatch, ratchet


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def shelf(studio):
    d = install_shelf(studio)
    scenes = studio / "brand" / "templates" / "2d"
    scenes.mkdir(parents=True, exist_ok=True)
    (scenes / "studio_window.html").write_text("<!doctype html><title>window</title>", encoding="utf-8")
    return d


def window(iid: str, start: float, end: float, **kw) -> dict:
    return {"id": iid, "kind": "2d", "scene": "headline", "start": start, "end": end, "data": {"text": "x"}, **kw}


def edit_plan(ep, *inserts, name: str = "plan-v001.json") -> dict:
    plan = {"words": "work/words-v001.json", "format": "landscape", "inserts": list(inserts)}
    (ep / "edit" / name).write_text(json.dumps(plan), encoding="utf-8")
    return plan


# ---------------------------------------------------------------- the density counts every full-frame graphic


def test_density_counts_2d_and_3d_full_frame_but_not_recordings_or_overlays():
    plan = {"format": "landscape", "inserts": [
        {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 10.0, "end": 14.0},
        window("w1", 20.0, 24.0), window("w2", 26.0, 29.0),                     # 2 s apart: no gap rule for 2D
        {"id": "s1", "kind": "3d", "scene": "box", "start": 40.0, "end": 44.0},
        {"id": "c1", "kind": "clip", "file": "broll/x.mp4", "start": 50.0, "end": 53.0},
        {"id": "k1", "kind": "2d", "scene": "keyword", "start": 60.0, "end": 62.0, "transparent": True},
        {"id": "k2", "kind": "2d", "scene": "keyword", "start": 64.0, "end": 66.0}]}
    rep = density.count(plan, [], density.limits({}), total_s=120.0)
    c = rep["counts"]
    assert c["big"] == 4 and c["big_by_kind"] == {"2d": 2, "3d": 1, "motion": 1}
    assert c["motion"] == 4 and c["motion_inserts"] == 1
    assert [m["id"] for m in rep["moments"]] == ["m1", "w1", "w2", "s1"]
    texts = [f["text"] for f in rep["findings"]]
    assert "4 full-frame inserts (2D 2, 3D 1, motion 1) (at most 5)" in texts
    assert not any("apart" in t for t in texts), "the 6 s gap stays a rule of motion inserts"
    assert density.kinds_text({"motion": 3}) == ""
    assert [e["id"] for e in density.full_frame_graphics(plan)] == ["m1", "w1", "w2", "s1"]


# ---------------------------------------------------------------- the motion plan has a row per full-frame picture


def _plan_with_window(eid: str) -> dict:
    p = ready_plan(eid)
    plan = director.load(p)
    plan["beats"][3].update(purpose="see the prompt", picture="the prompt types into a window", column="a",
                            piece="studio_window", params={}, length_s=4.0)
    p.write_text(json.dumps(plan))
    return plan


def test_a_2d_scene_row_counts_on_the_card_and_warns_as_a_slide(shelf):
    eid, ep = make_episode()
    _plan_with_window(eid)
    p, errors, warns = director.run_check(eid)
    assert errors == []
    plan = director.load(p)
    assert plan["density"]["line"].startswith("full-frame 3 of max ") and "(2D 1, motion 2)" in plan["density"]["line"]
    assert plan["density"]["counts"]["big_by_kind"] == {"2d": 1, "motion": 2}
    assert any("studio_window as the whole full-frame picture reads as a slide" in w for w in warns)
    assert "studio_window (2D)" in director.md_of(p).read_text()
    card = director.propose_card(eid)
    rows = card["data"]["motion_plan"]["columns"]["a"]
    assert {r["piece"]: r["render"] for r in rows} == {"number_roll": "motion", "studio_window": "2d"}
    assert card["title"].endswith("3 motion moments")


def test_a_quiet_beat_that_names_graphics_and_a_doubled_beat_number_fail(shelf):
    eid, _ep = make_episode()
    p = ready_plan(eid)
    plan = director.load(p)
    plan["beats"][0]["picture"] = "the 2D views: studio_window, then number_roll"
    plan["beats"][-1]["n"] = plan["beats"][-2]["n"]
    p.write_text(json.dumps(plan))
    _p, errors, _w = director.run_check(eid)
    assert any("column - leaves the beat to the speaker, but the picture names graphics (number_roll, "
               "studio_window)" in e for e in errors)
    assert any("appears twice" in e for e in errors)


def test_the_check_names_full_frame_inserts_of_the_edit_plan_without_a_row(shelf):
    eid, ep = make_episode()
    ready_plan(eid)
    edit_plan(ep, {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 3.5, "end": 7.5, "beat": 2,
                   "column": "a"}, window("w1", 20.0, 24.0), window("w2", 30.0, 33.0, beat=2, column="a"),
              window("k1", 40.0, 42.0, transparent=True))
    _p, _e, warns = director.run_check(eid)
    line = next(w for w in warns if "without a row in this plan" in w)
    assert line.startswith("plan-v001.json shows 1 full-frame picture(s) without a row in this plan: w1.")
    # w2 names a row; that it shares it with m1 is the gate's business (one row per full-frame insert)


def test_the_gate_wants_a_row_per_full_frame_insert_of_any_kind(shelf):
    eid, ep = make_episode()
    _plan_with_window(eid)
    card = director.propose_card(eid)
    approvals.decide(card["id"], True)
    roll = {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 3.5, "end": 7.5, "beat": 2, "column": "a"}
    ok = window("w1", 20.0, 24.0, scene="studio_window", beat=4, column="a")
    assert director.motion_gate(ep, {"inserts": [roll, ok]}) == []
    out = director.motion_gate(ep, {"inserts": [window("w2", 30.0, 33.0)]})
    assert out == ['w2: no beat and column; every full-frame 2D insert comes from a row of the approved motion plan '
                   '("beat": N, "column": "a", "b" or "c")']
    twice = director.motion_gate(ep, {"inserts": [ok, {**ok, "id": "w3", "start": 30.0, "end": 33.0}]})
    assert twice and twice[0].startswith("w3: beat 4 is already the row of w1")
    assert director.motion_gate(ep, {"inserts": [{**ok, "scene": "headline"}]}) == [
        "w1: it uses headline, beat 4 of motion plan v001 says studio_window"]
    overlay = window("k1", 40.0, 42.0, transparent=True)
    keyword = {"id": "k2", "kind": "2d", "scene": "keyword", "start": 50.0, "end": 52.0}
    clip = {"id": "c1", "kind": "clip", "file": "broll/x.mp4", "start": 60.0, "end": 62.0}
    assert director.motion_gate(ep, {"inserts": [overlay, keyword, clip]}) == []


# ---------------------------------------------------------------- every full-frame insert shows a style frame


def test_a_2d_insert_gets_a_style_frame_next_to_a_launch_film_frame(shelf, tmp_path):
    eid, ep = make_episode()
    edit_plan(ep, window("terminal-run", 20.0, 24.0, scene="studio_window"), window("rule-1", 30.0, 33.0),
              window("rule-2", 40.0, 43.0))
    assert "no style frame card yet" in custom.style_frame_gate(ep, "terminal-run")
    card = custom.style_frame(eid, "terminal-run", [str(image(tmp_path / "o.png"))])
    d = card["data"]
    assert d["shelf"] is True and d["piece"] == "2d" and d["scene"] == "studio_window" and d["covers"] == []
    fr = d["frames"][0]
    assert fr["launch_id"] == "prompt-meadow", "a terminal is compared with the launch film's prompt bar"
    assert fr["launch"] == "motion/terminal-run/refs/launch-prompt-meadow.jpg" and (ep / fr["launch"]).is_file()
    assert fr["launch_url"] == f"/api/files/{eid}/{fr['launch']}" and fr["launch_url"] in d["images"]
    assert d["images"][0] == fr["ours_url"]
    assert "next to the launch film" in card["body"]
    # one card may cover inserts that reuse the same piece; the yes opens all of them
    both = custom.style_frame(eid, "rule-1", [str(image(tmp_path / "o2.png"))], also=["rule-2"], launch="card-grid")
    assert both["data"]["covers"] == ["rule-2"] and both["data"]["frames"][0]["launch_id"] == "card-grid"
    assert both["title"] == "Style frame of rule-1, rule-2, round 1"
    assert f"card #{both['id']}" in custom.style_frame_gate(ep, "rule-2")
    approvals.decide(both["id"], True)
    assert custom.style_frame_gate(ep, "rule-1") is None and custom.style_frame_gate(ep, "rule-2") is None
    with pytest.raises(custom.CustomError, match="no such insert"):
        custom.style_frame(eid, "rule-1", [str(image(tmp_path / "o3.png"))], also=["nothing"])
    with pytest.raises(custom.CustomError, match="no launch film frame"):
        custom.style_frame(eid, "rule-1", [str(image(tmp_path / "o4.png"))], launch="nope")


def test_the_launch_film_frames_ship_with_the_app():
    frames = custom.launch_frames()["frames"]
    assert {f["id"] for f in frames} >= {"prompt-meadow", "card-grid", "word-reel", "type-3d", "end-lockup"}
    assert all((custom.launch_dir() / f["file"]).is_file() and f.get("shows") for f in frames)
    assert custom.launch_frame("m-20-to-4", "number_roll")["id"] == "type-3d"
    assert custom.launch_frame("role-1", "studio_role")["id"] == "card-grid"
    assert custom.launch_frame("x", None)["id"] == "card-grid"


def test_an_approved_shelf_style_frame_goes_to_the_editor_not_a_new_designer(crew, monkeypatch):
    from crewcut import episodes
    from crewcut.conductor import flow
    monkeypatch.setattr(flow, "post", lambda *a, **k: None)
    added = []
    monkeypatch.setattr(queue, "add", lambda *a, **k: added.append(a) or 7)
    eid = episodes.create("Shelf frames")["id"]
    jid = dispatch.dispatch({"id": 3, "episode": eid, "data": {"insert": "w1", "covers": ["w2"], "shelf": True}})
    assert jid == 0 and added == []
    assert db.kv_get(f"motion_assembly_pending:{eid}") == "1"
    dispatch.tick()
    assert [a[1] for a in added] == ["editor"]


# ---------------------------------------------------------------- the render waits, the ratchet counts


def test_render_2d_waits_for_the_row_and_the_style_frame(shelf, tmp_path, monkeypatch):
    from crewcut.render import html, workbench
    from crewcut.render.plan import Plan
    eid, ep = make_episode()
    _plan_with_window(eid)
    approvals.decide(director.propose_card(eid)["id"], True)
    edit_plan(ep, window("w1", 20.0, 24.0, scene="headline", beat=4, column="a"),
              window("k1", 40.0, 42.0, scene="keyword", transparent=True, data={"text": "Tage"}))
    plan = Plan(ep / "edit" / "plan-v001.json")
    monkeypatch.setattr(html, "render_2d", lambda *a, **k: [{"id": "w1", "frames_ok": True}])
    with pytest.raises(workbench.Waiting, match="w1: it uses headline, beat 4 of motion plan v001 says studio_window"):
        workbench.render_2d(plan)
    edit_plan(ep, window("w1", 20.0, 24.0, scene="studio_window", beat=4, column="a"))
    scenes = ep.parent.parent / "brand" / "templates" / "2d"
    (scenes / "studio_window.html").write_text("<!doctype html><title>window</title>", encoding="utf-8")
    for f in ("base.css", "motion.js", "scene.js"):
        (scenes / f).write_text("", encoding="utf-8")
    plan = Plan(ep / "edit" / "plan-v001.json")
    with pytest.raises(workbench.Waiting, match="w1: no style frame card yet"):
        workbench.render_2d(plan)
    assert workbench.render_2d(plan, gate=False) == [{"id": "w1", "frames_ok": True}]
    card = custom.style_frame(eid, "w1", [str(image(tmp_path / "o.png"))])
    with pytest.raises(workbench.Waiting, match=f"waiting for your yes on the style frame \\(card #{card['id']}\\)"):
        workbench.render_2d(plan)
    approvals.decide(card["id"], True)
    assert workbench.render_2d(plan) == [{"id": "w1", "frames_ok": True}]
    assert workbench.insert_gates(plan) == []


def test_the_ratchet_counts_every_full_frame_picture_and_the_slides(shelf):
    eid, ep = make_episode()
    edit_plan(ep, {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 3.5, "end": 7.5},
              window("w1", 20.0, 24.0), window("w2", 30.0, 33.0),
              {"id": "k1", "kind": "motion", "scene": "keyword_pop", "start": 40.0, "end": 42.0, "transparent": True})
    (ep / "review").mkdir(exist_ok=True)
    (ep / "review" / "cut-check-v001.json").write_text(json.dumps({"findings": [
        {"id": "slide:w1", "level": "ERROR"}, {"id": "slide:w2", "level": "ERROR"}, {"id": "slide:m1", "level": "OK"},
        {"id": "flash", "level": "ERROR"}]}))
    m = ratchet.measured(ep)
    assert m["full_frame"] == 3 and m["full_frame_by_kind"] == {"2d": 2, "motion": 1}
    assert m["motion_moments"] == 4 and m["overlays"] == 1
    assert m["slides"] == 2 and m["slide_check"] == "review/cut-check-v001.json"
    assert "slides" in ratchet.LOWER_IS_BETTER
    assert ratchet._never_down({"slides": 1}, {"slides": 3}) == ["slides 3 > 1"]
