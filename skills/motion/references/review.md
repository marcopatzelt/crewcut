# Review: look before anyone else does

Two looks. **The builder's own** (the Editor, after every stage, before handing over) and **the Critic's** (never the
builder, after every round, with the review bundle). The user sees nothing that has not passed both.

Read [craft.md](craft.md) first when the channel has selected benchmarks. Geometry, material and movement comparisons are required separately from technical checks.

## 1. The builder's own look

1. **Reference first.** When the piece has a reference, take its frames at 60 fps around every transition and write
   down the event times (click, burst start, frame full, hold length, iris open):

   ```bash
   ffmpeg -ss 3.1 -t 1.8 -i refs/x.mp4 -vf "fps=60,select='not(mod(n\,4))',scale=480:-1,tile=6x5" -frames:v 1 ref-sheet.jpg
   ```

   Reference clips stay in the episode's `refs/` and never enter an output, the repository or a rented machine.
2. **Comparison sheet** per beat: `crewcut motion render compare --ref refs/x.mp4 --ref-times 3.1,3.4,3.9 --times
   0.6,0.9,1.4 --out compare.jpg`, one row per moment, the reference next to ours.
3. **60 fps strips** across every transition (30 frames, every 2nd): `crewcut motion render sheet --times …`. Look for
   stutter, missing motion blur, empty frames, holds that are too long, glyphs that wait before their cue.
4. **Hue check:** `crewcut motion render palette frame.png --limit 0.30` (coloured = saturation ≥ 0.25 and value ≥
   0.15; 12 hue bins; exit 3 above the limit). Rework anything above 30 % unless it is natural content or the final
   lockup.
5. **Frame sheet** of the whole piece, one frame every 0.25 s, before you hand it over.

Then hand it to the Critic: `crewcut job add --episode $CREWCUT_EPISODE --identity critic --step edit "review motion
m3, round 1"`.

## 2. The Critic's bundle

`crewcut render motion-review <plan> [--ids m1,m3] [--ref refs/x.mp4 --ref-offset S]` writes
`review/motion-vNNN/<id>/` (the next free NNN), then `python3 skills/cut-check/scripts/motion_check.py
review/motion-vNNN` prints ERROR and CHECK lines and exits 1 on any ERROR.

| File | What | Fails when |
|---|---|---|
| `sheet.jpg` | every 0.25 s of the insert | a frame is empty; a hold shows no change for 0.5 s ("the camera stopped") |
| `strip-in.jpg`, `strip-out.jpg`, `strip-t<N>.jpg`, `strip-cue-<name>.jpg` | 60 fps, 30 frames, every 2nd, rendered from the comp at 60 fps whatever the plan's fps | stutter, missing blur, a hold longer than planned, glyphs waiting before their cue |
| `compare.jpg` | ours next to the reference at matched times (reference time = insert time + `--ref-offset`); without a reference: next to the library sample or the baseline's frames | the Critic writes one sentence per big moment on what the reference still does better (required) |
| `hue.json` | hue shares at 5 times | one hue above 30 % of the coloured pixels; `"natural": true` and the end lockup are exempt |
| `text.json` | every text layer's smallest size on screen; overlay pixels on the face box or outside the safe box | below `min_text_px`, outside the safe box, over the face box |
| `sharp.json` | Laplace variance, frame difference and content per frame | under 35 % of the mean outside the entrance, the exit and declared transitions; more than 3 such frames in a row is an ERROR |
| `web-look.md` | 8 frames with four questions | any yes |
| `lint.json` | the `.jsx`: hard-coded 1920/1080, a font name, Shatter, Temporal Motion Blur (ERROR); a rounded rect or a filled box with text (candidate) | any ERROR; candidates are for the Critic |
| `density.json` | the density counts over the whole plan, and this insert's neighbours | over a limit |

At the bundle root: `critic.md` (the form the Critic fills) and `bundle.json` (files, skipped steps, every finding).
Without the engine, the strips and the engine's text sizes are skipped with a line in the bundle; the rest works from
the rendered PNG frames.

## 3. How to read it

- **Sheet first.** Does every quarter second show something happening? A row of identical cells is a stopped camera.
  An empty first cell in a full-frame insert is a wrong start.
- **Strips next.** At 60 fps a good entrance shows long blurred frames at the start and sharp ones at the end (`expo`).
  Two identical neighbours in the middle of a move are a stutter. A glyph visible before its cue is a timing error, not
  taste.
- **Compare.** Put a finger on the moment the reference is better and say it in one sentence: "their number lands with
  a camera hit, ours just stops". That sentence goes into `critic.md` and becomes the next round's task.
- **The four web-look questions** for each of the 8 frames: could it be a screenshot of a web page or an app? Is there
  a rounded rectangle with text in it? Does a word stand in a filled box? Do all shadows share one shape although the
  depths differ? Any yes: back to the builder with the frame named.
- **Numbers last.** `hue.json`, `text.json`, `sharp.json`, `density.json` confirm what you saw. A number that passes
  does not make a weak piece good.
- **The ratchet.** The video against the bar: at least one named thing better, nothing that the bar did right now
  worse (`ratchet.md`).
- **What cannot be checked:** sound. `critic.md` lists every motion's in, cues, out and sound events with times for the
  user.

## 4. Rounds

At most 3 review rounds per piece (the bundle counts them). Findings go back to the builder through crew talk
(`crewcut say --to editor --about review/motion-v002/m3/critic.md --kind fix "…"`). After the third round the
Showrunner asks the user with the best version and the open points, instead of a fourth round. A fixed piece is a new
render and a new bundle, never an edited old one.
