# The web UI

The UI lives in `web/`: React 19, Vite 5, TypeScript (strict), plain CSS with tokens, and a few controls from
[Astryx](https://github.com/facebook/astryx) (MIT). It follows [DESIGN.md](../DESIGN.md) and talks to the server only
through [api.md](api.md). The container serves the built files from `web/dist/`.

The app fills the page from edge to edge: the rendered wallpaper as the page background, one sheet of glass over it,
the top bar and three columns directly on it, pictures first. There is no frame, no fake window and no fake window
buttons, in a browser tab, in an installed app window and in the desktop app alike. No Apple font is in the repository.

## Opening Crewcut: its own window

`./start.sh` (and `crewcut open`, both through the same steps: `host/open-app.sh` and `crewcut/opener.py`) waits until
the server answers, then opens the UI as an app window: `--app=http://localhost:4747` of the first installed of Google
Chrome, Microsoft Edge, Brave, Arc and Chromium (macOS: `open -na "<App>" --args --app=URL --window-size=1440,900`;
Linux: the default browser first when it is one of them; Windows through WSL or Git Bash: `msedge --app=URL`). It uses
the normal browser profile, so no first-run dialog appears. Without one of these browsers the default browser opens a
tab. `--no-open` or `CREWCUT_OPEN=none` only print the address, `CREWCUT_OPEN=browser` opens a tab.

The page is also an installable app (`public/manifest.webmanifest`: name Crewcut, `display: standalone`,
`display_override: ["window-controls-overlay", "standalone"]`, the 192 and 512 px icons of Slate, `--panel` as theme
and background colour; `theme-color` metas for light and dark, kept in step with a theme chosen in the palette).
Chrome and Edge show the install icon in the address bar on `localhost` (no service worker is needed); Safari on
macOS 14 or newer adds it with File → Add to Dock. The server sends the manifest as `application/manifest+json`.

In its own window the top bar is the window's title bar. With a window-controls overlay (an installed app that the user
switched to the compact title bar, and the desktop app) the system's window buttons sit over the top bar; the bar keeps
clear of them with `env(titlebar-area-x)`, `env(titlebar-area-width)` and `env(titlebar-area-height)`, which fall back
to the plain padding in a browser tab. Its empty parts move the window (`app-region: drag`); its buttons, links, the
search field, the palette, the menu and the teleprompter dialog are `no-drag`. The document title is "Crewcut · " and
the open view ("Crewcut · Episodes", "Crewcut · Claude improves a website 100 times").

## The places

| Part | What it shows | Code |
|---|---|---|
| Page | the wallpaper (`--wallpaper`, dark `green-dusk`, light `mint-dawn`, 1280 px below 900 px) as the page background, one sheet of glass over all of it, edge to edge | `src/App.tsx`, `src/styles/window.css` |
| Top bar (46 px) | breadcrumbs ("Episodes / 012"), the search field that opens the command palette, the view's actions ("Make a Short" and the teleprompter in an episode, "3 at work" on the home) and the right-column toggle | `src/components/TitleBar.tsx` |
| Sidebar (236 px; 64 px icon rail in an episode and below 1200 px) | the places with counts (Episodes, Shorts, Crew, Style pack, GPU and renders), the channel from the style pack, the crew dock with Slate's faces | `src/components/Sidebar.tsx` |
| Main | the Episodes home, an episode's media, a read-only page, the onboarding chat or "New episode" | `src/views/Home.tsx`, `src/views/EpisodeView.tsx`, `src/views/EpisodeMedia.tsx`, `src/views/ReadOnlyViews.tsx` |
| Right column (318 px) | Working now (each running job with its newest picture and progress) and Spend | `src/components/Crew.tsx` |
| Crew chat (372 px, in an episode) | the working tiles of this episode on top (other jobs as one line that opens the home), the money line, the transcript with cards and previews, the composer at the foot | `src/views/EpisodeView.tsx`, `src/components/ChatPane.tsx`, `src/components/CardView.tsx`, `src/components/Composer.tsx` |

**The Episodes home** is the start view. "Needs you" shows each episode with an open card, or with its interview
waiting for answers, as a large media card (the cover, a tag with the question from `needs.title` or "Interview:
waiting for your answers", the length from `seconds`, the variants from `needs.images` small
inside the picture, the title and the step bar below). "In work and published" is one complete row of 16:9 covers (the
grid's column count is read from its CSS; "Show all" opens the rest) with the length
or, while someone works on it, a Slate line ("Editor is cutting, 6 of 10"). "Shorts" is one row of 9:16 frames with
the title drawn over them, one row as well. Filter pills sit on top; the sidebar's "Shorts" is the Shorts pill (`#/episodes/shorts`).
"Import footage" appears only when an episode takes footage (the newest long video at the record or edit step); it
opens that episode and uploads the files into its chat.

**An episode** loads `GET /api/episodes/{id}/media` and shows, each only when it is there: the thumbnail variants (a
radio group; the recommended one chosen with a mint ring; "Use A" accepts the open thumbnail card with that choice; the
chosen one in a phone-size feed), the cut (frames, waveform from `peaks`, the Critic's markers, the style facts, the
time axis), the 3D scenes (one large, four small, render tiles on the one in work) and the rented GPU (time left, so
far, cap, progress, the price per hour with the cap per GPU-hour, the delete note, Stop). **Stop** asks once more
inside the card (no dialog), then `POST /api/episodes/{id}/gpu/{rental}/stop` deletes the machines of that render; the
frames that came home stay, and the card says what it cost. **Make a Short** calls `POST /api/episodes/{id}/shorts`: a
Short in clip mode from this episode, and the Scout's job appears in Working now. The media load again every 4 s while a job of the episode runs, and at once when its jobs
or cards change. A server without the endpoint (404) counts as "no media yet"; an error shows one line with "Try
again".

**Motion graphics** of an episode come from `GET /api/episodes/{id}/motion` (`src/views/EpisodeMotion.tsx`), loaded
like the media and again when one of its cards changes (a struck row points the plan card at a new version). Each
motion insert is a tile under the film strip of the cut, in the order it plays: its loop (or its poster or style
frame), its state on a tag (planned, style frame, building, in review, done), where it sits ("0:41", "on “offline”")
and what it is; a custom piece shows the first line of its brief. A quiet band on the waveform marks where each insert
with a start in seconds plays. The **Motion** panel below the cut shows the plan's three columns compact and
read-only (a strike happens on the card; "Show the card" scrolls the chat to the open one), density and budget with
the cap in one line, and after the build the motion report's three lines (better, behind, next), its verdict and the
retention hint. Without a cut the tiles sit in the Motion panel. A 404 counts as "no motion yet"; an error shows one
line with "Try again" and leaves the other media alone.

Cmd+B folds the sidebar and Cmd+Alt+B the right column (a spring on the grid columns). Below 900 px the parts stack
in one scrolling column and the sidebar opens as a menu from the top bar.

Style pack, Crew, GPU and renders and a job log open in the main column as read-only pages. They have no edit
controls; each ends with "To change something, say it in the chat."

The style pack has a **Motion** shelf (`src/views/MotionShelf.tsx`, `GET /api/motion/library` and
`GET /api/motion/ratchet`): one line about the bar and the lessons, then a grid of the pack's templates and the app's
(these with a small "Crewcut" mark; an app template the pack overrides is left out), each a muted sample loop that
plays while pointed at or focused, its title, its format marks, its version and "made for 013". A template still
waiting for its card's yes says so on its picture. Opened (a button with `aria-expanded`), a template shows its params
with their defaults (without `comp`), the videos that use it (each opens its episode), its older versions and the
newest review notes. Pieces made for one video and not kept are listed below the grid. A server without the motion
routes (404) shows no shelf.

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
when there is no episode yet.
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

**Connect Claude** (`src/components/ConnectEngine.tsx`) is the third and last text field. It shows on the first start
and at the top of the onboarding page while Claude is not connected: one primary button, "Connect Claude". It opens a
tab in the click, asks the server for Claude's sign-in link (`POST /api/engine/claude/connect`, which runs
`claude setup-token` in the container with `BROWSER=true`) and sends the tab there. The card then shows one field,
"Code from Claude's page", and Connect (`POST /api/engine/claude/code`); a wrong code says so and keeps the field. Done,
it says "Claude is connected as <email>. Paste your links below." "Connect Codex (beta) instead" calls
`POST /api/engine/codex/connect` and shows the device link and code until `GET /api/engine/login` says Codex is
connected. In the desktop app (`window.crewcutDesktop`, from its preload) both buttons call the app instead, which
keeps the Claude token in the system keychain; the page never sees it.

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

The four motion cards (`src/components/MotionCards.tsx`) put the media first:

- **motion-plan** ("Build this motion plan"): the three columns, stacked in the narrow chat and side by side when the
  card is wide: (a) what we have that fits, a loop of each shelf piece with its time, name and purpose; (b) what we
  build new for this video, the brief's line with effort, plates, cost and its cap; (c) what makes this video clearly
  better than the last one, each upgrade with its reason (lesson, reference, behind the bar, retention). Upgrades not
  chosen show as "For a later video" and are not tappable. Density and budget stand in one line with the cap per
  video ("GPU about $0.30, cap $2 for this video", "cap $0.50 for this Short"). Each row is a toggle button ("Not
  this one: 0:06 Number roll, believe the price", `aria-pressed` when struck): a tap calls
  `POST /api/cards/{id}/strike` and the same card shows the next plan version in place; a second tap brings the row
  back. A refusal (409, for example the only chosen upgrade) shows the server's sentence without "Try again".
- **style-frame** ("Build from this frame"): per format, our frame next to the reference, the bar's frame or the
  sentence for no reference, with the hue check under the pair. A note back is a sentence in the chat.
- **template** ("Keep it in the library"): the sample loops per format, the params with their defaults, where it was
  made, its version and the one it replaces, the format marks.
- **baseline** ("Raise the bar to 003", or "Make 003 the bar" when there is none): the bar now and this video side
  by side, each with a frame and its named strengths, what is better and against which strength, and the measured
  values ("5 to 6").

Sample loops are muted, have no controls, play only while at least half of them is in view (on the shelf while
pointed at), and show only their poster with reduced motion.

A spend card shows both ways as two choice surfaces. The first choice is honest: the rented GPU only when it saves at
least an hour, else this machine (also when a time is not known). The button follows the choice: "Rent a GPU for $0.60"
accepts the card. "Render on this machine" never calls accept, because accepting a spend card means "rent"; it declines
the card (`POST /api/cards/{id}/decline`) with the reason "Local is fine. Render on this machine." and the card folds to
"GPU rental not taken · this machine renders".

### Keyboard and the command palette

| Shortcut | Does |
|---|---|
| Cmd/Ctrl+K | Command palette (also the search field in the top bar): episodes (Cmd+1 to 9), "Show all episodes", "Show the Shorts", "Show the style pack", "Show the crew", "Show GPU and renders", "New episode", "Open teleprompter", "Switch to the dark/light theme", the sidebar and the right column |
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
and new messages again, and reopens. While it retries, a slim line under the top bar says "Lost the connection to the container. Retrying…". An `activity` event for a job the screen
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
| activity | `ended` | the time a finished render job shows under "GPU and renders" |
| activity | `engine`, `model`, `effort`, `engine_version` | one quiet line in the job log view ("Runs on Claude Code 2.1.325 · model sonnet · effort medium"), never on the row |
| message | `exchange` (`{topic, result, messages: [{id, sender, recipient, kind, about, text, route, status}]}`) | a finished exchange between two crew members ([crew-talk.md](crew-talk.md)): one collapsed quiet line, "Critic and Editor · fix about review/cut-check-v001.json · 2 messages"; opened, who wrote to whom, the file in mono, the text |

A message that only repeats the title of the card it carries is not shown; the card is.

### States

| Place | State | What shows |
|---|---|---|
| Home | no episodes | Slate dozing, "No episodes yet. Start one with New episode." and the button |
| Home | a filter without episodes | "Nothing here right now." |
| Main | first start (not onboarded, empty onboarding chat) | the top bar without search and actions; Slate waving, "Paste your links." and "Website, YouTube channel, socials. The crew reads the rest."; the composer floats under the sentence (560 px) and glides to the bottom after the first message |
| Episode | no media yet (or a server without the media route) | Slate dozing, "No pictures yet. Thumbnails, the cut and renders show here as the crew makes them." |
| Episode | the strip is being made (`cut.pending`) | "The strip and the waveform are on their way." and "Frames come as soon as the cut is read." |
| Episode | the media fail | "Couldn't load the pictures of this episode. …" and "Try again" |
| Crew chat | no messages | "Say an idea below, or ask the Scout for three." |
| Page | no Crewcut answers at the address (network error, a 404 page, an answer that is not JSON, a proxy's 502 to 504) | the top bar without search and actions, Slate working, "Crewcut is starting…" and "Waiting for the engine at this address. The first start takes a few minutes."; it asks again every 2 s |
| Page | still no answer after 90 s | Slate waiting, "Can't reach the Crewcut engine", "Check that Docker is running and Crewcut is started (the Crewcut app, or ./start.sh), then try again." and "Try again" (it asks again for 90 s) |
| Page | the live connection is lost | the slim line under the top bar |
| Card | a preview loads | a placeholder of the same size on `--sunken`, with the run shimmer after 300 ms |
| Card | a preview fails | "Couldn't load the preview. The file is at episodes/003-…/review/frame-231.png." and "Try again" |
| Working now | nobody works | "Nobody is working. Nothing is running, nothing costs money." |
| Working now | the engine is not connected | one line with a `--warn` dot: "Claude is not connected. Nothing can run yet." and "Connect Claude" (opens the onboarding; in the desktop app its settings) |
| Main | first start, Claude not connected | Slate waving, "Connect Claude first.", "Crewcut runs on your own Claude plan. Sign in once, then paste your links." and the Connect Claude card (below) |
| Spend | nothing spent | the three figures in `--ink-3` |

Only what arrives after a chat or Working now first showed animates in; what is already there stays still.

File previews use `/api/files/{episode}/{path}`. A path that already starts with `/api/` (the profile preview) is
used as it is.

## No made-up content

The app ships no sample or demo data and has no mode that shows any: when no Crewcut answers, it says so (the two
"Page" rows in the states table). The production build is checked for it in CI (`dist/` holds no sample fixture or
picture).

## Sample data for the pictures (CI only)

The README, the docs and the landing page need pictures with content. They come from sample data that never reaches
the app or the image: `tests/web-sample/` (excluded in `.dockerignore`). It holds an in-memory stand-in for the
server (`backend.ts`, the calls of api.md, the media and motion routes too) with fixtures shaped like api.md. Everything
in it is English. The pictures come from `tests/web-sample/media.json` (web-sized stills under
`tests/web-sample/public/media/`, made by `tools/sample/build_media.py` from the author's own videos): episode 012
"Claude improves a website 100 times" with two thumbnail variants, ten strip frames, the commercial's five 3D scenes and
a running GPU rental; the commercial, an episode in work, four published ones and nine Shorts. Episode 012 shows
variants A and B only (C spells its title differently). Chats, jobs and money are made up; a sentence gets a reply that
says these are sample data.

Motion graphics in the sample data (`tests/web-sample/motion.ts`) keep the workflow's order: the commercial (015) has a
cut from its five 3D shots, its motion plan approved (version 2, one row struck before the yes; read-only in the Motion
panel, one folded line in the chat), the style frame of its one new piece open next to the bar's frame, and three tiles
(done, style frame, in review); 013 shows the finished loop (pieces done, the report's three lines, the decided motion
cards); the style pack's shelf holds two templates of the pack, the app's five and one piece made for one video. A
strike on the sample's answered plan is refused as the server refuses it. The pictures are small posters drawn with
plain shapes (`tests/web-sample/public/motion/*.svg`); there are no loops.

The web tests use the stand-in with `setBackend` (`src/test/look.test.tsx`, `src/test/motion.test.tsx`). CI serves it
with `tools/ci/sample_server.mjs`: the built `web/dist`, `/api` answered by the stand-in (bundled for Node with
esbuild), `/api/events` as a real event stream, the files and pictures from `tests/web-sample/public`, and the
teleprompter at `/p/sample-token`. The still scene is the home with two open questions, or with
`#/e/012-website-100-times` the episode with the thumbnail pick open, scene 5 rendering at 62 % on a rented RTX 4090,
three of the crew working and "Month $4.10 of $20". For the README animation the server starts from the beginning of
the sequence (`POST /__sample/reset?play=1`) and `tools/ci/readme_shots.mjs` presses the real buttons:

| From load | What happens |
|---|---|
| 0.6 s | `POST /__sample/play/card-in`: the GPU card springs into the crew chat with "On this machine" chosen (50 min against 12 min, so this machine is the honest first choice); the Editor's waiting row appears |
| 2.0 s | the script clicks the rented GPU; the button now says "Rent a GPU for $0.60" |
| 3.3 s | the button is pressed (`data-pressed`), released and clicked: the real yes goes out and the card folds to one line |
| 3.6 s | `POST /__sample/play/after-yes`: "3D scene 5 of 5 on a rented GPU" slides into the working tiles; the GPU card and the render tiles of scene 5 appear among the media |

CI (`.github/workflows/screens.yml`) screenshots the home and episode 012 (`#/e/012-website-100-times`) at 1440x900 in
light and dark, at 1100 and at 390x844, plus `#/profile`, `#/crew` and the teleprompter, and the page without a server
("Crewcut is starting…", `app-starting*.png`). The README images (the app itself at 1440 x 1000, twice the density,
2880 x 2000: `crewcut-{dark,light}.png` for episode 012, `crewcut-episodes-{dark,light}.png` for the home) and the
animation (`crewcut-demo.webp` and `.mp4`, dark) come from `tools/ci/readme_shots.mjs`.

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
| `npm run test` | vitest + Testing Library: loading (spinner after 300 ms), empty, error with retry, long content (90-character title, 4,000-word message, 30 jobs), the engine not logged in, "Crewcut is starting…" and "Can't reach the Crewcut engine" (never made-up content), card accept (options, Ctrl+Enter, spend card, error), the composer (Enter, Shift+Enter, new episode, onboarding, failed send), the teleprompter; the states table above, the step dots, the spend card's two ways (local declines, never accepts), the waiting row jumping to its card, the palette and shortcuts, crew talk (collapsed and opened), the sample data's still scene and the steps of the README animation; the media of an episode (thumbnails, cut, scenes, GPU), the thumbnail pick, the GPU card's Stop, the media's empty, pending and error states, the home's sections and filters; the four motion cards (columns, the strike call and its refusal, the cap per video and per Short, posters only with reduced motion, accessible names), the motion tiles on the strip and the Motion panel (order, states, report lines, 404, error), the Motion shelf (hover to play, opened details, one-off pieces, no shelf) and motion in the sample data |
| `npm run check:tokens` | no raw colour values in `src/` outside `src/styles/tokens.css`; radii, shadows, durations and curves only from tokens (rules 4, 6, 9) |
| `npm run check:forms` | three text fields, the composer, the palette's search field and the code field of Connect Claude, and no `<form>` with more than one field (rules 1.2, 3, 15) |
| `npm run check:words` | no emoji, no exclamation marks in user-facing text (tooltips too), no "OK", "Submit" or "Yes" labels (rules 8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in light and dark: the opaque stand-ins, the glass window over the brightest and darkest wallpaper sample with tiles, chips and row states on it, tags over a white picture; the focus ring 3:1 (rules 4, 18) |
| `npm run check:fonts` | no font file in the repository or `dist/` whose name or inner name contains "SF Pro", "SF Compact", "SFNS", "SF Mono" or "New York"; no `@font-face` with these names (rule 5) |
| `npm run check:materials` | `backdrop-filter` only on the allowed surfaces (the window, tags on pictures, the palette, the teleprompter dialog and its phone controls), only inside `@supports`, after an opaque background, with fallbacks for reduced transparency and more contrast (rule 18) |
| `npm run check:motion` | every animation has a reduced-motion branch; only the run shimmer and the spinner loop; only `transform`, `opacity` and grid tracks animate (rule 9) |
| `npm run check` | all seven checks |
| `npm run build` | type check, then the production build into `dist/` |

The Taste design gate is not one of these checks: CI runs it only for big changes and only as information (CONTRIBUTING.md, "Design checks in CI").

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
