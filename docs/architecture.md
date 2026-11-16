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
Rented GPU (optional)           the same image (gpu target), no login data, only scene code and fonts go there
```

Two roots:

| Root | In the container | What it holds | Who owns it |
|---|---|---|---|
| **app root** | `/app` | `crewcut/`, `skills/`, `team/`, `templates/`, `packs/`, `config/`, `tools/`, `web/dist/` | the app; updates replace it |
| **studio root** | `/studio` (env `CREWCUT_STUDIO`) | `brand/`, `episodes/`, `config/` (user overrides), `.crewcut/` (state) | the user; updates never touch it |

`crewcut.paths` resolves both. Code never contains an absolute host path. Outside the container (tests, development)
`CREWCUT_STUDIO` defaults to `./studio` and the app root is the repository.

## Layers of knowledge

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
| `conductor/` | steps, job queue (one heavy job at a time), engine runner | core |
| `engines/` | one interface (`base.py`: Task, Event, RunResult; start, stream, stop, resume) and two engines on the user's own subscription: `claude_code.py` (default) and `codex.py` (beta); see [engine.md](engine.md) | core |
| `server/` | FastAPI app, API under `/api`, SSE at `/api/events`, teleprompter, serves `web/dist` | core |
| `doctor.py` | checks programs, fonts, templates, engine login, GPU, disk | core |
| `onboarding/` | fetch brand facts from pasted links, write `brand/`, ask for the preview | core |
| `thumbnail/` | one interface, way A (Codex) and way B (image API) | core |
| `youtube/` | OAuth, upload, thumbnail, captions, schedule (YouTube Data API v3) | core |
| `compute/` | rented GPUs: estimate, rent, run, fetch, destroy, guard, cost book entries | compute |
| `render/` | edit plan workbench: 2D (Chromium), 3D (Blender local or rented), assembly with sound, preview | render |
| `cut/` | ingest, audio check, transcription, speaker cut tools, grade, SRT | cut |

## Command line

Agents work through the `crewcut` command inside the container. Every command prints plain text by default and JSON with
`--json`. Exit codes: `0` ok, `1` error, `2` usage, `3` waiting for or refused by the user (card open or declined),
`4` missing login or key.

```
crewcut doctor [--json] [--ci]
crewcut serve [--host 0.0.0.0 --port 4747]

crewcut episode new "<working title>" [--source URL]      prints the episode id, e.g. 003-local-llms
crewcut episode status [<id>] [--json]
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

crewcut brand show [--json] | check | init | preview [--out file.mp4]
crewcut engine status | use <claude|codex> | install <name> | login <name> [--episode ID]
crewcut onboard <link> [<link> …]

crewcut render plan|2d|3d|probe|cut|shown|all <plan.json> [--local | --rented] [--gpus N]
crewcut ingest <episode> <file> [<file> …]
crewcut transcribe <file> [--model small] [--device auto|cpu|cuda] [--language xx]
crewcut cut islands|plan|build|verify|doubles|grade|srt …

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
crewcut youtube auth | upload --episode ID [--schedule ISO] | status
crewcut prompter <episode>                               prints the phone URL and a QR code
```

Environment set by the conductor for every agent run: `CREWCUT_STUDIO`, `CREWCUT_EPISODE`, `CREWCUT_IDENTITY`,
`CREWCUT_JOB`. Rights live in the identity: only `may_spend: true` identities may rent, only `may_publish: true` may upload.

## The ten steps

| # | Step id | Who | Result in `episodes/<id>/` | Card (user says yes) |
|---|---|---|---|---|
| 1 | `idea` | Scout | `brief/BRIEF.md` | topic |
| 2 | `title` | Scout | `brief/TITLE-vNNN.md` | title and thumbnail text |
| 3 | `proof` | Scout | `brief/PROOF-vNNN.md`, raw data in `review/` | what goes into the video |
| 4 | `script` | Writer | `brief/SCRIPT-vNNN.md` | script |
| 5 | `record` | the user; Editor ingests | `originals/`, `brief/ingest-*.json` | none (the user records) |
| 6 | `edit` | Editor, then Critic | `edit/plan-vNNN.json`, `export/<id>-vNNN-preview.mp4`, `review/cut-check-vNNN.json` | preview, then final |
| 7 | `thumbnail` | Designer | `graphics/thumbnail/` | thumbnail |
| 8 | `blog` | (planned) | | |
| 9 | `upload` | Publisher | `export/upload.json` | publish (every time) |
| 10 | `results` | Publisher (planned) | `review/results-48h.json` | |

Episode folder: `brief/`, `originals/`, `work/`, `audio/`, `broll/`, `graphics/`, `edit/`, `render/`, `review/`,
`export/`, plus `project.json`:

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
  "base": "work/speaker-v001.mp4",
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

Values left `null` come from the style pack (`edit-style.json`). A cue is a frame number inside the insert, or
`{"word": "…", "after": seconds, "offset": frames}`, or `{"time": seconds}`. A sound reference `"s1@value"` is the frame of
cue `value` in insert `s1`. After the user has seen an output, `crewcut render shown` writes `<output>.shown` (time and
sha256) and the workbench refuses to overwrite it: every change is a new plan version.

Scene names and their data keys are documented in `templates/2d/BLOCKS.md` and `templates/3d/README.md`. Skills point there
instead of repeating them.

## Style pack files

```
brand/  (or packs/neutral/)
  brand.json        colors, fonts, logo, shape, motion, 3D stage, sources
  edit-style.json   pace, captions, music, loudness, mix limits, speaker share, text limits
  channel.json      niche, audience, language, country, tone, reference channels, topics to avoid, closing line
  thumbnail.json    layouts, face, max words, colors, reference photo
  voice.md          how the user speaks: words to use and to avoid
  rules/<step>.md   learned rules, one per line block: date, rule, source (the user's words)
  references/       1 to 3 sample videos or links and measured values
  baseline.json     the user's best own video: the bar
  templates/        optional copies of 2D scenes rebuilt for this brand (never edit the app's templates)
```

Every value can carry its source in a `sources` map (`"colors.accent": "from your website, 16 Nov 2026"`). The profile view
shows it next to the value.

## Database (SQLite, `studio/.crewcut/crewcut.db`)

| Table | Columns (main) |
|---|---|
| `jobs` | id, episode, step, identity, kind (`agent` or `tool`), task, heavy, status (`queued`, `running`, `waiting`, `done`, `failed`, `cancelled`), doing, progress, created, started, ended, cost_usd, equiv_usd, log_path |
| `cards` | id, episode, step, kind, title, body, file, sha256, options (JSON), status (`open`, `accepted`, `declined`, `expired`), decided_by, decided_at, choice, created |
| `costs` | id, at, episode, step, kind (`gpu`, `api`, `other`), amount_usd, detail, ref |
| `rentals` | id, provider, instance, label, episode, job, price_per_hour, started, deadline, ended, status, detail |
| `events` | id, at, episode, kind, identity, text, data (JSON) |
| `messages` | id, at, episode, author (`user` or identity id), text, card |

Money: `costs` holds real money only (rented GPUs, paid APIs). Agent runs on a subscription have no real cost; their API
equivalent (`total_cost_usd` from Claude Code) is kept in `jobs.equiv_usd` and shown as such, never added to money.

## HTTP API

See [api.md](api.md).
