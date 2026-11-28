"""The script craft (crewcut.craft): opening, counted units, spoken rhythm, ending (rule set of 26 Nov 2026).

Synthetic samples: a verdict and a link sentence at the end, no goodbye, no recap, one "try this", one fixed ask in the
middle."""

import importlib.util
import json
from pathlib import Path

from crewcut import brand, craft

ROOT = Path(__file__).resolve().parents[2]

PLAN_EN = """
---
Premise: Four agents can edit a podcast episode in one evening, while the taste stays with the person.
Arc: hook the finished episode, tension a weekend of editing, turn the work split into four jobs, payoff the cost, close
the verdict
Beats:
- the transcript
- the rough cut
- the check
- the decision
[[first content | "So job one is the transcript"]]
[[urteil | "So four agents did the editing in one evening"]]
"""

GOOD_EN = """

I cut a whole podcast episode with four AI agents, and I only said yes or no.

Ninety minutes of raw audio became a 22 minute episode in one evening.

If you edit alone, you know what that costs you. Editing eats whole weekends.

Today I'll show you the four jobs I split the work into, and the agent behind each one.

And at the end I'll show you what the whole evening cost.



So job one is the transcript. Why start with text? A cut is only a start time and an end time, and text is what a model writes best.

So the first agent writes down every word you say, each with its exact time.

Let's say you recorded a sentence three times. Which take stays? The agent keeps your last full take.

That alone took your 90 minutes of audio down to 41 minutes of usable takes.

Did it get everything right? No. It failed once when two people talked at the same time, so now it marks those spots for you.

And what does that mean for you? You read a page of text instead of scrubbing through an hour of audio.



Then comes job two, the rough cut, and here the numbers start to matter.

Now you might think a model has to watch your video to cut it. Does it? It does not.

It reads your transcript and picks the strongest sentences, which means it works on text the whole way.

Your 22 minutes times 150 words per minute, that's about 3,300 words to keep.

So the agent keeps about one word in four, and you decide which version stays. On my episode it offered two versions of the opening, and I took the shorter one in under a minute.

Try this. Before your next edit, write down the three sentences your episode must keep.

If you like tests with real numbers like these, subscribe. No company pays for them.



Job three is the check, and the rule is simple. Whoever builds never checks their own work.

Why not? You see your own mistakes last, and so does a model.

So a second agent reads every cut against your transcript before you hear a single second of it. It looks for doubled starts, words cut in half and sentences that end too early.

A full check takes 40 minutes on a laptop against 4 minutes on a rented machine.

Said differently, 40 minutes against 4, for the same result on the same episode, with the same rules.

And who pays for the rented machine? You do, about 30 cents for one check of a whole episode.



And job four stays with you, because it is the decision about what goes out.

That is why every step ends with one question to you, and nothing goes out without your yes.

Does that sound slow? It is not, because each question takes you a few seconds. On this episode I answered eleven of them, and the longest one took me half a minute.

So let's say the check finds a cut in the middle of a word. You get one card with the fix, and one tap decides it.

That way you never publish anything you have not seen, and every correction you give becomes a rule for the next episode.



And now the cost I promised at the start.

It came to 3 hours of agent work and 14 dollars at list prices for the whole evening.



So four agents did the editing in one evening, and the taste stayed with me.

The checklist for your own setup is free, the link is in the description.
""" + PLAN_EN

BAD_EN = """
Hey everyone, welcome back to the channel.

Today I want to talk about editing with AI, which is something I have been thinking about a lot lately and want to share.

I tried a few tools last month. I liked some of them. I did not like others.

My setup is simple. I record on my laptop. I use my own microphone. I edit in the evening.

I think the tools are getting better every week. I use them for my own episodes now.

I wrote my notes into a document. I read them again before each episode. I keep my files in one folder.

I also tested a tool for captions. I found it fast. I did not change much afterwards.

I learned a lot from this. My episodes look cleaner now. My evenings are shorter.

Please subscribe to the channel. Leave a comment below. The link to my notes is in the description.

Thanks for watching.
"""

PLAN_DE = """
---
Prämisse: Vier Agents schneiden eine Podcast-Folge an einem Abend, der Geschmack bleibt beim Menschen.
Bogen: Einstieg die fertige Folge, Problem ein Wochenende Schnitt, Wende die Arbeit in vier Jobs, Auflösung die
Rechnung, Schluss das Urteil
Beats:
- die Abschrift
- der Rohschnitt
- die Prüfung
- die Entscheidung
"""

GOOD_DE = """

Diese Podcast-Folge haben vier KI-Agents geschnitten, und ich habe nur Ja oder Nein gesagt.

Aus 90 Minuten Rohmaterial wurden an einem Abend 22 Minuten Folge.

Wenn du allein schneidest, weißt du, was das kostet. Schnitt frisst ganze Wochenenden.

Heute zeige ich dir die vier Jobs, in die ich die Arbeit zerlegt habe.

Und am Ende zeige ich dir die Rechnung für diesen Abend.



Also, Job eins ist die Abschrift. Warum fängt alles mit Text an? Ein Schnitt ist nur eine Startzeit und eine Endzeit, und Text kann ein Modell am besten.

Also schreibt der erste Agent jedes Wort mit, das du sagst, jeweils mit der genauen Zeit.

Nehmen wir an, du sagst einen Satz dreimal. Welcher Versuch bleibt? Dein letzter vollständiger Versuch.

Das allein macht aus deinen 90 Minuten Aufnahme 41 Minuten brauchbare Takes, ohne dass du eine Minute davon anhörst.

Hat er alles richtig gemacht? Nein. Einmal ist er gescheitert, als zwei Leute gleichzeitig sprachen, und jetzt markiert er solche Stellen für dich.

Und was heißt das für dich? Du liest eine Seite Text, statt eine Stunde Ton abzusuchen.



Dann kommt Job zwei, der Rohschnitt, und hier zählen die Zahlen.

Jetzt denkst du vielleicht, ein Modell muss dein Video sehen, um es zu schneiden. Muss es das? Nein, muss es nicht.

Es liest deine Abschrift und wählt die stärksten Sätze, das heißt, es arbeitet die ganze Zeit mit Text.

Dazu eine Rechnung. Deine 22 Minuten mal 150 Wörter pro Minute, das sind rund 3.300 Wörter, die bleiben.

Also behält der Agent etwa jedes vierte Wort, und du entscheidest, welche Fassung bleibt. Bei meiner Folge kamen zwei Fassungen vom Einstieg, und ich habe in unter einer Minute die kürzere genommen.

Probier das. Schreib vor deinem nächsten Schnitt die drei Sätze auf, die deine Folge behalten muss.

Wenn du Tests mit echten Zahlen magst, abonnier den Kanal. Kein Anbieter bezahlt sie.



Job drei ist die Prüfung, und die Regel ist einfach. Wer baut, prüft nie selbst.

Warum nicht? Du siehst deine eigenen Fehler zuletzt, und einem Modell geht es genauso.

Deshalb liest ein zweiter Agent jeden Schnitt gegen deine Abschrift, bevor du auch nur eine einzige Sekunde davon hörst. Er sucht doppelte Satzanfänge, halbe Wörter und Sätze, die zu früh enden.

Eine ganze Prüfung dauert 40 Minuten auf dem Laptop gegen 4 Minuten auf einer gemieteten Maschine.

Anders gesagt, 40 Minuten gegen 4, für dasselbe Ergebnis mit denselben Regeln.

Und wer bezahlt die gemietete Maschine? Du, etwa 30 Cent für eine Prüfung der ganzen Folge, und die Maschine ist danach sofort wieder weg.



Und Job vier bleibt bei dir, denn das ist die Entscheidung, was rausgeht.

Deshalb endet jeder Schritt mit einer Frage an dich, und nichts geht raus ohne dein Ja, auch kein einziger Schnitt.

Klingt das langsam? Ist es nicht, denn jede Frage kostet dich ein paar Sekunden. Bei dieser Folge waren es elf Fragen, und die längste hat mich eine halbe Minute gekostet.

Also nehmen wir an, die Prüfung findet einen Schnitt mitten im Wort. Dann bekommst du eine Karte mit der Lösung, und ein Tippen entscheidet.

So veröffentlichst du nie etwas, das du nicht gesehen hast, und jede Korrektur, die du einmal gibst, wird eine feste Regel für die nächste Folge.



Und jetzt die Rechnung, die ich dir am Anfang versprochen habe.

Es waren 3 Stunden Arbeit der Agents und 14 Dollar zu Listenpreisen, für den ganzen Abend.



Den Schnitt machen jetzt vier Agents an einem Abend, den Geschmack nicht.

Die Checkliste für deinen eigenen Aufbau ist kostenlos, der Link steht in der Beschreibung.
""" + PLAN_DE


def rules(r, level=None):
    return [f["rule"] for f in r["findings"] if level is None or f["level"] == level]


def test_good_english_script_passes_all_four_groups():
    r = craft.check(GOOD_EN, "en", 150)
    assert r["findings"] == [], r["findings"]
    s = r["stats"]
    assert s["language"] == "en" and s["takeaways"] == 1 and s["depth_parts"] == 4
    assert s["ending_calls_to_action"] == ["link"] and s["ending_seconds"] <= 25
    assert s["you"] >= s["i"] and s["objections"] == 1 and s["live_math"] >= 1
    assert 7.5 <= s["questions_per_1000"] <= 20 and len(s["ask_at"]) == 1
    passed = " ".join(r["passed"])
    for want in ("plan with a count", "open loop", "no limit or caveat before the first content", "one link sentence",
                 "fixed ask", "no goodbye and no recap", "open loop is resolved", "answered in the next sentence"):
        assert want in passed, want


def test_good_german_script_passes_all_four_groups():
    r = craft.check(GOOD_DE, None, 150)          # the language comes from the text
    assert r["stats"]["language"] == "de"
    assert r["findings"] == [], r["findings"]
    assert r["stats"]["takeaways"] == 1 and r["stats"]["ending_calls_to_action"] == ["link"]
    assert any('plan with a count ("vier Jobs")' in p for p in r["passed"])


def test_bad_script_names_each_missing_part():
    r = craft.check(BAD_EN, "en", 150)
    assert set(rules(r, "error")) == {"greeting", "greeting_end"}
    warns = set(rules(r, "warn"))
    assert {"roadmap", "questions", "cta", "you_i"} <= warns
    assert "hook_number" not in rules(r) and "ending_parts" not in rules(r)   # retired on 26 Nov 2026
    cta = " ".join(f["text"] for f in r["findings"] if f["rule"] == "cta")
    assert "request in the ending (comment)" in cta and "the fixed ask stands at 87 %" in cta


def test_greeting_is_checked_even_in_a_short_text():
    r = craft.check("Hallo zusammen! Heute geht es um Schnitt.\n", "de", 150)
    assert rules(r) == ["greeting"]


def test_no_goodbye_and_no_recap_at_the_end():
    """The old ending (the parts as one list, thanks for watching) is now an error, in both languages."""
    old_end = ("\n\n\n\nSo, the four jobs in one sentence. One agent writes, one cuts, one checks, and you decide.\n\n"
               "Thanks for watching.\n")
    text = GOOD_EN.replace("The checklist for your own setup is free, the link is in the description.",
                           "The checklist for your own setup is free, the link is in the description." + old_end)
    r = craft.check(text, "en", 150)
    assert {"greeting_end", "recap"} <= set(rules(r, "error"))
    de = GOOD_DE.replace("der Link steht in der Beschreibung.",
                         "der Link steht in der Beschreibung.\n\nNoch einmal die vier Jobs in einem Satz. Einer "
                         "schreibt, einer schneidet, einer prüft.\n\nDanke fürs Zuschauen.")
    r = craft.check(de, None, 150)
    assert {"greeting_end", "recap"} <= set(rules(r, "error"))
    # the channel's own closing line is its choice: the goodbye check leaves exactly that sentence alone
    r = craft.check(text, "en", 150, {"closing_line": "Thanks for watching."})
    assert "greeting_end" not in rules(r) and "recap" in rules(r, "error")


def test_retired_checks_stay_off_even_when_a_pack_names_them():
    r = craft.check(BAD_EN, "en", 150, {"checks": {"hook_number": "error", "ending_parts": "error"}})
    assert "hook_number" not in rules(r) and "ending_parts" not in rules(r)
    old = craft.check(GOOD_EN, "en", 150, {"checks": {"limit": "warn"}, "limit_seconds": 45})
    assert "limit" in rules(old, "warn")      # the old limit by 0:45 runs only when a pack switches it on


def test_a_limit_before_the_first_content():
    text = GOOD_EN.replace("And at the end I'll show you what the whole evening cost.",
                           "And at the end I'll show you what the whole evening cost. Is it perfect? No, it is not "
                           "perfect yet.")
    r = craft.check(text, "en", 150)
    f = next(f for f in r["findings"] if f["rule"] == "limit_before_content")
    assert f["level"] == "warn" and "perfect" in f["text"]
    assert not any("before the first content" in x for x in r["passed"])


def test_open_loop_must_be_resolved():
    text = GOOD_EN.replace("And now the cost I promised at the start.", "And now a word on the hardware.") \
                  .replace(" for the whole evening.", ".").replace("did the editing in one evening", "did the editing")
    r = craft.check(text, "en", 150)
    assert "loop_resolved" in rules(r, "warn")


def test_more_than_one_try_this_line():
    text = GOOD_EN.replace("And who pays for the rented machine?", "Try this. Let a second chat review your work. And "
                           "who pays for the rented machine?")
    r = craft.check(text, "en", 150)
    f = next(f for f in r["findings"] if f["rule"] == "takeaways")
    assert f["level"] == "warn" and '2 "try this" lines' in f["text"]


def test_a_long_ending_and_a_second_request():
    long_end = " ".join(["The agents did the cutting while I watched the numbers on the screen."] * 6)
    text = GOOD_EN.replace("The checklist for your own setup is free, the link is in the description.",
                           long_end + " The checklist is free, the link is in the description. Subscribe for more.")
    r = craft.check(text, "en", 150)
    assert {"ending_length", "cta", "subscribe_once"} <= set(rules(r, "warn"))


def test_the_fixed_ask_belongs_in_the_middle():
    early = GOOD_EN.replace("If you like tests with real numbers like these, subscribe. No company pays for them.", "")
    early = early.replace("Editing eats whole weekends.", "Editing eats whole weekends. If you like tests like this, "
                          "subscribe.")
    f = next(f for f in craft.check(early, "en", 150)["findings"] if f["rule"] == "cta")
    assert "between 15 and 60 %" in f["text"]
    none = GOOD_EN.replace("If you like tests with real numbers like these, subscribe. No company pays for them.", "")
    f = next(f for f in craft.check(none, "en", 150)["findings"] if f["rule"] == "cta")
    assert "no fixed ask" in f["text"]


def test_a_packs_own_fixed_ask_ends_with_its_text():
    """Since 28 Nov 2026 a channel's one fixed ask can point to the link in the description instead of the subscribe
    line (channel.json script.craft.ask_ends_with)."""
    ask = "Die Vorlage dazu habe ich dir gebaut, der Link ist in der Videobeschreibung."
    text = GOOD_DE.replace("Wenn du Tests mit echten Zahlen magst, abonnier den Kanal. Kein Anbieter bezahlt sie.", ask)
    assert ask in text
    cfg = {"ask_ends_with": "der Link ist in der Videobeschreibung"}
    r = craft.check(text, "de", 150, cfg)
    assert not [f for f in r["findings"] if f["rule"] in ("cta", "subscribe_once")], r["findings"]
    assert len(r["stats"]["ask_at"]) == 1 and 0.15 <= r["stats"]["ask_at"][0] <= 0.6
    # without the key the same script has no fixed ask (subscribe)
    assert any("no fixed ask (subscribe)" in f["text"] for f in craft.check(text, "de", 150)["findings"]
               if f["rule"] == "cta")
    gone = text.replace(ask, "")
    assert any('no fixed ask ending with "der Link ist in der Videobeschreibung"' in f["text"]
               for f in craft.check(gone, "de", 150, cfg)["findings"] if f["rule"] == "cta")


def test_levels_and_limits_come_from_the_pack():
    r = craft.check(BAD_EN, "en", 150, {"checks": {"greeting": "off", "roadmap": "error", "questions": "hint"}})
    assert "greeting" not in rules(r)
    assert "roadmap" in rules(r, "error") and "questions" in rules(r, "hint")
    faster = craft.check(GOOD_EN, "en", 150, {"hook_seconds": 10})
    assert "open_loop" in rules(faster, "hint")  # 10 s are too short for the open loop
    strict = craft.check(GOOD_EN, "en", 150, {"idea_seconds": [60, 75]})
    assert "part_length" in rules(strict, "warn")


def test_questions_without_an_answer_and_answers_with_because():
    text = GOOD_EN.replace("So job one is the transcript. Why start with text?", "So job one is the transcript.") \
                  .replace("And what does that mean for you?", "And what does that mean for you? \n\n\n\nWhy?")
    r = craft.check(text, "en", 150)
    assert "answers" in rules(r)
    weil = GOOD_DE.replace("Warum fängt alles mit Text an? Ein Schnitt", "Warum fängt alles mit Text an? Weil ein Schnitt")
    f = next(f for f in craft.check(weil, None, 150)["findings"] if f["rule"] == "answers")
    assert "because" in f["text"] and "Weil" in f["text"]


def test_script_check_runs_the_craft_and_the_sentence_limit():
    neutral = brand.load(ROOT / "packs" / "neutral")
    sc = _script_check()
    r = sc.check_script(GOOD_EN, neutral)
    assert r["errors"] == 0 and r["stats"]["craft"]["takeaways"] == 1, r["findings"]
    assert sc.check_script(GOOD_DE, neutral)["errors"] == 0
    assert not [f for f in r["findings"] if f["area"] in ("hook", "depth", "rhythm", "ending")], r["findings"]
    assert r["manual"] and r["stats"]["minutes"] > 3
    long = GOOD_EN.replace("The checklist for your own setup is free, the link is in the description.",
                           "The checklist for your own setup is free, and it holds the four jobs, the prompts, the "
                           "costs per episode and the rules I wrote down, so the link is in the description.")
    assert any(f["area"] == "sentences" and f["level"] == "error" for f in sc.check_script(long, neutral)["findings"])
    b = sc.check_script(BAD_EN, neutral)
    assert any(f["area"] == "hook" and f["level"] == "error" for f in b["findings"])
    assert any(f["area"] == "ending" and f["level"] == "error" for f in b["findings"])   # the thanks at the end


def test_script_check_minutes_from_the_brief(capsys, tmp_path):
    sc = _script_check()
    p = tmp_path / "SCRIPT-v001.md"
    p.write_text(GOOD_DE, encoding="utf-8")
    pack = str(ROOT / "packs" / "neutral")
    assert sc.main([str(p), "--craft", "--pack", pack]) == 0
    out = capsys.readouterr().out
    assert "craft: parts" in out and "By hand" in out
    assert sc.main([str(p), "--craft", "--pack", pack, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "craft"
    sc.main([str(p), "--pack", pack, "--minutes", "11-14", "--json"])
    length = [f for f in json.loads(capsys.readouterr().out)["findings"] if f["area"] == "length"]
    assert length and "Target 1650 to 2100" in length[0]["text"]
    assert sc.main([str(p), "--pack", pack, "--minutes", "eleven"]) == 2


def _script_check():
    path = ROOT / "skills" / "script" / "scripts" / "script_check.py"
    spec = importlib.util.spec_from_file_location("craft_script_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
