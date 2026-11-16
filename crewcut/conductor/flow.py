"""The order of work. The conductor (this code) holds the ten steps; crew members do the steps.

Deterministic glue lives here so it costs no tokens: starting an episode, waking the next crew member after a yes,
sending a declined card back to its author, posting short status lines as the Showrunner.
"""

from __future__ import annotations

from .. import db, episodes, events
from . import prompts, queue

ONBOARDING = "_onboarding"  # pseudo-episode id for the onboarding chat and its profile card

STEP_DONE = {"topic": "idea", "title": "title", "proof": "proof", "script": "script", "final": "edit",
             "thumbnail": "thumbnail"}


def post(episode: str, text: str, author: str = "showrunner", cite: str | None = None, card: int | None = None,
         job: int | None = None, step: str | None = None, preview: str | None = None,
         facts: list[dict] | None = None, exchange: dict | None = None) -> int:
    if step is None and job:
        step = (db.get("jobs", job) or {}).get("step")
    if step is None and episode and not episode.startswith("_") and author != "user":
        try:
            step = episodes.read(episode).get("step")
        except (FileNotFoundError, ValueError):
            step = None
    extra = {k: v for k, v in (("preview", preview), ("facts", facts), ("exchange", exchange)) if v}
    mid = db.insert("messages", at=db.now(), episode=episode, author=author, text=text, cite=cite, card=card, job=job,
                    step=step, data=extra or None)
    events.emit("message", episode=episode, identity=None if author == "user" else author, text=text,
                data=message(mid))
    return mid


def message(mid: int) -> dict:
    m = db.get("messages", mid)
    out = {"id": m["id"], "at": m["at"], "episode": m["episode"], "author": m["author"], "text": m["text"],
           "cite": m.get("cite"), "card": m.get("card"), "step": m.get("step")}
    extra = m.get("data") if isinstance(m.get("data"), dict) else {}
    out.update({k: extra[k] for k in ("preview", "facts", "exchange") if extra.get(k)})
    return out


def messages(episode: str, after: int = 0, limit: int = 500) -> list[dict]:
    with db.conn() as c:
        rs = c.execute("SELECT id FROM messages WHERE episode = ? AND id > ? ORDER BY id LIMIT ?", (episode, after, limit))
        return [message(r["id"]) for r in rs]


def _first_open_step(project: dict) -> str | None:
    for s in episodes.STEPS:
        if s.get("planned"):
            continue
        if project["steps"].get(s["id"], {}).get("status") in ("open", "working", "waiting"):
            return s["id"]
    return None


def start_step(episode: str, step: str, seed: str = "") -> int | None:
    """Give a step to its owner. Returns the job id, or None when the step needs no agent run (record)."""
    episodes.set_step(episode, step, "working")
    if step == "record":
        return start_record(episode)
    owner = prompts.owner(step)
    if owner is None:
        episodes.set_step(episode, step, "skipped")
        return None
    return queue.add(episode, owner["id"], step, prompts.step_task(step, episode, seed))


def start_record(episode: str) -> None:
    from .. import prompter
    url = prompter.url_for(episode)
    post(episode, "The script is ready to record. Open the teleprompter on your phone: " + url +
         " . When you are done, drop the files into this chat or into the inbox folder of the studio.")
    episodes.set_step(episode, "record", "waiting", next_action="Record, then drop the files here.")
    return None


def new_episode(text: str) -> dict:
    title = " ".join(text.split())
    title = title if len(title) <= 90 else title[:87].rstrip() + "…"
    project = episodes.create(title)
    eid = project["id"]
    post(eid, text, author="user")
    jid = start_step(eid, "idea", seed=text)
    post(eid, "Scout is looking for the data behind this idea. You get a topic card when it is ready.", job=jid)
    return project


def user_message(episode: str, text: str) -> dict:
    mid = post(episode, text, author="user")
    if episode == ONBOARDING:
        start_onboarding(text)
        return message(mid)
    open_cards = [c for c in _cards(episode) if c["status"] == "open"]
    cards_txt = "; ".join(f"#{c['id']} {c['kind']} '{c['title']}' by {c['identity']}" for c in open_cards) or "none"
    task = (f"The user wrote in the chat of episode {episode}: {text!r}\n"
            f"Open cards: {cards_txt}.\n"
            "Decide what this means and act: answer in one or two sentences with `crewcut say`. If it changes an open "
            "card's subject, decline that card with `crewcut card decline <id> --reason \"…\"` (the author makes a new "
            "version) or, if the user clearly said yes or picked an option, accept it with `crewcut card accept <id> "
            "[--choice N]` (never for spend, publish or final cards: those need the button). If it is a correction "
            "that should hold for future videos, propose a rule. If it asks for work, assign it with `crewcut job "
            "add`; the conductor already starts the owner of the next step after every yes, so never add a job for a "
            "step that is working or waiting. Read the recent chat with `crewcut chat --episode " + episode + " --last 12` if you need context.")
    queue.add(episode, "showrunner", None, task)
    return message(mid)


def _cards(episode: str) -> list[dict]:
    from .. import approvals
    return approvals.list_cards(episode=episode)


def _resume_of(card: dict) -> dict | None:
    """Continue the session of the crew member who asked, so it keeps its context (same engine only)."""
    if not card.get("job"):
        return None
    j = db.get("jobs", card["job"]) or {}
    d = j.get("data") or {}
    if d.get("session") and d.get("engine"):
        return {"resume": {"engine": d["engine"], "session": d["session"]}}
    return None


def on_card_decided(card: dict) -> None:
    episode, kind = card.get("episode"), card.get("kind")
    accepted = card["status"] == "accepted"
    if not episode:
        return
    if episode == ONBOARDING:
        if kind == "profile" and accepted:
            db.kv_set("onboarded", "1")
            post(ONBOARDING, "Your style pack is set. Every new episode uses it. To change something, say it here.")
        elif not accepted:
            queue.add(None, "brand", None, f"The user wants changes to the profile (card #{card['id']}): "
                      f"{card.get('reason') or 'see the latest chat messages in _onboarding'}. Change the pack, make a "
                      "new preview, then a new profile card.")
        return
    if not accepted and kind == "spend":
        # "Render on this machine": local is fine for this episode; the crew carries on locally and does not ask again
        try:
            from ..compute.estimate import local_is_fine
            local_is_fine(episode)
        except Exception:  # noqa: BLE001 - the compute part is optional
            pass
        who = card.get("identity") or "editor"
        queue.add(episode, who, card.get("step"),
                  f"The user chose this machine for card #{card['id']} ({card['title']}). Local is fine for this "
                  "episode: carry on with the local way (`--local`), and do not ask about renting again in this "
                  f"episode. Their words: {card.get('reason') or 'none'}.", data=_resume_of(card))
        post(episode, "Rendering on this machine. No more GPU questions in this episode.", card=card["id"])
        return
    if not accepted:
        who = card.get("identity") or (prompts.owner(card["step"]) or {}).get("id") or "showrunner"
        queue.add(episode, who, card.get("step"),
                  f"The user did not accept card #{card['id']} ({card['title']}). Their words: "
                  f"{card.get('reason') or 'see the latest chat messages'}. Make a new version that answers this, run "
                  "your checks, and propose a new card.", data=_resume_of(card))
        return
    choice = card.get("choice")
    picked = card["options"][choice] if card.get("options") and choice is not None else None
    if kind in STEP_DONE:
        step = STEP_DONE[kind]
        if kind == "title" and picked:
            p = episodes.read(episode)
            p["title"] = picked
            episodes.write(episode, p)
        episodes.set_step(episode, step, "done")
        post(episode, f"{card['title']} · approved" + (f" · {picked}" if picked else ""), card=card["id"])
        nxt = _first_open_step(episodes.read(episode))
        if nxt:
            start_step(episode, nxt)
        else:
            off = [k for k, v in episodes.read(episode)["steps"].items() if v.get("status") == "skipped"]
            post(episode, "Every step that is switched on is done." +
                 (f" Switched off for this episode: {', '.join(off)}." if off else ""))
    elif kind == "preview":
        queue.add(episode, "editor", "edit",
                  f"The user approved the preview (card #{card['id']}, file {card.get('file')}). Build the final version "
                  "from the same plan at final quality, run the checks, then one card of kind final with the file.",
                  data=_resume_of(card))
    elif kind == "publish":
        queue.add(episode, "publisher", "upload",
                  f"The user approved publishing (card #{card['id']}). Upload exactly what the card showed with "
                  "`crewcut youtube upload`, then post the link and mark the step: `crewcut episode step "
                  f"{episode} upload done`.")
    elif kind == "spend":
        who = card.get("identity") or "editor"
        queue.add(episode, who, card.get("step"),
                  f"The spend card #{card['id']} was approved (budget ${(card.get('data') or {}).get('budget_usd')}). "
                  "Continue the work you paused, inside that budget.", data=_resume_of(card))
    elif kind == "rule":
        d = card.get("data") or {}
        post(episode, f"Rule added for {d.get('step')}: {d.get('rule')}", card=card["id"])


def after_job(job: dict, res) -> None:
    episode = job.get("episode")
    target = episode or (ONBOARDING if job["identity"] == "brand" else None)
    if not target:
        return
    with db.conn() as c:
        said = c.execute("SELECT COUNT(*) AS n FROM messages WHERE job = ?", (job["id"],)).fetchone()["n"]
    if not res.ok:
        from .. import team
        name = (team.get(job["identity"]) or {}).get("name", job["identity"])
        post(target, f"{name} stopped: {res.error[:200]}. Say \"try again\" and I restart it.")
        return
    if job["identity"] == "showrunner" and not said and res.text.strip():
        post(target, res.text.strip()[:2000], job=job["id"])


def on_upload(episode: str, files: list[str]) -> int:
    names = ", ".join(files[:6]) + (" …" if len(files) > 6 else "")
    post(episode, f"Got {len(files)} file(s): {names}. The Editor checks them now.")
    return queue.add(episode, "editor", "record",
                     f"New recordings arrived in the studio inbox for this episode: {files}. Ingest them with "
                     f"`crewcut ingest {episode} <files>`, check the sound to the end of every file and report problems "
                     f"with time stamps. When all takes are safe, mark the step: `crewcut episode step {episode} record "
                     "done`, then continue with the edit step: " + prompts.step_task("edit", episode), heavy=False)


def start_onboarding(text: str) -> int:
    import re
    links = re.findall(r"https?://[^\s<>\"']+", text)
    task = ("Onboarding. Follow the onboarding skill. The user pasted: " + repr(text) + ". "
            + (f"Fetch the facts first: `crewcut onboard {' '.join(links)}`. " if links else
               "There are no links: if the user wants to skip, keep the neutral pack and go straight to the profile "
               "card; otherwise ask at most one question, 'What is your channel about?', with `crewcut say "
               f"--episode {ONBOARDING}` and stop. ")
            + "Then write the pack in the studio's brand/ folder with a source for every value, run `crewcut brand "
            "check` until it is clean, make the 10-second sample with `crewcut brand preview --out brand/preview.mp4`, "
            "and propose one card: `crewcut card propose --episode " + ONBOARDING + " --step onboarding --kind profile "
            "--title \"Your style pack\" --file brand/preview.mp4 --body \"<the style in five sentences>\"`.")
    from .. import engines
    eng = engines.current()
    post(ONBOARDING, "Brand is reading your links. This takes a few minutes; you can watch it on the right. "
         f"The crew runs on {eng.label}" + (" (beta)" if eng.beta else "") + " with your own subscription; "
         + ("say \"use Codex\" if you prefer Codex (beta)." if eng.name == "claude" else
            "say \"use Claude\" to switch back."))
    return queue.add(None, "brand", None, task)
