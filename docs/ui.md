# The web UI

The UI lives in `web/`: React 18, Vite 5, TypeScript (strict), plain CSS with tokens. It follows [DESIGN.md](../DESIGN.md)
and talks to the server only through [api.md](api.md). The container serves the built files from `web/dist/`.

## The three places

| Place | What it shows | Code |
|---|---|---|
| Episodes (left) | "New episode", one row per episode (title, current step, ten-segment bar, a dot when a card is open), then Profile and Crew | `src/components/Episodes.tsx` |
| Chat (center) | the episode header (title, meta, Teleprompter, the ten steps), the transcript, cards and previews, the composer | `src/views/EpisodeView.tsx`, `src/components/CardView.tsx`, `src/components/Composer.tsx` |
| Crew (right) | running, waiting and queued jobs from `state.activity`, "Done today", the money row | `src/components/Crew.tsx` |

Profile, Crew and a job log open in the center as read-only views (`src/views/ReadOnlyViews.tsx`). They have no edit
controls; each ends with "To change something, say it in the chat."

Below 1100 px the Crew column folds into a bar above the composer (a tap opens it as a sheet). Below 960 px the step
strip becomes "Step 6 of 10 · Edit" with a bar. Below 760 px the Episodes list becomes a menu behind the button at the
top left.

### Views in the URL

The open view lives in the hash, so Back works and screenshots can open each place:

| Hash | View |
|---|---|
| `#/e/<episode-id>` | an episode chat |
| `#/onboarding` | the onboarding chat (pseudo-episode `_onboarding`) |
| `#/new` | no episode selected: the composer starts one |
| `#/profile` | the profile (style pack values, rules by step, the 10-second preview) |
| `#/crew` | the crew (identities, rights, sources, the not-affiliated note) |
| `#/job/<id>` | the read-only log of one job |

Without a hash the app opens the onboarding chat when `app.onboarded` is false, else the first episode, else `#/new`.
`?theme=light` or `?theme=dark` forces a theme; without it the system setting decides.

### Input

The composer is the only text field. Enter sends, Shift+Enter starts a new line. The microphone button uses the
browser's speech recognition (`SpeechRecognition` or `webkitSpeechRecognition`) and is hidden when the browser has
none. Some browsers send the audio to their maker's speech service; that is the browser's behaviour, not Crewcut's.

Where a sentence goes:

- an episode chat is open: `POST /api/episodes/{id}/messages`;
- `app.onboarded` is false: `POST /api/episodes/_onboarding/messages` (the empty state says "Paste your links.");
- no episode selected (`#/new`): `POST /api/episodes`, then the new episode opens;
- a read-only view is open: the last opened episode chat.

Dropping files on an episode chat uploads them with `POST /api/episodes/{id}/upload` and shows one line per file.

Cards have one primary button (`POST /api/cards/{id}/accept`, with `choice` for options). Ctrl/Cmd+Enter accepts the
lowest open card that is visible in the chat. Decided cards fold to one line ("Title approved · …").

### Live updates

On load the app fetches `GET /api/state`, then opens `EventSource('/api/events')` and applies `activity`, `message`,
`card`, `cost` and `episode` events. On a broken stream it closes it, waits 1 s, 2 s, 4 s … up to 30 s, fetches the state
and new messages again, and reopens. While it retries, a quiet line says so. An `activity` event for a job the screen
has not seen, without `identity` and `doing`, triggers one state fetch instead of a guess.

### Fields the UI reads beyond api.md

All optional; the UI works without them.

| Where | Field | Use |
|---|---|---|
| message | `step` | the step label in the "who" line ("Edit · 40 min ago") |
| message | `preview` (path in the episode) | a video or image under the message |
| message | `facts` (`[{label, value}]`) | a small table of numbers under the message |
| card | `data.estimate.*` or flat `data.*` | spend card: `local_seconds`, `local_source`, `rented_seconds`, `rented_usd`, `rented_usd_worst`, `gpus`, `gpu_name` |
| card | `data.amount_usd`, `data.cap_usd` or `data.budget_usd`, `data.referral` | spend card: button amount, cap, referral note |
| card | `data.rule`, `data.source` | rule card |
| card | `data.profile` (the `GET /api/profile` shape) | profile card rows |
| card | `data.schedule` (ISO time) | publish card button ("Publish on Friday 17:00") |
| card | `data.facts` | facts table on any card |
| activity | `ended` | the "Done today" list |

A message that only repeats the title of the card it carries is not shown; the card is.

File previews use `/api/files/{episode}/{path}`. A path that already starts with `/api/` (the profile preview) is
used as it is.

## Demo mode

`?demo=1` (or no API answering at the address: a network error, a 404 page or an answer that is not JSON) switches to
an in-memory backend in `src/demo/`. It answers the same calls with fixtures shaped like api.md and the mockup's
content: three made-up episodes, an open spend card, a running crew and a money row. Nothing runs; a sentence gets a
reply that says so. Test data only.

When the demo starts on its own, the Episodes column says "Demo data. Crewcut is not running at this address." With
`?demo=1` it says "Demo data. Nothing here is real."

Demo works from any static server at the site root, for example:

```
cd web && npm run build
python3 -m http.server -d dist 8080      # then open http://localhost:8080/index.html?demo=1
```

CI (`.github/workflows/screens.yml`) screenshots `index.html?demo=1` at 1440x900 (light and dark) and 390x844, and can
add `#/profile`, `#/crew` or `#/job/12` for the other views.

## The teleprompter

A second Vite entry, `prompter.html`, served by the teleprompter port at `/p/<token>` (assets under `/assets/`).

- Reads the token from the path (`?token=` during development) and loads `/p/<token>/script`.
- Big text on a dark background with a reading line at a third of the height. Full text or key points.
- Tap the text or press Space to play and pause. Arrow up and down change the speed, `+` and `-` the size, `M` mirrors,
  `P` switches the mode, Home goes back to the start.
- Follows `/p/<token>/control` every 500 ms. A change on this screen is posted at once; the playing screen reports its
  position while it plays, so a second phone or the desktop can drive it. `?remote=1` shows only the controls (the
  "Open the remote" link in the Teleprompter popover).
- Keeps the phone screen on while it plays, where the browser allows it (Wake Lock).
- `?demo=1` shows a demo script without a server.

## Run against a local server

```
crewcut serve                 # API on 127.0.0.1:4747, teleprompter on :4748
cd web
npm install
npm run dev                   # http://localhost:5173, forwards /api to :4747 and /p/<token>/script|control to :4748
```

`CREWCUT_API` and `CREWCUT_PROMPTER` override the two addresses. In development the teleprompter opens at
`http://localhost:5173/prompter.html?token=<token>`. For the real setup run `npm run build`; the server serves
`web/dist/`.

## Checks

| Command | What it checks |
|---|---|
| `npm run typecheck` | TypeScript, strict |
| `npm run test` | vitest + Testing Library: loading (spinner after 300 ms), empty, error with retry, long content (90-character title, 4,000-word message, 30 jobs), the engine not logged in, demo fallback, card accept (options, Ctrl+Enter, spend card, error), the composer (Enter, Shift+Enter, new episode, onboarding, failed send), the teleprompter |
| `npm run check:tokens` | no raw colour values in `src/` outside `src/styles/tokens.css` (rule 4) |
| `npm run check:forms` | exactly one text field (the composer) and no `<form>` with more than one field (rules 1.2, 3) |
| `npm run check:words` | no emoji, no exclamation marks in user-facing text, no "OK", "Submit" or "Yes" labels (rules 8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in light and dark, the focus ring 3:1 (rule 4) |
| `npm run check` | all four checks |
| `npm run build` | type check, then the production build into `dist/` |

The words check reads `.ts` and `.tsx` files with the TypeScript parser, so the `!` operator in code does not count;
class names, roles and ids in JSX attributes are skipped.

## Not done here

The UI was not opened in a browser while it was built; the CI job `screens` takes the screenshots. Until those and a
manual run exist, the layout, motion, the speech button, drag and drop, the QR scan and the teleprompter on a real
phone are untested. The unit tests run in jsdom, which has no layout.
