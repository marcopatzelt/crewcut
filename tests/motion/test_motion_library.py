"""The motion shelf and the user's library (motion plan 3.6): listing app, pack and episode pieces, versions and pins,
promotion of a reviewed custom piece (3.3 check 7) with a fake sample renderer, and the template card."""

from __future__ import annotations

import json
import shutil

import pytest
from flow_helpers import bundle, image, install_shelf, make_episode, template_src

from crewcut import approvals, doctor
from crewcut.conductor import queue
from crewcut.motion import custom, library
from crewcut.motion import templates as tp

COMP = """/* @template handoff
 * @description Four jobs leave the laptop, a card lights up, frames come back.
 * @kind full
 * @formats ["landscape", "portrait"]
 * @version 1
 * @params {"comp": "Main", "jobs": 4, "label": "GPU", "landAt": 1.2}
 * @end */
function handoff(P) {
  var F = CC.frame(), f = CC.font("display");
  var chip = EC.footage(P.comp, EC_ASSETS + "/chip.png", {name: "chip"});
  var t = EC.text(P.comp, {text: P.label, font: f.font, style: f.style, size: CC.px(140), fill: CC.ink()});
  return {comp: P.comp, layers: [chip, t], jobs: P.jobs};
}
"""


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / "app-templates"
    shutil.copytree(tp.app_dir() / "lib", d / "lib")
    monkeypatch.setattr(tp, "app_dir", lambda: d)
    return d


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def __call__(self, template, fmt, params, out):
        self.calls.append((template.name, fmt, params))
        out.write_bytes(b"\x00\x00\x00\x18ftypisom fake sample")
        poster = image(out.with_name(out.stem + "-poster.jpg"))
        return {"poster": str(poster)}


def _piece(eid, tmp_path, src=COMP, plan_data=None):
    brief = tmp_path / "brief.md"
    brief.write_text("Four jobs leave the laptop.\n")
    d = custom.new(eid, "handoff", brief)
    (d / "comp.jsx").write_text(src)
    (d / "assets").mkdir()
    image(d / "assets" / "chip.png", (40, 40))
    (d / "plates").mkdir()
    (d / "plates" / "gpu3d.py").write_text("# plate\n")
    ep = d.parent.parent
    plan = {"words": "work/words-v001.json", "inserts": [
        {"id": "handoff", "kind": "motion", "source": "motion/handoff/comp.jsx", "start": 9, "end": 14,
         "beat": 3, "column": "b", "data": plan_data if plan_data is not None else {"jobs": 4, "label": "GPU"}}]}
    (ep / "edit" / "plan-v001.json").write_text(json.dumps(plan))
    return d, ep


# ---------------------------------------------------------------- the shelf


def test_listing_shows_app_pack_and_episode_pieces(studio, app_dir, tmp_path):
    (app_dir / "number_roll.jsx").write_text(template_src("number_roll", params={"comp": "Main", "value": "0"}))
    (app_dir / "lower_third.jsx").write_text(template_src("lower_third", kind="overlay"))
    (app_dir / "samples").mkdir()
    (app_dir / "samples" / "lower_third-v1-landscape.mp4").write_bytes(b"x")
    (app_dir / "samples" / "lower_third-v1.jpg").write_bytes(b"x")
    pack = install_shelf(studio)
    eid, _ep = make_episode()
    brief = tmp_path / "b.md"
    brief.write_text("A piece.\n")
    custom.new(eid, "m3", brief)
    rows = {(r["origin"], r["name"]): r for r in library.entries()}
    assert ("pack", "number_roll") in rows and rows[("app", "number_roll")]["overridden"] is True
    assert ("pack", "keyword_pop") in rows and ("episode", f"{eid}/m3") in rows
    lt = rows[("app", "lower_third")]
    assert lt["samples"]["landscape"] == "/api/motion/app/samples/lower_third-v1-landscape.mp4"
    assert lt["samples"]["poster"] == "/api/motion/app/samples/lower_third-v1.jpg"
    assert library.shelf_names()["number_roll"]["path"] == str(pack / "number_roll.jsx")
    text = "\n".join(library.line(r) for r in library.entries())
    assert "yours" in text and "app" in text and "episode" in text


def test_resolve_version_and_pins(studio):
    d = install_shelf(studio, names=[])
    (d / "gpu_handoff.jsx").write_text(template_src("gpu_handoff", version=2))
    (d / "gpu_handoff.v1.jsx").write_text(template_src("gpu_handoff", version=1))
    (d / "plain.jsx").write_text(template_src("plain", version=None))
    assert library.resolve_version("gpu_handoff") == d / "gpu_handoff.jsx"
    assert library.resolve_version("gpu_handoff", 1) == d / "gpu_handoff.v1.jsx"
    assert library.resolve_version("gpu_handoff@1") == d / "gpu_handoff.v1.jsx"
    assert library.resolve_version("gpu_handoff@2") == d / "gpu_handoff.jsx"
    assert library.resolve_version("plain", 1) == d / "plain.jsx", "no @version counts as 1"
    with pytest.raises(tp.TemplateError, match="gpu_handoff@3"):
        library.resolve_version("gpu_handoff", 3)
    names = [r["name"] for r in library.entries(include_episodes=False)]
    assert names.count("gpu_handoff") == 1, "an old version is not a second template"


# ---------------------------------------------------------------- promotion


def test_promote_refuses_without_a_clean_review(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    _d, ep = _piece(eid, tmp_path)
    with pytest.raises(library.LibraryError, match="no Critic bundle"):
        library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    bundle(ep, "handoff", errors=2)
    with pytest.raises(library.LibraryError, match="2 error"):
        library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    bundle(ep, "handoff", errors=0, version=2)
    with pytest.raises(library.LibraryError, match="not connected"):
        library.promote(eid, "handoff", "gpu_handoff", None)
    with pytest.raises(library.LibraryError, match="lower case"):
        library.promote(eid, "handoff", "GPU", FakeRenderer())
    (app_dir / "taken.jsx").write_text(template_src("taken"))
    with pytest.raises(library.LibraryError, match="the app already has"):
        library.promote(eid, "handoff", "taken", FakeRenderer())


def test_promote_refuses_episode_values(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    src = COMP.replace("text: P.label", 'text: "about thirty cents"')
    _d, ep = _piece(eid, tmp_path, src=src, plan_data={"jobs": 4, "speed": 2})
    bundle(ep, "handoff")
    with pytest.raises(library.LibraryError) as e:
        library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    msg = str(e.value)
    assert "'about thirty cents' is spoken in this episode" in msg
    assert "the plan gives 'speed'" in msg
    assert not (studio / "brand" / "templates" / "motion" / "gpu_handoff.jsx").exists()


def test_promote_makes_a_template_a_second_plan_can_use(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    d, ep = _piece(eid, tmp_path)
    before = (d / "comp.jsx").read_text()
    bundle(ep, "handoff")
    fake = FakeRenderer()
    e = library.promote(eid, "handoff", "gpu_handoff", fake, title="GPU hand-off")
    pack = studio / "brand" / "templates" / "motion"
    src = (pack / "gpu_handoff.jsx").read_text()
    h = tp.parse_header(src)
    assert h["name"] == "gpu_handoff" and h["version"] == 1 and "function gpu_handoff(" in src
    assert 'EC_ASSETS + "/gpu_handoff/chip.png"' in src
    assert (pack / "assets" / "gpu_handoff" / "chip.png").is_file()
    assert (pack / "plates" / "gpu_handoff_gpu3d.py").is_file()
    assert (d / "comp.jsx").read_text() == before, "the episode's piece stays as it is"
    # samples: every claimed format with the defaults, and once more with every text twice as long
    assert [(c[1], c[2]["label"]) for c in fake.calls] == [("landscape", "GPU"), ("landscape", "GPU GPU"),
                                                          ("portrait", "GPU"), ("portrait", "GPU GPU")]
    assert e["samples"] == {"landscape": "samples/gpu_handoff-v1-landscape.mp4",
                            "portrait": "samples/gpu_handoff-v1-portrait.mp4"}
    assert e["sample"] == "samples/gpu_handoff-v1.jpg" and (pack / e["sample"]).is_file()
    assert not list(pack.glob(".stage-*")) and not list(pack.glob("check-*"))
    idx = library.read_index()["gpu_handoff"]
    assert idx["made_from"] == {"episode": eid, "insert": "handoff"} and idx["approved"] is None
    assert idx["sha256"] == library.sha256(pack / "gpu_handoff.jsx") and idx["needs_plates"] is True
    assert idx["engine_pin"] == doctor.read_pin() and idx["review"]["errors"] == 0
    assert idx["params"] == {"comp": "Main", "jobs": 4, "label": "GPU", "landAt": 1.2}
    card = approvals.get(e["card"])
    assert card["kind"] == "template" and card["status"] == "open"
    t = card["data"]["template"]
    assert t["name"] == "gpu_handoff" and t["version"] == 1 and t["samples"]["portrait"].endswith("-portrait.mp4")
    assert t["poster"] == "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v1.jpg"
    # a second plan uses it with other params, without touching the .jsx
    sha = library.sha256(pack / "gpu_handoff.jsx")
    code, merged = tp.program("gpu_handoff", {"jobs": 7, "label": "Render queue"})
    assert merged["jobs"] == 7 and '"label": "Render queue"' in code
    assert library.sha256(pack / "gpu_handoff.jsx") == sha
    rows = {r["name"]: r for r in library.entries()}
    assert rows["gpu_handoff"]["origin"] == "pack" and "waiting for your yes" in library.line(rows["gpu_handoff"])
    assert rows[f"{eid}/handoff"]["promoted_as"] == "gpu_handoff"


def test_template_card_yes_versions_and_no(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    d, ep = _piece(eid, tmp_path)
    bundle(ep, "handoff")
    e1 = library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    approvals.decide(e1["card"], True)
    idx = library.read_index()["gpu_handoff"]
    assert idx["approved"]["by"] == "user" and idx["approved"]["card"] == e1["card"]
    v1_sha = idx["sha256"]
    # a changed piece becomes version 2; version 1 is kept and a pinned plan still finds it
    (d / "comp.jsx").write_text(COMP.replace("CC.px(140)", "CC.px(150)"))
    e2 = library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    pack = studio / "brand" / "templates" / "motion"
    assert e2["version"] == 2 and (pack / "gpu_handoff.v1.jsx").is_file()
    assert library.sha256(pack / "gpu_handoff.v1.jsx") == v1_sha
    assert tp.parse_header(library.resolve_version("gpu_handoff@1").read_text())["version"] == 1
    assert tp.parse_header(library.resolve_version("gpu_handoff").read_text())["version"] == 2
    hist = library.read_index()["gpu_handoff"]["history"]
    assert [x["version"] for x in hist] == [1] and hist[0]["approved"]["by"] == "user"
    # no on version 2: it leaves, version 1 comes back
    approvals.decide(e2["card"], False, reason="keep the old one")
    assert library.sha256(pack / "gpu_handoff.jsx") == v1_sha and not (pack / "gpu_handoff.v1.jsx").exists()
    idx = library.read_index()["gpu_handoff"]
    assert idx["version"] == 1 and idx["approved"]["by"] == "user" and idx["history"] == []


def test_template_card_refuses_a_changed_file(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    _d, ep = _piece(eid, tmp_path)
    bundle(ep, "handoff")
    e = library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    p = studio / "brand" / "templates" / "motion" / "gpu_handoff.jsx"
    p.write_text(p.read_text() + "\n// changed\n")
    with pytest.raises(ValueError, match="changed after this card"):
        approvals.decide(e["card"], True)
    assert library.read_index()["gpu_handoff"]["approved"] is None


def test_a_first_promotion_declined_leaves_no_trace(studio, app_dir, tmp_path):
    eid, _ep = make_episode()
    _d, ep = _piece(eid, tmp_path)
    bundle(ep, "handoff")
    e = library.promote(eid, "handoff", "gpu_handoff", FakeRenderer())
    approvals.decide(e["card"], False)
    pack = studio / "brand" / "templates" / "motion"
    assert not (pack / "gpu_handoff.jsx").exists() and "gpu_handoff" not in library.read_index()
    assert not (pack / "assets" / "gpu_handoff").exists() and not list((pack / "plates").glob("gpu_handoff_*"))
