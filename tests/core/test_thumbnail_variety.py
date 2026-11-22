"""Real A/B variety: the format library, the plan check and the near-duplicate image check."""

import json
import types

import pytest
from PIL import Image, ImageDraw

from crewcut import approvals, episodes, paths
from crewcut.thumbnail import formats, variety

W, H = 640, 360


def house_style(path, box=(40, 200, 330, 330), word_w=300):
    """Dark ground, person on the right, a word top left, a result card bottom left (the old 019 kind)."""
    im = Image.new("RGB", (W, H), (11, 14, 20))
    d = ImageDraw.Draw(im)
    d.ellipse((420, 30, 620, 330), fill=(205, 160, 130))
    d.rectangle((30, 30, 30 + word_w, 110), fill=(250, 250, 250))
    d.rectangle(box, fill=(35, 32, 214))
    im.save(path)


def leaning_back(path):
    """Light ground, a small figure in the middle, a dark laptop bottom left, one dark word on top."""
    im = Image.new("RGB", (W, H), (250, 249, 245))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 20, 580, 90), fill=(20, 20, 19))
    d.ellipse((330, 130, 450, 260), fill=(205, 160, 130))
    d.polygon([(60, 340), (300, 340), (260, 230), (100, 230)], fill=(60, 60, 60))
    im.save(path)


def old_vs_new(path):
    """Split: grey left, terracotta right, a face in the middle, two labels."""
    im = Image.new("RGB", (W, H), (120, 120, 125))
    d = ImageDraw.Draw(im)
    d.rectangle((W // 2, 0, W, H), fill=(217, 119, 87))
    d.ellipse((250, 60, 390, 300), fill=(205, 160, 130))
    d.rectangle((20, 20, 140, 70), fill=(200, 30, 30))
    d.rectangle((500, 20, 620, 70), fill=(30, 160, 60))
    im.save(path)


LIB = {
    "house-face-result": {"id": "house-face-result", "name": "Face points at the result", "kind": "house"},
    "pro-leaning-back": {"id": "pro-leaning-back", "name": "Leaning back", "kind": "pro"},
    "pro-old-vs-new": {"id": "pro-old-vs-new", "name": "Old against new", "kind": "pro"},
    "pro-two-word-command": {"id": "pro-two-word-command", "name": "Two-word command", "kind": "pro"},
}


def plan(**over):
    v = [
        {"label": "A", "format": "house-face-result", "image": "A/t.png",
         "hook": {"focal_object": "a big approval button", "text": "Nur noch Ja", "emotion": "confident smile",
                  "composition": "face right third, button left", "colour": "near-black with terracotta box"}},
        {"label": "B", "format": "pro-leaning-back", "image": "B/t.png",
         "hook": {"focal_object": "laptop cutting by itself", "text": "Feierabend", "emotion": "relaxed, smug",
                  "composition": "figure leaning back at a desk", "colour": "warm cream ground, dark type"}},
        {"label": "C", "format": "pro-old-vs-new", "image": "C/t.png",
         "hook": {"focal_object": "old timeline with a red cross against the Claude mark",
                  "text": "Alt Neu", "emotion": "secretive, finger on lips",
                  "composition": "symmetric split, face centred", "colour": "cold grey against terracotta"}},
    ]
    p = {"schema": 1, "variants": v}
    p.update(over)
    return p


def test_near_duplicates_are_rejected_and_different_formats_pass(tmp_path):
    house_style(tmp_path / "a.png")
    house_style(tmp_path / "b.png", box=(50, 190, 320, 340), word_w=280)   # only the card and the word moved a bit
    leaning_back(tmp_path / "c.png")
    old_vs_new(tmp_path / "d.png")
    fp = {k: variety.fingerprint(tmp_path / f"{k}.png") for k in "abcd"}
    same = variety.compare(fp["a"], fp["b"])
    assert same["too_similar"], same
    for x, y in (("a", "c"), ("a", "d"), ("c", "d")):
        c = variety.compare(fp[x], fp[y])
        assert not c["too_similar"], (x, y, c)


def test_plan_needs_formats_kinds_and_a_new_hook():
    assert variety.check_plan(plan(), LIB) == []
    two = plan()
    two["variants"][2]["format"] = "pro-leaning-back"
    assert any("same format" in p for p in variety.check_plan(two, LIB))
    no_house = plan()
    no_house["variants"][0]["format"] = "pro-two-word-command"
    assert any("house format" in p for p in variety.check_plan(no_house, LIB))
    no_pro = plan()
    for v in no_pro["variants"][1:]:
        v["format"] = "house-face-result"
    assert any("pro format" in p for p in variety.check_plan(no_pro, LIB))
    same_text = plan()
    same_text["variants"][1]["hook"]["text"] = "Nur noch ja!"
    assert any("A and B share the same text" in p for p in variety.check_plan(same_text, LIB))
    short = plan()
    short["variants"] = short["variants"][:2]
    assert any("needs 3 to 5" in p for p in variety.check_plan(short, LIB))
    unknown = plan()
    unknown["variants"][1]["format"] = "nothing"
    assert any("not in the format library" in p for p in variety.check_plan(unknown, LIB))
    empty = plan()
    empty["variants"][2]["hook"]["emotion"] = ""
    assert any("C: the hook needs emotion" in p for p in variety.check_plan(empty, LIB))


def _round(root, near_duplicate=False):
    root.mkdir(parents=True)
    for label in "ABC":
        (root / label).mkdir()
    house_style(root / "A/t.png")
    if near_duplicate:
        house_style(root / "B/t.png", box=(50, 190, 320, 340))
    else:
        leaning_back(root / "B/t.png")
    old_vs_new(root / "C/t.png")
    (root / "SET.json").write_text(json.dumps(plan()))
    return root


def test_check_round_writes_the_result_and_names_the_variant_to_redo(tmp_path):
    good = variety.check_round(_round(tmp_path / "good"), LIB)
    assert good["ok"] and good["images_ready"] and len(good["pairs"]) == 3
    assert json.loads((tmp_path / "good/SET-CHECK.json").read_text())["ok"] is True
    bad = variety.check_round(_round(tmp_path / "bad", near_duplicate=True), LIB)
    assert not bad["ok"] and bad["redo"] == ["B"]
    (tmp_path / "good/C/t.png").unlink()
    later = variety.check_round(tmp_path / "good", LIB)
    assert later["ok"] and not later["images_ready"] and later["missing_images"] == ["C"]


@pytest.fixture
def studio_pack(crew):
    episode = episodes.create("Variety test")["id"]
    root = paths.user_brand_dir()
    (root / "references/formats").mkdir(parents=True)
    (root / "brand.json").write_text('{"schema":1}')
    (root / "thumbnail.json").write_text(json.dumps({"formats": {"per_set": 3}}))
    own = [{"id": "house-face-result", "name": "My face points at the proof", "kind": "house",
            "recipe": "Me on the right, pointing.", "strong": True},
           {"id": "pro-leaning-back", "name": "Leaning back", "kind": "pro", "recipe": "Hands behind the head."}]
    (root / "references/formats/formats.json").write_text(json.dumps({"schema": 1, "formats": own}))
    return episode


def test_user_library_adds_to_the_neutral_one_and_wins_by_id(studio_pack):
    lib = formats.load()
    assert lib["house-face-result"]["name"] == "My face points at the proof"
    assert lib["pro-old-vs-new"]["kind"] == "pro"            # from the neutral library
    assert all(not formats.problems_of({k: v for k, v in f.items() if k != "dir"}) for f in lib.values())


def test_neutral_library_is_valid():
    p = paths.neutral_pack_dir() / "references/formats/formats.json"
    assert formats.check_library(p) == []
    kinds = {f["kind"] for f in json.loads(p.read_text())["formats"]}
    assert kinds == {"house", "pro"}


def test_card_only_for_a_set_that_passed(studio_pack, capsys):
    ep = paths.episode_dir(studio_pack)
    _round(ep / "graphics/thumbnail/v2", near_duplicate=True)
    a = types.SimpleNamespace(episode=studio_pack, round="graphics/thumbnail/v2", setcmd="card", plan_only=False,
                              json=False, title=None, body=None, preview=None)
    assert variety.cli(a) == 1
    assert "No card" in capsys.readouterr().out
    leaning_back(ep / "graphics/thumbnail/v2/B/t.png.tmp.png")
    (ep / "graphics/thumbnail/v2/B/t.png.tmp.png").replace(ep / "graphics/thumbnail/v2/B/t.png")
    assert variety.cli(a) == 0
    out = capsys.readouterr().out
    assert out.startswith("card #")
    cid = int(out.split("#")[1])
    card = approvals.get(cid)
    names = [v["format_name"] for v in card["data"]["variants"]]
    assert names == ["My face points at the proof", "Leaning back", "Old against new"]
    assert card["options"][0] == "A · My face points at the proof"
    assert card["data"]["variants"][1]["image"] == "graphics/thumbnail/v2/B/t.png"


class _Pack:
    def __init__(self, palette):
        self.v = {"thumbnail.palette.main": palette.get("main"), "thumbnail.palette.marker": palette.get("marker"),
                  "thumbnail.palette.marker_share": palette.get("marker_share")}

    def value(self, key, default=None):
        return self.v.get(key, default)


def test_set_check_measures_the_brand_marker(tmp_path):
    pack = _Pack({"main": "#d97757", "marker": "#2320D6", "marker_share": [0.001, 0.06]})
    root = _round(tmp_path / "r")
    result = variety.check_round(root, LIB, pack=pack)
    # A (old blue card) is mostly blue, B has no marker at all, C has none either
    assert any(p.startswith("A: the brand marker colour covers") for p in result["problems"])
    assert any(p.startswith("B: the brand marker") and "missing" in p for p in result["problems"])
    assert set(result["redo"]) >= {"A", "B"} and not result["ok"]
    d = ImageDraw.Draw(im := Image.open(root / "C/t.png").convert("RGB"))
    d.rectangle((20, 80, 140, 86), fill=(35, 32, 214))
    im.save(root / "C/t.png")
    assert variety.check_round(root, LIB, pack=pack)["palette"]["C"]["problems"] == []
