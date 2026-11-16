"""The command line: exit codes and the commands that need no media program."""

import json
import wave

import numpy as np

from crewcut.cut import cli, common, islands, transcribe


def test_usage_errors_exit_2(capsys):
    assert cli.main(["cut"]) == 2
    assert cli.main(["cut", "nonsense"]) == 2
    assert cli.main(["--help"]) == 0


def test_ingest_with_nothing_to_do(episode, capsys):
    assert cli.main(["ingest", "001-test"]) == 2
    assert cli.main(["ingest", "001-test", "missing.MP4"]) == 1
    assert "file not found" in capsys.readouterr().err


def test_takes_writes_a_draft_and_the_report(episode, capsys):
    (episode / "brief" / "SCRIPT-v001.md").write_text("# T\n\nSo I built it myself. It works.\n")
    (episode / "originals" / "a-C0001.MP4").write_bytes(b"x")
    rows = [{"start": 0.0, "end": 0.9, "text": "So I built"}, {"start": 1.3, "end": 3.0, "text": "So I built it myself."},
            {"start": 3.4, "end": 4.0, "text": "It works."}]
    (episode / "work" / "a-C0001-islands.json").write_text(json.dumps({"source": "originals/a-C0001.MP4",
                                                                       "islands": rows}))
    assert cli.main(["cut", "takes", "001-test", "--take", "originals/a-C0001.MP4"]) == 0
    sel = json.loads((episode / "edit" / "selects-v001.json").read_text())
    assert sel["takes"]["A"]["source"] == "originals/a-C0001.MP4"
    assert sel["selects"] == [{"id": "s01-02", "take": "A", "start": 1.3, "end": 4.0,
                               "text": "So I built it myself. It works."}]
    assert (episode / "review" / "takes-v001.json").exists()
    assert "last full attempt" in capsys.readouterr().out
    assert cli.main(["cut", "takes", "001-test", "--take", "originals/a-C0001.MP4", "--version", "v001"]) == 1


def _decisions(episode):
    clips = [{"id": "a", "expected_text": "One two.", "timeline_in_frame": 0, "timeline_out_frame": 50},
             {"id": "b", "expected_text": "Three.", "timeline_in_frame": 50, "timeline_out_frame": 75}]
    p = episode / "work" / "edit-decisions-v002.json"
    p.write_text(json.dumps({"version": "v002", "fps": 25, "clips": clips}))
    return p


def test_srt_never_overwrites(episode, capsys):
    p = _decisions(episode)
    assert cli.main(["cut", "srt", str(p), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["srt"] == "export/001-test-v002.srt" and out["cues"] == 2
    assert (episode / "export" / "001-test-v002.srt").read_text().startswith("1\n00:00:00,050")
    assert cli.main(["cut", "srt", str(p)]) == 1


def _selects(episode, **kw):
    (episode / "originals" / "a.MP4").write_bytes(b"x")
    cfg = {"version": "v001", "takes": {"A": {"source": "originals/a.MP4", "face": [0.5, 0.4]}},
           "selects": [{"id": "s1", "take": "A", "start": 1.0, "end": 3.0, "text": "Hello there."}]}
    cfg.update(kw)
    p = episode / "edit" / "selects-v001.json"
    p.write_text(json.dumps(cfg))
    return p


def test_plan_from_selects(episode, monkeypatch, capsys):
    p = _selects(episode)
    monkeypatch.setattr(islands, "prepare", lambda ep, src, ch=None: (None, [(0.0, 0.95), (3.1, 4.0)], None))
    monkeypatch.setattr(transcribe, "mic_channel_of", lambda src, info=None: 1)
    assert cli.main(["cut", "plan", str(p)]) == 0
    plan = json.loads((episode / "edit" / "cut-plan-v001.json").read_text())
    assert plan["cuts"][0]["start"] == 0.88 and plan["voice_filter"].startswith("pan=stereo|c0=c1|c1=c1")
    assert plan["selects"] == "edit/selects-v001.json"
    assert cli.main(["cut", "plan", str(p)]) == 1                       # never overwrites


def test_plan_problems_exit_2(episode, monkeypatch, capsys):
    p = _selects(episode, music_seconds=1.0)
    monkeypatch.setattr(islands, "prepare", lambda ep, src, ch=None: (None, [], None))
    monkeypatch.setattr(transcribe, "mic_channel_of", lambda src, info=None: None)
    assert cli.main(["cut", "plan", str(p)]) == 2
    assert "longer than the music" in capsys.readouterr().err
    assert not (episode / "edit" / "cut-plan-v001.json").exists()


def test_doubles_fast_exits_2_on_a_find(episode, capsys):
    p = _selects(episode)
    words = [{"w": "Hello", "s": 1.0, "e": 1.3}, {"w": "there", "s": 1.35, "e": 1.6},
             {"w": "Hello", "s": 2.0, "e": 2.3}, {"w": "there.", "s": 2.35, "e": 2.9}]
    (episode / "work" / "words-a.json").write_text(json.dumps(words))
    assert cli.main(["cut", "doubles", str(p), "--fast"]) == 2
    report = json.loads((episode / "review" / "doubles-v001.json").read_text())
    assert report["rows"][0]["select"] == "s1" and report["rows"][0]["double"]


def test_dips_alias_reads_the_prepared_wav(episode, capsys):
    (episode / "originals" / "a.MP4").write_bytes(b"x")
    raw = episode / "work" / "raw"
    raw.mkdir(parents=True)
    x = np.concatenate([np.full(8000, 0.3), np.zeros(1600), np.full(8000, 0.3)])
    with wave.open(str(raw / "a-16k.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    (raw / "a-silence.txt").write_text("0.5 0.6\n")
    assert cli.main(["cut", "islands", "dips", "001-test", "originals/a.MP4", "0.3", "0.8", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["dips"]) == 1 and abs(out["dips"][0]["start"] - 0.5) < 0.021


def test_waiting_exits_3_and_compute_errors_keep_their_code(episode, monkeypatch, capsys):
    src = episode / "originals" / "a.MP4"
    src.write_bytes(b"x")

    def wait(*a, **k):
        raise common.Waiting("waiting for your yes on card 7", 7)
    monkeypatch.setattr(transcribe, "transcribe_rented", wait)
    assert cli.main(["transcribe", str(src), "--rented"]) == 3

    class MissingKey(Exception):
        exit_code = 4
    monkeypatch.setattr(transcribe, "transcribe_rented", lambda *a, **k: (_ for _ in ()).throw(MissingKey("no key")))
    assert cli.main(["transcribe", str(src), "--rented"]) == 4


def test_transcribe_outside_an_episode_needs_a_target(tmp_path, capsys):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    assert cli.main(["transcribe", str(f)]) == 1
    assert "--episode or --out" in capsys.readouterr().err
