import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_helpers import APP, pack, script  # noqa: E402

cc = script("cut-check/scripts/cut_check.py", "s2_cut_check")
cl = sys.modules["checklib"]


def clip(i, src, s, e, text, fin, fout):
    return {"id": i, "source": src, "start": s, "end": e, "expected_text": text,
            "timeline_in_frame": fin, "timeline_out_frame": fout}


def test_words_split_and_spelling():
    assert cc.words("Self-hosted, local AI.") == ["self", "hosted", "local", "ai"]
    assert cc.words("one two", {"one": "1"}) == ["1", "two"]
    assert cc.words(None) == []


def test_doubled_word_and_same_meaning():
    clips = [clip("a", "t1.mp4", 0, 2, "We use the tool", 0, 50), clip("b", "t1.mp4", 5, 7, "Tool calls work.", 50, 100),
             clip("c", "t2.mp4", 0, 2, "So we start.", 100, 150), clip("d", "t2.mp4", 3, 5, "therefore it runs.", 150, 200)]
    found = cc.doubled_at_cuts(clips, {}, [["so", "therefore"]])
    assert [(d["a"], d["b"]) for d in found] == [("a", "b")]
    clips[2]["expected_text"] = "We start so"
    found = cc.doubled_at_cuts(clips, {}, [["so", "therefore"]])
    assert ("c", "d") in [(d["a"], d["b"]) for d in found]


def test_pieces_of_one_select_are_not_doubled():
    clips = [clip("a1", "t.mp4", 0, 2, "same same", 0, 50), clip("a2", "t.mp4", 2.5, 4, "same same", 50, 90)]
    assert cc.doubled_at_cuts(clips, {}, []) == []


def test_leftovers_start_end_and_middle():
    clips = [clip("a", "t.mp4", 10.0, 12.0, "Hello there.", 0, 50), clip("b", "t.mp4", 20.5, 22.0, "Fine words.", 50, 90)]
    islands = {"t.mp4": [
        {"start": 8.0, "end": 9.9, "text": "Hello th"},          # discarded attempt 0.1 s before a
        {"start": 10.0, "end": 12.0, "text": "Hello there."},
        {"start": 19.8, "end": 22.0, "text": "and then fine words"},  # b starts inside this island
        {"start": 12.1, "end": 12.5, "text": "thanks"},          # transcript noise, ignored
    ]}
    lo = cc.leftovers(clips, islands, noise={"thanks"})
    kinds = {(x["id"], x["where"], x["level"]) for x in lo}
    assert ("a", "start", "CHECK") in kinds
    assert ("b", "middle", "ERROR") in kinds
    assert not any(x["where"] == "end" and x["id"] == "a" for x in lo)


def test_take_change_sentence():
    clips = [clip("a", "t1.mp4", 0, 2, "This sentence runs", 0, 50), clip("b", "t2.mp4", 0, 2, "over two takes.", 50, 100),
             clip("c", "t2.mp4", 2.1, 4, "New sentence.", 100, 150)]
    found = cc.take_change_sentences(clips)
    assert [(x["a"], x["b"]) for x in found] == [("a", "b")]


def test_stutters_and_fillers():
    clips = [clip("a", "t.mp4", 0, 2, "", 0, 50), clip("b", "t.mp4", 3, 4, "", 50, 90)]
    heard = {"a": "we we start uh now", "b": "it is 3 3 times. Times are good"}
    found = {x["id"]: x["found"] for x in cc.stutters(clips, heard, {"uh"})}
    assert found["a"] == ["we", "uh"]
    assert "b" not in found


def test_level_jumps():
    fps = 25
    clips = [clip("a", "t.mp4", 0, 5, "", 0, 125), clip("b", "t.mp4", 5, 10, "", 125, 250)]
    levels = np.concatenate([np.full(500, -20.0), np.full(500, -12.0)])
    voiced = np.ones(1000, bool)
    js = cc.level_jumps(levels, voiced, clips, fps)
    assert len(js) == 1 and abs(js[0]["db"] - 8.0) < 1e-6
    assert cc.level_jumps(np.full(1000, -20.0), voiced, clips, fps) == []


def test_cut_words_neutral_is_empty():
    cw = cc.cut_words(pack())
    assert cw["fillers"] == set() and cw["same_meaning"] == [] and cw["noise"] == set()


def test_cut_words_from_example_pack():
    cw = cc.cut_words(pack(APP / "examples" / "striq"))
    assert cw["fillers"] and cw["same_meaning"]


def test_check_end_to_end_without_media(tmp_path):
    ep = tmp_path / "001-test"
    (ep / "work").mkdir(parents=True)
    (ep / "brief").mkdir()
    (ep / "project.json").write_text("{}")
    dec = ep / "work" / "edit-decisions-v002.json"
    dec.write_text(json.dumps({"fps": 25, "voice": "audio/missing.wav", "clips": [
        clip("a", "originals/T1.MP4", 0, 2, "We test the tool", 0, 50),
        clip("b", "originals/T1.MP4", 5, 7, "tool is fast.", 50, 100)]}))
    ver = ep / "work" / "cut-verification-v002.json"
    ver.write_text(json.dumps({"status": "ok", "selects": [{"id": "a", "text": "We test the tool"},
                                                            {"id": "b", "text": "tool is fast."}],
                               "joins": [{}], "bad_joins": [], "edge_issues": []}))
    (ep / "brief" / "T1-islands.json").write_text(json.dumps([{"start": 0, "end": 2, "text": "We test the tool"},
                                                              {"start": 5, "end": 7, "text": "tool is fast."}]))
    code = cc.main([str(dec), "--pack", str(APP / "packs" / "neutral")])
    assert code == 1  # the doubled "tool"
    rep = json.loads((ep / "review" / "speaker-cut-check-v002.json").read_text())
    ids = {f["id"]: f["level"] for f in rep["findings"]}
    assert ids["doubled:a>b"] == "ERROR"
    assert ids["verify"] == "OK"
    assert ids["level"] == "NOTE"
    (ep / "review" / "cut-check-exceptions.json").write_text(json.dumps({"doubled:a>b": "user wants it, 16 Nov 2026"}))
    assert cc.main([str(dec), "--pack", str(APP / "packs" / "neutral")]) == 0


def test_report_exceptions_and_listening_list():
    r = cl.Report({"x": "ok by the user"})
    r.add("Cut", "ERROR", "x", "bad", 3.0)
    r.add("Cut", "CHECK", "y", "listen", 1.0)
    assert r.items[0]["level"] == "OK"
    assert [i["id"] for i in r.listening_list()] == ["y"]
    assert cl.tc(75.25) == "1:15.2"


def test_loudness_parse_and_verdict():
    lufs, peak = cl.parse_ebur128("  I:         -14.3 LUFS\n  Peak:        -1.6 dBFS\n")
    assert (lufs, peak) == (-14.3, -1.6)
    assert cl.loudness_verdict(lufs, peak, -14.0, [-2.0, 0.5], -1.5)[0] == "OK"
    assert cl.loudness_verdict(-12.0, -1.6, -14.0, [-2.0, 0.5], -1.5)[0] == "ERROR"
    assert cl.loudness_verdict(-14.0, -0.6, -14.0, [-2.0, 0.5], -1.0)[0] == "ERROR"
    assert cl.parse_volumedetect("mean_volume: -20.5 dB\nmean_volume: -21.0 dB") == [-20.5, -21.0]
