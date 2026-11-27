# Voice profile, reference moves and the learning loop

A channel that writes in the manner of a reference speaker (in the studio this was built for: Alex Hormozi's way of
speaking and his structure, carried into German) needs three things the style gate alone does not give:

1. **A voice profile**: how the reference speaker actually speaks, measured from his transcripts, and target bands for
   the channel's own scripts, each with its reason.
2. **Reference moves**: real passages of the speaker for each move of a video (hook, opening, proof, transition, punch
   line, ending, a Short's first and last line), each with the pattern in one line and a transfer line in the channel's
   language. The Writer models every hook and punch line on named passages.
3. **A learning loop**: after every gate round and every retention measurement, one file collects what the critics
   found most often, which units held viewers and which scripts passed. The Writer reads its head before every script.

Code: `crewcut/voicemetrics.py` (the metrics), `crewcut/voicecheck.py` (the checks in the gate), `crewcut/lernstand.py`
(the learning loop), `host/voice-profile.py` and `host/reference-moves.py` (run on the host, next to the transcripts),
`crewcut/conductor/prompts.py` (what the Writer is told). The idea of a video as units of hook, retain and reward is
Alex Hormozi's (*$100M Leads*, part 4 "Post Free Content", read on his podcast *The Game*, 2023; our summary).

## Settings

`[style_gate]` in `<studio>/config/crewcut.toml` (or `script.style_gate` in the style pack's `channel.json`). Paths are
inside the studio.

| Key | Default | Meaning |
|---|---|---|
| `voice` | `block` | `block`: a failing check of severity "error" fails the gate; `hint`: every finding is a hint; `off` |
| `voice_profile` | none | the profile (below); without it there are no voice and structure checks |
| `reference_moves` | none | the folder with the reference moves (`hook.md`, `intro.md`, …) |
| `learning_file` | `library/learnings/script-learning.md` | the learning file |
| `gold_dir` | none | where passing scripts are copied as gold candidates; none = no copies |
| `learning_labels` | `[]` | files that name the finding groups: markdown lines `- P-S1 [..] Question?`, JSON `{"labels": {id: text}, "aliases": {flag: id}}` or `{"checks": {id: {"titel"}}}`; an alias joins a unit flag and its question into one group |
| `learning_ignore` | `[]` | finding ids or unit flags that are only hints in this studio |
| `rule_after` | `3` | a finding group with this many findings gets one rule card; 0 = never |
| `rules_per_run` | `2` | at most this many new rule cards per run; the rest follow at the next runs |
| `companion_prefix` | `LEARN-` | the learning companion of `brief/SCRIPT-v002.md` is `brief/LEARN-SCRIPT-v002.md` |

The companion has the prefix in front, so no tool that looks for `SCRIPT-v*.md`, `CUES-v*.md` or `SHORT-v*.md`
mistakes it for a script.

## 1. The voice profile

`host/voice-profile.py` reads transcripts read-only: a SQLite database with `videos(id, title, duration_s, views, kind,
source, dup_of)` and `chunks(video_id, idx, start_s, text)`, or a folder of `<id>.json` word files and `<id>.txt`
texts. It measures every video, takes the top share by a score (`--scores` CSV with `id` and `outlier`, for example
views divided by the channel's usual views; without it, views) and writes the medians and quartiles for long videos
and Shorts separately:

| Metric | What it counts |
|---|---|
| `sentence_words_median`, `_p25`, `_p75`, `_p90` | words per sentence (only transcripts with sentence marks) |
| `short_share` | share of sentences with at most 8 words |
| `numbers_per_minute`, `first_number_s`, `first_number_word` | digits and number words (version names such as "Opus 4" do not count) |
| `you_per_100`, `i_per_100` | "you" and "I" words per 100 words |
| `questions_per_minute`, `imperative_share` | questions; sentences that are commands |
| `fillers_per_100` | filler words ("um", "basically"; German "halt", "quasi", …) |
| `words_per_minute` | pace (real times only) |
| `transitions_per_minute`, `first_transition_s`, `unit_seconds_median` | counted transitions ("number two", "Punkt zwei") and the time between them |

`--calibrate NAME=FILE` measures the channel's own texts too (a published video's words, a caption file, a script) and
`--targets FILE` gives the target bands, each `{"min", "max", "severity": "error"|"hint"|"info", "why"}`, plus
`script` (`lang`, `wpm` the speaker's words per minute, `bullet_seconds`, `min_sentences`) and `check_names` (the ids'
prefixes, default `VOICE` and `STRUCTURE`). A metric without a band gets a proposal from the reference's quartiles,
as a hint. Word lists exist for English and German (`LEXICON` in `voicemetrics.py`); a profile may add words.

```bash
python3 host/voice-profile.py --db corpus.db --source youtube --scores long.csv --scores shorts.csv \
    --calibrate own=studio/episodes/014/work/words-v006.json --targets targets.json \
    --out studio/brand/references/<style>/voice/profile.json
```

## 2. Reference moves

`host/reference-moves.py candidates` pulls candidate passages for each move from the best videos, word for word, with
the link to the chunk where the passage starts. A person or an agent picks 15 to 30 per move and writes the pattern and
a transfer line for each (`picks.json`); `render` writes one file per move, the passage in straight double quotes with
its source number, everything else in other quotes, so a quote checker can verify every passage against the
transcript. The files are study material for a private studio: they quote the speaker and do not belong in a
repository.

## 3. The checks in the gate

After the studio's checker ran, the gate adds the voice and structure checks to its result, in the checker's
interface version 1, so the card, the chat and the Writer's round show them like any other check (`kind` `auto` fails,
`hinweis` informs the Critic). Each failing check carries `points`: the line, why it breaks the band and, where a
machine can, a rewrite (a long sentence split at its joint, a line without its filler words). The stop on an
unchanged point works on them too.

- **Voice** (`<voice>:<metric>`): every metric with a band in `targets.long` or `targets.short`. Below
  `min_sentences` spoken sentences every voice check is a hint.
- **Structure, long** (`<structure>:…`): `intro` proof, promise and plan, the opening done by about 0:35; `window` a
  number or the promise before 0:20 and no background (times from the word position at the speaker's `wpm`); `units`
  hook, retain and reward in every unit; `loops` every hook has a number, a contrast or a question, every bridge is a
  question; `rewards` no gap over `reward_gap_s` (default 45) without a number, a proof or a punch line; `ending` no
  recap and no goodbye in the last 60 s (not for an excerpt without a close).
- **Structure, Short**: `case` sentence 1 is a case with a number and no question; `proof` by 0:15; `punch` the last
  sentence has at most 8 words; `no-ask`.

A cue sheet ([cue-sheets.md](cue-sheets.md)) is read as it will be spoken: the fixed lines are the sentences, every
bullet takes `bullet_seconds` and its numbers count. `crewcut voice check <file> [--format lang|short] [--json]`
runs the same checks for the Writer (exit 1 when one fails). A broken profile never stops the gate: it becomes one
hint.

## 4. What the Writer is told

While the studio has a profile or reference moves, the Writer, the Critic and the Showrunner get a voice block in the
script and title steps and in every job of a show-format episode: read the profile and the reference moves of the
format (long: hook, intro, proof, transition, punch, ending; Short: short-first, proof, punch, short-end), model every
hook and punch line on one or two named passages (file and number, never the words or the topic), and write the
learning companion next to every script version: per unit Hook / Retain / Reward, the passage it copies (with its
link) and the rule it fulfils. The plan job reads `hook.md` and `intro.md` for the packaging pairs. The head of the
learning file (findings and units) is in the same prompts.

## 5. The learning loop

`crewcut lernstand [--no-cards] [--print]` writes the file now; the gate does it after every round, the retention
units after every run (`crewcut retention units`).

1. **Most frequent findings**: from `*.kritik.json` (sentences without value with their question id, unit questions
   answered no, yes-no questions answered no), `*.zweitmeinung.json` (the second opinion, grouped into "wrong or
   misleading" and "unclear or not needed") and `review/critic-*.md` of scripts without such a file (quoted lines that
   say no). Top 10 by count, each with an example and the best fix: the newest "done" note of a later review, else the
   Critic's rewrite.
2. **Best and worst units**: from every episode's newest `analytics/retention-units.json`, units of at least 15 s,
   ranked by drop per minute against the median unit of the same video, with the hook sentence.
3. **Gold candidates**: when the gate passes, every passing script is copied into `gold_dir` as
   `CANDIDATE-NNN-<episode>-<file>` (German studios `KANDIDAT-…`) with its Critic answers and a score file
   (`100 / (1 + hints left)`); the same content is never copied twice.
4. **Rule cards**: a group with a name (`learning_labels`) that reaches `rule_after` findings gets one rule card
   (`approvals.propose_rule`, step script); a yes writes it into `brand/rules/script.md`. The state is in the learning
   file's `.json` next to it, so each group is proposed once.

## Limits

- Every count comes from word lists: numbers, commands, fillers and transitions are found, not understood. The bands
  are the studio's decision; the reference only shows where the speaker is.
- Times in a script are estimates from the word count; a cue sheet's bullets are a fixed number of seconds each.
- The structure checks find the form (a count word, a short last line), not whether the line is good: that stays the
  Critic's work.
- The learning file is a hint. One episode with many review rounds can fill the top findings alone.
