"""The teleprompter shows a cue sheet in pages and counts takes per page (synthetic sheets only)."""

import json

from fastapi.testclient import TestClient

from crewcut import db, episodes, paths, prompter
from crewcut.server.app import create_prompter_app

SHEET = """# Cue sheet, synthetic

## Opening
LINE1: The cheapest setting built my best clip. [Picture: ranking]
PROOF: I tested 4 settings on 8 clips.
PLAN: Here is why, in two points.

## Unit 1 | Proof: Screen | Short: yes
HOOK: My best clip took 40 minutes, the worst one 90.
• Proof: [both clocks] 40 minutes against 90 · same prompt
• Example: [the log] Why so fast? · three helpers · street, flat, edit
PUNCH: Helpers beat thinking time.
ASK: If you like tests like this, subscribe.
BRIDGE: So where did the time go?

## Unit 2 | Proof: Number | Short: no
HOOK: Rendering 600 frames took five hours on one card.
• Number: [counter] 600 times 30 seconds = five hours
PUNCH: One test frame saves hours.

## Payoff
PAYOFF: So the cheap setting wins twice.
• Sum: 40 plus 90 · against 300

## Close
VERDICT: I keep the cheap setting for big jobs.
LINK: If you want this system, the link is in the description.

---
Notes for the edit.
"""

# index of each page's first block: opening 0-2, unit 1 3-8, unit 2 9-11, payoff 12-13, close 14-15
FIRSTS = {"opening": 0, "unit 1": 3, "unit 2": 9, "payoff": 12, "close": 14}

SCRIPT = "First paragraph of a normal script.\n\nSecond paragraph.\n\n\n\nA new section.\n"


def make_episode(files: dict[str, str]) -> str:
    eid = episodes.create("Cue sheet prompter")["id"]
    for name, text in files.items():
        (paths.episode_dir(eid) / name).write_text(text, encoding="utf-8")
    return eid


def log_lines(eid: str, now_ms: float) -> list[dict]:
    return [json.loads(line) for line in prompter.log_file(eid, now_ms).read_text(encoding="utf-8").splitlines()]


def test_a_cue_sheet_becomes_blocks_in_pages():
    view = prompter.cue_sheet_blocks(SHEET)
    assert view["errors"] == []
    blocks, pages = view["blocks"], view["pages"]
    assert [(p["page"], p["label"], p["first"], p["short"]) for p in pages] == [
        ("opening", "Opening", 0, False), ("unit 1", "Unit 1", 3, True), ("unit 2", "Unit 2", 9, False),
        ("payoff", "Payoff", 12, False), ("close", "Close", 14, False)]
    assert [(b["kind"], b["role"]) for b in blocks[3:9]] == [
        ("fixed", "hook"), ("bullet", "proof"), ("bullet", "example"), ("fixed", "punch"), ("fixed", "ask"),
        ("fixed", "bridge")]
    assert [b["page"] for b in blocks] == ["opening"] * 3 + ["unit 1"] * 6 + ["unit 2"] * 3 + ["payoff"] * 2 + \
        ["close"] * 2
    assert [b["section"] for b in blocks] == [1] * 3 + [2] * 6 + [3] * 3 + [4] * 2 + [5] * 2
    assert [b["unit"] for b in blocks[2:4]] == [None, 1]
    # numbered like a normal script, with a longer breath before each new page
    assert [b["n"] for b in blocks] == list(range(1, 17))
    assert blocks[0]["weight"] == len(blocks[0]["text"]) + prompter.PAUSE_CHARS
    assert blocks[2]["weight"] == len(blocks[2]["text"]) + prompter.SECTION_PAUSE_CHARS
    # fixed lines: the spoken words without the picture cue, which is kept apart
    line1 = blocks[0]
    assert line1["text"] == "The cheapest setting built my best clip."
    assert line1["picture"] == "Picture: ranking" and line1["big"] is True and line1["groups"] == []
    assert [b["big"] for b in blocks[3:9]] == [True, False, False, True, False, False]
    assert blocks[1]["big"] is False  # PROOF in the opening is said word for word, in the normal size
    # bullets: the cue words joined with " · ", the picture and the leading question apart
    proof, example = blocks[4], blocks[5]
    assert proof["text"] == "40 minutes against 90 · same prompt"
    assert proof["groups"] == proof["points"] == ["40 minutes against 90", "same prompt"]
    assert proof["picture"] == "both clocks" and proof["question"] is None
    assert example["question"] == "Why so fast?"
    assert example["groups"] == ["three helpers", "street, flat, edit"]
    assert blocks[13]["role"] == "sum" and blocks[13]["picture"] is None
    assert all("Notes" not in b["text"] for b in blocks)


def test_a_german_sheet_keeps_its_page_names_for_the_screens():
    german = SHEET.replace("## Opening", "## Einstieg").replace("LINE1:", "SATZ1:") \
        .replace("## Unit 1 | Proof: Screen | Short: yes", "## Einheit 1 | Beleg: Bildschirm | Short: ja") \
        .replace("## Unit 2 | Proof: Number | Short: no", "## Einheit 2 | Beleg: Zahl | Short: nein") \
        .replace("## Payoff", "## Einlösung").replace("PAYOFF:", "EINLÖSUNG:").replace("## Close", "## Schluss")
    view = prompter.cue_sheet_blocks(german)
    assert [(p["page"], p["label"]) for p in view["pages"]] == [
        ("opening", "Einstieg"), ("unit 1", "Einheit 1"), ("unit 2", "Einheit 2"), ("payoff", "Einlösung"),
        ("close", "Schluss")]
    assert view["pages"][1]["short"] is True and view["blocks"][0]["big"] is True


def test_a_cue_sheet_is_preferred_over_script_drafts_and_the_newest_version_wins(crew):
    eid = make_episode({"brief/SCRIPT-v004.md": SCRIPT, "brief/CUES-v002.md": SHEET, "brief/DREHZETTEL-v010.md": SHEET,
                        "brief/CUES-v9.md": SHEET, "brief/CUES-v010-notes.md": SHEET})
    root = paths.episode_dir(eid)
    assert prompter.script_file(eid) == root / "brief/DREHZETTEL-v010.md"  # 10 > 9, the plain name before a suffix
    (root / "brief/CUES-v011.md").write_text(SHEET, encoding="utf-8")
    assert prompter.script_file(eid) == root / "brief/CUES-v011.md"
    # the selected recording script and the approved card still win
    prompter.select_script(eid, "brief/SCRIPT-v004.md")
    assert prompter.script_file(eid) == root / "brief/SCRIPT-v004.md"
    db.insert("cards", episode=eid, step="script", identity="writer", kind="script", title="Approved script",
              file="brief/CUES-v002.md", status="accepted", created=db.now())
    assert prompter.script_file(eid) == root / "brief/CUES-v002.md"


def test_script_drafts_alone_are_shown_as_before(crew):
    eid = make_episode({"brief/SCRIPT-v001.md": SCRIPT, "brief/SCRIPT-v002.md": SCRIPT + "\nOne more.\n"})
    assert prompter.script_file(eid) == paths.episode_dir(eid) / "brief/SCRIPT-v002.md"
    s = prompter.script(eid)
    assert s["format"] == "script" and s["pages"] == [] and s["note"] is None
    assert s["blocks"] == prompter.parse_script(SCRIPT + "\nOne more.\n")


def test_the_script_answer_has_the_format_and_the_pages(crew):
    eid = make_episode({"brief/CUES-v001.md": SHEET})
    token = episodes.read(eid)["prompter_token"]
    client = TestClient(create_prompter_app(), base_url="http://192.168.1.20:4748")
    s = client.get(f"/p/{token}/script").json()
    assert s["format"] == "cuesheet" and s["file"] == "brief/CUES-v001.md" and s["note"] is None
    assert [p["first"] for p in s["pages"]] == list(FIRSTS.values())
    assert s["blocks"][3]["role"] == "hook" and s["version"].startswith("CUES-v001.md:")
    assert client.get(f"/p/{token}/control").json()["takes"] == {}


def test_a_cue_sheet_is_also_known_by_its_content_and_its_problems_are_shown(crew):
    broken = SHEET.replace("• Number: [counter]", "Number: [counter]")  # a line without a marker is not shown
    eid = make_episode({"brief/approved.md": broken})
    db.insert("cards", episode=eid, step="script", identity="writer", kind="script", title="Approved script",
              file="brief/approved.md", status="accepted", created=db.now())
    s = prompter.script(eid)
    assert s["format"] == "cuesheet" and len(s["pages"]) == 5
    assert s["note"].startswith("Check the cue sheet: line ") and "a line without a marker" in s["note"]


def test_next_prev_and_repeat_move_by_page(crew):
    eid = make_episode({"brief/CUES-v001.md": SHEET})
    step = lambda action, **kw: prompter.set_control(eid, {"action": action, **kw})["block"]  # noqa: E731
    # a screen sends the first block of the page it wants
    assert step("next", block=3) == 3
    assert step("next", block=9) == 9
    assert step("prev", block=3) == 3
    assert step("repeat", block=3) == 3
    # a block inside a page: next goes to the following page, prev and repeat to the start of its page
    assert step("next", block=4) == 9
    assert step("prev", block=8) == 3
    assert step("repeat", block=13) == 12
    # without a block: from the block on the reading line
    prompter.set_control(eid, {"action": "jump", "block": 10})
    assert step("next") == FIRSTS["payoff"]
    assert step("next") == FIRSTS["close"]
    assert step("next") == FIRSTS["close"]  # the last page: nothing after it
    assert step("prev") == FIRSTS["payoff"]
    prompter.set_control(eid, {"action": "jump", "block": 13})
    assert step("repeat") == FIRSTS["payoff"]
    assert step("start") == 0 and step("prev") == 0  # the first page: nothing before it
    assert step("next", block="x") == 0  # a bad value never moves the text
    # a tap on any block still goes exactly there
    assert step("jump", block=5) == 5


def test_every_page_start_counts_a_take_and_the_log_names_page_unit_and_take(crew, monkeypatch):
    eid = make_episode({"brief/CUES-v001.md": SHEET})
    clock = [1_795_000_000_000.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])

    def send(values: dict) -> dict:
        clock[0] += 1000
        return prompter.set_control(eid, values)

    send({"action": "start"})
    send({"playing": True})
    send({"action": "next", "block": 3})
    send({"action": "repeat", "block": 3})
    send({"action": "jump", "block": 5})  # inside the page: the same take goes on
    send({"action": "repeat"})
    send({"action": "next"})
    send({"action": "scrolled", "block": 12, "offset": 0.5})  # a hand scroll into a page no command has started
    send({"playing": False})
    state = send({"mirror": True})  # settings are not takes
    assert state["takes"] == {"opening": 1, "unit 1": 3, "unit 2": 1}
    assert prompter.control(eid)["takes"] == state["takes"]
    lines = log_lines(eid, clock[0])
    assert [(e["action"], e["page"], e["unit"], e["take"]) for e in lines] == [
        ("start", "opening", None, 1), ("play", "opening", None, 1), ("next", "unit 1", 1, 1),
        ("repeat", "unit 1", 1, 2), ("jump", "unit 1", 1, 2), ("repeat", "unit 1", 1, 3), ("next", "unit 2", 2, 1),
        ("scroll", "payoff", None, None), ("pause", "payoff", None, None)]
    # the existing fields are all still there
    third = lines[2]
    assert third["block"] == 4 and third["section"] == 2 and third["offset"] == 0.0 and third["playing"] is True
    assert third["script"] == "brief/CUES-v001.md" and third["words"].startswith("My best clip took 40 minutes")
    assert set(third) >= {"time", "unix_ms", "action", "block", "section", "offset", "playing", "script", "words"}


def test_take_counts_survive_old_and_bad_states_and_screens_cannot_write_them(crew):
    eid = make_episode({"brief/CUES-v001.md": SHEET})
    # a state from before the take count
    db.kv_set(f"prompter:{eid}", json.dumps({"playing": False, "speed": 1.2, "seq": 5, "guide": 40.0}))
    state = prompter.control(eid)
    assert state["takes"] == {} and state["speed"] == 1.2 and state["guide"] == 40.0
    # broken counts are dropped, good ones kept
    db.kv_set(f"prompter:{eid}", json.dumps({"seq": 6, "takes": {"unit 1": "x", "unit 2": 3, "close": True,
                                                                  "payoff": -1}}))
    assert prompter.control(eid)["takes"] == {"unit 2": 3}
    assert prompter.set_control(eid, {"takes": {"unit 2": 99}, "speed": 1.1})["takes"] == {"unit 2": 3}
    assert prompter.set_control(eid, {"action": "next", "block": 9})["takes"] == {"unit 2": 4}
    assert prompter.DEFAULT_CONTROL["takes"] == {}  # the default is never changed by a count


def test_a_normal_script_keeps_its_blocks_steps_and_log(crew, monkeypatch):
    eid = make_episode({"brief/SCRIPT-v001.md": SCRIPT})
    clock = [1_795_000_000_000.0]
    monkeypatch.setattr(prompter, "_now_ms", lambda: clock[0])
    # next and prev go exactly to the block the screen sends, as before
    assert prompter.set_control(eid, {"action": "next", "block": 1})["block"] == 1
    assert prompter.set_control(eid, {"action": "prev", "block": 0})["block"] == 0
    assert prompter.set_control(eid, {"action": "repeat"})["block"] == 0  # without a block nothing moves
    state = prompter.set_control(eid, {"action": "repeat", "block": 2})
    assert state["block"] == 2 and state["takes"] == {}
    lines = log_lines(eid, clock[0])
    assert [(e["action"], e["block"], e["page"], e["unit"], e["take"]) for e in lines] == [
        ("next", 2, None, None, None), ("prev", 1, None, None, None), ("repeat", 3, None, None, None)]
