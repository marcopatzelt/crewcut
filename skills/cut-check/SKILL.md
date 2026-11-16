---
name: cut-check
description: "Checks a speaker cut and an edited video version before the user sees it: word rests and doubled words at cuts, tone over take changes, faces at cuts, graphics that wait still, speaker flashes, text and keyword limits, music length and rights, loudness, the shown-file lock. General checks for every style plus taste checks from the style pack (edit-style.json, rules/cut.md). Use for: check the cut, check the edit, before the preview, review the version, QA the export, is the cut ready, can this go to the user, cut errors."
---

# Cut check

The Critic runs this before any preview or final goes to the user. The Critic is never the identity that built the
version. Aim: the user never has to report the same fault twice. Be harsh: compare with the baseline
(`baseline.json`) and name every weak spot with its time.

## When

- A speaker cut, before anything is built on it: `cut_check.py`.
- Every edit plan version and its video, also after small corrections: `style_check.py`.
- The final, before the upload: `style_check.py <plan> --video export/<id>-vNNN-final.mp4`.

## Run

```
python3 skills/cut-check/scripts/cut_check.py work/edit-decisions-vNNN.json     # speaker cut
python3 skills/cut-check/scripts/style_check.py edit/plan-vNNN.json            # picture, plan, output
python3 skills/cut-check/scripts/style_check.py edit/plan-vNNN.json --no-media # plan only, before rendering
```

Both read the active style pack (`studio/brand`, else `packs/neutral`; `--pack DIR` for another). Output: ERROR, CHECK,
NOTE, OK per area, the listening list (every CHECK with a time), then the manual list with the rules of
`rules/cut.md`. Reports: `review/speaker-cut-check-vNNN.json` and `review/cut-check-vNNN.json`. Exit 1 on any ERROR.

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
| `loudness` | `edit_style.loudness_lufs`, `loudness_window_lu`, `true_peak_db` | -14, -2 to +0.5, -1.5 |
| word lists | `edit_style.cut_words` (`fillers`, `same_meaning`, `transcript_noise`, `same_spelling`) | empty |

Rules that are not measurable stay text in `rules/cut.md` and are printed as the manual list.

## Order

1. The speaker cut: `crewcut cut verify`, then `cut_check.py`. Fix every ERROR in the cut, new cut version.
2. The edit version: `style_check.py`. Fix every ERROR: new plan version, new build, check again. The line with `->`
   names the usual fix.
3. The listening list: each spot from 5 s before to 5 s after. This session cannot hear: never claim a listening check.
   Give the user the open spots with times.
4. The manual list, and the contact sheet of the video (one frame every 10 s). Put scene frames next to the reference.
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
