"""Parsing of ffmpeg's measurement output, and the sound verdicts. No ffmpeg runs here."""

import pytest

from crewcut.cut import audio

VOLUMEDETECT = """\
[Parsed_volumedetect_2 @ 0x55d5c8a0a8c0] n_samples: 5760000
[Parsed_volumedetect_2 @ 0x55d5c8a0a8c0] mean_volume: -19.4 dB
[Parsed_volumedetect_2 @ 0x55d5c8a0a8c0] max_volume: -2.1 dB
[Parsed_volumedetect_1 @ 0x55d5c8a0a580] n_samples: 5760000
[Parsed_volumedetect_1 @ 0x55d5c8a0a580] mean_volume: -61.5 dB
[Parsed_volumedetect_1 @ 0x55d5c8a0a580] max_volume: -48.0 dB
"""

ASTATS = "".join(f"frame:{i}    pts:{i * 480000}   pts_time:{i * 10}\nlavfi.astats.Overall.RMS_level={v}\n"
                 for i, v in enumerate(["-22.3", "-21.9", "-20.5", "-63.1", "-63.4", "-inf"]))

SILENCE = """\
[silencedetect @ 0x5600] silence_start: -0.002
[silencedetect @ 0x5600] silence_end: 0.81 | silence_duration: 0.812
[silencedetect @ 0x5600] silence_start: 146.3
[silencedetect @ 0x5600] silence_end: 146.33 | silence_duration: 0.03
[silencedetect @ 0x5600] silence_start: 560.12
"""

EBUR128 = """\
[Parsed_ebur128_0 @ 0x5581] t: 211.9  TARGET:-23 LUFS    M: -18.2 S: -16.0     I: -16.1 LUFS       LRA:   1.7 LU
[Parsed_ebur128_0 @ 0x5581] Summary:

  Integrated loudness:
    I:         -14.2 LUFS
    Threshold: -24.5 LUFS

  Loudness range:
    LRA:         5.3 LU
    Threshold:   -34.5 LUFS
    LRA low:     -19.0 LUFS
    LRA high:    -13.7 LUFS

  True peak:
    Peak:        -0.6 dBFS
"""

LOUDNORM = """\
[Parsed_loudnorm_7 @ 0x55] \n{
\t"input_i" : "-17.91",
\t"input_tp" : "0.09",
\t"input_lra" : "1.80",
\t"input_thresh" : "-27.95",
\t"output_i" : "-16.10",
\t"output_tp" : "-2.00",
\t"output_lra" : "1.70",
\t"output_thresh" : "-26.13",
\t"normalization_type" : "dynamic",
\t"target_offset" : "0.10"
}
"""


def test_channel_levels_are_ordered_left_then_right():
    assert audio.parse_channel_levels(VOLUMEDETECT) == [-61.5, -19.4]


def test_radio_mic_on_one_side_is_found():
    v = audio.mic_verdict([-61.5, -19.4])
    assert v["verdict"] == "external_one_side" and v["channel"] == 1 and "right" in v["message"]


def test_only_the_camera_mic_is_a_warning():
    v = audio.mic_verdict([-31.0, -32.2])
    assert v["verdict"] == "camera_mic_suspected" and v["message"].startswith("WARNING")


def test_loud_stereo_is_fine_and_mono_is_unknown():
    assert audio.mic_verdict([-18.0, -19.0])["verdict"] == "stereo"
    assert audio.mic_verdict([-18.0])["verdict"] == "unknown"


def test_rms_parsing_maps_digital_silence():
    assert audio.parse_rms(ASTATS) == [-22.3, -21.9, -20.5, -63.1, -63.4, -99.0]


def test_silent_tail_from_a_real_case():
    # A real episode: the radio microphone stopped 110 s before the end; both channels about -63 dB.
    left = [-60.0] * 46 + [-63.0] * 11
    right = [-20.0] * 45 + [-25.0] + [-63.0] * 11
    r = audio.silent_tail(left, right, window=10, duration=564.0)
    assert r["verdict"] == "silent_tail"
    assert r["last_sound_at_seconds"] == 460.0 and r["silent_tail_seconds"] == 104.0
    assert "460" in r["message"] and "564" in r["message"] and r["message"].startswith("WARNING")


def test_a_short_quiet_end_is_normal():
    r = audio.silent_tail([-20.0] * 10 + [-60.0] * 2, window=10)
    assert r["verdict"] == "ok" and r["silent_tail_seconds"] == 20.0


def test_no_levels_is_unknown():
    assert audio.silent_tail([])["verdict"] == "unknown"


def test_silences_with_open_end_and_negative_start():
    assert audio.parse_silences(SILENCE) == [(0.0, 0.81), (146.3, 146.33)]
    assert audio.parse_silences(SILENCE, duration=564.0)[-1] == (560.12, 564.0)


def test_silence_file_round_trip():
    sil = [(0.0, 0.81), (146.3, 146.33)]
    assert audio.read_silences(audio.format_silences(sil)) == sil


def test_ebur128_summary():
    m = audio.parse_ebur128(EBUR128)
    assert m["integrated_lufs"] == -14.2 and m["threshold_lufs"] == -24.5
    assert m["lra_lu"] == 5.3 and m["lra_low_lufs"] == -19.0 and m["lra_high_lufs"] == -13.7
    assert m["true_peak_dbtp"] == -0.6


def test_loudness_problems_against_targets():
    m = audio.parse_ebur128(EBUR128)
    assert audio.loudness_problems(m, -14.0, -1.5) == ["true peak -0.6 dBTP is above -1.5 dBTP"]
    assert len(audio.loudness_problems(m, -16.0, 0.0)) == 1
    assert audio.loudness_problems({"integrated_lufs": None, "true_peak_dbtp": None}, -14, -1)[0].startswith(
        "integrated")


def test_loudness_targets_default_to_the_style_pack():
    # neutral pack: -14 LUFS, -1.5 dBTP
    assert audio.loudness_problems({"integrated_lufs": -14.3, "true_peak_dbtp": -2.0}) == []


def test_loudnorm_second_pass_uses_the_measurement():
    measured = audio.parse_loudnorm(LOUDNORM)
    assert measured["input_i"] == "-17.91"
    f = audio.loudnorm_filter(-16, -2, 7, measured)
    assert f.startswith("loudnorm=I=-16:TP=-2:LRA=7:linear=true:")
    assert "measured_I=-17.91" in f and "offset=0.10" in f
    assert audio.loudnorm_filter(-16, -2, 7).endswith("print_format=json")


def test_loudnorm_without_output_is_an_error():
    with pytest.raises(audio.CutError):
        audio.parse_loudnorm("nothing here")


def test_command_lines():
    assert audio.channel_levels_cmd("a.mp4", 30, 120)[:7] == ["ffmpeg", "-nostdin", "-hide_banner", "-ss", "30", "-t",
                                                              "120"]
    cmd = audio.level_windows_cmd("a.mp4", 1, 10)
    af = cmd[cmd.index("-af") + 1]
    assert af.startswith("pan=mono|c0=c1,aresample=48000,asetnsamples=480000,astats")
    assert "silencedetect=noise=-38dB:d=0.12" in audio.silencedetect_cmd("x.wav", -38, 0.12)
    assert "ebur128=peak=true:framelog=verbose" in audio.ebur128_cmd("x.mp4")


def test_mic_check_runs_the_measurement_from_30_s(monkeypatch):
    seen = {}

    def fake_run(argv, check=True, **kw):
        seen["argv"] = argv

        class P:
            stderr = VOLUMEDETECT
        return P()
    monkeypatch.setattr(audio.media, "run", fake_run)
    assert audio.mic_check("take.mp4", duration=568.3)["channel"] == 1
    assert seen["argv"][3:7] == ["-ss", "30", "-t", "120"]
    audio.mic_check("short.mp4", duration=20.0)
    assert seen["argv"][3:5] == ["-ss", "5"]
