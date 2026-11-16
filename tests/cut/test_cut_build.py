"""Building the speaker cut: command lines, checks of the sources, reuse of unchanged clips. ffmpeg never runs."""

import json

import pytest

from crewcut.cut import build, common

VIDEO = {"format": {"duration": "568.32"},
         "streams": [{"codec_type": "video", "width": 3840, "height": 2160, "color_transfer": "bt709"},
                     {"codec_type": "audio", "channels": 2}]}


def cut(**kw):
    c = {"id": "s1", "source": "originals/a.MP4", "start": 81.1, "end": 89.24, "speed": 1.1, "zoom": 1.12,
         "zoom_center": [0.36, 0], "expected_text": "x"}
    c.update(kw)
    return c


def test_frames_follow_speed_and_tail():
    assert build.frames_of(cut(), 25) == 185          # a real clip: 8.14 s at 1.1x and 25 fps
    assert build.frames_of(cut(tail=0.24), 25) == round((8.14 + 0.24) / 1.1 * 25)


def test_filters_crop_for_zoom_and_fade_with_tail():
    vf, af, dur = build.clip_filters(cut(), 25, 1920, 1080)
    assert vf.startswith("trim=duration=") and "crop=iw/1.12:ih/1.12:(iw-iw/1.12)*0.36:(ih-ih/1.12)*0" in vf
    assert vf.endswith("fps=25,scale=1920:1080:flags=lanczos,setsar=1")
    assert af.startswith("atrim=duration=") and "atempo=1.1" in af and abs(dur - 7.4) < 1e-9
    vf, af, _ = build.clip_filters(cut(zoom=1.0, tail=0.24), 25, 1920, 1080)
    assert "crop=" not in vf
    assert af.startswith("asetpts=PTS-STARTPTS,atempo=1.1,afade=t=out:")     # no leading atrim with a tail


def test_too_short_clip_is_refused():
    with pytest.raises(common.CutError):
        build.clip_filters(cut(start=1.0, end=1.03, speed=1.0), 25, 1920, 1080)


def test_clip_command_maps_separate_sound(episode):
    dest = episode / "work" / "cut-v001" / "01-s1.mov"
    argv = build.clip_cmd(cut(), episode, dest, 25, 1920, 1080)
    assert argv[:6] == ["ffmpeg", "-nostdin", "-v", "error", "-n", "-threads"]
    assert "0:a:0" in argv and "dnxhr_hqx" in argv and argv[-1] == dest
    argv = build.clip_cmd(cut(audio={"source": "audio/rec.wav", "offset": 2.5}), episode, dest, 25, 1920, 1080)
    assert argv[argv.index("1:a:0") - 1] == "-map"
    second_input = [i for i, a in enumerate(argv) if a == "-i"][1]
    assert str(argv[second_input + 1]).endswith("audio/rec.wav")
    assert argv[second_input - 2:second_input] == ["-ss", pytest.approx(81.1 - 2.5)]   # recorder time


def test_clip_command_refuses_paths_outside_the_episode(episode):
    with pytest.raises(common.CutError):
        build.clip_cmd(cut(source="../../secret.MP4"), episode, episode / "x.mov", 25, 1920, 1080)


def test_source_checks():
    assert build.check_clip(cut(), VIDEO, 1920, 1080) == 0
    hdr = json.loads(json.dumps(VIDEO))
    hdr["streams"][0]["color_transfer"] = "arib-std-b67"
    with pytest.raises(common.CutError, match="HDR"):
        build.check_clip(cut(), hdr, 1920, 1080)
    with pytest.raises(common.CutError, match="framing"):
        build.check_clip(cut(), VIDEO, 1080, 1920)
    rotated = json.loads(json.dumps(VIDEO))
    rotated["streams"][0]["side_data_list"] = [{"rotation": -90}]
    assert build.check_clip(cut(), rotated, 1080, 1920) == -90
    with pytest.raises(common.CutError, match="after the end"):
        build.check_clip(cut(start=560, end=570), VIDEO, 1920, 1080)
    with pytest.raises(common.CutError):
        build.check_clip(cut(speed=3), VIDEO, 1920, 1080)


def test_concat_list_uses_names_next_to_it():
    clips = [{"file": "work/cut-v001/01-a.mov", "frames": 50}, {"file": "work/cut-v001/02-it's.mov", "frames": 25}]
    text = build.concat_text(clips, 25)
    assert text == "file '01-a.mov'\nduration 2.0\nfile '02-it'\\''s.mov'\nduration 1.0\n"


def test_voice_passes():
    measure, apply = build.voice_cmds("r.mov", "v.wav", "highpass=f=75", 10.0, {"voice_lufs": -16})
    assert measure[measure.index("-af") + 1] == "highpass=f=75,loudnorm=I=-16:TP=-2:LRA=7:print_format=json"
    second = apply({"input_i": "-18", "input_tp": "-1", "input_lra": "2", "input_thresh": "-28",
                    "target_offset": "0.1"})
    assert "measured_I=-18" in second[second.index("-af") + 1] and second[-1] == "v.wav"


def test_prepare_checks_everything_before_writing(episode):
    (episode / "originals" / "a.MP4").write_bytes(b"x")
    plan = {"version": "v002", "fps": 25, "width": 1920, "height": 1080, "voice_filter": "anull",
            "cuts": [cut(), cut(id="s2", start=100.0, end=102.0)]}
    p = episode / "edit" / "cut-plan-v002.json"
    p.write_text(json.dumps(plan))
    cfg, clips, out = build.prepare(p, episode, probe=lambda path: VIDEO)
    assert [c["file"] for c in clips] == ["work/cut-v002/01-s1.mov", "work/cut-v002/02-s2.mov"]
    assert clips[1]["timeline_in_frame"] == 185 and clips[1]["timeline_out_frame"] == 185 + 45
    assert out["manifest"].name == "edit-decisions-v002.json" and out["manifest"].parent.name == "work"
    assert out["rough"].name == "speaker-v002.mov" and out["voice"].name == "voice-v002.wav"
    assert not (episode / "work" / "cut-v002").exists()
    plan["version"] = "2"
    p.write_text(json.dumps(plan))
    with pytest.raises(common.CutError):
        build.prepare(p, episode, probe=lambda path: VIDEO)


def test_reuse_only_identical_clips(episode):
    old = episode / "work" / "cut-v001"
    old.mkdir(parents=True)
    (old / "01-s1.mov").write_bytes(b"same")
    (old / "02-s2.mov").write_bytes(b"old")
    a, b = cut(), cut(id="s2", start=100.0, end=102.0)
    old_clips = [{**a, "file": "work/cut-v001/01-s1.mov", "frames": 185},
                 {**b, "file": "work/cut-v001/02-s2.mov", "frames": 45}]
    (episode / "work" / "edit-decisions-v001.json").write_text(json.dumps({"clips": old_clips}))
    new = episode / "work" / "cut-v002"
    new.mkdir()
    clips = [{**a, "file": "work/cut-v002/01-s1.mov", "frames": 185},
             {**b, "start": 100.1, "file": "work/cut-v002/02-s2.mov", "frames": 45}]   # s2 changed, same frames
    assert build.reuse_from(episode, "v001", clips, new) == ["s1"]
    assert (new / "01-s1.mov").read_bytes() == b"same" and not (new / "02-s2.mov").exists()
