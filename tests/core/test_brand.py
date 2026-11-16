from crewcut import brand, paths


def test_neutral_pack_loads_and_is_valid():
    p = brand.load()
    assert p.is_neutral
    assert p.value("brand.colors.accent").startswith("#")
    assert p.value("edit_style.loudness_lufs") == -14.0
    assert p.value("brand.does.not.exist", 7) == 7
    assert brand.check(p) == []


def test_user_pack_merges_over_neutral(studio):
    d = studio / "brand"
    d.mkdir()
    (d / "brand.json").write_text('{"colors": {"accent": "#123456"}}')
    p = brand.load()
    assert not p.is_neutral
    assert p.value("brand.colors.accent") == "#123456"
    assert p.value("brand.colors.ink") == "#111111"  # kept from neutral
    assert paths.brand_dir() == d


def test_rules_roundtrip():
    line = brand.format_rule("2026-11-11", "Music stays 3 dB under the voice.", 'user, "music a bit too loud"')
    rules = brand.parse_rules("# Rules\n\n" + line + "\n- not a rule\n")
    assert rules == [{"date": "2026-11-11", "rule": "Music stays 3 dB under the voice.",
                      "source": 'user, "music a bit too loud"'}]


def test_css_vars_and_tokens():
    p = brand.load()
    v = p.css_vars()
    assert v["--c-accent"] == p.value("brand.colors.accent")
    assert "Inter" in v["--font-display"]
    t = p.render_tokens()
    assert t["colors"]["accent"] == v["--c-accent"]
    assert "sources" not in t["edit"]


def test_check_reports_bad_values(studio):
    d = studio / "brand"
    d.mkdir()
    (d / "brand.json").write_text('{"colors": {"accent": "blue"}, "logo": {"file": "logo.svg"}}')
    problems = brand.check(brand.load())
    assert any("accent" in x for x in problems)
    assert any("logo" in x for x in problems)
