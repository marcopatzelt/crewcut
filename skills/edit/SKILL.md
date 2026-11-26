---
name: edit
description: "Builds a video version from the user's recording: the speaker cut, then one edit plan with all inserts (2D scenes, 3D scenes, motion graphics, recordings, keywords), sound and music, built with one command (crewcut render). Use for: edit the video, build the cut, speaker cut, rough cut, insert, b-roll, 2D scene, 3D insert, motion insert, counter, keyword, music bed, sound, assemble, render the preview, new plan version, short from the long video."
---

# Edit: one plan, one command

The Editor turns the user's recording into a video in two parts. First the **speaker cut**: the best takes, cut at
pauses, graded. Then the **edit plan** (`edit/plan-vNNN.json`): every insert, its words and cues, the sound. Motion
graphics come from their own pass in between (skill `motion`): the video first, then the shelf. The
workbench `crewcut render` builds the plan. Nothing in this skill holds a colour, a font or a level: those come from
the style pack (`crewcut brand show`). Taste lives in `brand/rules/edit.md` and `brand/rules/cut.md`.

## Read first

| You want to | Read |
|---|---|
| cut the recording into the speaker cut | `references/record-to-cut.md` (sound to the end, split files, last full take, double starts, cuts at pauses, re-shoot, grade, show and lock) |
| write the plan, choose or build a scene, show a recording | `references/plan-and-scenes.md` (word anchors, count the mix, form per statement, cues, new 2D scene, reuse, recordings) |
| make music, set levels, or rent a GPU | `references/sound-and-gpu.md` (music along the story, chosen by measurement, levels, GPU pitfalls, the cost card) |
| build a 3D scene | skill `3d-scene` |
| plan and build motion graphics: the motion pass, shelf templates, comps made for this video | skill `motion` |
| check before showing | skill `cut-check` (run by the Critic, never by you) |

Scene names and their data keys: `templates/2d/BLOCKS.md`, `templates/3d/README.md` and, for motion,
`templates/motion/README.md` (`crewcut motion template show <name>`). Do not copy key lists here.

## How a version is made

1. **Speaker cut** (`references/record-to-cut.md`): `crewcut ingest`, `crewcut transcribe`, `crewcut cut …`. Run
   `python3 skills/cut-check/scripts/cut_check.py <decisions>` on it and fix every ERROR before you build on it.
2. **Words of the final cut**: `crewcut transcribe audio/voice-vNNN.wav` → `work/words-vNNN.json`. All plan times
   come from these words.
3. **Count the mix, then list the spots** (section below). Send the list as a card before the big render:
   `crewcut card propose --episode $CREWCUT_EPISODE --step edit --kind mix --title "Inserts for v002" --file edit/mix-v002.md`.
   Keep building while it is open; the card is a look, not a gate. The mix list holds clips and HTML scenes; motion
   has its own plan (step 4).
4. **The motion pass** (skill `motion`): per beat, what must the viewer understand, then which picture does it, and
   only then the shelf. Output: the three-column motion plan (`edit/motion-plan-vNNN.md`, from
   `crewcut motion plan <episode>`) with at least one chosen upgrade over the last video, and its `motion-plan` card.
5. **Write the plan** with a small generator script (`edit/make_plan.py`) that sets every time from a word anchor.
   Never type seconds by hand. Schema: `docs/architecture.md`, "Edit plan". Values left `null` come from the pack.
   Motion rows of the approved motion plan become `"kind": "motion"` entries with their `beat` and `column`.
6. `crewcut render plan edit/plan-vNNN.json`: lists every insert with frames and cues. Read it. An insert of half a
   second is a wrong anchor.
7. `crewcut render 2d edit/plan-vNNN.json`: 2D inserts, locally.
8. 3D: `crewcut render probe edit/plan-vNNN.json <id>` gives one still frame at half size. Look at it next to the
   reference before anything else (skill `3d-scene`). Then the cost estimate and the card (section "Rented GPU or
   local"), then `crewcut render 3d edit/plan-vNNN.json --rented --gpus N` or `--local`.
9. Motion: `crewcut render motion edit/plan-vNNN.json` (plates first, after their spend card). A piece made for this
   video goes through its style frame and review rounds first (skill `motion`).
10. `crewcut render cut edit/plan-vNNN.json`: assembly with the music bed, hits, typing, gaps, ducking and the loudness
   target from the pack. The output is **unchecked**. Tell the Showrunner: "built, unchecked, do not show".
11. Hand the version to the Critic
   (`crewcut job add --episode $CREWCUT_EPISODE --identity critic --step edit "check plan-vNNN"`). Only after both
   checks show 0 ERROR: the preview goes to `export/`, the Showrunner shows it as a card with the file
   (`crewcut card propose … --kind preview --file export/<id>-vNNN-preview.mp4`), and right after showing:
   `crewcut render shown edit/plan-vNNN.json`. From then on every change is a new plan version, even for two frames.

A changed text or number: change the plan (new version), run steps 6 to 11. Only changed inserts render again.
`crewcut render all <plan>` runs 2d, 3d, motion and cut in one go when nothing needs a look in between.

## Mix first, then the plan

These hold for every plan, before one frame is rendered. The limits come from `edit-style.json`.

1. **Symbol before text.** Every insert first shows something that happens. A text card (`headline`, `post`) only
   where the viewer must read a real source: at most `text_cards_max` sources and at most `text_share_max` of the
   full-screen inserts. `keyword` only for a number or a name, at most `keywords_max`, each at most
   `keyword_max_words` words. Count by kind before you render; the style check counts again.
2. **Symbolic means 2D and 3D.** 3D where an object with an action is the idea. Drawn 2D for processes, amounts, ways
   and comparisons: shapes that build, move or change. Per spot, pick what a viewer understands in 2 seconds. A scene
   holds at most one word or one number, on the spoken word.
3. **The bar is the reference, not "it renders".** Compare with `baseline.json` and `brand/references/`. Rented GPUs
   are for quality: full resolution, enough samples, soft shadows, clean edges. 2D is motion design, not a slide:
   parts build one after the other, the camera drifts a little, transitions are soft.
4. **Check every scene before the cut.** A still frame and a strip of 5 frames next to the reference. If it looks like
   a slide deck, clip art or a template, throw it away and build it again. Few very good scenes beat many average ones;
   reuse a scene 2 to 4 times with another word or state.
5. **Real material, without being asked.** A post, an announcement or a third-party result goes into the picture: the
   post as a card with a mark on the spoken word, a third-party video short on a card with its source visible. Never an
   invented screenshot, never a company logo you made up.
6. **Music belongs to the story** (`references/sound-and-gpu.md`). Instruments only, quiet under the voice, with a
   source and rights note.
7. **Compute fast, never idle.** While machines load, keep working locally (plan, 2D, cut). Every remote step has a time
   limit. At the end prove that no machine runs.
8. **Show the list before the big render** (step 3): time, kind, one line of what one sees, the number of text cards.

## Scenes

2D scenes (HTML, rendered by Chromium, styled by the brand tokens), 3D scenes (Blender by code, `templates/3d/`) and
motion graphics (EffectCraft comps, `templates/motion/`, skill `motion`). Data keys: `templates/2d/BLOCKS.md`,
`templates/3d/README.md`, `templates/motion/README.md`. Which form for which statement:
`references/plan-and-scenes.md`, section 3.

| Kind | Scenes |
|---|---|
| 2D numbers and amounts | `counter`, `bars`, `grid`, `wave` |
| 2D sources and real material | `headline`, `post`, `clip-card`, `cards`, `swap` |
| 2D drawn ideas | `area`, `flow`, `untangle` |
| 2D over the speaker (transparent) | `keyword` |
| 3D | `object-word`, `row`, `grid3d`, `stack`, `slide`, `box`, `scale` (shared kit `templates/3d/stage.py`) |
| motion | `"kind": "motion"`: a shelf template as `scene` (`crewcut motion library`) or a comp made for this video as `source`; full frame or overlay over the speaker. Chosen in the motion pass, never per sentence from the list (skill `motion`) |
| recording | `"kind": "clip"` with `file`, `at`, `speed`: a finished recording full screen |

One statement gets one form: never the same number as `counter` and as a motion `number_roll`. With the motion
engine present, motion templates are the default for numbers and keywords.

The neutral pack ships few, general 3D scenes. A user's own scenes go to `brand/templates/` (never edit the app's
templates). A new scene gets a line in `BLOCKS.md` or `templates/3d/README.md` and is not tested until a frame of it
has been looked at.

## Mix rules (values from the pack)

- 3D share: about `graphics_mix.3d` of the inserts; 2D carries the numbers; the speaker is on screen in between.
- Cut on the word, not on the beat. The word in the picture lands 0 to 3 frames before it is spoken.
- Split long speaker stretches with `"speaker": [{"at": s, "zoom": z}]` (zoom from `zoom_base` to `zoom_punch`, never
  over `zoom_max`).
- The speaker is never shorter than `speaker_min_seconds` between two full-screen parts, and at least
  `speaker_open_close_seconds` at the start and the end.
- Sound: music bed at `music_db` with `duck`, a hit only at strong spots, typing under counters, a short gap in the
  music before the most important number. Loudness `loudness_lufs`, true peak at most `true_peak_db`. When the
  channel's rules ask for music only in the opening, a dry Short or effects only on picture events, set
  `sound.music_until`, `sound.bed: "dry"` or `sound.events: "auto"` (`references/sound-and-gpu.md`, section B2).
- Pauses: the cut keeps the opening dense and natural pauses after it (`references/record-to-cut.md`). Put the
  Writer's `[[first content | ...]]` into the selects as `first_content` (the select where it starts) and its
  `[[key sentence | ...]]` as `pause_before` (1.5 to 3 s) on that sentence's select, when the rules ask for it.
- Sources honest: a headline card names the real source.
- Never claim a viewing or listening check that did not happen. This session cannot hear: name the times.

When you apply a rule that comes from a named source, you may say so in one line, for example
`crewcut say --episode $CREWCUT_EPISODE --cite "fast cutting and keyword captions after Alex Hormozi's editing style" "…"`.

## Rented GPU or local

- 3D frames render in Blender Cycles. Local means the container's CPU: fine for probes at half size and very short
  scenes. Anything longer goes to a rented GPU.
- **Cost first.** `crewcut compute estimate --kind blender --frames N [--local-sec-per-frame S]` prints time and money
  for local and rented. Put the estimate on a card (`--kind spend`, title with the amount), wait with
  `crewcut card wait <id>`. Exit 3 means no: render locally or drop the scene. Only an identity with `may_spend: true`
  rents (the Editor).
- Always: still frames at half size first, then the animation.
- Only scene code and fonts go to a rented machine. Never footage, the voice, keys or private data.
- At the end: `crewcut compute destroy --all-ours`, then `crewcut compute ledger --episode ID`; the report to the user
  holds the spend and the proof that no machine runs. Also after a failure.
- Pitfalls and what the tools do about them: `references/sound-and-gpu.md`, section B.

## Honest limits

- The agent cannot hear. Every music and voice judgement is a listening list with times for the user.
- Detection of a word rest, a double start or a level jump finds candidates, not certainties.
- The style check measures limits; whether a scene looks good only a person can say. Put the frames next to the
  reference and say plainly which scenes are still below it.

## Planned

- Re-timing 3D renders when word times shift by a few frames, so they are not rendered again.
- Generated music on a rented GPU through `crewcut compute` (the studio did it by hand; see `references/sound-and-gpu.md`).
- Web page recordings as a render step (Chromium is in the container; no command yet).
- Comparison sheets (scene frame next to the reference) as one command.
- A self-test on the demo episode in `examples/demo/` once it exists.

## Sources

No connection to or endorsement by these people; we took ideas and wrote our own summary.

- Alex Hormozi (editing and caption style made by his editor Ryan Magin), https://www.youtube.com/@AlexHormozi: fast
  cutting on the word and short word captions; here reduced to keyword captions.
- fern (YouTube channel), https://www.youtube.com/@fern-tv: inspiration for the 3D clay look only. No values from it.
