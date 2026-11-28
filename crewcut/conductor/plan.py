"""The plan of a format episode: the Scout picks the show format, the test runs, then the Writer writes the script.

New Episode with the format library not empty (crewcut/showformats.py):
1. the Scout's plan job (step idea, data `plan`): classify the input, pick the format, its kind and the topic type
   (`crewcut formats choose`), write brief/FORMAT-v001.md, BRIEF.md, TESTPLAN-v001.md, PACKAGING-v001.md;
2. when it ends, the conductor posts the pick and its reason in the chat and marks the idea step done. A format with a
   test plan runs its test first ("Do stuff, then talk about what you did or what happened", Hormozi, $100M Leads):
   the script step waits, and a card asks whether the Scout runs the test plan now (free tests; money needs its own
   spend card). The test writes brief/TESTERGEBNIS-v001.md (or MESSKARTE-v001.md). As soon as that file is there and no
   job of the episode runs, the conductor gives the script step to the Writer (`tick`). A format without a test plan
   goes to the Writer at once;
3. the Writer writes a full script brief/SCRIPT-v001.md from the format's template (data `format_script`); the style
   gate runs on it (stylegate.after_writer). A script with a placeholder fails before any Critic round; when the test
   result is still missing, the gate holds the script and waits here too. When the script passes and the format has a
   cue template, the Writer derives the cue sheet (prompts.cue_sheet_task), the gate checks that too, then the card;
4. after the script card the episode goes on with its normal steps (the title step starts from PACKAGING-v001.md).
"""

from __future__ import annotations

import json
import time

from .. import db, episodes, showformats
from . import prompts, queue

WAIT_KEY = "format_test_wait:"
EVERY_S = 20.0
_last = {"t": 0.0}


def start(episode: str, seed: str) -> int:
    jid = queue.add(episode, "scout", "idea", prompts.plan_task(episode, seed), data={"plan": 1})
    episodes.set_step(episode, "idea", "working",
                      next_action="Scout reads the input and picks the format.")
    return jid


def message(choice: dict) -> str:
    f = showformats.get(choice.get("format")) or {}
    head = f"Format: {choice.get('name') or choice.get('format')}"
    kind = showformats.kind_of(f, choice.get("kind"))
    meta = [x for x in (choice.get("format"), (kind or {}).get("name"), choice.get("length") or f.get("length"),
                        showformats.TOPIC_NAMES.get(choice.get("topic_type") or "", choice.get("topic_type"))) if x]
    text = head + (f" ({', '.join(meta)})" if meta else "") + "."
    if choice.get("reason"):
        text += f" {choice['reason']}"
    if choice.get("runner_up"):
        text += f" Runner-up: {choice['runner_up']}"
    return text


def after_job(job: dict, res) -> bool:
    """After the Scout's plan job. True when handled here."""
    d = job.get("data") or {}
    episode = job.get("episode")
    if not d.get("plan") or not episode or job.get("identity") != "scout":
        return False
    if not getattr(res, "ok", False):
        return False   # the usual "stopped" message; "try again" restarts it
    from . import flow
    choice = showformats.read_choice(episode)
    if choice is None:
        flow.post(episode, "The Scout wrote no brief/FORMAT-v001.md, so no format is chosen yet. Say \"try again\" "
                  "or name a format.", job=job["id"])
        return True
    project = episodes.read(episode)
    if not choice["known"]:
        flow.post(episode, f"The Scout chose {choice['format']!r}, which is not in the format library "
                  "(`crewcut formats`). Say which format to use.", job=job["id"])
        return True
    f = showformats.get(choice["format"]) or {}
    kind = choice.get("kind") if showformats.kind_of(f, choice.get("kind")) else None
    if project.get("show_format") != choice["format"] or (kind and project.get("format_kind") != kind):
        try:
            project = showformats.choose(episode, choice["format"],
                                         topic_type=choice.get("topic_type") if choice.get("topic_type")
                                         in showformats.TOPIC_TYPES else None, kind=kind)
        except ValueError as e:
            flow.post(episode, f"The format pick could not be recorded: {e}", job=job["id"])
            return True
    flow.post(episode, message(choice), author="scout", job=job["id"], preview=choice["file"])
    episodes.set_step(episode, "idea", "done")
    if showformats.test_pending(episode):
        wait_for_test(episode)
        return True
    start_script(episode)
    return True


def start_script(episode: str, after_test: str | None = None) -> int:
    from . import flow
    episodes.set_step(episode, "script", "working", next_action="The Writer writes the full script from the format.")
    jid = queue.add(episode, "writer", "script", prompts.format_script_task(episode),
                    data={"format_script": 1, **({"after_test": after_test} if after_test else {})})
    flow.post(episode, ("The test result is in (" + after_test + "). " if after_test else "")
              + "The Writer writes the full script now. The style check runs on it before you see it.", step="script")
    return jid


# ---- the test before the script -------------------------------------------------------------------------------------
def _german() -> bool:
    return prompts._german()


def waiting(episode: str) -> bool:
    return db.kv_get(WAIT_KEY + episode) is not None


def wait_for_test(episode: str, card: bool = True, why: str | None = None) -> bool:
    """The script step waits for the test result. Idempotent. False when there is nothing to wait for (no test needed,
    or the result is there already: then the caller may start the Writer)."""
    from . import flow
    if not showformats.test_pending(episode):
        return False
    plan_file = showformats.test_plan(episode)
    first = not waiting(episode)
    db.kv_set(WAIT_KEY + episode, json.dumps({"since": db.now(), "test_plan": plan_file.name if plan_file else None}))
    de = _german()
    episodes.set_step(episode, "script", "waiting",
                      next_action=("Das Skript wartet auf das Testergebnis (brief/TESTERGEBNIS-v001.md)." if de else
                                   "The script waits for the test result (brief/TEST-RESULT-v001.md)."))
    if first:
        plan_rel = f"brief/{plan_file.name}" if plan_file else "brief/TESTPLAN-v001.md"
        flow.post(episode, (why or "") + (
            f"Erst der Test, dann das Skript. Der Testplan steht in {plan_rel}. Das Skript beginnt, sobald "
            "brief/TESTERGEBNIS-v001.md (oder MESSKARTE-v001.md) mit den gemessenen Zahlen da ist; vorher schreibt "
            "niemand ein Skript und kein Critic prüft eines." if de else
            f"Test first, then the script. The test plan is {plan_rel}. The script starts as soon as "
            "brief/TEST-RESULT-v001.md (or TESTERGEBNIS-v001.md) with the measured numbers is there; until then nobody "
            "writes a script and no Critic reviews one."), step="script")
        if card:
            propose_test_card(episode, plan_rel)
    return True


def propose_test_card(episode: str, plan_rel: str) -> dict | None:
    from .. import approvals
    for c in approvals.list_cards(episode, "open"):
        if (c.get("data") or {}).get("format_test"):
            return None
    de = _german()
    try:
        return approvals.propose(
            episode, "script", "other",
            "Testplan jetzt ausführen?" if de else "Run the test plan now?",
            body=(f"{plan_rel} ist fertig. Ja: der Scout führt die kostenlosen Tests aus, zählt wie im Plan festgelegt "
                  "und schreibt brief/TESTERGEBNIS-v001.md; was Geld kostet, fragt vorher mit einer eigenen "
                  "Ausgabe-Karte. Danach schreibt der Writer das Skript aus den gemessenen Zahlen. Nein: das Skript "
                  "wartet, bis du das Testergebnis selbst ablegst." if de else
                  f"{plan_rel} is ready. Yes: the Scout runs the free tests, counts as the plan fixed it and writes "
                  "brief/TEST-RESULT-v001.md; anything that costs money asks first with its own spend card. Then the "
                  "Writer writes the script from the measured numbers. No: the script waits until you drop the test "
                  "result yourself."),
            identity="scout", job=None, data={"format_test": {"plan": plan_rel}})
    except (ValueError, FileNotFoundError):
        return None


def on_card(card: dict) -> bool:
    """The answer to the test card. True when handled here."""
    d = (card.get("data") or {}).get("format_test")
    if not d:
        return False
    from . import flow
    episode = card["episode"]
    de = _german()
    if card["status"] == "accepted":
        if showformats.test_result(episode) is None:
            jid = queue.add(episode, "scout", "script", prompts.format_test_task(episode), data={"format_test": 1})
            db.update("jobs", jid, doing="Running the test plan")
            flow.post(episode, "Der Scout führt den Testplan jetzt aus." if de else "The Scout runs the test plan now.",
                      card=card["id"], author="scout")
        return True
    flow.post(episode, ("Das Skript wartet. Leg das Testergebnis als brief/TESTERGEBNIS-v001.md ab oder sag, wer den "
                        "Test machen soll." if de else
                        "The script waits. Drop the result as brief/TEST-RESULT-v001.md or say who runs the test."),
              card=card["id"])
    return True


def _busy(episode: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM jobs WHERE episode = ? AND status IN ('queued', 'running')",
                         (episode,)).fetchone() is not None


def tick(force: bool = False) -> list[dict]:
    """In the worker: every episode that waits for its test result. When the result is there and no job of the episode
    runs, the Writer starts the script. Never raises for one broken episode."""
    now = time.monotonic()
    if not force and now - _last["t"] < EVERY_S:
        return []
    _last["t"] = now
    with db.conn() as c:
        keys = [r["k"] for r in c.execute("SELECT k FROM kv WHERE k LIKE ?", (WAIT_KEY + "%",))]
    out = []
    for k in keys:
        episode = k[len(WAIT_KEY):]
        try:
            project = episodes.read(episode)
        except (FileNotFoundError, ValueError):
            _clear(k)
            continue
        if project.get("steps", {}).get("script", {}).get("status") in ("done", "skipped"):
            _clear(k)
            continue
        result = showformats.test_result(episode)
        if result is None or _busy(episode):
            continue
        _clear(k)
        jid = start_script(episode, after_test=f"brief/{result.name}")
        out.append({"episode": episode, "job": jid, "result": result.name})
    return out


def _clear(k: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM kv WHERE k = ?", (k,))


__all__ = ["after_job", "message", "on_card", "propose_test_card", "start", "start_script", "tick", "wait_for_test",
           "waiting"]
