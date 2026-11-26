"""The style gate (crewcut/stylegate.py): a studio's own style checker is a hard gate for scripts.

A fake checker with the studio's interface (version 1 JSON, exit 0 pass, 1 fail, 2 unreadable) stands in for
`deutscher-hormozi/scripts/stil_check.py`: a script fails DH-L22 (old id HB2) when it ends with a goodbye, fails DH-L5
when it has no number, and its one Critic question K-HB2 is answered in `<script>.kritik.json`.
"""

import json
import os
import subprocess
import sys

import pytest

from crewcut import approvals, db, engines, episodes, paths, stylegate
from crewcut.conductor import flow, queue

FAKE = r'''
import json, re, sys
from pathlib import Path
args = sys.argv[1:]
f = Path(args[0])
if not f.is_file():
    print("unreadable", file=sys.stderr); sys.exit(2)
fmt = args[args.index("--format") + 1] if "--format" in args else "lang"
title = args[args.index("--titel") + 1] if "--titel" in args else None
kp = Path(args[args.index("--kritik") + 1]) if "--kritik" in args else f.with_suffix(".kritik.json")
text = f.read_text(encoding="utf-8").split("\n---\n")[0]
lines = text.splitlines()
checks = []
bye = next((i for i, x in enumerate(lines, 1) if "danke" in x.lower()), None)
checks.append({"id": "DH-L22", "alt": "HB2", "rule": "DH-L22", "kind": "auto", "titel": "Kein Gruß am Ende",
               "measured": 1 if bye else 0, "target": "0", "pass": bye is None, "line": f"Z{bye} ~4:10" if bye else None,
               "fix": None if bye is None else "Gruß streichen, mit dem Urteil enden."})
num = bool(re.search(r"\d", text))
checks.append({"id": "DH-L5", "alt": "HB1", "rule": "DH-L5", "kind": "auto", "titel": "Zahl in 0:10 bis 0:20",
               "measured": "ja" if num else "nein", "target": "Zahl", "pass": num, "line": None if num else "Z1 ~0:10",
               "fix": None if num else "Eine gemessene Zahl in 0:10 bis 0:20."})
answers = json.loads(kp.read_text()) if kp.is_file() else {}
a = answers.get("K-HB2")
a = a.get("antwort") if isinstance(a, dict) else a
checks.append({"id": "K-HB2", "rule": "DH-L22", "kind": "kritik", "titel": "Schluss ist ein Urteil",
               "measured": "offen" if a is None else ("ja" if a else "nein"), "target": "ja",
               "pass": None if a is None else bool(a), "line": None, "fix": None if a else "Urteil statt Rückblick.",
               "frage": "Ist der Schluss ein Urteil?"})
auto = all(c["pass"] for c in checks if c["kind"] == "auto")
ok = auto and all(c["pass"] is True for c in checks if c["kind"] == "kritik")
print(json.dumps({"version": 1, "datei": str(f), "format": fmt, "titel": title, "woerter": len(text.split()),
                  "dauer_s": 60.0, "zeiten": "geschaetzt", "pass": ok, "auto_pass": auto,
                  "kritik_offen": [c["id"] for c in checks if c["pass"] is None], "checks": checks, "metrics": {}}))
sys.exit(0 if ok else 1)
'''

GOOD = ("Claude hat 9 von 10 Läufen bestanden.\nDas habe ich gemessen.\n\nMein Urteil ist klar, es hält.\n\n---\n"
        "Prämisse: x\n")
BYE = GOOD.replace("Mein Urteil ist klar, es hält.", "Mein Urteil ist klar, es hält.\nUnd danke fürs Zuschauen.")


@pytest.fixture
def skill(studio):
    d = studio / "skills" / "deutscher-hormozi"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: deutscher-hormozi\ndescription: test\n---\n")
    (d / "scripts" / "stil_check.py").write_text(FAKE)
    return d


@pytest.fixture
def episode(studio, crew):
    ep = episodes.create("Claude im Test")["id"]
    for s in ("idea", "title"):
        episodes.set_step(ep, s, "done")
    episodes.set_step(ep, "script", "working")
    return ep


def write(ep: str, name: str, text: str, kritik: bool | None = None) -> str:
    p = paths.episode_dir(ep) / "brief" / name
    p.write_text(text, encoding="utf-8")
    if kritik is not None:
        p.with_suffix(".kritik.json").write_text(json.dumps({"K-HB2": {"antwort": kritik, "grund": "test"}}))
    return f"brief/{name}"


def writer_ends(ep: str) -> dict:
    """A Writer run in the script step that ended; the conductor's after_job runs as in the queue."""
    jid = queue.add(ep, "writer", "script", "Write the script.")
    db.update("jobs", jid, status="done", started=db.now(), ended=db.now(),
              data={"engine": "claude", "session": "sess-writer"})
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text="Done."))
    return queue.get(jid)


def jobs(ep: str, identity: str, after: int = 0) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = ? AND id > ? ORDER BY id",
                                 (ep, identity, after)))


def finish_all(ep: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE jobs SET status = 'done' WHERE episode = ? AND status IN ('queued', 'running')", (ep,))


def test_a_passing_script_gets_its_card(skill, episode):
    rel = write(episode, "SCRIPT-v001.md", GOOD, kritik=True)
    v = stylegate.check(episode)
    assert v["pass"] and v["mode"] == "block" and [r["file"] for r in v["results"]] == [rel]
    assert v["results"][0]["format"] == "lang" and v["results"][0]["kritik"] == "brief/SCRIPT-v001.kritik.json"
    card = approvals.propose(episode, "script", "script", "Skript", file=rel)
    assert card["status"] == "open" and card["data"]["style_gate"]["pass"] is True


def test_a_failing_script_gets_no_card_and_names_id_line_and_fix(skill, episode):
    rel = write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    with pytest.raises(stylegate.Blocked) as e:
        approvals.propose(episode, "script", "script", "Skript", file=rel)
    msg = str(e.value)
    assert "DH-L22" in msg and "Z5 ~4:10" in msg and "Gruß streichen" in msg
    assert stylegate.failed_ids(e.value.verdict) == ["DH-L22"]
    assert not approvals.list_cards(episode=episode)


def test_an_open_critic_question_blocks(skill, episode):
    rel = write(episode, "SCRIPT-v001.md", GOOD)           # no kritik.json yet
    with pytest.raises(stylegate.Blocked) as e:
        approvals.propose(episode, "script", "script", "Skript", file=rel)
    assert "open Critic questions: K-HB2" in str(e.value)
    r = e.value.verdict["results"][0]
    assert r["auto_pass"] and r["open"] == ["K-HB2"] and not r["failed"]


def test_after_the_writer_the_failed_checks_go_back_for_bounded_rounds(skill, episode):
    write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    first = writer_ends(episode)
    assert first["data"]["style_gate_after"]["pass"] is False
    [r1] = jobs(episode, "writer", first["id"])
    assert r1["data"]["style_gate_round"] == 1 and r1["data"]["resume"]["session"] == "sess-writer"
    assert "round 1 of 3" in r1["task"] and "DH-L22" in r1["task"] and "Gruß streichen" in r1["task"]
    assert any("Style check fails" in m["text"] and "DH-L22" in m["text"] for m in flow.messages(episode))
    last = r1
    for n in (2, 3):
        finish_all(episode)
        writer_ends(episode)
        [nxt] = [j for j in jobs(episode, "writer", last["id"]) if (j.get("data") or {}).get("style_gate_round")]
        assert nxt["data"]["style_gate_round"] == n
        last = nxt
    finish_all(episode)
    writer_ends(episode)                                  # round 4 would be too many: the user decides
    assert not [j for j in jobs(episode, "writer", last["id"]) if (j.get("data") or {}).get("style_gate_round")]
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    assert "still fails after 3 rounds" in card["title"] and card["data"]["style_gate_limit"]["pass"] is False
    approvals.decide(card["id"], True)                    # yes: more rounds
    more = [j for j in jobs(episode, "writer", last["id"]) if (j.get("data") or {}).get("style_gate_round")]
    assert more and more[-1]["data"]["style_gate_round"] == 1


def test_only_missing_critic_answers_go_to_the_critic(skill, episode):
    write(episode, "SCRIPT-v001.md", GOOD)
    w = writer_ends(episode)
    [c] = jobs(episode, "critic")
    assert c["step"] == "script" and c["parent"] == w["id"] and c["data"]["style_gate_kritik"] == 1
    assert "K-HB2" in c["task"] and "SCRIPT-v001.kritik.json" in c["task"] and "In doubt: false" in c["task"]
    assert not jobs(episode, "writer", w["id"])


def test_a_critic_no_goes_back_to_the_writer(skill, episode):
    write(episode, "SCRIPT-v001.md", GOOD, kritik=False)
    w = writer_ends(episode)
    [r1] = jobs(episode, "writer", w["id"])
    assert "K-HB2" in r1["task"] and "Urteil statt Rückblick" in r1["task"]


def test_nothing_is_queued_twice_while_a_critic_runs_or_a_card_waits(skill, episode):
    write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    queue.add(episode, "critic", "script", "check SCRIPT-v001.md")
    w = writer_ends(episode)
    assert not jobs(episode, "writer", w["id"])


def test_the_way_to_recording_refuses_a_failing_script(skill, episode):
    write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    with pytest.raises(stylegate.Blocked):
        stylegate.guard_advance(episode, "record")
    jid = flow.start_step(episode, "record")
    p = episodes.read(episode)
    assert p["steps"]["record"]["status"] == "open" and p["steps"]["script"]["status"] == "working"
    assert "record waits" in p["next_action"]
    assert queue.get(jid)["identity"] == "writer" and queue.get(jid)["data"]["style_gate_round"] == 1
    assert any("Record waits" in m["text"] for m in flow.messages(episode))
    # the cut of something not yet recorded waits too; a recorded episode's cut does not
    with pytest.raises(stylegate.Blocked):
        stylegate.guard_advance(episode, "edit")
    (paths.episode_dir(episode) / "originals" / "take1.mov").write_bytes(b"x")
    assert stylegate.guard_advance(episode, "edit") is None


def test_a_yes_on_a_card_that_fails_by_now_goes_back_to_the_writer(skill, episode):
    rel = write(episode, "SCRIPT-v001.md", GOOD, kritik=True)
    card = approvals.propose(episode, "script", "script", "Skript", file=rel)
    k = paths.episode_dir(episode) / "brief" / "SCRIPT-v001.kritik.json"
    k.write_text(json.dumps({"K-HB2": {"antwort": False, "grund": "Rückblick"}}))   # the Critic's answer changed
    with pytest.raises(stylegate.Blocked) as e:          # the path of the button and of `crewcut card accept`
        approvals.decide(card["id"], True)
    assert "went back to the Writer" in str(e.value)
    c = approvals.get(card["id"])
    assert c["status"] == "declined" and c["data"]["style_gate_refused"]["pass"] is False
    assert episodes.read(episode)["steps"]["script"]["status"] == "working"
    [w] = jobs(episode, "writer")
    assert "was refused: the style check fails" in w["task"] and "K-HB2" in w["task"]


def test_a_passing_yes_moves_on_to_recording(skill, episode, monkeypatch):
    from crewcut import prompter
    monkeypatch.setattr(prompter, "url_for", lambda e: "http://prompter")
    rel = write(episode, "SCRIPT-v001.md", GOOD, kritik=True)
    card = approvals.propose(episode, "script", "script", "Skript", file=rel)
    approvals.decide(card["id"], True)
    p = episodes.read(episode)
    assert p["steps"]["script"]["status"] == "done" and p["steps"]["record"]["status"] == "waiting"


def test_newest_script_and_short_are_the_subjects(skill, episode):
    write(episode, "SCRIPT-v002.md", GOOD, kritik=True)
    write(episode, "SCRIPT-v010-entwurf.md", BYE, kritik=True)
    write(episode, "SHORT-v003.md", GOOD, kritik=True)
    (paths.episode_dir(episode) / "brief" / "SCRIPT-DE-v099.md").write_text(BYE)   # not a script version
    found = stylegate.latest(episode)
    assert found["SCRIPT"].name == "SCRIPT-v010-entwurf.md" and found["SHORT"].name == "SHORT-v003.md"
    v = stylegate.check(episode)
    assert [(r["file"], r["format"]) for r in v["results"]] == [("brief/SCRIPT-v010-entwurf.md", "lang"),
                                                                 ("brief/SHORT-v003.md", "short")]
    assert not v["pass"] and stylegate.failed_ids(v) == ["DH-L22"]
    one = stylegate.check(episode, "brief/SCRIPT-v002.md")       # a card's file replaces the newest of its kind
    assert one["pass"] and [r["file"] for r in one["results"]] == ["brief/SCRIPT-v002.md", "brief/SHORT-v003.md"]


def test_the_title_goes_to_the_checker_when_the_script_does_not_name_it(skill, episode):
    p = episodes.read(episode)
    p["title"] = "Claude im Test"
    episodes.write(episode, p)
    write(episode, "SCRIPT-v001.md", GOOD, kritik=True)
    assert stylegate.check(episode)["results"][0]["title"] == "Claude im Test"
    write(episode, "SCRIPT-v001.md", GOOD + 'Titel: „Ein anderer Titel“\n', kritik=True)
    assert stylegate.check(episode)["results"][0]["title"] is None


def test_without_the_skill_the_gate_is_skipped_with_a_warning(episode):
    rel = write(episode, "SCRIPT-v001.md", BYE)
    v = stylegate.check(episode)
    assert v["pass"] and "has no deutscher-hormozi skill" in v["skipped"]
    assert writer_ends(episode)["data"]["style_gate_after"]["skipped"]
    assert not jobs(episode, "writer", 1)
    assert approvals.propose(episode, "script", "script", "Skript", file=rel)["data"]["style_gate"]["skipped"]


def test_mode_warn_and_off_from_the_pack(skill, episode, studio):
    rel = write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    brand = studio / "brand"
    brand.mkdir(exist_ok=True)
    (brand / "brand.json").write_text((paths.neutral_pack_dir() / "brand.json").read_text())
    (brand / "channel.json").write_text(json.dumps({"script": {"style_gate": {"mode": "warn"}}}))
    card = approvals.propose(episode, "script", "script", "Skript", file=rel)
    assert card["data"]["style_gate"]["pass"] is False and card["data"]["style_gate"]["mode"] == "warn"
    (brand / "channel.json").write_text(json.dumps({"script": {"style_gate": {"mode": "off"}}}))
    assert stylegate.guard_advance(episode, "record")["skipped"].startswith("the style gate is off")
    (brand / "channel.json").write_text(json.dumps({"script": {"style_gate": {"mode": "strict-typo"}}}))
    assert stylegate.settings()["mode"] == "block"           # a typo stays strict


def test_config_max_rounds_and_a_broken_checker(skill, episode, studio):
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text("[style_gate]\nmax_rounds = 1\n")
    assert stylegate.settings()["max_rounds"] == 1
    (skill / "scripts" / "stil_check.py").write_text("print('no json')\n")
    write(episode, "SCRIPT-v001.md", GOOD, kritik=True)
    v = stylegate.check(episode)
    assert not v["pass"] and "gave no JSON" in v["results"][0]["error"]
    (skill / "scripts" / "stil_check.py").write_text("import json; print(json.dumps({'version': 2}))\n")
    assert "interface version 2" in stylegate.check(episode)["results"][0]["error"]


def _cli(studio, *args):
    env = {**os.environ, "CREWCUT_STUDIO": str(studio)}
    env.pop("CREWCUT_IDENTITY", None)
    return subprocess.run([sys.executable, "-m", "crewcut", *args], capture_output=True, text=True, env=env)


def test_the_command_line_refuses_the_advance_and_shows_the_gate(skill, episode, studio):
    write(episode, "SCRIPT-v001.md", BYE, kritik=True)
    r = _cli(studio, "episode", "step", episode, "script", "done")
    assert r.returncode == 3 and "style check fails" in r.stderr and "DH-L22" in r.stderr
    assert episodes.read(episode)["steps"]["script"]["status"] == "working"
    r = _cli(studio, "style-gate", episode, "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["results"][0]["failed"][0]["id"] == "DH-L22"
    write(episode, "SCRIPT-v002.md", GOOD, kritik=True)
    r = _cli(studio, "style-gate", episode)
    assert r.returncode == 0 and "PASS" in r.stdout
    r = _cli(studio, "style-gate", episode, "--file", "brief/SCRIPT-v001.md")
    assert r.returncode == 1 and "BLOCK" in r.stdout
    assert _cli(studio, "episode", "step", episode, "script", "done").returncode == 0


def test_writer_and_critic_are_told_about_the_gate(skill, episode):
    from crewcut import team
    from crewcut.conductor import prompts
    for who in ("writer", "critic"):
        text = prompts.system_prompt(team.get(who), episode, "script")
        assert "stil_check.py" in text and "kritik.json" in text and "--nur-auto" in text, who
    assert "kritik.json" not in prompts.system_prompt(team.get("editor"), episode, "edit")
    task = prompts.step_task("script", episode)
    assert "no goodbye, no thanks, no recap" in task and "exactly one call to action" not in task
