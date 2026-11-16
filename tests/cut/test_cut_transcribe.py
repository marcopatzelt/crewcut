"""Speech recognition wrapper: no model is loaded and no ffmpeg runs; fakes stand in for both."""

import json
import sys
import types

import numpy as np
import pytest

from crewcut import approvals
from crewcut.cut import common, transcribe


class W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class Seg:
    def __init__(self, words, text=""):
        self.words, self.text = words, text


def test_words_from_segments():
    segs = [Seg([W(" Hello", 0.123, 0.5), W(" ", 0.5, 0.6)]), Seg([W("world.", 0.7, 1.049)]), Seg(None)]
    assert transcribe.words_from_segments(segs, offset=10) == [{"w": "Hello", "s": 10.12, "e": 10.5},
                                                               {"w": "world.", "s": 10.7, "e": 11.05}]


def test_words_file_names():
    assert transcribe.words_name("audio/voice-v003.wav") == "words-v003.json"
    assert transcribe.words_name("originals/abc-C0795.MP4") == "words-abc-C0795.json"
    assert transcribe.words_name("work/raw/abc-C0795-16k.wav") == "words-abc-C0795.json"


def test_invented_phrases_are_flagged():
    words = [{"w": "and", "s": 1.0, "e": 1.1}, {"w": "Thanks", "s": 50.0, "e": 50.2}, {"w": "for", "s": 50.2, "e": 50.3},
             {"w": "watching!", "s": 50.3, "e": 50.6}]
    assert transcribe.suspects(words) == [{"at": 50.0, "text": "thanks for watching"}]
    assert transcribe.suspects([]) == []


def test_decode_command():
    cmd = transcribe.decode_cmd("take.MP4", channel=1, start=2.5, end=9.0)
    assert cmd[:8] == ["ffmpeg", "-nostdin", "-v", "error", "-ss", "2.500", "-to", "9.000"]
    assert cmd[cmd.index("-af") + 1] == "pan=mono|c0=c1" and cmd[-5:] == ["-f", "f32le", "-acodec", "pcm_f32le", "-"]
    assert "-af" not in transcribe.decode_cmd("x.wav")


def test_device_choice(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)          # not installed -> cpu
    assert transcribe.pick_device("auto") == ("cpu", "int8")
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 1))
    assert transcribe.pick_device("auto") == ("cuda", "float16")
    assert transcribe.pick_device("cpu") == ("cpu", "int8")
    with pytest.raises(common.CutError):
        transcribe.pick_device("tpu")


def test_settings_from_the_studio_config(studio):
    (studio / "config").mkdir()
    (studio / "config" / "speech.toml").write_text('[speech]\nmodel = "small"\n')
    assert transcribe.settings()["model"] == "small" and transcribe.settings()["beam_size"] == 5


def test_quiet_recordings_get_gain():
    quiet = np.full(16000, 0.01, dtype=np.float32)              # -40 dB
    louder, gain = transcribe.with_gain(quiet, -25.0, 14.0)
    assert gain == 14.0 and transcribe.level_db(louder) > transcribe.level_db(quiet) + 13
    normal = np.full(16000, 0.2, dtype=np.float32)
    assert transcribe.with_gain(normal, -25.0, 14.0)[1] == 0.0


def test_missing_library_is_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    e = transcribe.Engine(device="cpu", language="en")
    with pytest.raises(common.CutError, match="faster-whisper"):
        _ = e.model


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, samples, **kw):
        self.calls.append((len(samples), kw))
        if kw.get("word_timestamps"):
            return [Seg([W("Hi", 0.1, 0.3), W("there.", 0.35, 0.7)])], None
        return [Seg(None, " Hi "), Seg(None, "there. ")], None


def test_engine_reads_words_and_pads_pieces():
    e = transcribe.Engine(device="cpu", language="de")
    e._model = FakeModel()
    assert e.words(np.zeros(100, np.float32))[1] == {"w": "there.", "s": 0.35, "e": 0.7}
    assert e.text(np.zeros(100, np.float32)) == "Hi there."
    n, kw = e._model.calls[-1]
    assert n == 100 + 16000 and kw["without_timestamps"] and kw["language"] == "de" and not kw["vad_filter"]


def test_language_defaults_to_the_channel(monkeypatch):
    assert transcribe.Engine(device="cpu").language == "en"            # neutral pack


def test_transcribe_local_writes_words(episode, monkeypatch):
    src = episode / "audio" / "voice-v001.wav"
    src.write_bytes(b"x")
    monkeypatch.setattr(transcribe.media, "probe", lambda p: {"format": {}, "streams": [
        {"codec_type": "audio", "channels": 1}]})
    monkeypatch.setattr(transcribe, "load_audio", lambda p, ch=None: np.full(32000, 0.2, np.float32))
    e = transcribe.Engine(device="cpu", language="en")
    e._model = FakeModel()
    out, ep = transcribe.output_path(src, None, None)
    assert out == episode / "work" / "words-v001.json" and ep == episode
    r = transcribe.transcribe_local(src, out, e)
    assert r["words"] == 2 and r["audio_seconds"] == 2.0 and r["channel"] is None
    assert json.loads(out.read_text())[0] == {"w": "Hi", "s": 0.1, "e": 0.3}
    with pytest.raises(common.CutError, match="exists"):
        transcribe.transcribe_local(src, out, e)


def test_files_outside_an_episode_need_a_target(tmp_path):
    with pytest.raises(common.CutError):
        transcribe.output_path(tmp_path / "a.wav", None, None)
    assert transcribe.output_path(tmp_path / "a.wav", str(tmp_path / "w.json"), None)[0] == tmp_path / "w.json"


def test_rented_path_asks_first_then_runs(episode, monkeypatch):
    src = episode / "originals" / "abc-C0001.MP4"
    src.write_bytes(b"camera file")
    monkeypatch.setattr(transcribe.media, "probe", lambda p: {"format": {"duration": "120"}, "streams": [
        {"codec_type": "audio", "channels": 2}]})
    monkeypatch.setattr(transcribe, "mic_channel_of", lambda p, info=None: 1)
    ran = []

    def fake_run(argv, **kw):
        ran.append(argv)
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"flac audio only")
    monkeypatch.setattr(transcribe.media, "run", fake_run)

    class Machine:
        def put(self, files, remote):
            self.sent = files

        def run(self, cmd, timeout=None):
            self.cmd = cmd
            return 0, "ok"

        def get(self, remote, local):
            (local / "words.json").write_text(json.dumps([{"w": "Hi", "s": 0.1, "e": 0.3}]))

    machine = Machine()

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def rent(self, gpus=1, max_minutes=60):
            return [machine]
    fake = types.SimpleNamespace(session=lambda **kw: Session())
    import crewcut
    monkeypatch.setitem(sys.modules, "crewcut.compute", fake)
    monkeypatch.setattr(crewcut, "compute", fake, raising=False)

    out = episode / "work" / "words-abc-C0001.json"
    with pytest.raises(common.Waiting) as w:
        transcribe.transcribe_rented(src, out, episode, "large-v3-turbo", "en")
    card = approvals.get(w.value.card_id)
    assert card["kind"] == "other" and card["data"]["privacy"] == "audio_upload"
    assert card["file"] == "work/upload/abc-C0001-16k.flac"
    cmd = ran[0]
    assert cmd[cmd.index("-af") + 1] == "pan=mono|c0=c1" and "-vn" in cmd and "-map_metadata" in cmd
    with pytest.raises(common.Waiting):                       # still open: no second card
        transcribe.transcribe_rented(src, out, episode, "large-v3-turbo", "en")
    assert len(approvals.list_cards(episode="001-test")) == 1
    approvals.decide(card["id"], accepted=True)
    r = transcribe.transcribe_rented(src, out, episode, "large-v3-turbo", "en")
    assert r["rented"] and r["words"] == 1 and json.loads(out.read_text())[0]["w"] == "Hi"
    assert [p.name for p in machine.sent] == ["abc-C0001-16k.flac"]
    assert "--device cuda" in machine.cmd and "crewcut.cut.cli transcribe" in machine.cmd


def test_declined_upload_is_refused(episode, monkeypatch):
    f = episode / "work" / "upload" / "a.flac"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"a")
    status, cid = transcribe.upload_consent("001-test", "work/upload/a.flac", approvals.sha256(f), "t", "b")
    approvals.decide(cid, accepted=False)
    assert transcribe.upload_consent("001-test", "work/upload/a.flac", approvals.sha256(f), "t", "b") == (
        "declined", cid)
