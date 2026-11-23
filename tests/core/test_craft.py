"""The script craft (crewcut.craft): hook in 30 seconds, depth pattern, spoken rhythm, ending. Synthetic samples."""

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
"""

GOOD_EN = """


I cut a whole podcast episode with four AI agents, and I only said yes or no.

Ninety minutes of raw audio became a 22 minute episode in one evening.

If you edit alone, you know what that costs you. Editing eats whole weekends.

Today I'll show you the four jobs I split the work into, and the agent behind each one.

And at the end I'll show you what the whole evening cost.

Is it perfect? No.

The agents can't hear music, so I still check the sound myself.



So job one is the transcript. Why start with text?

Because a cut is only a start time and an end time, and text is what a model writes best.

So the first agent writes down every word you say, each with its exact time.

Let's say you recorded a sentence three times. The agent keeps your last full take.

That alone took your 90 minutes of audio down to 41 minutes of usable takes.

It failed once when two people talked at the same time. Now it marks those spots for you.

Try this. Ask for a transcript with time stamps, and give the model the text instead of the video.



Then comes job two, the rough cut, and here the numbers start to matter.

Now you might think a model has to watch your video to cut it. It does not.

It reads your transcript and picks the strongest sentences, which means it works on text the whole way.

Your 22 minutes times 150 words per minute, that's about 3,300 words to keep.

So the agent keeps about one word in four, and you decide which version stays.

Try this. Before your next edit, write down the three sentences your episode must keep.

If you like tests with real numbers like these, subscribe. No company pays for them.



Job three is the check, and the rule is simple. Whoever builds never checks their own work.

The reason is that you see your own mistakes last, and so does a model.

So a second agent reads every cut against your transcript before you hear a single second.

A full check takes 40 minutes on a laptop against 4 minutes on a rented machine.

Said differently, 40 minutes against 4, for the same result.

Try this. Let a second chat review your work, one that did not write it.



And job four stays with you, because it is the decision.

That is why every step ends with one question to you, and nothing goes out without your yes.

That sounds slower than it is, because each question takes you a few seconds.

So let's say the check finds a cut in the middle of a word. You get one card with the fix, and one tap decides it.

That way you never publish anything you have not seen, and every correction becomes a rule.

Try this. Write every correction you had to give twice into one file the model reads each time.



And now the cost I promised at the start.

It came to 3 hours of agent work and 14 dollars at list prices for the whole evening.



So, the four jobs in one sentence. One agent writes, one cuts, one checks, and you decide.

What do I still do myself? I record, I listen to the sound, and I say yes or no.

And my verdict is simple. The agents do the editing now, but not the taste.

And the checklist with all four jobs is free, the link is in the description.

Thanks for watching.
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

Ist das perfekt? Nein.

Denn Musik hören kann keiner der Agents, den Ton prüfe ich selbst.



Also, Job eins ist die Abschrift. Warum fängt alles mit Text an?

Weil ein Schnitt nur eine Startzeit und eine Endzeit ist, und Text kann ein Modell am besten.

Also schreibt der erste Agent jedes Wort mit, das du sagst, jeweils mit der genauen Zeit.

Nehmen wir an, du sagst einen Satz dreimal. Dann bleibt dein letzter vollständiger Versuch.

Das allein macht aus deinen 90 Minuten Aufnahme 41 Minuten brauchbare Takes.

Einmal ist er gescheitert, als zwei Leute gleichzeitig sprachen. Jetzt markiert er solche Stellen für dich.

Probier das. Lass dir eine Abschrift mit Zeitmarken geben, und gib dem Modell den Text statt des Videos.



Dann kommt Job zwei, der Rohschnitt, und hier zählen die Zahlen.

Jetzt denkst du vielleicht, ein Modell muss dein Video sehen, um es zu schneiden. Muss es nicht.

Es liest deine Abschrift und wählt die stärksten Sätze, das heißt, es arbeitet die ganze Zeit mit Text.

Dazu eine Rechnung. Deine 22 Minuten mal 150 Wörter pro Minute, das sind rund 3.300 Wörter, die bleiben.

Also behält der Agent etwa jedes vierte Wort, und du entscheidest, welche Fassung bleibt.

Probier das. Schreib vor deinem nächsten Schnitt die drei Sätze auf, die deine Folge behalten muss.

Wenn du Tests mit echten Zahlen magst, abonnier den Kanal. Kein Anbieter bezahlt sie.



Job drei ist die Prüfung, und die Regel ist einfach. Wer baut, prüft nie selbst.

Und der Grund ist, dass du deine eigenen Fehler zuletzt siehst, und einem Modell geht es genauso.

Deshalb liest ein zweiter Agent jeden Schnitt gegen deine Abschrift, bevor du eine Sekunde hörst.

Eine ganze Prüfung dauert 40 Minuten auf dem Laptop gegen 4 Minuten auf einer gemieteten Maschine.

Anders gesagt, 40 Minuten gegen 4, für dasselbe Ergebnis.

Probier das. Lass deine Arbeit von einem zweiten Chat prüfen, der sie nicht geschrieben hat.



Und Job vier bleibt bei dir, denn das ist die Entscheidung.

Deshalb endet jeder Schritt mit einer Frage an dich, und nichts geht raus ohne dein Ja.

Das klingt langsamer, als es ist, denn jede Frage kostet dich ein paar Sekunden.

Also nehmen wir an, die Prüfung findet einen Schnitt mitten im Wort. Dann bekommst du eine Karte, und ein Tippen entscheidet.

So veröffentlichst du nie etwas, das du nicht gesehen hast, und jede Korrektur wird eine Regel.

Probier das. Schreib jede Korrektur, die du zweimal geben musstest, in eine Datei, die das Modell jedes Mal liest.



Und jetzt die Rechnung, die ich dir am Anfang versprochen habe.

Es waren 3 Stunden Arbeit der Agents und 14 Dollar zu Listenpreisen, für den ganzen Abend.



Noch einmal die vier Jobs in einem Satz. Einer schreibt mit, einer schneidet, einer prüft, und du entscheidest.

Was mache ich also noch selbst? Ich nehme auf, ich höre den Ton, und ich sage Ja oder Nein.

Und mein Urteil ist einfach. Den Schnitt machen jetzt die Agents, den Geschmack nicht.

Und die Checkliste mit allen vier Jobs ist kostenlos, der Link steht in der Beschreibung.

Danke fürs Zuschauen.
""" + PLAN_DE


def rules(r, level=None):
    return [f["rule"] for f in r["findings"] if level is None or f["level"] == level]


def test_good_english_script_passes_all_four_groups():
    r = craft.check(GOOD_EN, "en", 150)
    assert r["findings"] == [], r["findings"]
    s = r["stats"]
    assert s["language"] == "en" and s["takeaways"] == 4 and s["depth_parts"] == 4
    assert s["ending_calls_to_action"] == ["link"]
    assert s["you_depth"] >= s["i_depth"] and s["objections"] == 1 and s["live_math"] >= 1
    passed = " ".join(r["passed"])
    for want in ("a number", "roadmap", "open loop", "honest limit", "exactly one call to action",
                 "open loop is resolved"):
        assert want in passed, want


def test_good_german_script_passes_all_four_groups():
    r = craft.check(GOOD_DE, None, 150)          # the language comes from the text
    assert r["stats"]["language"] == "de"
    assert r["findings"] == [], r["findings"]
    assert r["stats"]["takeaways"] == 4 and r["stats"]["ending_calls_to_action"] == ["link"]
    assert any('roadmap with a count ("vier Jobs")' in p for p in r["passed"])


def test_bad_script_names_each_missing_part():
    r = craft.check(BAD_EN, "en", 150)
    assert rules(r, "error") == ["greeting"]
    warns = set(rules(r, "warn"))
    assert {"hook_number", "roadmap", "open_loop", "limit", "questions", "cta"} <= warns
    cta = next(f for f in r["findings"] if f["rule"] == "cta")
    assert "3 calls to action" in cta["text"]
    assert "you_i" not in rules(r)          # no depth part: the you-against-I rule has nothing to measure


def test_greeting_is_checked_even_in_a_short_text():
    r = craft.check("Hallo zusammen! Heute geht es um Schnitt.\n", "de", 150)
    assert rules(r) == ["greeting"]


def test_open_loop_must_be_resolved():
    text = GOOD_EN.replace("And now the cost I promised at the start.", "And now a word on the hardware.") \
                  .replace(" for the whole evening.", ".")
    r = craft.check(text, "en", 150)
    assert "loop_resolved" in rules(r, "warn")


def test_try_this_missing_in_one_part_is_a_hint_naming_it():
    text = GOOD_EN.replace("Try this. Let a second chat review your work, one that did not write it.",
                           "That rule holds for people as well.")
    r = craft.check(text, "en", 150)
    f = next(f for f in r["findings"] if f["rule"] == "takeaways")
    assert f["level"] == "hint" and "part 4" in f["text"]


def test_a_long_ending_and_two_calls_to_action():
    long_end = " ".join(["The agents did the cutting while I watched the numbers on the screen."] * 12)
    text = GOOD_EN.replace("Thanks for watching.", long_end + "\n\nSubscribe for more. Thanks for watching.")
    r = craft.check(text, "en", 150)
    assert {"ending_length", "cta"} <= set(rules(r, "warn"))
    assert "subscribe_once" in rules(r, "warn")


def test_levels_and_limits_come_from_the_pack():
    r = craft.check(BAD_EN, "en", 150, {"checks": {"greeting": "off", "roadmap": "error", "questions": "hint"}})
    assert "greeting" not in rules(r)
    assert "roadmap" in rules(r, "error") and "questions" in rules(r, "hint")
    faster = craft.check(GOOD_EN, "en", 150, {"hook_seconds": 10})
    assert "open_loop" in rules(faster)            # 10 s are too short for the whole hook


def test_questions_without_an_answer():
    text = GOOD_EN.replace("So job one is the transcript. Why start with text?", "So job one is the transcript.") \
                  .replace("Try this. Ask for a transcript", "Why does that help? \n\n\n\nTry this. Ask for a transcript")
    r = craft.check(text, "en", 150)
    assert "answers" in rules(r)


def test_script_check_runs_the_craft_and_the_new_sentence_limit():
    neutral = brand.load(ROOT / "packs" / "neutral")
    sc = _script_check()
    r = sc.check_script(GOOD_EN, neutral)
    assert r["errors"] == 0 and r["stats"]["craft"]["takeaways"] == 4, r["findings"]
    assert sc.check_script(GOOD_DE, neutral)["errors"] == 0
    assert not [f for f in r["findings"] if f["area"] in ("hook", "depth", "rhythm", "ending")], r["findings"]
    assert r["manual"] and r["stats"]["minutes"] > 3
    long = GOOD_EN.replace("Thanks for watching.", "Thanks for watching, and thanks to everyone who wrote to me with "
                           "questions about the setup, the prices and the agents last week.")
    assert any(f["area"] == "sentences" and f["level"] == "error" for f in sc.check_script(long, neutral)["findings"])
    b = sc.check_script(BAD_EN, neutral)
    assert any(f["area"] == "hook" and f["level"] == "error" for f in b["findings"])


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
