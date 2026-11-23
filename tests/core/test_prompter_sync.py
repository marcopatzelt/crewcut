"""The teleprompter's speaking blocks, its shared timeline and the take log.

Regression tests for the sync bug of 23 Nov 2026: a hand scroll on the phone did not reach the other screens (it was
never sent while paused), a playing screen's progress reports overwrote it, and a newly opened screen started at the
top. Now every command is an explicit, numbered write, and every screen follows the newest one."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from crewcut import episodes, paths, prompter
from crewcut.server.app import create_prompter_app

SCRIPT = """Erster Satz der Folge.

Zweiter Absatz, noch im Intro.



Rolle eins ist der Research. Den macht der Scout.

Victor ist 19 und macht das Growth.


Rolle zwei ist das Skript.

---
Notizen für den Schnitt.
"""


def make_episode(text: str = SCRIPT) -> tuple[str, str]:
    eid = episodes.create("Prompter blocks")["id"]
    (paths.episode_dir(eid) / "brief/SCRIPT-v001.md").write_text(text, encoding="utf-8")
    return eid, episodes.read(eid)["prompter_token"]


def weights(eid: str) -> list[float]:
    return [b["weight"] for b in prompter.script(eid)["blocks"]]


def test_blocks_are_numbered_paragraphs_and_keep_the_sections():
    blocks = prompter.parse_script(SCRIPT)
    assert [b["n"] for b in blocks] == [1, 2, 3, 4, 5]
    assert [b["section"] for b in blocks] == [1, 1, 2, 2, 3]
    assert blocks[0]["text"] == "Erster Satz der Folge."
    assert all("Notizen" not in b["text"] for b in blocks)
    # a breath after every block, a longer one before a new section
    assert blocks[0]["weight"] == len(blocks[0]["text"]) + prompter.PAUSE_CHARS
    assert blocks[1]["weight"] == len(blocks[1]["text"]) + prompter.SECTION_PAUSE_CHARS


def test_headings_start_a_section_and_have_no_number():
    blocks = prompter.parse_script("# Intro\n\nEins.\n\n# Hauptteil\nZwei.\n\nDrei.\n")
    assert [(b["text"], b["n"], b["section"]) for b in blocks] == [
        ("Intro", None, 1), ("Eins.", 1, 1), ("Hauptteil", None, 2), ("Zwei.", 2, 2), ("Drei.", 3, 2)]


def test_the_timeline_moves_through_blocks_and_stops_at_the_end():
    w = [10.0, 20.0, 30.0]
    assert prompter.advance(w, 0, 0.0, 5) == (0, 0.5, False)
    assert prompter.advance(w, 0, 0.5, 15) == (1, 0.5, False)
    assert prompter.advance(w, 1, 0.0, 20) == (2, 0.0, False)
    assert prompter.advance(w, 2, 0.5, 100) == (2, 1.0, True)
    assert prompter.advance([], 3, 0.2, 1) == (0, 0.0, True)
    state = {"playing": True, "at": 1000.0, "speed": 2.0, "block": 0, "offset": 0.0}
    # one second at speed 2 is 2 * CHARS_PER_SECOND characters
    block, offset, _ = prompter.where(state, [1000.0], 2000.0)
    assert (block, offset) == (0, pytest.approx(2 * prompter.CHARS_PER_SECOND / 1000))
    # before `at` (a hold after a jump) the text waits
    assert prompter.where(state, [1000.0], 500.0)[:2] == (0, 0.0)


def test_a_phone_scroll_reaches_the_other_screen_at_once_while_paused(crew):
    eid, token = make_episode()
    phone = TestClient(create_prompter_app(), base_url="http://192.168.1.20:4748")
    desk = TestClient(create_prompter_app(), base_url="http://127.0.0.1:4748")
    seen = desk.get(f"/p/{token}/control").json()
    # the phone scrolls back to the middle of block 2 (index 1) while nothing plays
    sent = phone.post(f"/p/{token}/control", json={"action": "scroll", "block": 1, "offset": 0.4, "client": "phone"}).json()
    assert sent["seq"] > seen["seq"] and sent["by"] == "phone"
    t0 = time.monotonic()
    after = desk.get(f"/p/{token}/control", params={"after": seen["seq"], "wait": 5}).json()
    assert time.monotonic() - t0 < 1.0  # already changed: no waiting
    assert (after["block"], after["offset"], after["playing"]) == (1, 0.4, False)
    # pressing Play keeps the place the phone scrolled to: no snap back to an older position
    played = phone.post(f"/p/{token}/control", json={"playing": True, "client": "phone"}).json()
    assert played["block"] == 1 and played["offset"] == pytest.approx(0.4, abs=0.01)


def test_a_waiting_screen_hears_a_command_within_a_fraction_of_a_second(crew):
    eid, token = make_episode()
    desk = TestClient(create_prompter_app(), base_url="http://127.0.0.1:4748")
    phone = TestClient(create_prompter_app(), base_url="http://192.168.1.20:4748")
    current = desk.get(f"/p/{token}/control").json()["seq"]
    result: dict = {}

    def listen():
        t0 = time.monotonic()
        result["state"] = desk.get(f"/p/{token}/control", params={"after": current, "wait": 10}).json()
        result["took"] = time.monotonic() - t0

    listener = threading.Thread(target=listen)
    listener.start()
    time.sleep(0.4)
    phone.post(f"/p/{token}/control", json={"action": "jump", "block": 3, "client": "phone"})
    listener.join(5)
    assert result["state"]["block"] == 3 and result["state"]["cue"] == 1
    assert result["took"] < 1.5  # 0.4 s before the command plus at most a few polls of 25 ms
    assert result["state"]["waited"] >= 300


def test_an_unchanged_state_waits_and_answers_with_the_server_time(crew):
    eid, token = make_episode()
    client = TestClient(create_prompter_app(), base_url="http://127.0.0.1:4748")
    seq = client.get(f"/p/{token}/control").json()["seq"]
    t0 = time.monotonic()
    state = client.get(f"/p/{token}/control", params={"after": seq, "wait": 0.3}).json()
    assert time.monotonic() - t0 >= 0.28 and state["seq"] == seq
    assert abs(state["now"] - time.time() * 1000) < 2000


def test_every_write_is_newer_and_names_its_screen(crew):
    eid, _ = make_episode()
    a = prompter.set_control(eid, {"speed": 1.2, "client": "desk"})
    b = prompter.set_control(eid, {"mirror": True, "client": "phone"})
    c = prompter.set_control(eid, {"guide": 40, "client": "../bad name"})
    assert a["seq"] < b["seq"] < c["seq"]
    assert (a["by"], b["by"], c["by"]) == ("desk", "phone", "")


def test_playing_follows_the_timeline_without_progress_reports(crew, monkeypatch):
    eid, _ = make_episode()
    clock = [1_000_000.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])
    prompter.set_control(eid, {"playing": True})
    w = weights(eid)
    clock[0] += 1000  # one second later the anchor has moved CHARS_PER_SECOND characters on every screen
    expected = prompter.advance(w, 0, 0.0, prompter.CHARS_PER_SECOND)
    assert prompter.where(prompter.control(eid), w, clock[0]) == expected
    # pausing stores where the text is, and it stays there
    paused = prompter.set_control(eid, {"playing": False})
    assert (paused["block"], paused["offset"]) == pytest.approx(expected[:2])
    clock[0] += 5000
    assert prompter.where(prompter.control(eid), w, clock[0])[:2] == pytest.approx(expected[:2])


def test_a_jump_while_playing_holds_at_the_block_start_then_plays_on(crew, monkeypatch):
    eid, _ = make_episode()
    clock = [2_000_000.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])
    prompter.set_control(eid, {"playing": True})
    clock[0] += 3000
    state = prompter.set_control(eid, {"action": "repeat", "block": 2, "client": "phone"})
    assert (state["block"], state["offset"], state["playing"]) == (2, 0.0, True)
    assert state["at"] == clock[0] + prompter.JUMP_HOLD_MS
    w = weights(eid)
    clock[0] += prompter.JUMP_HOLD_MS - 1
    assert prompter.where(prompter.control(eid), w, clock[0])[:2] == (2, 0.0)
    clock[0] += 1001
    block, offset, _ = prompter.where(prompter.control(eid), w, clock[0])
    assert block == 2 and offset > 0
    # a speed change during the hold keeps the hold
    clock[0] = state["at"] - 500
    held = prompter.set_control(eid, {"speed": 1.5})
    assert held["at"] == state["at"]


def test_start_goes_to_the_beginning_and_pauses(crew):
    eid, _ = make_episode()
    prompter.set_control(eid, {"action": "jump", "block": 3})
    prompter.set_control(eid, {"playing": True})
    state = prompter.set_control(eid, {"action": "start"})
    assert (state["block"], state["offset"], state["playing"]) == (0, 0.0, False)


def test_the_end_pauses_only_when_the_timeline_is_really_at_the_end(crew, monkeypatch):
    eid, _ = make_episode()
    clock = [3_000_000.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])
    prompter.set_control(eid, {"playing": True})
    clock[0] += 1000
    early = prompter.set_control(eid, {"action": "end"})
    assert early["playing"] is True
    clock[0] += 60_000
    done = prompter.set_control(eid, {"action": "end"})
    assert done["playing"] is False and done["block"] == len(weights(eid)) - 1 and done["offset"] == 1.0


def test_bad_values_never_move_the_text(crew):
    eid, _ = make_episode()
    before = prompter.set_control(eid, {"action": "jump", "block": 2})
    for bad in ({"action": "jump", "block": "x"}, {"action": "scroll", "block": 1, "offset": float("nan")},
                {"action": "jump", "block": True}, {"action": "scroll", "block": None, "offset": 0.5}):
        state = prompter.set_control(eid, bad)
        assert (state["block"], state["offset"]) == (before["block"], before["offset"])
    assert prompter.set_control(eid, {"action": "jump", "block": 99})["block"] == 4  # the last block
    assert prompter.set_control(eid, {"speed": "fast"})["speed"] == 1.0


def test_a_state_from_before_the_timeline_does_not_play_on(crew):
    from crewcut import db
    eid, _ = make_episode()
    db.kv_set(f"prompter:{eid}", json.dumps({"playing": True, "speed": 1.0, "position": 0.99, "guide": 75.0}))
    state = prompter.control(eid)
    assert state["playing"] is False and state["guide"] == 75.0 and state["block"] == 0


def test_jumps_repeats_and_play_are_written_to_the_take_log(crew, monkeypatch):
    eid, _ = make_episode()
    clock = [1_795_000_000_123.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])
    prompter.set_control(eid, {"action": "jump", "block": 2, "client": "phone"})
    clock[0] += 1000
    prompter.set_control(eid, {"playing": True})
    clock[0] += 4000
    prompter.set_control(eid, {"action": "repeat", "block": 2})
    prompter.set_control(eid, {"action": "next", "block": 3})
    prompter.set_control(eid, {"action": "scroll", "block": 1, "offset": 0.5})  # live scroll: not logged
    prompter.set_control(eid, {"action": "scrolled", "block": 1, "offset": 0.5})  # the end of the scroll: logged
    prompter.set_control(eid, {"mirror": True})  # settings are not takes
    log = prompter.log_file(eid, clock[0])
    assert log.name == "prompter-log-2026-11-18.jsonl" and log.parent.name == "brief"
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [(e["action"], e["block"]) for e in lines] == [
        ("jump", 3), ("play", 3), ("repeat", 3), ("next", 4), ("scroll", 2)]
    first = lines[0]
    assert first["time"] == "2026-11-18T11:06:40.123Z" and first["unix_ms"] == 1_795_000_000_123
    assert first["section"] == 2 and first["script"] == "brief/SCRIPT-v001.md"
    assert first["words"].startswith("Rolle eins ist der Research.")


def test_the_script_answer_has_numbers_weights_and_a_version(crew):
    eid, token = make_episode()
    p = TestClient(create_prompter_app(), base_url="http://192.168.1.20:4748")
    s = p.get(f"/p/{token}/script").json()
    assert [b["n"] for b in s["blocks"]] == [1, 2, 3, 4, 5]
    assert s["cps"] == prompter.CHARS_PER_SECOND and s["version"].startswith("SCRIPT-v001.md:")
    assert p.get(f"/p/{token}/control").json()["version"] == s["version"]
    assert p.get("/p/not-a-real-token-123/control").status_code == 404
