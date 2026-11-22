---
name: episode
description: "The conductor's method for one episode: the ten steps from idea to the 48-hour check, who does each step, which card the user approves, the optional step 3 (proof, off by default), and how the episode status stays true. Use when a new episode starts or the next step is unclear: \"new episode\", \"start a video\", \"next video\", \"what is next\", \"where are we\", \"episode status\", \"run the episode\". Not for the work inside one step when it is clear which skill does it."
---

# Episode

The Showrunner runs every episode with this skill. It holds the order and hands each step to the identity that owns it.
The method of each step lives in that step's skill, not here. The user's taste lives in the style pack (`brand/`),
read through `crewcut brand show`.

## 1. Start

```bash
crewcut doctor                                         # programs, templates, engine login; nothing is built
crewcut episode new "<working title>" [--source URL]   # prints the episode id, e.g. 003-local-llms
crewcut episode status <id>                            # steps, next action, open items
crewcut chat --episode <id> --last 12                  # what the user said lately
```

- Read the open items in `project.json` and the rules of the coming step (`brand/rules/<step>.md`, shown by
  `crewcut brand show`). Pick one open item this episode solves.
- Tell the user what happens next in one short message: `crewcut say --episode <id> "…"`. Keep the right column true
  with `crewcut doing --episode <id> "…" --progress 0.4`.

## 2. The ten steps

A step starts when the step before it is done. The blog (8) is planned; it may later run next to 6 and 7. Proof (3) is
optional and off by default (`[steps] proof` in `config/crewcut.toml`); a step that is off shows "switched off" and
the episode goes from title straight to script.

| # | Step | Who | Skill | Result in `episodes/<id>/` | Done when | Card |
|---|---|---|---|---|---|---|
| 1 | `idea` | Scout | `skills/idea/` | `brief/BRIEF.md` (topic, source, data) | the user said yes to the topic | `topic` |
| 2 | `title` | Scout | `skills/title/` | `brief/TITLE-vNNN.md` | the user chose a title and the thumbnail text | `title` |
| 3 | `proof` (optional, off by default) | Scout | this skill, section 3 | `brief/PROOF-vNNN.md`, raw data in `review/` | every factual claim and number for title and script has evidence | `proof` |
| 4 | `script` | Writer | `skills/script/` | `brief/SCRIPT-vNNN.md` | script check 0 errors, the user approved it | `script` |
| 5 | `record` | the user; Editor ingests | `skills/edit/` | `originals/`, `brief/ingest-*.json` | every take is saved and its sound checked to the end | none |
| 6 | `edit` | Editor, then Critic | `skills/edit/` | `edit/plan-vNNN.json`, `export/<id>-vNNN-preview.mp4`, `review/cut-check-vNNN.json` | 0 errors in the cut check, the user approved the preview, the final is built | `preview`, then `final` |
| 7 | `thumbnail` | Designer | `skills/thumbnail/` | `graphics/thumbnail/` | the user chose the image | `thumbnail` |
| 8 | `blog` | planned | | | | |
| 9 | `upload` | Publisher | `skills/upload/` | `export/upload.json` | package check 0 errors, the user said yes to publish | `publish`, every time |
| 10 | `results` | Publisher | `skills/upload/` | `review/results-48h.json` | the result is told in two sentences | none |

Set the status of each step: `crewcut episode step <id> <step> working|waiting|done|skipped`. Give work to an
identity with `crewcut job add --episode <id> --identity <who> --step <step> "<task>"`.

**Title before script.** Title and thumbnail text set what the viewer expects; the script and the test must deliver
exactly that. So step 2 always comes before step 4.

**Recording (5) and edit (6).** The rules from the recording to the cut (sound checked to the end of every file, split
files, the last full take counts, no cut into running speech, re-takes) live in `skills/edit/`. Read them before the
first file is ingested.

## 3. Facts and tests: inside the script step, or the optional step 3

By default there is no proof step and no proof card. The Writer gathers the material that serves the story while
preparing the script: facts, numbers, clips and scenes, for itself only in `work/material-vNNN.md`, with no card and
no report for the user. A test that needs a run follows the rules below; the Writer asks the Showrunner to give it to
the Scout (or, when it costs money, to the Editor).

What needs a source: concrete factual claims and numbers. What never does: emotional, style and title words ("Krass!",
"genial"). They are the user's voice, not claims; never judge them as unmeasured. The user's own title rule (a number
only when it is measured) stays. The Critic quietly checks the finished script and marks only claims that are false or
would mislead; the Writer fixes the wording. Limits go into the script only where leaving them out would mislead the
viewer, in one sentence, never as a list of caveats.

A studio that wants a separate fact check with its own card switches step 3 on (`[steps] proof = true`). Its result
is an internal fact check for the Writer, never script content.

1. **Real measurements only.** Nothing estimated, nothing invented. A number without evidence does not go into title
   or script.
2. **Visible and comparable.** Prefer a test the viewer can see side by side, plus one test that gives a number.
3. **Honest result.** If the tool does not keep its promise, say so, and send the title back to step 2.
4. **Test what the tool is built for.** A test of something it was never meant to do proves nothing.
5. **Cheap first.** Runs go through the user's own engine login. Do not benchmark other vendors' models at high cost:
   take published evaluations and fill gaps with the cheapest model that answers the question.
6. **Several tracks.** In a comparison every track gets the same fresh start, the same task and the same measurement.
   If the measurement changes, measure all tracks again and keep the old values next to the new ones. What is left out
   of one track is left out of all, with the reason in that track's log.
7. **Local pages through a local web server**, never as `file://` pages; browsers block modules there.
8. **Heavy runs** (GPU, many hours) go through the job queue. Anything that costs money needs a `spend` card; only an
   identity with `may_spend: true` rents. Ask the Editor through `crewcut job add`.

Result: one line per fact or number: the value, what it measures, and the path of its evidence in `review/`. In the
script step it stays in `work/material-vNNN.md`. Only when step 3 is on, it is `brief/PROOF-vNNN.md` with the `proof`
card.

## 4. Cards and approvals

- A skill never asks for a yes in prose. It proposes a card and waits:
  `crewcut card propose --episode <id> --step <step> --kind <kind> --title "…" --file <path> --body "<one sentence>"`,
  then `crewcut card wait <card-id>` (exit 0 accepted, 3 declined or timed out).
- A card shows one decision with one recommendation and one sentence of reason. Declining or changing is a sentence in
  the chat; read it with `crewcut chat --episode <id> --last 12` and make a new version.
- If the user said yes in words in the chat, the Showrunner may record it: `crewcut card accept <id> [--choice N]`, or
  record a no with `crewcut card decline <id> --reason "…"`. Never for `spend`, `publish` or `final` cards: those need
  the button.
- **The approved file is exactly the file the user saw** (its checksum is stored on the card). Any change after that is a
  new version and a new card.
- **Nothing unchecked goes to the user.** Every builder runs its step's check script until it shows 0 errors. The
  Critic checks every preview and thumbnail before the card. Say what nobody could check (an agent cannot hear: name
  the time stamps the user should listen to).
- **Money** needs a `spend` card with both estimates (`crewcut compute estimate`), every time.
- **Publishing** needs a `publish` card, every time. A yes for one video never carries over to the next.

## 5. Learning

- A correction from the user becomes a rule proposal, not a silent change:
  `crewcut rule propose --step <step> --rule "…" --source "<the user's words, short>" --episode <id>`.
  The user accepts it with one yes. A newer rule replaces an older one; rules do not pile up.
- Rules go to `brand/rules/<step>.md` (the user's taste) or into the skill (method for everyone, through a pull request),
  never into an identity's soul.
- At the end of the episode, set the open items in `project.json`: what this episode solved and what is new.

## Planned

- Rule review on a new model: list rules older than three episodes that were never broken and propose a deletion list.
- Step 8 (blog) and the automatic step 10 run (the 48-hour check is manual until then, see `skills/upload/`).

## Sources

- MrBeast's production handbook (public since 2024), summary: https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/
  Taken: title and thumbnail come before the shoot, and the first minute must deliver them.
