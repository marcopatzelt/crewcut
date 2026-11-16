"""Speech islands: pieces between pauses, words placed into them, gaps of the fast way, level dips."""

import json
import wave

import numpy as np

from crewcut.cut import islands


def test_pieces_between_pauses():
    sil = [(0.0, 0.8), (2.0, 2.1), (2.3, 3.6)]
    assert islands.speech_pieces(sil, 5.0) == [(0.8, 2.0), (3.6, 5.0)]     # 2.1-2.3 is a click, not speech
    assert islands.speech_pieces(sil, 5.0, min_len=0.1) == [(0.8, 2.0), (2.1, 2.3), (3.6, 5.0)]
    assert islands.speech_pieces(sil, 5.0, start=1.0) == [(3.6, 5.0)]


def test_words_go_into_the_island_that_holds_their_middle():
    pieces = [(0.8, 2.0), (2.1, 3.0), (3.6, 5.0)]
    words = [{"w": "Hello", "s": 0.85, "e": 1.2}, {"w": "there.", "s": 1.3, "e": 1.9},
             {"w": "Next", "s": 2.05, "e": 2.4},                  # starts in the pause, middle inside
             {"w": "late", "s": 5.1, "e": 5.3},                   # just after the end: nearest within slack
             {"w": "lost", "s": 9.0, "e": 9.2}]
    rows, lost = islands.assign_words(pieces, words)
    assert [r["text"] for r in rows] == ["Hello there.", "Next", "late"]
    assert lost == 1 and rows[0]["source"] == "words"


def test_gaps_are_long_islands_without_words():
    rows = [{"start": 0, "end": 3, "text": ""}, {"start": 4, "end": 4.5, "text": ""}, {"start": 5, "end": 9, "text": "x"}]
    assert islands.gaps(rows) == [rows[0]]


def test_partial_run_replaces_only_its_range():
    old = [{"start": 1, "end": 2, "text": "a"}, {"start": 5, "end": 6, "text": "b"}, {"start": 9, "end": 10, "text": "c"}]
    new = [{"start": 5.1, "end": 6.2, "text": "B"}]
    assert [r["text"] for r in islands.merge_rows(old, new, 4, 8)] == ["a", "B", "c"]


def _tone_with_gap(tmp_path, rate=16000):
    t = np.arange(int(rate * 1.0)) / rate
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    x = np.concatenate([tone, np.zeros(int(rate * 0.1)), tone])     # 100 ms of silence at 1.0 s
    wav = tmp_path / "x-16k.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return wav


def test_dips_find_the_gap_between_two_words(tmp_path):
    wav = _tone_with_gap(tmp_path)
    assert abs(islands.wav_duration(wav) - 2.1) < 1e-6
    x, rate = islands.read_wav(wav)
    series = islands.rms_series(x, rate, 0.5, 1.6)
    dips = islands.usable_dips(series)
    assert len(dips) == 1
    assert abs(dips[0]["start"] - 1.0) < 0.021 and abs(dips[0]["end"] - 1.1) < 0.021 and dips[0]["min_db"] < -60


def test_a_dip_must_last_long_enough():
    series = [(0.0, -20.0), (0.02, -45.0), (0.04, -20.0)]
    assert islands.usable_dips(series) == []
    assert islands.usable_dips(series, min_len=0.02)[0]["start"] == 0.02


def test_extract_takes_the_microphone_channel(episode):
    cmd = islands.extract_cmd(episode / "originals" / "a.MP4", episode / "work" / "raw" / "a-16k.wav", 1)
    assert cmd[cmd.index("-af") + 1] == "pan=mono|c0=c1"
    assert cmd[-5:-1] == ["-ar", "16000", "-c:a", "pcm_s16le"]
    assert "-af" not in islands.extract_cmd("a", "b", None)


def test_build_with_words_and_fill(episode, monkeypatch, tmp_path):
    (episode / "originals" / "a-C0001.MP4").write_bytes(b"x")
    wav = _tone_with_gap(tmp_path)
    raw = episode / "work" / "raw"
    raw.mkdir(parents=True)
    (raw / "a-C0001-16k.wav").write_bytes(wav.read_bytes())
    (raw / "a-C0001-silence.txt").write_text("1.0 1.1\n")
    words = episode / "work" / "words-a-C0001.json"
    words.write_text(json.dumps([{"w": "Hello", "s": 0.1, "e": 0.6}]))

    class FakeEngine:
        def text(self, samples):
            return f"read {len(samples)}"
    r = islands.build(episode, "originals/a-C0001.MP4", words_file=words, fill=True, engine_factory=FakeEngine)
    assert [x["text"] for x in r["rows"]] == ["Hello", "read 16800"]        # 1.0 s + 2 x 0.05 s padding
    assert [x["source"] for x in r["rows"]] == ["words", "island"]
    data = json.loads((episode / r["islands"]).read_text())
    assert data["source"] == "originals/a-C0001.MP4" and data["words"] == "work/words-a-C0001.json"
    assert islands.load(episode, "originals/a-C0001.MP4") == data["islands"]
