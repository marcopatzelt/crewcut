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
                 {"name": "Unit 1", "purpose": "Hook, proof, punch line.", "seconds": 30}],
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
| `kinds` | no | variants of the format, each `{id, name, when}`, optionally with its own `structure` and its own `script_template`, `cue_template`, `testplan_template` (a kind's own wins); the episode keeps its kind in `format_kind` |
| `keywords` | no | words that point to this format in an idea's text (the keyword guess) |
| `packaging_rules`, `title_formulas`, `thumbnail_formats` | no | for PACKAGING: rules, named title formulas, thumbnail format ids from `crewcut thumbnail formats` |
| `checker_format` | no | `lang` or `short` for the style checker; default from `length` |
| `gate_on` | no | `script` (default): the gate checks the full script, then the cue sheet is derived; `cues`: the Writer writes the full script and derives the cue sheet in the same run, and the gate checks the cue sheet (for a studio checker that takes only cue sheets for long videos) |
| `cadence`, `strong` | no | how often (e.g. `weekly`), and the evidence line |
| `title_patterns` | no | regular expressions that mark a title as this format, for the Scout's format test (`idea.py formats --library-patterns`) |
| `traffic_type` | no | `browse` (home page and feed, the default) or `search`: the scoreboard judges a search format on its first 28 days |

A format whose script or cue template waits for a test (a `[ZAHL nach Test]`, `[ERGEBNIS: …]` or `[NUMBER after
test]` slot above `---`) needs a `testplan_template` (its own or, for a kind, its kind's), so the test runs before the
script. A broken format is left out and named with a clear reason (`crewcut formats check`, also `problems` in
`GET /api/formats`). `[formats]` in `config/crewcut.toml`: `enabled = false` switches the system off (New Episode then
starts the idea step as before), `include_examples = false` leaves out the neutral examples.

```
crewcut formats [list]                     the library (studio formats replace examples with the same id)
crewcut formats show <id>                  one format as JSON, with the full template paths
crewcut formats check                      every problem of both files
crewcut formats choose <episode> <id> [--kind K] [--topic-type T] [--input tool|link|tweet|idea]   the Scout's pick
crewcut formats test <episode> [--wait] [--json]   test plan, test result, whether the script waits; --wait: the Writer starts once the result is there
crewcut formats score [--json]             the scoreboard (below)
```

The neutral pack has three generic examples: `tool-test` (long), `claim-check` (short) and `incident-file` (short).

## New Episode

`POST /api/episodes` takes `{"text", "length": "long"|"short"|"auto" (default auto), "show_format"?}`; the old body
`{"text"}` still works. The project gets `length`, and with a format `show_format`, `form` and `length` of the format.
`length: "short"` makes an original Short at once.

While the library is not empty, the first job is the Scout's **plan** (step idea, `data.plan`):

1. classify the input (tool, link, tweet, idea), read links, find the real material;
2. pick the format (or check the given one), its kind when it has kinds, and the topic type, record it with
   `crewcut formats choose` (with Auto a short format turns the episode into an original Short). The plan task names
   the kinds the last episodes of the format used, newest first, so the Scout switches kinds instead of repeating one;
3. write `brief/FORMAT-v001.md` (`format:`, `kind:`, `length:`, `topic_type:`, `input:`, `reason:` in 2 to 4
   sentences, `runner_up:`), `brief/BRIEF.md`, `brief/TESTPLAN-v001.md` when the format has a test plan, and
   `brief/PACKAGING-v001.md` with three title and thumbnail pairs from the format's named formulas. The test plan
   fixes the cases and the counting before any run and never the result (no "expected break"); a step that only makes
   sense after a certain result is written as "only if test N shows …". Packaging stays provisional until the test:
   words that depend on the result are `[ERGEBNIS: …]`, and a title formula with a condition (for example "only after
   a measured Claude win") is used only when the result meets it.

**Test first, then the script.** Alex Hormozi: "Do stuff, then talk about what you did or what happened." (*$100M
Leads*, part 4). When the plan ends, the conductor posts the pick and the reason in the chat (the episode head shows it
too) and marks the idea step done. A format with a test plan (its own or its kind's `testplan_template`, or a
`brief/TESTPLAN-vNNN.md` in the episode) now waits:

- the script step is `waiting`, and a card asks "Run the test plan now?". Yes: the Scout runs the free tests, counts as
  the plan fixed it, asks with a spend card before anything costs money, and writes the result file. No: the user drops
  the result file;
- the result file is `brief/TESTERGEBNIS-vNNN.md` (also accepted: `MESSKARTE-vNNN.md`, `TEST-RESULT-vNNN.md`): per test
  the measured value, its source, minutes and cost, what held and what broke, the verdict;
- as soon as the result file is there and no job of the episode runs, the worker (`conductor/plan.py`, `tick`) gives
  the script step to the Writer. `crewcut formats test <episode> --wait` arms the same wait for an episode that is
  already in the script step;
- a Writer job in the script step is refused while the result is missing (`crewcut job add`), and the Writer's task
  says to write nothing before it.

A format without a test plan goes to the Writer at once. The Writer writes `brief/SCRIPT-v001.md` as a full script
from the template (a kind's own template wins), reading the test result first: a long video is a chain of units of
about 30 seconds, each built like a Short (hook, retain, reward; whether it also works alone as a Short is only a
hint), numbers early, no greeting, recap or goodbye; a Short
is the own case with a number in sentence 1, the proof, the punch line, no ask. Numbers and results come only from the
test result and the material. The script tells what the test found: a unit that depends on a result that did not
happen is left out or takes the alternative the structure names.

**No placeholder reaches a review.** A script or cue sheet whose spoken part (above `---`) has a placeholder
(`[ZAHL nach Test]`, `[ERGEBNIS: …]`, `[NUMBER after test]`, `[Zahl]`, any bracket that says "after the test" or "as
measured", and a template slot left behind such as `[Betrag]`, `[Pointe …]`, `[… mit Zahl]` or `<…>`) fails
the [style gate](architecture.md#the-style-gate) at once with the check `PLACEHOLDER`, before the studio's checker and
before any Critic round. A word list never catches up with the templates, so every bracket in a script whose text is a
gap of one of the library's script or cue templates counts too (`showformats.template_slots`: a template with
`[Bezahl-Tool]` or `[dem schweren Fall]` makes the same bracket in a script a placeholder; case, spacing and closing
punctuation do not count). Not gaps: a picture or stage cue (`[Bild: …]`, `[Szene 3: …]`, `[Gesicht]`), the first
bracket of a cue-sheet bullet (`• Beleg: [Messkarte] …` names what is on screen), a citation marker (`[3]`) and
anything below `---`; `crewcut job add --identity critic --step script` is refused for it. While the test result is
missing, the gate holds the script and the conductor waits for the result as above; with the result there, the Writer
gets a round to fill every placeholder from it. The learning file counts no finding on a script with placeholders.

Then the style gate runs on the newest script. When it passes and the format has a `cue_template`, the Writer derives
the cue sheet (`DREHZETTEL-vNNN.md` in a German studio, else `CUES-vNNN.md`; the bullets come from the material and the
test result, not from shortening the full text), the gate checks it too, and only then comes the script card. After
the script card the episode goes on with its normal steps; the title step starts from `PACKAGING-v001.md`, fills its
`[ERGEBNIS: …]` from the test result and checks every pair against it.

**A pair the test reverses never reaches the title card** (`crewcut/titlepairs.py`). Packaging is written before the
test, so a pair can promise a direction the test turns around ("not as current as you think", and the test found it
more current). After the test the title step writes the next `brief/PACKAGING-vNNN.md` with one line per pair (each
pair a section `## Pair A …` or `## Paar A …` with its `- Title:` or `- Titel:` line):

    - Test: carries                  German: - Test: trägt
    - Test: reverses, <why>          German: - Test: dreht um, <warum>

A pair reverses when its title or image says the opposite of what was measured, or when its formula's condition is
not met; it is dropped or rebuilt in the measured direction. The title step's Critic gets the test result with this as
a hard question. `crewcut card propose --kind title` is refused while the newest packaging is older than the test
result or leaves a pair unchecked, and an option that is the title of a reversed pair is refused; the thumbnail step
never builds the image of a reversed pair. An episode without a show format, a test result or a packaging file with
pairs is not checked.

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

Your own week is a source too: `--recent-episodes` makes one card per studio episode that was published or measured
in the last `--days` days (default 7; episodes still in production are already topics), `--recent-git DIR` one card per own repository with its commit subjects of those days, and
`--braindump DIR --days 7` only the links saved in that time. Their topic type is recent past: "Look at your calendar
for the last week" (Hormozi, *$100M Leads*, part 4).

```bash
python3 host/ideas-export.py --studio ~/Crewcut --recent-episodes --recent-git ~/dev/my-tool --days 7
```

Run it by hand or from a timer of your own (not part of the repository), for example a systemd user timer that runs the
command above once a day. In the app, a loader (`crewcut/ideas.py`, every minute and on `GET /api/ideas`) imports the
files into the `ideas` table with status open, started or dismissed. Without a suggestion in the file it makes a first
guess from the format library by keyword rules (no model call), marked `suggestion: "rule"`: a suggestion, not a pick.
The home shows the open ideas with source, title, summary and the suggested format, with **Start episode** (the same
path as New Episode, with the idea's text, its suggested format and its length) and **Dismiss**. Loading never starts
a job. `crewcut ideas [list|load]` does the same on the command line.

## Scoreboard

`crewcut formats score`, `GET /api/scoreboard` and the table "Formats" on the home group episodes by `show_format`
(else `form`) and read only measured numbers. The fair numbers are a video's **first days**, never today's total
(skills/idea/references/method.md, section 10):

```bash
crewcut youtube results <episode> --first 7     # the first 7 days from the publication day (export/upload-result.json)
crewcut youtube results <episode> --first 28    # the same for 28 days; --start gives the day for older videos
```

Each report keeps its `window` and, when YouTube answers, the share of views from search and from browse features.
Per episode the scoreboard computes:

- `x_7d` and `x_28d`: views in those days against the median of the same days of the channel's last 10 videos of the
  same length (long or Short) before it;
- `ctr_rel` and `avp_rel`: click-through rate and average view percentage against the same videos. Click-through rate
  is not in the YouTube Analytics API: it shows as missing unless the episode has `analytics/ctr.json`
  (`{"ctr": 0.051, "impressions": 12000}`, copied from YouTube Studio);
- the diagnosis from the two (format carries; packaging carries, script or opening weak; content carries, packaging
  weak; weak for us);
- the traffic type: from the report's shares, else `traffic_type` in project.json or the format library, else browse.
  Search formats are judged on `x_28d`, browse formats on `x_7d`;
- subscribers gained per 1,000 views and the median drop per minute of the units (`analytics/retention-units.json`).

Without window reports the newest `review/results-*.json` (or, for Shorts, their newest row in `studio/shorts.tsv`)
gives total views against the channel median of the same length (Shorts against Shorts, long against long), marked
"total views" because it is unfair to young videos. Subscribers per 1,000 views are compared within the same length
too, and the channel line shows long videos and Shorts separately.

Per format: **too little data** under two judged episodes; with two or three a **stop early** when the first two are
both under 0.5 and both "weak for us", else **watch**; from four on, over the last four: **more of this** at a median
of at least 1.2 (1.0 for a format that already runs) or with more subscribers per 1,000 views than the channel,
**drop** under 0.8 without that, else **change** after the diagnosis and measure two more. A comparison that mixes
videos from before and after November 2026 is marked (public views include co-views since then). Every crew job gets
one line per measured format in its channel brief, so the Scout and the Writer see which formats win. It is a hint,
never a rule.

## Idea cards from the Scout

The Scout writes idea cards itself: `python3 skills/idea/scripts/idea.py rank review/idea-*.json --cards` puts the
best checked ideas into `inbox/ideas/`, each with its grade, evidence level, audience score and the matching format
from the library (`suggested_format`; the card says so when no format fits yet). The host exporter takes `--format
<id>` for a scout ranking made for one format and carries an entry's own `format` and its audience score.

## Limits

- The plan and the script are agent work: their quality depends on the engine and on the material. The format system
  sets the frame and the checks; it never invents numbers.
- The keyword guess for ideas is simple word overlap; the Scout's pick in the plan decides.
- Converting an episode between long and Short works only while no later step (title, script, record, edit) started.
