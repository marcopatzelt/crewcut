# Show formats: systems that work, used again and again

A show format is a recipe for a whole episode that a channel fills again and again: a tool test every week, a claim
check as a Short, a file on what an agent did wrong. Crewcut keeps the formats in a library. When you start an episode,
you paste what you have (a tool, a link, a tweet or an idea) and pick **Long**, **Short** or **Auto**. The Scout reads
the input, picks the format that fits and says in two to four sentences why, with the runner-up. Then the Writer
writes the **full script** from the format's template: every sentence, not a form. The style gate checks it as usual.

The idea behind it, in Alex Hormozi's words, is "winning formats": forms that can be filled again and again, and
topics that come from what you did, not from a search. Hormozi sorts topics into five types: far past, recent past,
present, trending and manufactured (made for the video). Every episode and every idea card carries one of them.
(Source: Alex Hormozi, *$100M Leads*, part 4 "Post Free Content", read on his podcast *The Game*, 2023; our summary.)

Code: `crewcut/showformats.py` (library, pick, prompt block), `crewcut/conductor/plan.py` (the plan job and what
follows), `crewcut/ideas.py` (idea cards), `crewcut/scoreboard.py` (which formats win), `host/ideas-export.py`.

## The library

Two files are merged: the neutral pack's examples `packs/neutral/show-formats/formats.json` and your own
`<studio>/brand/show-formats/formats.json`. A format in your file with the same id replaces the example. Template
paths are relative to the folder of the file that names them, so your templates sit next to your `formats.json`.

```json
{"schema": 1, "formats": [
  {"id": "tool-test", "name": "Tool test", "length": "long",
   "kinds": [{"id": "free-vs-paid", "name": "Free against paid", "when": "A free tool claims to replace a paid one."}],
   "when": "The input is a tool, an app, a repository or a model the viewer could use or pay for.",
   "keywords": ["tool", "app", "free", "paid"],
   "topic_types": ["manufactured", "trending"],
   "structure": [{"name": "Opening", "purpose": "The result first …", "seconds": 30},
                 {"name": "Unit 1", "purpose": "Hook, proof, punch line; stands alone as a Short.", "seconds": 30}],
   "script_template": "templates/tool-test.script.md",
   "cue_template": "templates/tool-test.cues.md",
   "testplan_template": "templates/tool-test.testplan.md",
   "packaging_rules": ["The viewer's stake is in the title."],
   "title_formulas": ["I tested X so you don't pay for Y"],
   "thumbnail_formats": ["house-face-result"],
   "checker_format": "lang", "cadence": "weekly",
   "strong": "One line of evidence why this format works."}]}
```

| Key | Required | Meaning |
|---|---|---|
| `id` | yes | lower-case letters, digits and dashes; stored in the episode as `show_format` and `form` |
| `name`, `when` | yes | the name, and what input fits (the Scout and the keyword guess read it) |
| `length` | yes | `long` or `short`; a short format makes the episode an original Short |
| `topic_types` | yes | one or more of `far_past`, `recent_past`, `present`, `trending`, `manufactured` |
| `structure` | yes | the ordered units, each with `name` and `purpose` (and `seconds` if you like) |
| `script_template` | yes | the full-script template the Writer starts from |
| `cue_template`, `testplan_template` | no | a cue sheet template ([cue sheets](cue-sheets.md)) and a test plan template |
| `kinds` | no | variants of the format, each `{id, name, when}` |
| `keywords` | no | words that point to this format in an idea's text (the keyword guess) |
| `packaging_rules`, `title_formulas`, `thumbnail_formats` | no | for PACKAGING: rules, named title formulas, thumbnail format ids from `crewcut thumbnail formats` |
| `checker_format` | no | `lang` or `short` for the style checker; default from `length` |
| `gate_on` | no | `script` (default): the gate checks the full script, then the cue sheet is derived; `cues`: the Writer writes the full script and derives the cue sheet in the same run, and the gate checks the cue sheet (for a studio checker that takes only cue sheets for long videos) |
| `cadence`, `strong` | no | how often (e.g. `weekly`), and the evidence line |

A broken format is left out and named with a clear reason (`crewcut formats check`, also `problems` in
`GET /api/formats`). `[formats]` in `config/crewcut.toml`: `enabled = false` switches the system off (New Episode then
starts the idea step as before), `include_examples = false` leaves out the neutral examples.

```
crewcut formats [list]                     the library (studio formats replace examples with the same id)
crewcut formats show <id>                  one format as JSON, with the full template paths
crewcut formats check                      every problem of both files
crewcut formats choose <episode> <id> [--topic-type T] [--input tool|link|tweet|idea]   the Scout records its pick
crewcut formats score [--json]             the scoreboard (below)
```

The neutral pack has three generic examples: `tool-test` (long), `claim-check` (short) and `incident-file` (short).

## New Episode

`POST /api/episodes` takes `{"text", "length": "long"|"short"|"auto" (default auto), "show_format"?}`; the old body
`{"text"}` still works. The project gets `length`, and with a format `show_format`, `form` and `length` of the format.
`length: "short"` makes an original Short at once.

While the library is not empty, the first job is the Scout's **plan** (step idea, `data.plan`):

1. classify the input (tool, link, tweet, idea), read links, find the real material;
2. pick the format (or check the given one) and the topic type, record it with `crewcut formats choose` (with Auto a
   short format turns the episode into an original Short);
3. write `brief/FORMAT-v001.md` (`format:`, `length:`, `topic_type:`, `input:`, `reason:` in 2 to 4 sentences,
   `runner_up:`), `brief/BRIEF.md`, `brief/TESTPLAN-v001.md` when the format has a test plan, and
   `brief/PACKAGING-v001.md` with three title and thumbnail pairs from the format's named formulas.

When the plan ends, the conductor posts the pick and the reason in the chat (the episode head shows it too), marks the
idea step done and gives the script step to the Writer, who writes `brief/SCRIPT-v001.md` as a full script from the
template: a long video is a chain of units of about 30 seconds, each built like a Short (hook, retain, reward), numbers
early, no greeting, recap or goodbye; a Short is the own case with a number in sentence 1, the proof, the punch line,
no ask. Numbers come only from material and tests that ran; where a test has not run, the script keeps a placeholder
such as `[ZAHL nach Test]`. Then the [style gate](architecture.md#the-style-gate) runs unchanged on the newest script.
When it passes and the format has a `cue_template`, the Writer derives the cue sheet (`DREHZETTEL-vNNN.md` in a German
studio, else `CUES-vNNN.md`), the gate checks it too, and only then comes the script card. After the script card the
episode goes on with its normal steps; the title step starts from `PACKAGING-v001.md`.

The system prompt of every job in such an episode carries the format block: structure, rules, formulas, template
paths and, when the studio has it, `brand/references/HORMOZI-NIE-OHNE-CONTENT.md` (where topics come from). With a
voice profile or reference moves, the Writer, the Critic and the Showrunner also get the voice block and the head of
the learning file ([hormozi-voice.md](hormozi-voice.md)).

## Idea cards

Ideas from outside the app come in as files, because the container sees only the studio. The host-side exporter
`host/ideas-export.py` (standard library only) reads a scout ranking and saved links and writes
`<studio>/inbox/ideas/<id>.json`:

```json
{"id": "scout-gh-example-tool", "source": "scout", "url": "…", "title": "…", "summary": "…",
 "signals": {"stars": 900, "velocity_day": 80}, "topic_type": "trending", "suggested_format": null, "created": "…"}
```

```bash
python3 host/ideas-export.py --studio ~/Crewcut --scout path/to/scout-2026-11-27.json --top 12
python3 host/ideas-export.py --studio ~/Crewcut --braindump path/to/links --project crewcut
```

- `--scout FILE` (repeatable): `{"date", "ranked": [{"key", "kind", "name", "url", "desc", "sig", "total", "excluded", …}]}`;
  the best `--top` entries that are not excluded (`--min-total` for a floor). Topic type: trending.
- `--braindump DIR`: one folder per saved link with `eintrag.json` and its result `ergebnis` (`titel`, `was`, `warum`,
  `projekte: [{"id", "idee", "wo"}]`, `tags`, `prioritaet`); only links whose projects contain `--project`
  (default `crewcut`). Topic type: present.
- An idea that exists is left alone (dedupe by id); `--refresh` rewrites open ones. A started or dismissed idea is never
  rewritten: Crewcut writes the decision back into the file.

Run it by hand or from a timer of your own (not part of the repository), for example a systemd user timer that runs the
command above once a day. In the app, a loader (`crewcut/ideas.py`, every minute and on `GET /api/ideas`) imports the
files into the `ideas` table with status open, started or dismissed. Without a suggestion in the file it makes a first
guess from the format library by keyword rules (no model call), marked `suggestion: "rule"`: a suggestion, not a pick.
The home shows the open ideas with source, title, summary and the suggested format, with **Start episode** (the same
path as New Episode, with the idea's text, its suggested format and its length) and **Dismiss**. Loading never starts
a job. `crewcut ideas [list|load]` does the same on the command line.

## Scoreboard

`crewcut formats score`, `GET /api/scoreboard` and the table "Formats" on the home group episodes by `show_format`
(else `form`) and read only measured numbers:

- the newest `review/results-*.json` of each episode (`crewcut youtube results`): views, average view percentage,
  subscribers gained per 1,000 views;
- for Shorts without such a file, their newest row in `studio/shorts.tsv` (column `form`);
- the median drop per minute of the units in `analytics/retention-units.json`, when it exists;
- click-through rate is not in the YouTube Analytics API: it shows as missing unless the episode has
  `analytics/ctr.json` (`{"ctr": 0.051, "impressions": 12000}`, copied from YouTube Studio).

Per format: episodes, measured episodes, median views, median view percentage, subscribers per 1,000 views, and a hint:
**more of this** when at least two episodes are measured and the format beats the channel median on two of the three
metrics; **too little data** below two measured episodes; else **watch**. Every crew job gets one line per measured
format in its channel brief, so the Scout and the Writer see which formats win. It is a hint, never a rule.

## Limits

- The plan and the script are agent work: their quality depends on the engine and on the material. The format system
  sets the frame and the checks; it never invents numbers.
- The keyword guess for ideas is simple word overlap; the Scout's pick in the plan decides.
- Converting an episode between long and Short works only while no later step (title, script, record, edit) started.
