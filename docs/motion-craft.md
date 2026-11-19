# Motion craft and imported benchmarks

Crewcut keeps user-selected examples in `brand/motion-quality.json` and their media
and source references under `brand/motion-quality/`. These are private studio data.
The public application never bundles a channel's videos or style preferences.

`crewcut motion benchmark add ID --frame FILE --clip FILE --source SOURCE --strength TEXT
--strength TEXT --strength TEXT --reason TEXT` copies explicitly selected evidence.
IDs cannot be replaced silently. These entries preserve selection provenance; they
are not invented historical review reports or new publication approvals.

Every new edit job for the Editor, Designer, Critic and Showrunner receives the
actual benchmark paths and strengths. Context also explains that recent explicit
feedback overrides old presets. A clay aesthetic may remain intentional; generic
rounded blocks cannot replace detailed, recognizable models merely because a colour
or render check passes. Good geometry, materials, lighting and timing are distinct
requirements. The target is a named improvement while retaining benchmark strengths.

When benchmarks exist, a new style-frame card needs an independent Critic report.
The five craft criteria, visible improvement, exact frames, unchanged benchmark and
reviewer job are checked before proposal and again on acceptance. The card includes
the benchmark image. `crewcut motion craft-compare` saves consecutive native frames
from the rendered insert and selected benchmark clip, a comparison sheet and hashes.
Preview/final acceptance requires animation reviews for newly reviewed inserts, with
comparisons at the entrance, main action and exit. Unchanged older accepted cards
remain historical; installation does not cancel or reinterpret a running production.

The full report contract is in [the craft guide](../skills/motion/references/craft.md).
This validates evidence and review independence. It does not objectively measure
beauty or guarantee that the user will like an internally passing result.

## Local probes and returned cloud renders

Custom Blender plates have an explicit quality profile in their cache key. Probes
use a separate directory, half-size output and 32 samples. Final Cycles plates use
the configured size and sampling (128 by default). A Blender bootstrap applies the
profile before rendering; scripts cannot accidentally leave their low probe defaults
as the final settings. Rented rendering requires an available NVIDIA device instead
of silently running Cycles on the rented machine's CPU.

After local rendering or cloud download, the host checks every expected PNG, its
dimensions and integrity, plus actual render settings. Only then does it write a final
completion receipt. A successful exit code, matching file count or old preview is
insufficient. The Critic then compares the returned final render visually. More
samples reduce rendering noise; they never create missing geometry or better art direction.

Budget limits and the normal compute lifecycle remain. Probes and scene building use
one GPU at most. Native Blender final jobs can distribute frames across several GPUs;
custom motion plates currently use one GPU per render invocation. 2D motion composition
may need CPU capacity rather than GPU capacity. A new budget request stays visible,
including in Full auto; the application does not silently trade quality for a cheaper path.

Verified: synthetic review rejection and changed-artifact tests, consecutive-frame
comparison with real ffmpeg, and a tiny real local Blender probe/final pair. Rented
NVIDIA execution of the new custom-plate bootstrap still needs verification on actual
hardware. No cloud rental is part of installing the feature.

## Reuse proven code

The existing `motion promote` flow still requires a clean review, parameterized values,
rendered samples and a library card. Promotion now also keeps a complete immutable
source bundle per version: composition, Python helpers, nested plate code and assets.
Hashes bind the files. `crewcut motion reuse NAME EP NEW_ID --version N` copies that
approved version into a new insert without changing the original or starting work.
The Editor adapts text, cues, duration and plate frame ranges, then runs fresh reviews.

`motion import-source-kit NAME --root DIR --file RELATIVE_FILE --entrypoint RELATIVE_FILE
--reason TEXT` imports explicitly selected legacy source files. Repeat `--file` for
all required helpers and assets. A source kit keeps relative imports and can be copied
with `motion reuse`; it is explicitly marked as source code needing adaptation, not
as a verified native scene. It never runs during import. Rented plate jobs preserve
Python helper paths, and helper changes invalidate the rendered-frame cache.
