# Plan and scenes: steps, rules, examples

Paths are relative to the episode folder. The plan schema is in `docs/architecture.md`, "Edit plan".

## 1. The plan comes from word anchors, never from typed seconds

- Write one small generator per episode, `edit/make_plan.py`, that reads `work/words-vNNN.json` and writes
  `edit/plan-vNNN.json`. Every time is "start of word X minus 2 frames". Cues name the spoken word:
  `"cues": {"value": {"word": "thirty"}}`; the workbench computes the frames.
- Why: the speaker cut changes several times, and every change moves all times. With anchors you run the generator
  again and are done.
- Traps: (1) common words ("and", "the", "I") hit the wrong occurrence. Use the word plus the next word, or a start time
  (`{"word": "and", "after": 41.0}`). After every run read `crewcut render plan <plan>`: an insert of half a second is
  a wrong anchor. (2) The transcriber spells names differently each time. Anchor on the word before the name.
- 3D is expensive. When word times move by a few frames, the scene's data changes and it would render again. Keep the
  3D length and cue position from the previous plan when the spoken word only moved a little (planned as a tool; until
  then do it in the generator).

## 2. Count the mix first

Before one frame is rendered:

1. Write the list of all spots: time, sentence, what one sees. One line per spot (`edit/mix-vNNN.md`).
2. Ask per spot: what HAPPENS in the picture? If only a name or a text stands there, it is not a scene yet. Pick a form
   from the table below.
3. Count: text cards against `text_cards_max` and `text_share_max`, keywords against `keywords_max` and
   `keyword_max_words` (all in `edit-style.json`). `style_check.py` counts the same (`text-share`, `text-sources`,
   `keyword-count`, `keyword-words`).
4. Show real material instead of symbols: the real concept image, the real model page, the real result in motion.
   Tiles with icons name things instead of showing them.
5. Send the list as a card, then render.

## 3. Which form for which statement

| Statement | Form | Scene | Data that must be real |
|---|---|---|---|
| Someone posted something | the post as a card, a mark on the spoken word | `post` | text word for word, name, handle, date, numbers from the post's metadata |
| Show a third-party video | clip on a card with a source label | `clip-card` | the clip, never full screen, never zoomed |
| A web page | a real recording full screen | `kind: clip` | public page, no login, nothing clicked |
| Something is replaced | two real page crops: one is struck and tips away, the new one drops in, a stamp | `swap` | crops from real recordings |
| A becomes B | two cards with an arrow; the second can be a running clip | `cards` | images or clips from the project |
| Music or sound | waveform from measured values of the real piece | `wave` | peak values of the real file |
| Amount over time | bars from real values, the number snaps on the word | `bars` | the bars add up to the spoken number |
| One number | rolling counter | `counter` | |
| Many of the same, one stands out | grid of symbols, the last one in the accent | `grid`, 3D `grid3d` | |
| A place or a region | map as a flat area with a label | `area` | |
| Messy becomes clear | a tangled line becomes straight lines | `untangle` | |
| A process (only when there is no real material) | tiles with a moving dot | `flow` | |
| Cost per time, a thing with an action | one 3D object that does something, one word | 3D `object-word` | |
| One becomes several | 3D row, the word changes | 3D `row` | |
| Something is loaded and started | blocks slide into the object | 3D `slide` | |
| Many rules or documents | sheets fall into a stack | 3D `stack` | |
| Locked in, set free | a ball in a box that opens | 3D `box` | |
| A beats B | a balance, one side sinks | 3D `scale` | |

## 4. Cues: when something happens

- Every scene builds within its first 0.4 s and then has an event ON the spoken word.
- At most 2.5 s between the scene start and its first cue. If more: start the scene later, or fill the wait with
  action (bars grow, a line draws, coins fall from the start). The style check measures it (`waits:<id>`).
- Counters need a lead: start at least 0.6 s before the number.
- The speaker between two full-screen parts never shorter than `speaker_min_seconds`. If two inserts are closer, start
  the second right where the first ends.

## 5. A new 2D scene

1. Copy a template from `templates/2d/` to `brand/templates/2d/` (never edit the app's templates). Everything is a
   function of the frame number; no CSS animation. Colours, fonts, radius, shadow and motion come from the brand tokens
   (CSS variables); never write a colour into the scene.
2. In every scene: parts enter one after the other (`motion.entrance_frames`, `motion.stagger_frames`), a slow drift
   if the pack sets `motion.drift_per_s`, the shadow from `shape.shadow_css`. If the brand has a logo, leave its corner
   (`logo.placement`) free: no shape may cover the logo or the content.
3. Probe three frames (start, cue, end) with the 2D renderer, put them side by side and look.
4. Traps: images the scene loads itself must be decoded before the frame is taken. A clip inside a card must report
   when its frame is ready. Test data needs ALL fields, or the example data is replaced by an empty object.
5. Add a line to `templates/2d/BLOCKS.md` (or the brand's own list) and to the table in `SKILL.md`.

A new 3D scene: skill `3d-scene`.

## 6. Reuse

Aim: every 3D scene at least twice, with another word or another state. The same data and the same length is no new
render. A post card can appear three times with a different mark each time.

## 7. Recordings (screen, game, web page)

- **A recording shows a place or a result, not someone moving around.** Calm pictures that show the quality: the
  subject stands, the camera pans or moves past once, slowly. No clip where a figure walks, unless the sentence is about
  walking. From long sequences only the strongest seconds.
- Check each recording before it goes into the plan: a strip of 5 frames. Reject it when a wall or pillar covers more
  than a quarter of the frame (use only the free part, `at` in the plan), when it is too dark (mean under 40 of 255),
  or when menus and toolbars are in the picture.
- Place the event (a hit, a reveal) on the spoken word: `at = event_time - (word_time - start)`.
- Third-party material never full screen and never without its source: `clip-card` with a label.
- Web pages: only public pages, no login, nothing clicked, slow scroll after a short still start.

## 8. Build and check

```
crewcut render plan edit/plan-vNNN.json      # read: lengths, cues, missing frames
crewcut render 2d   edit/plan-vNNN.json
crewcut render probe edit/plan-vNNN.json <id>[,<id>…]
crewcut render 3d   edit/plan-vNNN.json --rented --gpus N     # or --local, after the cost card
crewcut render cut  edit/plan-vNNN.json
# the Critic, never the builder:
python3 skills/cut-check/scripts/style_check.py edit/plan-vNNN.json
python3 skills/cut-check/scripts/cut_check.py work/edit-decisions-vNNN.json
```
