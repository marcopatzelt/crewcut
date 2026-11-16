"""`crewcut cut short`: pieces of a finished episode, mapped back to the original and cut in 9:16.

Planning is tested with fake probes; the build runs ffmpeg on a tiny synthetic episode (no speech model: the engine is
a fake).
"""

import json
import shutil
import subprocess

import pytest

from crewcut.cut import cli, common, short

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
UHD = {"format": {"duration": "600"}, "streams": [{"codec_type": "video", "width": 3840, "height": 2160},
                                                  {"codec_type": "audio", "channels": 2}]}
HD = {"format": {"duration": "600"}, "streams": [{"codec_type": "video", "width": 1920, "height": 1080},
                                                 {"codec_type": "audio", "channels": 2}]}
WORDS = [{"w": "One", "s": 0.2, "e": 0.7}, {"w": "two.", "s": 1.2, "e": 1.7},
         {"w": "Three", "s": 2.2, "e": 2.7}, {"w": "four.", "s": 3.2, "e": 3.55}]
BURSTS = "0.4*sin(2*PI*330*t)*between(mod(t\\,1)\\,0.2\\,0.7)"


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


def make_episode(studio, eid, fmt="landscape"):
    d = studio / "episodes" / eid
    for sub in ("originals", "work", "audio", "edit", "review", "export"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps({"id": eid, "format": fmt, "fps": 25}))
    return d


def source_episode(studio, media=True, face=(0.7, 0.4)):
    """010-src: one original (5 s), two cuts s1 0-2 s and s2 3-4.6 s, so the cut timeline is 0-2 | 2-3.6 s."""
    d = make_episode(studio, "010-src")
    if media:
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=5", "-f", "lavfi", "-i",
               f"aevalsrc={BURSTS}:s=48000:d=5", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
               "-c:a", "pcm_s16le", d / "originals" / "a.mov")
        ffmpeg("-f", "lavfi", "-i", f"aevalsrc={BURSTS}|{BURSTS}:s=48000:d=3.6", "-c:a", "pcm_s24le",
               d / "audio" / "voice-v001.wav")
    else:
        (d / "originals" / "a.mov").write_bytes(b"x")
        (d / "audio" / "voice-v001.wav").write_bytes(b"x")
    (d / "edit" / "selects-v001.json").write_text(json.dumps(
        {"takes": {"A": {"source": "originals/a.mov", "face": list(face)}}}))
    (d / "edit" / "cut-plan-v001.json").write_text(json.dumps(
        {"version": "v001", "selects": "edit/selects-v001.json", "voice_filter": "highpass=f=75", "cuts": []}))
    clips = [{"id": "s1", "source": "originals/a.mov", "start": 0.0, "end": 2.0, "speed": 1.0,
              "timeline_in_frame": 0, "timeline_out_frame": 50},
             {"id": "s2", "source": "originals/a.mov", "start": 3.0, "end": 4.6, "speed": 1.0,
              "timeline_in_frame": 50, "timeline_out_frame": 90}]
    (d / "work" / "edit-decisions-v001.json").write_text(json.dumps(
        {"version": "v001", "fps": 25, "clips": clips, "plan": "edit/cut-plan-v001.json",
         "voice": "audio/voice-v001.wav"}))
    (d / "work" / "words-v001.json").write_text(json.dumps(WORDS))
    return d


def spec(short_ep, name="pieces-v001.json", **kw):
    s = {"source_episode": "010-src", "size": [90, 160],
         "pieces": [{"id": "p1", "from_word": "One", "to_word": "two."}, {"id": "p2", "from": 2.1, "to": 2.9}]}
    s.update(kw)
    p = short_ep / "edit" / name
    p.write_text(json.dumps(s))
    return p


class FakeEngine:
    def words(self, samples):
        return [{"w": "One", "s": 0.1, "e": 0.62}, {"w": "two.", "s": 1.1, "e": 1.62},
                {"w": "Three", "s": 1.88, "e": 2.3}, {"w": "fo", "s": 2.42, "e": 2.5}]   # a foreign syllable

    def describe(self):
        return {"model": "fake"}


# ---- planning ----------------------------------------------------------------------------------------------------
def test_crop_box_around_the_face():
    assert short.crop_box(3840, 2160, [0.55, 0.4]) == [1504, 0, 1216, 2160]
    assert short.crop_box(3840, 2160, [0.99, 0.4]) == [3840 - 1216, 0, 1216, 2160]     # kept inside the frame
    x, y, w, h = short.crop_box(3840, 2160, [0.5, 0.4], zoom=1.25)
    assert (w, h) == (972, 1728) and y == round(0.4 * 2160 - 1728 * 0.4)
    assert short.crop_box(1080, 1920, [0.5, 0.4]) == [0, 0, 1080, 1920]                # upright: the whole frame
    assert short.face_in_crop([0.55, 0.4], (3840, 2160), [1504, 0, 1216, 2160]) == [0.5, 0.4]


def test_soft_warning_for_a_1080p_original():
    box = short.crop_box(1920, 1080, [0.5, 0.4])
    assert box[2] == 608
    msg = short.soft_warning("originals/a.mov", (1920, 1080), box, short.OUT_SIZE)
    assert "608x1080" in msg and "soft" in msg
    assert short.soft_warning("x", (3840, 2160), short.crop_box(3840, 2160, [0.5, 0.4]), short.OUT_SIZE) is None


def test_phrase_search_and_word_loading(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"words": [{"word": " The", "start": 1.0}, {"word": "ranking,", "start": 1.3, "end": 1.6}]}))
    w = short.load_words(p)
    assert w[0]["e"] == 1.3 and w[1]["w"] == "ranking,"
    assert short.find_phrase(w, "the Ranking", 0, "x") == (0, 1)
    with pytest.raises(common.CutError, match="not found"):
        short.find_phrase(w, "ranking", 2.0, "piece p1")


def test_face_comes_from_spec_cut_selects_or_zoom():
    c = {"source": "a", "zoom": 1.25, "zoom_center": [0.6, 0.2]}
    assert short.face_for(c, {"a": [0.3, 0.3]}, {"a": [0.7, 0.4]}, 0.4) == ([0.3, 0.3], "spec")
    assert short.face_for({**c, "face": [0.2, 0.5]}, {}, {"a": [0.7, 0.4]}, 0.4) == ([0.2, 0.5], "cut")
    assert short.face_for(c, {}, {"a": [0.7, 0.4]}, 0.4) == ([0.7, 0.4], "selects")
    face, how = short.face_for(c, {}, {}, 0.4)
    assert how == "zoom centre" and face == [round(0.6 * 0.2 + 0.4, 3), round(0.2 * 0.2 + 0.32, 3)]
    assert short.face_for({"source": "a"}, {}, {}, 0.4) == ([0.5, 0.4], "default")


def test_prepare_maps_pieces_back_to_the_original(studio):
    source_episode(studio, media=False)
    ep = make_episode(studio, "S001-clip", "portrait")
    plan = short.prepare(spec(ep), ep, probe=lambda p: UHD)
    p1, p2 = plan["pieces"]
    assert (p1["from"], p1["to"], p1["frames"]) == (0.12, 1.88, 44)      # pads, rounded to frames
    assert p1["clip"] == "s1" and p1["text"] == "One two." and p1["face_from"] == "selects"
    assert p2["clip"] == "s2" and p2["source_from"] == pytest.approx(3.12) and p2["frames"] == 20
    assert p2["short_from"] == pytest.approx(1.76) and plan["seconds"] == pytest.approx(2.56)
    assert plan["voice"] == "audio/voice-v001.wav" and plan["version"] == "v001" and not plan["soft"]


def test_piece_over_a_cut_boundary_is_refused(studio):
    source_episode(studio, media=False)
    ep = make_episode(studio, "S001-clip", "portrait")
    p = spec(ep, pieces=[{"id": "long", "from_word": "two.", "to_word": "Three"}])
    with pytest.raises(common.CutError, match=r"piece long crosses the cut boundary at 2\.00 s .*s1 and s2"):
        short.prepare(p, ep, probe=lambda p: UHD)
    p = spec(ep, name="pieces-v002.json", pieces=[{"id": "x", "from": 1.5, "to": 2.5}])
    with pytest.raises(common.CutError, match="piece x crosses"):
        short.prepare(p, ep, probe=lambda p: UHD)


def test_small_original_is_soft_before_anything_is_built(studio, capsys, monkeypatch):
    source_episode(studio, media=False)
    ep = make_episode(studio, "S001-clip", "portrait")
    p = spec(ep, size=None)
    plan = short.prepare(p, ep, probe=lambda p: HD)
    assert plan["soft"] and "608x1080" in plan["soft"][0]
    from crewcut.cut import media
    monkeypatch.setattr(media, "probe", lambda p: HD)
    assert cli.main(["cut", "short", str(p), "--words", "carry"]) == 2
    assert "Nothing built" in capsys.readouterr().err
    assert not (ep / "work" / "short-v001").exists()


def test_word_check_finds_shifted_times():
    import numpy as np
    levels = np.full(300, -70.0)
    levels[50:100] = -20.0                          # sound 0.5-1.0 s
    good = short.word_check([{"w": "a", "s": 0.5, "e": 1.0}], levels, -70.0)
    assert good["ok"] and good["largest_offset_s"] == 0.0
    off = short.word_check([{"w": "a", "s": 0.1, "e": 0.45}], levels, -70.0)
    assert not off["ok"] and "fixed seconds" in off["message"]


def test_edge_words_compare_first_and_last_word():
    pieces = [{"id": "p1", "text": "One two.", "short_from": 0.0, "short_to": 1.8}]
    heard = [{"w": "One", "s": 0.1, "e": 0.5}, {"w": "two", "s": 1.0, "e": 1.4}, {"w": "thr", "s": 1.6, "e": 1.75}]
    assert short.edge_words(pieces, heard) == [{"piece": "p1", "side": "end", "at": 1.8, "expected": "two",
                                                "heard": "thr"}]


# ---- the build (real ffmpeg on tiny files) -----------------------------------------------------------------------
@needs_ffmpeg
def test_build_from_the_clean_voice_with_new_words(studio):
    source_episode(studio)
    ep = make_episode(studio, "S001-clip", "portrait")
    plan = short.prepare(spec(ep), ep)
    assert plan["pieces"][0]["crop"] == [173, 0, 102, 180]
    r = short.build_short(plan, ep, "new", FakeEngine, log=lambda m: None)
    from crewcut.cut import build, media
    speaker = ep / r["speaker"]
    assert r["speaker"] == "work/speaker-v001.mov" and build.probe_frames(speaker) == 64
    v = media.video_stream(media.probe(speaker))
    assert (v["width"], v["height"]) == (90, 160)
    assert abs(r["voice"]["measured_lufs"] - r["voice"]["lufs"]) <= 0.6, r["voice"]  # on target after the limiter
    assert r["voice"]["from"] == "audio/voice-v001.wav"
    words = json.loads((ep / "work" / "words-v001.json").read_text())
    assert [w["w"] for w in words] == ["One", "two.", "Three", "fo"]
    assert r["words"]["mode"] == "new" and r["words"]["carried_check"]["ok"]
    assert r["words"]["edge_issues"] == [{"piece": "p2", "side": "end", "at": 2.56, "expected": "three",
                                          "heard": "fo"}]
    assert any("expected «three», heard «fo»" in x["what"] for x in r["listen"])
    assert {"at": 1.76, "what": "join p1 -> p2: no foreign syllable, no clipped word, the breath sounds natural"} \
        in r["listen"]
    rep = json.loads((ep / "work" / "short-cut-v001.json").read_text())
    assert rep["pieces"][1]["face"] == [0.5, 0.4] and rep["edges"]
    with pytest.raises(common.CutError, match="exists already"):
        short.build_short(short.prepare(spec(ep), ep), ep, "new", FakeEngine, log=lambda m: None)


@needs_ffmpeg
def test_build_from_the_camera_sound_with_carried_words(studio, capsys):
    source_episode(studio)
    ep = make_episode(studio, "S001-clip", "portrait")
    p = spec(ep, name="pieces-v003.json", voice=None, pieces=[{"id": "p1", "from_word": "One", "to_word": "two."}])
    assert cli.main(["cut", "short", str(p), "--words", "carry", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["voice"]["from"] == "camera" and r["words"]["mode"] == "carry"
    words = json.loads((ep / "work" / "words-v003.json").read_text())
    assert words[0] == {"w": "One", "s": 0.08, "e": 0.58}           # moved onto the Short's timeline
    assert r["words"]["check"]["ok"], r["words"]["check"]
    assert (ep / "audio" / "voice-v003.wav").is_file() and (ep / "work" / "speaker-v003.mov").is_file()


def test_dry_run_builds_nothing(studio, capsys, monkeypatch):
    source_episode(studio, media=False)
    ep = make_episode(studio, "S001-clip", "portrait")
    from crewcut.cut import media
    monkeypatch.setattr(media, "probe", lambda p: UHD)
    assert cli.main(["cut", "short", str(spec(ep)), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "p1" in out and "2.56 s" in out
    assert not (ep / "work" / "short-v001").exists()


def test_edge_levels_flag_sound_at_a_piece_edge():
    import numpy as np
    levels = np.full(400, -60.0)
    levels[190:215] = -15.0                     # speech runs over the edge at 2.0 s
    pieces = [{"id": "p1", "short_from": 0.0, "short_to": 2.0}, {"id": "p2", "short_from": 2.0, "short_to": 4.0}]
    edges = short.edge_levels(levels, -60.0, pieces)
    assert [(e["piece"], e["side"], e["loud"]) for e in edges] == [
        ("p1", "start", False), ("p1", "end", True), ("p2", "start", True), ("p2", "end", False)]
