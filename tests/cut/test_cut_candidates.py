"""`crewcut cut candidates`: stand-alone passages from the words, graphics and retention of a finished episode."""

import json

from crewcut.cut import candidates, cli

TEXTS = [
    "I tested five local models on one laptop.", "And the results surprised me.", "The plan was simple.",
    "Each model got the same task.", "It had to sort 37 invoices.", "The first model failed after 12 minutes.",
    "So I tried the second one.", "It finished in 4 minutes.", "But it mixed up two customers.",
    "The third model was the winner.", "It sorted all 37 without a mistake.", "That surprised me more than anything.",
    "Here is what I changed after that.", "I now run the small model first.", "Is that the right call?",
    "We will see next week.", "The cost was 0 euros for all of it.", "That is the whole test.",
]


def words_for(texts, gap=0.5, per_word=0.4):
    out, t = [], 0.5
    for text in texts:
        for w in text.split():
            out.append({"w": w, "s": round(t, 2), "e": round(t + per_word - 0.05, 2)})
            t += per_word
        t += gap
    return out


def episode_with_words(episode, texts=TEXTS):
    words = words_for(texts)
    (episode / "work" / "words-v002.json").write_text(json.dumps(words))
    return words


def test_sentences_end_at_marks_and_long_pauses():
    words = [{"w": "One", "s": 0.0, "e": 0.3}, {"w": "two.", "s": 0.4, "e": 0.7}, {"w": "three", "s": 0.9, "e": 1.2},
             {"w": "four", "s": 3.0, "e": 3.3}, {"w": "five?", "s": 3.4, "e": 3.7}]
    s = candidates.split_sentences(words)
    assert [x["text"] for x in s] == ["One two.", "three", "four five?"]
    assert [x["complete"] for x in s] == [True, False, True]


def test_retention_from_a_studio_csv_and_its_rises(tmp_path):
    p = tmp_path / "retention.csv"
    p.write_text("Video position (%),Absolute audience retention (%)\n0,100\n10,80\n20,70\n30,75\n40,78\n50,60\n")
    curve = candidates.read_retention(p, 200.0)
    assert curve[2] == (40.0, 70.0)
    assert candidates.rises(curve) == [{"from": 40.0, "to": 80.0, "gain": 8.0}]
    j = tmp_path / "r.json"
    j.write_text(json.dumps([{"elapsedVideoTimeRatio": 0.5, "audienceWatchRatio": 0.4},
                             {"elapsedVideoTimeRatio": 0.6, "audienceWatchRatio": 0.45}]))
    assert candidates.read_retention(j, 100.0) == [(50.0, 40.0), (60.0, 45.0)]


def test_passages_with_signals(episode):
    words = episode_with_words(episode)
    t_37 = next(w["s"] for w in words if w["w"] == "37")
    plan = {"words": "work/words-v002.json", "base": "work/speaker-v002.mov", "inserts": [
        {"id": "c1", "kind": "2d", "scene": "counter", "start": t_37 - 0.5, "end": t_37 + 2.0,
         "data": {"label": "invoices", "value": "37"}}]}
    (episode / "edit" / "plan-v002.json").write_text(json.dumps(plan))
    clips = [{"id": "a", "source": "originals/a.MP4", "timeline_in_frame": 0, "timeline_out_frame": 25 * 20},
             {"id": "b", "source": "originals/b.MP4", "timeline_in_frame": 25 * 20, "timeline_out_frame": 25 * 60}]
    (episode / "originals" / "b.MP4").write_bytes(b"x")                      # a.MP4 was deleted
    (episode / "work" / "edit-decisions-v002.json").write_text(json.dumps(
        {"version": "v002", "fps": 25, "duration_seconds": 60.0, "clips": clips, "voice": "audio/voice-v002.wav"}))
    (episode / "review" / "retention.csv").write_text("seconds,retention\n0,90\n20,70\n30,72\n35,76\n40,60\n")
    r = candidates.find(episode, lo=10, hi=30, limit=50)
    assert r["plan"] == "edit/plan-v002.json" and r["decisions"] == "work/edit-decisions-v002.json"
    assert r["retention_rises"] == [{"from": 20.0, "to": 35.0, "gain": 6.0}]
    assert r["material"] == {"originals_missing": ["originals/a.MP4"], "clean_voice": None}
    assert all(bool(p["originals_missing"]) == (p["from"] < 20) for p in r["passages"])
    first = r["sentences"][0]
    assert first["text"] == TEXTS[0] and first["starts_with_link"] is False
    assert r["sentences"][1]["starts_with_link"] is True                     # "And the results ..."
    s37 = r["sentences"][4]
    assert s37["numbers"] == ["37"] and s37["graphics"] == ["c1"]
    assert all(10 <= p["seconds"] <= 30 and p["sentences"][1] - p["sentences"][0] < 12 for p in r["passages"])
    assert all(r["sentences"][p["sentences"][1] - 1]["complete"] for p in r["passages"])
    best = r["passages"][0]
    assert best["graphics"] and best["graphics"][0]["label"] == "invoices 37"
    across = [p for p in r["passages"] if p["from"] < 20 < p["to"]]
    assert across and all(p["pieces_needed"] == 2 and p["cut_boundaries"] == [20.0] for p in across)
    for a in r["passages"]:                                                # thinned: no big overlaps
        for b in r["passages"]:
            if a is not b:
                assert min(a["to"], b["to"]) - max(a["from"], b["from"]) <= 0.5 * min(a["seconds"], b["seconds"])


def test_text_only_without_plan_or_curve(episode, capsys):
    episode_with_words(episode)
    assert cli.main(["cut", "candidates", "--episode", "001-test", "--min", "10", "--max", "25", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["report"] == "review/short-candidates-v002.json" and (episode / r["report"]).is_file()
    assert r["plan"] is None and r["retention"] is None
    assert any("rests on the text alone" in n for n in r["notes"])
    assert r["passages"] and all(p["pieces_needed"] == 1 for p in r["passages"])


def test_no_words_is_a_clear_error(episode, capsys):
    assert cli.main(["cut", "candidates", "001-test"]) == 1
    assert "no word record" in capsys.readouterr().err
