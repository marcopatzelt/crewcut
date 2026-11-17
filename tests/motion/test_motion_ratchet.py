"""The quality ratchet (motion plan 3.8): the motion report with its lessons, the baseline card that moves the bar
only on a yes and never down, the references the user and the Scout file, and the library growing through use."""

from __future__ import annotations

import json

import pytest
from flow_helpers import bundle, image, install_shelf, make_episode, ready_plan

from crewcut import approvals, brand
from crewcut.conductor import queue
from crewcut.motion import custom, director, lessons, library, ratchet, references


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def shelf(studio):
    return install_shelf(studio)


def approved(eid: str) -> dict:
    ready_plan(eid)
    card = director.propose_card(eid)
    return approvals.decide(card["id"], True)


def edit_plan(ep, inserts=None):
    inserts = inserts or [
        {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 3.5, "end": 7.5, "beat": 2, "column": "a"},
        {"id": "m2", "kind": "motion", "source": "motion/m2/comp.jsx", "start": 12.0, "end": 17.0, "beat": 3,
         "column": "b"}]
    (ep / "edit" / "plan-v001.json").write_text(json.dumps({"words": "work/words-v001.json", "inserts": inserts}))


def data(better=True, n_lessons=1, strengths=3, baseline=True, behind_bar=False):
    return {
        "better": [{"what": "the number lands on the spoken word", "time": 7.2, "against": "numbers land heavy",
                    "frame": "review/motion-v001/m1/sheet.jpg"}] if better else [],
        "behind": [{"what": "the reference's exit is two frames faster", "against": "ref-001"}]
        + ([{"what": "the colours are flatter than the bar's", "against": "bar"}] if behind_bar else []),
        "upgrades": [{"id": "u1", "landed": True, "evidence": "0:12 the exit is caused by the card flip, "
                                                              "review/motion-v001/m2/strip-out.jpg"}],
        "pieces": [{"insert": "m1", "reference_better": "the reference's digits are heavier"}],
        "lessons": [{"rule": f"Lesson number {i}: exits are caused by a motion", "time": 12.0, "source": "review",
                     "frame": "review/motion-v001/m2/sheet.jpg"} for i in range(n_lessons)],
        "strengths": [{"name": f"strength {i}", "time": 7.0, "frame": f"review/motion-v001/m1/s{i}.jpg"}
                      for i in range(strengths)],
        "proposals": {"library": [{"insert": "m2", "name": "gpu_handoff", "why": "fits a second video"}],
                      "baseline": baseline},
    }


def first_bar(shelf_ok=True) -> str:
    """Episode 1 becomes the bar (its report is the first, the user says yes)."""
    eid, ep = make_episode("First video")
    approved(eid)
    edit_plan(ep)
    bundle(ep, "m1")
    r = ratchet.report(eid, data(better=False))
    assert r["verdict"] == "first" and r["baseline_card"]
    approvals.decide(r["baseline_card"], True)
    assert ratchet.bar()["episode"] == eid
    return eid


# ---------------------------------------------------------------- checks 1 and 2: the report and its lessons


def test_report_sections_and_better_or_back(shelf):
    bar_ep = first_bar()
    eid, ep = make_episode("Second video")
    approved(eid)
    edit_plan(ep)
    bundle(ep, "m1")
    r1 = ratchet.report(eid, data(better=False))
    assert r1["verdict"] == "back" and r1["file"] == "review/motion-report-v001.json"
    assert "baseline_card" not in r1, "a version that is not better never proposes a new bar"
    r2 = ratchet.report(eid, data(better=True))
    assert r2["verdict"] == "better" and r2["bar"] == bar_ep
    md = (ep / "review" / "motion-report-v002.md").read_text()
    for head in ("## Better", "## Behind", "## Upgrades landed", "## Proposals"):
        assert head in md
    assert "the number lands on the spoken word" in md and "u1 Every exit" in md and "landed" in md
    assert "no retention data" in md
    assert r2["summary"]["better"].startswith("the number lands") and r2["summary"]["next"]
    assert r2["measured"]["motion_moments"] == 2 and r2["measured"]["custom"] == 1
    assert r2["measured"]["upgrades_landed_share"] == 1.0
    # the third try after a "back" that is still not better: the Showrunner tells the user
    r3 = ratchet.report(eid, data(better=False))
    assert r3["verdict"] == "tell"
    # a strength of the bar that got worse sends it back too
    assert ratchet.report(eid, data(better=True, behind_bar=True))["verdict"] == "tell"


def test_report_fails_without_a_lesson_and_writes_nothing(shelf):
    eid, ep = make_episode()
    approved(eid)
    n = len(lessons.read())
    with pytest.raises(ratchet.ReportError, match="at least one lesson"):
        ratchet.report(eid, data(n_lessons=0))
    assert not list((ep / "review").glob("motion-report-*")) and len(lessons.read()) == n
    bad = data()
    bad["lessons"][0]["frame"] = ""
    with pytest.raises(ratchet.ReportError, match="frame"):
        ratchet.report(eid, bad)
    bad = data()
    bad["upgrades"] = []
    with pytest.raises(ratchet.ReportError, match="upgrade u1: say whether it landed"):
        ratchet.report(eid, bad)
    bad = data()
    bad["lessons"][0]["source"] = "retention"
    with pytest.raises(ratchet.ReportError, match="repeat in 3 videos"):
        ratchet.report(eid, bad)
    r = ratchet.report(eid, data(n_lessons=2))
    ids = [x["id"] for x in r["lessons"]]
    assert len(ids) == 2 and len(lessons.read()) == n + 2 and set(ids) <= lessons.ids()
    line = (brand.load().dir / "rules" / "motion.md").read_text().splitlines()[-1]
    assert line.startswith(f"- {ids[1][:10]}: [{ids[1]}] Lesson number 1") and "Evidence: " in line
    assert line.endswith("(source: review)") and "review/motion-v001/m2/sheet.jpg" in line
    assert brand.parse_rules(line)[0]["source"] == "review"
    # the next video's plan cites a lesson id, or the check warns
    eid2, _ep2 = make_episode("Next video")
    ready_plan(eid2)
    _p, _e, warns = director.run_check(eid2)
    assert any("no upgrade cites one" in w for w in warns)


def test_above_forty_lessons_a_merge_is_proposed(shelf):
    eid, ep = make_episode()
    approved(eid)
    for i in range(lessons.MERGE_ABOVE):
        lessons.append(f"rule {i}", {"episode": eid, "time": 1, "frame": "x.jpg"}, "review")
    r = ratchet.report(eid, data(baseline=False))
    assert r["proposals"]["merge_lessons"] and approvals.get(r["merge_card"])["data"]["motion_merge"] is True


# ---------------------------------------------------------------- check 6: the bar moves only on a yes, never down


def test_baseline_needs_the_yes_and_never_moves_down(shelf):
    bar_ep = first_bar()
    eid, ep = make_episode("Second video")
    approved(eid)
    edit_plan(ep)
    bundle(ep, "m1")
    r = ratchet.report(eid, data())
    card = approvals.get(r["baseline_card"])
    assert card["kind"] == "baseline" and card["status"] == "open"
    assert card["data"]["old"]["episode"] == bar_ep and card["data"]["new"]["episode"] == eid
    assert len(card["data"]["new"]["strengths"]) == 3
    assert ratchet.bar()["episode"] == bar_ep, "never moves silently"
    approvals.decide(card["id"], False, reason="not yet")
    assert ratchet.bar()["episode"] == bar_ep
    # a third video proposes while the second one's card is still open
    eid3, ep3 = make_episode("Third video")
    approved(eid3)
    edit_plan(ep3)
    bundle(ep3, "m1")
    stale = ratchet.report(eid3, data())["baseline_card"]
    second = ratchet.report(eid, data())["baseline_card"]
    approvals.decide(second, True)
    b = ratchet.bar()
    assert b["episode"] == eid and b["history"][-1]["episode"] == bar_ep and b["card"] == second
    assert b["strengths"][0]["name"] == "strength 0" and b["measured"]["motion_moments"] == 2
    # the card made against the old bar can no longer move it
    with pytest.raises(ValueError, match="The bar moved"):
        approvals.decide(stale, True)
    assert ratchet.bar()["episode"] == eid and approvals.get(stale)["status"] == "open"
    # a video that measures worse than the bar cannot become it
    bundle(ep3, "m1", errors=3, version=2)
    rep = ratchet.report(eid3, data(baseline=False))
    with pytest.raises(ratchet.ReportError, match="never moves down"):
        ratchet.propose_baseline(eid3, ep3 / rep["file"])
    assert ratchet.bar()["episode"] == eid


def test_a_changed_report_cannot_move_the_bar(shelf):
    first_bar()
    eid, ep = make_episode("Second video")
    approved(eid)
    edit_plan(ep)
    r = ratchet.report(eid, data())
    p = ep / r["file"]
    p.write_text(p.read_text().replace('"better"', '"better"', 1) + " ")
    with pytest.raises(ValueError, match="report changed"):
        approvals.decide(r["baseline_card"], True)
    assert ratchet.bar()["episode"] != eid


def test_the_bar_needs_three_to_six_strengths(shelf):
    eid, ep = make_episode()
    approved(eid)
    r = ratchet.report(eid, data(strengths=1, baseline=False))
    assert r["baseline_card"] is None and "3 to 6 named strengths" in r["baseline_refused"]
    with pytest.raises(ratchet.ReportError, match="3 to 6 named strengths"):
        ratchet.propose_baseline(eid, ep / r["file"])


# ---------------------------------------------------------------- check 3: references


def test_a_dropped_link_becomes_a_reference_with_the_users_sentence(studio, tmp_path):
    got = []

    def fake_download(url, dest):
        got.append(url)
        dest.mkdir(parents=True, exist_ok=True)
        f = dest / "reel.mp4"
        f.write_bytes(b"fake clip")
        return f

    eid, _ep = make_episode()
    rows = references.from_message(eid, "look at this reel, the number lands so heavy "
                                        "https://www.instagram.com/reel/abc123/", download=fake_download)
    assert got == ["https://www.instagram.com/reel/abc123/"]
    assert len(rows) == 1
    e = references.read()[0]
    assert e["id"] == "ref-001" and e["by"] == "user" and e["episode"] == eid
    assert e["reason"] == "look at this reel, the number lands so heavy"
    assert e["link"] == "https://www.instagram.com/reel/abc123/" and e["local_only"] is True
    assert (studio / "brand" / "references" / "motion" / e["file"]).read_bytes() == b"fake clip"
    # the same link again is not filed twice; no link, no entry
    assert references.from_message(eid, "again https://www.instagram.com/reel/abc123/", download=fake_download) == []
    assert references.from_message(eid, "no link here") == []
    # a dropped file
    clip = image(tmp_path / "still.png")
    f = references.add(str(clip), "the light from the top left", episode=eid, download=None)
    assert f["file"] == "files/ref-002.png" and f["source_name"] == "still.png"
    with pytest.raises(ValueError, match="needs a reason"):
        references.add("https://example.org/x", " ")


def test_the_scout_adds_a_few_per_video(studio):
    eid, _ep = make_episode()
    for i in range(references.SCOUT_PER_EPISODE):
        references.add(f"https://example.org/{i}", "a caused transition", by="scout", episode=eid, download=None)
    with pytest.raises(ValueError, match="at most 3"):
        references.add("https://example.org/9", "one more", by="scout", episode=eid, download=None)
    assert references.add("https://example.org/9", "the user's own", by="user", episode=eid, download=None)


# ---------------------------------------------------------------- check 4: the library grows through use


def test_the_library_grows_through_use(shelf, tmp_path):
    def render(template, fmt, params, out):
        out.write_bytes(b"sample")
        return {"poster": str(image(tmp_path / "poster.jpg"))}

    # video 1: one custom piece, reviewed clean, promoted, kept
    eid1, ep1 = make_episode("First video")
    brief = tmp_path / "brief.md"
    brief.write_text("Four jobs leave the laptop.\n")
    custom.new(eid1, "m2", brief)
    edit_plan(ep1)
    bundle(ep1, "m2")
    e = library.promote(eid1, "m2", "gpu_handoff", render)
    approvals.decide(e["card"], True)
    # video 2: uses the promoted piece with other params, and makes its own one-off
    eid2, ep2 = make_episode("Second video")
    approved(eid2)
    custom.new(eid2, "m9", brief)
    edit_plan(ep2, [
        {"id": "m1", "kind": "motion", "scene": "gpu_handoff", "start": 3.5, "end": 8.0, "beat": 2, "column": "a",
         "data": {}},
        {"id": "m9", "kind": "motion", "source": "motion/m9/comp.jsx", "start": 12.0, "end": 17.0, "beat": 3,
         "column": "b"}])
    bundle(ep2, "m1")
    ratchet.report(eid2, data(baseline=False))
    idx = library.read_index()["gpu_handoff"]
    assert idx["approved"]["by"] == "user" and idx["samples"]["landscape"].endswith("-landscape.mp4")
    assert idx["sample"].endswith(".jpg")
    assert [u["episode"] for u in library.uses("gpu_handoff")] == [eid2]
    assert any(f"used in {eid2} (m1): review 0 error(s)" in n["text"] for n in idx["notes"])
    rows = {r["name"]: r for r in library.entries()}
    assert rows[f"{eid2}/m9"]["origin"] == "episode" and rows[f"{eid2}/m9"]["promoted_as"] is None
    assert rows[f"{eid1}/m2"]["promoted_as"] == "gpu_handoff"
