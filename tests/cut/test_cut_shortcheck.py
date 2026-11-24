"""`crewcut cut short-check`: the Critic's rules for Shorts. Pure rules first, then one run on a tiny synthetic Short."""

import json
import shutil
import subprocess

import pytest

from crewcut.cut import cli, shortcheck

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg is not installed")
S = {"length_s": [30, 50], "max_still_s": 2.5, "text_cards_max": 3, "loudness_lufs": -14.0,
     "limiter_headroom_db": 1.4, "true_peak_db": -1.5, "right_free_frac": 0.18, "min_mean_luma": 40,
     "end_tail_s": 1.0}
PIECE = {"id": "p1", "short_from": 0.0, "short_to": 10.0, "face": [0.5, 0.35], "face_from": "selects"}


def areas(findings, level=None):
    return [f["area"] for f in findings if level is None or f["level"] == level]


def test_format_and_length():
    assert shortcheck.format_findings(1080, 1920, 40, S) == []
    assert areas(shortcheck.format_findings(1920, 1080, 40, S), "error") == ["format"]
    assert areas(shortcheck.format_findings(720, 1280, 25, S), "warning") == ["format", "length"]
    assert areas(shortcheck.format_findings(1080, 1920, 200, S), "error") == ["length"]


def test_face_rules():
    edge = {**PIECE, "id": "p2", "face": [0.05, 0.4]}
    under = {**PIECE, "id": "p3", "face": [0.85, 0.4]}
    guess = {**PIECE, "id": "p4", "face_from": "default"}
    f = shortcheck.face_findings([PIECE, edge, under, guess], [], S)
    assert [(x["level"], x["area"]) for x in f] == [("error", "face"), ("warning", "face"), ("warning", "face")]
    covered = shortcheck.face_findings([edge], [{"start": 0, "end": 10, "kind": "2d", "scene": "counter"}], S)
    assert covered == []                                   # a full-frame insert hides the speaker the whole time


def test_text_over_the_face_and_in_the_button_zone():
    over_face = {"id": "k1", "kind": "2d", "scene": "keyword", "transparent": True, "start": 1, "end": 3,
                 "data": {"words": [{"text": "LOCAL", "y": 0.36}]}}
    low = {**over_face, "id": "k2", "data": {"text": "LOCAL"}}                      # default y 0.68: free of the face
    wide = {**over_face, "id": "k3", "data": {"text": "a very long keyword chip text", "y": 0.7}}
    f, manual = shortcheck.text_findings([PIECE], [over_face, low, wide], S)
    assert [(x["level"], x["text"].split()[1]) for x in f] == [("error", "k1"), ("error", "k3")]
    assert "over the face" in f[0]["text"] and "right 18 %" in f[1]["text"]
    hidden = {"id": "c1", "kind": "2d", "scene": "counter", "start": 0, "end": 5}
    f, manual = shortcheck.text_findings([PIECE], [over_face, hidden], S)
    assert f == [] and any("c1" in m for m in manual)        # over a full-frame insert the face is not visible
    other = {"id": "o1", "kind": "2d", "scene": "bars", "transparent": True, "start": 1, "end": 2}
    assert any("o1" in m for m in shortcheck.text_findings([PIECE], [other], S)[1])


def test_text_cards_and_loudness():
    cards = [{"id": f"h{i}", "scene": "headline", "start": i, "end": i + 1} for i in range(4)]
    assert areas(shortcheck.card_findings(cards, S), "error") == ["text cards"]
    assert shortcheck.card_findings(cards[:3], S) == []
    assert shortcheck.loudness_findings({"integrated_lufs": -14.3, "true_peak_dbtp": -2.0}, S) == []
    warn = shortcheck.loudness_findings({"integrated_lufs": -15.4, "true_peak_dbtp": -2.0}, S)
    assert warn[0]["level"] == "warning" and "1.4 dB" in warn[0]["text"]
    bad = shortcheck.loudness_findings({"integrated_lufs": -17.0, "true_peak_dbtp": -0.5}, S)
    assert [x["level"] for x in bad] == ["error", "error"]


def test_brightness_still_and_pace():
    means = [100.0] * 10 + [20.0] * 6 + [100.0] * 4
    f = shortcheck.luma_findings(means, S)
    assert len(f) == 1 and f[0]["at"] == 2.0 and "2.0 to 3.2 s" in f[0]["text"]
    diffs = [3.0] * 5 + [0.0] * 15 + [20.0] + [3.0] * 10        # frozen for 3 s, then a cut
    f, shots = shortcheck.still_findings(diffs, [5.0], 6.4, S)
    assert [(x["level"], x["area"]) for x in f] == [("error", "still"), ("warning", "pace")]
    assert [s["from"] for s in shots] == [0.0, 4.2, 5.0]
    assert shortcheck.tail_findings([{"w": "end", "s": 1.0, "e": 2.0}], 4.0, S)[0]["area"] == "end"
    assert shortcheck.tail_findings([{"w": "end", "s": 1.0, "e": 2.0}], 3.2, S) == []


# ---- a run on a tiny Short ---------------------------------------------------------------------------------------
def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


@needs_ffmpeg
def test_check_a_short(studio, capsys):
    ep = studio / "episodes" / "S002-clip"
    for sub in ("work", "audio", "edit", "review"):
        (ep / sub).mkdir(parents=True)
    (ep / "project.json").write_text(json.dumps({"id": "S002-clip", "format": "portrait", "fps": 25}))
    bursts = "0.4*sin(2*PI*330*t)*between(mod(t\\,1)\\,0.2\\,0.7)"
    # 2 s moving test picture, 3.5 s of a still grey frame, 1 s of black; sound in bursts
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=90x160:r=25:d=2", "-f", "lavfi", "-i", "color=c=0x909090:s=90x160:r=25:d=3.5",
           "-f", "lavfi", "-i", "color=c=black:s=90x160:r=25:d=1", "-f", "lavfi", "-i",
           f"aevalsrc={bursts}:s=48000:d=6.5", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
           "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "pcm_s16le", ep / "work" / "speaker-v001.mov")
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc={bursts}:s=48000:d=6.5", "-c:a", "pcm_s24le", ep / "audio" / "voice-v001.wav")
    pieces = [{"id": "p1", "short_from": 0.0, "short_to": 2.45, "face": [0.5, 0.4], "face_from": "selects"},
              {"id": "p2", "short_from": 2.45, "short_to": 6.5, "face": [0.5, 0.4], "face_from": "selects"}]
    (ep / "work" / "words-v001.json").write_text(json.dumps([{"w": "Hi.", "s": 0.2, "e": 0.7}]))
    (ep / "work" / "short-cut-v001.json").write_text(json.dumps(
        {"version": "v001", "pieces": pieces, "voice": {"file": "audio/voice-v001.wav"},
         "words": {"file": "work/words-v001.json"}, "listen": [{"at": 2.45, "what": "join p1 -> p2"}]}))
    (ep / "edit" / "plan-v001.json").write_text(json.dumps(
        {"format": "portrait", "base": "work/speaker-v001.mov", "inserts": [
            {"id": "k1", "kind": "2d", "scene": "keyword", "transparent": True, "start": 0.5, "end": 1.5,
             "data": {"words": [{"text": "HI", "y": 0.4}]}}]}))
    code = cli.main(["cut", "short-check", str(ep / "work" / "speaker-v001.mov"), "--plan", "edit/plan-v001.json",
                     "--json"])
    r = json.loads(capsys.readouterr().out)
    assert code == 2 and not r["ok"]
    assert (r["width"], r["height"]) == (90, 160) and r["cut"] == "work/short-cut-v001.json"
    errors = areas(r["findings"], "error")
    assert {"still", "brightness", "text"} <= set(errors) and "format" not in errors
    assert {"length", "edges", "end"} <= set(areas(r["findings"], "warning"))
    assert any(e["piece"] == "p1" and e["side"] == "end" and e["loud"] for e in r["edges"])   # 2.45 s: in a burst
    assert any(x["what"] == "join p1 -> p2" for x in r["listen"])
    from PIL import Image
    with Image.open(ep / r["sheet"]) as im:
        assert im.size == (6 * 184 + 4, 4 * 324 + 4)
    assert (ep / "review" / "short-check-speaker-v001.json").is_file()


def test_insert_times_in_every_plan_form(tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "words.json").write_text(json.dumps(
        [{"w": "Das", "s": 1.0, "e": 1.2}, {"w": "kostet", "s": 1.2, "e": 1.6}, {"w": "kostet", "s": 5.0, "e": 5.4}]))
    plan = {"words": "work/words.json"}
    inserts = [{"id": "a", "start": 2.0, "end": 3.0},
               {"id": "b", "start": {"time": 4.0}, "end": {"time": 6.0, "offset": -0.5}},
               {"id": "c", "start": {"word": "kostet", "offset": -0.2}, "end": {"word": "kostet", "after": 2.0}},
               {"id": "d", "start": {"word": "fehlt"}, "end": 9.0}]
    out, notes = shortcheck.insert_seconds(inserts, plan, tmp_path)
    assert [(e["id"], e["start"], e["end"]) for e in out] == [("a", 2.0, 3.0), ("b", 4.0, 5.5), ("c", 1.0, 5.0)]
    assert len(notes) == 1 and "insert d" in notes[0]
    assert shortcheck.full_frame(out) == [(2.0, 3.0), (4.0, 5.5), (1.0, 5.0)]
