---
name: crew-talk
description: "How crew members message each other directly when crew talk is on: only to fix, to ask the author of a file, or to note a changed file; one message, a file named, within the limits. Use when you want to tell or ask another crew member something, when the Critic has findings for the builder, or when you changed a file others already read. Not for approvals, money or new assignments."
---

# Crew talk

Files are the default: results, plans, reports and measurements are files in the episode folder, and the next crew
member reads them. A message is for what a file does not answer. Crew talk is off unless the studio switched it on
(`crewcut crew talk status`).

## The three cases

| Case | From, to | Example |
|---|---|---|
| `fix` | the Critic to the crew member who built the version | "Loudness is fine. The pause at 2:31 is 0.8 s too long. Graphic 4 lands 6 frames after the word." |
| `question` | anyone to the author of a file they use | "Does '$900 laptop' mean the price or the build cost?" |
| `notice` | the author of a changed file to those who read it | "Title changed after the user's note. New file: brief/TITLE-v003.md." |

```bash
crewcut say --to editor --about review/cut-check-v001.json --kind fix "Three findings, all in the report: …"
crewcut say --to critic --reply-to 12 --about work/edit-decisions-v002.json --expects none "Fixed in cut v2."
```

It reaches a crew member whether it is running or not: a running one is reached through Claude Code's own messaging
(`crewcut say` tells you the session name to use with SendMessage), otherwise its last session continues with your
message. Notices are kept and handed over at the recipient's next start.

## Rules

1. Read the file first. Ask only what the files do not answer, in **one** message, and name the file (`--about`) or a
   time stamp.
2. The Critic bundles **all** findings of one version into one `fix` message.
3. At most 2 rounds per topic and 3 fix rounds per piece of work; at most 20 messages per episode. At a limit, write your
   view to the file and tell the Showrunner, who decides or asks the user with a card.
4. No thanks, no "understood". When no answer is needed, send `--expects none`, and do not answer such messages.
5. A message is never an approval, never a new assignment and never money. Approvals are cards; work is given by the
   Showrunner; money needs a spend card.

## Planned

Crew talk with Codex (its session resume is untested); measured defaults (see `docs/crew-talk.md`).
