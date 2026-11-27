# Motion graphics

Motion graphics are short animated pictures in a video: a number that rolls to its value, one or two words that pop in
beside the speaker, a name with a line under it. Crewcut makes them with EffectCraft, an open-source motion graphics
engine, through its command-line program `effectcraft-cli`. This page is for people who make videos with Crewcut.
How the workbench renders them is in [rendering.md](rendering.md#motion-graphics-effectcraft-here-or-rented).

Words on this page:

| Word | Meaning |
|---|---|
| insert | a piece of picture that the edit plan puts into the video at a time, e.g. 12.0 to 15.5 s |
| full frame | the insert covers the whole picture; the speaker is not seen while it runs |
| overlay | the insert lies on top of the speaker; around it the speaker stays visible |
| template | a ready motion graphic with settings (params), e.g. `number_roll`; files in `templates/motion/` |
| comp | short for composition: one animated picture inside EffectCraft. A template builds one |
| style pack | your colours, fonts and rules as data (`studio/brand/`), see [style-packs.md](style-packs.md) |

## What a motion insert is

The Editor writes it into the edit plan, like a 2D or 3D insert:

```json
{"id": "m1", "kind": "motion", "scene": "number_roll", "start": {"word": "costs", "offset": -0.6}, "end": 14.2,
 "cues": {"landAt": {"word": "thirty"}}, "data": {"value": "30", "unit": "cents"}, "sound": true}
```

- `scene` names a template; `source` names a comp made only for this episode (`motion/m3/comp.jsx`).
- `start` may sit on a spoken word: 0.6 s before "costs". When the speaker cut changes, the insert follows.
- `cues` say when something happens: here the number lands when "thirty" is spoken.
- `transparent: true` makes an overlay; otherwise the insert is full frame with the pack's ground colour.
- `sound: true` adds the template's own sound (a whoosh, a hit or typing) to the cut, at most one per insert.

All fields are in [architecture.md](architecture.md#edit-plan-episodesideditplan-vnnnjson).

```
crewcut render plan   <plan.json>     lists the motion inserts, warnings and notes
crewcut render motion <plan.json>     renders them (--draft for a quick look, --ids m1,m2 for some)
crewcut render all    <plan.json>     2D, motion, 3D, then the cut
```

## Colours, fonts and the look

Templates never hold your colours or font names. They read them from your style pack: `colors`, `fonts` and the
block `motion_graphics` in `brand.json` (content colours, light versions, ground, entrance and exit times, motion
blur). Without that block the content colours come from your accent: the accent, its opposite colour and two
neighbours, all equally light. Your font files in the pack work without installing them. Details:
[style-packs.md](style-packs.md#brandjson-motion_graphics-motion-graphics).

## Where they render: two locations

One setting decides, in `config/crewcut.toml` of your studio:

```toml
[render]
location = "local"         # or "rented"
```

| Location | What happens | Good for |
|---|---|---|
| `local` (default) | your computer renders, on its processor; the Crewcut image has `effectcraft-cli` | everyone with the Crewcut image; nothing leaves your computer |
| `rented` | one rented machine renders, after you say yes on a card; it is deleted at the end | a computer that should stay free, or one without the engine |

On a rented machine:

- a card shows the price first; nothing is rented before your yes;
- the cap is $2 for a video and $0.50 for a Short; the plan can set a lower one (`"motion_cap_usd"`);
- only the generated animation script, its settings, your font files and the pictures the insert shows go up. Your
  recording, your voice and your keys never do. An insert that needs your recording (a speaker backdrop) renders on
  your computer only;
- the machine is deleted when the work is done, also after an error.

`crewcut render motion <plan> --local` or `--rented` overrides the setting for one run.

Speed: not measured yet. The first second of every insert is timed, and the log says how long the rest should take.

## The defaults

| What | Default | Where you change it |
|---|---|---|
| Full-frame motion insert | 3 to 6 s | `edit-style.json` `motion.insert_s` |
| Overlay | at least 1.5 s | `motion.overlay_min_s` |
| Motion graphics before the 2D counter and keyword | yes, when the engine is there | `motion.prefer` (`"motion"` or `"2d"`) |
| Big moments (full frame) | 3 to 5 per video; a Short at most 2 | `motion.big_moments`, `motion.shorts` |
| All motion graphics | at most 2 per minute, never two starting within 6 s | `motion.per_minute_max`, `motion.min_gap_s` |
| Per sentence | at most one | `motion.per_sentence_max` |
| Entrance, exit | 0.4 s, 0.25 s | `brand.json` `motion_graphics.enter_s`, `.exit_s` |
| Motion blur | 180 degrees, 16 samples (8 with `--draft`) | `motion_graphics.blur` |
| Money for rented work | $2 a video, $0.50 a Short | `"motion_cap_usd"` in the plan (lower only) |

`crewcut render plan` warns when a plan breaks a rule. A warning does not stop the render; the Critic decides.

## When the engine is missing

Without `effectcraft-cli`, `crewcut render motion` stops with one sentence and says what to do (use the Crewcut image,
or set `location = "rented"`). Everything else still works. A plan with `"motion_without_engine": "skip"` lets
`render all` finish without the motion graphics; the cut's notes name them. The demo episode does this.

## Ready-made libraries

Before a graphic is built from scratch, the crew looks at three free libraries: HyperFrames templates (overlays and
UI inserts as 2D scenes `hf-*`), private imported templates (Lottie and After Effects, converted to your style) and
CC0 HDRIs and materials for Blender. See [motion-libraries.md](motion-libraries.md).

## Behind the speaker

See [motion-matte.md](motion-matte.md).
