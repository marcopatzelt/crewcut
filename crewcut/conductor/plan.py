"""The plan of a format episode: the Scout picks the show format, the Writer writes the full script, the style gate runs.

New Episode with the format library not empty (crewcut/showformats.py):
1. the Scout's plan job (step idea, data `plan`): classify the input, pick the format and the topic type
   (`crewcut formats choose`), write brief/FORMAT-v001.md, BRIEF.md, TESTPLAN-v001.md, PACKAGING-v001.md;
2. when it ends, the conductor posts the pick and its reason in the chat, marks the idea step done and gives the
   script step to the Writer (data `format_script`): a full script brief/SCRIPT-v001.md from the format's template;
3. the style gate runs on it unchanged (stylegate.after_writer); when it passes and the format has a cue template, the
   Writer derives the cue sheet (prompts.cue_sheet_task), the gate checks that too, then the script card;
4. after the script card the episode goes on with its normal steps (the title step starts from PACKAGING-v001.md).
"""

from __future__ import annotations

from .. import episodes, showformats
from . import prompts, queue


def start(episode: str, seed: str) -> int:
    jid = queue.add(episode, "scout", "idea", prompts.plan_task(episode, seed), data={"plan": 1})
    episodes.set_step(episode, "idea", "working",
                      next_action="Scout reads the input and picks the format.")
    return jid


def message(choice: dict) -> str:
    f = showformats.get(choice.get("format")) or {}
    head = f"Format: {choice.get('name') or choice.get('format')}"
    meta = [x for x in (choice.get("format"), choice.get("length") or f.get("length"),
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
    if project.get("show_format") != choice["format"]:
        try:
            project = showformats.choose(episode, choice["format"],
                                         topic_type=choice.get("topic_type") if choice.get("topic_type")
                                         in showformats.TOPIC_TYPES else None)
        except ValueError as e:
            flow.post(episode, f"The format pick could not be recorded: {e}", job=job["id"])
            return True
    flow.post(episode, message(choice), author="scout", job=job["id"], preview=choice["file"])
    episodes.set_step(episode, "idea", "done")
    episodes.set_step(episode, "script", "working", next_action="The Writer writes the full script from the format.")
    queue.add(episode, "writer", "script", prompts.format_script_task(episode), data={"format_script": 1})
    flow.post(episode, "The Writer writes the full script now. The style check runs on it before you see it.",
              step="script")
    return True


__all__ = ["after_job", "message", "start"]
