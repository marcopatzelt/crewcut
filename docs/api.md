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

## Episodes

| Method and path | Body | Answer |
|---|---|---|
| `GET /api/episodes/{id}` | | episode as in `state.episodes[]` plus `project` (the raw `project.json`) and `files` (list of `{path, size, kind}` under `export/`, `graphics/`, `brief/`) |
| `POST /api/episodes` | `{"text": "an idea in one sentence"}` | the new episode; the Showrunner starts with the sentence |
| `GET /api/episodes/{id}/messages?after=ID` | | `[{"id", "at", "author", "text", "card", "cite", "step", "preview", "facts"}]`; `author` is `user` or an identity id; `cite`, `preview` (a file in the episode) and `facts` (`[{"label", "value"}]`) are optional |
| `POST /api/episodes/{id}/messages` | `{"text": "…"}` | the stored message; the Showrunner answers in later messages |
| `GET /api/files/{episode}/{path}` | | the file (video, image, text) for previews; only inside the episode folder |
| `POST /api/episodes/{id}/upload` | multipart, field `file` (one or more) | `[{"path": "inbox/…", "size"}]`; recordings dropped into the chat land in `studio/inbox/<episode>/` and the Editor ingests them |
| `GET /api/episodes/{id}/prompter` | | `{"url": "http://<lan-host>:4748/p/<token>", "qr_svg": "<svg …>"}` for the teleprompter on a phone |

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
