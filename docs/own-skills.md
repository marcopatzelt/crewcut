# Your own skills and the channel brief

Crewcut's skills (`skills/`) are generic: they work for any channel. If you already have skills of your own, such as
a title study of your niche, a script method in your voice or a thumbnail checklist with scripts, give them to the
crew. They then write *your* way, not Crewcut's average way.

## Put them in the studio

One folder per skill in your studio, the same form Claude Code uses:

```
<studio>/skills/my-titles/SKILL.md        front matter with name and description, then the instructions
<studio>/skills/my-titles/scripts/…       checks the skill runs
<studio>/skills/my-titles/references/…    data and examples it reads
<studio>/skills/my-titles/CREWCUT.md      optional adapter note (below)
```

Name where each one applies in `<studio>/config/crewcut.toml`:

```toml
[[skills.own]]
name = "my-titles"          # the folder <studio>/skills/my-titles/
steps = ["title"]           # Crewcut steps: idea, title, proof, script, record, edit, thumbnail, blog, upload,
                            # results; "*" = every step and the channel conversation
roles = ["scout"]           # optional: only these crew members; default: whoever works on those steps
replaces = ["title"]        # optional: the Crewcut skills it overrides on content, voice and style
path = "skills/my-titles"   # optional: another folder inside the studio (a link inside the studio is fine)
```

`crewcut skills own` lists them and says when one is not usable (no `SKILL.md`, no name, a path outside the studio).
`crewcut doctor` shows the same.

## Who wins

On content, voice, language, style, the structure of deliverables, data and checks, your skill wins over Crewcut's
generic skill and over the agent's own preferences. Crewcut keeps its tools, commands, approval cards, episode files
and every safety rule: spending and publishing still need your card. A newer explicit correction from you (in chat, or
a later dated rule in `brand/rules/`) still wins over an older rule in a skill.

## Skills written for another setup

A skill can name paths or tools of the setup it was written for: an old folder layout, a script that is not in
Crewcut, a manual step in a browser. Do not rewrite the skill. Put an adapter note `CREWCUT.md` next to `SKILL.md`
that maps those names to Crewcut, for example "`00-brief/` is the episode's `brief/`" or "the image step is
`crewcut thumbnail make --way codex`". The crew reads it together with the skill. When no note covers a name, the
agent uses the matching `crewcut` command and says in one line what it mapped.

## How each engine gets them

- **Claude Code** loads them as real skills: at every job Crewcut builds a small plugin `studio` in its state folder
  whose skill folders link to yours, and passes it with `--plugin-dir`. The skills appear as `studio:<name>`; scripts
  run and write data in your own folders. The crew's agent files name the own skills of each crew member.
- **Codex** gets the text of the step's own skills and their adapter notes in its prompt (up to 120,000 characters;
  a skill beyond that is named with its path, and Codex reads the file).

Both engines are told which own skills belong to the job, where they are and the order of precedence above.

## The channel brief

Every job, on both engines, also gets a compact channel brief:

- the channel facts of your style pack (`brand/channel.json`): name, niche, audience, language, tone, topics to avoid;
- your own text in `brand/brief.md` (up to 6,000 characters; longer text is cut and the agent is told where the whole
  file is): what the channel is for, the business behind it, what worked and what did not;
- the measured results of published videos that Crewcut fetched with `crewcut youtube results` (newest first). Without
  measurements there is no results section.

The brief is evidence and direction, not an approval. Keep it short: long knowledge belongs in a skill.
