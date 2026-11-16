"""Ingest: split recordings, saving originals, the report. ffprobe and ffmpeg are replaced by fakes."""

import json

import pytest

from crewcut.cut import common, ingest

# Values of three real camera files: two parts of one recording, then a pickup three hours later.
C0795 = {"name": "C0795.MP4", "bytes": 4181874329, "created": "2026-01-10T10:00:00Z", "duration": 568.32}
C0796 = {"name": "C0796.MP4", "bytes": 4160901712, "created": "2026-01-10T10:09:28Z", "duration": 564.0}
C0797 = {"name": "C0797.MP4", "bytes": 1459673670, "created": "2026-01-10T13:21:56Z", "duration": 197.28}


def test_camera_split_at_4_gb_is_one_recording():
    groups = ingest.split_groups([C0795, C0796, C0797])
    assert [g["files"] for g in groups] == [["C0795.MP4", "C0796.MP4"], ["C0797.MP4"]]
    assert "4 GB" in groups[0]["reason"] and groups[1]["reason"] is None


def test_consecutive_numbers_with_a_time_gap_are_two_recordings():
    late = dict(C0796, created="2026-01-10T10:25:00Z")
    assert [g["files"] for g in ingest.split_groups([C0795, late])] == [["C0795.MP4"], ["C0796.MP4"]]


def test_small_first_file_is_not_a_split():
    small = dict(C0795, bytes=900_000_000)
    assert len(ingest.split_groups([small, C0796])) == 2


def test_without_times_name_and_size_say_probably():
    a = {"name": "MVI_0041.MOV", "bytes": 4_294_000_000}
    b = {"name": "MVI_0042.MOV", "bytes": 1_000_000}
    g = ingest.split_groups([b, a])
    assert g == [{"files": ["MVI_0041.MOV", "MVI_0042.MOV"], "index": [1, 0], "reason": g[0]["reason"]}]
    assert g[0]["reason"].startswith("probably")


def test_gopro_chapters_and_other_cameras():
    files = [{"name": "GH010123.MP4", "bytes": 4_000_000_000}, {"name": "GH020123.MP4", "bytes": 100},
             {"name": "GH010124.MP4", "bytes": 100}, {"name": "notes.txt", "bytes": 3}]
    assert [g["files"] for g in ingest.split_groups(files)] == [["GH010123.MP4", "GH020123.MP4"], ["GH010124.MP4"],
                                                                ["notes.txt"]]


def test_original_names():
    assert ingest.original_name("ab" * 32, "My Take (1).MP4") == "abababababab-My_Take_1_.MP4"
    assert ingest.safe_name("../../etc/passwd") == "passwd"


def _fakes(monkeypatch, mic=None, tail=None, audio_streams=True):
    probe = {"format": {"duration": "12.5", "tags": {"creation_time": "2026-01-10T10:00:00.000000Z"}},
             "streams": [{"codec_type": "video", "width": 1920, "height": 1080}]
             + ([{"codec_type": "audio", "channels": 2}] if audio_streams else [])}
    monkeypatch.setattr(ingest.media, "probe", lambda p: probe)
    monkeypatch.setattr(ingest.audio, "mic_check", lambda p, d=None: mic or {
        "verdict": "external_one_side", "channel": 1, "message": "External microphone on the right channel."})
    monkeypatch.setattr(ingest.audio, "sound_to_end", lambda p, channels=2, duration=None: tail or {
        "verdict": "ok", "message": "Sound until 10 s of 12 s, then 2 s of silence."})


def test_ingest_copies_never_overwrites_and_reports(episode, tmp_path, monkeypatch):
    _fakes(monkeypatch)
    card = tmp_path / "card"
    card.mkdir()
    src = card / "C0001.MP4"
    src.write_bytes(b"picture and sound" * 100)
    r = ingest.ingest("001-test", [src])
    f = r["files"][0]
    assert f["status"] == "copied" and src.exists()          # the card is never changed
    saved = episode / f["file"]
    assert saved.read_bytes() == src.read_bytes() and saved.name.endswith("-C0001.MP4")
    assert f["sha256"] == ingest.sha256_file(src) and f["created"].startswith("2026-01-10T10:00:00")
    assert not list((episode / "originals").glob(".*.part"))
    report = json.loads((episode / r["report"]).read_text())
    assert report["files"][0]["mic_check"]["channel"] == 1 and report["warnings"] == []
    again = ingest.ingest("001-test", [src])
    assert again["files"][0]["status"] == "already saved"
    assert len(list((episode / "brief").glob("ingest-*.json"))) == 2


def test_inbox_files_are_moved(episode, studio, monkeypatch):
    _fakes(monkeypatch)
    inbox = studio / "inbox" / "001-test"
    inbox.mkdir(parents=True)
    (inbox / "take.mov").write_bytes(b"x" * 1000)
    (inbox / ".hidden").write_bytes(b"x")
    files = ingest.inbox_files("001-test")
    assert [p.name for p in files] == ["take.mov"]
    r = ingest.ingest("001-test", files)
    assert r["files"][0]["status"] == "moved" and not (inbox / "take.mov").exists()
    assert r["files"][0]["source"] == "inbox/001-test/take.mov"


def test_warnings_for_a_silent_tail_and_no_sound(episode, tmp_path, monkeypatch):
    _fakes(monkeypatch, tail={"verdict": "silent_tail", "message": "WARNING: the last 110 s are silent"})
    src = tmp_path / "C0002.MP4"
    src.write_bytes(b"y" * 10)
    r = ingest.ingest("001-test", [src])
    assert r["warnings"] == ["C0002.MP4: WARNING: the last 110 s are silent"]
    _fakes(monkeypatch, audio_streams=False)
    src2 = tmp_path / "C0003.MP4"
    src2.write_bytes(b"z" * 10)
    r = ingest.ingest("001-test", [src2])
    assert r["warnings"] == ["C0003.MP4: WARNING: no sound track."]
    assert r["files"][0]["mic_check"] is None


def test_split_is_found_across_ingests(episode, tmp_path, monkeypatch):
    _fakes(monkeypatch)
    a, b = tmp_path / "C0795.MP4", tmp_path / "C0796.MP4"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    probes = {
        "C0795.MP4": {"format": {"duration": "568.32", "tags": {"creation_time": "2026-01-10T10:00:00Z"}},
                      "streams": [{"codec_type": "video"}, {"codec_type": "audio", "channels": 2}]},
        "C0796.MP4": {"format": {"duration": "564.0", "tags": {"creation_time": "2026-01-10T10:09:28Z"}},
                      "streams": [{"codec_type": "video"}, {"codec_type": "audio", "channels": 2}]},
    }
    monkeypatch.setattr(ingest.media, "probe", lambda p: probes[p.name.split("-", 1)[-1]])
    monkeypatch.setattr(ingest, "SPLIT_MIN_BYTES", 0)       # the test files are tiny
    ingest.ingest("001-test", [a])
    r = ingest.ingest("001-test", [b])
    assert any(len(g["files"]) == 2 for g in r["recordings"])
    assert any("one recording" in n for n in r["notes"])


def test_refuses_files_without_picture_or_sound(episode, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest.media, "probe", lambda p: {"format": {}, "streams": []})
    src = tmp_path / "notes.txt"
    src.write_text("hi")
    with pytest.raises(common.CutError):
        ingest.ingest("001-test", [src])
    assert not list((episode / "originals").iterdir())


def test_unknown_episode(tmp_path):
    with pytest.raises(common.CutError):
        ingest.ingest("999-none", [])
