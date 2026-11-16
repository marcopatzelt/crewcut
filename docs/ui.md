# The web UI

The UI lives in `web/`: React 19, Vite 5, TypeScript (strict), plain CSS with tokens, and a few controls from
[Astryx](https://github.com/facebook/astryx) (MIT). It follows [DESIGN.md](../DESIGN.md) and talks to the server only
through [api.md](api.md). The container serves the built files from `web/dist/`.

It looks like one good Mac app window lying on a desk: the rendered wallpaper behind, the app as a single sheet of
glass, pictures first. The three dots in the title bar are decoration; there is no fake menu bar, no Apple logo and no
Apple font in the repository.

## The window and its places

| Part | What it shows | Code |
|---|---|---|
| Desk and window | the wallpaper (`--wallpaper`, dark `green-dusk`, light `mint-dawn`, 1280 px below 900 px), the glass window inset 22/26 px with radius 20 px | `src/App.tsx`, `src/styles/window.css` |
| Title bar (46 px) | three decorative dots, breadcrumbs ("Episodes / 012"), the search field that opens the command palette, the view's actions ("Make a Short" and the teleprompter in an episode, "3 at work" on the home) and the right-column toggle | `src/components/TitleBar.tsx` |
| Sidebar (236 px; 64 px icon rail in an episode and below 1200 px) | the places with counts (Episodes, Shorts, Crew, Style pack, GPU and renders), the channel from the style pack, the crew dock with Slate's faces | `src/components/Sidebar.tsx` |
| Main | the Episodes home, an episode's media, a read-only page, the onboarding chat or "New episode" | `src/views/Home.tsx`, `src/views/EpisodeView.tsx`, `src/views/EpisodeMedia.tsx`, `src/views/ReadOnlyViews.tsx` |
| Right column (318 px) | Working now (each running job with its newest picture and progress, then "Done today") and Spend | `src/components/Crew.tsx` |
| Crew chat (372 px, in an episode) | the working tiles on top, the money line, the transcript with cards and previews, the composer at the foot | `src/views/EpisodeView.tsx`, `src/components/ChatPane.tsx`, `src/components/CardView.tsx`, `src/components/Composer.tsx` |

**The Episodes home** is the start view. "Needs you" shows each episode with an open card as a large media card (the
cover, a tag with the question from `needs.title`, the length from `seconds`, the variants from `needs.images` small
inside the picture, the title and the step bar below). "In work and published" is a grid of 16:9 covers with the length
or, while someone works on it, a Slate line ("Editor is cutting, 6 of 10"). "Shorts" is one row of 9:16 frames with
the title drawn over them. Filter pills sit on top; the sidebar's "Shorts" is the Shorts pill (`#/episodes/shorts`).
"Import footage" appears only when an episode takes footage (the newest long video at the record or edit step); it
opens that episode and uploads the files into its chat.

**An episode** loads `GET /api/episodes/{id}/media` and shows, each only when it is there: the thumbnail variants (a
radio group; the recommended one chosen with a mint ring; "Use A" accepts the open thumbnail card with that choice; the
chosen one in a phone-size feed), the cut (frames, waveform from `peaks`, the Critic's markers, the style facts, the
time axis), the 3D scenes (one large, four small, render tiles on the one in work) and the rented GPU (time left, so
far, cap, progress, the delete note, Stop). Stop and "Make a Short" send one sentence to the chat, exactly as typing it
would ("Stop the rented GPU now. Keep the frames that are done.", "Make a Short from this episode."): the API has no
endpoint to stop a machine. The media load again every 4 s while a job of the episode runs, and at once when its jobs
or cards change. A server without the endpoint (404) counts as "no media yet"; an error shows one line with "Try
again".

Cmd+B folds the sidebar and Cmd+Alt+B the right column (a spring on the grid columns). Below 900 px the window fills
the screen, the parts stack in one scrolling column and the sidebar opens as a menu from the title bar.

Style pack, Crew, GPU and renders and a job log open in the main column as read-only pages. They have no edit
controls; each ends with "To change something, say it in the chat."

### Views in the URL

The open view lives in the hash, so Back works and screenshots can open each place:

| Hash | View |
|---|---|
| `#/episodes`, `#/episodes/<filter>` | the Episodes home, optionally filtered (`needs`, `work`, `long`, `shorts`, `done`) |
| `#/e/<episode-id>` | an episode: its media and its crew chat |
| `#/onboarding` | the onboarding chat (pseudo-episode `_onboarding`) |
| `#/new` | no episode selected: the composer starts one |
| `#/profile` | the style pack (values, rules by step, the 10-second preview) |
| `#/crew` | the crew (identities, rights, sources, the not-affiliated note) |
| `#/renders` | GPU and renders: every job that renders or rents, running first |
| `#/job/<id>` | the read-only log of one job |

Without a hash the app opens the onboarding chat when `app.onboarded` is false, else the Episodes home, else `#/new`
when there is no episode yet. The scripted demo (`?demo=1&play=1`) opens its episode.
`?theme=light` or `?theme=dark` forces a theme; without it the choice made in the palette ("Switch to the dark theme",
kept in the browser's storage where the browser allows it) or else the system setting decides.

On Apple devices `main.tsx` puts the class `is-apple` on `<html>`, and the CSS uses the installed system font through
`system-ui`. Everywhere else, and in every CI screenshot, the font is the bundled Inter. No Apple font file is in the
repository or in `dist/` (`npm run check:fonts`).

### Input

The composer is the one field for sentences ("Tell the crew what you want"); it sits at the foot of the crew chat, and
floats at the foot of the main column on the other views. Enter sends, Shift+Enter starts a new line; it grows to six lines, then
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
| Cmd/Ctrl+K | Command palette (also the search field in the title bar): episodes (Cmd+1 to 9), "Show all episodes", "Show the Shorts", "Show the style pack", "Show the crew", "Show GPU and renders", "New episode", "Open teleprompter", "Switch to the dark/light theme", the sidebar and the right column |
| Cmd/Ctrl+N | New episode (`#/new`, focus in the composer) |
| Cmd/Ctrl+1 to 9 | Episode 1 to 9 |
| Cmd/Ctrl+B, Cmd/Ctrl+Alt+B | Sidebar, right column (below 760 px Cmd+B opens the menu) |
| Cmd/Ctrl+Enter | Accept the open card in view |
| Esc | Close the palette, the teleprompter dialog or the menu |
| / | Focus in the composer (when no field has the focus) |
| Arrow up and down | Move between the places of the sidebar |

Both Cmd and Ctrl work on every system; tooltips and keycaps show ⌘ on Apple devices and Ctrl elsewhere. Some browsers
keep Cmd/Ctrl+N and Cmd/Ctrl+1 to 9 for themselves; the palette offers the same actions. There is no shortcut to stop a
running job yet: the API has no endpoint for it.

### Live updates

On load the app fetches `GET /api/state`, then opens `EventSource('/api/events')` and applies `activity`, `message`,
`card`, `cost` and `episode` events. `crew` events (one direct message between crew members) are read and ignored: a
finished exchange arrives as a `message` with an `exchange`. On a broken stream it closes it, waits 1 s, 2 s, 4 s … up to 30 s, fetches the state
and new messages again, and reopens. While it retries, a slim line under the title bar says "Lost the connection to the container. Retrying…". An `activity` event for a job the screen
has not seen, without `identity` and `doing`, triggers one state fetch instead of a guess.

### Fields the UI reads beyond api.md

All optional; the UI works without them.

| Where | Field | Use |
|---|---|---|
| episode | `cover`, `needs`, `seconds` | the cover on the home, the "Needs you" media card, the length chip |
| activity | `preview` | the newest picture of a running job in Working now |
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
| Home | no episodes | Slate dozing, "No episodes yet. Start one with New episode." and the button |
| Home | a filter without episodes | "Nothing here right now." |
| Main | first start (not onboarded, empty onboarding chat) | the title bar without search and actions; Slate waving, "Paste your links." and "Website, YouTube channel, socials. The crew reads the rest."; the composer floats under the sentence (560 px) and glides to the bottom after the first message |
| Episode | no media yet (or a server without the media route) | Slate dozing, "No pictures yet. Thumbnails, the cut and renders show here as the crew makes them." |
| Episode | the strip is being made (`cut.pending`) | "The strip and the waveform are on their way." and "Frames come as soon as the cut is read." |
| Episode | the media fail | "Couldn't load the pictures of this episode. …" and "Try again" |
| Crew chat | no messages | "Say an idea below, or ask the Scout for three." |
| Window | the live connection is lost | the slim line under the title bar |
| Card | a preview loads | a placeholder of the same size on `--sunken`, with the run shimmer after 300 ms |
| Card | a preview fails | "Couldn't load the preview. The file is at episodes/003-…/review/frame-231.png." and "Try again" |
| Working now | nobody works | "Nobody is working. Nothing is running, nothing costs money." |
| Working now | the engine is not logged in | one line with a `--warn` dot: "Claude Code is not logged in. Run claude setup-token, put the value in .env and restart Crewcut." |
| Spend | nothing spent | the three figures in `--ink-3` |

Only what arrives after a chat or Working now first showed animates in; what is already there stays still.

File previews use `/api/files/{episode}/{path}`. A path that already starts with `/api/` (the profile preview) is
used as it is.

## Demo mode

`?demo=1` (or no API answering at the address: a network error, a 404 page or an answer that is not JSON) switches to
an in-memory backend in `src/demo/`. It answers the same calls, the media route too, with fixtures shaped like api.md.
Everything in it is English. The pictures come from `src/demo/media.json` (web-sized stills under
`public/demo/media/`, made by `tools/demo/build_media.py`): episode 012 "Claude improves a website 100 times" with three
thumbnail variants, ten strip frames, the commercial's five 3D scenes and a running GPU rental; the commercial, an
episode in work, four published ones and nine Shorts. Chats, jobs and money are made up. Nothing runs; a sentence gets a
reply that says so.

When the demo starts on its own, Working now says "Demo data. Crewcut is not running at this address." With
`?demo=1` it says "Demo data. Nothing here is real."

`?demo=1` is a still scene: the home with two open questions, or with `#/e/012-website-100-times` the episode with the
thumbnail pick open, scene 5 rendering at 62 % on a rented RTX 4090, three of the crew working and "Month $4.10 of
$20". `?demo=1&play=1` opens episode 012 and plays a short scripted sequence once, for the README animation, then
stays still:

| From load | What happens |
|---|---|
| 0.6 s | the GPU card springs into the crew chat with "On this machine" chosen (50 min against 12 min, so this machine is the honest first choice); the Editor's waiting row appears |
| 2.0 s | the choice moves to the rented GPU; the button now says "Rent a GPU for $0.60" |
| 3.3 s | the button is pressed (`data-pressed`), then released: the yes goes out and the card folds to one line |
| 4.2 s | "Renders 3D scene 5 of 5 on a rented RTX 4090" slides into the working tiles; the GPU card and the render tiles of scene 5 appear among the media |
| 6.9 s | `window.__crewcutPlayDone = true` |

The sequence starts 600 ms after the page has loaded and the screen listens for events. It clicks the real buttons, so
the screen does exactly what it does for a person. Storage is optional everywhere.

Demo works from any static server at the site root, for example:

```
cd web && npm run build
python3 -m http.server -d dist 8080      # then open http://localhost:8080/index.html?demo=1
```

CI (`.github/workflows/screens.yml`) screenshots the home (`index.html?demo=1`) and episode 012
(`#/e/012-website-100-times`) at 1440x900 in light and dark, at 1100 and at 390x844, plus `#/profile` and `#/crew`.
The README images (the app itself at 1600 x 1000, twice the density: `crewcut-{dark,light}.png` for episode 012,
`crewcut-episodes-{dark,light}.png` for the home) and the animation (`crewcut-demo.webp` and `.mp4`, dark, play mode)
come from `tools/ci/readme_shots.mjs`.

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
| `npm run test` | vitest + Testing Library: loading (spinner after 300 ms), empty, error with retry, long content (90-character title, 4,000-word message, 30 jobs), the engine not logged in, demo fallback, card accept (options, Ctrl+Enter, spend card, error), the composer (Enter, Shift+Enter, new episode, onboarding, failed send), the teleprompter; the states table above, the step dots, the spend card's two ways (local declines, never accepts), the waiting row jumping to its card, the palette and shortcuts, crew talk (collapsed and opened), the still demo and the scripted sequence; the media of an episode (thumbnails, cut, scenes, GPU), the thumbnail pick, the GPU card's Stop, the media's empty, pending and error states, the home's sections and filters |
| `npm run check:tokens` | no raw colour values in `src/` outside `src/styles/tokens.css`; radii, shadows, durations and curves only from tokens (rules 4, 6, 9) |
| `npm run check:forms` | two text fields, the composer and the palette's search field, and no `<form>` with more than one field (rules 1.2, 3, 15) |
| `npm run check:words` | no emoji, no exclamation marks in user-facing text (tooltips too), no "OK", "Submit" or "Yes" labels (rules 8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in light and dark: the opaque stand-ins, the glass window over the brightest and darkest wallpaper sample with tiles, chips and row states on it, tags over a white picture; the focus ring 3:1 (rules 4, 18) |
| `npm run check:fonts` | no font file in the repository or `dist/` whose name or inner name contains "SF Pro", "SF Compact", "SFNS", "SF Mono" or "New York"; no `@font-face` with these names (rule 5) |
| `npm run check:materials` | `backdrop-filter` only on the allowed surfaces (the window, tags on pictures, the palette, the teleprompter dialog and its phone controls), only inside `@supports`, after an opaque background, with fallbacks for reduced transparency and more contrast (rule 18) |
| `npm run check:motion` | every animation has a reduced-motion branch; only the run shimmer and the spinner loop; only `transform`, `opacity` and grid tracks animate (rule 9) |
| `npm run check` | all seven checks |
| `npm run build` | type check, then the production build into `dist/` |

The words check reads `.ts` and `.tsx` files with the TypeScript parser, so the `!` operator in code does not count;
class names, roles and ids in JSX attributes are skipped.

## Astryx

`@astryxdesign/core` (MIT, prebuilt CSS, no build plugin) gives `Button`, `Badge`, `StatusDot`, `ProgressBar` and
`Kbd`. `main.tsx` imports its `reset.css` and `astryx.css` (both in CSS layers, so our unlayered rules win), then
`src/styles/astryx-theme.css`, which maps its tokens onto ours under `[data-astryx-theme="crewcut"]` (set on
`<html>` in `index.html`). Kept as our own, on purpose: the command palette (Astryx's would bring a second text field
and lose the tested keyboard behaviour), the composer and the chat (our cards, exchanges and the Humanizer note live in
the transcript), the thumbnail pick (Astryx's `SelectableCard` is a checkbox; picking one of A, B, C is a radio group),
Slate's avatars (Astryx's `Avatar` shows an image and cannot take the CSS colours and state animations of
`src/slate/art.ts`), the steps (they jump to their card in the chat) and the whole media layer.

## Not done here

The UI is not opened in a browser on a developer laptop; the CI job `screens` takes the screenshots. Drag and drop,
the microphone level, the QR scan and the teleprompter on a real phone are untested. The unit tests run in jsdom,
which has no layout, no CSS and no blur.

The spring curves are generated by `node scripts/springs.mjs` and pasted into `tokens.css`.
