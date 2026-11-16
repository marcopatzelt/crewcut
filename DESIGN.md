# Crewcut design rules

These rules cover the web app in `web/` and every page the container serves (the teleprompter too). Every UI change
follows them, whoever writes it: a maintainer, a contributor or a coding agent. A reviewer can point at a rule number and
ask for a change. If a rule stops you from doing the right thing, change the rule in the same pull request and say why.

Several rules are enforced by checks (rule 16); the rest rely on review.
The [Taste skill](https://github.com/Leonxlnx/taste-skill) (MIT) is the design check we run before a release
(rule 17); we link it, we do not copy it.

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

## 2. Three places

The app has three places. New things go into one of them; there is no fourth.

| Place | Width at 1440 px | Holds |
|---|---|---|
| **Episodes** (left) | 272 px | "New episode", one row per episode with its step bar, then "Profile" and "Crew" at the bottom |
| **Chat** (center) | the rest | the episode header with the ten steps, the main chat with the Showrunner, cards and previews, the composer |
| **Crew** (right) | 320 px | who is working on what right now (identity, step, what, time, cost), then the money line |

- One row per episode: title, current step, a ten-segment bar. No counters, no badges with numbers.
- An open card shows as a small dot on its episode row. That is the only "needs you" mark.
- Profile, rules and crew details open in the center place as read-only views. They have no edit controls: a change is a
  sentence to the agent.
- Below 1100 px the Crew column folds into a bar above the composer; below 760 px the Episodes list becomes a menu.

## 3. Input

- The composer is the only text field in the app. Its placeholder says "Say what you want…". It has a microphone button
  (browser speech input where available) and a send button.
- The one exception is the search field of the command palette (rule 15). It picks from a list and takes no values.
- Onboarding is the composer too: "Paste your links." Links go in, the Brand identity works in the Crew column, a profile
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
| Surfaces | `--window` (behind everything, with a faint fixed gradient), `--bg` (chat), `--panel` (Crew column, opaque stand-in for material), `--card` (cards, menus: the raised layer), `--sunken` (fields, mark plates, preview ground) |
| Row states | `--hover`, `--selected` (both neutral grey, translucent) |
| Text | `--ink`, `--ink-2` (supporting), `--ink-3` (meta, timestamps, hints) |
| Lines | `--line` (dividers), `--line-strong` (field edges, card edges in dark) |
| Accent | `--accent`, `--accent-ink` (text on accent), `--focus` (the focus ring), `--selection` (selected text) |
| Status | `--ok`, `--warn`, `--danger` |
| Material (rule 18) | `--material-sidebar`, `--material-bar`, `--material-float`, `--edge-light` |
| Depth | `--shadow-1` (cards in the chat, segments), `--shadow-2` (composer, floating side panels), `--shadow-3` (menus, palette, the teleprompter dialog), `--shadow-press` |

- **Depth instead of lines.** Layers come from material and shadow. A hairline only separates two things on the same
  layer.
- **One accent.** It marks the primary button, links, focus and progress. Nothing else. A selected row is neutral grey
  (`--selected`), as in Finder and Mail. The highlighted item of a menu or the palette is the one place where a selection
  is coloured.
- **Hierarchy comes from ink and size,** not from extra colours.
- **Status colours mean status.** `--danger` for errors and for money above the cap, never as decoration.
- **Identities have no colours.** They are told apart by their two-letter mark and name (rule 13).
- **Three layers in dark:** `--window` darkest, `--bg` and `--panel` in the middle, `--card` lighter. Raised means
  lighter, not darker with more shadow. In dark the light hairline in `--shadow-*` carries the edge.
- Text clears 4.5:1 on every surface it sits on, in both themes. On material the check uses the opaque fallback and the
  translucent colour over `--window`. A token that fails gets more contrast; the rule does not get softer.

## 5. Type

**Inter** (SIL Open Font License, bundled through `@fontsource`) everywhere. On Apple devices the app uses the system
font through `system-ui` (the class `is-apple` on `<html>`), so the browser takes the font that is already installed.
No Apple font file goes into the repo or the image (`check:fonts`). Screenshots are made in CI on Linux, with Inter.
Numbers that change in place use `font-variant-numeric: tabular-nums`.

| Token | Use | Size / line height | Weight | Tracking | Ink |
|---|---|---|---|---|---|
| `--t-title` | The large episode title at the top of the chat | 20 / 26 | 600 | -0.015em | `--ink` |
| `--t-figure` | The one big number of a card ("About 12 min") | 22 / 26 | 600 | -0.02em | `--ink` |
| `--t-head` | Card title, section title, the title in the toolbar | 15 / 20 | 600 | -0.01em | `--ink` |
| `--t-chat` | Chat text | 15 / 23 | 400 | -0.005em | `--ink` |
| `--t-body` | Rows, buttons, body | 13 / 18 | 400 or 500 | 0 | `--ink` or `--ink-2` |
| `--t-meta` | Meta, hints | 12 / 16 | 400 | 0 | `--ink-3` |
| `--t-label` | Group labels ("Episodes", "Working now") | 11 / 14 | 600 | +0.02em | `--ink-3` |

- Three weights: 400, 500, 600. No 700 or heavier.
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
| `--r-panel` | Floating surfaces: Episodes, the chat, Crew, palette, dialogs | 18 px |
| `--r-composer` | Composer | 22 px |
| `--r-full` | Primary button, round icon buttons, dots | full |

A nested shape is smaller than its container: inner radius = outer radius minus the distance to the edge. No in-between
values. Where the browser supports `corner-shape: squircle`, panels and cards use it; elsewhere corners stay round.

## 7. Space and layout

- 4 px grid. Steps: 4, 8, 12, 16, 20, 24, 32, 40.
- The three places are floating surfaces on `--window`, 8 px from the edge and from each other (at 1440 px: 272 px left,
  320 px right). Cmd+B folds the Episodes panel, Cmd+Alt+B the Crew panel.
- The chat runs under the toolbar and under the composer; neither cuts it off with a hard edge.

| Measure | Value |
|---|---|
| Inset of the Episodes panel | 12 px |
| Row height in the Episodes panel | 32 px (an episode row with two lines: 52 px) |
| Toolbar height | 52 px |
| Reading width of the chat | at most 720 px, centred |
| Card padding | 16 px, 20 px from 1100 px window width |
| Between messages / between a message and its card | 20 px / 12 px |
| Composer | floats 16 px above the bottom edge, as wide as the chat |

- One inset per surface: everything in a column starts and ends at the same edge.
- Group with space before lines. A divider only between groups that space cannot separate.
- No cards inside cards.
- Design at 1440 x 900, check at 1100, 760 and 390. The README image is 1600 x 1000 at twice the density.

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
| New row in the Crew column | height 0 to full, `--spring-snappy` | 280 ms |
| Episodes or Crew panel in and out | width, `--spring-soft` | 420 ms |
| Current step dot moves on | position, `--spring-soft` | 420 ms |
| Palette, dialog | scale 0.96 to 1 from where it was opened, `--spring-snappy`; closing only fades | 280 / 120 ms |
| Switching the episode | the content cross-fades, nothing moves | 160 ms |
| Slate works (Crew column) | the bar ticks open and shut four times, again when the crew member reports a new step | 4 × 900 ms |
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
- In the Crew column one row per running job: avatar with its state, name, "what it is doing" (one line), step, elapsed time, cost.
  Waiting jobs say what they wait for ("Waiting for your yes on the preview").

## 14. Money

- One fixed row at the bottom of the Crew column with three figures: today, this episode, this month against the cap
  ("Month $3.78 of $20").
- Real money only (rented GPUs, paid APIs). Subscription runs show their API equivalent in the job log, not in the line.
- Above 80 % of the cap the month figure uses `--warn`; at the cap `--danger`, and renting stops.

## 15. Accessibility

- Keyboard first: Tab order follows the three places; Enter sends; Ctrl/Cmd+Enter accepts the open card in view.
- Every action can be reached without a mouse. Cmd+K (Ctrl+K outside the Mac) opens the command palette: episodes, views
  and actions, filtered as you type. Its search field only picks from the list; it takes no values (rule 3).

| Shortcut | Does |
|---|---|
| Cmd+K | Command palette |
| Cmd+N | New episode (focus in the composer) |
| Cmd+1 to Cmd+9 | Episode 1 to 9 |
| Cmd+B | Episodes panel in and out |
| Cmd+Alt+B | Crew panel in and out |
| Cmd+Enter | Accept the open card in view |
| Esc | Close the palette, menu or dialog |
| / | Focus in the composer |
| Arrow up and down | Move between episodes in the Episodes panel |

- Shortcuts show in tooltips and in the palette as small keycaps: `⌘` on the Mac, "Ctrl" elsewhere. Some browsers keep
  Cmd/Ctrl+N and Cmd/Ctrl+1 to 9 for themselves; the palette offers the same actions.
- Visible focus ring everywhere: `box-shadow: 0 0 0 3px var(--focus)` with the radius of the element, on
  `:focus-visible` only. Never `outline: none` without this ring. The composer shows the ring around its whole capsule. The search field of the palette is
  the one field without a ring: while the palette is open, it always has the focus.
- The chat is an `aria-live="polite"` region; cards use `role="group"` with a label. The step dots stay a list of ten
  items with `aria-current="step"`.
- Targets are at least 32 px, 40 px on touch. A 28 px icon button keeps a 32 px hit area.

## 16. What the checks enforce

| Check | Rule |
|---|---|
| `npm run check:tokens` | no raw colour values outside `tokens.css`; radii, shadows and durations only from tokens (4, 6, 9) |
| `npm run check:forms` | two text fields: the composer and the search field of the palette; no `<form>` with more than one field (1.2, 3, 15) |
| `npm run check:words` | no emoji, no exclamation marks, no "Submit"/"OK" buttons in `src/` (8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in both themes, material counted as its opaque fallback and over `--window` (4, 18) |
| `npm run check:fonts` | no font file in the repo or in `dist/` whose name or inner name contains "SF Pro", "SF Compact", "SFNS", "SF Mono" or "New York"; no `@font-face` with these names (5) |
| `npm run check:materials` | every rule with `backdrop-filter` has an opaque background before it and sits in `@supports`; only the allowed surfaces use material; each has a reduced-transparency and a more-contrast fallback (18) |
| `npm run check:motion` | every animation has a `prefers-reduced-motion` branch; no infinite animation except the run shimmer and the loading spinner; transitions and keyframes move only `transform`, `opacity` and grid tracks (9) |
| `npm run test` | rendering of the empty, loading, error and long-content states (11) |

## 17. Before a release

- [ ] Screenshots of all three places in light and dark, at 1440 and 390 (CI job `screens` makes them).
- [ ] The Taste skill's checker run over the screenshots or the built page; every FAIL fixed or waived with a reason.
- [ ] Every state in rule 11 handled.
- [ ] Screenshots use test data, never real accounts, names or messages.
- [ ] Once by hand: the new image next to a native Mac app such as Mail or Notes. Does something lie over something
  else? Is the selection neutral? Does content run under the toolbar? Is only one thing coloured? Would you share the
  image?

## 18. Material

Material is a translucent surface: the background shows through, blurred (`backdrop-filter`). It is used in a few places
only, because too much glass looks cheap and costs rendering time.

| Surface | Token |
|---|---|
| Episodes panel | `--material-sidebar`, `--blur-sidebar` |
| Toolbar of the chat, money row | `--material-bar`, `--blur-bar` |
| Composer, palette, the teleprompter dialog | `--material-float`, `--blur-float` |
| Teleprompter controls (on the phone) | `--prompter-material` |

Cards, lists and the Crew panel stay opaque: they hold numbers that must read safely. Every material surface follows
these five steps, in this order:

1. an opaque colour (`--panel` or `--card`) as the base value;
2. inside `@supports (backdrop-filter: blur(1px))` the translucent colour plus `backdrop-filter` and
   `-webkit-backdrop-filter`;
3. `box-shadow: inset 0 1px 0 var(--edge-light)` for the fine light edge;
4. in `@media (prefers-reduced-transparency: reduce)` opaque again;
5. in `@media (prefers-contrast: more)` opaque, with a `--line-strong` edge.

Behind everything lies `--window` with a very faint, fixed gradient (two large blurred spots, at most 6 % opacity), so
the glass has something to show. It never moves. No refraction effects. If you notice the effect, it is too strong.

Text that scrolls under the toolbar fades out (`--under-bar-fade` on the scroll area): the material may blur what lies
behind it, but it never shows the chat as a second, ghost title.

