import datetime as dt

from conftest import load_script

idea = load_script("skills/idea/scripts/idea.py")
NOW = dt.datetime(2026, 11, 16, tzinfo=dt.UTC)
CFG = dict(idea.DEFAULTS)


def ago(days):
    return (NOW - dt.timedelta(days=days)).isoformat()


def test_parse_duration_and_refs():
    assert idea.parse_duration("PT1H2M3S") == 3723
    assert idea.parse_duration("PT45S") == 45
    assert idea.parse_duration("P1D") == 86400
    assert idea.parse_duration("bad") is None
    assert idea.parse_channel_ref("https://www.youtube.com/@some.channel/videos") == ("handle", "@some.channel")
    assert idea.parse_channel_ref("UC" + "a" * 22) == ("id", "UC" + "a" * 22)
    assert idea.parse_channel_ref("name") == ("handle", "@name")


def test_outliers():
    old = [{"id": f"o{i}", "views": 1000, "published": ago(30 + i), "duration_s": 600} for i in range(10)]
    fresh = {"id": "new", "views": 5000, "published": ago(2), "duration_s": 600}
    short = {"id": "short", "views": 90000, "published": ago(1), "duration_s": 40}
    rows = idea.outliers([short, fresh] + old, 2000, NOW, CFG)
    assert [r["id"] for r in rows] == ["new"]
    r = rows[0]
    assert r["x_median"] == 5.0 and r["x_last5"] == 5.0 and r["per_sub"] == 2.5 and r["outlier"]


def test_early_signal_counts_within_three_days():
    v = {"x_median": 1.2, "per_sub": 0.1, "age_days": 2, "x_last5": 1.3}
    assert idea.is_outlier(v, CFG)
    assert not idea.is_outlier(dict(v, age_days=5), CFG)


def test_breakthrough():
    assert idea.breakthrough(30000, 5000, CFG)
    assert not idea.breakthrough(30000, 500, CFG)
    assert not idea.breakthrough(3000, 5000, CFG)


def test_saturation_verdicts():
    assert idea.saturation([], NOW)["verdict"] == "no proof"
    assert idea.saturation([{"views": 900, "published": ago(5)}], NOW)["verdict"] == "no proof"
    first = {"id": "a", "views": 500000, "published": ago(10)}
    closing = [first] + [{"id": f"c{i}", "views": 3000, "published": ago(9 - i)} for i in range(4)]
    assert idea.saturation(closing, NOW)["verdict"] == "closing"
    assert idea.saturation([dict(first, published=ago(40))], NOW)["verdict"] == "open"
    closed = [dict(first, published=ago(60))] + [{"id": f"k{i}", "views": 200, "published": ago(50 - i)}
                                                  for i in range(20)]
    s = idea.saturation(closed, NOW)
    assert s["verdict"] == "closed" and s["copies"] == 20
    stable = [dict(first, published=ago(60))] + [{"id": f"s{i}", "views": 80000, "published": ago(25 - i)}
                                                  for i in range(12)]
    assert idea.saturation(stable, NOW)["verdict"] == "stable"
    assert s["send_by"] == (NOW - dt.timedelta(days=60) + dt.timedelta(days=14)).date().isoformat()


def test_gap_and_hints():
    assert idea.gap([], 30000)["gap"] == "empty"
    assert idea.gap([{"id": "x", "views": 1000}], 30000)["gap"] == "thin"
    assert idea.gap([{"id": "x", "views": 90000}], 30000)["gap"] == "taken"
    sat = {"verdict": "closed", "best": {"views": 200000}, "copies_median": 500}
    h = idea.hints(sat, {"gap": "empty"}, [{"views": 5}])
    assert len(h) == 4


def test_word_matcher():
    m = idea.word_matcher("make it better 100 times")
    assert m("I told Claude to make it better 100 times")
    assert not m("Claude Code tutorial")
    r = idea.regex_matcher(r"\b100\b.*times")
    assert r("Made better 100 more times")


def test_settings_read_the_pack(striq):
    cfg = idea.settings(striq)
    assert cfg["home_language"] == "de" and cfg["market_language"] == "en"
    assert cfg["gap_thin_views"] == 30000


def test_missing_key(monkeypatch, capsys):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert idea.main(["--pack", "packs/neutral", "scan"]) == 4
    monkeypatch.delenv("CREWCUT_IDEA_YTDLP", raising=False)
    assert idea.main(["--source", "ytdlp", "--pack", "packs/neutral", "scan"]) == 1
