import json

import pytest

from crewcut import brand, db, episodes, importer
from crewcut.conductor import inbox, queue


@pytest.fixture
def no_jobs(monkeypatch):
    jobs = []
    monkeypatch.setattr(queue, "add", lambda *a, **k: jobs.append((a, k)) or len(jobs))
    return jobs


def make_source(tmp_path):
    src = tmp_path / "S017-old"
    (src / "00-brief").mkdir(parents=True)
    (src / "00-brief" / "SCRIPT-DE-v001.md").write_text("# Script\n\nHello.\n")
    (src / "04-broll" / "web").mkdir(parents=True)
    (src / "04-broll" / "stage-v001.mp4").write_bytes(b"x")
    (src / "04-broll" / "web" / "frame.png").write_bytes(b"x")
    (src / ".claude").mkdir()
    (src / ".claude" / "secret.mp4").write_bytes(b"x")
    runs = src / "07-review" / "laeufe"
    for r in ("opus-low", "fable-max"):
        (runs / r / "out").mkdir(parents=True)
        (runs / r / "out" / "spot.mp4").write_bytes(b"x")
    return src


def test_import_copies_script_and_broll_and_starts_record(crew, studio, tmp_path, no_jobs):
    src = make_source(tmp_path)
    p = importer.import_episode(src, "KI-Beirat", fmt="portrait")
    ep = studio / "episodes" / p["id"]
    assert (ep / "brief" / "SCRIPT-v001.md").read_text().startswith("# Script")
    assert sorted(f.name for f in (ep / "broll").iterdir()) == ["frame.png", "stage-v001.mp4"]
    st = {k: v["status"] for k, v in p["steps"].items()}
    assert st["script"] == "done" and st["upload"] == "skipped" and st["record"] == "waiting"
    assert p["format"] == "portrait" and p["step"] == "record"
    assert not no_jobs  # record needs no agent: the teleprompter link is posted instead
    msgs = [m["text"] for m in __import__("crewcut.conductor.flow", fromlist=["x"]).messages(p["id"])]
    assert any("teleprompter" in m for m in msgs) and any("Imported" in m for m in msgs)


def test_import_explicit_broll_with_same_names(crew, studio, tmp_path, no_jobs):
    src = make_source(tmp_path)
    runs = src / "07-review" / "laeufe"
    p = importer.import_episode(src, "Denkstufen", broll=[runs / "opus-low" / "out" / "spot.mp4",
                                                          runs / "fable-max" / "out" / "spot.mp4"], start=False)
    names = sorted(f.name for f in (studio / "episodes" / p["id"] / "broll").iterdir())
    assert names == ["fable-max-spot.mp4", "opus-low-spot.mp4"]


def test_convert_plan_keys():
    old = {"format": "hoch", "worte": "w.json", "basis": "b.mp4", "nachlauf": 1.5,
           "sprecher": [{"ab": 3.0, "zoom": 1.1}],
           "einschuebe": [{"id": "s1", "art": "2d", "baustein": "zaehler", "von": 1, "bis": 2,
                           "cues": {"zahl": {"wort": "dreissig", "versatz": 2}}, "daten": {"zahl": "30"}}],
           "ton": {"musik": "m.wav", "loecher": [{"vor": "s1@zahl", "bilder": 15}], "ducken": True},
           "ausgabe": "out.mp4"}
    new = importer.convert_plan(old)
    assert new["format"] == "portrait" and new["words"] == "w.json" and new["tail"] == 1.5
    assert new["speaker"] == [{"at": 3.0, "zoom": 1.1}]
    i = new["inserts"][0]
    assert i["kind"] == "2d" and i["scene"] == "counter" and i["start"] == 1 and i["cues"]["zahl"] == {
        "word": "dreissig", "offset": 2}
    assert new["sound"]["gaps"] == [{"before": "s1@zahl", "frames": 15}] and new["sound"]["duck"] is True


def test_init_pack_from_example_with_private_fonts(studio, tmp_path):
    from crewcut import paths
    font = tmp_path / "Display.otf"
    font.write_bytes(b"font")
    logo = tmp_path / "mark.svg"
    logo.write_text("<svg/>")
    d = importer.init_pack(paths.app_root() / "examples" / "striq", fonts={"display": font}, logo=logo, accept=True)
    pack = brand.load()
    assert not pack.is_neutral and pack.dir == d
    assert pack.value("brand.colors.accent") == "#2320D6"
    assert pack.value("brand.fonts.display.files") == ["fonts/Display.otf"]
    assert pack.value("brand.logo.file") == "logo.svg"
    assert pack.rules("cut") and db.kv_get("onboarded") == "1"
    assert not (d / "README.md").exists()


def test_inbox_watcher_waits_for_stable_files(crew, studio, tmp_path, no_jobs, monkeypatch):
    src = make_source(tmp_path)
    p = importer.import_episode(src, "Short")
    box = studio / "inbox" / p["id"]
    box.mkdir(parents=True)
    f = box / "C0001.MP4"
    f.write_bytes(b"abc")
    sizes = {}
    assert inbox.scan(sizes) == []           # first sight: maybe still copying
    f.write_bytes(b"abcdef")
    assert inbox.scan(sizes) == []           # still growing
    got = inbox.scan(sizes)                  # stable now
    assert got == [(p["id"], [f"inbox/{p['id']}/C0001.MP4"])]
    assert inbox.scan(sizes) == []           # announced once
    assert any(k.get("heavy") is False or a[1] == "editor" for a, k in no_jobs)
    assert json.loads(db.kv_get(f"inbox_seen:{p['id']}"))
    episodes.set_step(p["id"], "record", "done")
    episodes.set_step(p["id"], "upload", "done")
    (box / "C0002.MP4").write_bytes(b"x")
    inbox.scan(sizes)
    assert inbox.scan(sizes) == []           # published: no longer watched
