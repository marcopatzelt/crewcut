# Style packs

A style pack holds the user's taste as data; this page lists the keys each step reads, with the neutral default.

## How a pack works

A style pack is the user's taste as data. Skills and tools hold the know-how and read every colour, font, loudness,
limit and channel rule from the active pack through `crewcut.brand.load()`; none of it is written in code.

| Pack | Where | Owner |
|---|---|---|
| neutral default | `packs/neutral/` in the app | the app; updates may change it |
| the user's pack | `studio/brand/` | the user; updates never touch it |
| example | `examples/striq/` | a real, dated example (the author's channel): values and rules only |

- The user's pack is merged over the neutral one: a key the user's pack does not set keeps its neutral default.
- `studio/brand/` appears when onboarding writes it (`crewcut brand init` copies the neutral pack first) or when the first
  learned rule is accepted.
- Every value may carry its source in the file's `sources` map, keyed by the dotted path
  (`"colors.accent": "from your website, 16 Nov 2026"`). The profile view shows it next to the value.
- `rules/<step>.md` holds learned rules, one list item each, newest last:
  `- 2026-11-11: Music stays about 3 dB under the voice. (source: user, "music a bit too loud")`. A rule is added only
  after the user accepts its card. Rules replace older rules on the same point instead of piling up.
- `brand/templates/` may hold copies of 2D scenes rebuilt for this brand; the app's own templates are never edited.
- `crewcut brand show` prints the active pack, `crewcut brand check` validates it, `crewcut brand preview` renders the
  10-second sample.

The sections below list the keys the skills read, file by file.

## edit-style.json: edit and cut-check

Read by the skills `edit` and `cut-check` and by `skills/cut-check/scripts/style_check.py` and `cut_check.py`.
Keys marked "(new)" came with the cut checks of 16 Nov 2026.

| Key | Neutral default | Meaning |
|---|---|---|
| `captions` | `"keywords"` | `none`, `keywords` (single words or numbers over the speaker) or `full` |
| `keyword_max_words` | 4 | words per keyword (style check `keyword-words`, ERROR above) |
| `keywords_max` (new) | 8 | keywords per video, 2D `keyword` and motion `keyword_pop` together (style check `keyword-count`, CHECK above; `render plan` warns) |
| `text_cards_max` | 3 | different text sources (headline, post) per video (CHECK above) |
| `text_share_max` (new) | 0.4 | share of full-screen inserts that are text cards (ERROR above) |
| `italics` | false | false: italic type in the scene templates is an ERROR |
| `min_text_px` | 40 | font sizes under this in the scene templates are a CHECK |
| `music` | `"none"` | `none`, `generated` or `own`; with music, the plan needs `sound.music_source` |
| `music_db`, `duck` | -16.0, true | music bed level under the voice, and ducking while someone speaks |
| `loudness_lufs`, `true_peak_db` | -14.0, -1.5 | export target and true-peak limit |
| `loudness_window_lu` (new) | [-2.0, 0.5] | allowed loudness relative to the target (style check `loudness`) |
| `graphics_mix` | motion 0.4, 2d 0.4, 3d 0.0, text 0.2 | target share of insert kinds (NOTE only); `motion` = motion graphics |
| `pace_cuts_per_minute` | 8 | shots per minute (NOTE only) |
| `speaker_min_seconds` | 2.0 | speaker never shorter than this between two full-screen parts (ERROR) |
| `speaker_open_close_seconds` (new) | 3.0 | speaker at least this long at the start and in the last 30 s (ERROR) |
| `speaker_share_min`, `speaker_share_max` (new) | 0.4, 0.95 | share of the video with the speaker on screen (CHECK outside) |
| `speech_speed` (new) | 1.0 | speed of the speaker cut |
| `zoom_base`, `zoom_punch` (new), `zoom_max` | 1.0, 1.1, 1.15 | speaker zoom: normal, punch-in, never more than |
| `end_card` | true | the video ends with an end card |
| `cut_words` (new) | all empty | language data for the cut checks, see below |

`motion` holds the motion graphics rules. `crewcut render plan` warns when a plan breaks one, the style check counts
them (`motion-*`), both through `crewcut/motion/density.py`; see [motion.md](motion.md). "Full frame" is a motion
insert that covers the picture, an overlay lies on the speaker. A pack that leaves a key out keeps the neutral value.

| Key | Neutral default | Meaning |
|---|---|---|
| `prefer` | `"motion"` | `"motion"`: with the engine present (or `render.location = "rented"`) the motion templates (`number_roll`, `keyword_pop`) are the default over the 2D `counter` and `keyword`, and `render plan` says so; `"2d"` keeps the 2D scenes first |
| `insert_s` | [3, 6] | shortest and longest full-frame motion insert, seconds |
| `insert_long_s` | 8 | longest for an explainer (`"explainer": true` in its data) |
| `overlay_min_s` | 1.5 | shortest overlay; nothing enters and leaves within 1 s |
| `template_min_s`, `template_max_s` | keyword_pop 1.5, lower_third 3, number_roll 3, prompt_bar 3 to 6, word_reel 3, quote 4, ranking up to 8 | per-template lengths over the two above |
| `per_sentence_max` | 1 | motion graphics starting in one sentence: overlay or insert, never both (needs the words file) |
| `big_moments` | [3, 5] | full-frame motion inserts per long video (fewer is a note) |
| `big_per_minute_max` | 1 | videos longer than 5 minutes: at most one big moment per minute |
| `per_minute_max` | 2 | all motion, overlays included, per minute on average |
| `min_gap_s` | 6 | never two motion graphics starting this close together (long videos) |
| `heroes`, `heroes_max` | big_claim, card_gallery, ranking; 2 | hero templates: each once per video, at most this many in total |
| `sounds_per_motion_max` | 1 | sounds per motion graphic (the workbench uses only the first `@sounds` entry) |
| `shorts` | big_max 2, total [3, 5], heroes_max 1 | the same for a Short (portrait plan) |

The speaker also stays alone for `speaker_open_close_seconds` at the start and end (a Short: `shorts.end_face_s` at
the end), and at least `speaker_min_seconds` between two full-frame parts when one of them is motion.

`cut_words` holds the word lists of the channel's language; code never contains them, the neutral pack has none:

| Key | Meaning |
|---|---|
| `fillers` | filler words ("uh"); heard ones are a CHECK (`stutter`) |
| `same_meaning` | groups of words that count as the same at a cut (`[["so", "therefore"]]`, `doubled`) |
| `transcript_noise` | phrases a transcriber invents in silence; ignored when looking for discarded attempts |
| `same_spelling` | spelling map for comparing words (`{"one": "1"}`) |
| `end_card_cue` | words of the sentence where the end card starts (`end-card`); empty = no check |

## thumbnail.json: thumbnail

Read by the skill `thumbnail` and `skills/thumbnail/scripts/thumb_check.py`.

| Key | Neutral default | Meaning |
|---|---|---|
| `layouts` | face-result, result-vs-result, before-after | allowed layout templates; the first is image 1 (also `progress`) |
| `face`, `face_position` | true, `"left"` | a face in the first layout, and where: `left`, `right`, `side`, `center`, `any` |
| `face_min_area` (new) | 0.06 | face box share of the image (CHECK under) |
| `max_faces` (new) | 1 | faces in the image (CHECK above) |
| `max_words` | 4 | words in the image (CHECK above, ERROR at 3 or more above) |
| `max_numbers` (new) | 1 | numbers in the image (CHECK above) |
| `colors` | accent, ink, paper | brand colour names or `#RRGGBB` values for the prompt |
| `background` (new) | null | brand colour name or `#RRGGBB`; the image edge is checked against it |
| `avoid_colors` (new) | [] | `#RRGGBB` values or `{"name": "yellow", "hue": [42, 68]}`; over 0.5 % is a CHECK |
| `reference_photo` | null | file in the pack: the person's fixed photo, image 1 of every prompt |
| `style_reference` (new) | null | file in the pack: the user's best own thumbnail, style only |
| `variants` | 3 | images per round (an A/B test takes up to 3) |

## brand.json stage3d.checks: 3d-scene

Read by `skills/3d-scene/scripts/measure_frame.py` (with `stage3d.background` and `stage3d.accent`) and by the skill
`3d-scene`. All new; the defaults are Crewcut's own, not measured from any channel.

| Key | Neutral default | Meaning |
|---|---|---|
| `background_tolerance` | 0.06 | allowed brightness difference of the rendered background to `stage3d.background` |
| `accent_share` | [0.01, 0.30] | share of the frame in the accent colour |
| `accent_distance` | 40 | allowed RGB distance of the rendered accent to `stage3d.accent` |
| `shadow_depth` | [0.08, 0.40] | how much darker the floor shadow is than the lit floor |
| `dark_share_max` | 0.10 | share of dark pixels outside the accent |
| `object_height_min` | 0.30 | the main object fills at least this share of the frame height (checked by eye) |
| `word_height_max` | 0.18 | the word is at most this share of the frame height (checked by eye) |

## brand.json motion_graphics: motion graphics

Read by the motion graphics workbench (`crewcut render motion`), which hands the resolved block to every template as
`CC_CTX.brand.mg` (see `templates/motion/README.md`), and by the skill `motion`. All keys are optional; a pack that
leaves the block out gets the values below.

| Key | Neutral default | Meaning |
|---|---|---|
| `palette` | null | content colours, 3 to 5 `#RRGGBB`, the first is the accent. null: derived from `colors.accent`: the accent, its complement and its two neighbours at +-40 degrees of hue, all at the accent's lightness and chroma in OKLCH (chroma lowered only where sRGB cannot show the colour). The neutral accent gives #E4572E, #009CB7, #B87E00, #DD508E |
| `pastels` | true | true: a light version of each palette colour (OKLCH lightness 0.93) for grounds and gradients; a list: one `#RRGGBB` per palette colour; false: none (templates get the ground) |
| `ground` | `"soft"` | full-frame ground: a pack colour name or `#RRGGBB`; `"ink"` for a dark pack |
| `ink` | null | text on the ground: a colour name or `#RRGGBB`; null: `colors.ink`, or `colors.paper` when the ground is `"ink"` |
| `glass` | true | the frosted plate (`prompt_bar`) is allowed |
| `enter_s`, `exit_s` | 0.4, 0.25 | entrance and exit, seconds |
| `ease` | `"expo"` | entrance ease, one of `EC.EASES` (linear, easy, smooth, strong, out, expo, in, expoIn, soft, snap) |
| `drift_pct_per_s` | 2.0 | push per second while a picture holds |
| `blur` | shutter 180, samples 16 | motion blur of every comp (8 samples with `--draft`) |
| `plate3d` | glossy, bevel 0.05, extrude 0.2 | material of Blender plates (`big_claim`) |

Fonts come from `fonts.display` and `fonts.body` as for 2D: templates get family and weight, never a font name of
their own. The pack's font `files` are copied into a font folder for every motion render and EffectCraft finds them
through `EFFECTCRAFT_FONT_DIRS`, so a pack font needs no install. The look tokens (`colors`, `fonts`, `shape`,
`motion_graphics`) are part of every motion insert's cache key: change one and every motion insert renders again.

## rules/edit.md, rules/cut.md, rules/3d.md, rules/thumbnail.md

Learned rules of the steps edit, cut, 3D and thumbnail (format: `- YYYY-MM-DD: rule (source: …)`). The cut checks print
`rules/cut.md` as their manual list; `thumb_check.py` prints `rules/thumbnail.md`. The neutral pack ships a few general
rules dated 2026-11-16 with the source "Crewcut default". `examples/striq/rules/` shows a real, dated set.

## channel.json: idea, title, script, upload

Read by the skills `idea`, `title`, `script`, `upload` and their scripts (`idea.py`, `title_check.py`,
`script_check.py`, `package_check.py`). All four blocks are new (16 Nov 2026). Besides them the scripts read the
existing keys `language`, `country`, `reference_channels`, `closing_line`, `category_id` and `default_privacy`, and
`edit-style.json` `length_minutes` and `format`.

A key under `checks` sets how strict one style check is: `"error"` (blocks the card), `"warn"`, `"hint"` or `"off"`.

`idea` (method in `skills/idea/references/method.md`):

| Key | Neutral default | Meaning |
|---|---|---|
| `market_language`, `market_region` | `"en"`, `"US"` | the source market where formats are measured for saturation |
| `fresh_days` | 14 | uploads younger than this count as fresh in a scan |
| `long_min_seconds` | 181 | shorter videos count as Shorts and are left out |
| `outlier_x_median` | 2.0 | views against the channel's median that make an outlier |
| `outlier_per_sub` | 1.0 | views per subscriber that make an outlier |
| `small_channel_subs` | [1000, 100000] | subscriber range of a small channel |
| `breakthrough_per_sub` | 3.0 | views per subscriber that make a small channel's breakthrough |
| `gap_thin_views` | 30000 | in the user's market, a best video under this leaves a thin gap |

`title`:

| Key | Neutral default | Meaning |
|---|---|---|
| `max_chars`, `target_chars` | 70, 55 | ERROR above the maximum, WARN above the target (YouTube's own limit is 100) |
| `name_within` | 40 | the best-known name must start within this many characters |
| `names` | [] | names that may stand in front (an episode adds its tool with `--name`) |
| `acronyms` | [] | words in capitals that are not shouting (`"API"`) |
| `exclamations_max` | 1 | more exclamation marks are a WARN |
| `variants` | 3 | titles for the A/B test |
| `checks` | colon off, dash off, caps_words hint, factor off, question hint | `factor` is an "x times" number such as "10x" |

`script`:

| Key | Neutral default | Meaning |
|---|---|---|
| `words_per_minute` | 150 | speaking rate; with `length_minutes` it gives the target length in words |
| `sentence_max_words`, `sentence_avg_words` | 22, 14 | ERROR above the maximum (a teleprompter line; 25 before 23 Nov 2026), hint above the average |
| `paragraph_max_sentences` | 3 | a teleprompter paragraph is one breath |
| `hook_sentences` | 2 | the sentences that count as the hook |
| `name_within_sentences` | 4 | the tool (`--name`) must be named this early |
| `title_number_within_sentences` | 6 | the title's numbers must appear this early |
| `end_mentions` | [] | words that must stand in the last four sentences (an offer, the channel name) |
| `checks` | dash off, question_opening hint, hook_number off, title_number warn, paragraph warn | |
| `craft` (new, 23 Nov 2026) | see below | the script craft (`crewcut/craft.py`, `skills/script/references/craft.md`) |

`script.craft` sets the limits and levels of the craft check (hook in 30 seconds, depth pattern, spoken rhythm,
ending). Missing keys take the default; seconds become words through `words_per_minute`.

| Key | Neutral default | Meaning |
|---|---|---|
| `hook_seconds`, `limit_seconds` | 30, 45 | the hook's window and the latest place for an honest limit |
| `start_rate` | 1.2 | the first minute is dense: its words per minute against the base rate |
| `idea_seconds` | [40, 60] | one idea; reported in the stats as words |
| `part_max_seconds` | 180 | a longer part holds several ideas (hint) |
| `end_seconds` | 60 | the ending (the last part) |
| `questions_per_1000` | [2.5, 6] | questions per 1,000 words (target 3 to 5) |
| `short_share` | [15, 40] | percent of sentences of at most `short_words` (6) words |
| `checks` | greeting error; hook_number, roadmap, open_loop, limit, takeaways, questions, ending_length, cta, subscribe_once, loop_resolved warn; the rest hint | one level per rule: `error`, `warn`, `hint` or `off`. Rules: greeting, hook_number, roadmap, open_loop, stakes, limit, part_length, takeaways, concrete, signposts, short_share, questions, answers, objections, repeat, you_i, ending_length, cta, subscribe_once, ending_parts, loop_resolved |

`upload`:

| Key | Neutral default | Meaning |
|---|---|---|
| `tags_min`, `tags_max` | 5, 15 | tag count the channel wants (YouTube's limit is 500 characters) |
| `hashtags_max` | 3 | hashtags in the description (above 15 YouTube ignores all) |
| `main_link`, `link_within_lines` | null, 3 | a link (or its start) that must stand in the first lines of the description |
| `required_text` | [] | fixed text every description contains |
| `description_footer` | null | file in the pack folder that ends every description word for word (about the creator and the company); the check fails when it is missing or changed |
| `publish_time`, `timezone` | null, null | the channel's fixed upload time, such as `"08:00"` and `"Europe/Berlin"` |
| `playlist` | null | playlist every episode goes into (planned in the upload command) |
| `checks` | dash off | |

## voice.md: word lists

`voice.md` is prose for the Writer, plus optional lists that the checks read. A list is a `## heading` with one item
per line. Words match whole words, ignoring case; a trailing `*` matches any ending (`compan*`). The neutral pack has no
lists, so these checks then fall back to judgement by hand.

| Heading | Item format | Read by | Effect |
|---|---|---|---|
| `## Words to avoid` | `- phrase` | `script_check.py`, `title_check.py` | ERROR in a script, WARN in a title |
| `## Words to use` | `- phrase` | `script_check.py` | hint when none of them appears |
| `## Title hooks` | `- label: word, word` | `title_check.py` | each label found counts as a hook (+6 points) |
| `## Title words to avoid` | `- label: word, word` | `title_check.py` | ERROR |

## voice/: your own spoken words

One to three Markdown files with the plain spoken text of your own videos: `crewcut brand voice add <video link>`
(the video's captions, through yt-dlp) or `crewcut brand voice add <recording>` (transcribed on this machine). Each
file names its source and method; the oldest goes when a fourth comes. The Writer gives them to the Humanizer pass as
the voice sample, so a script keeps your words and rhythm. Updates never touch them; delete a file to drop it.

## rules/idea.md, rules/title.md, rules/proof.md, rules/script.md, rules/upload.md

Learned rules of the first steps, in the same format as the other rule files. The agents read them before each step;
the checks do not parse them. The neutral pack ships four general rules per step, dated 2026-11-16, source "Crewcut
default". `examples/striq/` shows a real, dated set and the values above as one channel set them (`--pack
examples/striq` on any check).
# Fixed thumbnail references

`thumbnail.json` can name `reference_photo` and `style_reference` as paths relative to `brand/`.
`crewcut thumbnail make` automatically attaches the person first (unless `face` is false), then the style reference,
then episode images from `--ref`. Duplicate paths are removed. A configured missing file or path outside its root
stops generation before choosing a generator or requesting money. Personal photos belong only in the private pack.
The pack's thumbnail rules can explicitly request reuse of the reference layout; otherwise it supplies style only.

### Preserve background geometry

`motion_graphics.background.mode` accepts `pools` (existing default), `plain` or `shapes`.
`shapes` requires a nonempty `layouts` array for every used format (`landscape`, `portrait`, `stage`).
Each item has `kind` (`ring`, `square`, `plus`, `bar`, `circle`), `x`, `y`, `size`,
and optionally `thickness`, `blur`, `rotation`, `spin`, `vx`, `vy`, `opacity`, `color` or `palette`.
Positions and velocity use frame fractions (per second for velocity); size, thickness
and blur use the shorter frame dimension. Rotation and spin use degrees and degrees/second.
Place large cropped foreground forms before smaller sharper distant ones as the reference requires.
The layout belongs to the private style pack. No channel's design is a public default.
Transparent overlays never receive a background. Missing shape layouts fail explicitly.

`motion_graphics.accent_area_limit` defaults to `0`. A pack may set it up to `0.3`:
when the entire coloured area occupies no more than this fraction of the whole frame,
the palette check allows a single accent hue. Larger coloured areas retain the normal
balance check. Reports retain both the whole-frame area and the coloured-pixel ratio.
This preserves sparse brand accents on neutral imagery without bypassing craft review.

### Original HTML scene bundles

A private `brand/templates/2d/NAME.html` may have `NAME.scene.json` beside it:
`{"contract":"video-studio","files":["legacy/core.js","legacy/style.css","legacy/fonts/display.otf"]}`.
Declare every dependency, including the source HTML, images and fonts. Paths stay within
this template folder. Their content and the manifest invalidate the render cache.
The default contract is `native`. `video-studio` adapts DATA/frames/format to
DATEN/bilder/quer/hoch and waits for SZENE_BEREIT. It preserves the original page's
layout and animation code. Legacy scenes require 25 fps; unsupported frame rates fail.
Original sources and personal branding stay private. Importing does not start production.
