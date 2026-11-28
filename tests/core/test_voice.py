"""The voice profile, the reference moves and the voice and structure checks in the style gate (docs/hormozi-voice.md).

Everything here is synthetic: a tiny transcript database, made-up scripts and a hand-written profile."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from crewcut import episodes, paths, stylegate, voicecheck
from crewcut import voicemetrics as vm

ROOT = Path(__file__).resolve().parents[2]


def host(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "host" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROFILE = {
    "schema": 1,
    "script": {"lang": "en", "wpm": 180, "bullet_seconds": 12, "min_sentences": {"long": 8, "short": 4}},
    "check_names": {"voice": "VOICE", "structure": "STRUCTURE"},
    "reference": {"long_top": {"metrics": {"sentence_words_median": {"median": 13, "p25": 11, "p75": 14, "n": 40}}}},
    "targets": {
        "long": {
            "sentence_words_median": {"min": 5, "max": 15, "severity": "error", "why": "the speaker says 13"},
            "sentence_words_p90": {"max": 24, "severity": "error", "why": "long sentences end at 24 words"},
            "numbers_per_minute": {"min": 2.0, "max": 25, "severity": "error", "why": "numbers carry proof"},
            "fillers_per_100": {"max": 1.0, "severity": "error", "why": "no fillers in a script"},
            "you_per_100": {"min": 1.5, "severity": "error", "why": "speak to the viewer"},
            "questions_per_minute": {"min": 0.3, "max": 4, "severity": "hint", "why": "questions at joints"},
            "words_per_minute": {"severity": "info"},
        },
        "short": {
            "sentence_words_median": {"min": 4, "max": 11, "severity": "error", "why": "short lines"},
            "numbers_per_minute": {"min": 3, "severity": "error", "why": "numbers"},
        },
    },
}

GOOD = """The cheapest setting built my best clip, and you can copy it today.
I tested four settings on eight clips for 40 dollars.
By the end you'll know which one I keep.
Here it is in three points.

Number one. My best clip took 40 minutes, the worst one 90.
You see both clocks side by side.
The fast one used three helpers for street, flat and edit.
Helpers beat thinking time.

Number two. Rendering 600 frames took five hours on one card.
That is 30 seconds per frame, and you pay for every second.
One test frame first saved me two hours.
Test one frame first.

Number three. The top setting cost 45 dollars and came last.
It thought twice as long as the middle one.
More thinking, worse clip.

I keep the middle setting, because it was cheaper and better in every test you saw.
The link is in the description.
"""

BAD = """Basically, the thing with these settings is that, um, you kind of have to understand how the whole system works.
Actually it is literally about how the model thinks about the problem and how long it keeps going on before it stops.
The settings change the way the model works on a task.
Some settings are higher and some settings are lower than the others.
Basically the higher ones think more and the lower ones think less about it.
Um, that is kind of the whole idea behind the settings in the tool.
It is good to know about it when you work with the model every day.
So in summary we have seen today that the settings are basically important for the result.
Thanks for watching and see you next time.
"""

SHEET = """## Opening
LINE1: The highest setting built my two worst clips.
PROOF: I tested all five settings. Ten clips, 192 dollars.
PROMISE: By the end you'll know which one I keep, and you can copy it.
PLAN: Here is why, in two points.

## Unit 1 | Proof: Screen | Short: no
HOOK: Point one. My best clip took 40 minutes, the worst one 90.
• Proof: [both clocks] 40 against 90
• Example: [three helpers] street · flat · edit
PUNCH: Helpers beat thinking time.
BRIDGE: So where did the time go?

## Unit 2 | Proof: Number | Short: no
HOOK: Point two. Rendering 600 frames took five hours on one card.
• Number: [counter] 600 times 30 seconds
PUNCH: One test frame saves you hours.

## Close
VERDICT: I keep the middle setting, and you can copy it.
LINK: The link is in the description.

---
notes
"""


@pytest.fixture
def profile(studio):
    p = studio / "brand" / "voice" / "profile.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(PROFILE))
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text('[style_gate]\nvoice_profile = "brand/voice/profile.json"\n')
    return p


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ---- metrics -------------------------------------------------------------------------------------------------------
def test_metrics_count_like_a_listener():
    sents = vm.from_text("I tested 4 settings. You see the clocks? Look at the second one. Um, it took 90 minutes.", 180)
    m = vm.measure(sents, "en")
    assert m["sentences"] == 4 and m["sentence_words_median"] == 4.5
    assert m["numbers_per_minute"] > 0 and m["first_number_word"] == 2
    assert m["you_per_100"] > 0 and m["i_per_100"] > 0
    assert m["questions_per_minute"] > 0 and m["imperative_share"] == 0.25 and m["fillers_per_100"] > 0
    t = vm.measure(vm.from_text("Number one is speed. " * 3 + "Number two is price. " * 3, 60), "en")
    assert t["transitions_per_minute"] > 0 and t["first_transition_s"] == 0.0


def test_version_names_are_not_numbers_and_chunks_spread_time():
    lex = vm.lexicon("de")
    assert vm.numbers_in("Opus 4 und RTX 5090 bauen 3 Spots", lex) == ["3"]
    s = vm.from_chunks([(0, "One two three four. Five six seven eight."), (10, "Nine ten.")])
    assert s[0].start == 0 and 4 < s[1].start < 6 and s[2].start == 10


# ---- the host scripts ----------------------------------------------------------------------------------------------
def corpus(tmp_path) -> Path:
    db = tmp_path / "corpus.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE videos (id TEXT, title TEXT, duration_s INT, views INT, kind TEXT, source TEXT, "
                "dup_of TEXT, published TEXT)")
    con.execute("CREATE TABLE chunks (video_id TEXT, idx INT, start_s INT, text TEXT)")
    for i in range(8):
        vid = f"long{i}"
        con.execute("INSERT INTO videos VALUES (?,?,?,?,?,?,NULL,?)", (vid, f"Video {i}", 600, 1000 * (i + 1), "long",
                                                                      "youtube", "2026-01-01"))
        con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (vid, 0, 0, f"I made {i + 3} million dollars with one "
                    "offer. In this video I'm going to show you the three steps. Here they are."))
        con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (vid, 1, 30, "Number two, raise your price. Let's say "
                    "you charge 100 dollars a month for 12 months. That's 1,200 dollars. You keep the client "
                    "longer because the offer is better than anything else they could buy. Simple."))
        con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (vid, 2, 300, "And that is how you double the business "
                    "without a single new lead or ad. Pick the path that is right for you."))
    for i in range(6):
        vid = f"short{i}"
        con.execute("INSERT INTO videos VALUES (?,?,?,?,?,?,NULL,?)", (vid, f"Short {i}", 50, 500, "short", "youtube",
                                                                      "2026-02-01"))
        con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (vid, 0, 0, f"I have {i + 2} gyms. We do 1.2 million a "
                    "year. The fix is simple. Raise the price. That's the game."))
    con.commit()
    con.close()
    return db


def test_the_profile_is_measured_from_transcripts_with_targets_and_calibration(tmp_path):
    db = corpus(tmp_path)
    scores = write(tmp_path, "scores.csv", "id,outlier\n" + "".join(f"long{i},{i}\nshort{i},{i * 2}\n"
                                                                   for i in range(8)))
    words = write(tmp_path, "words.json", json.dumps([{"w": w, "s": i * 0.3, "e": i * 0.3 + 0.25} for i, w in
                                                      enumerate("Ich habe drei Stufen getestet. Du siehst es hier."
                                                                .split())]))
    targets = write(tmp_path, "targets.json", json.dumps({"script": {"lang": "de", "wpm": 178}, "long": {
        "numbers_per_minute": {"min": 2.5, "severity": "error", "why": "the reference says 3.5"}},
        "check_names": {"voice": "STIMME", "structure": "STRUKTUR"}}))
    out = tmp_path / "profile.json"
    rc = host("voice-profile").main(["--db", str(db), "--scores", str(scores), "--calibrate", f"spoken={words}",
                                     "--targets", str(targets), "--out", str(out), "--long-min-s", "60"])
    assert rc == 0
    p = json.loads(out.read_text())
    assert p["schema"] == 1 and p["source"]["long"] == 8 and p["source"]["short"] == 6
    assert p["reference"]["long_top"]["n"] == 2 and p["reference"]["long_top"]["ids"][0] == "long7"
    assert p["reference"]["long_top"]["metrics"]["numbers_per_minute"]["median"] > 0
    assert p["targets"]["long"]["numbers_per_minute"]["why"] == "the reference says 3.5"
    assert p["targets"]["long"]["sentence_words_median"]["severity"] == "hint"   # a proposal, not a rule
    assert p["calibration"]["spoken"]["timing"] == "measured" and p["script"]["wpm"] == 178
    assert p["check_names"]["voice"] == "STIMME"


def test_reference_moves_are_word_for_word_with_links(tmp_path):
    db = corpus(tmp_path)
    scores = write(tmp_path, "scores.csv", "id,outlier\n" + "".join(f"long{i},{i}\nshort{i},{i}\n" for i in range(8)))
    rm = host("reference-moves")
    cand = tmp_path / "cand.json"
    assert rm.main(["candidates", "--db", str(db), "--scores", str(scores), "--out", str(cand), "--long-min-s", "60"]) == 0
    c = json.loads(cand.read_text())
    assert c["hook"] and c["transition"] and c["short-first"] and c["proof"]
    h = c["hook"][0]
    assert h["quote"].startswith("I made 10 million dollars") and h["link"].endswith("v=long7&t=0s")
    picks = write(tmp_path, "picks.json", json.dumps({"hook": {"title": "Hook", "intro": "Say \"why\".", "pick": [
        {"id": h["id"], "pattern": "Result with a \"number\" first.", "transfer": "Ich habe 3 Spots gebaut.",
         "spoken": "Ich habe DREI / Spots gebaut, \"slow\"."}]}}))
    out = tmp_path / "moves"
    assert rm.main(["render", "--candidates", str(cand), "--picks", str(picks), "--dir", str(out)]) == 0
    md = (out / "hook.md").read_text()
    assert f"\"{h['quote']}\" [1]" in md and "[1] https://www.youtube.com/watch?v=long7&t=0s" in md
    assert "„number“" in md and "„why“" in md and "„Ich habe 3 Spots gebaut.“" in md   # only the passage is in "…"
    assert "- Spoken: Ich habe DREI / Spots gebaut, „slow“." in md


# ---- the checks ----------------------------------------------------------------------------------------------------
def test_a_good_script_passes_voice_and_structure(tmp_path):
    res = voicecheck.checks(write(tmp_path, "SCRIPT-v001.md", GOOD), "lang", PROFILE)
    assert not [c["id"] for c in res if c["pass"] is False], [(c["id"], c["measured"], c.get("points")) for c in res
                                                               if c["pass"] is False]
    ids = {c["id"] for c in res}
    assert {"STRUCTURE:intro", "STRUCTURE:window", "STRUCTURE:units", "STRUCTURE:rewards", "STRUCTURE:ending"} <= ids


def test_a_bad_script_fails_with_lines_and_rewrites(tmp_path):
    res = voicecheck.checks(write(tmp_path, "SCRIPT-v001.md", BAD), "lang", PROFILE)
    failed = {c["id"]: c for c in res if c["pass"] is False}
    assert "VOICE:fillers_per_100" in failed and "VOICE:numbers_per_minute" in failed
    assert {"STRUCTURE:intro", "STRUCTURE:ending", "STRUCTURE:units"} <= set(failed)
    fill = failed["VOICE:fillers_per_100"]["points"][0]
    assert "um" in fill["text"].lower() and "rewrite" in fill and " um" not in fill["rewrite"].lower()
    assert any("Thanks for watching" in p["text"] for p in failed["STRUCTURE:ending"]["points"])
    assert all(c["kind"] == "auto" and c["fix"] for c in failed.values())


def test_a_long_sentence_gets_a_split(tmp_path):
    long = ("I tested every setting on ten clips over two weeks with the same prompt, and the middle one built the "
            "best clip of all of them for half the price of the top one. ")
    text = GOOD.replace("Helpers beat thinking time.", long).replace("Test one frame first.", long) \
        .replace("More thinking, worse clip.", long)
    res = voicecheck.checks(write(tmp_path, "SCRIPT-v001.md", text), "lang", PROFILE)
    p90 = next(c for c in res if c["id"] == "VOICE:sentence_words_p90")
    assert p90["pass"] is False and p90["points"][0]["rewrite"].startswith("I tested every setting")
    assert ". The middle one built" in p90["points"][0]["rewrite"]


def test_a_cue_sheet_counts_bullets_as_spoken_time(tmp_path):
    p = write(tmp_path, "CUES-v001.md", SHEET)
    sp = voicecheck.read(p, PROFILE)
    assert sp.cue_sheet and len(sp.units) == 2 and len(sp.bullets) == 3 and sp.bullets[0]["numbers"] == ["40", "90"]
    assert sp.end > 3 * 12
    res = voicecheck.checks(p, "lang", PROFILE)
    assert not [c for c in res if c["pass"] is False], [(c["id"], c["measured"]) for c in res if c["pass"] is False]


def test_a_label_hook_and_a_statement_bridge_fail_the_loop_check(tmp_path):
    text = SHEET.replace("Point two. Rendering 600 frames took five hours on one card.", "Point two. Rendering.") \
        .replace("So where did the time go?", "Now the rendering.")
    res = voicecheck.checks(write(tmp_path, "CUES-v002.md", text), "lang", PROFILE)
    loops = next(c for c in res if c["id"] == "STRUCTURE:loops")
    assert loops["pass"] is False and {p["text"] for p in loops["points"]} == {"Point two. Rendering.",
                                                                               "Now the rendering."}


def test_a_short_needs_a_case_a_punch_and_no_ask(tmp_path):
    ok = "I built 3 clips for 40 dollars. Here are the clocks. The cheap one won by 50 minutes. Cheap won."
    res = voicecheck.checks(write(tmp_path, "SHORT-v001.md", ok), "short", PROFILE)
    assert not [c for c in res if c["pass"] is False]
    bad = "Why do clips cost so much? I tested 3 clips. Subscribe for more tests like this one, okay?"
    failed = {c["id"] for c in voicecheck.checks(write(tmp_path, "SHORT-v002.md", bad), "short", PROFILE)
              if c["pass"] is False}
    assert {"STRUCTURE:case", "STRUCTURE:punch", "STRUCTURE:no-ask"} <= failed


def test_a_short_may_end_with_the_channels_comment_ask(tmp_path, studio):
    (studio / "brand").mkdir()
    (studio / "brand" / "brand.json").write_text("{}")
    (studio / "brand" / "channel.json").write_text(json.dumps({"script": {
        "short_ask": "If you want this too, comment {WORD}."}}))
    ok = ("I built 3 clips for 40 dollars. Here are the clocks. The cheap one won by 50 minutes. Cheap won. "
          "If you want this too, comment CLIPS.")
    res = voicecheck.checks(write(tmp_path, "SHORT-v001.md", ok), "short", PROFILE)
    assert not [c for c in res if c["pass"] is False], [(c["id"], c["measured"]) for c in res if c["pass"] is False]
    ask = next(c for c in res if c["id"] == "STRUCTURE:no-ask")
    assert ask["measured"] == "comment ask CLIPS"
    missing = ok.replace(" If you want this too, comment CLIPS.", "")
    failed = {c["id"] for c in voicecheck.checks(write(tmp_path, "SHORT-v002.md", missing), "short", PROFILE)
              if c["pass"] is False}
    assert "STRUCTURE:no-ask" in failed
    twice = ok.replace("Here are the clocks.", "Subscribe for more.")
    res = voicecheck.checks(write(tmp_path, "SHORT-v003.md", twice), "short", PROFILE)
    assert next(c for c in res if c["id"] == "STRUCTURE:no-ask")["pass"] is False


def test_too_few_sentences_and_hint_mode_only_inform(tmp_path):
    p = write(tmp_path, "SCRIPT-v001.md", "Basically, um, the settings are kind of important for you. I tested it.")
    res = voicecheck.checks(p, "lang", PROFILE)
    assert not [c for c in res if c["id"].startswith("VOICE") and c["pass"] is False]
    assert any(c["id"] == "VOICE:fillers_per_100" and c["kind"] == "hinweis" for c in res)
    hint = voicecheck.checks(write(tmp_path, "SCRIPT-v002.md", BAD), "lang", PROFILE, "hint")
    failed = {c["id"] for c in hint if c["pass"] is False}
    # hint mode: the counts never fail (filler words stay hard), the build checks do
    assert failed and all(i == "VOICE:fillers_per_100" or i.startswith("STRUCTURE:") for i in failed)
    assert not failed & {"STRUCTURE:window", "STRUCTURE:rewards", "STRUCTURE:punch"}
    assert not [c for c in voicecheck.checks(write(tmp_path, "SCRIPT-v003.md", BAD), "lang", PROFILE, "hint",
                                             voice_hard=(), structure_soft=("intro", "window", "units", "loops",
                                                                            "rewards", "ending"))
                if c["pass"] is False]
    assert voicecheck.checks(p, "lang", PROFILE, "off") == []


def test_the_command_line(tmp_path, profile, capsys):
    p = write(tmp_path, "SCRIPT-v001.md", BAD)
    assert voicecheck.main(["check", str(p)]) == 1
    assert "FAIL  VOICE:fillers_per_100" in capsys.readouterr().out
    assert voicecheck.main(["check", str(write(tmp_path, "SCRIPT-v002.md", GOOD)), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True


# ---- in the style gate ---------------------------------------------------------------------------------------------
PASSING_CHECKER = r'''
import json, sys
print(json.dumps({"version": 1, "pass": True, "auto_pass": True, "kritik_offen": [],
                  "checks": [{"id": "S1", "kind": "auto", "pass": True}]}))
'''


@pytest.fixture
def skill(studio):
    d = studio / "skills" / "deutscher-hormozi" / "scripts"
    d.mkdir(parents=True)
    (d.parent / "SKILL.md").write_text("---\nname: deutscher-hormozi\ndescription: test\n---\n")
    (d / "stil_check.py").write_text(PASSING_CHECKER)
    return d


@pytest.fixture
def episode(studio, crew):
    ep = episodes.create("Clips im Test")["id"]
    for s in ("idea", "title"):
        episodes.set_step(ep, s, "done")
    episodes.set_step(ep, "script", "working")
    return ep


def test_the_gate_adds_failing_voice_checks_and_sends_the_lines_back(skill, profile, episode):
    from crewcut.conductor import queue
    (paths.episode_dir(episode) / "brief" / "SCRIPT-v001.md").write_text(BAD + "\n---\nnotes\n")
    v = stylegate.check(episode)
    r = v["results"][0]
    assert v["pass"] is False and not r["auto_pass"] and "VOICE:fillers_per_100" in r["voice"]
    failed = {x["id"]: x for x in r["failed"]}
    assert failed["VOICE:fillers_per_100"]["points"][0]["rewrite"]
    pts = stylegate.points(v)
    assert any(p["id"] == "VOICE:fillers_per_100" and p.get("rewrite") for p in pts)
    out = stylegate.writer_round(episode, v)
    assert out["action"] == "writer"
    task = queue.get(out["job"])["task"]
    assert "VOICE:fillers_per_100" in task and "->" in task


def test_the_gate_passes_a_good_script_and_ignores_voice_when_off(skill, profile, episode, studio):
    brief = paths.episode_dir(episode) / "brief"
    (brief / "SCRIPT-v001.md").write_text(GOOD + "\n---\nnotes\n")
    assert stylegate.check(episode)["pass"] is True
    (brief / "SCRIPT-v002.md").write_text(BAD + "\n---\nnotes\n")
    assert stylegate.check(episode)["pass"] is False
    (studio / "config" / "crewcut.toml").write_text('[style_gate]\nvoice = "off"\n'
                                                     'voice_profile = "brand/voice/profile.json"\n')
    assert stylegate.check(episode)["pass"] is True


def test_a_broken_profile_is_a_hint_not_a_failure(skill, profile, episode):
    profile.write_text("{not json")
    (paths.episode_dir(episode) / "brief" / "SCRIPT-v001.md").write_text(BAD + "\n---\nnotes\n")
    v = stylegate.check(episode)
    assert v["pass"] is True and v["results"][0]["hints"] == 1


def test_the_writer_note_names_the_voice_check(skill, profile, episode):
    assert "crewcut voice check" in stylegate.writer_note(episode)


def test_the_cli_delegates(profile, tmp_path, monkeypatch):
    from crewcut import cli
    p = write(tmp_path, "SCRIPT-v001.md", GOOD)
    monkeypatch.setattr(sys, "argv", ["crewcut"])
    assert cli.main(["voice", "check", str(p)]) == 0


def test_in_hint_mode_the_command_and_the_writer_never_aim_at_a_count(tmp_path, profile, studio, capsys):
    """Abnahme Hormozi round 2, S1: with voice = "hint" no count blocks and the Writer is not told to hit one."""
    from crewcut.conductor import prompts
    (studio / "config" / "crewcut.toml").write_text('[style_gate]\nvoice = "hint"\n'
                                                     'voice_profile = "brand/voice/profile.json"\n')
    good = write(tmp_path, "SCRIPT-v002.md", GOOD)
    assert voicecheck.main(["check", str(good)]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "never a target" in out and "build checks stay hard" in out
    bad = write(tmp_path, "SCRIPT-v001.md", BAD)
    assert voicecheck.main(["check", str(bad)]) == 1   # filler words and the build stay hard
    out = capsys.readouterr().out
    assert "FAIL  VOICE:fillers_per_100" in out and "HINT  VOICE:sentence_words_median" in out or \
        "HINT  VOICE:" in out
    assert "FAIL  VOICE:numbers_per_minute" not in out and "FAIL  VOICE:you_per_100" not in out
    assert voicecheck.main(["check", str(bad), "--mode", "block"]) == 1
    capsys.readouterr()
    line = voicecheck.prompt_lines()
    assert "never a target" in line and "build checks stay hard" in line
    block = prompts.voice_block()
    assert "never targets" in block and "Write inside the bands" not in block
    assert "Never add, cut or bend a sentence" in block
    assert "never a target" in stylegate.writer_note(None) or "crewcut voice check" not in stylegate.writer_note(None)


def test_the_writer_of_a_short_hears_the_channels_comment_ask(profile, studio):
    from crewcut.conductor import prompts
    assert "comment ask" not in prompts.voice_block(short=True)
    (studio / "brand" / "brand.json").write_text("{}")
    (studio / "brand" / "channel.json").write_text(json.dumps({"script": {
        "short_ask": "Wenn du das auch willst, kommentier {WORD}."}}))
    block = prompts.voice_block(short=True)
    assert '"Wenn du das auch willst, kommentier WORD."' in block and "only ask in the Short" in block
    assert "comment ask" not in prompts.voice_block(short=False)
