# The web UI

The UI lives in `web/`: React 18, Vite 5, TypeScript (strict), plain CSS with tokens. It follows [DESIGN.md](../DESIGN.md)
and talks to the server only through [api.md](api.md). The container serves the built files from `web/dist/`.

It should feel like a good Mac app that happens to run in a browser: three floating surfaces on a calm window, a
translucent Episodes panel, a real toolbar the chat runs under, soft depth, springs, and every action on the keyboard.
It does not imitate macOS: no fake window buttons, no fake menu bar, no Apple logo, no Apple font in the repository.

## The three places

| Place | What it shows | Code |
|---|---|---|
| Episodes (left) | the brand and a "New episode" icon, one row per episode (title, current step, ten-stroke bar, a dot when a card is open), then Profile and Crew. Material (rule 18) | `src/components/Episodes.tsx` |
| Chat (center) | the toolbar (title once the large title has scrolled away, the ten step dots, Teleprompter, Crew column, palette), the large title, the transcript, cards and previews, the floating composer | `src/views/EpisodeView.tsx`, `src/components/Toolbar.tsx`, `src/components/CardView.tsx`, `src/components/Composer.tsx` |
| Crew (right) | running, waiting and queued jobs from `state.activity` as a grouped list, "Done today", the money row on a material bar. Opaque | `src/components/Crew.tsx` |

The window (`--window`, with a faint fixed gradient) holds the three places as floating surfaces, 8 px apart, with
radius 18 px. The chat runs under the toolbar (52 px, material) and under the composer, which floats 16 px above the
bottom edge; the app measures the composer's height into `--dock-h` so the last message can scroll clear of it.
Cmd+B folds the Episodes panel and Cmd+Alt+B the Crew panel (a spring on the grid columns).

Profile, Crew and a job log open in the center as read-only views (`src/views/ReadOnlyViews.tsx`). They have no edit
controls; each ends with "To change something, say it in the chat."

Below 1100 px the Crew column folds into a bar above the composer (a tap opens it as a sheet). When the toolbar is
narrower than 720 px (a container query, so it follows the toolbar, not the window) the ten dots fold to
"6 of 10 · Edit" with a thin capsule. Below 760 px the Episodes list becomes a menu behind the button at the left of
the toolbar, and the chat surface fills the screen.

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
`?theme=light` or `?theme=dark` forces a theme; without it the choice made in the palette ("Switch to the dark theme",
kept in the browser's storage where the browser allows it) or else the system setting decides.

On Apple devices `main.tsx` puts the class `is-apple` on `<html>`, and the CSS uses the installed system font through
`system-ui`. Everywhere else, and in every CI screenshot, the font is the bundled Inter. No Apple font file is in the
repository or in `dist/` (`npm run check:fonts`).

### Input

The composer is the one field for sentences. Enter sends, Shift+Enter starts a new line; it grows to six lines, then
scrolls inside. The microphone button uses the browser's speech recognition (`SpeechRecognition` or
`webkitSpeechRecognition`) and is hidden when the browser has none; while it listens, five small strokes follow the
microphone level (through `getUserMedia`, nothing is recorded or sent by Crewcut). Some browsers send the audio to their
maker's speech service; that is the browser's behaviour, not Crewcut's.

The second text field is the search field of the command palette (`src/components/Palette.tsx`). It only picks from a
list of episodes, views and actions; it takes no values.

Where a sentence goes:

- an episode chat is open: `POST /api/episodes/{id}/messages`;
- `app.onboarded` is false: `POST /api/episodes/_onboarding/messages` (the empty state says "Paste your links.");
- no episode selected (`#/new`): `POST /api/episodes`, then the new episode opens;
- a read-only view is open: the last opened episode chat.

Dropping files on an episode chat uploads them with `POST /api/episodes/{id}/upload` and shows one line per file.

Cards have one primary button (`POST /api/cards/{id}/accept`, with `choice` for options). Ctrl/Cmd+Enter accepts the
lowest open card that is visible in the chat. Decided cards fold to one line ("Title approved · …"); a card decided
while it is on screen folds away with a spring first.

A spend card shows both ways as two choice surfaces. The first choice is honest: the rented GPU only when it saves at
least an hour, else this machine (also when a time is not known). The button follows the choice: "Rent a GPU for $0.60"
accepts the card. "Render on this machine" never calls accept, because accepting a spend card means "rent"; it declines
the card (`POST /api/cards/{id}/decline`) with the reason "Local is fine. Render on this machine." and the card folds to
"GPU rental not taken · this machine renders".

### Keyboard and the command palette

| Shortcut | Does |
|---|---|
| Cmd/Ctrl+K | Command palette: episodes (Cmd+1 to 9), "Show profile", "Show the crew", "New episode", "Open teleprompter", "Switch to the dark/light theme", the panels |
| Cmd/Ctrl+N | New episode (`#/new`, focus in the composer) |
| Cmd/Ctrl+1 to 9 | Episode 1 to 9 |
| Cmd/Ctrl+B, Cmd/Ctrl+Alt+B | Episodes panel, Crew panel (below 760 px Cmd+B opens the Episodes menu) |
| Cmd/Ctrl+Enter | Accept the open card in view |
| Esc | Close the palette, the teleprompter dialog or the menu |
| / | Focus in the composer (when no field has the focus) |
| Arrow up and down | Move between episode rows |

Both Cmd and Ctrl work on every system; tooltips and keycaps show ⌘ on Apple devices and Ctrl elsewhere. Some browsers
keep Cmd/Ctrl+N and Cmd/Ctrl+1 to 9 for themselves; the palette offers the same actions. There is no shortcut to stop a
running job yet: the API has no endpoint for it.

### Live updates

On load the app fetches `GET /api/state`, then opens `EventSource('/api/events')` and applies `activity`, `message`,
`card`, `cost` and `episode` events. `crew` events (one direct message between crew members) are read and ignored: a
finished exchange arrives as a `message` with an `exchange`. On a broken stream it closes it, waits 1 s, 2 s, 4 s … up to 30 s, fetches the state
and new messages again, and reopens. While it retries, a slim line under the toolbar says "Lost the connection to the container. Retrying…". An `activity` event for a job the screen
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
| activity | `engine`, `model`, `effort`, `engine_version` | one quiet line in the job log view ("Runs on Claude Code 2.1.325 · model sonnet · effort medium"), never on the row |
| message | `exchange` (`{topic, result, messages: [{id, sender, recipient, kind, about, text, route, status}]}`) | a finished exchange between two crew members ([crew-talk.md](crew-talk.md)): one collapsed quiet line, "Critic and Editor · fix about review/cut-check-v001.json · 2 messages"; opened, who wrote to whom, the file in mono, the text |

A message that only repeats the title of the card it carries is not shown; the card is.

### States

| Place | State | What shows |
|---|---|---|
| Episodes | no episodes | "No episodes yet." in `--ink-3` |
| Chat | first start (not onboarded, empty onboarding chat) | no toolbar; the mark, "Paste your links." and "Website, YouTube channel, socials. The crew reads the rest."; the composer floats under the sentence (560 px) and glides to the bottom after the first message |
| Chat | an episode without messages | the large title, then "Say an idea below, or ask the Scout for three." |
| Chat | the live connection is lost | the slim line under the toolbar |
| Card | a preview loads | a placeholder of the same size on `--sunken`, with the run shimmer after 300 ms |
| Card | a preview fails | "Couldn't load the preview. The file is at episodes/003-…/review/frame-231.png." and "Try again" |
| Crew | nobody works | "Nobody is working. Nothing is running, nothing costs money." |
| Crew | the engine is not logged in | one line with a `--warn` dot: "Claude Code is not logged in. Run claude setup-token, put the value in .env and restart Crewcut." (in the crew bar below 1100 px) |
| Money | nothing spent | the three figures in `--ink-3` |

Only what arrives after a chat or the Crew column first showed animates in; what is already there stays still.

File previews use `/api/files/{episode}/{path}`. A path that already starts with `/api/` (the profile preview) is
used as it is.

## Demo mode

`?demo=1` (or no API answering at the address: a network error, a 404 page or an answer that is not JSON) switches to
an in-memory backend in `src/demo/`. It answers the same calls with fixtures shaped like api.md and the mockup's
content: three made-up episodes, an open spend card, a running crew and a money row. Nothing runs; a sentence gets a
reply that says so. Test data only.

When the demo starts on its own, the Episodes column says "Demo data. Crewcut is not running at this address." With
`?demo=1` it says "Demo data. Nothing here is real."

`?demo=1` is a still scene: the moment of the README image (the GPU card open with both ways, three rows in
"Working now", step 6 of 10, "Month $3.78 of $20"). `?demo=1&play=1` plays a short scripted sequence once, for the README
animation, and then stays still:

| From load | What happens |
|---|---|
| 0.6 s | the GPU card springs in with "On this machine" chosen (here 50 min against 12 min, so this machine is the honest first choice); the Showrunner's waiting row appears |
| 2.0 s | the choice moves to the rented GPU; the button now says "Rent a GPU for $0.60" |
| 3.3 s | the button is pressed (`data-pressed`), then released: the yes goes out and the card folds to one line |
| 4.2 s | "Editor · Rendering 3D scene 1 of 9 · rented GPU" slides into "Working now" |
| 6.9 s | `window.__crewcutPlayDone = true` |

The sequence starts 600 ms after the page has loaded and the screen listens for events. It clicks the real buttons, so
the screen does exactly what it does for a person. Both modes work inside an iframe (the CI script renders the app in a
1600 x 1000 frame at twice the density); storage is optional everywhere.

Demo works from any static server at the site root, for example:

```
cd web && npm run build
python3 -m http.server -d dist 8080      # then open http://localhost:8080/index.html?demo=1
```

CI (`.github/workflows/screens.yml`) screenshots `index.html?demo=1` at 1440x900 (light and dark) and 390x844, and can
add `#/profile`, `#/crew` or `#/job/12` for the other views. The README images and the animation come from
`tools/ci/readme_shots.mjs`.

## The teleprompter

A second Vite entry, `prompter.html`, served by the teleprompter port at `/p/<token>` (assets under `/assets/`).

- Reads the token from the path (`?token=` during development) and loads `/p/<token>/script`.
- Big text on a black background with a reading line at a third of the height. Full text or key points. The controls
  sit in one capsule with material at the bottom, every target at least 44 px. On an iPhone the text uses the system
  font.
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
| `npm run test` | vitest + Testing Library: loading (spinner after 300 ms), empty, error with retry, long content (90-character title, 4,000-word message, 30 jobs), the engine not logged in, demo fallback, card accept (options, Ctrl+Enter, spend card, error), the composer (Enter, Shift+Enter, new episode, onboarding, failed send), the teleprompter; the states table above, the step dots, the spend card's two ways (local declines, never accepts), the waiting row jumping to its card, the palette and shortcuts, crew talk (collapsed and opened), the still demo and the scripted sequence |
| `npm run check:tokens` | no raw colour values in `src/` outside `src/styles/tokens.css`; radii, shadows, durations and curves only from tokens (rules 4, 6, 9) |
| `npm run check:forms` | two text fields, the composer and the palette's search field, and no `<form>` with more than one field (rules 1.2, 3, 15) |
| `npm run check:words` | no emoji, no exclamation marks in user-facing text (tooltips too), no "OK", "Submit" or "Yes" labels (rules 8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in light and dark, material counted as its opaque fallback and over `--window`; the focus ring 3:1 (rules 4, 18) |
| `npm run check:fonts` | no font file in the repository or `dist/` whose name or inner name contains "SF Pro", "SF Compact", "SFNS", "SF Mono" or "New York"; no `@font-face` with these names (rule 5) |
| `npm run check:materials` | `backdrop-filter` only on the allowed surfaces, only inside `@supports`, after an opaque background, with fallbacks for reduced transparency and more contrast (rule 18) |
| `npm run check:motion` | every animation has a reduced-motion branch; only the run shimmer and the spinner loop; only `transform`, `opacity` and grid tracks animate (rule 9) |
| `npm run check` | all seven checks |
| `npm run build` | type check, then the production build into `dist/` |

The words check reads `.ts` and `.tsx` files with the TypeScript parser, so the `!` operator in code does not count;
class names, roles and ids in JSX attributes are skipped.

## Not done here

The UI was not opened in a browser while it was built; the CI job `screens` takes the screenshots. Until those and a
manual run exist, the layout, the material, the springs, the tooltips, the composer's travel on first start, the
microphone level, drag and drop, the QR scan and the teleprompter on a real phone are untested. The unit tests run in
jsdom, which has no layout, no CSS and no blur.

The spring curves are generated by `node scripts/springs.mjs` and pasted into `tokens.css`.
