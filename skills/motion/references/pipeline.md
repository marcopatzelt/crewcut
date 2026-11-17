# The pipeline: from the idea to a rendered insert

idea → beat sheet → style frame → plates → comp → render → review → into the cut. The launch film
(`examples/launch-film/`) went this way, and so does every custom piece of a video.

## 1. Beat sheet first

Before one layer exists, write `beats.md`: a table in the comp's seconds.

| Beat | Time | Content | Exit motion |
|---|---|---|---|
| 1 | 0.00–0.45 | four job tiles slide out of the laptop outline, staggered 0.06 s | the tiles carry on to the right |
| 2 | 0.45–2.10 | the GPU block lights up (light sweep 0.6–1.0), the tiles enter it | push in 100 → 112 % |
| 3 | 2.10–4.80 | frames fly back and stack, the counter lands "4 / 4" at the cue | a click on the stack grows a circle in the ground colour |

- Every row has an **exit motion**: the thing that causes the next picture (rule 1).
- If a reference exists, measure its timing at 60 fps first (`review.md`, step 1) and write the numbers next to yours.
  The launch film's reference never held longer than about 0.4 s; a talking video holds longer, but never still.
- Cues come from the words: `"cues": {"land": {"word": "four"}}` in the plan becomes a param `land` in seconds local
  to the insert. The word or number is complete 1 to 2 frames before it is spoken.

## 2. Time bases (keep them straight)

| Time | 0 is | Used by |
|---|---|---|
| Insert time | the first frame of the insert | template and comp params, cues, `beats.md`, the review bundle |
| Comp time | the comp's frame 0 (one comp per beat: the beat start) | `crewcut motion key set`, `EC.keys`; layers start at 0 and are trimmed, so layer time = comp time |
| Global time | the start of a multi-beat piece (a `Master` comp) | `layer.timing {"start": t}` when beat comps are stacked |
| Plate time | frame 1 of a plate sequence | frame `f` shows comp time `t0 + (f − 1) / fps` |

Blender scripts take `--t0` and their event times (`--tin`, `--tsmash`, …) in the **same seconds the comp uses**, so
plates and comp line up by construction. Never re-time a plate by hand.

## 3. Style frame before animation

One real frame of the strongest moment, rendered by the engine (not a mock-up), in every format the piece needs:
`crewcut motion render frame --time 2.4 --out frame-v1.png --max-side 1920`. For a 3D piece add one half-size plate
still. Check it (`crewcut motion render palette frame-v1.png`, text sizes) and send the `style-frame` card. Nothing
animated is built before its yes.

## 4. Plates (Blender, rented GPU)

Everything that must catch light is rendered as an RGBA PNG sequence (a JPEG sequence for a full-frame world). One
script per plate in `motion/<insert-id>/plates/`, run after the spend card. Probe first: one half-size still per plate.
Details: `blender-plates.md`.

## 5. The comp

A custom piece is one `comp.jsx` with a template header (`templates.md`). For a longer piece built in stages, the launch
film's pattern holds:

- One comp per beat (local time 0 = beat start), plus a `Master` that stacks them with `layer.timing`. A world that
  spans beats lives in global time and is used by both.
- A build script runs the harness calls in order. Wrap each call so that a failure prints the call and the end of its
  JSON error, then stops:

  ```bash
  ok() { out=$("$@" 2>&1) || { echo "FAILED: $*"; echo "${out: -1500}"; exit 1; }; }
  ok crewcut motion project new -o p/x.ecproj --comp Main --profile 1080p25 --duration 4.8 --overwrite
  ok crewcut motion --project p/x.ecproj comp new Beat1 --duration 4.8 --no-use --bg "#F1F1EF" --samples 16
  ok crewcut motion --project p/x.ecproj run-template gpu_handoff --params @beat1.json --context @ctx.json
  ```

  Without the wrapper, a failed step inside `set -e` with output thrown away dies silently.
- **Delete a test project before rebuilding it** (`rm -f p/x.ecproj*`): running a stage again on an existing project
  adds a second comp with the same name.
- Plates enter as footage sequences: `layer add footage --path plates/gpu/0001.png --sequence --frame-rate 60`, then
  `exec layer.timing --params '{"comp": "Beat2", "layers": [7], "start": 0.45}'` to put frame 1 at `t0`.
- After every stage of the comp: a 12-frame contact sheet (`crewcut motion render sheet --times … --out sheet.jpg`).
  Look at it before building the next stage.

## 6. Render

- **In a video:** `crewcut render motion <plan>`. Per insert: a project in a temp folder with the plan's size and fps,
  `run-template` with params and tokens, a chunked render into `render/inserts/<id>-<hash>/`, then the usual encoders
  (H.264 CRF 14 for full frame, QuickTime Animation with alpha for overlays). Only a changed insert renders again (the
  hash covers params, the `.jsx`, `lib/*`, the tokens and the engine pin). The first frame of each insert is timed and
  the estimate shown before the rest renders. `--draft` = 8 blur samples, half size, for your own looks only.
- **Standalone:** `crewcut motion render video --comp Master --start 0 --end 17.5 --fps 60 --chunk 1.0 --jobs 6 --out
  out/x.mp4`. Each chunk is a fresh engine process (ProRes), joined and encoded once. The reply gives `frames` and
  `expected_frames`: they must be equal. Never render a long range in one process: the engine keeps every frame of a
  chunk in memory (jobs = cores / 4, at least 1).

## 7. Review

The Critic's bundle (`crewcut render motion-review <plan>`) after every round; your own look before that: the sheet,
the 60 fps strips across every transition, the hue check. `review.md`.

## 8. Into the cut

The insert is a `"kind": "motion"` entry of `edit/plan-vNNN.json`:

```json
{"id": "m3", "kind": "motion", "source": "motion/m3/comp.jsx", "start": {"word": "jobs", "offset": -0.4}, "end": 47.5,
 "cues": {"handoff": {"word": "GPU"}}, "data": {"jobs": 4}, "beat": 4, "column": "b", "sound": true,
 "plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0, "tin": 1.2}, "frames": 120}]}
```

- `scene` (a library template, `"number_roll"` or pinned `"number_roll@2"`) or `source` (an episode comp): exactly one.
- `start` may be a word anchor with an offset; cues become params in seconds local to the insert.
- `plates` must exist before the comp renders; each has its own hash and folder `render/plates/<id>-<hash>/`.
- `sound: true` turns the template's `@sounds` into events of the existing `sound.whooshes / hits / typing`, from the
  synthesized kit (`crewcut/motion/sfx.py`): at most one sound per motion, 10 to 14 dB under the voice, ducked.
- Then `crewcut render cut <plan>` as usual (skill `edit`), and the Critic.
