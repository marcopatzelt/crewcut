"""`crewcut retention units` against a fixed, synthetic retention curve (no API in CI).

The made-up video is 120 s long: an intro (0-20 s), "Punkt eins" (20-50 s), "Punkt zwei" (50-100 s) and an outro with
the link (100-120 s). Its audience falls from 100 % to 70 % in the intro, holds over unit 1, falls from 68 % to 48 %
between 60 and 70 s in unit 2, and leaves again at the link.
"""

from __future__ import annotations

import json
import types

import pytest

from crewcut import cli, episodes, paths
from crewcut.youtube import units

DUR = 120.0
VID = "abcDEF12345"

SENTENCES = [  # (start, text)
    (0.0, "Mein Claude hat heute ein ganzes Video allein geschnitten."),
    (6.0, "Wenn du Videos machst, kostet dich der Schnitt Tage."),
    (12.0, "Heute zeige ich dir zwei Punkte, und am Ende sage ich dir den Preis."),
    (20.0, "Punkt eins."),
    (21.5, "Mein Test hat 12 von 30 Szenen in einem Durchgang geschafft."),
    (30.0, "Das Programm liest jedes Wort und legt den Schnitt in die Pause."),
    (40.0, "Das spart dir am Ende viele Stunden."),
    (50.0, "Punkt zwei ist die Theorie."),
    (55.0, "Ein Markt hat Angebot und Nachfrage, und jedes Format ist ein eigener Markt."),
    (60.0, "Die Nachfrage bestimmt den Preis, das Angebot bestimmt die Menge."),
    (70.0, "Machen zu viele dasselbe, sinken die Aufrufe pro Video."),
    (85.0, "Darum suche ich ein Format, das viele sehen wollen."),
    (100.0, "Der Link ist in der Videobeschreibung."),
    (110.0, "Danke fürs Zuschauen."),
]


def words() -> list[dict]:
    out = []
    for k, (start, text) in enumerate(SENTENCES):
        end = SENTENCES[k + 1][0] if k + 1 < len(SENTENCES) else DUR - 1
        ws = text.split()
        step = (end - start) / len(ws)
        out += [{"w": w, "s": round(start + i * step, 2), "e": round(start + (i + 1) * step, 2)}
                for i, w in enumerate(ws)]
    return out


def level(t: float) -> float:
    if t <= 20:
        return 1.0 - 0.3 * t / 20
    if t <= 60:
        return 0.70 - 0.02 * (t - 20) / 40
    if t <= 70:
        return 0.68 - 0.20 * (t - 60) / 10
    if t <= 100:
        return 0.48
    return 0.48 - 0.08 * (t - 100) / 20


def rank(t: float) -> float:
    return 0.45 if t < 60 else 0.25


def curve_answer(scale: float = DUR) -> dict:
    rows = [[k / 100, round(level(k / 100 * scale), 4), rank(k / 100 * scale)] for k in range(1, 101)]
    return {"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"},
                              {"name": "relativeRetentionPerformance"}], "rows": rows}


DAYS = {"columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "averageViewDuration"},
                          {"name": "averageViewPercentage"}],
        "rows": [["2026-11-20", 300, 60, 50.0], ["2026-11-21", 100, 40, 33.3], ["2026-11-22", 0, 0, 0]]}


class Fake:
    """A recorded YouTube: one curve for every window that holds a day with views."""

    def __init__(self, curve=None, days=DAYS, duration=DUR):
        self.curve, self.days, self.dur, self.params = curve or curve_answer(), days, duration, []

    def query(self, p):
        self.params.append(p)
        rows = [r for r in self.days["rows"] if p["startDate"] <= r[0] <= p["endDate"]]
        if p.get("dimensions") == "elapsedVideoTimeRatio":
            return self.curve if any(r[1] for r in rows) else {**self.curve, "rows": []}
        return {**self.days, "rows": rows}

    def duration(self, video_id):
        return self.dur


def args(**kw) -> types.SimpleNamespace:
    base = {"words": None, "duration": None, "since": None, "until": None, "video": None, "saved": False, "clips": 0,
            "no_learnings": False, "json": False, "rtcmd": "units"}
    return types.SimpleNamespace(**{**base, **kw})


def video(title: str = "Published video", vid: str = VID, ws: list[dict] | None = None) -> str:
    eid = episodes.create(title)["id"]
    ep = paths.episode_dir(eid)
    (ep / "work" / "words-v003.json").write_text(json.dumps(ws if ws is not None else words()))
    (ep / "edit" / "plan-v003.json").write_text(json.dumps({"words": "work/words-v003.json", "inserts": []}))
    (ep / "export" / "upload-result.json").write_text(json.dumps({"video_id": vid, "at": "2026-11-20T10:00:00Z"}))
    return eid


def test_units_from_counted_signposts(studio):
    eid = video()
    api = Fake()
    res = units.run(eid, args(), api=api, today=units.date(2026, 11, 27))
    p = api.params[0]
    assert p["metrics"] == "audienceWatchRatio,relativeRetentionPerformance"
    assert p["dimensions"] == "elapsedVideoTimeRatio" and p["filters"] == f"video=={VID}"
    assert p["startDate"] == "2026-11-20" and p["endDate"] == "2026-11-27" and p["ids"] == "channel==MINE"
    m = res["measurements"][0]
    assert m["boundaries"] == "signposts" and m["duration_s"] == DUR and m["data_until"] == "2026-11-21"
    assert m["sample"] == {"views": 400, "average_view_s": 55.0, "average_view_percent": 45.8}
    kinds = [(u["kind"], u["n"], u["start"]) for u in m["units"]]
    assert kinds == [("intro", 0, 0.0), ("unit", 1, 20.0), ("unit", 2, 50.0), ("outro", None, 100.0)]
    intro, one, two, outro = m["units"]
    assert one["retention_start"] == pytest.approx(70.0, abs=0.6) and one["retention_end"] == pytest.approx(68.5, abs=0.6)
    assert one["verdict"] == "holds" and one["drop_per_min"] < 5
    assert one["hook"] == "Punkt eins. Mein Test hat 12 von 30 Szenen in einem Durchgang geschafft."
    assert one["hook_type"] == "number" and one["hook_first_person"] is True
    assert two["verdict"] == "loses" and two["drop_points"] == pytest.approx(20.0, abs=1.0)
    assert two["hook_type"] == "label" and two["rel_mean"] == pytest.approx(0.27, abs=0.03)
    st = two["steepest"]
    assert st["start"] == pytest.approx(60.0, abs=1.3) and st["points"] == pytest.approx(20.0, abs=1.0)
    assert st["sentence"].startswith("Die Nachfrage bestimmt den Preis")
    assert m["units"][m["worst_unit"]] is two
    assert intro["verdict"] == "neutral", "the intro is judged by its rank (0.45)"
    assert outro["kind"] == "outro"
    ep = paths.episode_dir(eid)
    saved = json.loads((ep / "analytics" / "retention-units.json").read_text())
    assert saved["video_id"] == VID and saved["measurements"][0]["units"][2]["verdict"] == "loses"
    md = (ep / "analytics" / "retention-units.md").read_text()
    assert "| 2 | Unit 2: Punkt zwei ist die Theorie." in md and "Lost the most: Unit 2" in md


def test_the_learnings_file_has_a_stable_format_and_one_block_per_data_day(studio):
    eid = video()
    units.run(eid, args(), api=Fake(), today=units.date(2026, 11, 27))
    units.run(eid, args(), api=Fake(), today=units.date(2026, 11, 28))         # same data day: replaced
    text = units.learnings_path().read_text()
    assert units.learnings_path() == studio / "library" / "learnings" / "retention-units.md"
    assert text.startswith("# Retention per content unit") and "Format (schema 1, stable)" in text
    assert text.count(units.OVERALL_START) == 1 and text.count(units.OVERALL_END) == 1
    assert text.count(f"## {eid} · data until 2026-11-21") == 1 and "Measured 2026-11-28" in text
    assert "- Loses: Unit 2" in text and "- Steepest drop: Unit 2 at 1:00" in text
    data = [line for line in text.splitlines() if line.startswith(units.DATA_MARK)]
    assert len(data) == 1
    d = json.loads(data[0][len(units.DATA_MARK):].rsplit("-->", 1)[0])
    assert d["schema"] == 1 and [u["verdict"] for u in d["units"]] == ["neutral", "holds", "loses", "loses"]
    # a new data day appends a block
    days = {**DAYS, "rows": DAYS["rows"] + [["2026-11-23", 50, 50, 41.0]]}
    units.run(eid, args(), api=Fake(days=days), today=units.date(2026, 11, 29))
    text = units.learnings_path().read_text()
    assert f"## {eid} · data until 2026-11-21" in text and f"## {eid} · data until 2026-11-23" in text
    assert "| kind | unit | 2 | 1 | 1 | 1 |" in text, "the overall section counts only the newest block of an episode"


def test_a_group_becomes_a_lesson_after_three_episodes(studio):
    for k in range(3):
        units.run(video(f"Video {k}", f"abcDEF1234{k}"), args(), api=Fake(), today=units.date(2026, 11, 27))
    text = units.learnings_path().read_text()
    overall = text.split(units.OVERALL_START)[1].split(units.OVERALL_END)[0]
    assert "Episodes: 3" in overall
    assert "| hook | label | 3 | 3 | 0 | 3 |" in overall and "lesson: loses" in overall
    assert "| hook | number | 3 | 3 | 3 | 0 |" in overall and "lesson: holds" in overall


def test_no_data_yet_writes_nothing(studio):
    eid = video()
    empty = {**DAYS, "rows": []}
    with pytest.raises(units.NoData):
        units.run(eid, args(), api=Fake(days=empty), today=units.date(2026, 11, 27))
    assert not (paths.episode_dir(eid) / "analytics" / "retention-units.json").exists()
    assert not units.learnings_path().exists()


def test_a_trimmed_video_is_measured_per_version(studio):
    eid = video()
    ep = paths.episode_dir(eid)
    long = [{**w, "s": w["s"] * 1.5, "e": w["e"] * 1.5} for w in words()]
    (ep / "work" / "words-v002.json").write_text(json.dumps(long))
    (ep / "analytics").mkdir()
    (ep / "analytics" / "versions.json").write_text(json.dumps({"versions": [
        {"label": "first", "words": "work/words-v002.json", "duration_s": 180, "until": "2026-11-21"},
        {"label": "trimmed", "words": "work/words-v003.json", "since": "2026-11-23"}]}))
    api = Fake(curve=curve_answer(180))
    res = units.run(eid, args(), api=api, today=units.date(2026, 11, 27))
    assert [m["label"] for m in res["measurements"]] == ["first"]
    assert res["skipped"] == [{"label": "trimmed", "status": units.NO_DATA, "since": "2026-11-23", "until": None}]
    m = res["measurements"][0]
    assert m["duration_s"] == 180 and m["units"][2]["start"] == pytest.approx(75.0)
    assert {(p["startDate"], p["endDate"]) for p in api.params} == {("2026-11-20", "2026-11-21"),
                                                                    ("2026-11-23", "2026-11-27")}


def test_drehzettel_units_bring_their_type(studio):
    eid = video()
    ep = paths.episode_dir(eid)
    (ep / "brief" / "DREHZETTEL-v001.md").write_text(
        "# Drehzettel\n\n## Einstieg\nSATZ1: Mein Claude hat heute ein ganzes Video allein geschnitten.\n\n"
        "## Einheit 1 | Beleg: Zahl | Short: ja\nHOOK: Punkt eins. Mein Test hat 12 von 30 Szenen geschafft.\n"
        "• Beleg: jedes Wort\nPUNCH: Das spart Stunden.\n\n## Einheit 2 | Beleg: Rechnung | Short: nein\n"
        "HOOK: Punkt zwei. Ein Markt hat Angebot und Nachfrage.\nPUNCH: Genau die Mitte.\n\n## Schluss\n"
        "URTEIL: Der Link ist in der Videobeschreibung.\nLINK: Danke fürs Zuschauen.\n\n---\n\nNotizen\n")
    m = units.run(eid, args(), api=Fake(), today=units.date(2026, 11, 27))["measurements"][0]
    assert m["boundaries"] == "drehzettel" and m["boundaries_file"] == "DREHZETTEL-v001.md"
    assert [(u["kind"], u["type"], u["short"]) for u in m["units"]] == [
        ("intro", None, None), ("unit", "Zahl", True), ("unit", "Rechnung", False), ("outro", None, None)]
    text = units.learnings_path().read_text()
    assert "| type | Rechnung | 1 | 1 | 0 | 1 |" in text


def test_without_signposts_the_script_parts_and_chapters_mark_the_units(studio):
    plain = [w if w["w"] != "eins." else {**w, "w": "Test."} for w in words()]
    plain = [w for w in plain if w["w"] not in ("Punkt", "zwei")]
    eid = video(ws=plain)
    ep = paths.episode_dir(eid)
    (ep / "brief" / "SCRIPT-v001.md").write_text(
        "Mein Claude hat heute ein Video geschnitten.\n\n\n\nMein Test hat 12 von 30 Szenen in einem Durchgang "
        "geschafft.\n\nDas Programm liest jedes Wort.\n\n\n\nEin Markt hat Angebot und Nachfrage, jedes Format ist "
        "ein Markt.\n\n\n\nDer Link ist in der Videobeschreibung. Danke fürs Zuschauen.\n\n---\n\nStory-Plan\n")
    m = units.run(eid, args(), api=Fake(), today=units.date(2026, 11, 27))["measurements"][0]
    assert m["boundaries"] == "script"
    assert [(u["kind"], round(u["start"])) for u in m["units"]] == [("intro", 0), ("unit", 22), ("unit", 55),
                                                                    ("outro", 100)]
    (ep / "work" / "chapters.txt").write_text("0:00 Intro\n0:20 Der Test\n0:50 Die Theorie\n")
    (ep / "analytics" / "versions.json").write_text(json.dumps({"versions": [
        {"label": "v003", "words": "work/words-v003.json", "chapters": "work/chapters.txt"}]}))
    m = units.run(eid, args(), api=Fake(), today=units.date(2026, 11, 27))["measurements"][0]
    assert m["boundaries"] == "chapters"
    assert [(u["label"], round(u["start"])) for u in m["units"]][:3] == [
        ("Intro", 0), ("Unit 1 (Der Test)", 21), ("Unit 2 (Die Theorie)", 52)]


def test_reasons_from_a_watcher_go_into_the_report_and_saved_needs_no_api(studio):
    eid = video()
    units.run(eid, args(no_learnings=True), api=Fake(), today=units.date(2026, 11, 27))
    ep = paths.episode_dir(eid)
    (ep / "analytics" / "retention-units-why.json").write_text(json.dumps([
        {"version": "words-v003", "unit": 2, "at": 60.0, "by": "a video model", "text": "Theory without a test."}]))
    res = units.run(eid, args(saved=True), api=None, today=units.date(2026, 11, 28))
    assert res["measurements"][0]["units"][2]["why"][0]["text"] == "Theory without a test."
    md = (ep / "analytics" / "retention-units.md").read_text()
    assert "### Why viewers left (watched)" in md and "Unit 2, 1:00 (a video model): Theory without a test." in md
    assert "- Why (watched by a video model): Unit 2 at 1:00: Theory without a test." in \
        units.learnings_path().read_text()


def test_hook_types_and_real_numbers():
    assert units.hook_type("Punkt eins. Mein Opus hat 6 Dollar gekostet.", "de", True) == ("number", True)
    assert units.hook_type("Rolle 3 ist der Schnitt.", "de", True) == ("label", False)
    assert units.hook_type("Wie schneidet Claude ein Video?", "de", False)[0] == "question"
    assert units.hook_type("Jetzt denkst du dir vielleicht, das ist teuer.", "de", False)[0] == "objection"
    assert units.hook_type("Qwen 3.8 schickt deine Daten heimlich an fremde Dienste.", "de", False)[0] == "claim"
    assert units.signpost({"toks": units.toks("Und Rolle 4 sind die Grafiken.")}, "de") == 4
    assert units.signpost({"toks": units.toks("1 ist der Research.")}, "de") == 1
    assert units.signpost({"toks": units.toks("Schritt für Schritt gehen wir durch.")}, "de") is None
    assert units.chain([(3, 1), (5, 7), (9, 2), (12, 3), (14, 2)]) == [(3, 1), (9, 2), (12, 3)]
    assert units.iso_seconds("PT4M47S") == 287 and units.iso_seconds("PT1H2S") == 3602 and units.iso_seconds("x") is None
    assert units.norm_words([[0.1, 0.4, "Hallo."]]) == [{"w": "Hallo.", "s": 0.1, "e": 0.4}]


def test_the_command_line(studio, capsys, monkeypatch):
    eid = video()
    monkeypatch.setattr(units, "YouTube", lambda: Fake())
    assert cli.main(["retention", "units", eid]) == 0
    out = capsys.readouterr().out
    assert "units from signposts" in out and "Unit 2" in out and "loses" in out
    assert cli.main(["retention", "units", eid, "--saved", "--json", "--no-learnings"]) == 0
    assert json.loads(capsys.readouterr().out)["video_id"] == VID
    monkeypatch.setattr(units, "YouTube", lambda: Fake(days={**DAYS, "rows": []}))
    assert cli.main(["retention", "units", eid]) == 0
    assert units.NO_DATA in capsys.readouterr().out
