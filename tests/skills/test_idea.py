import datetime as dt
import json

import pytest
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


# ---------- the market method of 27 Nov 2026 (baseline window, hit rates, evidence, grade, audience) ----------
def chan(cid, views, start_days, step=7, lang="de", subs=50000, fmt=None, title="video"):
    """Uploads of one channel, newest first: views[i] is the upload start_days + i * step days ago."""
    return [{"id": f"{cid}-{i}", "channel_id": cid, "channel": cid.upper(), "subs": subs, "lang": lang,
             "title": f"{title} {i}", "views": v, "duration_s": 600, "published": ago(start_days + i * step),
             **({"format": fmt[i]} if fmt else {})} for i, v in enumerate(views)]


def test_baseline_takes_the_window_around_the_video():
    ups = chan("a", [1000] * 40, 1)
    longs = idea._dated_longs(ups, CFG)
    b = idea.window_baseline(longs, 20, NOW, CFG)        # 141 days ago: 15 before and 15 after, all mature
    assert (b["before"], b["after"], b["n"], b["median"]) == (15, 15, 30, 1000)
    young = idea.window_baseline(longs, 0, NOW, CFG)     # a fresh upload: nothing after it is 28 days old
    assert young["after"] == 0 and young["before"] == 15
    near = idea.window_baseline(longs, 3, NOW, CFG)      # 22 days ago: the uploads of the last 28 days do not count
    assert near["after"] == 0
    few = idea.window_baseline(idea._dated_longs(chan("b", [1000] * 9, 40), CFG), 0, NOW, CFG)
    assert few["n"] == 8 and few["median"] is None       # under 10 uploads: no value
    wide = idea._dated_longs(chan("c", [1000] * 12, 40, step=40), CFG)   # 40 days apart: 6 months reach 4 each side
    assert idea.window_baseline(wide, 6, NOW, CFG)["n"] == 8


def test_a_growing_channel_is_measured_at_the_time_of_the_video():
    # views grow 10 % per upload toward today; the old rule (median of today's 30 newest) made old videos look weak
    views = [int(1000 * 1.1 ** (60 - i)) for i in range(61)]
    ups = chan("g", views, 30)
    row = next(r for r in idea.measure(ups, None, NOW, CFG) if r["id"] == "g-30")
    old = views[30] / idea.channel_median(ups, 181)
    assert old < 0.3 and 0.9 < row["x_median"] < 1.1


def test_x_last5_is_the_median_and_per_sub_stops_at_90_days():
    views = [5000, 100, 100, 100, 100, 100000] + [1000] * 20
    rows = idea.measure(chan("m", views, 1, step=1, subs=1000), 1000, NOW, CFG)
    assert rows[0]["x_last5"] == 50.0              # the mean of the five would give 0.05
    old = idea.measure(chan("o", [1000] * 30, 100), 1000, NOW, CFG)
    assert old[0]["per_sub"] is None and old[0]["final"]


def test_tiers_floors_and_young_videos():
    assert [idea.tier(x, CFG) for x in (1.9, 2.0, 3.0, 10.0)] == [None, "candidate", "strong", "very strong"]
    base = chan("f", [3000] * 30, 40)
    en = [dict(v, lang="en") for v in base]
    en_hit = [dict(en[0], id="en-hit", views=9000, published=ago(35))] + en
    de_hit = [dict(base[0], id="de-hit", views=9000, published=ago(35))] + base
    r_en = next(r for r in idea.measure(en_hit, None, NOW, CFG) if r["id"] == "en-hit")
    r_de = next(r for r in idea.measure(de_hit, None, NOW, CFG) if r["id"] == "de-hit")
    assert r_en["x_median"] == r_de["x_median"] == 3.0
    assert not r_en["outlier"] and r_de["outlier"]   # English needs 10,000 views, other languages 3,000
    young = idea.measure(chan("y", [9000] + [3000] * 30, 10), None, NOW, CFG)[0]
    assert young["final"] is False and young["x_median"] == 3.0


def test_coview_change_is_noted():
    rows = idea.measure(chan("cv", [1000] * 30, 1, step=3), None, NOW, CFG)
    assert rows[0]["coview_era"] and not rows[-1]["coview_era"]
    assert any(r["coview_mixed"] for r in rows)
    assert "co-views" in idea.coview_note(rows)


def test_statistics():
    assert round(idea.binom_sf(4, 8, 0.13), 3) == 0.013          # the research's example: 4 of 8 at 13 %
    assert idea.binom_sf(0, 5, 0.5) == 1.0 and idea.binom_sf(6, 5, 0.5) == 0.0
    ps = [0.2] * 12
    assert abs(idea.poisson_binomial_sf(ps, 5) - idea.binom_sf(5, 12, 0.2)) < 1e-12
    assert idea.poisson_binomial_sf([0.1, 0.9], 2) == 0.09000000000000001 or \
        abs(idea.poisson_binomial_sf([0.1, 0.9], 2) - 0.09) < 1e-12
    assert idea.bh([0.01, 0.04, 0.03, None]) == [0.03, 0.04, 0.04, None]


def market(hit_channels=6):
    """Six channels of 30 mature uploads at 5,000 views. Format "duel": 4 videos at 15,000 views on hit_channels
    channels. "flat": 4 normal videos on every channel. "solo": 5 hits on channel 0, 3 normal videos elsewhere."""
    rows = []
    for c in range(6):
        fmt = ["none"] * 30
        views = [5000] * 30
        for i in range(4):
            fmt[1 + i] = "flat"
            if c < hit_channels:
                fmt[10 + i], views[10 + i] = "duel", 15000
        if c == 0:
            for i in range(5):
                fmt[20 + i], views[20 + i] = "solo", 20000
        elif c in (1, 2):
            fmt[20] = "solo"
        rows += chan(f"c{c}", views, 30, fmt=fmt, subs=20000 if c < 3 else 500000)
    return rows


def table(rows):
    return {f["format"]: f for f in idea.format_table(idea.label_rows(idea.measure_rows(rows, NOW, CFG)), NOW,
                                                      CFG)["formats"]}


def test_hit_rates_against_each_channels_normal_rate():
    t = table(market())
    d = t["duel"]
    assert (d["n"], d["channels"], d["hits"], d["channel_wins"]) == (24, 6, 24, 6)
    assert d["level"] == "strong" and d["grade_max"] == 5 and d["edge"] == "above"
    assert d["without_top"]["level"] in ("strong", "medium") and d["share_small"] == 0.5
    assert t["flat"]["hits"] == 0 and t["flat"]["level"] == "none" and t["flat"]["grade_max"] == 3
    assert t["solo"]["level"] == "one-channel" and t["solo"]["top_hits"] == 5
    four = table(market(hit_channels=4))["duel"]
    assert four["level"] == "medium" and four["q_channel"] >= 0.10   # 4 of 4 channels: sign test too weak for strong


def test_flops_count_and_flagged_videos_leave_the_test():
    rows = market()
    labels = {r["id"]: {"id": r["id"], "format": r["format"]} for r in rows}
    for r in rows:   # every duel video on channel c0 and c1 was a collaboration with a big guest
        if r["format"] == "duel" and r["channel_id"] in ("c0", "c1"):
            labels[r["id"]]["flags"] = ["collab"]
    measured = idea.label_rows(idea.measure_rows(rows, NOW, CFG), labels)
    res = idea.format_table(measured, NOW, CFG)
    d = next(f for f in res["formats"] if f["format"] == "duel")
    assert d["n"] == 16 and res["flagged"] == 8
    unlabelled = idea.label_rows(idea.measure_rows([dict(r, format=None) for r in rows], NOW, CFG))
    assert idea.format_table(unlabelled, NOW, CFG)["unlabelled"] == 180


def test_labels_and_patterns():
    rows = [{"id": "a", "title": "Claude vs GPT: same app"}, {"id": "b", "title": "10 tips"}, {"id": "c", "title": "x"}]
    out = idea.label_rows(rows, {"c": {"id": "c", "format": "list", "flags": ["news", "bogus"]}},
                          {"duel": r"\bvs\b"})
    assert [r["format"] for r in out] == ["duel", "none", "list"] and out[2]["flags"] == ["news"]
    assert idea.label_rows([{"id": "z", "title": "?"}])[0]["format"] is None


def test_labels_file_forms(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text('{"id": "a", "format": "duel"}\n{"id": "b", "format": "none"}\n')
    assert idea.load_labels(p)["b"]["format"] == "none"
    q = tmp_path / "l.json"
    q.write_text('{"a": "duel"}')
    assert idea.load_labels(q)["a"]["format"] == "duel"


def test_series_and_decay():
    fr = [{"channel_id": "s", "channel": "S", "published": ago(200 - i), "x_median": x}
          for i, x in enumerate([5.0, 1.5, 1.3, 1.2, 1.4])]
    s = idea.series(fr)
    assert s["series"] == 1 and s["repeatable"] == 1 and s["best"][0]["later_median_x"] == 1.3
    prev = [{"published": ago(100 + i), "x_median": 2.0} for i in range(4)]
    last = [{"published": ago(40 + i), "x_median": 1.0} for i in range(8)]
    assert idea.decay(prev + last, NOW, CFG)["closing"]
    assert not idea.decay(prev + last[:4], NOW, CFG)["closing"]


def test_card_sample_takes_hits_and_as_many_others():
    measured = idea.label_rows(idea.measure_rows(market(), NOW, CFG))
    cards = idea.card_sample(measured, CFG, "duel")
    assert len([c for c in cards if c["hit"]]) == 24 and len(cards) == 24   # duel videos are all hits
    all_cards = idea.card_sample(measured, CFG)
    hits = [c for c in all_cards if c["hit"]]
    assert len(all_cards) == 2 * len(hits) and set(all_cards[0]["card"]) == set(idea.CARD_FIELDS)
    assert all_cards == idea.card_sample(measured, CFG)                       # seeded: the same sample again


def test_gap_is_relative_to_the_users_market_and_imports_count_originals():
    home = [{"id": "h", "views": 25000}]
    assert idea.gap(home, 30000, market_median=10000)["gap"] == "taken"   # 25,000 is over 2x the market's median
    assert idea.gap(home, 30000, market_median=20000)["gap"] == "thin"
    assert idea.gap([{"id": "h", "views": 31000}], 30000, market_median=100000)["gap"] == "taken"
    found = [{"id": "1", "title": "Claude kostenlos: ich teste 3 Wege ohne Abo", "views": 900},
             {"id": "2", "title": "Use Claude Code for free", "lang": "en", "views": 200000},
             {"id": "3", "title": "Stop paying for every tool you use", "views": 5000}]
    h, imp = idea.split_home(found, "de")
    assert [v["id"] for v in h] == ["1"] and [v["id"] for v in imp] == ["2", "3"]
    assert any("One grade off" in x for x in idea.hints({"verdict": "open"}, {"gap": "thin"}, imp, CFG))


def test_grade_needs_evidence_for_four_and_five():
    sat = {"verdict": "open", "best": {"views": 100}, "copies_median": 50}
    g = idea.grade(sat, {"gap": "empty"}, 3.5, "medium", 0, CFG)
    assert g["grade"] == 5 and g["grade_max"] == 5
    capped = idea.grade(sat, {"gap": "empty"}, 3.5, "hint", 0, CFG)
    assert capped["grade"] == 3 and "at most 3" in capped["why"][-1]
    assert idea.grade(sat, {"gap": "thin"}, 2.2, "strong", 0, CFG)["grade"] == 3
    assert idea.grade(sat, {"gap": "thin"}, 3.2, "strong", 150000, CFG)["grade"] == 3          # import penalty
    assert idea.grade(sat, {"gap": "thin"}, 3.2, "strong", 150000, CFG, local=True)["grade"] == 4
    assert idea.grade({"verdict": "closed"}, None, 9.0, "strong", 0, CFG)["grade"] == 1
    assert idea.grade({"verdict": "stable"}, None, 3.0, None, 0, CFG)["grade"] == 3
    assert idea.max_grade("strong") == 5 and idea.max_grade("one-channel") == 3


AUD = dict(CFG, audience={
    "groups": {"Builder": ["build\\w*", "apps?", "website\\w*", "no.?code"],
               "Creator": ["youtube", "shorts", "thumbnails?", "videos?"],
               "Power user": ["tips", "tricks?", "workflows?", "free"]},
    "core": ["claude"], "open": ["anyone", "free", "without (?:coding|code)"],
    "zero": ["enterprise\\w*", "b2b", "compliance", "your clients", "accounting"],
    "narrow": ["rust", "kernels?", "compilers?"], "insider": ["sdk", "cli", "mcp"]})


def test_audience_score():
    assert idea.audience_score("anything", CFG) is None
    b2b = idea.audience_score("Claude for enterprise compliance teams", AUD)
    assert b2b["score"] == 0 and b2b["group"] == "zero"
    best = idea.audience_score("Claude builds an app for free, anyone can do it, then a YouTube video", AUD)
    assert best["score"] == 5 and best["group"] in ("Builder", "Creator", "Power user")
    assert idea.audience_score("Claude CLI and the MCP SDK", AUD)["score"] == 1
    assert idea.audience_score("A Rust compiler with Claude builds apps", AUD)["score"] == 2
    with pytest.raises(idea.SourceError):
        idea.audience_score("x", dict(CFG, audience={"groups": {"a": ["(bad"]}}))


def check_json(topic, grade_, audience, fmt=None, proof=3.4, verdict="open", gap="thin", first_age=40):
    return {"topic": topic, "market": {"saturation": {"verdict": verdict, "send_by": "2030-01-01",
                                                      "first_age_days": first_age}},
            "home": {"gap": {"gap": gap}}, "evidence": {"level": "medium"},
            "proof": [{"id": "v1", "title": "T", "channel": "C", "views": 50000, "x_median": proof}],
            "grade": {"grade": grade_, "grade_max": 5, "why": ["proof strong"]}, "audience": audience,
            "format": fmt}


def test_rank_puts_grade_first_then_audience_and_leaves_framing_out():
    fmt = {"format": "tool-test", "name": "Tool test", "length": "long", "reason": "named at the check"}
    r = idea.rank([check_json("A", 4, {"score": 2, "group": "Builder"}, fmt),
                   check_json("B", 4, {"score": 5, "group": "Creator"}),
                   check_json("C", 5, {"score": 1, "group": None}),
                   check_json("D", 5, {"score": 0, "group": "zero", "why": "framing"})])
    assert [x["topic"] for x in r["ranked"]] == ["C", "B", "A"]
    assert r["not_ranked"][0]["topic"] == "D"


def test_idea_cards_name_the_library_format(studio):
    from crewcut import ideas
    fmt = {"format": "tool-test", "name": "Tool test", "length": "long", "reason": "named at the check"}
    r = idea.rank([check_json("Free tool against the paid one", 4, {"score": 4, "group": "Builder"}, fmt),
                   check_json("Something new", 3, None, None, first_age=5)])
    res = idea.write_cards(r["ranked"], "2030-01-02")
    assert res["written"] == 2
    card = json.loads((studio / "inbox" / "ideas" / "idea-free-tool-against-the-paid-one.json").read_text())
    assert card["suggested_format"] == "tool-test" and card["length"] == "long"
    assert "Format: Tool test (tool-test)." in card["summary"] and card["signals"]["audience"] == 4
    new = json.loads((studio / "inbox" / "ideas" / "idea-something-new.json").read_text())
    assert new["suggested_format"] is None and "candidate for a new format" in new["summary"]
    assert new["topic_type"] == "trending"
    ideas.load()
    assert ideas.get("idea-free-tool-against-the-paid-one")["suggested_format"] == "tool-test"
    assert ideas.get("idea-free-tool-against-the-paid-one")["suggestion"] == "exporter"
    p = studio / "inbox" / "ideas" / "idea-something-new.json"
    p.write_text(json.dumps(dict(json.loads(p.read_text()), status="dismissed")))
    assert idea.write_cards(r["ranked"], "2030-01-03")["decided"] == 1


def test_formats_command_offline(tmp_path, capsys):
    f = tmp_path / "videos.jsonl"
    f.write_text("".join(json.dumps(dict(r, fetched_at=NOW.isoformat())) + "\n" for r in market()))
    out = tmp_path / "formats.json"
    todo, cards = tmp_path / "todo.jsonl", tmp_path / "cards.jsonl"
    assert idea.main(["--pack", "packs/neutral", "--out", str(out), "formats", str(f), "--todo", str(todo),
                      "--cards", str(cards), "--format", "duel"]) == 0
    res = json.loads(out.read_text())
    assert {x["format"]: x["level"] for x in res["formats"]}["duel"] == "strong" and res["date"] == "2026-11-16"
    assert todo.read_text() == "" and len(cards.read_text().splitlines()) == 24
    assert "STRONG" in capsys.readouterr().out


def test_sources_and_the_unit_guard(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(idea.shutil, "which", lambda name: None)
    assert isinstance(idea.make_source("auto", CFG), idea.YouTubeAPI)
    monkeypatch.setattr(idea.shutil, "which", lambda name: "/usr/bin/yt-dlp")
    assert isinstance(idea.make_source("auto", dict(CFG, search_source="ytdlp")), idea.Hybrid)
    api = idea.YouTubeAPI(key="k", max_units=150)
    api.units = 100
    with pytest.raises(idea.SourceError, match="unit limit"):
        api._get("search", q="x")
    assert api.units == 100
    assert "sp=CAISAggE" in idea.ytdlp_search_url("claude", "date", NOW - dt.timedelta(days=28), NOW)
    assert "sp=EgIIBQ%3D%3D" in idea.ytdlp_search_url("claude", "relevance", NOW - dt.timedelta(days=112), NOW)


def test_rank_command_reads_saved_checks(tmp_path, capsys):
    (tmp_path / "idea-a.json").write_text(json.dumps(check_json("Topic A", 4, None)))
    assert idea.main(["--pack", "packs/neutral", "rank", str(tmp_path / "idea-*.json")]) == 0
    assert "1. Topic A: grade 4" in capsys.readouterr().out


class FakeSource:
    """Search and channel reads from fixed data (no network)."""
    units = 0
    name = "fake"

    def __init__(self):
        self.market = [{"id": f"m{i}", "title": f"Free tool replaces paid app {i}", "channel_id": f"ch{i % 3}",
                        "channel": f"CH{i % 3}", "views": 90000 - i * 1000, "duration_s": 700, "lang": "en",
                        "published": ago(40 + i)} for i in range(6)]
        self.home = [{"id": "d1", "title": "Kostenloses Tool ersetzt die bezahlte App", "channel_id": "dech",
                      "channel": "DE", "views": 12000, "duration_s": 700, "lang": "de", "published": ago(60)},
                     {"id": "m0", "title": "Free tool replaces paid app 0", "channel_id": "ch0", "views": 90000,
                      "duration_s": 700, "lang": "en", "published": ago(40)}]

    def search(self, q, *, order="relevance", after=None, lang=None, region=None, n=50):
        return self.home if lang == "de" else self.market

    def channel(self, ref):
        return {"id": ref, "title": ref.upper(), "subs": 40000, "uploads": ref}

    def uploads(self, ch, n=50, since=None):
        own = [v for v in self.market + self.home if v["channel_id"] == ch["id"]]
        base = chan(ch["id"], [10000 if ch["id"] != "dech" else 4000] * 30, 30, lang="en")
        return sorted(own + base, key=lambda v: v["published"], reverse=True)

    def subscribers(self, ids):
        return dict.fromkeys(ids, 40000)


def test_check_end_to_end_with_a_fake_source(tmp_path, neutral):
    import argparse
    cfg = dict(idea.settings(neutral), home_language="de", home_region="DE")
    a = argparse.Namespace(topic="free tool replaces paid app", pattern=r"free tool", home_pattern=r"kostenlos",
                           query=["free tool"], home_query=["kostenloses tool"], proof=3, format="tool-test",
                           evidence=None, market_channel=None, local=False)
    r = idea.cmd_check(a, cfg, FakeSource(), NOW)
    assert r["proof"][0]["x_median"] == 9.0 and r["proof"][0]["baseline"] == "window"
    assert r["home"]["gap"]["gap"] == "taken" and r["home"]["gap"]["market_median"] == 4000   # 12,000 > 2 x 4,000
    assert [v["id"] for v in r["home"]["imports"]] == ["m0"]
    assert r["evidence"]["level"] == "hint" and r["grade"]["grade_max"] == 3
    assert r["format"]["format"] == "tool-test"
    ev = tmp_path / "formats.json"
    ev.write_text(json.dumps({"formats": [{"format": "tool-test", "level": "medium"}]}))
    a.evidence, a.market_channel = str(ev), "dech"
    r2 = idea.cmd_check(a, dict(cfg, gap_thin_x_market=4.0), FakeSource(), NOW)
    assert r2["home"]["gap"]["gap"] == "thin" and r2["evidence"]["level"] == "medium"
    assert r2["grade"]["grade"] == 4 and r2["grade"]["grade_max"] == 5       # thin with strong proof
