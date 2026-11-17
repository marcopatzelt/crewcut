# Engine pitfalls

EffectCraft is a Rust compositor with an After Effects-style object model. `effectcraft-cli --empty commands --json`
(or `crewcut motion commands`) lists every command id and its params; unknown params are refused with the accepted
list. `app.run(id, params)` inside a script reaches every command. These are the traps that cost time while the launch
film was built. Each has a repro, so you can test whether a new engine pin still has it.

| Pitfall | Repro or evidence | Workaround |
|---|---|---|
| `keys.setEase` took layer time only, while the other key commands take `timeBase` | a layer with `start: 1`; `prop.addKey {time: 2, timeBase: "comp"}`; `keys.setEase {time: 2, side: "in", influence: 90}` finds no key at 2 s | fixed by `third_party/effectcraft/patches/0001-keys-setEase-timeBase.patch`; `EC.keys` passes `timeBase: "comp"` and falls back to the layer's start time on builds without the patch |
| A frame render through the persistent engine comes out at half size | `mcp --empty`, `comp.new` 1920 x 1080, `render_frame {path}` writes 960 x 540 | always pass `max_side` (`render frame --max-side 1920`); the harness does it in `--persistent` mode |
| Nulls are 100 x 100 with the anchor at (50, 50), so children sit relative to the top-left corner | `layer get <null> transform/anchor` gives `[50, 50, 0]` | `EC.nul` sets the anchor to (0, 0, 0); parent first (`layer.setParent … compensate: false`), then set the child's position |
| A shape with only a stroke gets a default blue fill `[0.25, 0.55, 1.0]` | render a stroke-only rect: blue inside | pass `fillOpacity: 0` |
| Effect points (Shatter force, Gradient Ramp start and end, effect camera XY) are in layer pixels; shape and text layers have comp-sized effect bounds centred on their origin | a Shatter force at `[0.5, 0.55]` broke only the top-left corner | compute points in the layer's pixel space |
| Shatter renders only inside the layer bounds and has no memory: a piece breaks while it is inside the force sphere now, its position is velocity × time since the layer start; a force sphere deeper than its radius never touches the plane | the early logo break: sparse, slow, a ring of thin triangles (`lessons/02-shatter-vs-authored-flakes.jpg`) | do not use Shatter in a video piece (the lint refuses it); hero breaks are Blender plates with authored paths |
| 2D layers above a 3D group in the same comp were hidden | the cursor above the card grid was invisible; the same cursor showed after the grid moved to its own comp (a minimal repro did not reproduce it) | keep every 3D group in its own comp and nest it |
| A text animator reply gives only a uid; animator paths are by index | `layer.addTextAnimator` returns `{animator: 126}`; the path is `text/animators/#2/selectors/#1/start` | `EC.animator` counts the existing animators and returns `{uid, index, path}` |
| There is no `layer.info` | — | `EC.dims` reads `layer.width/height` through the object model |
| A long render keeps every frame in memory | one process over a long range runs out of memory | render in chunks (`--chunk 1.0`, a fresh process each); jobs = cores / 4 |
| Temporal Motion Blur is very expensive on the CPU | an early 2.6 s beat with it: 72 s wall time, 57 CPU minutes for 156 frames | never use it; the comp's motion blur switches give the same look (the lint refuses it) |
| Running a build stage again on an existing project duplicates comps | a stage re-run gave two `Beat4` comps | delete the project before rebuilding (`rm -f p/x.ecproj*`), or build into a new file |
| A failed step in a shell build dies silently | `set -e` with the output thrown away: the script stops, nothing says where | wrap every call (`ok …`, see `pipeline.md`) to print the call and the end of its JSON error |
| The GPU compositor is untested | `render video --gpu` was never compared with the CPU path | render on the CPU; it was fast enough for the launch film |

## Before you blame the engine

- Read the command's params: `crewcut motion commands --filter <word>`. A misspelt param is refused with the list of
  accepted ones; read that list.
- Read the property path: `crewcut motion layer props <layer>`. Paths are by name or by `#index`.
- Render one frame at the time in question (`render frame --time T --max-side 960`) instead of the whole piece.
- Keep the generated script (`run-template … --keep-script f.jsx`) and run it with `crewcut motion script f.jsx` to
  isolate the step.

## What should be patched next

Small, tested patches, one change each, as numbered files in `third_party/effectcraft/patches/` (never a fork, never a
pull request upstream without the maintainer's OK):

1. `layer.addTextAnimator` returns `{animator, index, path}`.
2. A read-only `layer.info` with source size, duration, start, in, out and anchor.
3. The persistent `render_frame` defaults to the full comp size, or names the size in its reply.
4. Shatter: a per-piece break time and a "toward the camera" force direction (today not usable for hero moments).
5. `keys.velocity` takes `timeBase`, like the `keys.setEase` patch.
