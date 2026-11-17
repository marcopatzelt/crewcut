# Calm in a talking video

The launch film is loud by design. Inside a normal video the speaker is the show: one idea per insert, type in space,
a slow camera in every hold, real motion blur. These rules hold for shelf templates and custom comps alike. Limits are
read from the pack (`edit-style.json` `motion`, `brand.json` `motion_graphics`); the numbers below are the neutral
defaults.

## 1. The shelf, as planned

The app's in-video templates (`templates/motion/`). `crewcut motion template list` shows what exists today; this
table says what each is for. Look at it **after** you know the picture you need.

| Template | Kind | What one sees | Default length |
|---|---|---|---|
| `keyword_pop` | overlay | 1 to 3 words, 120 to 160 px, enter per word from the baseline with blur, 2 % drift, leave with the next camera move | 2.0 s (min 1.5) |
| `lower_third` | overlay | name and role, a thin stroke draws itself under the name, no box | 4.5 s (min 3) |
| `number_roll` | full or overlay | digits roll like a meter, tight spacing, blur only while rolling, whole 1 frame before the cue, a unit and one line | 4.0 s (min 3) |
| `prompt_bar` | full, backdrop = the speaker's picture | frosted bar over the blurred video, typed text, push in and pull back: "what I asked" | 5.0 s (3 to 6) |
| `word_reel` | full | steps or tools roll, the box lands on the current one | 3.5 s (min 3) |
| `chapter_card` | full | chapter number and title grow out of one point in the next ground colour | 3.0 s |
| `quote` | full | the quote at 35 % white; a light run brings the key line to full white and draws an underline | 5.0 s (min 4) |
| `versus` | full | two things side by side, values count, the winner grows, the other dims; 2 to 3 rows | 5.0 s |
| `ranking` | full | 3 to 5 places in tilted 2.5D, light goes on place by place, the camera ends on place 1 | 6.0 s |
| `card_gallery` | full | the episode's real screenshots fly in as a masonry grid | 3.5 s, once per video |
| `callout` | overlay | a drawn stroke or arrow points at something in the picture, an optional word | 2.5 s |
| `big_claim` | full, Blender plate | one heavy 3D word lands with a paint splash | 3.0 s, once per video |
| `end_lockup` | full | logo and channel name settle | 2.5 s |
| `cursor` | overlay helper | a pointer path with a click squash, for screen recordings | 0.4 to 0.8 s per move |

Launch-only (in `examples/launch-film/templates/`, not for talking videos): the app dock, a full-frame burst, the iris
reveal, the logo shatter, the pixel burst, the sky gradient, the particle converge with the logo plates.

The HTML scenes in `templates/2d` stay the light path for data cards (`bars`, `headline`, `post`, `cards`, `grid`,
`clip-card`). **One statement gets one form:** a plan never shows the same number as `counter` and as `number_roll`.
With the engine present, motion templates are the default for numbers and keywords (`edit-style.json`
`motion.prefer`).

## 2. Lengths and motion

| Value | Default |
|---|---|
| Full-frame insert | at least 3.0 s, typically 4, at most 6 (explainers and rankings up to 8) |
| Overlay | at least 1.5 s; nothing enters and leaves within 1 s |
| Entrance | 0.35 to 0.5 s, ease `expo`; springs only on scale, overshoot at most 4 % |
| Exit | 0.25 s, ease `in`, or carried by the next camera move; never a plain fade of the whole frame |
| Hold | never still: 1.5 to 3 % push per second, ease `linear` |
| Motion blur | 180°, 16 samples (8 in draft); off on layers that only drift; never on Blender plates; never the Temporal Motion Blur effect |
| Frame rate | the plan's (25 or 30); comps are time based, so the same comp renders 60 fps review strips |
| Text | hero 120 to 160 px; labels at least `min_text_px` (40 px) after every scale and push |
| Cue | the word or number is complete 1 to 2 frames before it is spoken |

## 3. Colour and type

- Templates take the pack's tokens through `CC.*`: content colours from `motion_graphics.palette` in order, the first
  is the accent and goes only on the one thing that matters; pastels for grounds and gradients.
- The hue check is part of every review: no hue above 30 % of the coloured pixels, unless the insert declares
  `"natural": true` (grass, sky, footage) or it is the end lockup.
- Fonts: the pack's `fonts.display` and `fonts.body` through `CC.font(role)`. A template never names a font.
- No chips, pills or boxes behind words. Type stands in space. The one allowed plate is the frosted glass that shows
  the video through it, and only when `motion_graphics.glass` is true.

## 4. Density: not overloaded

`crewcut render plan` warns and the style check counts. Limits come from `edit-style.json` `motion`.

| Rule | Long video | Short |
|---|---|---|
| Motion per sentence | at most 1 (overlay or insert, never both) | same |
| Big moments (full-frame motion) | 3 to 5 per video; at most 1 per minute in long videos | at most 2 |
| All motion, overlays included | at most 2 per minute on average, never 2 inside 6 s | 3 to 5 in total |
| Heroes (`big_claim`, `card_gallery`, `ranking`) | each once per video, at most 2 in total | at most 1, better reuse the long video's |
| Speaker between two full-frame parts | at least `speaker_min_seconds` (2 s) | same; `max_still_s` is met by speaker zooms, not by more graphics |
| Sounds | at most one per motion, none on `keyword_pop` twice in a row | same |
| First and last seconds | the speaker alone for `speaker_open_close_seconds`; Short: `end_face_s` | same |

`keywords_max` counts the HTML `keyword` and `keyword_pop` together. `graphics_mix` has a `motion` share.

## 5. Where a graphic sits

- **Full frame** (`"kind": "motion"`, not transparent): its own ground from the pack, placed like a 2D insert. In a
  Short with the proof on top it goes on the 1080 x 960 stage (`@formats` includes `"stage"`), so nothing is cropped.
- **Full frame with the speaker as backdrop** (`"backdrop": "speaker"`, `prompt_bar` first): the workbench hands the
  comp the graded, zoomed speaker piece of exactly this span; frame 0 equals the speaker frame, so the join is
  invisible. Only the picture is replaced; the voice is untouched.
- **Overlay** (`"transparent": true`): RGBA frames laid on the speaker. Text sits on the free side at chest to shoulder
  height (`CC.frame().sideBox`, `anchor`), never over the face box (face centre ± 0.16 of the width, ± 0.14 of the
  height), never a ring or frame around the head.
- **Behind the speaker** (`"layer": "behind"`): only with a matte that passed the edge gate; otherwise the graphic goes
  beside the speaker automatically. `matte.md`.

## 6. Safe areas (in `CC.frame`)

| Format | Keep free |
|---|---|
| 16:9 (1920 x 1080) | 5 % on every side; the bottom 8 % for overlays (the player bar) |
| 9:16 (1080 x 1920) | top 10 %, bottom 20 %, right 18 % (`shorts.right_free_frac`), left 6 %; overlays centre at 0.41 of the width |
| stage (1080 x 960) | 5 % on every side; the bottom 6 % is the seam to the face |

Every template positions through `CC.frame`; no template contains 1920 or 1080.
