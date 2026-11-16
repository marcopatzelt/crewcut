from conftest import load_script

tc = load_script("skills/title/scripts/title_check.py")

HOOKS = """# Voice

## Title hooks
- free: free, no cost
- new: new, finally

## Title words to avoid
- business: business, compan*

## Words to avoid
- game changer
"""


def levels(r, rule=None):
    return [f["level"] for f in r["findings"] if rule is None or f["rule"] == rule]


def test_length_limits_from_neutral_pack(neutral):
    assert "error" in levels(tc.check_title("A" * 30 + " " + "b" * 45, neutral), "length")
    r = tc.check_title("x" * 60, neutral)
    assert levels(r, "length") == ["warn"]
    assert "error" in levels(tc.check_title("y" * 101, neutral), "length")


def test_angle_brackets_fail(neutral):
    assert tc.check_title("Claude <test>", neutral, ["Claude"])["status"] == "fail"


def test_name_must_start_early(neutral):
    ok = tc.check_title("Ollama runs five models on a laptop", neutral, ["Ollama"])
    assert "plus" in levels(ok, "name")
    late = tc.check_title("I ran five local models on an old laptop with Ollama", neutral, ["Ollama"])
    assert "error" in levels(late, "name")
    missing = tc.check_title("Five local models on a laptop", neutral, ["Ollama"])
    assert "error" in levels(missing, "name")
    none = tc.check_title("Five local models on a laptop", neutral)
    assert levels(none, "name") == ["hint"]


def test_neutral_pack_allows_colon_and_factor(neutral):
    r = tc.check_title("Ollama: 10x faster", neutral, ["Ollama"])
    assert r["status"] == "ok"


def test_striq_taste_is_data(striq):
    r = tc.check_title("Claude: 10x schneller", striq)
    assert "error" in levels(r, "colon") and "error" in levels(r, "factor")
    caps = tc.check_title("Claude ist KRASS", striq)
    assert "error" in levels(caps, "caps")
    acronym = tc.check_title("Claude baut eine KI", striq)
    assert not levels(acronym, "caps")
    assert "error" in levels(tc.check_title("Claude " + "w" * 50, striq), "length")


def test_hooks_and_avoid_words_from_voice(neutral):
    neutral.voice = HOOKS
    r = tc.check_title("Ollama is free now", neutral, ["Ollama"])
    assert "plus" in levels(r, "hook")
    bad = tc.check_title("Ollama for your company", neutral, ["Ollama"])
    assert "error" in levels(bad, "avoid")
    flat = tc.check_title("Ollama on a laptop", neutral, ["Ollama"])
    assert levels(flat, "hook") == ["hint"]
    assert r["points"] > flat["points"]
    assert "warn" in levels(tc.check_title("Ollama is a game changer", neutral, ["Ollama"]), "voice")


def test_amount_is_a_hook_without_word_list(neutral):
    r = tc.check_title("Ollama saves 90 %", neutral, ["Ollama"])
    assert "plus" in levels(r, "hook")


def test_thumbnail_text(neutral):
    r = tc.check_title("Ollama runs five models", neutral, ["Ollama"], thumbnail="FIVE MODELS")
    assert "plus" in levels(r, "thumbnail")
    r = tc.check_title("Ollama runs five models", neutral, ["Ollama"], thumbnail="Too slow")
    assert levels(r, "thumbnail") == ["hint"]
    r = tc.check_title("Ollama runs five models", neutral, ["Ollama"], thumbnail="one two three four five six")
    assert "warn" in levels(r, "thumbnail")


def test_voice_section_parser():
    items = tc.voice_section(HOOKS, "Title hooks")
    assert items == [("free", ["free", "no cost"]), ("new", ["new", "finally"])]
    assert tc.voice_section(HOOKS, "Words to avoid") == [(None, ["game changer"])]
    assert tc.find_terms("Companies love it", ["compan*"]) == ["Companies"]
    assert tc.find_terms("costs $5", ["$"]) == ["$"]


def test_main_exit_codes(capsys):
    assert tc.main(["Five models", "--pack", "packs/neutral"]) == 0
    assert tc.main(["y" * 120, "--pack", "packs/neutral"]) == 1
    assert tc.main(["--pack", "packs/neutral"]) == 2
