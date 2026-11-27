"""Cue sheets: the parser the teleprompter and the style gate share (synthetic sheets only)."""

from crewcut import cuesheet

EN = """# Cue sheet, synthetic

## Opening
LINE1: The cheapest setting built my best clip. [Picture: ranking]
PROOF: I tested four settings on eight clips.
PLAN: Here is why, in two points.

## Unit 1 | Proof: Screen | Short: yes
HOOK: My best clip took 40 minutes, the worst one 90.
• Proof: [both clocks] 40 minutes against 90 · same prompt
• Example: [the log] three helpers · street, flat, edit
PUNCH: Helpers beat thinking time.
ASK: If you like tests like this, subscribe.
BRIDGE: So where did the time go?

## Unit 2 | Proof: Number | Short: no
HOOK: Rendering 600 frames took five hours on one card.
• Number: [counter] 600 times 30 seconds = five hours
PUNCH: One test frame saves hours.

## Close
VERDICT: I keep the cheap setting for big jobs.
LINK: If you want this system, the link is in the description.

---
Notes for the edit.
"""

DE = EN.replace("## Opening", "## Einstieg").replace("LINE1:", "SATZ1:").replace("PROOF: I", "BEWEIS: I") \
    .replace("## Unit 1 | Proof: Screen | Short: yes", "## Einheit 1 | Beleg: Bildschirm | Short: ja") \
    .replace("## Unit 2 | Proof: Number | Short: no", "## Einheit 2 | Beleg: Zahl | Short: nein") \
    .replace("ASK:", "BITTE:").replace("BRIDGE:", "BRÜCKE:").replace("## Close", "## Schluss") \
    .replace("VERDICT:", "URTEIL:")


def test_english_and_german_markers_read_the_same():
    for text in (EN, DE):
        s = cuesheet.parse(text)
        assert s.errors == []
        assert [p.label for p in s.parts] == ["opening", "unit 1", "unit 2", "close"]
        u1, u2 = s.units
        assert u1.short and not u2.short
        assert u1.meta["proof"] in ("Screen", "Bildschirm")
        assert u1.fixed("hook")[0].spoken.startswith("My best clip")
        assert u1.bullets[0].picture == "both clocks"
        assert u1.bullets[0].groups == ["40 minutes against 90", "same prompt"]
        assert s.part("opening").fixed("line1")[0].spoken == "The cheapest setting built my best clip."
        assert s.part("opening").fixed("line1")[0].picture == "Picture: ranking"
        assert s.notes.strip() == "Notes for the edit."


def test_names_and_content_detection():
    assert cuesheet.is_name("brief/CUES-v003.md") and cuesheet.is_name("DREHZETTEL-v001.md")
    assert not cuesheet.is_name("brief/SCRIPT-v009.md")
    assert cuesheet.looks_like(EN)
    assert not cuesheet.looks_like("Point one. A full text script.\n\n---\nnotes")


def test_a_leading_question_is_kept_apart_from_the_cue_words():
    s = cuesheet.parse(EN.replace("• Example: [the log] three helpers", "• Example: [the log] Why so fast? · three helpers"))
    b = s.units[0].bullets[1]
    assert b.question == "Why so fast?"
    assert b.groups == ["three helpers", "street, flat, edit"]


def test_structure_errors_name_the_unit_and_the_fix():
    broken = EN.replace("PUNCH: Helpers beat thinking time.\n", "").replace("BRIDGE: So where did the time go?\n", "")
    errors = " ".join(cuesheet.parse(broken).errors)
    assert "unit 1: exactly one PUNCH line" in errors
    assert "unit 1: one BRIDGE line" in errors
    assert "a line without a marker" in " ".join(cuesheet.parse(EN.replace("• Number:", "Number:")).errors)
    two_asks = EN.replace("PUNCH: One test frame saves hours.", "PUNCH: One test frame saves hours.\nASK: Subscribe.")
    assert "2 ask lines" in " ".join(cuesheet.parse(two_asks).errors)
    assert "LINK line is the last" in " ".join(cuesheet.parse(EN.replace(
        "LINK: If you want this system, the link is in the description.",
        "LINK: If you want this system, the link is in the description.\nVERDICT: Again.")).errors)
