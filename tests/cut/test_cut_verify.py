"""verify: word differences, join pauses measured on a synthetic voice, the status, the whole run with fakes."""

import json

import numpy as np

from crewcut.cut import verify

RATE = 16000


def voice_with_pauses(pauses, piece=1.0):
    """Tone pieces of `piece` seconds separated by the given pauses (s), with a quiet noise floor."""
    rng = np.random.default_rng(1)
    t = np.arange(int(RATE * piece)) / RATE
    tone = 0.3 * np.sin(2 * np.pi * 200 * t)
    parts = [tone]
    for p in pauses:
        parts += [np.zeros(int(RATE * p)), tone]
    x = np.concatenate(parts)
    return x + 0.0005 * rng.standard_normal(len(x))


def clips_for(pauses, piece=1.0, fps=25):
    out, t = [], 0.0
    for k in range(len(pauses) + 1):
        start = t
        t += piece + (pauses[k] if k < len(pauses) else 0)
        out.append({"id": f"c{k}", "timeline_in_frame": round(start * fps)})
    # a cut sits in the middle of each pause
    for k, p in enumerate(pauses, 1):
        out[k]["timeline_in_frame"] = round((k * piece + sum(pauses[:k]) - p / 2) * fps)
    return out


def test_join_pauses_are_measured_and_judged():
    pauses = [0.25, 0.08, 0.6]
    rms = verify.level_track(voice_with_pauses(pauses), RATE)
    joins = verify.join_pauses(rms, clips_for(pauses), 25)
    got = [j["pause"] for j in joins]
    assert abs(got[0] - 0.25) <= 0.04 and got[1] <= 0.1 and got[2] >= 0.55
    bad = verify.bad(joins, 0.17, 0.45)
    assert [b["to"] for b in bad] == ["c2", "c3"]


def test_word_differences_ignore_spacing_and_number_words():
    same = verify.spelling()
    assert verify.diff_issues("Free LLM API costs five dollars", "free-llm-api costs 5 dollars", same) == []
    assert len(verify.diff_issues("costs five dollars", "costs 5 dollars")) == 1      # without the spelling map
    issues = verify.diff_issues("so I built it", "so I built built it")
    assert issues == [{"type": "insert", "expected": "", "heard": "built", "context": "so i built it"}]


def test_status():
    assert verify.status([], [], [], False) == "match"
    assert verify.status([{"x": 1}], [], [], False) == "words_to_review"
    assert verify.status([], [], [{"at": 1}], False) == "review_needed"
    assert verify.status([], [], [], True) == "review_needed"


def test_whole_run_writes_the_verification_next_to_the_decisions(episode, monkeypatch):
    plan = {"expected_script": "One two. Three four.", "join_min": 0.17}
    (episode / "edit" / "cut-plan-v001.json").write_text(json.dumps(plan))
    clips = [{"id": "a", "expected_text": "One two.", "file": "work/cut-v001/01-a.mov", "timeline_in_frame": 0},
             {"id": "b", "expected_text": "Three four.", "file": "work/cut-v001/02-b.mov", "timeline_in_frame": 31}]
    dec = episode / "work" / "edit-decisions-v001.json"
    dec.write_text(json.dumps({"version": "v001", "fps": 25, "clips": clips, "voice": "audio/voice-v001.wav",
                               "plan": "edit/cut-plan-v001.json"}))
    voice = voice_with_pauses([0.25], piece=1.125)
    from crewcut.cut import transcribe
    monkeypatch.setattr(transcribe, "load_audio", lambda p, *a, **k: voice if p.name.startswith("voice") else
                        np.zeros(10, np.float32) + (1 if p.name.startswith("01") else 2))
    monkeypatch.setattr(verify.audio, "channel_levels", lambda p: [-20.0, -20.5])

    class Engine:
        def text(self, x):
            return "One two." if x[0] == 1 else "Three four"

        def describe(self):
            return {"model": "fake"}
    r = verify.verify(dec, episode, Engine(), log=lambda m: None)
    assert r["status"] == "match", r
    assert r["report"] == "work/cut-verification-v001.json"
    saved = json.loads((episode / r["report"]).read_text())
    assert saved["selects"] == [{"id": "a", "text": "One two."}, {"id": "b", "text": "Three four"}]
    assert saved["bad_joins"] == [] and saved["channel_levels_db"] == [-20.0, -20.5]
    assert "status: match" in verify.describe(r)
