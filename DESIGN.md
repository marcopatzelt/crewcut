# Crewcut design rules

These rules cover the web app in `web/` and every page the container serves (the teleprompter too). Every UI change
follows them, whoever writes it: a maintainer, a contributor or a coding agent. A reviewer can point at a rule number and
ask for a change. If a rule stops you from doing the right thing, change the rule in the same pull request and say why.

Several rules are enforced by checks (rule 16); the rest rely on review.
The [Taste skill](https://github.com/Leonxlnx/taste-skill) (MIT) is the design check we run for big changes and
before a release (rule 17); we link it, we do not copy it. It is information only: it never blocks a deploy or a merge,
and CI runs it only for big changes (see "Design checks in CI" in CONTRIBUTING.md).

## 1. Principles

1.1 **The screen shows work. It does not take input.** Agents do the work; the user watches, says one sentence, or gives
one yes. Crewcut exists so that nobody has to sit and type.

1.2 **No forms.** No settings dialog, no wizard, no field the agent could fill itself. What an agent can find out, it
finds out. What only the user knows, the user says in one sentence (typed or spoken).

1.3 **Calm by default.** Nothing blinks, counts or moves unless the user needs to act or work is really running.

1.4 **One thing per card.** A card shows one decision: a preview, one sentence of reason, one button to accept.
Declining or changing is a sentence in the chat.

1.5 **Nothing runs out of sight.** Every running job has a row in the right column. The two questions "how long still?"
and "what is running?" are always answered on screen.

1.6 **Plain words.** Say what the user knows: "rented GPU", not "instance"; "cut", not "timeline render".

1.7 **Every state is designed.** Empty, loading, error, long text, narrow window, light and dark.

1.8 **The app has no brand of its own in the video.** The user's style shows only in their videos and previews. The app
itself stays neutral.

## 2. The window and its places

The app is one glass window on a desk (rule 18): the rendered wallpaper behind it (dark `green-dusk`, light
`mint-dawn`, the 1280 px versions on small screens), the window inset 22 px at the top and 26 px elsewhere, radius
20 px. Inside it a 46 px title bar and three places side by side. New things go into one of them; there is no fourth.

| Place | Width at 1440 px | Holds |
|---|---|---|
| **Sidebar** (left) | 236 px, 64 px as an icon rail in an episode | the brand, the places with their counts (Episodes, Shorts, Crew, Style pack, GPU and renders), the channel, and the crew dock: Slate's faces overlapping, a mint ring on whoever works, one line ("Editor and Designer are working. Six rest until you ask.") |
| **Main** (center) | the rest | the Episodes home, an episode's media, or a read-only page |
| **Right column** | 318 px; the crew chat 372 px | on the home and the read-only pages: Working now and Spend. In an episode: the crew chat |

- **Title bar:** three decorative dots (`aria-hidden`, no function), breadcrumbs ("Episodes / 012"), a centred search
  field that opens the command palette (rule 15), and the actions of the view on the right ("Make a Short" and the
  teleprompter in an episode, "3 at work" on the home, the right-column toggle).
- **The Episodes home is the start view** (`#/episodes`). Title "Episodes" and one line ("Two need your yes.
  Everything else is moving."), "Import footage" (only when an episode takes footage: the newest one at the record or
  edit step) and "New episode". Filter pills (All, Needs you, In work, Long videos, Shorts, Published; a pill shows its
  count, empty ones hide; the selected one is filled with `--chip-on`, not the accent). Then three sections:
  **Needs you** as large media cards (rule 19), **In work and published** as one complete row of 16:9 thumbnails
  (four at 1440 px, newest first), **Shorts** as one row of 9:16 frames (seven at 1440 px); "Show all" in the
  section head opens the filter with everything. The sidebar's "Shorts" is the Shorts pill.
- **An episode** (`#/e/<id>`) shows its media first: the title with its facts as chips, the steps as segments, the
  crew on it; then the thumbnail variants, the cut, the 3D scenes and the rented GPU (rule 19). The crew chat on the
  right: "Working now" tiles of this episode's running jobs on top (the others as one line, "One more job on other
  episodes", that opens the home), the money line, the transcript with its cards, the composer at the foot. What
  scrolls up under the tiles fades out; an open card that is the newest item keeps its top in view.
- **Working now** (the right column of the home) shows each running job with its newest picture (`Activity.preview`)
  and its progress; a waiting row jumps to its open card, every other row opens the job's log. A finished job keeps
  its log; render jobs stay listed under "GPU and renders".
- Style pack, Crew, GPU and renders and a job log open in the main column as read-only pages. They have no edit
  controls: a change is a sentence to the agent. The composer floats at their foot.
- Headlines are large and bold (rule 5), never italic; emphasis comes from weight.
- Below 1200 px the sidebar is the icon rail everywhere. Below 900 px the window fills the screen and the parts stack
  in one scrolling column (main, then the right column); the sidebar opens as a menu from the title bar.

## 3. Input

- The composer is the only text field in the app. Its placeholder says "Tell the crew what you want". It has a microphone button
  (browser speech input where available) and a send button.
- The one exception is the search field of the command palette (rule 15). It picks from a list and takes no values.
- Onboarding is the composer too: "Paste your links." Links go in, the Brand identity works in Working now, a profile
  card comes back.
- Cards have exactly one primary button. Its label says what happens ("Use this title", "Rent a GPU", "Publish on
  Friday 17:00"). There is no "Decline" button; under the button one quiet line says "Or say what to change".
- Two exceptions where the user pastes a value once: the engine login (`.env`, outside the UI) and a provider key (only
  when the user wants to rent). The agent opens the right page and says where the key is.

## 4. Colour

All colours are tokens in `web/src/styles/tokens.css`, defined for light and dark. Components use the tokens, never raw
values.

| Job | Tokens |
|---|---|
| Desk | `--wallpaper`, `--wallpaper-small` (the rendered landscape), `--window` (its colour before it loads), `--desk-hi`, `--desk-lo` (the brightest and darkest wallpaper colour after the window's blur, for the contrast check), `--desk-tint` |
| Glass | `--material-window` (the window), `--edge-window`, `--panel` (its opaque stand-in), `--tile` (panels, cards and rows on the glass), `--chip` (pills, chips, the search field), `--chip-on`, `--chip-on-ink` (a selected pill, the user's bubble) |
| Surfaces | `--bg`, `--card` (opaque: chat cards, menus, the palette), `--sunken` |
| Row states | `--hover`, `--selected` (both neutral, translucent) |
| Text | `--ink`, `--ink-2` (supporting), `--ink-3` (meta, timestamps, hints) |
| Lines | `--line` (dividers), `--line-strong` (field edges) |
| Accent | `--accent` (deep green words: links, the Designer's pick), `--accent-ink`; `--accent-fill` (mint: the primary button, progress, the ring of a chosen picture), `--accent-fill-ink`; `--focus`, `--selection` |
| Status | `--ok`, `--warn`, `--danger`, `--marker` (the amber of a Critic note and of "needs your yes") |
| On pictures | `--material-tag`, `--tag-solid`, `--tag-ink`, `--tag-edge` (tags), `--media-ground`, `--media-fade`, `--on-media`, `--on-media-shade`, `--on-media-ring`, `--render-pending` |
| Fixed cards | the GPU card (`--gpu-*`), the phone preview (`--phone*`), the title bar dots (`--dot-close`, `--dot-minimize`, `--dot-zoom`) |
| Material (rule 18) | `--material-window`, `--material-tag`, `--material-float`, `--edge-light` |
| Depth | `--shadow-1`, `--shadow-2`, `--shadow-3`, `--shadow-press`, `--shadow-window` (the window on the desk), `--shadow-media` (pictures) |

- **Depth instead of lines.** Layers come from material and shadow. A hairline only separates two things on the same
  layer.
- **One accent: Crewcut green.** Mint (`--accent-fill`) marks the primary button, progress and the chosen picture
  (a thumbnail variant); the deep green (`--accent`) marks links and words. Nothing else. A selected row or place is
  neutral (`--chip`, `--selected`), as in Finder and Mail. The highlighted item of a menu or the palette is the one
  place where a selected row is coloured.
- **Hierarchy comes from ink and size,** not from extra colours.
- **Status colours mean status.** `--danger` for errors and for money above the cap, never as decoration.
- **Identities have no colours.** They are told apart by their two-letter mark and name (rule 13).
- **Layers in dark:** the desk darkest, the glass of the window over it, tiles lighter on the glass, `--card` (menus,
  chat cards) lighter still. Raised means lighter, not darker with more shadow.
- Text clears 4.5:1 on every surface it sits on, in both themes. On the glass the check uses the opaque stand-in and
  the translucent window over both wallpaper samples (`--desk-hi`, `--desk-lo`), with tiles, chips and row states on
  top. Words on pictures sit on a tag or a fade that clears 4.5:1 even over a white picture. A token that fails gets
  more contrast; the rule does not get softer.

## 5. Type

**Inter** (SIL Open Font License, bundled through `@fontsource`) everywhere. On Apple devices the app uses the system
font through `system-ui` (the class `is-apple` on `<html>`), so the browser takes the font that is already installed.
No Apple font file goes into the repo or the image (`check:fonts`). Screenshots are made in CI on Linux, with Inter.
Numbers that change in place use `font-variant-numeric: tabular-nums`.

| Token | Use | Size / line height | Weight | Tracking | Ink |
|---|---|---|---|---|---|
| display | The home's "Episodes" | 40 / 44 | 700 | -0.035em | `--ink` |
| display | A page title; an episode's title | 34 / 40; 27 / 32 | 700 | -0.03em | `--ink` |
| display | Section heads ("Needs you"), panel heads ("Thumbnail"), a media card's title | 15 to 17 / 20 to 22 | 700 | -0.01em | `--ink` |
| `--t-title` | The title of the onboarding chat | 20 / 26 | 600 | -0.015em | `--ink` |
| `--t-figure` | The one big number of a card ("About 12 min") | 22 / 26 | 600 | -0.02em | `--ink` |
| `--t-head` | Card title, section title, the title in the toolbar | 15 / 20 | 600 | -0.01em | `--ink` |
| `--t-chat` | Chat text | 15 / 23 | 400 | -0.005em | `--ink` |
| `--t-body` | Rows, buttons, body | 13 / 18 | 400 or 500 | 0 | `--ink` or `--ink-2` |
| `--t-meta` | Meta, hints | 12 / 16 | 400 | 0 | `--ink-3` |
| `--t-label` | Group labels ("Episodes", "Working now") | 11 / 14 | 600 | +0.02em | `--ink-3` |

- Four weights: 400, 500, 600, and 700 only for the display titles above (`--font-display`). Nothing heavier.
- Sentence case everywhere. No ALL CAPS labels, no Title Case. Group labels too.
- No italics.
- Titles and rows stay on one line and truncate; the full text is in `title` and in the opened view.
- The two-letter marks use the rounded system font on Apple devices (`--font-rounded`), Inter elsewhere.

## 6. Shape

| Token | Element | Radius |
|---|---|---|
| `--r-xs` | Small marks, chips, shortcut keycaps, tooltips | 6 px |
| `--r-row` | Rows, fields, segments, identity marks | 8 px |
| `--r-ctl` | Buttons with text that are not a capsule, previews, choice surfaces, menus | 10 px |
| `--r-group` | Grouped lists (the running jobs) | 12 px |
| `--r-card` | Cards | 14 px |
| `--r-panel` | Panels and media cards on the glass, the palette, dialogs | 18 px |
| `--r-window` | The window on the desk | 20 px |
| `--r-composer` | Composer | 22 px |
| `--r-full` | Primary button, round icon buttons, dots | full |

A nested shape is smaller than its container: inner radius = outer radius minus the distance to the edge. No in-between
values. Where the browser supports `corner-shape: squircle`, panels and cards use it; elsewhere corners stay round.

## 7. Space and layout

- 4 px grid. Steps: 4, 8, 12, 16, 20, 24, 32, 40. Media keep their own aspect: 16:9 thumbnails and frames, 9:16
  Shorts, 16:7.4 for the picture of a media card.
- The window sits on the desk 22 px from the top and 26 px from the other edges; below 900 px 12 px, below 760 px it
  fills the screen. Cmd+B folds the sidebar, Cmd+Alt+B the right column (a spring on the grid columns).
- Each scroll area scrolls on its own: the main column, the right column, the transcript of the crew chat.

| Measure | Value |
|---|---|
| Title bar | 46 px |
| Sidebar / icon rail | 236 px / 64 px |
| Right column / crew chat | 318 px / 372 px at 1440 px (290 / 340 below 1280 px) |
| Home: padding of the main column | 6 px top, 30 px right, 22 px left |
| Home grid | 4 columns at 1440 px, 3 below a 760 px column, 2 below 560 px; gap 16 px |
| Media panel padding | 16 px; panels 16 px apart |
| Reading width of the onboarding chat and of text pages | at most 760 px, centred |
| Between messages / between a message and its card | 20 px / 12 px |
| Composer | at the foot of the crew chat; on the main column it floats 18 px above the bottom edge |

- One inset per surface: everything in a column starts and ends at the same edge.
- Group with space before lines. A divider only between groups that space cannot separate.
- No cards inside cards.
- Design at 1440 x 900, check at 1100, 760 and 390. The README images are the app itself at 1440 x 1000, twice the
  density (2880 x 2000): episode 012 and the home, light and dark (`tools/ci/readme_shots.mjs`). At that size each
  view fits whole: on the home one complete row of thumbnails and of Shorts ("Show all" opens the rest), in an episode
  the panels down to the GPU card.

## 8. Icons

- `lucide-react` only, 16 px in rows and buttons, 14 px next to 12 px text, stroke width 1.75. No emoji, no icon
  fonts, no SF Symbols.
- Icons are bare: no tinted squares or circles. Slate's avatars (rule 13) are the only shapes on a tile.
- Decorative icons get `aria-hidden="true"`; icon-only buttons get an `aria-label`.

## 9. Motion

- Motion explains a change. Everything that appears or moves uses a spring (`--spring-snappy`, 280 ms, or
  `--spring-soft`, 420 ms; both from `web/scripts/springs.mjs`, at most 2.5 % overshoot). Colour and opacity changes are
  short and linear (`--t-fast`, 120 ms).
- 300 ms is the ceiling for timing curves. Springs may run to 420 ms, because they reach the target early and only
  settle after that.

| What | How | Time |
|---|---|---|
| Hover, colour, opacity | linear | 120 ms |
| Button pressed | scale 0.97 and `--shadow-press` | 120 ms |
| New message | 8 px up and fade in, `--spring-snappy` | 280 ms |
| Card appears | scale 0.98 to 1 and fade in, `--spring-snappy` | 280 ms |
| Card decided | folds to one line, `--spring-snappy` | 280 ms |
| New row in Working now | height 0 to full, `--spring-snappy` | 280 ms |
| Sidebar or right column in and out | grid columns, `--spring-soft` | 420 ms |
| Current step dot moves on | position, `--spring-soft` | 420 ms |
| Palette, dialog | scale 0.96 to 1 from where it was opened, `--spring-snappy`; closing only fades | 280 / 120 ms |
| Switching the episode | the content cross-fades, nothing moves | 160 ms |
| Slate works (Working now) | the bar ticks open and shut four times, again when the crew member reports a new step | 4 × 900 ms |
| Slate needs you | the "?" sign pops up once, `--spring-snappy` | 420 ms |
| Slate is done | the bar snaps shut once and the check pops up | 280 / 420 ms |
| Slate waits its turn | the Zzz drift in once | 2.4 s |
| The welcome | Slate waves three times | 3 × 700 ms |

- Animate only `transform` and `opacity`; heights go through `grid-template-rows` (0fr to 1fr), panel widths through
  `grid-template-columns`. Never width, height or position directly.
- The only loop is the run shimmer: on the progress line of a running job, the active segment of a running episode and a
  loading preview, only while that work runs. The loading spinner (rule 11, after 300 ms) is the one other repeating
  animation. Slate never loops: each state plays once and holds its end pose, so nothing moves on its own for more
  than about four seconds.
- Content that is already there when a chat opens does not animate; only what arrives later does.
- `prefers-reduced-motion` turns all of it off, except cross-fades of 120 ms.
- Nothing moves to draw attention to itself (rule 1.3).

## 10. Words

- Short sentences, sentence case, no exclamation marks, no marketing words inside the app.
- Buttons say what they do. Never "OK", "Submit" or "Yes".
- Errors say what happened and what to do next: "Couldn't reach Vast.ai. Check the key in .env and try again."
- Empty states are one line and one action: "No episodes yet. Say an idea below." Slate stands above the line (asleep
  where nothing runs).
- Times and money are exact and honest: "about 12 min", "$0.31", "API equivalent $0.41 (on your subscription)".
- Never promise unbuilt features in the app. Planned work lives in the README roadmap.
- An agent may name the method it applies, in a short line under its message: "Niche check after Vexian's growth
  stages". It never claims the creator endorses Crewcut.

## 11. States

Before a UI change is done it handles: default, hover, focus-visible, pressed, disabled; loading (keep the layout, spinner
only after 300 ms); empty; error (inline, with retry); long content (a 90-character title, a 4,000-word script, a 30-job
crew); narrow window; light and dark; the engine not logged in.

## 12. Cards

- Card anatomy, top to bottom: who asks (avatar and name) and the step; title (15/600); one sentence of reason; the preview
  (options list, video, image, diff, numbers); one primary button; the quiet line "Or say what to change".
- A card about a file shows what the user approves: the exact file, with its checksum stored. Approving means this
  version; any change after that is a new version and a new card.
- A money card shows both ways side by side: "About 3 h on this machine" and "About 12 min for about $0.60 on a rented
  GPU". The referral note sits under the button in `--ink-3`: "Referral link: the author of Crewcut earns 3% of your Vast
  spend as credit. It costs you nothing extra."
- Decided cards collapse to one line in the chat: "Title approved · I ran five local AI models".
- **Media cards** on the home ("Needs you") are cards too, but picture first: the episode's cover large, a tag with
  what is asked ("Pick a thumbnail") and the length on top of it, the variants or scenes small inside the picture,
  and the title, the episode and step and the step bar in the line under it. The whole card opens the episode.

## 13. Identities

- Each crew member has a name, a one-line role, a two-letter mark for logs and the terminal (`SR`, `SC`, `WR`, `ED`,
  `CR`, `DE`, `PU`, `BR`) and an avatar: **Slate**, the Crewcut mascot (a clapperboard with a face; the striped bar is
  the "flat-top crew cut"), holding the prop of its role on a round `--slate-tile`: headset (Showrunner), magnifier
  (Scout), pencil (Writer), scissors (Editor), clipboard with a red check (Critic), brush (Designer), paper plane
  (Publisher), colour swatches (Brand). `avatar:` in `team/<id>.md` names the prop.
- Slate shows the state, never decoration: asleep with a small Zzz (waiting its turn), the bar ticking (working), a
  small "?" sign (needs you), the bar shut with a check (done). The welcome of the first start is Slate waving. One
  geometry for the app and the brand files: `web/src/slate/art.ts`; colours only from the `--slate-*` tokens. No speech
  bubbles.
- In the chat a message from an identity starts with its avatar and name. User messages have no avatar.
- Crew members may message each other directly in three narrow cases ([crew-talk.md](docs/crew-talk.md)). A finished
  exchange is one quiet, collapsed line in the chat ("Critic and Editor · fix about review/cut-check-v001.json ·
  2 messages"); opened, it lists who wrote to whom, the file and the text. No bubbles between crew members.
- In Working now one row per running job: avatar with its state, name, "what it is doing", step, elapsed time,
  cost, and on the home its newest picture.
  Waiting jobs say what they wait for ("Waiting for your yes on the preview").

## 14. Money

- Three figures: today, this episode, this month against the cap ("Month $3.78 of $20"). On the home they are the
  Spend card of the right column, with the cap as a bar and one line about what counts; in an episode they are one
  quiet line under the working tiles of the crew chat. A rented GPU has its own card among the media: name, time
  left, so far, cap, progress, "Deleted when done, frames come home", and Stop (a sentence to the crew).
- Real money only (rented GPUs, paid APIs). Subscription runs show their API equivalent in the job log, not in the line.
- Above 80 % of the cap the month figure uses `--warn`; at the cap `--danger`, and renting stops.

## 15. Accessibility

- Keyboard first: Tab order follows the window (title bar, sidebar, main, right column); Enter sends; Ctrl/Cmd+Enter
  accepts the open card in view.
- Every action can be reached without a mouse. Cmd+K (Ctrl+K outside the Mac) opens the command palette: episodes, views
  and actions, filtered as you type. Its search field only picks from the list; it takes no values (rule 3).

| Shortcut | Does |
|---|---|
| Cmd+K | Command palette |
| Cmd+N | New episode (focus in the composer) |
| Cmd+1 to Cmd+9 | Episode 1 to 9 |
| Cmd+B | Sidebar in and out |
| Cmd+Alt+B | Right column (Working now, or the crew chat) in and out |
| Cmd+Enter | Accept the open card in view |
| Esc | Close the palette, menu or dialog |
| / | Focus in the composer |
| Arrow up and down | Move between the places of the sidebar |

- Shortcuts show in tooltips and in the palette as small keycaps: `⌘` on the Mac, "Ctrl" elsewhere. Some browsers keep
  Cmd/Ctrl+N and Cmd/Ctrl+1 to 9 for themselves; the palette offers the same actions.
- Visible focus ring everywhere: `box-shadow: 0 0 0 3px var(--focus)` with the radius of the element, on
  `:focus-visible` only. Never `outline: none` without this ring. The composer shows the ring around its whole capsule. The search field of the palette is
  the one field without a ring: while the palette is open, it always has the focus.
- The chat is an `aria-live="polite"` region; cards use `role="group"` with a label. The steps stay a list of ten
  items with `aria-current="step"`. Thumbnail variants are a radio group; pictures that carry meaning have alt text
  ("Frame at 1:12"), decorative ones `alt=""`; the Critic's notes on the strip are also a list for screen readers.
- `prefers-reduced-motion` and `prefers-reduced-transparency` are respected (rules 9 and 18).
- Targets are at least 32 px, 40 px on touch. A 28 px icon button keeps a 32 px hit area.

## 16. What the checks enforce

| Check | Rule |
|---|---|
| `npm run check:tokens` | no raw colour values outside `tokens.css`; radii, shadows and durations only from tokens (4, 6, 9) |
| `npm run check:forms` | two text fields: the composer and the search field of the palette; no `<form>` with more than one field (1.2, 3, 15) |
| `npm run check:words` | no emoji, no exclamation marks, no "Submit"/"OK" buttons in `src/` (8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in both themes: the opaque stand-ins, the glass over both wallpaper samples with tiles and chips on it, tags over a white picture (4, 18) |
| `npm run check:fonts` | no font file in the repo or in `dist/` whose name or inner name contains "SF Pro", "SF Compact", "SFNS", "SF Mono" or "New York"; no `@font-face` with these names (5) |
| `npm run check:materials` | every rule with `backdrop-filter` has an opaque background before it and sits in `@supports`; only the allowed surfaces use material (the window, tags on pictures, the palette, the teleprompter dialog and its phone controls); each has a reduced-transparency and a more-contrast fallback (18) |
| `npm run check:motion` | every animation has a `prefers-reduced-motion` branch; no infinite animation except the run shimmer and the loading spinner; transitions and keyframes move only `transform`, `opacity` and grid tracks (9) |
| `npm run test` | rendering of the empty, loading, error and long-content states (11) |

## 17. Before a release

- [ ] Screenshots of the home and an episode in light and dark, at 1440, 1100 and 390 (CI job `screens` makes them).
- [ ] The Taste skill's checker run over the screenshots or the built page (by hand: run the `screens` or `pages`
      workflow with `run_gate`); fix what a person can see is wrong, waive the rest with a reason. Do not loop on it.
- [ ] Every state in rule 11 handled.
- [ ] Screenshots use test data, never real accounts, names or messages.
- [ ] Once by hand: the new image next to a native Mac app such as Mail or Notes. Does something lie over something
  else? Is the selection neutral? Does content run under the toolbar? Is only one thing coloured? Would you share the
  image?

## 18. Material

Material is a translucent surface: what lies behind shows through, blurred (`backdrop-filter`). Crewcut has one big
sheet of it, the window on the desk, and a few small pieces. Too much glass looks cheap and costs rendering time.

| Surface | Token |
|---|---|
| The window on the desk | `--material-window`, `--blur-window` (`blur(44px) saturate(1.5)`) |
| Tags on pictures ("Pick a thumbnail", "Scene 5, 62 %") | `--material-tag`, `--blur-tag` |
| Palette, the teleprompter dialog | `--material-float`, `--blur-float` |
| Teleprompter controls (on the phone) | `--prompter-material` |

Inside the window nothing blurs again: panels, cards, rows and the composer are tiles (`--tile`, `--chip`) or opaque
cards (`--card`). Every material surface follows these five steps, in this order:

1. an opaque colour (`--panel`, `--card` or `--tag-solid`) as the base value;
2. inside `@supports (backdrop-filter: blur(1px))` the translucent colour plus `backdrop-filter` and
   `-webkit-backdrop-filter`;
3. a fine light edge (`--edge-window`, `--tag-edge`, `--edge-light`);
4. in `@media (prefers-reduced-transparency: reduce)` opaque again;
5. in `@media (prefers-contrast: more)` opaque, with a `--line-strong` edge.

**The desk** behind the window is the rendered wallpaper (`--wallpaper`), credits in
`web/public/wallpapers/CREDITS.md`. It never moves. No refraction effects. If you notice the effect, it is too strong.

## 19. Media first

- Pictures are the content: real thumbnails, frames, render frames and Shorts, never a drawing that pretends to be one.
  What is missing says so in one line ("No pictures yet. Thumbnails, the cut and renders show here as the crew makes
  them."), with Slate where a whole area is empty.
- The state of an episode stands in the line under its picture, never on the thumbnail (it would fight the
  thumbnail's own words). On a picture only small tags: what is asked, the length, a progress figure.
- The episode view (`GET /api/episodes/{id}/media`, reloaded while a job of the episode runs):
  - **Thumbnail:** the variants large as a radio group, the recommended one chosen with a mint ring and "Designer's
    pick", "Use A" on each (the primary one on the chosen variant; it accepts the thumbnail card with that choice),
    and the chosen one at phone size between two other covers ("B in your feed").
  - **Cut:** ten real frames as a strip, the waveform from `peaks`, the Critic's notes as amber marks (red for an
    error) on the frame and on the waveform, the style facts as chips, the time axis.
  - **3D scenes:** one large picture and up to four small ones; the one in work shows its render tiles and percent,
    a queued one says "queued" without a picture.
  - **Rented GPU** (rule 14): its own dark green card over the newest frame.
- The Shorts row draws the English title over the text-free frame.
- Demo data is English everywhere (titles, cards, chat lines, crew messages), its pictures carry no German text, and
  the "Demo data" line stays.

## 20. Astryx

Crewcut uses parts of [Astryx](https://github.com/facebook/astryx) (MIT, prebuilt CSS in layers): `Button`,
`Badge`, `StatusDot`, `ProgressBar` and `Kbd`. Its theme `crewcut` (`web/src/styles/astryx-theme.css`, switched on
by `data-astryx-theme="crewcut"` on `<html>`) points every Astryx token at ours, so Astryx has no colours of its own.
Our own CSS is unlayered and always wins. The media layer (desk, window, thumbnails, film strip, waveform, render
tiles, GPU card, phone check), Slate, the chat, the cards, the composer and the command palette stay ours.
