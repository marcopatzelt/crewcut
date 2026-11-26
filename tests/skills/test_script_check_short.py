"""script_check.py --short: the reel rules for a Short's script. The long mode is tested in test_script_check.py."""

from conftest import load_script

sc = load_script("skills/script/scripts/script_check.py")

STORY = """Three weeks ago I gave an agent my whole video edit. It took 37 minutes, and I watched every one of them.
I thought it would fail on the first cut. I was sure of it, because my own first cuts are always a mess.

But it found every doubled sentence start. I checked all 14 of them by hand, with headphones on.
It even caught a breath I had missed for months. That one hurt a little, if I am honest with myself.

Now I only listen to the joins and the ends of sentences. That is my job now, and it takes me ten minutes.
I still do not trust it with the music. Maybe that is the next test, in a week or two, on a real episode.
The edit used to eat my whole Sunday. Last Sunday I went for a walk instead and came back to a finished cut.
The final listen stays mine.

---
proof: screen recording of the cut report
"""

GERMAN = """Vor drei Wochen habe ich einem Agenten meinen ganzen Schnitt gegeben. Er brauchte 37 Minuten.
Ich dachte, er scheitert am ersten Schnitt. Ich war mir sicher.
Aber er fand jeden doppelten Satzanfang. Ich habe alle 14 von Hand geprüft.
"""


def kinds(r, level=None):
    return [f["area"] for f in r["findings"] if level is None or f["level"] == level]


def test_a_good_story_passes(neutral):
    r = sc.check_short(STORY, neutral)
    assert r["mode"] == "short" and r["errors"] == 0, r["findings"]
    assert r["stats"]["i_sentences"] > r["stats"]["you_sentences"]
    assert 110 <= r["stats"]["words"] <= 170
    text = " ".join(r["passed"])
    assert "turn:" in text and "number: 37" in text and "time anchor: three weeks ago" in text


def test_reel_rules_find_the_robot_script(neutral):
    text = ("Imagine you could edit faster — this is a game changer. It is not a tool, it is a team. "
            "You should try it. Your videos will thank you.\n")
    r = sc.check_short(text, neutral)
    errors = kinds(r, "error")
    assert {"length", "phrases", "opening"} <= set(errors)      # no number in the first 12 words
    assert "i-form" in kinds(r, "warn")                          # a warning since 26 Nov 2026
    msg = next(f["text"] for f in r["findings"] if f["area"] == "phrases")
    assert "Imagine" in msg and "game changer" in msg and "—" in msg and "It is not a tool, it is" in msg
    assert {"turn", "proof", "anchor"} <= set(kinds(r, "warn"))


def test_not_x_not_y_but_z(neutral):
    r = sc.check_short("I built it. Not for money. Not for fame. But because I was bored.\n", neutral)
    assert any(f["area"] == "phrases" and "Not for money" in f["text"] for f in r["findings"])


def test_crooked_numbers():
    assert sc.crooked("37") and sc.crooked("4.3") and sc.crooked("1,247") and sc.crooked("5,5")
    assert not sc.crooked("40") and not sc.crooked("1,000") and not sc.crooked("7") and not sc.crooked("2026")


def test_visible_proof_replaces_the_number(neutral):
    text = "I tried it last week. I thought it would break. But it held up.\n"
    assert "proof" in kinds(sc.check_short(text, neutral), "warn")
    assert "proof" not in kinds(sc.check_short(text + "\n---\ndemo: the screen recording\n", neutral))
    assert "proof" not in kinds(sc.check_short(text, neutral, proof="run log"))


def test_german_lists(neutral):
    r = sc.check_short(GERMAN, neutral, lang="de")
    assert r["stats"]["language"] == "de"
    assert not {"i-form", "turn", "proof", "anchor", "phrases"} & set(kinds(r)), r["findings"]
    bad = sc.check_short("Stell dir vor, du hast einen Game-Changer. Das ist nicht nur ein Tool, sondern ein Team.\n",
                         neutral, lang="de")
    msg = next(f["text"] for f in bad["findings"] if f["area"] == "phrases")
    assert "Stell dir vor" in msg and "Game-Changer" in msg and "sondern" in msg


def test_unknown_language_falls_back_to_english(neutral):
    r = sc.check_short(STORY, neutral, lang="fr")
    assert "language" in kinds(r, "hint") and r["errors"] == 0


def test_phrase_file_format(tmp_path):
    p = tmp_path / "phrases-xx.txt"
    p.write_text("# comment\n\nbuzz*\nre:\\bfoo\\s+bar\\b\n", encoding="utf-8")
    pats = sc.load_phrases("xx", p)
    assert [label for label, _ in pats] == ["buzz*", r"\bfoo\s+bar\b"]
    assert pats[0][1].search("Buzzword") and pats[1][1].search("FOO  bar")
    for lang in ("en", "de"):
        assert len(sc.load_phrases(lang)) > 20


def test_main_short(tmp_path, capsys):
    p = tmp_path / "SCRIPT-v001.md"
    p.write_text(STORY, encoding="utf-8")
    assert sc.main([str(p), "--short", "--pack", "packs/neutral"]) == 0
    out = capsys.readouterr().out
    assert "I-sentences" in out and "This really happened" in out
    p.write_text("Imagine this.\n", encoding="utf-8")
    assert sc.main([str(p), "--short", "--pack", "packs/neutral", "--json"]) == 1


def test_a_short_has_no_question_first_no_ask_and_a_short_last_line(neutral):
    """The Short rules of 26 Nov 2026: sentence 1 no question, a number in the first 12 words, no ask, a last
    sentence of at most 8 words, 2 to 3 counted steps (levels in channel.json script.short_checks)."""
    bad = ("Did you know agents can cut video? I tried it last week on my own channel. "
           "It found doubled starts and cut breaths. Subscribe for more tests like this one, and see the link below. "
           "I think this is the start of something really big for every creator out there.\n")
    r = sc.check_short(bad, neutral)
    errs = [(f["area"], f["text"]) for f in r["findings"] if f["level"] == "error"]
    assert any(a == "opening" and "is a question" in t for a, t in errs)
    assert any(a == "opening" and "no number in the first 12 words" in t for a, t in errs)
    assert {"ask", "ending"} <= {a for a, _ in errs}
    assert "steps" in kinds(r, "warn")
    good = ("I gave an agent 37 minutes of raw video last week. First, it read the transcript. "
            "Second, it cut every doubled start. I thought it would miss the breaths. "
            "But it found all 14 of them. One job stayed mine. The final listen.\n")
    r = sc.check_short(good, neutral)
    assert not {"opening", "ask", "ending", "steps"} & set(kinds(r, "error") + kinds(r, "warn")), r["findings"]
    assert r["stats"]["counted_steps"] == 2
    soft = {**neutral.channel, "script": {**neutral.channel["script"],
                                          "short_checks": {"ask": "off", "last_sentence": "hint"}}}
    pack = type(neutral)(**{**neutral.__dict__, "channel": soft})
    r = sc.check_short(bad, pack)
    assert "ask" not in kinds(r) and "ending" in kinds(r, "hint")
