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
| `keywords_max` (new) | 8 | keywords per video (style check `keyword-count`, CHECK above) |
| `text_cards_max` | 3 | different text sources (headline, post) per video (CHECK above) |
| `text_share_max` (new) | 0.4 | share of full-screen inserts that are text cards (ERROR above) |
| `italics` | false | false: italic type in the scene templates is an ERROR |
| `min_text_px` | 40 | font sizes under this in the scene templates are a CHECK |
| `music` | `"none"` | `none`, `generated` or `own`; with music, the plan needs `sound.music_source` |
| `music_db`, `duck` | -16.0, true | music bed level under the voice, and ducking while someone speaks |
| `loudness_lufs`, `true_peak_db` | -14.0, -1.5 | export target and true-peak limit |
| `loudness_window_lu` (new) | [-2.0, 0.5] | allowed loudness relative to the target (style check `loudness`) |
| `graphics_mix` | 2d 0.7, 3d 0.0, text 0.3 | target share of insert kinds (NOTE only) |
| `pace_cuts_per_minute` | 8 | shots per minute (NOTE only) |
| `speaker_min_seconds` | 2.0 | speaker never shorter than this between two full-screen parts (ERROR) |
| `speaker_open_close_seconds` (new) | 3.0 | speaker at least this long at the start and in the last 30 s (ERROR) |
| `speaker_share_min`, `speaker_share_max` (new) | 0.4, 0.95 | share of the video with the speaker on screen (CHECK outside) |
| `speech_speed` (new) | 1.0 | speed of the speaker cut |
| `zoom_base`, `zoom_punch` (new), `zoom_max` | 1.0, 1.1, 1.15 | speaker zoom: normal, punch-in, never more than |
| `end_card` | true | the video ends with an end card |
| `cut_words` (new) | all empty | language data for the cut checks, see below |

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
| `sentence_max_words`, `sentence_avg_words` | 25, 14 | ERROR above the maximum, hint above the average |
| `paragraph_max_sentences` | 3 | a teleprompter paragraph is one breath |
| `hook_sentences` | 2 | the sentences that count as the hook |
| `name_within_sentences` | 4 | the tool (`--name`) must be named this early |
| `title_number_within_sentences` | 6 | the title's numbers must appear this early |
| `end_mentions` | [] | words that must stand in the last four sentences (an offer, the channel name) |
| `checks` | dash off, question_opening hint, hook_number off, title_number warn, paragraph warn | |

`upload`:

| Key | Neutral default | Meaning |
|---|---|---|
| `tags_min`, `tags_max` | 5, 15 | tag count the channel wants (YouTube's limit is 500 characters) |
| `hashtags_max` | 3 | hashtags in the description (above 15 YouTube ignores all) |
| `main_link`, `link_within_lines` | null, 3 | a link (or its start) that must stand in the first lines of the description |
| `required_text` | [] | fixed text every description contains |
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
