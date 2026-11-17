# The motion workflow

How the crew decides which motion graphics a video gets, builds the ones the shelf does not have, keeps the good ones,
and makes every video a little better than the last. What a motion insert is and where it renders:
[motion.md](motion.md). The cards and the API the web UI reads: [api.md](api.md) ("Motion cards", "Motion").

Everything here is written into your studio folder (`episodes/<id>/`, `brand/`), never into the app.

## 1. The motion pass: start from the video

The Editor (with the Designer for the look) runs it once per video, after the speaker cut and its words exist, and in
short form for each Short. It starts from what the viewer must understand or feel in each beat, not from the template
list. Most beats get no motion: the speaker's face and voice carry them.

```
crewcut motion plan <episode> [--short]       # skeleton: edit/motion-plan-vNNN.json and .md
crewcut motion plan <episode> --check         # validate, compute density and budget, write the .md
crewcut motion plan <episode> --check --card  # then open the motion-plan card
crewcut motion library                        # the shelf: app templates, your own, episode pieces
```

The skeleton has one row per beat (sentences of the words file, joined to about 6 s or 3 sentences), the Writer's
marks (`[[motion: number | "thirty cents"]]` below the script's `---` line, at most 5: wishes the director may drop),
the lessons, the bar, the references and the shelf. The director fills the JSON:

- per beat: `purpose` (what the viewer must understand or feel), `picture` (what happens on screen, described as a
  thing that happens, never just a template name), `column`: `a` (a shelf piece, with `piece`, `params`,
  `length_s`), `b` (built new: `piece` names an entry in `new` with its brief and why no shelf piece does it), `c` (a
  chosen upgrade that needs a picture), or `-` (no motion);
- column (c): 2 to 4 upgrade candidates, each with a source (a lesson id, a reference, a gap to the baseline, a
  retention finding); **at least one is chosen**. A plan without a chosen upgrade fails with one sentence.

`--check` refuses a row without purpose, picture or column, a picture that only names a template, a plan where every
beat has motion, a cost over the cap, and upgrades without a source. It warns when lessons exist and no upgrade cites
one, and lists the density findings. The density and budget lines are computed, never typed. The money cap is $2 for a
long video and $0.50 for a Short (`[motion] cap_usd`, `cap_usd_short` in `config/crewcut.toml`).

The **motion-plan card** shows the three columns. A tap strikes a row ("not this one"): a new plan version, the same
card. Shelf pieces may be built while the card is open; new pieces and upgrades wait for the yes. Every motion insert
in the edit plan then names its row: `"beat": 4, "column": "b"`. `crewcut render plan` refuses motion inserts without
an approved row (`crewcut.motion.director.motion_gate`; `--no-gate` only for tests).

A worked example: `examples/demo/edit/motion-plan-v001.md` (one shelf piece, two beats left to the speaker, one chosen
upgrade).

## 2. Custom motion: made for this video

```
crewcut motion new <episode> <insert-id> --from brief.md
crewcut motion style-frame <episode> <insert-id> --ours frame-landscape.png --ours frame-portrait.png [--ref ref.png]
```

`new` makes `episodes/<id>/motion/<insert-id>/` with `brief.md`, `beats.md` (beat sheet in local seconds), `refs/`
(reference clips: timing and look only, never in the output, never uploaded), `review/`, `notes.md` and `comp.jsx`. The
comp starts as a valid empty piece: the pack's ground and a slow push, in landscape and portrait, with the full template
header (`@template`, `@kind`, `@formats`, `@version`, `@params`). The edit plan names it with
`"source": "motion/<insert-id>/comp.jsx"`; it renders through the same code as a library template.

`style-frame` opens the **style-frame card**: one real frame of the strongest moment next to the reference (or the
bar's frame), per format. A frame where one hue holds more than 30 % of the coloured pixels is refused (`--natural`
for grass, sky or footage). Nothing animated is built before this yes (`crewcut.motion.custom.style_frame_gate`).

Blender plates of a piece rent a GPU only after their own `spend` card has a yes; its cap is the motion plan's
(`crewcut render plates`, `crewcut/render/plates.py`).

## 3. Your library

```
crewcut motion promote <episode> <insert-id> --name gpu_handoff [--title "GPU hand-off"]
```

A custom piece that passed its review (its newest Critic bundle has 0 errors) and would fit a second video becomes a
template of your style pack: `brand/templates/motion/<name>.jsx`, its plates as `plates/<name>_*.py`, its images in
`assets/<name>/`, sample loops in `samples/`. Promotion refuses a comp that still holds episode values: a text spoken
in the episode, a value the plan passes that is not a param with a default, a path into the episode. It renders the
samples in every format the template claims, once with the defaults and once with every text twice as long, then opens
the **template card** ("Keep it in your library?"). The index `brand/templates/motion/library.json` holds per name:
`title`, `version`, `kind`, `formats`, `params`, `needs_plates`, `made_from`, `approved` (`null` until your yes),
`sample` and `samples`, `sha256`, `engine_pin`, `history`, `notes`.

A change is a new version: `@version N+1`, the old file stays as `<name>.vN.jsx`. A plan may pin `"scene":
"gpu_handoff@1"`; without a pin it takes the newest. A no on the template card takes the new version out again.

## 4. The ratchet: the bar only goes up

| File | What |
|---|---|
| `brand/baseline.json` → `motion` | the best video so far: episode, report, 3 to 6 named strengths with frames, measured values, history |
| `episodes/<id>/review/motion-report-vNNN.md` + `.json` | the video against the bar: better, behind, upgrades landed, proposals |
| `brand/rules/motion.md` | the lessons: `- 2026-11-17: [2026-11-17-3] rule. Evidence: episode, time, frame (source: review)` |
| `brand/references/motion/index.json` + `files/` | reels and stills to learn from; they stay on this computer |

```
crewcut motion report <episode> --skeleton                          # the form: review/motion-report-input.json
crewcut motion report <episode> --from review/motion-report-input.json
crewcut motion lessons
crewcut motion reference add <link-or-file> --reason "..." [--by user|scout] [--episode <id>]
crewcut motion reference from-chat --episode <id> --text "<the user's message>"
```

After the user has seen the video, the Critic fills the form: what is better than the bar (named, with time and frame),
what is behind (against the bar and each reference used), whether each chosen upgrade landed, what the reference still
does better per piece, 1 to 5 lessons with evidence, the video's strengths, proposals. The report **fails unless it
appends at least one lesson**. When nothing is named better (or a strength of the bar got worse) the version goes back to
the Editor once; the second time the Showrunner tells the user plainly. Above 40 lessons a card proposes a merge.

When the report says better (or it is the first report), a **baseline card** asks whether this video becomes the bar.
Only that yes moves it, and never down: a card made against an older bar, a changed report or a worse measured value
is refused.

References: what the user sends is always filed, with the user's own sentence as the reason; the Scout adds at most 3
per episode, each with a reason. Clips are fetched with `yt-dlp` when it is installed, else only the link is kept.

## 5. Retention

`crewcut youtube retention <episode>` lays the audience retention curve of the published video over its motion moments
(see [youtube.md](youtube.md)). A hint, not proof: findings are "watch" until they repeat in 3 videos, then they become a
lesson. Unproven against a real channel so far.
