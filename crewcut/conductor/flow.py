"""The order of work. The conductor (this code) holds the ten steps; crew members do the steps.

Deterministic glue lives here so it costs no tokens: starting an episode, waking the next crew member after a yes,
sending a declined card back to its author, posting short status lines as the Showrunner.
"""

from __future__ import annotations

from .. import db, episodes, events, paths
from . import prompts, queue

ONBOARDING = "_onboarding"  # pseudo-episode id for the onboarding chat and its profile card

STEP_DONE = {"topic": "idea", "title": "title", "proof": "proof", "script": "script", "final": "edit",
             "thumbnail": "thumbnail"}


def post(episode: str, text: str, author: str = "showrunner", cite: str | None = None, card: int | None = None,
         job: int | None = None, step: str | None = None, preview: str | None = None,
         facts: list[dict] | None = None, exchange: dict | None = None, relay_for: list[str] | None = None) -> int:
    if step is None and job:
        step = (db.get("jobs", job) or {}).get("step")
    if step is None and episode and not episode.startswith("_") and author != "user":
        try:
            step = episodes.read(episode).get("step")
        except (FileNotFoundError, ValueError):
            step = None
    extra = {k: v for k, v in (("preview", preview), ("facts", facts), ("exchange", exchange), ("for", relay_for))
             if v}
    scope = "channel" if episode == "_channel" else "onboarding" if episode == ONBOARDING else "episode"
    mid = db.insert("messages", at=db.now(), episode="" if scope == "channel" else episode, scope=scope,
                    author=author, text=text, cite=cite, card=card, job=job,
                    step=step, data=extra or None)
    events.emit("message", episode=episode, identity=None if author == "user" else author, text=text,
                data=message(mid))
    return mid


def message(mid: int) -> dict:
    m = db.get("messages", mid)
    out = {"id": m["id"], "at": m["at"], "episode": "_channel" if m["scope"] == "channel" else m["episode"],
           "scope": m["scope"], "job": m.get("job"), "author": m["author"], "text": m["text"],
           "cite": m.get("cite"), "card": m.get("card"), "step": m.get("step")}
    extra = m.get("data") if isinstance(m.get("data"), dict) else {}
    out.update({k: extra[k] for k in ("preview", "facts", "exchange", "for") if extra.get(k)})
    if out["scope"] == "episode" and (m["author"] == "user" or extra.get("for")):
        from . import deliver
        out["delivered"] = deliver.deliveries(mid)   # "Delivered to the Editor at 20:05" under the message
    return out


def messages(episode: str, after: int = 0, limit: int = 500) -> list[dict]:
    scope = "channel" if episode == "_channel" else "onboarding" if episode == ONBOARDING else "episode"
    with db.conn() as c:
        rs = c.execute("SELECT id FROM messages WHERE scope = ? AND episode = ? AND id > ? ORDER BY id LIMIT ?",
                       (scope, "" if scope == "channel" else episode, after, limit))
        return [message(r["id"]) for r in rs]


def _first_open_step(project: dict) -> str | None:
    for s in episodes.STEPS:
        if s.get("planned"):
            continue
        if project["steps"].get(s["id"], {}).get("status") in ("open", "working", "waiting"):
            return s["id"]
    return None


def start_step(episode: str, step: str, seed: str = "") -> int | None:
    """Give a step to its owner. Returns the job id, or None when the step needs no agent run (record). Recording and a
    cut before any recording wait while the newest script fails the style gate (crewcut/stylegate.py): the script
    step goes back to the Writer with the findings instead."""
    if step in ("record", "edit"):
        from .. import stylegate
        try:
            stylegate.guard_advance(episode, step)
        except stylegate.Blocked as e:
            return _held(episode, step, e.verdict)
    episodes.set_step(episode, step, "working")
    if step == "record":
        return start_record(episode)
    owner = prompts.owner(step)
    if owner is None:
        episodes.set_step(episode, step, "skipped")
        return None
    from .. import interview
    if step == "script" and interview.needed(episode):   # the creator's own story first (crewcut/interview.py)
        return interview.start(episode)
    return queue.add(episode, owner["id"], step, prompts.step_task(step, episode, seed))


def _held(episode: str, step: str, verdict: dict) -> int | None:
    """The newest script fails the style gate: the step does not start, the script step works again."""
    from .. import stylegate
    episodes.set_step(episode, "script", "working",
                      next_action=f"The style check fails; {step} waits until the script passes.")
    post(episode, f"{step.capitalize()} waits: {stylegate.short_line(verdict)}", step="script")
    r = stylegate.writer_round(episode, verdict, why=f"The {step} step did not start. ")
    return r.get("job")


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
    if episode == "_channel":
        from .. import channel
        return channel.user_message(text)
    mid = post(episode, text, author="user")
    if episode == ONBOARDING:
        start_onboarding(text)
        return message(mid)
    from .. import interview
    if interview.on_message(episode, text, mid):   # while it waits, every message is an interview answer
        return message(mid)
    from . import deliver
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
            "step that is working or waiting. Read the recent chat with `crewcut chat --episode " + episode + " --last 12` if you need context.\n"
            + deliver.reply_note(episode))
    queue.add(episode, "showrunner", None, task, data={"reply_to": mid})   # the reply lane: no wait behind crew work
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
    if kind == "other" and (card.get("data") or {}).get("connect") == "youtube":
        if not accepted:
            post(episode, "YouTube stays unconnected. Say \"connect YouTube\" when you want it.", card=card["id"])
            return
        from ..youtube import connect
        try:
            connect.request_setup()
        except (RuntimeError, OSError) as e:
            post(episode, f"Could not start the setup: {e}", card=card["id"], author="publisher")
            return
        db.kv_set("youtube_connect_episode", episode)
        post(episode, "Claude opens in a window on your computer and sets up the YouTube API in your Chrome. Sign in to "
             "Google there when it asks. I post the last step here.", card=card["id"], author="publisher")
        return
    if kind == "other" and (card.get("data") or {}).get("standing") == "shorts":
        if accepted:
            from .. import approvals
            approvals.grant_standing("shorts", card)
            post(episode, "Shorts are now published without asking, after the Critic's check. Say \"ask me again for "
                 "Shorts\" to switch it off.", card=card["id"])
        else:
            post(episode, "Shorts keep asking for your yes.", card=card["id"])
        return
    from . import review
    if review.on_limit_card(card):   # the Critic's last round still said back; the user decides
        return
    from .. import stylegate
    if stylegate.on_limit_card(card):   # the style check still failed after the last round; the user decides
        return
    tl = (card.get("data") or {}).get("time_limit")
    if tl:   # a run hit the time limit twice
        if accepted:
            j = db.get("jobs", tl["job"]) or {}
            queue.add(episode, card.get("identity") or j.get("identity") or "editor", card.get("step"),
                      f"The user said continue (card #{card['id']}). Your run (job {tl['job']}) stopped at the time "
                      "limit. Continue where you stopped; do not redo finished parts." +
                      ("" if tl.get("resume") else "\n\nYour task was:\n" + (j.get("task") or "")),
                      heavy=bool(j.get("heavy")),
                      data={k: v for k, v in (("resume", tl.get("resume")), ("continues", tl.get("continues")),
                                              ("time_limits", 1)) if v})
        else:
            post(episode, "It stays stopped. Say in the chat what should happen instead.", card=card["id"])
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
    if ((kind in ("motion-plan", "style-frame", "template", "baseline") or (card.get("data") or {}).get("motion_merge"))
            and _motion_card(episode, card, accepted)):
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
    if not accepted and (card.get("data") or {}).get("style_gate_refused"):
        queue.add(episode, card.get("identity") or "writer", card.get("step") or "script",
                  f"The yes on card #{card['id']} ({card['title']}) was refused: the style check fails now. "
                  f"{card.get('reason') or ''}\nFix every failed check at its line, as its fix says, run the checker "
                  "until it passes, let the Critic answer its questions again, then propose a new script card.",
                  data={**(_resume_of(card) or {}), "style_gate_round": 1})
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
        from .. import full_auto
        project = episodes.read(episode)
        if episodes.skip_switched_off(project["steps"]):   # e.g. proof, switched off after this episode began
            episodes.write(episode, project)
        nxt = (_first_open_step(project) if not full_auto.active(episode) or step not in ("edit", "title", "thumbnail")
               else next((s for s in ("edit", "title", "thumbnail", "upload") if project["steps"].get(s, {}).get("status") != "done"), None))
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
    elif kind == "mix" and (card.get("data") or {}).get("auto_revision"):
        queue.add(episode, card.get("identity") or "editor", "edit",
                  "The Critic accepted the mix under Full auto. Continue through the preview and final production cards.")


def _motion_card(episode: str, card: dict, accepted: bool) -> bool:
    """The answer to a motion card (crewcut/motion/cards.py). True when handled here; a no on a motion plan or a style
    frame goes the usual way (a new version that answers it)."""
    kind, d = card["kind"], card.get("data") or {}
    if d.get("motion_merge"):
        if accepted:
            queue.add(episode, "critic", "edit",
                      f"The user agreed to merge the motion lessons (card #{card['id']}). Merge duplicates in "
                      "brand/rules/motion.md: keep every id a plan cites, keep the evidence, keep the user's words "
                      "verbatim. Show the merged file in the chat before it replaces the old one.")
        return True
    if kind == "motion-plan" and accepted:
        mp = d.get("motion_plan") or {}
        queue.add(episode, card.get("identity") or "editor", "edit",
                  f"The user approved the motion plan (card #{card['id']}, {mp.get('file')}). Build columns (b) and "
                  f"(c) now: each new piece with `crewcut motion new {episode} <insert-id> --from <brief.md>`, then "
                  "its style frame card before anything animated. Every motion insert in the edit plan keeps its "
                  '"beat" and "column".', data=_resume_of(card))
        return True
    if kind == "style-frame" and accepted:
        from ..motion.dispatch import dispatch
        dispatch(card)
        return True
    if kind == "template":
        t = d.get("template") or {}
        post(episode, f"'{t.get('title') or t.get('name')}' is in your library now." if accepted else
             f"'{t.get('title') or t.get('name')}' stays a one-off in this episode.", card=card["id"], author="editor")
        return True
    if kind == "baseline":
        new = (d.get("new") or {}).get("episode")
        post(episode, f"The motion bar is now {new}. The next video has to beat it." if accepted else
             "The motion bar stays where it was.", card=card["id"], author="critic")
        return True
    return False


def after_job(job: dict, res) -> None:
    from .. import channel, engines
    from ..motion import dispatch
    if dispatch.after_job(job, res):
        return
    if channel.is_channel(job):
        channel.after_job(job, res)
        return
    parent = queue.get(job["parent"]) if job.get("parent") else None
    channel_child = (parent and channel.is_channel(parent)) or (job.get("data") or {}).get("origin_scope") == "channel"
    if channel_child:
        channel.child_result(job, res)
    episode = job.get("episode")
    target = episode or (ONBOARDING if job["identity"] == "brand" else None)
    if not target:
        return
    with db.conn() as c:
        said = c.execute("SELECT COUNT(*) AS n FROM messages WHERE job = ? AND episode = ?",
                         (job["id"], target)).fetchone()["n"]
    if (job.get("data") or {}).get("interview") == "ask":
        from .. import interview
        interview.after_ask_job(job, res.ok)
    if not res.ok:
        if getattr(res, "timed_out", False) and episode and _after_time_limit(job, res):
            return
        from .. import team
        name = (team.get(job["identity"]) or {}).get("name", job["identity"])
        post(target, f"{name} stopped: {engines.scrub(res.error)[:200]}. Say \"try again\" and I restart it.")
        return
    if (job["identity"] == "showrunner" or channel_child) and not said and res.text.strip():
        post(target, engines.scrub(res.text).strip()[:2000], job=job["id"], author=job["identity"])
    if episode and not channel_child:
        from . import review
        review.after_review(job, res.text)   # the Critic's verdict starts the next round or asks the user
        from .. import stylegate
        stylegate.after_writer(job, res)     # the Writer's newest script against the studio's style checker
        stylegate.after_critic(job, res)     # a review the gate asked for: check again, next round or the card
        stylegate.after_transcript_review(job, res)   # a review of what was said: the cut list goes to the edit
        if job["identity"] in ("editor", "designer"):
            from ..cut import prune
            prune.after_write(paths.episode_dir(episode))   # older intermediate renders go (the newest two stay)


def _files_since(episode: str, started: str | None, limit: int = 15) -> list[str]:
    """The episode's files written since a run started, newest first (what that run made so far)."""
    since = db.parse_time(started) or 0
    root = paths.episode_dir(episode)
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if rel.parts[0].startswith(".") or not p.is_file():
            continue
        try:
            t = p.stat().st_mtime
        except OSError:
            continue
        if t >= since:
            found.append((t, str(rel)))
    found.sort(reverse=True)
    out = [r for _, r in found[:limit]]
    return out + ([f"… and {len(found) - limit} more"] if len(found) > limit else [])


def _after_time_limit(job: dict, res) -> bool:
    """A crew member's run hit the time limit in the middle of its work. The first time it continues by itself, in the
    same session; the second time a card asks the user. True when handled here."""
    from .. import approvals, team
    if job.get("kind") != "agent" or queue.is_reply(job):
        return False
    d = job.get("data") or {}
    name = (team.get(job["identity"]) or {}).get("name", job["identity"])
    minutes = round((db.parse_time(job.get("ended")) or 0) - (db.parse_time(job.get("started")) or 0)) // 60
    files = _files_since(job["episode"], job.get("started"))
    session = res.session or d.get("session")
    resume = {"resume": {"engine": d.get("engine"), "session": session}} if session and d.get("engine") else {}
    first = d.get("continues") or job["id"]
    if int(d.get("time_limits") or 0) >= 1:   # it continued once already: the user decides
        approvals.propose(job["episode"], job.get("step"), "other",
                          f"{name} hit the time limit twice: continue once more?",
                          body=(f"Job {job['id']} stopped after {minutes} min, for the second time (first: job "
                                f"{first}). Files so far: {', '.join(files) or 'none'}.\n\nYes: it continues where it "
                                "stopped. No: it stays stopped; say in the chat what should happen instead."),
                          identity=job["identity"], job=None,
                          data={"time_limit": {"job": job["id"], "continues": first, **resume}})
        return True
    task = (f"Your last run (job {job['id']}) stopped at the time limit after {minutes} min, in the middle of the "
            "work. Continue where you stopped: do not start again and do not redo finished parts. Files so far: "
            f"{', '.join(files) or 'none written yet'}. Check what is done, then finish the rest of the task.")
    if not resume:
        task += "\n\nYour task was:\n" + job["task"]
    jid = queue.add(job["episode"], job["identity"], job.get("step"), task, heavy=bool(job.get("heavy")),
                    data={**resume, "continues": first, "time_limits": int(d.get("time_limits") or 0) + 1})
    db.update("jobs", jid, doing="Continuing after the time limit")
    post(job["episode"], f"{name} hit the time limit after {minutes} min and continues where it stopped (once; a "
         "second time I ask you).", job=jid)
    return True


def on_upload(episode: str, files: list[str]) -> int:
    from .. import interview
    if interview.waiting(episode) and interview.is_voice(files):   # a spoken answer, not a recording
        return interview.voice_files(episode, files)
    names = ", ".join(files[:6]) + (" …" if len(files) > 6 else "")
    post(episode, f"Got {len(files)} file(s): {names}. The Editor checks them now.")
    return queue.add(episode, "editor", "record",
                     f"New recordings arrived in the studio inbox for this episode: {files}. Ingest them with "
                     f"`crewcut ingest {episode} <files>`, check the sound to the end of every file and report problems "
                     f"with time stamps. When all takes are safe, mark the step: `crewcut episode step {episode} record "
                     "done`, then continue with the edit step: " + prompts.step_task("edit", episode), heavy=False)


def on_more_media(episode: str, files: list[str]) -> int:
    """Media for an episode whose recording step is over but whose video is not published yet: a second camera, a
    retake, a recorder file. The Editor hears of it once: a running Editor at its next `crewcut` call, a queued one in
    its task, else a new short run."""
    names = ", ".join(files[:6]) + (" …" if len(files) > 6 else "")
    task = (f"Additional recording arrived in the studio inbox for this episode after the record step: {files}. Ingest "
            f"it with `crewcut ingest {episode} <files>`, check its sound to the end, and decide whether it belongs in "
            "the cut (a second camera angle, a retake, separate sound). Say in one sentence what it is and what you do "
            "with it." + (" Leave the record step as it is." if episodes.read(episode).get("steps", {}).get("record", {})
                          .get("status") in ("done", "skipped") else ""))
    from . import deliver
    running = [j for j in deliver.receivers(episode) if j["identity"] == "editor"]
    if running:
        post(episode, f"Additional recording arrived: {names}. {task}", author="showrunner", relay_for=["editor"])
        return running[0]["id"]
    with db.conn() as c:
        queued = db.row(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = 'editor' AND status = 'queued' "
                                  "ORDER BY id LIMIT 1", (episode,)).fetchone())
    if queued:
        db.update("jobs", queued["id"], task=queued["task"] + "\n\n" + task)
        post(episode, f"Additional recording arrived: {names}. The Editor takes it in its next run.")
        return queued["id"]
    post(episode, f"Additional recording arrived: {names}. The Editor checks it now.")
    return queue.add(episode, "editor", "edit", task, heavy=False)


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
