"""The identity gate, the control variant, finalists and the references each variant was made from."""

import json
import types

import numpy as np
import pytest
from PIL import Image
from test_thumbnail_variety import LIB, _round, plan

from crewcut import approvals, episodes, paths
from crewcut.thumbnail import identity, make, variety


def fake_embed(table):
    """An embedder that reads the face from the file name: 'marco*' is the person, 'lookalike*' is not."""
    vecs = {"marco": np.array([1.0, 0.0, 0.0]), "lookalike": np.array([0.3, 0.95, 0.0]), "none": None}

    def embed(path):
        key = next((k for k in table if k in str(path)), None)
        v = vecs[table[key]] if key else vecs["marco"]
        return (None, {"faces": 0}) if v is None else (v / np.linalg.norm(v), {"faces": 1})
    return embed


def test_threshold_sits_in_the_gap_or_above_every_lookalike():
    t = identity.threshold([0.70, 0.85, 0.79], [0.17, 0.34, 0.24])
    assert t["separated"] and t["min_similarity"] == round((0.34 + 0.70) / 2, 3)
    assert t["positives_rejected"] == 0 and t["negatives_accepted"] == 0
    overlap = identity.threshold([0.40, 0.80], [0.45, 0.20])
    assert not overlap["separated"] and overlap["min_similarity"] == 0.46
    assert overlap["negatives_accepted"] == 0 and overlap["positives_rejected"] == 1
    with pytest.raises(ValueError):
        identity.threshold([], [0.2])


def test_gate_passes_the_person_and_fails_a_lookalike(tmp_path):
    embed = fake_embed({"lookalike": "lookalike", "empty": "none"})
    gate = identity.Gate([tmp_path / "marco-photo.jpg", tmp_path / "marco-frame.jpg"], 0.6, embed)
    assert gate.measure(tmp_path / "A.png")["ok"]
    bad = gate.measure(tmp_path / "lookalike.png")
    assert not bad["ok"] and "not the person" in bad["problem"] and bad["similarity"] < 0.6
    assert gate.measure(tmp_path / "empty.png")["problem"] == "no face found"


def test_gate_needs_a_face_in_the_references(tmp_path):
    with pytest.raises(identity.Unavailable):
        identity.Gate([tmp_path / "empty.jpg"], 0.5, fake_embed({"empty": "none"}))


def test_set_check_rejects_a_wrong_face_and_records_it(tmp_path):
    root = _round(tmp_path / "r")
    gate = identity.Gate([tmp_path / "marco.jpg"], 0.6, fake_embed({"/C/": "lookalike"}))
    res = variety.check_round(root, LIB, gate=gate)
    assert not res["ok"] and res["redo"] == ["C"]
    assert res["identity"]["A"]["ok"] and not res["identity"]["C"]["ok"]
    assert any(p.startswith("C: the face is not the person") for p in res["problems"])


def test_variant_without_person_skips_the_face(tmp_path):
    root = _round(tmp_path / "r")
    p = plan()
    p["variants"][2]["face"] = False
    (root / "SET.json").write_text(json.dumps(p))
    gate = identity.Gate([tmp_path / "marco.jpg"], 0.6, fake_embed({"/C/": "lookalike"}))
    res = variety.check_round(root, LIB, gate=gate)
    assert res["ok"] and "C" not in res["identity"]


def test_identity_fails_closed_when_it_cannot_run(tmp_path, monkeypatch):
    root = _round(tmp_path / "r")

    class Pack:
        dir = str(tmp_path)

        def value(self, key, default=None):
            return {"thumbnail.reference_photo": "photo.jpg"}.get(key, default)
    Image.new("RGB", (8, 8)).save(tmp_path / "photo.jpg")

    def broken(*a, **k):
        raise identity.Unavailable("OpenCV is not installed")
    monkeypatch.setattr(identity.Gate, "for_pack", classmethod(lambda cls, pack, embed=None: broken()))
    res = variety.check_round(root, LIB, pack=Pack())
    assert not res["ok"] and set(res["redo"]) == {"A", "B", "C"}
    assert "could not run" in res["identity"]["A"]["problem"]


def _five(root):
    _round(root)
    p = plan(finalists=["A", "C", "E"])
    for label in "DE":
        (root / label).mkdir()
    Image.new("RGB", (640, 360), (30, 160, 60)).save(root / "D/t.png")
    im = Image.new("RGB", (640, 360), (12, 18, 60))
    im.paste((240, 240, 240), (0, 220, 640, 360))
    im.paste((35, 32, 214), (360, 30, 620, 120))
    im.save(root / "E/t.png")
    p["variants"] += [
        {"label": "D", "format": "pro-two-word-command", "image": "D/t.png",
         "hook": {"focal_object": "two heavy words", "text": "Schneid selbst", "emotion": "determined",
                  "composition": "face left, words right", "colour": "green field"}},
        {"label": "E", "role": "control", "format": "house-face-result", "image": "E/t.png",
         "hook": {"focal_object": "code card with the proof", "text": "Video fertig?", "emotion": "pointing, calm",
                  "composition": "face right, card left under the words", "colour": "navy with blue box"}}]
    (root / "SET.json").write_text(json.dumps(p))
    return root


def test_control_is_exempt_from_the_palette_and_finalists_leave_a_reserve(tmp_path):
    class Pack:
        def value(self, key, default=None):
            return {"thumbnail.palette.main": "#d97757", "thumbnail.palette.marker": "#2320D6",
                    "thumbnail.palette.marker_share": [0.0, 0.06]}.get(key, default)
    res = variety.check_round(_five(tmp_path / "r"), LIB, pack=Pack())
    assert res["control"] == ["E"] and "E" not in res["palette"]
    assert res["finalists"] == ["A", "C", "E"] and res["reserve"] == ["B", "D"]
    assert not any(p.startswith("E:") for p in res["problems"])


def test_plan_limits_controls_and_needs_finalists_for_more_than_three():
    p = plan()
    p["variants"].append(dict(p["variants"][0], label="D", role="control"))
    assert any("finalists" in x for x in variety.check_plan(p, LIB))
    p["finalists"] = ["A", "B", "D"]
    assert variety.check_plan(p, LIB) == [] or all("share the same" in x for x in variety.check_plan(p, LIB))
    p["variants"].append(dict(p["variants"][1], label="E", role="control"))
    assert any("control variants" in x for x in variety.check_plan(p, LIB))
    p["finalists"] = ["A", "X", "D"]
    assert any("finalists must name" in x for x in variety.check_plan(p, LIB))


def test_pro_variant_made_from_the_house_reference_fails(tmp_path):
    root = _round(tmp_path / "r")
    (root / "C/REFERENCES.json").write_text(json.dumps({"runs": [{"images": ["t.png"], "references": [
        {"file": "photo.jpg", "role": "face"}, {"file": "house.png", "role": "style"}]}]}))
    (root / "B/REFERENCES.json").write_text(json.dumps({"runs": [{"images": ["t.png"], "references": [
        {"file": "photo.jpg", "role": "face"}, {"file": "f032.png", "role": "layout"}]}]}))
    res = variety.check_round(root, LIB)
    assert res["redo"] == ["C"] and "house style reference instead" in res["problems"][0]
    assert res["references"]["B"]["source"] == "make" and res["references"]["A"] is None


@pytest.fixture
def pack_with_formats(crew):
    episode = episodes.create("Reference plan")["id"]
    root = paths.user_brand_dir()
    (root / "references/formats/img").mkdir(parents=True)
    (root / "brand.json").write_text('{"schema":1}')
    (root / "thumbnail.json").write_text(json.dumps({
        "reference_photo": "photo.jpg", "style_reference": "house.png",
        "identity": {"references": ["frame-1.jpg", "frame-2.jpg"], "max_references": 3},
        "control": {"reference": "old.png", "name": "Kontrolle"}}))
    for f in ("photo.jpg", "frame-1.jpg", "frame-2.jpg", "house.png", "old.png", "references/formats/img/split.png"):
        (root / f).write_bytes(b"x")
    own = [{"id": "house-face-result", "name": "Face points", "kind": "house", "recipe": "r"},
           {"id": "pro-split", "name": "Old vs new split", "kind": "pro", "recipe": "r", "images": ["img/split.png"]},
           {"id": "pro-empty", "name": "No example", "kind": "pro", "recipe": "r"}]
    (root / "references/formats/formats.json").write_text(json.dumps({"schema": 1, "formats": own}))
    return episode, root


def test_pro_format_gets_its_example_and_not_the_house_thumbnail(pack_with_formats):
    episode, root = pack_with_formats
    pro = make.reference_plan(episode, [], "pro-split")
    assert [(p.name, r) for p, r in pro] == [("photo.jpg", "face"), ("frame-1.jpg", "face"), ("frame-2.jpg", "face"),
                                            ("split.png", "layout")]
    house = make.reference_plan(episode, [], "house-face-result")
    assert [r for _, r in house] == ["face", "face", "face", "style"] and house[-1][0].name == "house.png"
    control = make.reference_plan(episode, [], "house-face-result", role="control")
    assert control[-1][0].name == "old.png" and control[-1][1] == "control"
    with pytest.raises(FileNotFoundError, match="no example image"):
        make.reference_plan(episode, [], "pro-empty")
    with pytest.raises(ValueError, match="not in the format library"):
        make.reference_plan(episode, [], "pro-unknown")
    header = make.roles_header(pro, "Old vs New split")
    assert "4. split.png: LAYOUT EXAMPLE of the format Old vs New split" in header


def test_make_reads_the_format_from_set_json_and_records_the_references(pack_with_formats, monkeypatch, capsys):
    episode, root = pack_with_formats
    ep = paths.episode_dir(episode)
    rnd = ep / "graphics/thumbnail/v4"
    (rnd / "C-split").mkdir(parents=True)
    (rnd / "C-split/prompt.txt").write_text("An old vs new split.")
    (rnd / "SET.json").write_text(json.dumps({"variants": [
        {"label": "C", "format": "pro-split", "image": "C-split/thumbnail-v001.png", "prompt": "C-split/prompt.txt"}]}))
    sent = {}

    def fake_make(prompt, refs, out, edit=False):
        sent["prompt"], sent["refs"], sent["edit"] = prompt, [r.name for r in refs], edit
        Image.new("RGB", (16, 9)).save(out)
        return out
    monkeypatch.setattr(make, "choose_way", lambda asked: "codex")
    monkeypatch.setattr(make, "make_codex", fake_make)
    monkeypatch.setattr(make, "identity_gate", lambda a: (None, 1))
    a = types.SimpleNamespace(episode=episode, prompt="graphics/thumbnail/v4/C-split/prompt.txt", ref=[],
                              way="codex", variants=1, out="graphics/thumbnail/v4/C-split", format=None,
                              control=False)
    assert make.cli(a) == 0
    assert sent["refs"] == ["photo.jpg", "frame-1.jpg", "frame-2.jpg", "split.png"]
    assert sent["prompt"].startswith("ATTACHED IMAGES") and sent["prompt"].endswith("An old vs new split.")
    runs = json.loads((rnd / "C-split/REFERENCES.json").read_text())["runs"]
    assert runs[-1]["format"] == "pro-split" and runs[-1]["kind"] == "pro"
    assert [r["role"] for r in runs[-1]["references"]] == ["face", "face", "face", "layout"]


def test_card_marks_the_control_and_the_reserve(crew, capsys):
    episode = episodes.create("Control card")["id"]
    root = paths.user_brand_dir()
    root.mkdir(parents=True)
    (root / "brand.json").write_text('{"schema":1}')
    (root / "thumbnail.json").write_text(json.dumps({"control": {"name": "Kontrolle"}}))
    (root / "references/formats").mkdir(parents=True)
    (root / "references/formats/formats.json").write_text(json.dumps({"schema": 1, "formats": [
        {**f, "recipe": "r"} for f in LIB.values()]}))
    ep = paths.episode_dir(episode)
    _five(ep / "graphics/thumbnail/v5")
    a = types.SimpleNamespace(episode=episode, round="graphics/thumbnail/v5", setcmd="card", plan_only=False,
                              json=False, title=None, body=None, preview=None)
    assert variety.cli(a) == 0
    card = approvals.get(int(capsys.readouterr().out.split("#")[1]))
    e = card["data"]["variants"][4]
    assert e["role"] == "control" and e["format_name"].startswith("Kontrolle")
    assert card["data"]["finalists"] == ["A", "C", "E"] and card["data"]["reserve"] == ["B", "D"]
    assert card["options"][1].endswith("(reserve)") and "Reserve for a second round: B, D" in card["body"]


def test_make_retries_a_wrong_face_and_edits_keep_the_base_first(pack_with_formats, monkeypatch, capsys):
    episode, root = pack_with_formats
    ep = paths.episode_dir(episode)
    (ep / "graphics/thumbnail/v4/A").mkdir(parents=True)
    (ep / "graphics/thumbnail/v4/A/prompt.txt").write_text("Change the text only.")
    Image.new("RGB", (16, 9)).save(ep / "graphics/thumbnail/good-face.png")
    calls = []

    def fake_make(prompt, refs, out, edit=False):
        calls.append((out.name, refs[0].name, edit, prompt.splitlines()[1]))
        Image.new("RGB", (16, 9)).save(out)
        return out

    class Gate:
        n = 0

        def measure(self, img):
            Gate.n += 1
            return {"ok": Gate.n > 1, "similarity": 0.3 if Gate.n == 1 else 0.7, "problem": "the face is not the person"}
    monkeypatch.setattr(make, "choose_way", lambda asked: "codex")
    monkeypatch.setattr(make, "make_codex", fake_make)
    monkeypatch.setattr(make, "identity_gate", lambda a: (Gate(), 3))
    a = types.SimpleNamespace(episode=episode, prompt="graphics/thumbnail/v4/A/prompt.txt", ref=[], way="codex",
                              variants=1, out="graphics/thumbnail/v4/A", format="house-face-result", control=False,
                              edit="graphics/thumbnail/good-face.png")
    assert make.cli(a) == 0
    assert len(calls) == 2 and calls[0][1] == "good-face.png" and calls[0][2] is True
    assert calls[0][3].startswith("1. good-face.png: EDIT BASE")
    files = sorted(f.name for f in (ep / "graphics/thumbnail/v4/A").glob("*.png"))
    assert any(f.endswith("-wrong-face.png") for f in files) and any("-try2.png" in f for f in files)


def test_limited_colour_warns_but_the_control_is_exempt(tmp_path):
    class Pack:
        def value(self, key, default=None):
            return {"thumbnail.palette.limits": [{"colour": "#2320D6", "max_share": 0.01, "name": "brand blue"}]}.get(
                key, default)
    root = _five(tmp_path / "r")          # A (house style test image) is mostly blue, E (control) has a blue box
    res = variety.check_round(root, LIB, pack=Pack())
    assert any(w.startswith("A: brand blue covers") for w in res["warnings"])
    assert not any(w.startswith("E:") for w in res["warnings"])
    assert res["ok"]                      # a warning does not fail the set
