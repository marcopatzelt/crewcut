# Preserve the channel's style, then improve craft

Reproduce the selected channel reference's visual grammar first. Keep its actual
background objects, depth layers, typography (size, spacing, weight, shadows), camera
and motion helpers. A gradient is not equivalent to visible background objects.
Use the original source foundation when available. A product launch film can teach
craft without replacing the channel's identity. Never mix these roles silently.
If a numeric gate fails the approved reference itself, report the conflict before
changing the visual design. The pack's sparse-accent allowance measures colour
against the whole frame; do not add unrelated hues merely to satisfy a histogram.

At the start of each motion job, the conductor supplies the user's selected benchmark
frames, clips, source files and named strengths. Inspect those files. A path in a
prompt is not a visual review. `crewcut motion benchmark list` lists them again.
Never replace a benchmark with an inferior draft just to pass the check.

Use the closest relevant benchmark for the job: object modeling for 3D, graphic
construction and transitions for 2D. Keep its strengths and name one concrete,
visible improvement. "Higher quality" and more pixels are not improvements by themselves.
A stylized clay model may be excellent; its defining parts, edge proportions and
lighting still need deliberate design. A realistic material name on a rounded cube
is not a detailed model. Do not add random details that obscure the idea.
New user feedback takes precedence over old presets. Preserve evidence of previous
preferences, but resolve conflicts instead of treating every old setting as current.

## Reuse before building

Read `crewcut motion library`. Reuse an approved complete source bundle with
`crewcut motion reuse NAME EP NEW_ID [--version N]`. Helpers and assets retain their
relative paths. Legacy source kits are reusable starting points, not native scenes;
adapt their arguments and render a probe. Do not modify the proven library copy.
After a new insert passes review, parameterize its changing values and propose it
with `crewcut motion promote`. Reuse never removes the new episode's quality checks.

## Style frame

The Designer builds the scene and renders the strongest moment. Use an inexpensive
local probe or one rented machine within an approved budget. A probe may have fewer
samples or smaller pixels. It must already show the intended geometry and design.
Do not promise that a cloud GPU will invent missing model detail later.

The Designer sends a separate Critic job the frame paths, source, beat plan and
benchmark ID. The Critic opens both images, compares the source and records the seven
criteria below. Each criterion needs an observation and a comparison with the selected
benchmark. A failed criterion means repair. Do not propose a style-frame card yet.

Write `motion/INSERT/review/style-craft.json`:

```json
{
  "verdict": "pass",
  "reviewer_job": 123,
  "benchmark": "USER_SELECTED_ID",
  "benchmark_sha256": "HASH_OF_BENCHMARK_FRAME",
  "frame_sha256": ["HASH_OF_OUR_FRAME_FOR_EACH_FORMAT"],
  "criteria": {
    "shape_detail": {"pass": true, "observation": "visible defining parts and precise edge scale", "comparison": "which benchmark detail is retained or improved"},
    "materials": {"pass": true, "observation": "intentional surfaces and colours", "comparison": "what separates the surfaces as clearly as the benchmark"},
    "light_depth": {"pass": true, "observation": "contact, depth and controlled highlights", "comparison": "how the light matches the benchmark's craft"},
    "composition": {"pass": true, "observation": "legibility, hierarchy and object proportions", "comparison": "specific comparison at viewing size"},
    "motion_intent": {"pass": true, "observation": "the beat plan's action, camera and spoken cue", "comparison": "the intended timing compared with the benchmark clip"},
    "typography": {"pass": true, "observation": "actual font, weight, size, spacing and shadow", "comparison": "matches the channel reference, not just its font family"},
    "background_layers": {"pass": true, "observation": "visible forms, depth, cropping and movement", "comparison": "preserves the reference's background construction, with no unrequested gradient substitution"}
  },
  "improvement": {"what": "one concrete improvement", "evidence": "where it is visible"},
  "unresolved": []
}
```

Use actual observations, never copy the example's descriptions as findings.
The Critic then calls:

```sh
crewcut motion style-frame EP INSERT --ours motion/INSERT/frame.png --craft-review motion/INSERT/review/style-craft.json
```

Only the Critic job named in the report can submit it. The tool checks frame hashes,
benchmark identity, report completeness and unresolved defects. The card includes the
selected benchmark next to the rendered frame. Acceptance rechecks the evidence.
An imported historical approval is not a new craft review.

## Animation and cloud return

Render only the approved design. Record the renderer, resolution, sampling, motion
blur, render location and exact output path. A local probe is not a final render.
Keep probe output separate from final output. Use rented GPUs for Blender work and
sufficient CPU capacity for the motion compositor; the GPU alone does not accelerate
all 2D work. Do not silently lower quality to fit a machine or budget. Use the normal
compute estimate and accepted budget; if missing, leave a clear budget decision.
Return all frames, validate them, then destroy the rented machines. A successful job
exit or a file count is not visual approval.

The Critic inspects the returned output, not the earlier local probe. Compare each
entrance, main action and exit with consecutive frames of the benchmark clip:

```sh
crewcut motion craft-compare EP INSERT --ours render/insert.mp4 --benchmark ID --start 0 --reference-start 1 --frames 24
```

Repeat with meaningful times for the main action and exit. Read every comparison
sheet and the saved individual PNGs. These are consecutive native frames, without
interpolation. Different frame rates remain explicit in the manifest and labels.
Also inspect the full clip for holds, camera continuity, caused transitions, blur,
clipping and artifacts between the selected windows. Palette checks come after this.

Write `motion/INSERT/review/animation-craft.json` with the same review fields as above.
Here `frame_sha256` contains the complete output clip's hash. Also add:

```json
{
  "style_frame_card": 17,
  "output": "render/insert.mp4",
  "comparisons": [
    {"moment": "entrance", "manifest": "motion/INSERT/review/craft-compare-A/comparison.json", "sha256": "HASH"},
    {"moment": "main_action", "manifest": "motion/INSERT/review/craft-compare-B/comparison.json", "sha256": "HASH"},
    {"moment": "exit", "manifest": "motion/INSERT/review/craft-compare-C/comparison.json", "sha256": "HASH"}
  ]
}
```

The Editor reads the reports and uses the reviewed outputs. Preview/final acceptance
requires unchanged comparison frames, sheets, clips and reports for inserts with the
new craft review. A still review does not approve animation. Existing accepted cards
remain history; do not silently reinterpret them as a new visual approval.

This enforces evidence and independent review. It does not mathematically prove
beauty, and the user may still reject an internally passing result.
