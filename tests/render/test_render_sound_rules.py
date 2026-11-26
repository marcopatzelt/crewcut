"""Sound rules a channel can switch on per plan: music only up to a moment (A1), a dry Short (A4) and the effect layer
on picture events (A2), which stays off until the user approved the effect set. ffmpeg is never run here."""

import dataclasses

import numpy as np
import pytest
from render_helpers import basic_plan

from crewcut import brand, paths
from crewcut.render import assemble, sfx_events
from crewcut.render.plan import Plan, PlanError


def music_plan(episode, **sound) -> Plan:
    for f in ("voice.wav", "music.wav"):
        (episode.dir / "audio" / f).write_bytes(b"x")
    p = basic_plan(voice="audio/voice.wav")
    p["sound"] = {"music": "audio/music.wav", "music_source": "licence CC0", **sound}
    return Plan(episode(p))


def music_filter(g) -> str:
    return next(f for f in g.filters if "[mu0]" in f and f.startswith("[1:a]"))


def approved_pack(**sfx_over) -> brand.Pack:
    base = brand.load()
    es = {**base.edit_style, "sfx": dict(sfx_over)}
    pack = dataclasses.replace(base, edit_style=es)
    sid = sfx_events.set_info(pack)["id"]
    return dataclasses.replace(base, edit_style={**es, "sfx": {**sfx_over, "approved_set": sid}})


# ---- A1: music only in the opening -------------------------------------------------------------------------------
def test_default_music_still_runs_the_whole_video(episode):
    g = assemble.audio_graph(music_plan(episode), end=300)
    f = music_filter(g)
    assert "atrim=0:12.000" in f and "afade=t=out:st=10.800:d=1.2" in f and "apad" not in f
    assert not any("music ends" in n for n in g.notes)


def test_music_until_a_second_fades_out_there(episode):
    g = assemble.audio_graph(music_plan(episode, music_until=4.0, music_fade=1.5), end=300)
    f = music_filter(g)
    assert "atrim=0:4.000" in f and "afade=t=out:st=2.500:d=1.500,apad=whole_dur=12.000[mu0]" in f
    assert any("music ends at 4.00 s (a 1.5 s fade)" in n for n in g.notes)
    assert "[mu0][vk]sidechaincompress" in ";".join(g.filters)       # the opening keeps its ducking


def test_music_until_an_insert_stops_hard_with_a_whoosh_on_it(episode):
    g = assemble.audio_graph(music_plan(episode, music_until="k1", music_out="whoosh"), end=300)
    f = music_filter(g)
    assert "atrim=0:4.000" in f and "afade=t=out:st=3.940:d=0.060" in f      # k1 starts at 4.0 s
    kit = paths.state_dir() / "sfx"
    assert str(kit / "whoosh.wav") in g.inputs
    assert "[whoosh0]atrim=0:0.800,volume=-16dB,adelay=3880:all=1" in ";".join(g.filters)  # 120 ms pre-roll


def test_music_until_a_word_and_gaps_after_the_stop_are_dropped(episode):
    g = assemble.audio_graph(music_plan(episode, music_until={"word": "thirty", "offset": -0.2},
                                        gaps=[{"before": "k1", "frames": 10}]), end=300)
    f = music_filter(g)
    assert "volume=enable" not in f                                     # the gap lay after the music's end


def test_music_until_checks_its_values(episode):
    with pytest.raises(PlanError, match="music_out"):
        assemble.audio_graph(music_plan(episode, music_until=4.0, music_out="crash"), end=300)
    with pytest.raises(PlanError, match="music_fade"):
        assemble.audio_graph(music_plan(episode, music_until=4.0, music_fade=9), end=300)
    g = assemble.audio_graph(music_plan(episode, music_until=60.0), end=300)    # after the end: whole video
    assert "afade=t=out:st=10.800:d=1.2" in music_filter(g)


# ---- A4: a dry Short ---------------------------------------------------------------------------------------------
def test_a_dry_short_refuses_music(episode):
    with pytest.raises(PlanError, match="dry Short"):
        assemble.audio_graph(music_plan(episode, bed="dry"), end=300)
    with pytest.raises(PlanError, match="sound.bed"):
        assemble.audio_graph(music_plan(episode, bed="wet"), end=300)


def test_a_dry_short_without_approved_effects_is_voice_and_room_only(episode):
    (episode.dir / "audio" / "voice.wav").write_bytes(b"x")
    p = basic_plan(voice="audio/voice.wav")
    p["sound"] = {"bed": "dry", "hits": ["s1@value"], "whooshes": [3.0], "events": "auto"}
    g = assemble.audio_graph(Plan(episode(p)), end=300)
    assert g.inputs == ["-i", str(episode.dir / "audio" / "voice.wav")]
    assert any("dry Short has voice and room only" in n for n in g.notes)
    assert any("not approved yet" in n for n in g.notes)
    assert g.filters[-1].startswith("[voice]amix=inputs=1")


def test_a_dry_short_with_the_approved_layer_gets_at_most_two_quiet_pops(episode):
    p = basic_plan(voice="audio/voice.wav")
    (episode.dir / "audio" / "voice.wav").write_bytes(b"x")
    p["inserts"] += [{"id": "c1", "kind": "2d", "scene": "keyword", "start": 8.0, "end": 9.0, "transparent": True,
                      "data": {"text": "THREE"}}]
    p["sound"] = {"bed": "dry", "events": "auto"}
    g = assemble.audio_graph(Plan(episode(p), pack=approved_pack()), end=300, voice_levels=np.full(1200, -60.0))
    assert [e["sounds"][0]["sound"] for e in g.events] == ["pop_soft", "pop_soft"]
    assert all(len(e["sounds"]) == 1 for e in g.events)
    assert any("a dry Short gets at most 2" in n for n in g.notes)


# ---- A2: the effect layer ----------------------------------------------------------------------------------------
def layer_plan(episode, extra=(), **sound) -> dict:
    p = basic_plan()
    p["inserts"] += list(extra)
    p["sound"] = {"events": "auto", **sound}
    return p


def test_the_layer_is_off_until_the_set_is_approved(episode):
    p = layer_plan(episode)
    g = assemble.audio_graph(Plan(episode(p)), end=300)
    assert g.events == [] and any("not approved yet" in n for n in g.notes)
    g = assemble.audio_graph(Plan(episode(p), pack=approved_pack()), end=300, voice_levels=np.full(1200, -60.0))
    assert [(e["insert"], e["class"]) for e in g.events] == [("s1", "number"), ("k1", "text")]
    kit = paths.state_dir() / "sfx"
    assert g.inputs == ["-i", str(kit / "pop_soft.wav")]
    assert "[evpop_soft0]volume=-18dB" in ";".join(g.filters)


def test_a_changed_level_needs_a_new_yes():
    pack = approved_pack()
    assert sfx_events.approved(pack)[0]
    louder = dataclasses.replace(pack, edit_style={**pack.edit_style, "sfx": {**pack.edit_style["sfx"],
                                                                              "levels_db": {"pop_soft": -10}}})
    ok, sid = sfx_events.approved(louder)
    assert not ok and sid != pack.edit_style["sfx"]["approved_set"]


def test_events_only_on_picture_moments_with_the_part_pair(episode):
    chapter = {"id": "ch", "kind": "clip", "file": "work/card.mp4", "start": 6.0, "end": 7.0, "sfx": "part"}
    broll = {"id": "b1", "kind": "clip", "file": "work/screen.mp4", "start": 9.0, "end": 11.0}
    quiet = {"id": "q", "kind": "clip", "file": "work/q.mp4", "start": 11.0, "end": 11.5, "sfx": False}
    p = layer_plan(episode, [chapter, broll, quiet])
    p["base"] = {"color": "soft", "seconds": 60}
    plan = Plan(episode(p), pack=approved_pack())
    events, notes = sfx_events.layer(plan, 60 * 25, np.full(6000, -60.0))
    by = {e.insert: e for e in events}
    assert set(by) == {"s1", "k1", "ch", "b1"}
    assert by["s1"].t == pytest.approx(2.0)                  # the number lands on its cue, not at the insert's start
    names = [n for n, _, _ in by["ch"].sounds]
    assert names == ["whoosh_soft", "pop_soft"]               # the same quiet pair on every part change
    (_, w_start, _), (_, p_start, _) = by["ch"].sounds
    assert w_start + sfx_events.PEAK_AT["whoosh_soft"] == pytest.approx(6.0, abs=0.002)
    assert p_start > w_start
    assert [n for n, _, _ in by["b1"].sounds] == ["swoosh"]
    assert any("silent (\"sfx\": false)" in n for n in notes)
    assert all(n in sfx_events.SET_SOUNDS for e in events for n, _, _ in e.sounds)   # no riser, no hit


def test_at_most_six_a_minute_and_part_changes_stay(episode):
    many = [{"id": f"t{i}", "kind": "2d", "scene": "keyword", "start": 12.0 + i * 2.0, "end": 13.0 + i * 2.0,
             "transparent": True, "data": {"text": "X"}} for i in range(20)]
    many.append({"id": "part", "kind": "clip", "file": "work/card.mp4", "start": 40.0, "end": 41.0, "sfx": "part"})
    p = layer_plan(episode, many)
    p["base"] = {"color": "soft", "seconds": 90}
    plan = Plan(episode(p), pack=approved_pack())
    events, notes = sfx_events.layer(plan, 90 * 25, np.full(9000, -60.0))
    times = [e.t for e in events]
    assert "part" in {e.insert for e in events}
    for t in times:
        assert sum(1 for u in times if t <= u < t + 60) <= 6
    assert all(b - a >= 1.0 for a, b in zip(times, times[1:], strict=False))
    assert any("already 6 in that minute" in n for n in notes)


def test_a_short_video_keeps_the_rate_but_at_least_two(episode):
    many = [{"id": f"t{i}", "kind": "2d", "scene": "keyword", "start": 6.0 + i * 1.2, "end": 6.8 + i * 1.2,
             "transparent": True, "data": {"text": "X"}} for i in range(4)]
    plan = Plan(episode(layer_plan(episode, many)), pack=approved_pack())
    events, _ = sfx_events.layer(plan, 300, np.full(1200, -60.0))      # 12 s: 6 a minute -> 2
    assert len(events) == 2 and events[0].insert == "s1"                # the number wins over text


def test_never_on_a_speech_peak(episode):
    plan = Plan(episode(layer_plan(episode)), pack=approved_pack())
    levels = np.full(1200, -45.0)                    # quiet speech everywhere
    levels[::3] = -20.0                              # syllables
    levels[395:430] = -10.0                          # k1 (4.0 s) lands on a loud word that lasts 0.35 s
    levels[380:395] = -40.0                          # a quiet spot just before it
    events, notes = sfx_events.layer(plan, 300, levels)
    k1 = next(e for e in events if e.insert == "k1")
    assert k1.t < 4.0 and sfx_events._loudness_at(levels, k1.t) < sfx_events.peak_threshold(levels)
    assert any("moved" in n and "k1" in n for n in notes)
    levels[300:500] = -10.0                          # a long shout: no quiet spot within 0.2 s
    events, notes = sfx_events.layer(plan, 300, levels)
    assert "k1" not in {e.insert for e in events}
    assert any("on a speech peak" in n for n in notes)


def test_the_layer_replaces_the_inserts_own_motion_sounds(episode):
    p = layer_plan(episode, hits=[3.5])
    plan = Plan(episode(p), pack=approved_pack())
    g = assemble.audio_graph(plan, end=300, voice_levels=np.full(1200, -60.0))
    f = ";".join(g.filters)
    assert "[hit0]" in f                                 # an explicit plan hit still plays
    assert g.events and all(e["sounds"] for e in g.events)


def test_classify_knows_the_templates():
    class X:
        def __init__(self, kind, scene, transparent=False, raw=None):
            self.kind, self.scene, self.transparent, self.raw = kind, scene, transparent, raw or {}
    assert sfx_events.classify(X("motion", "chapter_card")) == "part"
    assert sfx_events.classify(X("motion", "number_roll")) == "number"
    assert sfx_events.classify(X("motion", "keyword_pop", True)) == "text"
    assert sfx_events.classify(X("motion", "cursor")) is None
    assert sfx_events.classify(X("2d", "counter")) == "number"
    assert sfx_events.classify(X("3d", "stack")) == "broll"
    assert sfx_events.classify(X("clip", None, raw={"sfx": "text"})) == "text"


# ---- listening sheet and the user's yes --------------------------------------------------------------------------
def test_listening_sheet_writes_every_sound_a_demo_and_the_id(tmp_path):
    from render_helpers import FakeRunner
    run = FakeRunner()
    pack = brand.load()
    r = sfx_events.listening_sheet(tmp_path / "sheet", pack, runner=run)
    page = (tmp_path / "sheet" / "index.html").read_text()
    assert r["id"].startswith("sfx-") and r["id"] in page and f"sfx-approve {r['id']}" in page
    assert set(r["files_at_level"]) == {"pop_soft.wav", "whoosh_soft.wav", "swoosh.wav"}
    demo = run.calls[-1]
    assert "anullsrc=r=48000:cl=stereo" in demo                      # no voice given: the effects alone
    assert sum(1 for x in demo if str(x).endswith(".wav")) >= 8      # 6 demo moments, two of them pairs, plus output
    assert "prefers-color-scheme: dark" in page


def test_only_the_user_approves_the_set(tmp_path, monkeypatch):
    import json
    pack_dir = tmp_path / "brand"
    pack_dir.mkdir()
    (pack_dir / "edit-style.json").write_text(json.dumps({"schema": 1, "music_db": -15.0}))
    sid = sfx_events.set_info(brand.load(pack_dir))["id"]
    monkeypatch.setenv("CREWCUT_JOB", "12")
    with pytest.raises(PermissionError):
        sfx_events.approve(sid, pack_dir, "test")
    monkeypatch.delenv("CREWCUT_JOB")
    with pytest.raises(ValueError, match="not the current effect set"):
        sfx_events.approve("sfx-000000000000", pack_dir, "test")
    sfx_events.approve(sid, pack_dir, "Marco, after listening")
    d = json.loads((pack_dir / "edit-style.json").read_text())
    assert d["sfx"]["approved_set"] == sid and d["music_db"] == -15.0
    assert sfx_events.approved(brand.load(pack_dir))[0]


# ---- real ffmpeg: the music really stops, the dry Short really has no bed ---------------------------------------
def _band_level(x, sr: int, a: float, b: float, lo: float, hi: float) -> float:
    seg = x[int(a * sr):int(b * sr)]
    spec = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    return 10 * np.log10(spec[(f >= lo) & (f <= hi)].sum() + 1e-12)


def _read16(path):
    import wave
    with wave.open(str(path)) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), "<i2").reshape(n, ch).mean(axis=1) / 32768.0
    return x, sr


@pytest.mark.skipif(not (__import__("shutil").which("ffmpeg")), reason="ffmpeg is not installed")
def test_real_music_ends_where_the_plan_says(episode):
    import shutil
    import subprocess
    ff = shutil.which("ffmpeg")
    a = episode.dir / "audio"
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=f=1000:d=12:sample_rate=48000", "-af",
                    "volume=-12dB", "-ac", "2", str(a / "voice.wav")], check=True)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=f=150:d=20:sample_rate=48000", "-ac", "2",
                    str(a / "music.wav")], check=True)
    p = basic_plan(voice="audio/voice.wav")
    p["sound"] = {"music": "audio/music.wav", "music_source": "sine", "duck": False, "music_db": -6,
                  "music_until": 4.0, "music_fade": 1.0}
    g = assemble.audio_graph(Plan(episode(p)), end=300)
    out = episode.dir / "mix.wav"
    subprocess.run(assemble.audio_cmd(g, out), check=True)
    x, sr = _read16(out)
    before = _band_level(x, sr, 1.0, 2.5, 120, 180)
    after = _band_level(x, sr, 6.0, 10.0, 120, 180)
    voice = _band_level(x, sr, 6.0, 10.0, 950, 1050)
    assert before - after > 40                                          # the bed is gone after the fade
    assert voice > after + 40                                           # the voice stays
