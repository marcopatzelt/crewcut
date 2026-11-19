---
name: motion
description: "Plans, builds and authors the motion graphics of a video with EffectCraft (crewcut motion) and Blender plates: the motion pass that starts from the idea and the cut and ends in a three-column motion plan (what we have that fits, what we build new for this video, what makes this video clearly better than the last one), shelf templates and custom comps written for one video, style frames, review rounds with the Critic, the quality ratchet, graphics behind the speaker with a matte. Use for: motion graphics, motion pass, motion plan, animated insert, number roll, keyword pop, lower third, kinetic type, custom animation, write a comp, new motion template, jsx, Blender plate, style frame, behind the speaker, promote to the library, make this video look better than the last one."
---

# Motion: the video first, then the shelf

The Editor is the motion director; the Designer owns the look (style frames, palettes). Motion is part of the edit
step. It runs once per video after the speaker cut and its words exist, and again in short form for each Short. Comps
are built in EffectCraft through `crewcut motion …`; anything that must catch light (heavy 3D type, a logo, a small
world) is a Blender plate. Colours, fonts, lengths and limits come from the style pack (`brand.json`
`motion_graphics`, `edit-style.json` `motion`). This skill holds the method and the craft, not values.

The level of craft to reach is the launch film in `examples/launch-film/` (17.5 s, made with these tools on one rented
GPU for 1.75 $). The channel's own bar is its best video so far (`brand/baseline.json`), and every video must beat it
in at least one named way. In a talking video the craft runs calmer: one idea per insert, the speaker carries most of
the time.

## Read first

| You want to | Read |
|---|---|
| plan the motion of a video: read order, per-beat questions, the three columns, a worked example | `references/director.md` |
| compare object craft and native animation frames with user-selected benchmarks | `references/craft.md` |
| know the bar, the report, the lessons and what the Critic sends back | `references/ratchet.md` |
| place motion calmly: shelf, lengths, density, overlay, backdrop, safe areas | `references/calm-in-video.md` |
| build an insert: beat sheet, plates, comp, render, time bases | `references/pipeline.md` |
| the commands, the `EC.*` and `CC.*` helpers, eases, the persistent engine | `references/harness.md` |
| write a template or a custom comp (header, params, formats, cues, sounds, `CC_CTX`) | `references/templates.md` |
| the engine does something odd | `references/engine-pitfalls.md` |
| make a 3D plate in Blender | `references/blender-plates.md` |
| look at your own work before the Critic does; read the review bundle | `references/review.md` |
| see bad and good side by side, with our own frames | `references/lessons.md` |
| put a graphic behind the speaker | `references/matte.md` |
| know what a piece costs and where it renders | `references/cost.md` |
| 2D and 3D inserts, the cut, music and sound | skill `edit`, skill `3d-scene` |
| check a version (the Critic, never the builder) | skill `cut-check` |

Template params: `crewcut motion template show <name>` and `templates/motion/README.md`. Do not copy key lists here.

## Video first

Never start from the template list, and never "pick a template per sentence".

1. **Read, in this order:** the idea, title and thumbnail promise, the script with the Writer's marks, the proof file;
   the speaker cut and its words; `brand/rules/motion.md` (the channel's motion lessons) and the last video's motion
   report; `brand/baseline.json` (block `motion`) and `brand/references/motion/`; only then the shelf
   (`crewcut motion library`).
2. **Per beat** (one statement, usually 1 to 3 sentences): what must the viewer understand or feel here, in one line?
   If the face and the voice already do it: nothing. Most beats get nothing. Otherwise: what picture does it in
   2 seconds, described as a thing that happens ("four jobs leave the laptop, one card lights up"), not as a
   template name. Then the column: (a) on the shelf, (b) build new, (c) a stronger version that lifts the whole video.
3. **The plan:** `crewcut motion plan <episode>` writes the skeleton of `edit/motion-plan-vNNN.md` and `.json` from
   the words and the script marks and validates the finished file. Column (c) holds 2 to 4 candidates, each tied to
   a lesson id, a reference, a gap to the baseline or a retention finding, and **at least one is chosen in every
   video** (the targeted upgrade).
4. **One card** `--kind motion-plan`: the three columns, density and budget in one line, one yes. Column (a) may be
   built while the card is open; (b) and (c) wait for the yes.
5. After the yes, each row becomes a `"kind": "motion"` entry of `edit/plan-vNNN.json` through your generator script,
   with `"beat"` and `"column"` kept, so the Critic can trace picture to purpose.

Details and a worked example: `references/director.md`.

## The eight rules

They cost a review round each in the launch film. They bind templates and custom work alike.

1. **Every transition is caused by a motion.** A click grows a circle in the next scene's ground colour; a swirl opens
   an iris; the next camera move carries the exit. Never a plain cut or cross-fade between ideas.
2. **The camera never stops.** Every hold drifts or pushes (1.5 to 3 % per second in a talking video, up to 8 % in a
   loud piece). A frozen hold of 0.5 s fails the review.
3. **Real 3D where light matters.** Logos, heavy type, objects that turn: Blender. EffectCraft does 2D and 2.5D:
   layout, type, mattes, cameras over flat layers, timing.
4. **Motion blur on what moves, never twice:** comp 180°, 16 samples; Blender plates bring their own blur.
5. **Colour comes from the content; the brand is an accent.** No hue above 30 % of the coloured pixels
   (`crewcut motion render palette`), natural content excepted.
6. **Readable at a glance:** hero text 120 to 160 px, nothing below `min_text_px` (40 px) after every scale and push.
7. **Authored paths, not physics,** for anything that must land on a frame.
8. **Compare frame by frame** (60 fps strips, the reference or the baseline) before anyone else sees it.

## Shelf or custom

- **The shelf** (`crewcut motion library`): the app's templates (`templates/motion/`), the pack's own
  (`brand/templates/motion/`, they win over the app's), and earlier custom pieces. Use a shelf piece when it shows the
  picture you described. Change its params, never its `.jsx` for one video.
- **Build new** (column b) when the idea needs a picture the shelf does not have: `crewcut motion new <episode> <id>
  --from brief.md` makes `episodes/<id>/motion/<insert-id>/` with a `comp.jsx` skeleton. A custom comp has the same
  header as a template and renders the same way (`"source"` instead of `"scene"` in the plan). Write it yourself:
  layers, keys, cameras, plates. Filling params is not enough.
- New pieces are not rationed below the density and budget limits, and never added to look busy. A video with zero
  new pieces is fine when column (c) carries the upgrade.
- **Keep what works:** a piece with a clean review that would fit a second video without a rewrite is proposed with
  `crewcut motion promote <episode> <insert-id> --name <name>` (card `--kind template`). One-offs stay in the episode.
- **One statement, one form.** Never the same number as an HTML `counter` and as `number_roll`. With the engine
  present, motion templates are the default over the HTML `counter` and `keyword`.

## Stages of a new piece

They start after the motion-plan card has its yes. Each card is one decision.

| # | Stage | Who | Output | Card |
|---|---|---|---|---|
| 1 | Brief | Editor | `brief.md` from the plan row; references picked from `brand/references/motion/` and earlier pieces | none (in the motion plan) |
| 2 | Design | Designer (look), Editor (timing) | `beats.md` in local seconds; reference timing measured at 60 fps; palette from `motion_graphics.palette` plus content colours | only a new `spend` card when the cost would pass the plan's cap |
| 3 | Style frame | Designer directs, Editor builds | one real engine frame of the strongest moment (and a half-size plate still if 3D), hue and text size checked | **`--kind style-frame`**: the frame next to the reference, both formats if needed. Nothing animated before this yes |
| 4 | Build | Editor | `comp.jsx` and plates; a 12-frame contact sheet after every stage of the comp | none |
| 5 | Review | Critic | the review bundle and a list with time stamps, back through crew talk (`--kind fix`) | none while it fails |
| 6 | Iterate | Editor, Critic | at most 3 rounds; then the Showrunner asks the user with the best version and the open points | only then |
| 7 | Final | Showrunner | the insert in the cut (`--kind preview`) with a line "new motion graphic m3" and its own 6 s loop | preview |
| 8 | Keep | Editor proposes, user decides | `crewcut motion promote` | **`--kind template`** |

## Where it renders, what it may cost

- **Comps** run on the CPU, inside the Crewcut container (`crewcut render motion <plan>`), or on the rented machine
  when the studio setting `render.location` is `rented`. A comp with the speaker's picture in it goes up only under
  the matte rule: the clip is named on an accepted card. Details: `references/cost.md`.
- **Blender plates** render on a rented RTX 4090 (or the studio's own NVIDIA card) after a `spend` card.
- **Caps per video:** $2 for a long video, $0.50 for a Short, written on the motion-plan card. Renting gets its own
  `spend` card with that cap. At the end: `crewcut compute destroy --all-ours` and `crewcut compute ledger`.

## Behind the speaker

A word behind the shoulders needs a person matte: `crewcut render matte` (the matting model runs on a rented GPU as
a separate program), an edge gate here (hair and shoulders at 200 %, no halo, no hard frame edges, the person never
shrunk), and an automatic fallback **beside** the speaker when the gate fails. Ask for it only when "behind" carries
the idea. `references/matte.md`.

## Honest limits

- This session cannot hear. Every sound is a listening list with times for the user.
- The checks measure; whether a piece looks good, only a person can say. Put frames next to the bar and say plainly
  which pieces are still below it.
- Retention data is a hint. It becomes a lesson only after the same pattern in 3 videos.
- Nobody has watched every template in every format; a template is not proven until a person has seen a sample loop.

## Sources

- The launch film in `examples/launch-film/`: the method of this skill (the eight rules, beat sheets, plates with a
  shared time base, 60 fps strips, hue checks), made with Crewcut's own tools.
- EffectCraft (MIT OR Apache-2.0), https://github.com/storytold/effectcraft: the motion engine, pinned and patched in
  `third_party/effectcraft/`. Blender (GPL-3.0-or-later), used as a tool. RobustVideoMatting (GPL-3.0),
  https://github.com/PeterL1n/RobustVideoMatting: run as its own program on the rented machine, never shipped.

No connection to or endorsement by these projects; we use their software and wrote our own method.
