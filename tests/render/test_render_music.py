"""Music bed: the licence rule, holes, argument lists and the loudness passes with a fake ffmpeg, then one real mix of
tiny sine-wave files (made with ffmpeg here) to check the level under the voice, the ducking, the hole and the
loudness roughly."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from render_helpers import loudness_text

from crewcut import brand
from crewcut.render import cli, music
from crewcut.render.music import Bed, MusicRefused
from crewcut.render.plan import PlanError

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


class FakeFfmpeg:
    """Answers ffprobe with a length, every loudness measurement with the next (lufs, peak) pair, and writes the
    output file of any other ffmpeg run."""

    def __init__(self, lengths=(10.0, 30.0), loud=((-30.0, -20.0), (-25.0, -12.0), (-18.0, -6.0), (-12.6, -1.0),
                                                    (-14.1, -1.8))):
        self.calls: list[list[str]] = []
        self.lengths, self.loud = list(lengths), list(loud)

    def __call__(self, cmd, timeout=600, cwd=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if Path(cmd[0]).name.startswith("ffprobe"):
            return 0, f"{self.lengths.pop(0)}\n"
        if any("ebur128=peak=true" in c for c in cmd):
            lufs, peak = self.loud.pop(0)
            return 0, loudness_text(lufs, peak)
        Path(cmd[-1]).write_bytes(b"RIFF")
        return 0, ""


def files(tmp_path, source=None):
    voice, track = tmp_path / "voice.wav", tmp_path / "song.wav"
    voice.write_bytes(b"x")
    track.write_bytes(b"y")
    if source is not None:
        (tmp_path / "song.source.json").write_text(json.dumps(source))
    return voice, track


def test_refuses_a_track_without_licence(tmp_path):
    voice, track = files(tmp_path)
    run = FakeFfmpeg()
    with pytest.raises(MusicRefused, match="no licence stated.*clear rights"):
        music.music_bed(voice, track, runner=run, bed=Bed())
    for empty in ("", "unknown", "Unclear.", " n/a "):
        (tmp_path / "song.source.json").write_text(json.dumps({"licence": empty, "credit": "x"}))
        with pytest.raises(MusicRefused):
            music.source_info(track)
    assert run.calls == []                                   # refused before any program ran
    with pytest.raises(MusicRefused):                        # an explicit source dict is checked too
        music.music_bed(voice, track, source={"credit": "x"}, runner=run, bed=Bed())
    assert run.calls == []
    (tmp_path / "song.source.json").write_text(json.dumps({"license": "CC-BY 4.0", "credit": "Music: A", "made": "b"}))
    info = music.source_info(track)
    assert info["licence"] == "CC-BY 4.0" and "license" not in info and info["source_file"].endswith("song.source.json")
    assert music.source_info(track, licence="CC0 1.0")["licence"] == "CC0 1.0"         # given values win
    with pytest.raises(PlanError, match="not found"):
        music.source_info(track, tmp_path / "missing.json")


def test_cli_refusal_and_usage(tmp_path, capsys):
    voice, track = files(tmp_path)
    assert cli.main(["music-bed", str(voice), "--music", str(track)]) == 1
    assert "no licence stated" in capsys.readouterr().err
    assert cli.main(["music-bed", str(voice)]) == 2           # --music is required
    assert cli.main(["music-bed", str(voice), "--music", str(tmp_path / "nope.wav"), "--licence", "CC0"]) == 1
    assert "not found" in capsys.readouterr().err


def test_bed_values_from_pack(studio):
    b = Bed.from_pack(brand.load())
    assert (b.music_db, b.hole_s, b.tail_s, b.lufs, b.headroom_db, b.true_peak_db) == (-15.0, 0.5, 1.0, -14.0, 1.4, -1.5)
    b = Bed.from_pack(brand.load(), music_db=-18, hole_s=None, lufs=-16)
    assert (b.music_db, b.hole_s, b.lufs) == (-18.0, 0.5, -16.0)


def test_holes_and_expression():
    assert music.holes([8.0, 3.2], 0.5, 10) == [(2.7, 3.2), (7.5, 8.0)]
    assert music.holes([0.3], 0.5, 10) == [(0.0, 0.3)]
    with pytest.raises(PlanError, match="outside the Short"):
        music.holes([12.0], 0.5, 10)
    assert music.hole_expr([]) == "1"
    assert music.hole_expr([(7.5, 8.0)]) == "1-0.95*clip(min((t-7.450)/0.05,(8.050-t)/0.05),0,1)"
    two = music.hole_expr([(2.7, 3.2), (7.5, 8.0)])
    assert two.startswith("1-0.95*max(clip(") and two.count("clip(") == 2
    assert music.duck_threshold(-14.0) == pytest.approx(10 ** (-28 / 20)) and music.duck_threshold(-90) == 0.001


def test_mix_and_master_commands(tmp_path):
    bed = Bed()
    cmd = music.mix_cmd(tmp_path / "v.wav", tmp_path / "m.wav", 12.0, 11.0, -6.5, 0.04, [(7.5, 8.0)], bed, True,
                        tmp_path / "x.wav")
    i = cmd.index("-stream_loop")
    assert cmd[i:i + 5] == ["-stream_loop", "-1", "-ss", "12.000", "-i"] and cmd[i + 5] == str(tmp_path / "m.wav")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur=11.000" in fc
    assert "volume=-6.50dB,asetnsamples=n=480:p=0,volume=volume='1-0.95*clip(" in fc and "':eval=frame" in fc
    assert "afade=t=in:d=0.500,afade=t=out:st=9.800:d=1.200[mu]" in fc
    assert "[mu][key]sidechaincompress=threshold=0.04000:ratio=2:attack=25:release=450:makeup=1[duck]" in fc
    assert fc.endswith("[vo][duck]amix=inputs=2:normalize=0:duration=first[mix]")
    assert cmd[-3:] == ["-t", "11.000", str(tmp_path / "x.wav")] and "pcm_f32le" in cmd
    plain = music.mix_cmd(tmp_path / "v.wav", tmp_path / "m.wav", 0.0, 11.0, 0, 0.04, [], bed, False, tmp_path / "x.wav")
    assert "-stream_loop" not in plain and "-ss" not in plain and "eval=frame" not in " ".join(plain)
    m = music.master_cmd(tmp_path / "x.wav", 3.1, -2.0, tmp_path / "o.wav")
    assert m[m.index("-af") + 1] == f"volume=3.10dB,alimiter=limit={10 ** (-2 / 20):.4f}:level=false"
    assert "pcm_s24le" in m


def test_loudness_passes_and_source_file(tmp_path):
    voice, track = files(tmp_path, {"licence": "CC0 1.0", "credit": "Music: Test Band", "made": "recorded 2026",
                                    "title": "Song"})
    run = FakeFfmpeg()
    logs: list[str] = []
    info = music.music_bed(voice, track, punches=[8.0], start=2.0, bed=Bed(), runner=run, log=logs.append)
    out = tmp_path / "voice-bed-v001.wav"
    assert info["output"] == str(out) and out.is_file()
    assert not list(tmp_path.glob("*.mix.wav")) and not list(tmp_path.glob("*.tmp.wav"))
    bed = info["bed"]
    assert info["seconds"] == 11.0 and info["loops"] is False and info["start_s"] == 2.0
    assert bed["voice_lufs"] == -30.0 and bed["music_lufs"] == -25.0 and bed["music_gain_db"] == -20.0   # -30-15+25
    # the first pass aims 1.4 dB over the target (-18 measured -> +5.4 dB), the second corrects by the miss (-12.6)
    assert [p["gain_db"] for p in bed["passes"]] == [5.4, 4.0]
    assert info["lufs"] == -14.1 and info["true_peak"] == -1.8 and info["notes"] == []
    side = json.loads((tmp_path / "voice-bed-v001.music.json").read_text())
    assert side["licence"] == "CC0 1.0" and side["credit"] == "Music: Test Band" and side["made"] == "recorded 2026"
    assert side["track"] == str(track) and len(side["track_sha256"]) == 64 and side["source_extra"] == {"title": "Song"}
    assert side["bed"]["holes"] == [[7.5, 8.0]] and any("music hole" in x for x in side["listen"])
    measure = run.calls[3]                                   # lengths, voice, then the track's part
    assert measure[measure.index("-ss") + 1] == "2.000" and measure[measure.index("-t") + 1] == "11.000"
    assert music.next_bed(voice).name == "voice-bed-v002.wav"
    with pytest.raises(PlanError, match="never overwritten"):
        music.music_bed(voice, track, out, bed=Bed(), runner=FakeFfmpeg())


def test_short_track_loops_and_peak_lowers_limiter(tmp_path):
    voice, track = files(tmp_path, {"licence": "CC0"})
    run = FakeFfmpeg(lengths=(10.0, 6.0), loud=((-30.0, -20.0), (-25.0, -12.0), (-18.0, -6.0), (-14.0, -0.6),
                                                 (-14.2, -1.6)))
    info = music.music_bed(voice, track, bed=Bed(), runner=run, log=lambda *a: None)
    assert info["loops"] is True and any("loop" in x for x in info["listen"])
    mix = next(c for c in run.calls if "-filter_complex" in c)
    assert "-stream_loop" in mix
    limits = [p["limit_db"] for p in info["bed"]["passes"]]
    assert limits[0] == -2.0 and limits[1] == pytest.approx(-2.0 - (1.5 - 0.6) - 0.2)
    assert any("credit" in n for n in info["notes"])          # no credit line given


def _level(path: Path, a: float, b: float, band: str) -> float:
    r = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-af",
                        f"atrim=start={a}:end={b},{band},{band},volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr).group(1))


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
def test_real_mix_of_sine_waves(tmp_path):
    ff = shutil.which("ffmpeg")
    voice, track = tmp_path / "voice.wav", tmp_path / "tone.wav"
    # the "voice": 1 kHz, speaking from 1 to 4 s of 10 s; the "music": 150 Hz, 20 s, louder than the voice
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=f=1000:d=10:sample_rate=48000", "-af",
                    "volume=enable='lt(t,1)+gt(t,4)':volume=0", str(voice)], check=True)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=f=150:d=20:sample_rate=48000", "-ac", "2",
                    "-af", "volume=3", str(track)], check=True)
    info = music.music_bed(voice, track, punches=[8.0], start=2.0, bed=Bed(),
                           source={"licence": "CC0 1.0", "credit": "Music: test tone"}, log=lambda *a: None)
    out = Path(info["output"])
    low, high = "lowpass=f=400", "highpass=f=600"              # music band, voice band
    speech, calm, hole, back = (1.5, 3.5), (4.5, 6.5), (7.6, 7.95), (8.2, 9.0)
    music_calm = _level(out, *calm, low)
    voice_lvl = _level(out, *speech, high)
    assert 12.0 <= voice_lvl - music_calm <= 17.5               # music about 15 dB under the voice
    assert music_calm - _level(out, *speech, low) >= 3.0         # ducked while the voice speaks
    assert music_calm - _level(out, *hole, low) >= 20.0          # the hole before the punchline
    assert abs(_level(out, *back, low) - music_calm) <= 1.0      # back on the punchline
    assert abs(info["lufs"] - (-14.0)) <= 0.6 and info["true_peak"] <= -1.5
    assert info["seconds"] == 11.0                               # voice plus the 1 s tail
    side = json.loads(out.with_name(out.stem + ".music.json").read_text())
    assert side["licence"] == "CC0 1.0" and side["start_s"] == 2.0
