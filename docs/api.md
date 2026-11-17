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
- `cover`: URL of the newest thumbnail image, or `null`.
- `needs`: the first open card with up to three small pictures, or `null`:
  `{"card": 41, "kind": "thumbnail", "title": "Thumbnail A, test B", "images": ["/api/files/…", "…"]}`. The pictures
  are the thumbnail variants for a `thumbnail` card, the 3D frames (or probe stills) for a `spend` card, else the
  card's `preview` or `file` when it is an image.
- `seconds`: length of the newest export or cut (see `cut` under "Episode media"), or `null`. ffprobe runs once per
  file version (cache keyed by path, size and mtime), not on every call.

Optional field of an activity: `preview`, the URL of the newest image written in the job's episode since the job
started (render frames, probe stills, thumbnail drafts, strip frames), for `running` and `waiting` jobs; else `null`.
A `thumbnail` job looks in `graphics/`, an `edit` job in `render/`, `review/` and `work/strip-*/`, others in all of
them. The scan is bounded (300 folders, depth 4) and cached per folder until its mtime changes.

## Episodes

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/episodes/{id}` | | episode as in `state.episodes[]` plus `project` (the raw `project.json`) and `files` (list of `{path, size, kind}` under `export/`, `graphics/`, `brief/`) |
| `GET /api/episodes/{id}/media` | | what the episode view shows first: thumbnails, the cut, 3D scenes, the rented GPU (see "Episode media" below) |
| `POST /api/episodes` | `{"text": "an idea in one sentence"}` | the new episode; the Showrunner starts with the sentence |
| `GET /api/episodes/{id}/messages?after=ID` | | `[{"id", "at", "author", "text", "card", "cite", "step", "preview", "facts"}]`; `author` is `user` or an identity id; `cite`, `preview` (a file in the episode) and `facts` (`[{"label", "value"}]`) are optional |
| `POST /api/episodes/{id}/messages` | `{"text": "…"}` | the stored message; the Showrunner answers in later messages |
| `GET /api/files/{episode}/{path}` | | the file (video, image, text) for previews; only inside the episode folder |
| `POST /api/episodes/{id}/upload` | multipart, field `file` (one or more) | `[{"path": "inbox/…", "size"}]`; recordings dropped into the chat land in `studio/inbox/<episode>/` and the Editor ingests them |
| `GET /api/episodes/{id}/prompter` | | `{"url": "http://<lan-host>:4748/p/<token>", "qr_svg": "<svg …>"}` for the teleprompter on a phone |

## Episode media

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
`profile`, `other`. Optional `data` fields the UI shows: `estimate` (`local_seconds`, `local_source`, `rented_seconds`,
`rented_usd`, `rented_usd_worst`, `gpus`, `gpu_name`), `amount_usd`, `cap_usd` or `budget_usd`, `referral`, `rule`,
`source`, `profile`, `schedule` (ISO time, publish cards), `facts` (`[{"label", "value"}]`).
A `spend` card carries `amount_usd` and the two estimates; a `rule` card carries the rule text and its source; a `profile`
card carries the profile and a 10-second preview video path.

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
| `GET /p/{token}/script` | `{"title", "mode": "full" or "points", "blocks": [{"text", "points": ["…"]}]}` |
| `GET /p/{token}/control`, `POST /p/{token}/control` | `{"playing": bool, "speed": 1.0, "position": 0.0, "mirror": false, "size": 1.0}` (a second phone or the desktop can be the remote) |

## Stop a rented GPU, make a Short

| Method and path | Body | Answer |
|---|---|---|
| `POST /api/episodes/{id}/gpu/{rental}/stop` | none | `{stopped, rentals: [ids], cost_usd}`: every machine of that render (its compute session) is deleted now; frames that came home stay. 404 when the machine is not of this episode. Never spends money. |
| `POST /api/episodes/{id}/shorts` | none | `{episode, job}`: a new Short in clip mode from this long episode, and the Scout's queued job (it shows in `/api/jobs` and Working now). 400 on a Short, 404 for an unknown episode. |
