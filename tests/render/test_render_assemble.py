"""The cut: shown lock, pieces, ffmpeg argument lists, sound graph, loudness loop. ffmpeg is never run."""

import json

import pytest
from render_helpers import FakeRunner, basic_plan, loudness_text

from crewcut.render import assemble, media
from crewcut.render.plan import Plan, PlanError


def rendered(plan: Plan) -> None:
    """Pretend every 2D/3D insert is rendered and encoded."""
    for ins in plan.inserts:
        if ins.kind == "clip":
            continue
        ins.out_dir.mkdir(parents=True, exist_ok=True)
        for i in range(ins.render_frames):
            (ins.out_dir / f"{i:04d}.png").write_bytes(b"x")
        ins.clip.write_bytes(b"clip")


def test_shown_writes_json_and_blocks_the_cut(episode):
    plan = Plan(episode(basic_plan()))
    with pytest.raises(PlanError, match="nothing to lock"):
        assemble.shown(plan)
    plan.output.write_bytes(b"video")
    info = assemble.shown(plan)
    d = json.loads(plan.shown_path.read_text())
    assert set(d) == {"at", "sha256"} and len(d["sha256"]) == 64 and d["at"].endswith("Z")
    assert d["sha256"] == info["sha256"] == assemble.sha256(plan.output)
    run = FakeRunner()
    with pytest.raises(assemble.ShownError, match="already shown.*new plan version"):
        assemble.cut(plan, run, log=lambda *a: None)
    assert run.calls == []                    # refused before any program ran
    assert plan.output.read_bytes() == b"video"


def test_pieces_cut_at_inserts_overlays_and_zoom(episode):
    p = basic_plan(speaker=[{"at": 7.0, "zoom": 1.1}])
    plan = Plan(episode(p))
    ps = assemble.pieces(plan, base_end=300, end=300)
    assert [(x.a, x.b) for x in ps] == [(0, 25), (25, 75), (75, 100), (100, 150), (150, 175), (175, 300)]
    assert [x.source for x in ps] == ["color", "insert", "color", "color", "color", "color"]
    assert ps[1].label == "s1" and ps[1].seek == 0
    assert ps[3].overlays and ps[3].overlays[0][0] == plan.by_id("k1").clip and ps[3].overlays[0][1] == 0
    assert ps[5].label == "background"
    shots = assemble.shots(plan, 300, 300)
    assert [s["frame"] for s in shots] == [0, 25, 75, 175]     # overlay edges are no cuts
    assert shots[1]["what"] == "s1"


def test_speaker_zoom_and_overlay_commands(episode):
    ep = episode.dir
    (ep / "work" / "speaker.mp4").write_bytes(b"x")
    p = basic_plan(base="work/speaker.mp4", speaker=[{"at": 4.5, "zoom": 1.12}], face=[0.5, 0.4])
    plan = Plan(episode(p))
    ps = assemble.pieces(plan, base_end=300, end=300)
    zoomed = next(x for x in ps if x.a == 112)
    assert zoomed.source == "base" and zoomed.label == "speaker x1.12"
    assert "scale=iw*1.12:-2:flags=lanczos,crop=1920:1080:(iw-1920)*0.5:(ih-1080)*0.4," in zoomed.vf
    assert zoomed.overlays                                   # the keyword lies over it
    cmd = assemble.piece_cmd(plan, zoomed, ep / "x.mkv")
    assert cmd[cmd.index("-ss") + 1] == f"{112 / 25 - 0.004:.3f}"
    assert cmd.count("-i") == 2 and cmd[cmd.index("-frames:v") + 1] == str(zoomed.frames)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=format=auto[b1]" in fc and fc.endswith("[b1]format=yuv420p[v]")
    assert cmd[cmd.index("-video_track_timescale") + 1] == "12800"
    plain = ps[0]
    assert plain.vf.startswith("scale=1920:1080:force_original_aspect_ratio=increase") and "iw*" not in plain.vf


def test_color_base_and_clip_speed(episode):
    ep = episode.dir
    (ep / "broll").mkdir()
    (ep / "broll" / "c.mp4").write_bytes(b"x")
    p = basic_plan()
    p["inserts"].append({"id": "v1", "kind": "clip", "file": "broll/c.mp4", "at": 10.0, "speed": 2.0, "start": 7.0, "end": 9.0})
    plan = Plan(episode(p))
    ps = assemble.pieces(plan, 300, 300)
    clip = next(x for x in ps if x.label == "v1" and x.a == 175)
    assert clip.seek == 10.0 and "setpts=(PTS-STARTPTS)/2," in clip.vf
    color = assemble.piece_cmd(plan, ps[0], ep / "c.mkv")
    assert color[color.index("-f") + 1] == "lavfi" and color[color.index("-i") + 1].startswith("color=c=0xF1F1EF:s=1920x1080:r=25:")


def test_tail_needs_an_insert(episode):
    plan = Plan(episode(basic_plan(tail=1.0)))
    with pytest.raises(PlanError, match="tail needs"):
        assemble.pieces(plan, base_end=300, end=assemble.end_frame(plan, 300))
    p = basic_plan(tail=1.0)
    p["inserts"].append({"id": "end", "kind": "2d", "scene": "headline", "start": 11.5, "end": 13.0, "data": {"title": "Bye"}})
    plan = Plan(episode(p, "plan-v002.json"))
    ps = assemble.pieces(plan, base_end=300, end=325)
    assert ps[-1].label == "end" and ps[-1].b == 325


def test_audio_graph_voice_music_duck_gaps_hits(episode):
    ep = episode.dir
    for f in ("voice.wav", "music.wav", "hit.wav"):
        (ep / "audio" / f).write_bytes(b"x")
    p = basic_plan(voice="audio/voice.wav", voice_db=1.5)
    p["sound"] = {"music": "audio/music.wav", "music_source": "made for this video, licence CC0", "music_db": None,
                  "gaps": [{"before": "s1@value", "frames": 10}], "hits": ["s1@value", {"at": "k1", "offset": 2, "frames": 5}],
                  "hit_file": "audio/hit.wav", "typing": ["s1"], "whooshes": [3.0]}
    plan = Plan(episode(p))
    g = assemble.audio_graph(plan, end=300)
    assert g.seconds == 12.0
    assert g.inputs == ["-i", str(ep / "audio" / "voice.wav"), "-stream_loop", "-1", "-i", str(ep / "audio" / "music.wav"),
                        "-i", str(ep / "audio" / "hit.wav")]
    f = ";".join(g.filters)
    assert "[0:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume=1.5dB,apad=whole_dur=12.000[voice]" in f
    assert "volume=-16dB" in f                                          # music_db null -> pack value
    assert "volume=enable='between(t,1.600,1.960)':volume=0.05" in f    # gap: 10 frames before frame 50
    assert "[mu0][vk]sidechaincompress=threshold=0.04:ratio=2.2" in f
    assert "adelay=1960:all=1" in f                                     # hit at frame 50 = 2.0 s, 40 ms pre-roll
    assert "[hit1]atrim=0:0.200,volume=-9dB,adelay=4040:all=1" in f     # k1 starts at frame 100, +2 = 4.08 s - 40 ms
    assert g.filters[-1].startswith("[vm][mu][hitd0][hitd1]amix=inputs=4:normalize=0:duration=first")
    assert any("typing" in n for n in g.notes) and any("whoosh" in n for n in g.notes)
    assert not any("hit sound" in n for n in g.notes)


def test_audio_graph_without_voice_or_music(episode):
    p = basic_plan()
    p["sound"] = {"music": "audio/missing.wav", "hits": ["s1@value"]}
    g = assemble.audio_graph(Plan(episode(p)), end=250)
    assert g.inputs == []
    assert g.filters[0] == "anullsrc=r=48000:cl=stereo,atrim=0:10.000[voice]"
    assert any("music file not found" in n for n in g.notes) and any("hit sound(s) skipped" in n for n in g.notes)
    assert g.filters[-1].startswith("[voice]amix=inputs=1")
    cmd = assemble.audio_cmd(g, episode.dir / "a.wav")
    assert cmd[-3:] == ["-t", "10.000", str(episode.dir / "a.wav")] and "pcm_s16le" in cmd


def test_audio_from_base_when_no_voice(episode):
    (episode.dir / "work" / "speaker.mp4").write_bytes(b"x")
    g = assemble.audio_graph(Plan(episode(basic_plan(base="work/speaker.mp4"))), end=250)
    assert "loudnorm=I=-15:TP=-1.5:LRA=7" in g.filters[0]


def test_loudness_parsing_and_gain():
    t = "noise\n" + loudness_text(-19.3, -0.7)
    assert media.parse_loudness(t) == {"lufs": -19.3, "true_peak": -0.7}
    silent = loudness_text(-70.0, 0).replace("0.0 dBFS", "-inf dBFS")
    assert media.parse_loudness(silent)["true_peak"] == float("-inf")
    assert media.parse_loudness("nothing") == {"lufs": None, "true_peak": None}
    assert assemble.loudness_gain(-19.3, -14.0) == 5.3
    assert assemble.loudness_gain(-70.0, -14.0) == 0.0 and assemble.loudness_gain(None, -14.0) == 0.0


def test_true_peak_loop_lowers_the_limiter(tmp_path):
    run = FakeRunner(peaks=[-0.4, -1.2, -1.8])
    tp, notes = assemble.encode_audio(tmp_path / "a.wav", tmp_path / "a.m4a", 5.3, -1.5, run)
    encodes = [c for c in run.calls if "aac" in c]
    limits = [c[c.index("-af") + 1] for c in encodes]
    assert len(encodes) == 3 and tp == -1.8 and notes == []
    assert limits[0] == f"volume=5.30dB,alimiter=limit={10 ** (-2.6 / 20):.3f}:level=false"
    assert limits[1] == f"volume=5.30dB,alimiter=limit={10 ** ((-2.6 - 1.3) / 20):.3f}:level=false"
    run = FakeRunner(peaks=[-0.1, -0.1, -0.1, -0.1, -0.1])
    tp, notes = assemble.encode_audio(tmp_path / "a.wav", tmp_path / "a.m4a", 0, -1.5, run)
    assert "still above" in notes[0]


def test_full_cut_with_fake_programs(episode):
    p = basic_plan(crf=19)
    p["sound"] = {"music_source": "none"}
    plan = Plan(episode(p))
    rendered(plan)
    run = FakeRunner(lufs=-21.0, peaks=[-1.0, -1.7])
    info = assemble.cut(plan, run, log=lambda *a: None)
    out = plan.output
    assert out.is_file() and info["output"] == str(out)
    assert info["frames"] == 300 and info["seconds"] == 12.0 and info["music_source"] == "none"
    assert len(run.find(".pieces")) >= 5                               # one run per piece, plus the concat
    audio = run.find(".raw.wav")[0]
    assert "-filter_complex" in audio
    final = run.calls[-2]
    assert final[final.index("-crf") + 1] == "19" and "+faststart" in final and final[-1].endswith(".tmp.mp4")
    report = json.loads((out.parent / "out-v001.cut.json").read_text())
    assert report["lufs_before"] == -21.0 and [s["what"] for s in report["shots"]] == ["speaker", "s1", "speaker"]
    assert not (out.parent / "out-v001.raw.wav").exists()
    # second run: pieces are reused, only sound and final encode run again
    n_before = len(run.find(".pieces"))
    run2 = FakeRunner(lufs=-21.0)
    assemble.cut(plan, run2, log=lambda *a: None)
    assert len(run2.find(".pieces")) == 1 and n_before > 1           # just the concat reading the list


def test_cut_needs_rendered_inserts(episode):
    plan = Plan(episode(basic_plan()))
    with pytest.raises(PlanError, match="not rendered yet"):
        assemble.cut(plan, FakeRunner(), log=lambda *a: None)
