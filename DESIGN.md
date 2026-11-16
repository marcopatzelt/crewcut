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
| Surfaces | `--bg` (chat), `--panel` (side columns), `--card`, `--sunken` (composer, inputs), `--hover`, `--selected` |
| Text | `--ink`, `--ink-2` (supporting), `--ink-3` (meta, timestamps, hints) |
| Lines | `--line` (borders, dividers) |
| Accent | `--accent`, `--accent-ink` (text on accent), `--focus` |
| Status | `--ok`, `--warn`, `--danger` |

- **One accent.** It marks the primary button, links, focus and the selected row. Nothing else.
- **Hierarchy comes from ink and size,** not from extra colours.
- **Status colours mean status.** `--danger` for errors and for money above the cap, never as decoration.
- **Identities have no colours.** They are told apart by their two-letter mark and name (rule 13).
- Text clears 4.5:1 on every surface it sits on, in both themes.

## 5. Type

One family: **Inter** (SIL Open Font License, bundled through `@fontsource`). Numbers that change in place use
`font-variant-numeric: tabular-nums`.

| Use | Size / line height | Weight | Ink |
|---|---|---|---|
| Episode title in the header | 20 / 28 | 600 | `--ink` |
| Section and card title | 15 / 22 | 600 | `--ink` |
| Chat text | 15 / 24 | 400 | `--ink` |
| Rows, buttons, body | 13 / 20 | 400 or 500 | `--ink` or `--ink-2` |
| Meta, hints, group labels | 12 / 16 | 400 (labels 500) | `--ink-3` |

- Three weights: 400, 500, 600. No 700 or heavier.
- Sentence case everywhere. No ALL CAPS labels, no Title Case.
- No italics.
- Titles and rows stay on one line and truncate; the full text is in `title` and in the opened view.

## 6. Shape

| Element | Radius |
|---|---|
| Buttons, chips, marks | full |
| Rows, inputs | 8 px |
| Cards, menus | 12 px |
| Composer | 16 px |
| Window columns | 0 |

A nested shape is smaller than its container. No in-between values.

## 7. Space and layout

- 4 px grid. Paddings 8, 12, 16, 24, 32.
- One inset per surface: everything in a column starts and ends at the same edge.
- Group with space before lines. A divider only between groups that space cannot separate.
- No cards inside cards.
- Design at 1440 x 900, check at 1100, 760 and 390.

## 8. Icons

- `lucide-react` only, 16 px in rows and buttons, 14 px next to 12 px text. No emoji, no icon fonts.
- Icons are bare: no tinted squares or circles. Identity marks are the only shapes with a plate.
- Decorative icons get `aria-hidden="true"`; icon-only buttons get an `aria-label`.

## 9. Motion

- Motion explains a change: a new message slides in (160 ms), a card appears (200 ms), a row in the Crew column fades
  in (160 ms). Ease `cubic-bezier(0.22, 1, 0.36, 1)`. 300 ms is the ceiling.
- The only loop is the thin progress line of a running job, and only while it runs.
- Hover and press: 120 ms, colour and opacity only.
- `prefers-reduced-motion` turns all of it off.

## 10. Words

- Short sentences, sentence case, no exclamation marks, no marketing words inside the app.
- Buttons say what they do. Never "OK", "Submit" or "Yes".
- Errors say what happened and what to do next: "Couldn't reach Vast.ai. Check the key in .env and try again."
- Empty states are one line and one action: "No episodes yet. Say an idea below."
- Times and money are exact and honest: "about 12 min", "$0.31", "API equivalent $0.41 (on your subscription)".
- Never promise unbuilt features in the app. Planned work lives in the README roadmap.
- An agent may name the method it applies, in a short line under its message: "Niche check after Vexian's growth
  stages". It never claims the creator endorses Crewcut.

## 11. States

Before a UI change is done it handles: default, hover, focus-visible, pressed, disabled; loading (keep the layout, spinner
only after 300 ms); empty; error (inline, with retry); long content (a 90-character title, a 4,000-word script, a 30-job
crew); narrow window; light and dark; the engine not logged in.

## 12. Cards

- Card anatomy, top to bottom: who asks (mark and name) and the step; title (15/600); one sentence of reason; the preview
  (options list, video, image, diff, numbers); one primary button; the quiet line "Or say what to change".
- A card about a file shows what the user approves: the exact file, with its checksum stored. Approving means this
  version; any change after that is a new version and a new card.
- A money card shows both ways side by side: "About 3 h on this machine" and "About 12 min for about $0.60 on a rented
  GPU". The referral note sits under the button in `--ink-3`: "Referral link: the author of Crewcut earns 3% of your Vast
  spend as credit. It costs you nothing extra."
- Decided cards collapse to one line in the chat: "Title approved · I ran five local AI models".

## 13. Identities

- Each crew member has a name, a one-line role and a two-letter mark (`SR`, `SC`, `WR`, `ED`, `CR`, `DE`, `PU`, `BR`). The
  mark sits on a neutral plate (`--sunken`, 1 px `--line`). No faces, no mascots, no speech-bubble personalities.
- In the chat a message from an identity starts with its mark and name. User messages have no mark.
- In the Crew column one row per running job: mark, name, "what it is doing" (one line), step, elapsed time, cost.
  Waiting jobs say what they wait for ("Waiting for your yes on the preview").

## 14. Money

- One fixed line at the bottom of the Crew column: "Today $0.00 · Episode $0.62 · Month $3.78 of $20".
- Real money only (rented GPUs, paid APIs). Subscription runs show their API equivalent in the job log, not in the line.
- Above 80 % of the cap the month figure uses `--warn`; at the cap `--danger`, and renting stops.

## 15. Accessibility

- Keyboard first: Tab order follows the three places; Enter sends; Ctrl/Cmd+Enter accepts the open card in view.
- Visible focus ring (`--focus`) everywhere.
- The chat is an `aria-live="polite"` region; cards use `role="group"` with a label.
- Targets are at least 32 px, 40 px on touch.

## 16. What the checks enforce

| Check | Rule |
|---|---|
| `npm run check:tokens` | no raw colour values outside `tokens.css` (4) |
| `npm run check:forms` | the app has one text input (the composer) and no `<form>` with more than one field (1.2, 3) |
| `npm run check:words` | no emoji, no exclamation marks, no "Submit"/"OK" buttons in `src/` (8, 10) |
| `npm run check:contrast` | every text token clears 4.5:1 on its surfaces in both themes (4) |
| `npm run test` | rendering of the empty, loading, error and long-content states (11) |

## 17. Before a release

- [ ] Screenshots of all three places in light and dark, at 1440 and 390 (CI job `screens` makes them).
- [ ] The Taste skill's checker run over the screenshots or the built page; every FAIL fixed or waived with a reason.
- [ ] Every state in rule 11 handled.
- [ ] Screenshots use test data, never real accounts, names or messages.
