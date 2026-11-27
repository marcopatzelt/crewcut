"""The style gate with cue sheets: the Critic's review loop until it approves, the stop on an unchanged point, the
second opinion through the host helper, and the review of what was said after the recording.

A fake checker stands in for a studio checker that knows cue sheets: it passes the form, its Critic check K-HZ reads
`review` in `<sheet>.kritik.json` (open without it, failing with the marked lines as points), and K-SO asks for a
second opinion in `<sheet>.second.json` once K-HZ passes.
"""

import hashlib
import hmac
import json

import pytest

from crewcut import approvals, db, engines, episodes, paths, second_opinion, stylegate
from crewcut.conductor import flow, queue, review

FAKE = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
f = Path(args[0])
if not f.is_file():
    sys.exit(2)
checks = []
cue = f.name.upper().startswith(("CUES", "DREHZETTEL"))
checks.append({"id": "FORM", "kind": "auto", "titel": "form", "measured": "ok" if cue else "full text",
               "target": "cue sheet", "pass": cue, "fix": None if cue else "Write a cue sheet."})
checks.append({"id": "H-H", "kind": "hinweis", "titel": "number in the hook", "measured": "560", "target": "a number",
               "pass": None})
if "--drehzettel" in args:
    kp = f.with_suffix(".kritik.json")
else:
    kp = f.with_suffix(".kritik.json")
rv = (json.loads(kp.read_text()) if kp.is_file() else {}).get("review")
if rv is None:
    hz, pts = None, []
else:
    pts = [{"text": t, "neu": "a better line", "grund": "gives the viewer nothing"} for t in rv.get("marked", [])]
    hz = rv.get("verdict") == "pass" and not pts
checks.append({"id": "K-HZ", "kind": "kritik", "titel": "every line gives value", "pass": hz,
               "measured": "open" if hz is None else ("pass" if hz else f"{len(pts)} points"), "target": "pass",
               "points": pts, "instructions": "/studio/brand/REVIEW.md", "frage": "Review every line."})
so = f.with_suffix(".second.json")
if hz:
    a = json.loads(so.read_text()) if so.is_file() else None
    if a is None or a.get("status") == "requested":
        sp, sm, spts = None, "open", []
    elif a.get("status") == "unavailable":
        sp, sm, spts = True, "unavailable: " + a.get("reason", ""), []
    else:
        spts = a.get("points") or []
        sp, sm = bool(a.get("agree")) and not spts, ("agrees" if a.get("agree") else "disagrees")
else:
    sp, sm, spts = None, "waits for the Critic", []
checks.append({"id": "K-SO", "kind": "kritik", "titel": "second opinion", "pass": sp, "measured": sm, "target": "agree",
               "points": spts, "second_opinion": True, "answer_file": str(so)})
auto = all(c["pass"] for c in checks if c["kind"] == "auto")
ok = auto and all(c["pass"] is True for c in checks if c["kind"] == "kritik")
print(json.dumps({"version": 1, "datei": str(f), "format": "lang", "pass": ok, "auto_pass": auto,
                  "kritik_offen": [c["id"] for c in checks if c["kind"] == "kritik" and c["pass"] is None],
                  "checks": checks, "pruefstuecke": [{"text": "x"}], "woerter": 10, "dauer_s": 60.0}))
sys.exit(0 if ok else 1)
'''

SHEET = """## Opening
LINE1: The highest setting built my two worst clips.
PLAN: Here is why, in two points.

## Unit 1 | Proof: Screen | Short: yes
HOOK: My best clip took 40 minutes, the worst one 90.
• Proof: [both clocks] 40 against 90
PUNCH: Helpers beat thinking time.
ASK: If you like tests like this, subscribe.
BRIDGE: So where did the time go?

## Unit 2 | Proof: Number | Short: no
HOOK: Rendering 600 frames took five hours on one card.
• Number: [counter] 600 times 30 seconds
PUNCH: One test frame saves hours.

## Close
VERDICT: I keep the cheap setting.
LINK: The link is in the description.

---
notes
"""


@pytest.fixture
def skill(studio):
    d = studio / "skills" / "deutscher-hormozi"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: deutscher-hormozi\ndescription: test\n---\n")
    (d / "scripts" / "stil_check.py").write_text(FAKE)
    return d


@pytest.fixture
def until_pass(monkeypatch):
    real = stylegate.settings

    def s():
        return {**real(), "loop": "until_pass", "safety_rounds": 6}
    monkeypatch.setattr(stylegate, "settings", s)


@pytest.fixture
def episode(studio, crew):
    ep = episodes.create("Clips im Test")["id"]
    for s in ("idea", "title"):
        episodes.set_step(ep, s, "done")
    episodes.set_step(ep, "script", "working")
    return ep


def sheet(ep: str, n: int, review: dict | None = None) -> str:
    p = paths.episode_dir(ep) / "brief" / f"CUES-v{n:03d}.md"
    p.write_text(SHEET, encoding="utf-8")
    if review is not None:
        p.with_suffix(".kritik.json").write_text(json.dumps({"review": review}))
    return f"brief/{p.name}"


def ends(ep: str, identity: str, data: dict | None = None) -> dict:
    jid = queue.add(ep, identity, "script", f"{identity} run")
    db.update("jobs", jid, status="done", started=db.now(), ended=db.now(), data=data or {})
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text="Done.\nVerdict: back"))
    return queue.get(jid)


def jobs(ep: str, identity: str, after: int = 0) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = ? AND id > ? ORDER BY id",
                                 (ep, identity, after)))


def finish_all(ep: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE jobs SET status = 'done' WHERE episode = ? AND status IN ('queued', 'running')", (ep,))


def test_a_cue_sheet_is_the_long_script_once_there_is_one(skill, episode):
    d = paths.episode_dir(episode) / "brief"
    (d / "SCRIPT-v009.md").write_text("Point one. A full text.\n\n---\nnotes")
    assert stylegate.latest(episode)["SCRIPT"].name == "SCRIPT-v009.md"
    sheet(episode, 1)
    assert stylegate.latest(episode)["SCRIPT"].name == "CUES-v001.md"
    v = stylegate.check(episode)
    r = v["results"][0]
    assert r["file"] == "brief/CUES-v001.md" and r["open"] == ["K-HZ", "K-SO"]
    assert r["instructions"] == ["/studio/brand/REVIEW.md"] and r["hints"] == 1


def test_the_critic_gets_the_instructions_and_not_the_second_opinion(skill, episode):
    sheet(episode, 1)
    w = ends(episode, "writer")
    [c] = jobs(episode, "critic")
    assert c["data"]["style_gate_kritik"] == 1 and "K-HZ" in c["task"] and "K-SO" not in c["task"]
    assert "/studio/brand/REVIEW.md" in c["task"] and "kind hinweis" in c["task"]
    assert not jobs(episode, "writer", w["id"])


def test_until_pass_goes_on_while_the_points_change(skill, episode, until_pass):
    sheet(episode, 1, {"verdict": "back", "marked": ["Line A"]})
    w = ends(episode, "writer")
    last = w["id"]
    for n, marked in enumerate(["Line B", "Line C", "Line D", "Line E"], 2):
        [r] = [j for j in jobs(episode, "writer", last) if (j.get("data") or {}).get("style_gate_round")]
        assert r["data"]["style_gate_round"] == n - 1 and "until the checker and the Critic pass" in r["task"]
        assert "a better line" in r["task"]
        finish_all(episode)
        sheet(episode, n, {"verdict": "back", "marked": [marked]})   # the Writer fixed the point, the Critic finds another
        ends(episode, "writer")
        last = r["id"]
    assert not [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]


def test_the_same_point_twice_stops_with_exactly_that_point(skill, episode, until_pass):
    sheet(episode, 1, {"verdict": "back", "marked": ["Das stand übrigens so in meinem Prompt."]})
    ends(episode, "writer")
    finish_all(episode)
    sheet(episode, 2, {"verdict": "back", "marked": ["Das stand übrigens so in meinem Prompt."]})
    w = ends(episode, "writer")
    assert not [j for j in jobs(episode, "writer", w["id"]) if (j.get("data") or {}).get("style_gate_round")]
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    assert card["title"].split(": ", 1)[1] == "Das stand übrigens so in meinem Prompt."
    assert card["title"].startswith(("Not approved: ", "Nicht freigegeben: "))
    assert card["data"]["style_gate_stuck"]["rewrite"] == "a better line"


def test_a_critic_run_the_gate_asked_for_is_routed_by_the_gate_not_by_the_review(skill, episode, until_pass):
    sheet(episode, 1, {"verdict": "back", "marked": ["Line A"]})
    c = ends(episode, "critic", {"style_gate_kritik": 1})
    assert review.after_review(c, "Verdict: back") is None
    [r] = [j for j in jobs(episode, "writer") if (j.get("data") or {}).get("style_gate_round")]
    assert "Line A" in r["task"] and "The Critic reviewed your script" in r["task"]


def test_without_a_host_helper_the_second_opinion_is_unavailable_and_the_card_says_so(skill, episode, until_pass):
    sheet(episode, 1, {"verdict": "pass", "marked": []})
    c = ends(episode, "critic", {"style_gate_kritik": 1})
    answer = json.loads((paths.episode_dir(episode) / "brief" / "CUES-v001.second.json").read_text())
    assert answer["status"] == "unavailable" and "host helper" in answer["reason"]
    [w] = jobs(episode, "writer", c["id"])
    assert "Propose your script card" in w["task"] and "Second opinion: unavailable" in w["task"]
    v = stylegate.check(episode)
    assert v["pass"]


@pytest.fixture
def helper(studio, monkeypatch):
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", "t0ken")
    box = studio / ".crewcut" / "host"
    box.mkdir(parents=True)
    import time
    (box / "helper.json").write_text(json.dumps({"version": 1, "at": time.time(), "second_opinion": True}))
    return box


def test_with_the_host_helper_the_request_is_signed_and_the_answer_moves_the_gate(skill, episode, until_pass, helper):
    sheet(episode, 1, {"verdict": "pass", "marked": []})
    ends(episode, "critic", {"style_gate_kritik": 1})
    [req] = list((helper / "requests").glob("*.req"))
    f = dict(line.split("=", 1) for line in req.read_text().splitlines())
    msg = ";".join(f"{k}={f[k]}" for k in second_opinion.FIELDS)
    assert f["sig"] == hmac.new(b"t0ken", msg.encode(), hashlib.sha256).hexdigest()
    assert f["file"].endswith("brief/CUES-v001.md") and f["answer"].endswith("brief/CUES-v001.second.json")
    assert f["verdict"].endswith("brief/CUES-v001.kritik.json") and not f["file"].startswith("/")
    assert not stylegate.check(episode)["pass"]                       # waiting: no card yet
    (helper / "runs").mkdir(exist_ok=True)
    (helper / "runs" / f"{f['id']}.json").write_text(json.dumps({"status": "success", "response": (
        'Here is my answer: {"agree": false, "points": [{"text": "Helpers beat thinking time.", "why": "not shown",'
        ' "rewrite": "Three helpers, 50 minutes saved."}]}')}))
    done = second_opinion.tick(force=True)
    assert done and done[0]["status"] == "ok" and done[0]["agree"] is False
    [r] = [j for j in jobs(episode, "writer") if (j.get("data") or {}).get("style_gate_round")]
    assert "Helpers beat thinking time." in r["task"] and "Three helpers, 50 minutes saved." in r["task"]


def test_parse_reads_an_envelope_a_plain_answer_and_a_failure():
    ok = second_opinion.parse(json.dumps({"status": "success", "response": '{"agree": true, "points": []}'}))
    assert ok == {"status": "ok", "agree": True, "points": [], "model": None, "checksum": None}
    plain = second_opinion.parse('{"zustimmung": false, "punkte": [{"text": "X", "grund": "Y", "neu": "Z"}]}')
    assert plain["agree"] is False and plain["points"] == [{"text": "X", "why": "Y", "rewrite": "Z"}]
    quota = second_opinion.parse(json.dumps({"status": "error", "error": "quota exhausted"}))
    assert quota["status"] == "unavailable" and "quota exhausted" in quota["reason"]
    assert second_opinion.parse("no json here")["status"] == "unavailable"


def test_a_cue_sheet_card_needs_readable_fixed_lines_not_a_story_plan(skill, episode):
    rel = sheet(episode, 1, {"verdict": "pass", "marked": []})
    (paths.episode_dir(episode) / "brief" / "CUES-v001.second.json").write_text(
        json.dumps({"status": "unavailable", "reason": "test"}))
    card = approvals.propose(episode, "script", "script", "Cue sheet", file=rel)
    assert card["status"] == "open" and card["data"]["style_gate"]["pass"] is True


def test_after_the_cut_the_critic_reviews_what_was_said_and_the_edit_gets_a_cut_list(skill, episode):
    rel = sheet(episode, 1)
    episodes.set_step(episode, "script", "done")
    ep = paths.episode_dir(episode)
    words = ep / "work" / "words-v003.json"
    words.parent.mkdir(exist_ok=True)
    words.write_text(json.dumps([{"w": "Hello.", "s": 0.0, "e": 0.5}]))
    res = stylegate.after_transcript(episode, words)
    [c] = jobs(episode, "critic")
    assert res["job"] == c["id"] and c["step"] == "edit" and c["data"]["plan"] == rel
    assert "--drehzettel brief/CUES-v001.md" in c["task"] and "edit/cutlist-v003.json" in c["task"]
    assert stylegate.after_transcript(episode, ep / "work" / "words-take1.json") is None   # not a cut's voice
    (ep / "edit").mkdir(exist_ok=True)
    (ep / "edit" / "cutlist-v003.json").write_text(json.dumps({"version": 1, "saetze": [{"text": "x"}]}))
    db.update("jobs", c["id"], status="done")
    out = stylegate.after_transcript_review(queue.get(c["id"]), engines.RunResult(ok=True, exit_code=0, text="ok"))
    assert out == {"action": "cut_list", "file": "edit/cutlist-v003.json", "sentences": 1}
    assert review.after_review(queue.get(c["id"]), "Verdict: show") is None
