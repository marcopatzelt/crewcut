# Architecture

This page is the contract between the parts of Crewcut. If you change a name, a path or a command here, change the code in
the same pull request.

## The big picture

```
Browser (localhost:4747)        episodes, main chat, who is working on what, cards, costs
   │  HTTP + server-sent events
Container "crewcut"             web server (FastAPI), conductor, job queue, approvals, cost book
   │                            engines: Claude Code (default) or Codex (beta), the user's own CLI and subscription
   │                            tools: ffmpeg, Chromium (Playwright), Blender (amd64), Python, Node, faster-whisper
   │
Studio folder (mounted)         brand/, episodes/, config/, .crewcut/ (database, logs, keys)
   │
Rented GPU (optional)           the same image (gpu target), no login data; scene code and fonts go there, and a
                                picture-only shot only after its own card (person matte, docs/motion-matte.md)
```

Two roots:

| Root | In the container | What it holds | Who owns it |
|---|---|---|---|
| **app root** | `/app` | `crewcut/`, `skills/`, `team/`, `templates/`, `packs/`, `config/`, `tools/`, `web/dist/` | the app; updates replace it |
| **studio root** | `/studio` (env `CREWCUT_STUDIO`) | `brand/`, `episodes/`, `config/` (user overrides), `.crewcut/` (state) | the user; updates never touch it |

`crewcut.paths` resolves both. Code never contains an absolute host path. Outside the container (tests, development)
`CREWCUT_STUDIO` defaults to `./studio` and the app root is the repository.

## Layers of knowledge

`motion/quality.py` supplies private craft benchmarks to every edit job and binds independent
style-frame and animation reviews to exact media. `render/slide.py` is the slide check: it measures on the video
whether a full-frame insert's camera stands still and its frame is flat (calibrated against the launch film), for
the style check and `crewcut render slides`. `render/plate_quality.py` keeps probe and
final quality separate and validates returned custom Blender plates. See [motion craft](motion-craft.md).

Preview/final cards may bind `data.production_review` to an independent Critic's
checksum-bound manifest of the assembly plan, card video and every mounted clip's
style and animation evidence. This checks actual revisions without revoking unused
historical cards. See `skills/motion/references/craft.md` for the manifest format.
Compute budgets with a named purpose apply to that purpose; a motion rental does
not authorize music generation. Unscoped budgets retain their episode-wide meaning.

### Production automation and parallel inserts

`full_auto.py` stores an explicit per-episode mode and revision in the database. The existing worker assigns
production cards to a Critic; only that assigned review may decide under the current revision. Turning the mode off
revokes pending automatic upload permission. Existing card checks and spending boundaries remain.
`motion/dispatch.py` gives each approved style frame of a custom piece a fresh designer session in its own insert
folder, then a focused Critic review; an approved style frame of a shelf template or a 2D or 3D scene goes to the
Editor's fan-in instead. The Editor owns the shared plan and assembly. Up to five agent jobs can run; jobs for the
same insert stay serial and heavy rendering retains its separate limit. See [Full auto](full-auto.md).

### Computer media

The native desktop media service discovers standard media folders and removable
drives on demand. Agent requests use source IDs and relative paths through
`crewcut media`; the desktop validates them and copies only media into the studio
inbox. No host shell or whole-home mount is exposed. Both engines share this
capability. See [desktop media](desktop-media.md).

### Research workspaces

All crew members may use persistent `studio/workspaces/<name>/` projects for research, code and experiments.
`crewcut workspace create|list|path` manages their locations without editing the app or mounting host folders.
Both engines receive the capability instructions, and Claude's generated subagents receive them too.
See [research and coding projects](workspaces.md) for permissions, evidence and safety boundaries.

### Channel coordination and imported history

The Showrunner leads the Channel conversation. It reuses the existing engine and queue, not a second agent service.
Channel jobs have no episode and work from the studio root. Explicit conversation scope separates their messages and
session reuse from episode work and brand onboarding. `_channel` is only a transport identifier, never an episode folder.
The channel context is a bounded index of episodes, publication facts, active jobs, open decisions and costs.
An episode task retains its episode ID and can reference a parent channel job. Its result returns to both scopes.
Existing spending and publication gates still apply. Asking a question does not create an episode.

`crewcut.import_history` reconciles imports offline, with a dry-run default, metadata backups and an audit.
It separates historical production evidence, publication state, lifecycle and permission to execute work.
Exact provider IDs can supersede stale legacy stage labels. A missing provider record does not prove non-publication.
Importing and reconciliation never dispatch jobs, grant approvals or repeat uploads.
Original creation time and import time remain separate. Imported cover previews are not thumbnail approval candidates.

| Layer | Content | Owner |
|---|---|---|
| `skills/` and `tools/` | Know-how without taste: how to cut, check, render, upload | the app |
| `brand/` (in the studio) | The style pack: brand tokens, edit style, channel, rules learned from corrections | the user |
| `packs/neutral/` | The neutral default style pack that `brand/` starts from | the app |
| `examples/striq/` | A real, dated example of learned rules and values (no logo, no photos) | example only |

A skill never hard-codes a colour, font, logo, loudness or mix limit. It reads them from the active style pack
(`crewcut.brand.load()`), which is `studio/brand/` when it exists, else `packs/neutral/`.

## Python package `crewcut`

| Module | Job | Owner |
|---|---|---|
| `paths.py` | `app_root()`, `studio_root()`, `state_dir()`, `episodes_dir()`, `brand_dir()` | core |
| `config.py` | loads `config/*.toml` from the app root, then overrides from `studio/config/*.toml` | core |
| `db.py` | SQLite at `studio/.crewcut/crewcut.db`: jobs, cards, costs, rentals, events, messages | core |
| `events.py` | append an event (activity, chat message, card, cost); the server streams them as SSE | core |
| `brand.py` | load and validate a style pack; CSS variables and render tokens for the 2D/3D renderers | core |
| `team.py` | load identities from `team/*.md` (front matter + soul) | core |
| `approvals.py` | cards: propose, decide, wait, `require_spend()`; checksum of the shown file | core |
| `ledger.py` | cost book: add, totals for today / episode / month, cap | core |
| `episodes.py` | create and read episodes, `project.json`, the ten steps | core |
| `studio_import.py` | offline legacy studio copy, manifests and visible references; no jobs or publication | core |
| `conductor/` | steps, job queue (one heavy job at a time; chat answers in their own reply lane, one per episode; a chat message that arrives while a crew member runs reaches it once at its next `crewcut doing`, `say`, `chat` or `card propose`, and the chat shows when, `conductor/deliver.py`), engine runner | core |
| `engines/` | one interface (`base.py`: Task, Event, RunResult; start, stream, stop, resume), two engines on the user's own subscription (`claude_code.py` default, `codex.py` beta) and the version manager (`versions.py`: newest version, smoke test, way back); see [engine.md](engine.md) | core |
| `plugin.py` | builds Crewcut as a Claude Code plugin (skills, crew agents, guard hook) | core |
| `server/` | FastAPI app, API under `/api`, SSE at `/api/events`, teleprompter, serves `web/dist` | core |
| `doctor.py` | checks programs, fonts, templates, engine login, GPU, disk | core |
| `onboarding/` | fetch brand facts from pasted links, write `brand/`, ask for the preview | core |
| `thumbnail/` | one interface, way A (Codex) and way B (image API) | core |
| `youtube/` | OAuth, upload, thumbnail, captions, schedule (YouTube Data API v3) | core |
| `compute/` | rented GPUs: estimate, rent, run, fetch, destroy, guard, cost book entries | compute |
| `render/` | edit plan workbench: 2D (Chromium), 3D (Blender local or rented), assembly with sound, preview | render |
| `media.py` | what the episode view shows first: thumbnail variants, the cut as film strip with waveform and Critic markers (frames and peaks cached in `work/strip-<video>/`), 3D scenes with their render state, the open GPU rental | server |
| `cut/` | ingest, audio check, transcription, speaker cut tools, grade, SRT | cut |

## Command line

Agents work through the `crewcut` command inside the container. Every command prints plain text by default and JSON with
`--json`. Exit codes: `0` ok, `1` error, `2` usage, `3` waiting for or refused by the user (card open or declined),
`4` missing login or key.

```
crewcut doctor [--json] [--ci]
crewcut serve [--host 0.0.0.0 --port 4747]

crewcut episode new "<working title>" [--source URL]      prints the episode id, e.g. 003-local-llms
crewcut episode new "<title>" --short clip --from <episode> | --short original      a Short (docs/shorts.md)
crewcut episode import <folder> --title "…" [--format portrait] [--script F] [--broll F …] [--plan F] [--skip upload]
crewcut episode status [<id>] [--json]
crewcut episode lifecycle <id> active|planned|parked|archived  organize or resume; no jobs or approvals
crewcut episode recording-script <id> <file> [--partial]     choose text; does not replace a different approved script
crewcut episode refresh-cover <id> [--youtube-id ID] [--image FILE]  fill a missing card preview; no approval
crewcut episode step <id> <step> <status>                 status: open | working | waiting | done | skipped

crewcut say --episode ID [--cite "<method> (<source>)"] "<text>"   message in the main chat, from $CREWCUT_IDENTITY
crewcut chat --episode ID [--last 12]                     the recent chat, for context
crewcut doing --episode ID "<what I am doing now>" [--progress 0.4]   updates the right column
crewcut card propose --episode ID --step STEP --kind KIND --title "…" [--file PATH] [--body "…"] [--option "…" …]
crewcut card wait <card-id> [--timeout S]                 exit 0 accepted, 3 declined or timed out
crewcut card accept <id> [--choice N] | decline <id> --reason "…"   Showrunner only: a yes or a change the user said in
                                                          words (never for spend, publish or final cards)
crewcut card list [--episode ID] [--status open]
crewcut rule propose --step STEP --rule "…" --source "…" [--episode ID]
crewcut job add --episode ID --identity ID --step STEP "<task>"

crewcut brand show [--json] | check | preview [--out file.mp4]
crewcut brand init [--from <pack>] [--font ROLE=FILE …] [--logo FILE] [--accept]
crewcut engine status | use <claude|codex> | install <name> | login <name> [--episode ID]
crewcut engine update [<name>] [--channel latest|stable|X.Y.Z] | rollback [<name>]
crewcut plugin [--out DIR]                                 the Claude Code plugin (skills, crew agents, guard hook)
crewcut hook pre-tool                                      called by Claude Code through the plugin
crewcut onboard <link> [<link> …]

crewcut render plan|2d|3d|probe|cut|shown|all <plan.json> [--local | --rented] [--gpus N]   (docs/rendering.md)
crewcut render measure <image.png> | samples [--out DIR]
crewcut ingest <episode> <file> [<file> …]
crewcut ingest <episode> --imported                        verify and register copied legacy recordings; no jobs
crewcut transcribe <file> [--model small] [--device auto|cpu|cuda] [--language xx]
crewcut cut islands|dips|probe|takes|plan|build|verify|doubles|grade|srt|audio|loudness …   (docs/recording.md)
crewcut cut candidates <episode> [--retention CSV|JSON] [--min 20 --max 55 --sentences 12]   Short candidates
crewcut cut short <edit/pieces-vNNN.json> [--words new|carry] [--accept-soft] [--dry-run]   9:16 rough cut of a clip
crewcut cut short-check <video> [--cut …] [--plan …]       the Critic's Short rules, contact sheet, listening list
crewcut render capture <episode> --url URL | --html FILE | --terminal FILE [--seconds N] [--scroll …] [--size full|stage]
crewcut render music-bed <voice.wav> --music TRACK --licence "…" [--start S] [--punch T,…] [--credit "…"]
crewcut shorts standing on|off|status | slot --episode ID | results --episode ID | table

crewcut compute estimate --kind blender --frames N [--local-sec-per-frame S] [--gpu-sec-per-frame S] [--gpus N]
                         [--scene NAME] [--episode ID] [--job ID] [--local-fine] [--json]
crewcut compute rent --episode ID [--gpus 1] [--minutes 60] [--max-usd X] [--step edit] [--purpose "…"] [--json]
crewcut compute put <machine> <local> [<local> …] <remote-dir>
crewcut compute run <machine> [--timeout S] [--doing "rendering"] -- <command>
crewcut compute fetch <machine> <remote-dir> <local-dir>
crewcut compute destroy [<machine> | --all-ours]
crewcut compute guard [--once] [--every S]
crewcut compute ledger [--episode ID]

crewcut thumbnail make --episode ID --prompt FILE [--ref IMG …] [--way codex|api] [--variants 3]
crewcut youtube connect [--episode ID] | auth | upload --episode ID [--schedule ISO] | status
crewcut youtube verify <episode> [--package export/upload.json]   read-only metadata/caption-track comparison
crewcut youtube results <episode> --start YYYY-MM-DD --end YYYY-MM-DD [--video ID]  read-only calendar-day results
crewcut humanize record --draft FILE --final FILE [--why "…"]       the Humanizer pass of a script, for its card
crewcut brand voice add <video link | recording> | list          the user's own spoken words (brand/voice/)
crewcut skills status | update [<name>]                           skills from other projects (Humanizer), newest
crewcut skills own [--json]                                      your own skills from <studio>/skills and where they apply
crewcut prompter <episode>                               prints the phone URL and a QR code
```

Environment set by the conductor for every agent run: `CREWCUT_STUDIO`, `CREWCUT_EPISODE`, `CREWCUT_IDENTITY`,
`CREWCUT_JOB`. Rights live in the identity: only `may_spend: true` identities may rent, only `may_publish: true` may upload.

## The ten steps

| # | Step id | Who | Result in `episodes/<id>/` | Card (user says yes) |
|---|---|---|---|---|
| 1 | `idea` | Scout | `brief/BRIEF.md` | topic |
| 2 | `title` | Scout | `brief/TITLE-vNNN.md` | title and thumbnail text |
| 3 | `proof` (optional, off by default: `[steps] proof` in `config/crewcut.toml`) | Scout | `brief/PROOF-vNNN.md`, raw data in `review/`; off: the Writer keeps its facts in `work/material-vNNN.md` | the facts (only when on) |
| 4 | `script` | Writer; first the interview (on by default: `[steps] interview`) | `brief/INTERVIEW-vNNN.md` (the user's answers), `brief/SCRIPT-vNNN.md` | script |
| 5 | `record` | the user; Editor ingests | `originals/`, `brief/ingest-<time>.json` | none (the user records) |
| 6 | `edit` | Editor, then Critic | `work/words-*.json`, `edit/selects-vNNN.json`, `edit/cut-plan-vNNN.json`, `work/speaker-vNNN.mov`, `audio/voice-vNNN.wav`, `work/edit-decisions-vNNN.json`, `work/cut-verification-vNNN.json`, `review/takes-vNNN.json`, `edit/plan-vNNN.json`, `export/<id>-vNNN-preview.mp4`, `review/cut-check-vNNN.json` | mix, preview, then final |
| 7 | `thumbnail` | Designer | `graphics/thumbnail/` | thumbnail |
| 8 | `blog` | (planned) | | |
| 9 | `upload` | Publisher | `export/upload.json` | publish (every time) |
| 10 | `results` | Publisher (planned) | `review/results-48h.json` | |

### The interview

The script step of a long video starts with an interview (`[steps] interview` in `config/crewcut.toml`, default
`true`; code in `crewcut/interview.py`). After the title is approved and before the first draft, the Writer reads the
brief, the packaging and the research and asks the user 5 to 8 short, numbered, open questions in one chat message
(`crewcut interview ask <id> --file work/interview-questions.md`; the command checks the count and length, adds how to
answer, and sets the step to waiting). The questions target what no file knows: the personal start, doubts, the real
turning point, setbacks with concrete details, how the user works, what it changes for them.

The episode then waits: "Interview: waiting for your answers" on its card and in the episode view. Every chat
message is an answer, typed or dictated with the composer's microphone; an audio file dropped into the chat is
transcribed on this machine (`crewcut interview answer`, a tool job in the heavy lane). One message counts as complete;
a message that says more is coming ("more coming", "mehr kommt", "Teil 1") keeps it open until the user says "done"
("fertig") or presses "Done answering". "Skip interview" (the words or the button) skips it for this episode.

The conductor writes the answers verbatim, with light cleanup (filler sounds and spaces only), to
`brief/INTERVIEW-vNNN.md` with the questions and a "Do not mention (hard rules)" list taken from the user's own words,
copies the answers into `brand/voice/interviews/<episode>.md` (the newest three; the Humanizer's voice sample), and
starts the Writer on the script in the session that asked. The Writer uses the user's sentences as much as possible,
keeps every leave-out wish as a hard rule, and marks the lines from the interview below `---` as
`[[interview: 3 | "the spoken words"]]`; `script_check.py --interview` checks the marks. Only the user answers, ends
or skips: crew members cannot do it for them (`crewcut interview skip|done` refuse inside an agent job). An episode
that already has a script draft, or recorded an interview by hand (`project.json` `interview.status`), is not asked
again; Shorts have no interview.

Episode folder: `brief/`, `originals/`, `work/`, `audio/`, `broll/`, `graphics/`, `edit/`, `render/`, `review/`,
`export/`, plus `project.json`:

Imported episodes may also contain `legacy/`, `legacy-import.json` and `legacy-visible.json`. These preserve earlier
files and provenance without making old plans executable or old approvals current. Shared historical material lives
under `studio/library/`. See [private studios](private-studio.md) for the import command and boundaries.

The episode view offers script downloads and a read-only, paginated browser for imported folders. Historical publication
and parked states appear separately from current step approvals. Download links use `?download=true`; active web files
(HTML, SVG and JavaScript) are always attachments rather than executable pages on the studio origin.

```json
{"id": "003-local-llms", "title": "Working title", "created": "2026-11-16T10:00:00Z", "format": "landscape", "fps": 25,
 "step": "script", "steps": {"idea": {"status": "done", "card": 4}}, "next_action": "…", "open_items": []}
```

## Edit plan (`episodes/<id>/edit/plan-vNNN.json`)

One plan builds one version of the video. Times are seconds; frames are at `fps` (default 25).

```json
{
  "format": "landscape",
  "words": "work/words-v001.json",
  "base": "work/speaker-v001.mov",
  "base_until": null,
  "voice": "audio/voice-v001.wav",
  "voice_db": 0.0,
  "tail": 1.5,
  "face": [0.5, 0.38],
  "speaker": [{"at": 12.4, "zoom": 1.12}],
  "inserts": [
    {"id": "s1", "kind": "2d", "scene": "counter", "start": 10.0, "end": 14.2,
     "cues": {"value": {"word": "thirty"}, "label": 8}, "data": {"label": "1 MILLION TOKENS", "value": "30", "unit": "cents"}},
    {"id": "k1", "kind": "2d", "scene": "keyword", "start": 20.0, "end": 22.0, "transparent": true, "data": {"text": "LOCAL"}},
    {"id": "d1", "kind": "3d", "scene": "stack", "start": 30.0, "end": 33.0, "data": {}},
    {"id": "c1", "kind": "clip", "file": "broll/screen.mp4", "at": 3.0, "speed": 1.0, "start": 40.0, "end": 44.0}
  ],
  "sound": {"music": "audio/music.wav", "music_db": null, "duck": true, "gaps": [{"before": "s1@value", "frames": 15}],
            "hits": ["s1@value"], "typing": [], "whooshes": [], "lufs": -14},
  "output": "export/003-local-llms-v001-preview.mp4",
  "crf": 17
}
```

Portrait plans (Shorts) may set `"layout": "proof-top"` (else the pack's `shorts.layout`, default `full`): the proof
on a top stage, the speaker below, the end on the face alone. Inserts then take `place` (`stage` or `full`), `fit`
(`cover` or `contain`, a card on `stage_color`) and `anchor`; the plan takes `end_face` (seconds, default 2.0) and
`right_free` (the right share kept free of text for YouTube's buttons). Details: [rendering.md](rendering.md).

`base` may also be `{"color": "soft", "seconds": 20}`: a generated background instead of a recording (the demo and
the onboarding preview use it). Values left `null` come from the style pack (`edit-style.json`). A cue is a frame number inside the insert, or
`{"word": "…", "after": seconds, "offset": frames}`, or `{"time": seconds}`. A sound reference `"s1@value"` is the frame of
cue `value` in insert `s1`. After the user has seen an output, `crewcut render shown` writes `<output>.shown` (time and
sha256) and the workbench refuses to overwrite it: every change is a new plan version.

`start` and `end` of an insert may also be word anchors: `{"word": "costs", "offset": -0.6, "after": 10.0}` (offset in
seconds; an end anchor looks from the start on).

Motion graphics (`"kind": "motion"`, rendered by EffectCraft, see [rendering.md](rendering.md#motion-graphics-effectcraft-here-or-rented)
and [motion.md](motion.md)):

```json
{"id": "m1", "kind": "motion", "scene": "number_roll", "start": {"word": "costs", "offset": -0.6}, "end": 14.2,
 "cues": {"landAt": {"word": "thirty"}}, "data": {"value": "30", "unit": "cents", "label": "1 million tokens"},
 "transparent": false, "backdrop": null, "sound": true, "beat": 4, "column": "a"}
{"id": "m2", "kind": "motion", "scene": "keyword_pop@1", "start": 20.0, "end": 22.0, "transparent": true,
 "layer": "behind", "data": {"words": ["runs", "offline"]}}
{"id": "m3", "kind": "motion", "source": "motion/m3/comp.jsx", "start": 41.0, "end": 47.5,
 "cues": {"handoff": {"word": "GPU"}}, "data": {"jobs": 4},
 "plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0, "tin": 1.2}, "frames": 120}]}
```

| Field | Meaning |
|---|---|
| `scene` | a library template (`templates/motion/<name>.jsx`; the pack's `brand/templates/motion/` wins). `"name@N"` pins version N: `<name>.jsx` when its `@version` is N (no `@version` counts as 1), else `<name>.vN.jsx` in the same folder |
| `source` | instead of `scene`: a comp in the episode folder (custom motion). Exactly one of the two |
| `data` | template params; a param the template's header does not declare is refused. Image and footage paths (relative to the episode) become absolute paths, and their files are part of the hash |
| `cues` | template params in seconds local to the insert (0 = its first frame); a cue must be a declared param and must not also be in `data`. Cue forms as above (a number is a frame inside the insert) |
| `transparent` | true: an overlay (RGBA frames, MOV with alpha); left out: the template's `@kind` decides |
| `backdrop` | null or `"speaker"` (full frame only): the comp gets the speaker piece of this span as footage |
| `layer` | null or `"behind"` (overlays only): meant to sit behind the speaker; rendered as an overlay until the matte step composites it |
| `plates` | Blender plates the comp needs: `[{"id", "script", "args", "frames"}]`; only their shape is checked for now |
| `sound` | true: the template's `@sounds` become `hits`, `whooshes` or `typing` events of the cut (one per insert) |
| `beat`, `column` | the row of the approved motion plan this insert comes from (for the Critic). Every motion insert and every full-frame 2D or 3D insert needs one, its own; the render waits for the row and for the yes on the insert's style frame (`render/workbench.py` `insert_gates`) |
| `place`, `fit`, `anchor` | as for every full-frame insert; with `place` top in proof-top the comp renders at the stage size (format `"stage"`, 1080 x 960) |

Plan-level keys for motion: `motion_cap_usd` (lowers the rented cap: $2 a video, $0.50 a Short) and
`motion_without_engine` (`"fail"`, the default, or `"skip"`: `render all` leaves the motion inserts out where
`effectcraft-cli` is missing). `face` may be `[x, y]`, `[x, y, w, h]` or `{"x", "y", "w", "h"}` (fractions of the frame;
the box size defaults to 0.32 x 0.28); motion overlays keep text off that box. A template whose `@formats` lacks the
insert's format is an error.

Scene names and their data keys are documented in `templates/2d/BLOCKS.md`, `templates/3d/README.md` and
`templates/motion/README.md`. Skills point there instead of repeating them.

## Style pack files

```
brand/  (or packs/neutral/)
  brand.json        colors, fonts, logo, shape, motion, motion_graphics, 3D stage, sources
  edit-style.json   pace, captions, music, loudness, mix limits, motion limits, speaker share, text limits
  channel.json      niche, audience, language, country, tone, reference channels, topics to avoid, closing line
  thumbnail.json    layouts, face, max words, colors, reference photo
  voice.md          how the user speaks: words to use and to avoid
  rules/<step>.md   learned rules, one per line block: date, rule, source (the user's words)
  references/       1 to 3 sample videos or links and measured values
  baseline.json     the user's best own video: the bar
  templates/        optional copies of 2D scenes and motion templates rebuilt for this brand (never edit the app's)
```

Every value can carry its source in a `sources` map (`"colors.accent": "from your website, 16 Nov 2026"`). The profile view
shows it next to the value.

## Database (SQLite, `studio/.crewcut/crewcut.db`)

| Table | Columns (main) |
|---|---|
| `jobs` | id, episode, step, identity, kind (`agent` or `tool`), task, heavy, status (`queued`, `running` while the process runs, also after it proposed a card; `waiting` once it ended with an open card; `done`, `failed`, `cancelled`), doing, progress, created, started, ended, cost_usd, equiv_usd, log_path |
| `cards` | id, episode, step, kind, title, body, file, sha256, options (JSON), status (`open`, `accepted`, `declined`, `expired`), decided_by, decided_at, choice, created |
| `costs` | id, at, episode, step, kind (`gpu`, `api`, `other`), amount_usd, detail, ref |
| `rentals` | id, provider, instance, label, episode, job, price_per_hour, started, deadline, ended, status, detail |
| `events` | id, at, episode, kind, identity, text, data (JSON) |
| `messages` | id, at, episode, author (`user` or identity id), text, card |

Money: `costs` holds real money only (rented GPUs, paid APIs). Agent runs on a subscription have no real cost; their API
equivalent (`total_cost_usd` from Claude Code) is kept in `jobs.equiv_usd` and shown as such, never added to money.

## HTTP API

See [api.md](api.md).
