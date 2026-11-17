---
name: cut-check
description: "Checks a speaker cut and an edited video version before the user sees it: word rests and doubled words at cuts, tone over take changes, faces at cuts, graphics that wait still, speaker flashes, text and keyword limits, music length and rights, loudness, the shown-file lock, and the review bundle for motion graphics (sheets, 60 fps strips, hue, text size, sharpness, web-look lint, density). General checks for every style plus taste checks from the style pack (edit-style.json, rules/cut.md). Use for: check the cut, check the edit, before the preview, review the version, QA the export, is the cut ready, can this go to the user, cut errors, review the motion graphics."
---

# Cut check

The Critic runs this before any preview or final goes to the user. The Critic is never the identity that built the
version. Aim: the user never has to report the same fault twice. Be harsh: compare with the baseline
(`baseline.json`) and name every weak spot with its time.

## When

- A speaker cut, before anything is built on it: `cut_check.py`.
- Every edit plan version and its video, also after small corrections: `style_check.py`.
- The final, before the upload: `style_check.py <plan> --video export/<id>-vNNN-final.mp4`.
- Every plan with motion inserts (`"kind": "motion"`), after they are rendered: the review bundle and `motion_check.py`
  (section "Motion review").

## Run

```
python3 skills/cut-check/scripts/cut_check.py work/edit-decisions-vNNN.json     # speaker cut
python3 skills/cut-check/scripts/style_check.py edit/plan-vNNN.json            # picture, plan, output
python3 skills/cut-check/scripts/style_check.py edit/plan-vNNN.json --no-media # plan only, before rendering
python3 -m crewcut.motion.review edit/plan-vNNN.json [--ids m1,m2] [--ref refs/x.mp4 --ref-offset S]  # bundle
python3 skills/cut-check/scripts/motion_check.py review/motion-vNNN              # motion machine checks
```

The scripts read the active style pack (`studio/brand`, else `packs/neutral`; `--pack DIR` for another). Output: ERROR,
CHECK, NOTE, OK per area, the listening list (every CHECK with a time), then the manual list with the rules of
`rules/cut.md`. Reports: `review/speaker-cut-check-vNNN.json`, `review/cut-check-vNNN.json`, and
`review/motion-check-vNNN.json` (a plan) or `review/motion-vNNN/motion-check.json` (a bundle). Exit 1 on any ERROR.
`motion_check.py` also takes the plan itself (no engine; the bundle adds the engine's measurements).

## General checks (every style)

| Id | Rule | How |
|---|---|---|
| `verify`, `join:*`, `edge:*`, `channels` | The cut verification ran for this cut, is newer than the decisions, every join pause is in range, the voice is on both sides | reads the verification file of `crewcut cut verify` |
| `doubled:*` | No doubled word at a cut | last word before = first word after, in the script and in what was heard; same-meaning words from the pack count too |
| `leftover:*` | No word rest at a cut | an edge within 0.28 s of a discarded attempt (CHECK); a start inside a speech island (ERROR) |
| `take-change:*` | Same tone over every cut | a sentence over a take change goes on the listening list; if it sounds different, take the whole sentence from one take |
| `level:*` | No level jump | 4 dB or more between the voiced parts 2.5 s before and after a cut |
| `stutter:*` | Stutters cut out | repeated words and the pack's filler words in what was heard (the transcriber hears few of them) |
| `face:*` | No back of the head or turned-away head at a speaker start or end | skin share in the face window of the plan (`face`) under 60 % of the median |
| `waits:*` | A full-screen insert does not wait still for its first cue | 1.5 s or more to the first cue and over 80 % of it without motion |
| `empty:*` | A full-screen insert does not start with an empty frame | under 0.3 % content in its first frame (CHECK) |
| `music`, `music-rights` | Music at least as long as the video; source and rights note exists | `sound.music_source` points at a file |
| `grade` | Each episode has its own measured grade | a grade measurement in `review/` (CHECK) |
| `fresh`, `shown` | The video is newer than the plan; a shown file was not changed | `<output>.shown` holds the sha256 |
| `loudness`, `channels` | Loudness around the target, true peak under the limit, sound on both sides | ffmpeg ebur128 and volumedetect |

## Taste checks (values from the style pack)

| Id | Pack value | Default in the neutral pack |
|---|---|---|
| `flash:*` | `edit_style.speaker_min_seconds` | 2.0 s |
| `open`, `close` | `edit_style.speaker_open_close_seconds` | 3.0 s |
| `share` | `edit_style.speaker_share_min`, `speaker_share_max` | 0.4 to 0.95 |
| `text-share`, `text-sources` | `edit_style.text_share_max`, `text_cards_max` | 0.4, 3 |
| `keyword-words`, `keyword-count`, `keywords` | `edit_style.captions`, `keyword_max_words`, `keywords_max` | keywords, 4, 8 |
| `italic`, `small-text` | `edit_style.italics`, `min_text_px` (scans the scene templates) | no italics, 40 px |
| `logo:*` | `brand.logo.file`, `logo.placement`, `logo.size` | no logo, so no check |
| `end-card` | `edit_style.cut_words.end_card_cue` | empty, so no check |
| `mix`, `pace` (NOTE) | `edit_style.graphics_mix`, `pace_cuts_per_minute` | |
| `motion-*` (density) | `edit_style.motion` (lengths, big moments, per minute, gap, per sentence, heroes, sounds) | 3 to 6 s full frame, 1.5 s overlay; 3 to 5 big moments; 2 per minute; never 2 inside 6 s; 1 per sentence; heroes once, 2 in total; 1 sound per motion. Short: 2 big, 3 to 5 in total, 1 hero |
| `loudness` | `edit_style.loudness_lufs`, `loudness_window_lu`, `true_peak_db` | -14, -2 to +0.5, -1.5 |
| word lists | `edit_style.cut_words` (`fillers`, `same_meaning`, `transcript_noise`, `same_spelling`) | empty |

Rules that are not measurable stay text in `rules/cut.md` and are printed as the manual list.
`keywords_max` counts the 2D `keyword` chips and the motion `keyword_pop` together.

## Motion review

The Critic reviews every motion insert, and never one it built. The bundle command writes
`review/motion-vNNN/<id>/` (the next free NNN) from the rendered frames, the `.jsx` source and the plan:

| File | What | Fails when |
|---|---|---|
| `sheet.jpg` | every 0.25 s of the insert | a frame is empty; a hold shows no change for 0.5 s ("the camera stopped") |
| `strip-in.jpg`, `strip-out.jpg`, `strip-t<N>.jpg`, `strip-cue-<name>.jpg` | 60 fps, 30 frames, every 2nd, built from the comp at 60 fps (engine only) | stutter, missing blur, a hold longer than planned, glyphs waiting before their cue |
| `compare.jpg` | ours next to the reference at matched times (`--ref`, reference time = insert time + `--ref-offset`); else the library sample or the baseline's motion frames | the required sentence per big moment |
| `hue.json` | hue shares at 5 times | one hue above 30 % of the coloured pixels; `"natural": true` and the end lockup are exempt |
| `text.json` | every text layer's smallest size on screen (engine), overlay pixels on the face box or outside the safe box | below `min_text_px`, outside the safe box, over the face box (overlays) |
| `sharp.json` | Laplace variance, frame difference and content per frame | under 35 % of the mean outside the entrance, the exit and the declared `transitions`; more than 3 such frames in a row is an ERROR |
| `web-look.md` | 8 frames with the four questions as an empty form | any yes |
| `lint.json` | the `.jsx`: hard-coded 1920/1080, a font name, Shatter, Temporal Motion Blur (ERROR); a rounded rect or a filled box with text (candidate) | any ERROR; candidates are for the Critic |
| `density.json` | the density counts over the whole plan, and this insert's neighbours | over a limit |

At the bundle root: `critic.md` (the form) and `bundle.json` (files, skipped steps, every finding). Without
`effectcraft-cli` the strips and the text sizes from the engine are skipped with a line in the bundle; everything else
works from the PNG frames. Never run the engine on the user's laptop for this: the image or a rented machine.

The Critic's own look, written into `critic.md`:
1. The sheet and the strips: stutter, blur, holds, cues.
2. The four web-look questions for each of the 8 frames: could it be a screenshot of a web page or an app; is there a
   rounded rectangle with text in it; does a word stand in a filled box; do all shadows share one shape although the
   depths differ. Any yes: back to the builder with the frame named.
3. For every big moment (full-frame insert), one sentence on what the reference still does better. Required.
4. The ratchet: a video that is not better than the bar in at least one named way goes back. Name the way, with time
   and frame.
5. What I cannot check: sound. The listening list in `critic.md` (every motion's in, cues, out and its sound events)
   goes to the user.

At most 3 review rounds per piece (the bundle counts them). After the third, the Showrunner asks the user instead of a
fourth round.

## Order

1. The speaker cut: `crewcut cut verify`, then `cut_check.py`. Fix every ERROR in the cut, new cut version.
2. The edit version: `style_check.py`. Fix every ERROR: new plan version, new build, check again. The line with `->`
   names the usual fix.
3. The listening list: each spot from 5 s before to 5 s after. This session cannot hear: never claim a listening check.
   Give the user the open spots with times.
4. The manual list, and the contact sheet of the video (one frame every 10 s). Put scene frames next to the reference.
   With motion inserts: the bundle, `motion_check.py` on it, and `critic.md` filled in (section "Motion review").
5. **Only at 0 ERROR** does the version go to the user. Until then tell the Showrunner "unchecked, do not show". Say in
   one sentence what is checked and what stays open.
6. Right after it was shown: `crewcut render shown <plan>`. Every change after that is a new plan version.

**Exceptions.** If an ERROR or CHECK is shown to be fine (the user wants it so), its id goes with the reason, the
user's words and the date into `review/cut-check-exceptions.json`, for example
`{"waits:s3": "user approved v005 like this, 16 Nov 2026"}`. The scripts then print OK with the reason. No exception
without a reason.

## Limits

- Word rest: transcribers often miss a cut-off word. The script measures the edge against the speech islands; it finds
  candidates, not a verdict. Listening decides.
- Tone: level and pitch measurements did not separate bad joins from normal ones. That is why every sentence over a take
  change is on the listening list.
- Face: a skin-colour measure in the plan's face window, not a face detector. If the speaker sits elsewhere than the
  plan says, it gives false errors: measure `face` again.
- Logo: the script finds "something" in the logo corner, not the logo itself.
- Motion lint: the web-look rules read the source, not the picture. A rounded or filled shape tied to a text layer
  is a candidate; the Critic decides with the frames. The overlay face check counts visible pixels in the face box, so
  a deliberate pointer near the face needs an exception with a reason.
- What the checks do not find: double sentence starts inside a select (use `crewcut cut doubles` before building), music
  that is too loud, a weak choice of recordings, a slide-deck feeling. Only a person sees and hears that.

## Learning from a correction

When the user reports a cut fault that is missing here:
1. Propose a rule for the pack: `crewcut rule propose --step cut --rule "…" --source "user, <date>, <their words>"`.
   The user accepts it with one yes. A newer rule replaces an older one; rules do not pile up.
2. If it is measurable: add a check to `style_check.py` or `cut_check.py` that reads its limit from the pack (a new key
   with a neutral default in `packs/neutral/`, documented in `docs/style-packs.md`). Test: the version the user
   complained about must now fail, the corrected one must pass.
3. If it is not measurable: it stays a rule in `rules/cut.md` and shows up in the manual list.
4. If it belongs to the script, title, thumbnail or upload, change that skill or rule file instead.

## Planned

- Zoom measurement in third-party clips (OpenCV): third-party clips are never zoomed in many packs.
- A real face detector instead of the skin share.
- Logo detection against the logo file instead of "something in the corner".
- A length check against the assembly's own frame count.

## Sources

No connection to or endorsement by this person; we took ideas and wrote our own summary.

- Alex Hormozi (editing and caption style made by his editor Ryan Magin), https://www.youtube.com/@AlexHormozi: cuts on
  the word, no dead air, short captions; the checks for word rests, stutters and keyword length follow from that.
