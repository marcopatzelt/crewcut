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
    assert "points" not in r and r["passed"] and flat["passed"]   # a gate: both pass, nothing to raise
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


def ten(formulas: list[str]) -> list[tuple[str, str]]:
    return [(f, f"Ollama title number {i + 1}") for i, f in enumerate(formulas)]


def test_set_gate_passes_with_ten_from_four_formulas(neutral):
    rows = ten(["situation", "howto", "contrast", "flip"] * 2 + ["plan", "year"])
    rep = tc.check_set(rows, neutral, ["Ollama"])
    assert rep["passed"], rep["problems"]
    assert rep["candidates"] == 10 and len(rep["formulas"]) == 6


def test_set_gate_fails_on_too_few_formulas_or_candidates(neutral):
    rep = tc.check_set(ten(["howto"] * 7 + ["situation"] * 3), neutral, ["Ollama"])
    assert not rep["passed"] and any("formulas" in p for p in rep["problems"])
    rep = tc.check_set(ten(["situation", "howto", "contrast", "flip", "plan"]), neutral, ["Ollama"])
    assert not rep["passed"] and any("candidates" in p for p in rep["problems"])


def test_set_gate_keeps_every_hygiene_check(striq):
    rows = [(f, f"Claude spart Geld Nummer {i}") for i, f in
            enumerate(["situation", "howto", "contrast", "flip", "plan", "condition-plan", "condensed", "year",
                       "time", "case"])]
    assert tc.check_set(rows, striq)["passed"]
    rows[3] = ("flip", "Claude: 10x schneller")          # colon and factor are errors in this pack
    rep = tc.check_set(rows, striq)
    assert not rep["passed"] and not rep["results"][3]["passed"]


def test_set_gate_needs_a_known_formula_and_no_twins(neutral):
    rows = ten(["situation", "howto", "contrast", "flip"] * 2 + ["plan", "year"])
    rows[0] = ("clickbait", rows[0][1])
    rows[9] = ("year", rows[8][1])
    rep = tc.check_set(rows, neutral, ["Ollama"])
    assert not rep["passed"]
    assert rep["results"][0]["findings"][0]["rule"] == "formula"
    assert any("twice" in p for p in rep["problems"])


def test_parse_set_and_aliases():
    rows = tc.parse_set("# formula, title\nsituation\tWenn du Claude nutzt\nhow-to | So geht das\nNo label here\n")
    assert rows == [("situation", "Wenn du Claude nutzt"), ("how-to", "So geht das"), ("", "No label here")]
    assert tc.formula_id("How-To") == "howto" and tc.formula_id("condition plan") == "condition-plan"
    assert tc.formula_id("nonsense") is None


def test_main_set_exit_codes(tmp_path, capsys):
    f = tmp_path / "set.tsv"
    f.write_text("".join(f"{x}\tOllama runs model {i}\n" for i, x in
                         enumerate(["situation", "howto", "contrast", "flip"] * 2 + ["plan", "year"])))
    assert tc.main(["--set", str(f), "--name", "Ollama", "--pack", "packs/neutral"]) == 0
    assert "GATE PASSED" in capsys.readouterr().out
    f.write_text("howto\tOllama runs one model\n")
    assert tc.main(["--set", str(f), "--name", "Ollama", "--pack", "packs/neutral"]) == 1
    assert "GATE FAILED" in capsys.readouterr().out
