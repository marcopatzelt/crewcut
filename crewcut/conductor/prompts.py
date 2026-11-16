"""What a crew member is told on every run: who it is, the house rules of the app, and where the episode stands."""

from __future__ import annotations

import json

from .. import brand, episodes, paths, team

HOUSE_RULES = """\
You work inside Crewcut, a studio where a crew of agents makes a YouTube video with one human, the user.
The user records the video and gives a few yes answers. Everything else is the crew's work.

How you talk and act:
- Talk to the user only with `crewcut say --episode {episode} "<text>"`: short, plain sentences, no exclamation marks.
  When you apply a rule from a named source, you may add one short cite line with `--cite "<method> (<source>)"`.
  Never claim that a creator endorses Crewcut.
- Say what you are doing right now with `crewcut doing --episode {episode} "<one line>" [--progress 0.4]`, at the start
  and whenever the work changes. Nothing runs out of sight.
- Ask for a decision only with a card: `crewcut card propose --episode {episode} --step <step> --kind <kind> --title "…"
  [--file <path in the episode>] [--body "<one sentence of reason>"] [--option "…"]`, then stop and end your turn. The
  conductor wakes the right crew member when the user answers. Never ask questions in prose.
- A correction from the user that should hold for future videos becomes a rule proposal:
  `crewcut rule propose --step <step> --rule "…" --source "user, <their words in a few words>"`.
- Never show the user anything unchecked: run the checks of your skill first and fix every error.
- Name what you could not check (you cannot hear audio; give time stamps the user should listen to).
- Spending money and publishing need the identity right and a card. The `crewcut` command enforces both; never try to
  work around it.
- Taste comes from the style pack (`crewcut brand show`), never from your own preferences.
- Work in the episode folder you start in. Never touch files outside the studio folder and the episode.
- Secrets live in environment variables. Never print, write or send them anywhere.
- The engine: Crewcut runs on Claude Code (default) or Codex (beta), both on the user's own subscription. If the user
  asks to switch ("use Codex", "back to Claude"), run `crewcut engine use <claude|codex>`; if it says the login is
  missing, run `crewcut engine login <name> --episode {episode}` (the link and code appear in the chat by themselves).
"""


def system_prompt(identity: dict, episode: str | None, step: str | None, with_identity: bool = True) -> str:
    """The job context. With a real engine agent (`--agent crewcut:<id>`) the identity's soul already is the agent's
    system prompt, so it is left out here (with_identity=False) and only what changes per job is appended."""
    ident = (f"You are {identity.get('name')}, {identity.get('role')}\n\n"
             f"How you work:\n{identity.get('soul', '').strip()}\n") if with_identity else ""
    rights = (f"Your rights: may spend money: {'yes' if identity.get('may_spend') else 'no'}; "
              f"may publish: {'yes' if identity.get('may_publish') else 'no'}.\n")
    skills = identity.get("skills") or []
    skill_line = ""
    if skills:
        skill_paths = ", ".join(f"{paths.skills_dir() / s / 'SKILL.md'}" for s in skills)
        skill_line = f"Your skills (read the one for your step before you start): {skill_paths}\n"
    ctx = ""
    if episode:
        try:
            p = episodes.read(episode)
            ctx = ("\nThe episode right now (project.json, shortened):\n" +
                   json.dumps({k: p.get(k) for k in ("id", "title", "format", "fps", "step", "steps", "next_action",
                                                     "open_items")}, ensure_ascii=False)[:3000] + "\n")
        except FileNotFoundError:
            ctx = f"\nThe episode {episode} does not exist yet.\n"
    pack = brand.load()
    pack_line = (f"Style pack: {'the neutral default (no user brand yet)' if pack.is_neutral else 'the user brand'}, "
                 f"language {pack.value('channel.language', 'en')}, format {pack.value('edit_style.format')}.\n")
    step_line = f"Your step now: {step}.\n" if step else ""
    from .. import crewtalk
    if episode and crewtalk.settings()["enabled"]:
        step_line += (
            "Crew talk is on. Read the file first. Ask a crew member only what the files do not answer, in one message, "
            "and say which file it is about: `crewcut say --to <crew member> --about <file> --kind question|fix|notice "
            "\"…\"` (skill `crew-talk`). It reaches a crew member whether it runs or not. A message is never an "
            "approval and never a new assignment; results stay files.\n")
        if identity.get("id") == "critic":
            step_line += ("Bundle all findings of one version into ONE message to the crew member who built it "
                          "(`--kind fix`).\n")
    return "\n".join([ident, rights, skill_line, HOUSE_RULES.format(episode=episode or "<id>"), pack_line, step_line, ctx])


STEP_TASKS = {
    "idea": "Find the topic of this episode with the idea skill. Start from the user's sentence: {seed}. End with one "
            "card of kind topic (the topic, the data reason, the gap) and stop.",
    "title": "Write title and thumbnail text candidates with the title skill, before any script exists. End with one "
             "card of kind title: the candidates as options, your recommendation in the body. Then stop.",
    "proof": "Plan and run the proof for the title's promise (the test in the episode skill). Real measurements only. "
             "Write brief/PROOF-vNNN.md with every number and its evidence path, then one card of kind proof.",
    "script": "Write the script with the script skill in the user's voice (voice.md). Run its check until it has no "
              "errors, then one card of kind script with the file.",
    "record": "The script is approved. Tell the user in one or two sentences that recording can start, with the "
              "teleprompter link from `crewcut prompter {episode}`, and where to drop the files (the chat, or the "
              "studio inbox folder). Then stop; the Editor starts when files arrive.",
    "edit": "Build the video with the edit skill: ingest and check the files, transcribe, speaker cut, edit plan, 2D and "
            "3D inserts (estimate first; rented GPU only after a spend card), sound, assembly. Then ask the Critic for a "
            "check with `crewcut job add --identity critic --step edit …`. Only after a clean check: one card of kind "
            "preview with the preview file.",
    "thumbnail": "Make the thumbnail with the thumbnail skill: complete prompt, reference photo from the pack, 2 to 3 "
                 "variants with `crewcut thumbnail make`, check each, then one card of kind thumbnail.",
    "upload": "Prepare the upload with the upload skill: package check, title, description, tags, chapters, captions, "
              "thumbnail, schedule. Then one card of kind publish that shows exactly what goes out. Upload only after "
              "the yes, with `crewcut youtube upload`.",
}


def step_task(step: str, episode: str, seed: str = "") -> str:
    t = STEP_TASKS.get(step)
    if not t:
        return f"Work on step {step} of episode {episode}."
    return t.format(seed=json.dumps(seed or "(no sentence)", ensure_ascii=False), episode=episode)


def owner(step: str) -> dict | None:
    info = episodes.step_info(step)
    return team.get(info["owner"]) if info.get("owner") else None
