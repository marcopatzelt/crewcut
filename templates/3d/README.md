# 3D scenes: data keys

Each scene is a Blender Python script in `templates/3d/`. All scenes build on `stage.py`: the stage (a cove: floor
curving up into a wall), materials, light, text, camera and render settings. The look comes from the style pack
(`brand.json` `stage3d`, `colors`, `fonts`, `motion`), passed as `--brand tokens.json`. Neutral defaults: a light grey
stage, a matte off-white base material, the accent colour for the object that matters, soft light, 128 samples.

3D is the exception in a video: 2D carries the numbers. A scene shows one object doing one thing and one word. No
product models of real brands.

## Run

```
blender -b --factory-startup --python templates/3d/<scene>.py -- --data d.json --brand tokens.json \
    --out <dir> --anim --from A --to B [--gpu] [--samples N]
blender -b --factory-startup --python templates/3d/<scene>.py -- --data d.json --brand tokens.json \
    --out still.png --frame N --scale 50          # one still at half size (probe)
```

`crewcut render 3d <plan>` and `crewcut render probe <plan> <id>,<id>` write the data and tokens and run this for you,
here or on a rented GPU (there Blender is `/opt/blender/blender` and the scene files go to `/work/3d/`).

| Argument | Meaning |
|---|---|
| `--data f.json` | scene data (keys below); `format` (`landscape` or `portrait`), `frames`, `fps`, `cues` are set by the workbench |
| `--brand t.json` | render tokens of the style pack |
| `--out` | folder for `--anim` (`0000.png` ...), or a file for a still |
| `--anim --from A --to B` | render frames A to B (inclusive) |
| `--frame N` | render one still |
| `--scale 50` | percent of the full size |
| `--samples N` | Cycles samples (default `stage3d.samples`, neutral 128) |
| `--gpu` | use the first GPU Cycles finds (OptiX, CUDA, HIP, Metal, oneAPI); without one it renders on the CPU |

## Tokens read from the pack

| Token | Neutral | Use |
|---|---|---|
| `stage3d.background` | `#EFEFEC` | stage and world light |
| `stage3d.base` | `#F7F7F5` | the material of objects and sheets |
| `stage3d.accent` | `#E4572E` | the object that matters (ball, blocks, heading bars) |
| `stage3d.material` | `matte` | `matte`, `clay` or `gloss` |
| `stage3d.light` | `soft` | `soft` (key, fill and wall light) or `hard` (small key light, no fill) |
| `stage3d.samples` | 128 | Cycles samples |
| `stage3d.font` | none | a font file in the pack for 3D text; else the display font file of the pack; else the system font of the display family (Inter in the image); else Blender's built-in font |
| `stage3d.text` | `colors.ink` | colour of the 3D text |
| `stage3d.accent_share` | none | optional `[min, max]` percent of accent pixels; `crewcut render measure` checks it when set |
| `motion.entrance_frames`, `motion.entrance_from` | 10, 0.94 | how the word appears |
| `motion.decor` | `none` | anything else adds a few floating accent shapes at the frame edges |

## Keys for every scene

| Key | Type | Default | Meaning |
|---|---|---|---|
| `word` | text | per scene | The word, flat and sharp in front of the scene; landscape left of the object, portrait above it. At most 15 % of the frame height in landscape. |
| `sub` | text or null | per scene | A smaller line under the word; it appears one entrance later. |
| `cues.word` | frame | per scene | The word appears here; the action is timed so its moment lands just before. |

## box

An accent ball in a box made of sheets.

| Key | Default | Meaning |
|---|---|---|
| `action` | `"open"` | `open`: the walls fold out, the lid flies off, the ball grows to full size ("without limits"). `closed`: the walls close in, the lid drops, the ball is pressed small ("held back"). |
| `cues.word` | 30 | |

```json
{"word": "Without limits", "sub": null, "action": "open", "cues": {"word": 30}}
```

## stack

Sheets (documents, no text on them) fall onto a stack, or fly off it.

| Key | Default | Meaning |
|---|---|---|
| `action` | `"fall"` | `fall`: one after the other, the last lands just before the word ("many rules"). `clear`: from the top, sheets fly out until `keep` are left ("delete what is not needed"). |
| `count` | 10 | 1 to 30 sheets |
| `keep` | 3 | `clear` only: sheets that stay |
| `lead` | 0 | `clear` only: frames before the word the first sheet flies |
| `seed` | 5 | changes the small offsets and turns of the sheets |
| `cues.word` | 30 | |

## scale

A balance: on the left a stack of sheets, on the right accent blocks drop into the pan one by one until that side
goes down ("A outweighs B").

| Key | Default | Meaning |
|---|---|---|
| `count` | 3 | 1 to 6 blocks; the last lands just before the word |
| `cues.word` | 60 | |

```json
{"word": "Compute", "sub": "beats rules by hand", "count": 3, "cues": {"word": 60}}
```

## Planned

Not built yet (they exist in the author's studio and wait for a neutral port): `object-word` (one object with an
action and a word), `row` (one becomes several, the word changes), `grid3d` (many objects drop into a grid), `slide`
(blocks slide into an object). A plan that names one of them fails with the list of available scenes.

## Status

Untested in Blender: the scripts were written against the Blender 5.0 Python API and checked only with a stand-in for
`bpy` (every frame of every scene runs through). The first real probe renders on the CI image or a rented GPU decide.
Speed: on the author's laptop CPU the studio's scenes took about 144 s per frame; an RTX 4090 about 20 to 70 s at
128 samples.
