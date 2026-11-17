# Blender plates

A plate is a picture sequence rendered by Blender (Cycles) for something that must catch light: heavy 3D type, a
logo that turns, a small world. The comp places it like footage. Blender runs by code, never with its window, on a
rented GPU or the studio's own NVIDIA card, after a `spend` card. The worked scripts are in `examples/launch-film/`
(`slate3d.py`, `type3d.py`, `meadow3d.py`); copy their patterns.

## 1. The contract of a plate script

```bash
blender -b --factory-startup --python plates/gpu3d.py -- --out DIR --frames 1-120 --samples 96 \
   --t0 0.0 --tin 1.2 [--half] [--frame N] [--font F.otf]
```

- **Time base:** frame `f` shows comp time `t0 + (f − 1) / fps`. Every event time (`--tin`, `--tsmash`, `--tshatter`)
  is in the **same seconds the comp uses**, so plate and comp line up by construction. Inside the script:
  `def F(t): return 1 + round((t - t0) * FPS)`.
- `--half` renders at half size for probes; `--frame N` renders one frame. Always probe first: one half-size still
  per plate, next to the style frame, before the animation.
- Output: RGBA PNG with a transparent film for objects that sit in the comp; JPEG 95 for a full-frame world.
- Fonts come in as a file path (`--font`), never by a name inside the script. Colours come in as hex arguments from the
  pack's tokens (`motion_graphics.plate3d` gives material, bevel and extrude).
- Seeded randomness (`random.seed(n)`), so a re-render gives the same frames.
- In the plan: `"plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0, "tin": 1.2},
  "frames": 120}]`. `crewcut render plates <plan>` renders them through the 3D chooser (own NVIDIA card, else the
  estimate both ways, the spend card, then a rented RTX 4090); each plate is cached by its own hash in
  `render/plates/<id>-<hash>/`. Only plate scripts, their args, tokens and font files go up.

## 2. Colour management

| Plate | View transform | Why |
|---|---|---|
| logos, type, brand objects | **Standard**, look "Medium High Contrast", exposure 0 | exact brand colours; keep whites at 235 to 245, not 255 |
| photoreal worlds (grass, sky) | **AgX**, look "Medium High Contrast", exposure about +0.6 | an HDRI sky needs the range |

Standard clips whites and turns dark greens mint under strong lights: use lights at about a third of what AgX needs.

## 3. Three patterns from the launch film

**3D logo with bristles and a swirl (`slate3d.py`).** The logo SVG is imported as curves and sorted by role from the
importer's colours (they are **linear**, not sRGB). Extrude 0.2, bevel 0.05 with 6 segments; small details sit a few
thousandths in front of the bevelled face. Entrance: pivot scale 0.17 → 1 and a turn of 540° → −18° in 0.25 s; the
hold turns slowly (−18° → +17°) while a strip light sweeps across. The flakes are a Geometry Nodes formula, no
physics: points on the logo grow bristles, release, spiral around the view axis and fly toward the camera, all as
functions of `tau = (frame − F(tS)) / 60`. The camera is fixed (the comp does the push); 50 mm, f/2.8, motion blur
shutter 0.25, Cycles 128 samples, denoised, film transparent. Reversed in file order, the same plate is the "converge"
of the end card.

**Heavy 3D word (`type3d.py`).** Text curve (size 1, extrude 0.14, bevel 0.022) → mesh → loose parts grouped per
letter by x. Each letter flies from near the lens with a rotation and lands in 0.12 s, then squashes (1.12 / 0.84 →
0.95 / 1.07 → 1), staggered 0.035 s. Near-black glossy material (roughness 0.28, coat 0.8). Two puffy shapes pop with
115 % overshoot. Camera 50 mm at a distance from the text width, a slow push, f/3.2, motion blur 0.4, Standard view,
RGBA. **In the comp the plate layer starts at `tsmash − 0.13`**, otherwise glyphs that wait are visible.

**Photoreal world (`meadow3d.py`).** Ground in three zones (near, mid, far) with falling density; blades scattered
with **Geometry Nodes** (Distribute Points on Faces → Instance on Points, random tilt, Z turn and scale), not hair
particles. Wind as a 4D noise on the rotation. Blades from 12 curved, twisted strips with a translucent material and a
dark root; flowers built from petals. An HDRI sky (CC0, downloaded at run time), a back light, a low camera (0.36 m,
horizon at about 40 % from the top), f/2.8. Cycles 64 samples with OIDN, **no motion blur**, persistent data on,
rendered 20 % larger than the frame for a settle in the comp. Bloom comes from the comp (Glow), not from Blender.

## 4. Lessons (each cost time)

- Hair particles rotate instances so their X axis follows the hair: blades lie flat. Use Geometry Nodes.
- A comment in the middle of a line can swallow `transform_apply(scale=True)`: the ground kept its scale and every blade
  was stretched. Keep apply calls on their own line.
- Motion blur on a scene with about a million instances re-syncs the scene per sub-frame on one CPU core (GPU at 0 %):
  20 s and more per frame. Turn motion blur off for slow camera moves and set `use_persistent_data`.
- The SVG importer's material colours are linear, not sRGB.
- Blender 5.0 actions are layered: `action.fcurves` does not exist. Set
  `preferences.edit.keyframe_new_interpolation_type` and edit handles through
  `action.layers[0].strips[0].channelbag(slot)`.
- Bake particle caches before rendering single frames out of order (only if physics is used at all; better: don't).
- Place shapes relative to the visible frame at their depth (`half width = (d − z) · 0.36` for a 50 mm lens on a
  36 mm sensor), not by absolute coordinates.
- Long inline Blender commands are fragile: write the script to a file and run the file.
- Never motion blur twice: a plate with its own blur gets no comp blur (switch it off on the footage layer).

## 5. Cost

See `cost.md`. A beat of new 3D content cost roughly 0.10 to 0.30 $ on one RTX 4090; the expensive part is idle GPU
time while someone writes code. Write and test the script on a half-size frame, then render in one burst.
