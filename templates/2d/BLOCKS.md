# 2D scenes: data keys, cues, examples, limits

Each scene is one HTML file in `templates/2d/`. A plan only gives data (JSON); the look comes from the style pack
(`brand.json`: colours, fonts, radius, shadow, motion, logo). Shared files: `base.css` (every colour, font, radius and
shadow is a CSS variable from `crewcut.brand.Pack.css_vars()`), `motion.js` (motion helpers, values from
`BRAND.motion`), `scene.js` (format, cues, fine values, decor, logo).

A style pack may hold its own copy of the whole folder in `brand/templates/2d/` (the scene and the three shared files).
The workbench then uses the pack's scene instead of the app's. The app's files are never edited for one brand.

## Render one scene

```
node tools/render_html.js templates/2d/<scene>.html <out_dir> --data <data.json> --brand <tokens.json> [--transparent] [--from A --to B]
```

- Output `0000.png`, `0001.png`, ... at 1920x1080 (`landscape`) or 1080x1920 (`portrait`).
- `--data` is set as `window.DATA` before the page runs. Without data, or with `"example": true`, the scene's built-in
  example is used (`{"example": true, "format": "portrait"}` shows the example upright).
- `--brand` is the pack's render tokens; `crewcut render 2d` writes and passes them itself.
- `--frames N` may be left out: then `frames` from the data, else the scene's own count.
- `--from -1 --to -1` renders only the last frame (a quick look).
- `crewcut render samples` renders one frame of every scene's example in both formats.

## Keys for every scene

| Key | Type | Default | Meaning |
|---|---|---|---|
| `format` | `"landscape"` or `"portrait"` | `"landscape"` | 1920x1080 or 1080x1920. The workbench sets it from the plan. |
| `frames` | number | per scene | Length in frames. The workbench sets it (insert length + 2). |
| `fps` | number | 25 | Frames per second. The workbench sets it. |
| `cues` | object name -> frame | per scene | Frame (inside the insert) on which a word is spoken. The graphic is done 1 to 2 frames before. In a plan, a cue may be `{"word": "thirty"}`, `{"time": 12.4}` or a frame number; the workbench turns it into a frame. |
| `seed` | number | per scene | Changes the floating decor bits (decor `float` only). |
| `fine` | object | empty | Fine values for special cases, listed per scene. Normally left out. |
| `decor` | `"none"`, `"shapes"`, `"float"` | from the pack | Overrides `BRAND.motion.decor` for this insert. Neutral is `none`: calm. |
| `logo` | `false` | | Hides the pack's logo in this insert. The logo shows only when the pack has one and places it (`brand.json` `logo.file`, `logo.placement`); never on transparent overlays. |

Rules for all: text is plain text (no HTML). Too long text is set smaller, never cut off, and never below the pack's
minimum text size (`edit-style.json` `min_text_px`, neutral 40 px). Motion values (entrance, stagger, counter roll,
highlight, drift) come from `brand.json` `motion`; the neutral pack keeps everything still after the entrance
(`drift_per_s: 0`), because slow growth makes text edges jump by fractions of a pixel.

Motion keys read from `BRAND.motion` (all optional): `entrance_frames` (10), `entrance_from` (0.94), `stagger_frames`
(6), `exit_frames` (6), `drift_per_s` (0), `counter_frames` (30), `digit_stagger_frames` (3), `mark_frames` (12),
`ease` (`[0.22, 1, 0.36, 1]`, a CSS cubic-bezier), `decor` (`none`).

---

## counter

A number rolls and locks in on the spoken word. A label chip above, a unit next to it, an optional line below.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `label` | text or null | none | Chip above the number. |
| `value` | text | required | Write it as text: `"30"`, `"15,000"`. Digits roll; commas, dots and spaces stand still. |
| `unit` | text or null | none | One word (`"cents"`) is set smaller next to the number; a symbol of 1 or 2 characters (`"$"`, `"%"`) as large as the number. |
| `sub` | text or null | none | A line below the number (`"per month"`). |

Cues:
- `label`: the chip stands 2 frames before. Missing or below 3: the chip is there from the start.
- `value` (default 50, 20 with more than 3 digits): the last digit locks in 1 frame before. The calm roll needs
  `counter_frames` plus `digit_stagger_frames` per further digit; with less time before the cue the number rolls short
  and fast from frame 0. A counter should start at least 0.6 s before its number.
- `unit`: the unit comes in from the left 2 frames before. Missing: it stands from the start.
- `sub` (default 25 frames after `value`).

Fine: `size` (fixed number size), `size_max` (330 portrait, 290 landscape), `max_width` (0.84 / 0.72 of the width),
`y` (centre as a share of the height), `roll_frames`, `digit_stagger`, `turns`, `pop` (0.06), `label_size` (44), `gap`.

```json
{"label": "1 million tokens", "value": "30", "unit": "cents", "cues": {"label": 8, "value": 60, "unit": 70}}
```

## headline

A source as a card: one or two chips above, the title in lines, a highlight runs over one phrase on the spoken word,
a source line at the bottom. A text card: the viewer reads a real source. The pack limits text cards per video
(`edit-style.json` `text_cards_max`, neutral 3).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `chips` | list of 1 or 2 texts | none | First chip in the accent colour (who), second on the card colour (where). |
| `title` | text | required | Breaks into lines itself; `\n` forces a break. |
| `mark` | text | none | A phrase of the title the highlight runs over. Must appear in the title exactly; it stays on one line. |
| `source` | text or null | none | Source line. The scene writes the bold "Source:" itself (a leading "Source:" is removed). |

Cues: `mark` (default 15): the highlight starts here and needs `mark_frames`.

Fine: `width` (0.86 / 0.62 of the width), `size` (72 / 76), `source_size` (40), `max_lines` (6 / 4; more lines make the
font smaller), `chip_size` (44), `chip2_size` (40), `mark_frames`, `source_label` ("Source:").

```json
{"chips": ["Example source", "Report, 2026"], "title": "A small team shipped the same feature in a third of the time",
 "mark": "a third of the time", "source": "Example data, written for this template.", "cues": {"mark": 20}}
```

## keyword

Key words as a chip over the speaker. Always rendered with `--transparent` (the plan sets `"transparent": true`) and
laid over the video. Only key words or a number, never full captions; 1 to 3 words.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `text` | text | | Short form: one chip for the whole insert (cues `in` and `out` move its start and end). |
| `words` | list | | Several chips: `[{text, from, to, x, y, style}]`. They may overlap in time when `y` differs. |
| `words[].from` / `to` | frame | 0 / `frames` | First frame of the entrance; from `to` on the chip is gone. |
| `words[].y` | 0 to 1 | 0.68 portrait, 0.8 landscape | Centre as a share of the height. |
| `words[].x` | 0 to 1 | 0.5 | Centre as a share of the width. |
| `words[].style` | `"accent"` or `"paper"` | `"accent"` | Accent chip with accent-ink text, or card colour with ink text. |

Safe zones: in portrait the chip stays out of the bottom 20 % and the top 10 % (platform buttons and captions); in
landscape out of the bottom 8 %. A `y` outside is moved in. Font 82 (portrait) or 74 (landscape); a too long text gets
smaller, never below `min_size` (54 / 50, at least the pack minimum): then shorten it.

Fine: `size`, `height`, `pad`, `radius`, `max_width` (0.86 / 0.6), `min_size`, `y`, `bottom_free`, `top_free`,
`enter`, `exit`.

```json
{"text": "Runs offline"}
```

## cards

1 to 4 real images (or a running clip as frames) as cards in a row, a label under each, optional arrows between
(a chain: A becomes B).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `cards` | list of 1 to 4 | required | `[{image, label, pos, folder, pattern, start}]`. |
| `cards[].image` | path | | An image, relative to the episode folder. |
| `cards[].folder` | path | | A clip as single frames instead (`pattern` `"%04d.jpg"`, `start` = first frame); it runs at the episode fps. |
| `cards[].label` | text | none | Chip under the card. With arrows the last label is in the accent colour. |
| `cards[].pos` | CSS object-position | centre | Which part of the image stays visible. |
| `aspect` | number | 1.5 | Card width / height. |
| `chip` | text or null | none | Chip above the row. |
| `arrows` | bool | false | Arrows between the cards. |

Cues: `c0` ... `c3`: each card stands 2 frames before its word (default 4, 16, 28, 40).

Fine: `width`, `max_height`, `gap`, `y`, `label_size` (40), `zoom` (slow image zoom per second, 0.02), `enter` (16).

Only real material the user may show. No platform logos.

## bars

A bar chart from real values grows from the left; a large number rolls and locks in on the word. The bars should add
up to the number that is said.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `values` | list of numbers | required | One bar each; 0 is a flat, soft bar. |
| `start_label`, `end_label` | text | none | Chips under the first and last bar (e.g. times). |
| `value` | text | `"0"` | The large number. |
| `unit` | text | none | Word next to the number. |
| `chip` | text | none | Chip above the number. |

Cues: `value` (default 40): the number locks in 1 frame before; the last bar stands shortly before.

Fine: `width`, `height`, `y`, `size` (number size), `axis_size` (40), `chip_size`.

## post

A social post as a card: name, handle, the text word for word, date. The user gives the data (copy it from the real
post; the agent never invents one). No platform logos; `network` is plain text if given.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | text | required | |
| `handle` | text | none | |
| `initials` | text | from the name | Shown in the round avatar when there is no `avatar` image. |
| `avatar` | path | none | An image the user may use (relative to the episode folder). |
| `network` | text | none | Plain text, e.g. `"LinkedIn"`. |
| `text` | text | required | Word for word. `\n` breaks a line. |
| `marks` | list of up to 3 texts | none | Phrases that get a highlight on their cue. |
| `date` | text | none | |

Cues: `m0`, `m1`, `m2`: the highlight of `marks[i]` starts here. No cue: no highlight.

Fine: `width`, `size` (text size; a long post gets smaller, never below the pack minimum), `mark_frames`,
`max_height` (0.8 of the height).

## clip-card

Footage that is not the user's own runs as a card with a visible source label, never full frame and never zoomed.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `folder` | path | required | The clip as single frames (`ffmpeg -i clip.mp4 -vf fps=25 frames/%04d.jpg`). |
| `pattern` | text | `"%04d.jpg"` | File name pattern. |
| `start` | frame | 0 | First frame of the clip to show. |
| `aspect` | number | 16/9 | Width / height of the clip. |
| `chip` | text | none | Chip above. |
| `label` | text | required in practice | The source, visible under the clip. |

No cues. Fine: `width`, `enter`, `chip_size`, `label_size`. Use only footage the user has the right to show.

## grid

A grid of symbols builds row by row; the last one (bottom right) fills with the accent and pulses. A chip above, a
large chip below on the end cue. For "one in N", "N people".

| Key | Type | Default | Meaning |
|---|---|---|---|
| `columns` | number | 14 | 1 to 40. |
| `rows` | number | 8 | 1 to 30. |
| `symbol` | `"person"`, `"dot"`, `"square"` | `"person"` | |
| `chip_top` | text | none | |
| `chip_bottom` | text | none | Comes on the cue `end`. |

Cues: `grid` (default 0): the first symbol. `end` (default `grid` + 46): the last symbol is filled, the bottom chip
stands. Building needs about 40 frames; with less time the grid builds faster.

Fine: `cell` (spacing, at most 72), `max_width`, `max_height`, `chip_size`, `bottom_size`.

---

## Planned

Not built yet (they exist in the author's studio and wait for a neutral port): `area` (a map outline as a flat
surface with a chip), `flow` (tiles with symbols and a dot that walks through the steps), `wave` (a waveform from
measured values with a play head), `swap` (one tile is struck out and replaced), `untangle` (a knotted line becomes
three straight lines). A plan that names one of them fails with the list of available scenes.
