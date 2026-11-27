# HTTP API

The web UI talks to the container over this API. All paths start with `/api`. Bodies and answers are JSON. Times are ISO
8601 in UTC. Money is US dollars as numbers. The server binds to `127.0.0.1` by default; there is no login because only
the local machine can reach it. The teleprompter has its own port and a token (see the end).

## State

`GET /api/state` returns everything the main screen needs in one answer:

```json
{
  "app": {"version": "0.1.0", "engine": "claude", "engine_ok": true, "gpu_local": false, "onboarded": false},
  "team": [{"id": "showrunner", "name": "Showrunner", "role": "Runs the episode through the ten steps.", "mark": "SR",
            "skills": ["episode"], "may_spend": false, "may_publish": false}],
  "episodes": [{"id": "003-local-llms", "title": "Local LLMs on a laptop", "step": "script",
                "steps": [{"id": "idea", "n": 1, "label": "Idea", "status": "done"}],
                "updated": "2026-11-16T10:00:00Z", "open_cards": 1}],
  "activity": [{"job": 12, "episode": "003-local-llms", "identity": "writer", "step": "script",
                "doing": "Writing the script, version 2", "progress": 0.4, "status": "running",
                "started": "2026-11-16T10:02:00Z", "seconds": 312, "cost_usd": 0.0, "equiv_usd": 0.41,
                "engine": "claude", "model": "the model the engine reported", "effort": null, "engine_version": "2.1.325"}],
  "money": {"today_usd": 0.0, "episode_usd": {"003-local-llms": 0.62}, "month_usd": 3.78, "cap_month_usd": 20.0}
}
```

`status` of a step: `open`, `working`, `waiting` (a card is open), `done`, `skipped`.

Optional fields of an episode, for its card in the grid:
- `historical_status`: `published`, `parked`, `paused` or `archived`, when explicitly recorded in imported metadata.
  This affects display only. It does not grant upload approval or set current step statuses.
- `cover`: URL of the newest thumbnail image, or `null`.
- `needs`: the first open card with up to three small pictures, or `null`:
  `{"card": 41, "kind": "thumbnail", "title": "Thumbnail A, test B", "images": ["/api/files/…", "…"]}`. The pictures
  are the thumbnail variants for a `thumbnail` card, the 3D frames (or probe stills) for a `spend` card, else the
  card's `preview` or `file` when it is an image.
- `interview`: the interview before the first script draft, or absent:
  `{"status": "asking|waiting|done|skipped", "label": "Interview: waiting for your answers", "answers": 2,
  "questions": 6, "file": "brief/INTERVIEW-v001.md"}`. An episode whose interview is `waiting` belongs in "Needs you".
- `seconds`: length of the newest export or cut (see `cut` under "Episode media"), or `null`. ffprobe runs once per
  file version (cache keyed by path, size and mtime), not on every call.

Optional field of an activity: `preview`, the URL of the newest image written in the job's episode since the job
started (render frames, probe stills, thumbnail drafts, strip frames), for `running` and `waiting` jobs; else `null`.
A `thumbnail` job looks in `graphics/`, an `edit` job in `render/`, `review/` and `work/strip-*/`, others in all of
them. The scan is bounded (300 folders, depth 4) and cached per folder until its mtime changes.

## Episodes

`GET /api/episodes/{id}/full-auto` returns the episode's automation policy (default `{"mode":"off"}`).
`POST` to the same path takes `{"mode":"off|ready|private|publish"}` and returns a new policy revision.
Only the user's explicit UI choice changes it. `ready` stops before upload; `private` allows private uploads without
scheduling; `publish` allows the reviewed publication package. Existing jobs are not cancelled.
See [Full auto](full-auto.md) for review and stop conditions.

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/episodes/{id}` | | episode as in `state.episodes[]` plus `project` (the raw `project.json`) and `files` (list of `{path, size, kind}` under `export/`, `graphics/`, `brief/`) |
| `GET /api/episodes/{id}/media` | | what the episode view shows first: thumbnails, the cut, 3D scenes, the rented GPU (see "Episode media" below) |
| `GET /api/episodes/{id}/imported-files?folder=&offset=0&limit=100` | | read-only directory listing under `legacy/`: `{folder, total, entries: [{path, name, directory, size?}]}`; at most 100 entries, no hidden files, excluded credential names or links |
| `POST /api/episodes` | `{"text": "a tool, link, tweet or idea", "length": "long"\|"short"\|"auto", "show_format": "id"}` (only `text` is required) | the new episode with `length` and, once chosen, `show_format: {id, name, length, topic_type, reason, runner_up, file}`; with a format library the Scout's plan starts (docs/formats.md), else the idea step; 400 for an unknown format or a format of the other length |
| `GET /api/formats` | | `{formats: [the format without its folder, with "templates"], problems: ["…"], enabled}` |
| `GET /api/ideas?status=` | | idea cards `[{id, source, url, title, summary, signals, topic_type, suggested_format, reason, suggestion, status, episode, created}]`, open first; loads new files from `inbox/ideas/` first |
| `POST /api/ideas/{id}/start` | `{"length"?, "show_format"?}` or none | `{idea, episode}`: the episode made the same way as `POST /api/episodes`; 400 when the idea is decided, 404 unknown |
| `POST /api/ideas/{id}/dismiss` | none | the idea with status `dismissed` |
| `GET /api/scoreboard` | | `{channel: {median_views, median_avg_view_pct, subs_per_1000, episodes}, formats: [{format, name, length, episodes, measured, median_views, median_avg_view_pct, subs_per_1000, retention_drop_per_min, ctr, verdict, verdict_text}]}` |
| `GET /api/episodes/{id}/messages?after=ID` | | `[{"id", "at", "author", "text", "card", "cite", "step", "preview", "facts"}]`; `author` is `user` or an identity id; `cite`, `preview` (a file in the episode) and `facts` (`[{"label", "value"}]`) are optional |
| `POST /api/episodes/{id}/messages` | `{"text": "…"}` | the stored message; the Showrunner answers in later messages. While the interview waits, the message is an answer instead (docs/architecture.md, "The interview") |
| `POST /api/episodes/{id}/interview` | `{"action": "skip"}` or `{"action": "done"}` | `episode.interview` after "Skip interview" or "Done answering"; 400 when the interview is over (skip) or not waiting (done) |
| `GET /api/channel/messages?after=ID` | | channel history, independent of episode and onboarding histories |
| `POST /api/channel/messages` | `{"text": "…"}` | stored channel message; Showrunner runs from the studio root without creating an episode |
| `GET /api/channel/context` | | bounded episode index, active jobs, open decisions and costs |
| `GET /api/files/{episode}/{path}` | | the file (video, image, text) for previews; only inside the episode folder |
| `POST /api/episodes/{id}/upload` | multipart, field `file` (one or more) | `[{"path": "inbox/…", "size"}]`; recordings dropped into the chat land in `studio/inbox/<episode>/` and the Editor ingests them; while the interview waits, audio files (no video) are voice answers, transcribed on this machine |
| `GET /api/episodes/{id}/prompter` | | `{"url": "http://<lan-host>:4748/p/<token>", "qr_svg": "<svg …>"}` for the teleprompter on a phone |

## Episode media

Imported episodes can include `history` with `distribution` (`published`, `scheduled`, `uploaded`, `unknown`),
`source`, `checked_at`, `url`, `published_at` and `scheduled_at`. Optional `imported_at` is not a creation date.
Steps may have `unknown` status: historical work not verified after import. This does not mean not started.
The media response also includes `cover_preview` (safe local preview URL or null) and `imported` (boolean).
These previews are independent of the approval candidates in `thumbnails`.

`GET /api/episodes/{id}/media` (code: `crewcut/media.py`, UI types: `EpisodeMedia` in `web/src/api/types.ts`). It only
reads the episode folder and the database. A missing folder or file gives `null` or an empty list, never an error; an
unknown episode is a 404.

```json
{
  "thumbnails": [{"id": "A", "label": "Face right", "note": "Title left, four sites", "recommended": true,
                  "url": "/api/files/003-local-llms/graphics/thumbnail/v2-face/A-face-right/thumbnail-v001.png",
                  "picked": false, "card": 41}],
  "cut": {"version": "v2", "seconds": 312.4, "shots": 38, "pending": false,
          "frames": [{"t": 15.62, "url": "/api/files/003-local-llms/work/strip-003-local-llms-v002-preview/frame-01.jpg"}],
          "peaks": [0.12, 0.4, 1.0],
          "markers": [{"t": 41.2, "level": "error", "text": "Black frame between two cuts"}],
          "facts": ["Keywords only", "8 cuts a minute", "-14 LUFS"]},
  "scenes": {"title": "3D scenes", "done": 1, "total": 3,
             "items": [{"id": "d1", "name": "Stack", "status": "done", "progress": 1.0, "seconds": 3.0,
                        "url": "/api/files/003-local-llms/render/inserts/d1-1a2b3c4d5e/0076.png"},
                       {"id": "d2", "name": "Tower", "status": "rendering", "progress": 0.31, "seconds": 2.0,
                        "url": "…"},
                       {"id": "d3", "name": "Scale", "status": "queued", "progress": null, "seconds": 4.0,
                        "url": null}]},
  "gpu": {"name": "RTX 4090", "started": "2026-11-16T10:02:00Z", "minutes_left": 45, "so_far_usd": 0.3,
          "cap_usd": 1.5, "progress": 0.37, "delete_note": "Deleted when done, frames come home", "session": 7}
}
```

- **`thumbnails`**: the variants of the newest round in `graphics/thumbnail/` (the round folder `vN-<purpose>/` whose
  newest image is newest; images directly in `graphics/thumbnail/` count as a round too). One variant per folder
  `A-<motif>/`, `B-<motif>/` (its image: a file named `thumbnail*` first, then the highest version, then the newest),
  else the round's images in file order as A, B, C. Inputs (`1-photo.jpg`, `3-result.png`), preview sheets
  (`preview-*.png`) and upload copies (`*-1280x720.jpg`) are not variants. `label` defaults to the motif ("Face
  right") or "Variant A". The Designer may write `variants.json` in the round folder to set `label`, `note`,
  `recommended` and optionally `file` (relative to the round folder) per `id`: a list of objects, `{"variants": [...]}`
  or `{"A": {...}}`. `card` is the open `thumbnail` card of the episode; `picked` comes from the newest accepted
  `thumbnail` card's `choice` (the option's letter or label, else the index), unless a newer thumbnail card is open or
  the accepted card's file lies in another round.
- **`cut`**: the newest video in `export/` (highest version in the name, then newest file; `*.tmp.*` skipped), else
  the newest `work/speaker-vNNN.mov`; `null` when there is none. `version` is `v` plus the number in the name (`v2`).
  `seconds` comes from ffprobe (cached). `shots` = the pieces of the matching cut plan (`edit/cut-plan-vNNN.json`
  `cuts`, or `edit/pieces-vNNN.json` `pieces` for a Short; the version of the edit plan's `base`) plus the full-frame
  inserts (not `transparent`) of the edit plan whose `output` is this video (else the plan of the same version).
  `markers` are the findings with a time from `review/cut-check-vNNN.json` of the same version (else the newest):
  `ERROR` → `error`, `CHECK` → `warning`, `NOTE` → `note`; `OK` is left out. `facts` come from the style pack:
  captions, `pace_cuts_per_minute`, `loudness_lufs` (a Short's own `edit_style.shorts` values where they exist).
- **Frames and peaks** are made once per video by ffmpeg in a background thread (one at a time per video) into
  `work/strip-<video stem>/`: `frame-01.jpg` … `frame-10.jpg` (320 px wide, at 5 %, 15 % … 95 % of the length) and
  `peaks.json` (240 values 0..1: the loudest sample of each slice, scaled to the loudest slice; written last, with the
  video's size and mtime). A request never waits: until `peaks.json` matches the video, `cut` has `frames: []`,
  `peaks: []`, `pending: true`. A changed video (other size or mtime) is made again. A video ffmpeg cannot read gets a
  `peaks.json` with empty lists and `errors`, so it is not retried on every request.
- **`scenes`**: the `kind: "3d"` inserts of the newest `edit/plan-vNNN.json`; `null` without a plan or without 3D
  inserts. `title` is the plan's `title`, else "3D scenes". Frames are counted in the insert's folder
  `render/inserts/<id>-<hash>/` (as the renderer names it; when the plan does not load, the newest
  `render/inserts/<id>-<10 hex>/`). `done` when the encoded clip exists or every frame is there; `rendering` while a
  running job of the episode says it renders 3D (or Blender) or a rented GPU of the episode is live: the inserts that
  have some frames, else the first unfinished one; else `queued`. `progress` is frames done / frames to render (1.0
  when done, `null` before the first frame). `url` is the newest rendered frame, else the newest probe still
  `render/probe/<id>-NNNN.png`, else `null`. `name` is the insert's `name`, else its scene.
- **`gpu`**: the live machines (`creating`, `starting`, `ready`, `lost`) of the episode's newest compute session in the
  `rentals` table, else `null`. `name` is the GPU model ("2 × RTX 4090" for two machines), `started` the earliest
  start, `minutes_left` the minutes until the latest deadline, `so_far_usd` price times time over every machine of the
  session, `cap_usd` the session's cap, `progress` the renting job's progress (else frames done / frames over the 3D
  inserts). `session` is the row id of the newest live rental (the compute session's own id is a hex string).

## Cards

A card asks the user for one yes. Declining or changing is a sentence in the chat, not a second button set.

```json
{"id": 4, "episode": "003-local-llms", "step": "title", "kind": "title", "identity": "scout",
 "title": "Pick a title", "body": "Recommendation: option 1. It names the result and the tool.",
 "options": ["I ran 5 local LLMs on a laptop", "…"], "file": "brief/TITLE-v001.md", "preview": null,
 "sha256": "…", "status": "open", "created": "…"}
```

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/cards?episode=ID&status=open` | | list of cards |
| `POST /api/cards/{id}/accept` | `{"choice": 0}` (optional, index into `options`) | the card; the conductor continues |
| `POST /api/cards/{id}/decline` | `{"reason": "…"}` (optional) | the card |

Card kinds: `topic`, `title`, `proof`, `script`, `mix`, `preview`, `final`, `thumbnail`, `publish`, `spend`, `rule`,
`profile`, `other`, and the four motion cards `motion-plan`, `style-frame`, `template`, `baseline` (see "Motion cards"
below). Optional `data` fields the UI shows: `estimate` (`local_seconds`, `local_source`, `rented_seconds`,
`rented_usd`, `rented_usd_worst`, `gpus`, `gpu_name`), `amount_usd`, `cap_usd` or `budget_usd`, `referral`, `rule`,
`source`, `profile`, `schedule` (ISO time, publish cards), `facts` (`[{"label", "value"}]`).
A `spend` card carries `amount_usd` and the two estimates; a `rule` card carries the rule text and its source; a `profile`
card carries the profile and a 10-second preview video path.
Any card may carry `data.images` (a list of picture URLs); `needs` on an episode uses them when the card kind has no
pictures of its own.

| Method and path | Body | Answer |
|---|---|---|
| `POST /api/cards/{id}/strike` | `{"row": "beat:4", "struck": true}` (`row` is `beat:N`, `new:ID` or `upgrade:ID`; `struck: false` brings a row back) | the same card, now showing the next motion plan version (new `file`, `sha256`, `data`). 409 when the card is answered, the row is the only chosen upgrade, or the plan would no longer pass its check; 404 for an unknown card |

## Motion cards

Code: `crewcut/motion/cards.py` (what a yes or a no does), `director.py`, `custom.py`, `library.py`, `ratchet.py`. A yes
goes through `POST /api/cards/{id}/accept` like every card; each motion card refuses a yes (409) when its files changed
after it was made.

**`motion-plan`** (one per video; `file` is `edit/motion-plan-vNNN.md`). Shows the three columns as media, the
density and budget in one line, and one yes. A tap on a row strikes it (`/strike`), which writes the next plan version
and points the same card at it. Shelf pieces (column a) may be built while the card is open; new pieces (b) and
upgrades (c) wait for the yes.

```json
{"motion_plan": {
   "version": 2, "file": "edit/motion-plan-v002.json", "md": "edit/motion-plan-v002.md", "json_sha256": "…",
   "columns": {
     "a": [{"row": "beat:2", "beat": 2, "time": "0:06", "purpose": "believe the price",
            "picture": "the price rolls and lands on thirty as the word is said", "piece": "number_roll",
            "params": {"value": "30", "unit": "cents"}, "length_s": 3.6, "cost_usd": 0.0,
            "media": {"loop": "/api/motion/app/samples/number_roll-v2-landscape.mp4", "poster": "…"},
            "struck": false}],
     "b": [{"row": "new:handoff", "id": "handoff", "beat": 3, "brief": "Four jobs leave the laptop for a rented GPU.",
            "why_new": "No shelf piece shows work moving between machines.", "kind": "full", "plates": 1,
            "effort": "M", "cost_usd": 0.3, "cap_usd": 1.0, "struck": false,
            "beats": [{"row": "beat:3", "beat": 3, "time": "0:12", "purpose": "…", "picture": "…",
                       "piece": "handoff", "length_s": 5.0, "struck": false}]}],
     "c": [{"row": "upgrade:u1", "id": "u1", "upgrade": "Every exit from a full-frame piece is caused by a motion",
            "source": {"kind": "lesson", "ref": "2026-11-17-3"}, "effort": "S", "cost_usd": 0.0, "chosen": true,
            "struck": false, "beats": []}]},
   "quiet": [{"row": "beat:1", "beat": 1, "time": "0:00", "purpose": "know what this is",
              "picture": "the speaker alone", "struck": false}],
   "density": "full-frame 2 of max 5 · all motion 3 in 6:10 (max 12) · heroes 0",
   "budget": "GPU about $0.30, cap $2", "estimate_usd": 0.3, "cap_usd": 2.0, "bar": "002-local-ai", "short": false},
 "cap_usd": 2.0, "images": ["…"]}
```

`quiet` are the beats left to the speaker (most beats). `source.kind` is `lesson`, `reference`, `baseline` or
`retention`. `media.loop`/`poster` may be `null` (a template without samples). The cap is $2 for a long video and
$0.50 for a Short unless `[motion] cap_usd` / `cap_usd_short` in `config/crewcut.toml` say otherwise; renting a GPU
still asks with its own `spend` card, with this cap.

**`style-frame`** (one per custom piece and round; `file` is our first frame). Two pictures side by side per format:
ours and the reference (or the bar's frame when there is no reference). Nothing animated is built before the yes.

```json
{"insert": "m3", "round": 1,
 "frames": [{"format": "landscape", "ours": "motion/m3/frame-v1-landscape.png",
             "ours_url": "/api/files/003-local-ai/motion/m3/frame-v1-landscape.png",
             "ref": "motion/m3/refs/reel.png", "ref_url": "/api/files/003-local-ai/motion/m3/refs/reel.png",
             "ref_label": "reference", "hue": {"dominant_share": 0.24, "ok": true}},
            {"format": "portrait", "ours": "motion/m3/frame-v1-portrait.png", "ours_url": "…", "ref": null,
             "ref_url": null, "ref_label": "no reference: say what it should beat", "hue": {"…": "…"}}],
 "images": ["…"]}
```

`ref_label` is `reference`, `the bar` or the no-reference sentence. A no (`decline` with a reason) goes back to the
Designer for a new frame and a new card.

**`template`** ("Keep it in your library?"): the promoted piece with its sample loops and its params. Yes sets
`approved` in `brand/templates/motion/library.json`; no takes the new version out again (the previous version, if
any, comes back).

```json
{"template": {"name": "gpu_handoff", "title": "GPU hand-off", "version": 2, "kind": "full",
              "formats": ["landscape", "portrait"], "params": {"comp": "Main", "jobs": 4, "label": "GPU"},
              "samples": {"landscape": "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2-landscape.mp4",
                          "portrait": "…"},
              "poster": "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2.jpg",
              "made_from": {"episode": "003-local-ai", "insert": "m3"}, "sha256": "…", "replaces": 1},
 "images": ["…"]}
```

**`baseline`** ("Raise the motion bar from 002 to 003?"; `file` is the motion report). Old and new episode with their
named strengths. Only this yes moves the bar, and the server refuses it (409) when the bar moved since, the report
changed, or a measured value is worse (the bar never moves down).

```json
{"old": {"episode": "002-local-ai", "strengths": [{"name": "numbers land heavy", "time": 7.0, "frame": "…"}],
         "measured": {"motion_moments": 5, "critic_errors": 0}},
 "new": {"episode": "003-local-ai", "report": "review/motion-report-v002.json",
         "strengths": [{"name": "every exit is caused by a motion", "time": 41.2,
                        "frame": "review/motion-v002/m3/sheet.jpg"}],
         "measured": {"motion_moments": 6, "critic_errors": 0, "upgrades_landed_share": 1.0},
         "better": [{"what": "the number lands on the spoken word", "time": 7.2, "against": "numbers land heavy",
                     "frame": "…"}]},
 "report_sha256": "…", "images": ["…"]}
```

An `other` card with `data.motion_merge: true` (and `lessons`: the count) asks to merge the motion lessons when there
are more than 40.

## Motion

Code: `crewcut/motion/views.py`, `library.py`, `ratchet.py`. Read-only.

| Method and path | Answer |
|---|---|
| `GET /api/episodes/{id}/motion` | `{plan, pieces, report, retention}` (below); 404 for an unknown episode |
| `GET /api/motion/library` | `{"templates": [row, …]}`: the shelf, the user's pack first, then the app's, then episode pieces |
| `GET /api/motion/ratchet` | `{"bar": {…} or null, "lessons": [{"id", "date", "rule", "evidence", "source", "line"}], "merge_needed": false, "references": [{"id", "link", "file", "by", "reason", "episode", "tags", "timing", "added", "local_only"}]}` |
| `GET /api/motion/app/samples/{path}` | a sample loop or poster of an app template (`templates/motion/samples/`) |

```json
{"plan": {"file": "edit/motion-plan-v002.json", "md_url": "/api/files/003-local-ai/edit/motion-plan-v002.md",
          "version": 2, "card": {"id": 12, "status": "open"}, "approved": false,
          "columns": {"a": [], "b": [], "c": []}, "quiet": [], "density": "…", "budget": "…", "estimate_usd": 0.3,
          "cap_usd": 2.0, "bar": "002-local-ai", "short": false},
 "pieces": [{"id": "m3", "kind": "custom", "scene": null, "source": "motion/m3/comp.jsx", "beat": 3, "column": "b",
             "state": "style frame", "brief": "Show how the agent hands a render job to a rented GPU",
             "loop": null, "poster": "/api/files/003-local-ai/motion/m3/frame-v1-landscape.png",
             "start": 41.0, "end": 47.5, "transparent": false}],
 "report": {"better": "the number lands on the spoken word (0:07.2)", "behind": "…", "next": "promote m3 as gpu_handoff",
            "verdict": "better", "file": "review/motion-report-v002.json",
            "url": "/api/files/003-local-ai/review/motion-report-v002.md"},
 "retention": {"fetched": "2026-11-20", "summary": {"moments": 4, "held": 3, "dropped": 0, "held_share": 0.75},
               "unproven": true}}
```

- `plan`: the newest `edit/motion-plan-vNNN.json`, with the columns of its card (or computed when it has no card yet);
  `null` before the motion pass.
- `pieces`: the motion inserts of the newest edit plan, plus custom pieces (`motion/<id>/`) not in it yet. `state` is
  `planned`, `style frame` (its card is open or answered with a note), `building`, `in review` (the newest Critic
  bundle has errors for it) or `done` (0 errors). `kind` is `library` (a `scene`) or `custom` (a `source`); custom ones
  carry the brief's first line. `loop` is the encoded clip in `render/inserts/`, `poster` the middle rendered frame or
  the newest style frame.
- `report`: the newest motion report's three lines (better, behind, next); `null` before the first.
- `retention`: from `review/retention.json`; marked `unproven` until a real channel's data has been seen.

A shelf row: `{"name", "origin": "app" | "pack" | "episode", "title", "description", "kind": "full" | "overlay",
"formats", "version", "versions", "params", "path", "samples": {"landscape", "portrait", "poster"} (URLs, each
optional), "made_from", "approved" (`null` until the template card's yes), "needs_plates", "notes"}`; app rows have
`overridden` (the pack has its own copy); episode rows have `episode`, `insert`, `promoted_as` and `header_ok`. Pack
and app rows also carry `uses`: the videos whose newest edit plan has a motion insert with this `scene` (or
`scene@N`), as `[{"episode", "plan", "insert", "version"}]` (`version` is the pin, else `null`).

## Team, activity and logs

| Method and path | Answer |
|---|---|
| `GET /api/team` | identities (as in `state.team`) with `soul` (the short "how I work" text) and `sources` |
| `GET /api/jobs?episode=ID&status=running` | jobs with identity, step, doing, progress, seconds, cost |
| `GET /api/jobs/{id}/log` | `{"lines": ["…"]}`: the readable log of one job (tool calls and messages, secrets removed) |

## Brand and onboarding

The onboarding chat uses the pseudo-episode id `_onboarding`: `GET/POST /api/episodes/_onboarding/messages` and cards
with `"episode": "_onboarding"` (the `profile` card). It never appears in `state.episodes`.

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/profile` | | `{"source": "neutral" or "brand", "rows": [{"label": "Accent", "value": "#E4572E", "kind": "color", "source": "from your website"}], "preview": "path or null", "rules": [{"step", "date", "rule", "source"}]}` |
| `POST /api/onboarding` | `{"links": ["https://…"], "text": "optional sentence"}` | `{"job": 31}`; the Brand identity works, then posts a `profile` card |

## Connect Claude and Codex

The CLIs' own sign-in, driven by the server (`crewcut/engines/connect.py`); no OAuth client of Crewcut's own. Writes
need a local origin like every write.

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/engine/login` | | `{"claude": {"installed", "connected", "source": "stored", "environment" or null, "signing_in"}, "codex": {"installed", "connected", "status"?, "url"?, "code"?, "text"?}, "chosen": "claude"}` |
| `POST /api/engine/claude/connect` | `{}` | `{"url": "https://claude.ai/oauth/authorize?…"}`: `claude setup-token` runs with `BROWSER=true`; only a link to claude.ai, claude.com, console.anthropic.com or platform.claude.com counts. 409 while Claude Code is still being installed, 502 when no link comes |
| `POST /api/engine/claude/code` | `{"code": "…"}` (8 to 1024 of `A-Za-z0-9_-#.:`) | `{"connected": true, "account": {"email"?, "orgName"?, "subscriptionType"?, "authMethod"?}}`; the token goes to `/opt/engine/secrets/claude-oauth-token` (0600) and into the server's environment. 400 for a malformed code (the sign-in stays open), 409 when no sign-in runs, 502 when Claude refuses the code |
| `POST /api/engine/claude/disconnect` | `{}` | as `GET /api/engine/login`; 409 when the token comes from the environment (`.env` or the desktop app) |
| `POST /api/engine/codex/connect` | `{}` | `{"status": "waiting", "url", "code"}` (installs Codex first when needed); `GET /api/engine/login` says when it is connected |
| `POST /api/engine/codex/disconnect` | `{}` | as `GET /api/engine/login` |

The same steps on the command line, as JSON lines (the desktop app uses them through `docker compose exec`):
`crewcut engine connect claude [--print-token]` prints `{"step": "url", "url"}`, reads the code as one line on stdin,
then prints `{"step": "done", "account", "token" or "stored": true}` or `{"step": "error", "text"}`;
`crewcut engine connect codex` prints `{"step": "device", "url", "code"}`, then `done` or `error`;
`crewcut engine disconnect claude|codex`. Run as root (as `docker compose exec` does), they switch to the studio
folder's owner first.

## Money and compute

| Method and path | Answer |
|---|---|
| `GET /api/money` | as `state.money` plus `rows` (cost book entries) |
| `GET /api/compute/estimate?kind=blender&frames=840` | `{"local_seconds", "rented_seconds", "rented_usd", "gpus", "suggest_rent", "sentence", "referral": {"url", "note"} or null}` |

## Live updates

`GET /api/events` is a server-sent event stream. Each event:

```
event: activity | message | card | cost | episode
data: {"…": "same shapes as above"}
```

The UI keeps its state from `GET /api/state` and applies events. On a broken stream it reconnects and fetches the state
again.

## Teleprompter

Separate port (`4748` by default), reachable from a phone in the same network. Every episode has a random token;
`crewcut prompter <episode>` prints the URL and a QR code.

| Method and path | Answer |
|---|---|
| `GET /p/{token}` | the teleprompter page |
| `GET /p/{token}/script` | `{"title", "mode": "full" or "points", "format": "script" or "cuesheet", "pages", "cps": 17.0, "version", "blocks": [{"text", "points": ["…"], "n": 1, "section": 1, "weight": 120}]}`: numbered speaking blocks (`n` is null for a heading), a new `section` after two or more blank lines, `weight` the block's characters plus a breath on the timeline, `cps` characters per second at speed 1.0. A cue sheet (`"format": "cuesheet"`) has one block per fixed line and per bullet, each also with `kind` (`fixed` or `bullet`), `role`, `page`, `unit`, `picture`, `question`, `groups` and `big`, one `section` per page, and `pages: [{"page": "unit 1", "label", "first": <block index>, "short"}]`; `pages` is empty for a normal script |
| `GET /p/{token}/control[?after=<seq>&wait=<s>]` | `{"playing", "speed", "mirror", "size", "guide", "block", "offset", "at", "seq", "by", "cue", "now", "waited", "version", "position"}`. The shared timeline: the anchor (`block` index, `offset` 0..1 in it) at server time `at` (ms), moving `cps × speed` characters a second while playing. `seq` rises with every write, `by` is the screen that wrote it, `cue` rises with every jump, `now` is the server time, `takes` is the take count per cue sheet page (`{"unit 1": 2}`). With `after` and `wait` (at most 25 s) the answer waits until `seq` differs from `after`. |
| `POST /p/{token}/control` | Settings (`playing`, `speed`, `mirror`, `size`, `guide`) and an optional `action` with `client` (the screen's id): `jump`, `next`, `prev`, `repeat` with `block` (to its start; while playing the text holds there 1.5 s), `start` (the beginning, paused), `scroll` and `scrolled` with `block` and `offset` (a hand scroll and its end), `end`. On a cue sheet `next`, `prev` and `repeat` go to the start of a page (`block` optional: without it, from the block on the reading line), and every command that lands at the start of a page counts a new take of it. The last block of every page is an end on the timeline, like the end of the script: playing stops there (`end`), and a command that arrives after a page ended first ends it, so the next page waits for `playing`. Answers the new state. Jumps, repeats, the end of a hand scroll, play and pause add a line to the take log `brief/prompter-log-<UTC date>.jsonl`: `{"time": "…Z", "unix_ms", "action", "block", "section", "offset", "playing", "script", "words", "page", "unit", "take"}` (the last three are null for a normal script). |

## Stop a rented GPU, make a Short

| Method and path | Body | Answer |
|---|---|---|
| `POST /api/episodes/{id}/gpu/{rental}/stop` | none | `{stopped, rentals: [ids], cost_usd}`: every machine of that render (its compute session) is deleted now; frames that came home stay. 404 when the machine is not of this episode. Never spends money. |
| `POST /api/episodes/{id}/shorts` | none | `{episode, job}`: a new Short in clip mode from this long episode, and the Scout's queued job (it shows in `/api/jobs` and Working now). 400 on a Short, 404 for an unknown episode. |

## Engine selection

`POST /api/engine/{claude|codex}/use` selects a connected engine for new work. A missing login returns 409, an invalid
engine returns 400. It starts no job and disconnects neither account. The response matches `GET /api/engine/login`.
