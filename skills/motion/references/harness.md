# The harness: `crewcut motion` and the helpers

`crewcut motion` drives EffectCraft through its native `effectcraft-cli`; nothing is re-implemented. The `.ecproj`
file is the state. A session file next to it (`<project>.cli-session.json`) keeps the active comp, the history and
undo snapshots. `crewcut doctor` shows whether the engine is there (pin and patch count).

## Global flags

`--json` (machine output), `--project P.ecproj`, `--session F`, `--cli PATH` (else `$EFFECTCRAFT_CLI`, then `PATH`),
`--gpu` (GPU compositor, untested: do not rely on it), `--dry-run` (run a change in the engine without saving),
`--templates-dir A:B` (template folders searched before the pack and the app), `--persistent` (one engine process
for all calls of the command). `--json`, `--dry-run` and `--gpu` may also stand at the end of the line.

Exit codes: 0 ok, 1 error (the JSON reply has `error` and often `detail`), 2 usage, 3 `render palette` found a hue
above the limit.

## Commands, group by group

```bash
crewcut motion info                                          # harness and engine version, binary, session
crewcut motion commands --filter text                        # the engine's command registry: ids and params
```

**project**

```bash
crewcut motion project new -o p/x.ecproj --comp Main --profile 1080p25 --duration 6 --bg "#F1F1EF" --overwrite
crewcut motion project open p/x.ecproj
crewcut motion project info
crewcut motion project save --as p/x-round2.ecproj
crewcut motion project profiles      # 1080p60 1080p30 1080p25 vertical60 vertical30 square60 4k30 720p30
```

**comp**

```bash
crewcut motion comp new Beat2 --width 1080 --height 1920 --fps 25 --duration 4 --bg "#F1F1EF" --samples 16 --no-use
crewcut motion comp list
crewcut motion comp use Beat2
crewcut motion comp set --params '{"duration": 5.5}'
crewcut motion comp motion-blur on
crewcut motion comp info --comp Beat2
```

**layer**

```bash
crewcut motion layer add text --text "thirty" --font Inter --style ExtraBold --size 140 --pos 1300,560 --mb
crewcut motion layer add solid --color "#F1F1EF" --name Ground
crewcut motion layer add shape --kind ellipse --size 200,200 --fill "#E4572E" --pos 960,540
crewcut motion layer add footage --path plates/gpu/0001.png --sequence --frame-rate 60 --name GPU
crewcut motion layer add null --name Rig
crewcut motion layer add camera --preset 50mm --dof --focus 1800 --aperture 30
crewcut motion layer add light --kind Spot --intensity 120 --shadows
crewcut motion layer add precomp --source Beat2 --comp Master
crewcut motion layer props Title                     # the property tree with paths
crewcut motion layer get Title transform/position --time 1.2
crewcut motion layer set Title transform/opacity 80
crewcut motion layer switch Title motionBlur on
crewcut motion layer timing Title --in 0.4 --out 3.6
crewcut motion layer parent Title Rig
crewcut motion layer matte Fill Shape --kind alpha
crewcut motion layer blend Flash Add
```

Layers are referenced by name, by id (digits) or as `#n`.

**key, expr**

```bash
crewcut motion key set Title transform/position 0=1300,620 0.45=1300,560 --ease expo
crewcut motion key set Title transform/scale 0=94,94 0.45=100,100 --ease expo --spring
crewcut motion key set Card transform/position 0=200,540 0.6=960,540 --influence 5,95
crewcut motion expr set Rig transform/scale "value + time*2"
crewcut motion expr preset Rig transform/position wiggle --params '{"freq": 1, "amp": 3}'   # wiggle loop spring time
```

Key times are comp seconds. Without `--ease` a segment is `smooth`.

**effect, text**

```bash
crewcut motion effect list --filter blur
crewcut motion effect params glow                     # the param ids and defaults: read them, never guess
crewcut motion effect apply Title glow --values '{"<paramId>": 86}' --keys '{"<paramId>": [[0, 0], [0.4, 60]]}'
crewcut motion text animator Title --props opacity,blur --values '{"opacity": 0, "blur": 12}' \
   --range '{"start": [[0.1, 0], [0.5, 100]]}' --ease out
```

Effect aliases: glow, shatter, particles3d, particles2d, particleplayground, echo, radialblur, directionalblur,
gaussian, lensblur, fractal, ramp, turbulent, carddance, dof, pixelshatter. Never Shatter or the Temporal Motion Blur
effect in a video piece (`engine-pitfalls.md`).

**precompose, template, run-template**

```bash
crewcut motion precompose Card1 Card2 Card3 --name Grid
crewcut motion template list                          # --templates-dir, then the pack, then the app
crewcut motion template show number_roll              # description, kind, formats, sounds, version, defaults
crewcut motion run-template number_roll --params '{"value": "30", "unit": "cents"}' --context @ctx.json
crewcut motion --templates-dir episodes/003-x/motion/m3 run-template gpu_handoff --params @p.json --context @ctx.json
crewcut motion run-template number_roll --params @p.json --keep-script /tmp/m1.jsx   # also write the script
```

A custom comp runs by its name from its own folder (`--templates-dir`). Unknown params are refused (a typo must not
silently do nothing); `--loose` accepts them for a quick test only.

**render**

```bash
crewcut motion render frame --time 2.4 --out f.png --max-side 1920 [--transparent] [--comp Beat2]
crewcut motion render sheet --times 0,0.25,0.5,0.75,1,1.25 --out sheet.jpg --cols 6
crewcut motion render compare --ref refs/x.mp4 --ref-times 3.1,3.4 --times 0.6,0.9 --out compare.jpg
crewcut motion render video --comp Master --start 0 --end 6 --fps 60 --chunk 1.0 --jobs 4 --out out/m3.mp4
crewcut motion render palette f.png --limit 0.30      # hue check, exit 3 above the limit
```

**session, raw engine**

```bash
crewcut motion session status | undo | redo | history --last 10
crewcut motion exec layer.timing --params '{"comp": "Master", "layers": [4], "start": 2.7}'
crewcut motion exec comp.info --params '{"comp": "Main"}' --read-only
crewcut motion batch steps.json                       # [{"command": id, "params": {...}}, ...] in one process
crewcut motion script build.jsx --with-lib            # an AE-style script with EC.* prepended
```

Undo works across processes: the project is copied into `.ecproj-history/` before every change.

## The workbench (whole plans, episode files)

| Command | What |
|---|---|
| `crewcut motion plan <episode>` | the motion plan skeleton from the words and the script marks; validates a finished plan (`director.md`) |
| `crewcut motion library` | the shelf: app templates, the pack's own, earlier custom pieces, with samples and notes |
| `crewcut motion new <episode> <id> --from brief.md` | the folder of a new piece with a `comp.jsx` skeleton that renders in every format it claims |
| `crewcut motion promote <episode> <id> --name <name>` | a reviewed piece becomes a pack template, with samples and an index entry; opens the `template` card |
| `crewcut motion report <episode>` | the skeleton of the motion report for the ratchet (`ratchet.md`) |
| `crewcut render motion <plan>` | every motion insert of an edit plan: chunked, cached by hash, encoded |
| `crewcut render motion-review <plan> [--ids m1] [--ref refs/x.mp4 --ref-offset S]` | the Critic's review bundle (`review.md`) |
| `crewcut render matte` | the person matte on a rented GPU, the edge gate, the fallback (`matte.md`) |
| `crewcut youtube retention <episode>` | the retention curve mapped onto the motion moments |

## Ease presets

An ease is (out influence of the earlier key, in influence of the later key), speed 0 at both.

| Name | Out / in | Use |
|---|---|---|
| `linear` | none | drifts and pushes in holds; iris diameters |
| `easy` | 33 / 33 | small moves |
| `smooth` | 60 / 60 | the default |
| `strong` | 85 / 85 | heavy moves |
| `out` | 8 / 92 | arrive softly |
| `expo` | 3 / 97 | entrances (the house ease): fast start, long settle |
| `in` | 92 / 8 | exits |
| `expoIn` | 97 / 3 | a push that accelerates into a cut |
| `soft` | 40 / 75 | camera moves |
| `snap` | 1 / 99 | a click or a hit |

An explicit pair: `--influence 5,95`, or in a script `[5, 95]`; in `EC.keys` a list gives one ease per segment.

## `EC.*` (lib/ec_lib.jsx)

Every helper calls engine commands (`app.run(id, params)`) inside one script process: one template = one process = one
undo step. Times are comp seconds.

| Helper | What |
|---|---|
| `EC.comp({name, width, height, fps, duration, bg, samples, shutterAngle, renderer})` | a comp, motion blur on |
| `EC.solid/text/shape/nul/camera/light(c, o)` | layers; `o` takes `in`, `out`, `threeD`, `mb`, `blend`, `pos`, `scale`, `rot`, `opacity`, `anchor`, `start`, `parent` |
| `EC.footage(c, path, {sequence, frameRate, name})`, `EC.item(path)`, `EC.precompLayer(c, comp, o)` | footage and nested comps |
| `EC.keys(c, id, path, [[t, v], …], ease)` | keys with eases (preset, pair, or a list per segment) |
| `EC.hold(c, id, path, keys)` | step keys |
| `EC.spring(c, id, path, amp, freq, decay)` | an overshoot after the last key (scale only, at most 4 %) |
| `EC.expr(c, id, path, code)`, `EC.set(c, id, path, v)` | expressions, static values |
| `EC.fx(c, id, effect, values, keys, ease)` | apply an effect and key its params; returns the effect path |
| `EC.animator(c, id, props, name)` | a text animator; returns `{uid, index, path}` (counts existing animators) |
| `EC.trim`, `EC.sw`, `EC.parent`, `EC.matte`, `EC.rename` | in/out, switches, parenting, track mattes |
| `EC.dims(c, id)`, `EC.compInfo(c)`, `EC.layerObj(c, id)` | sizes and the object model (there is no `layer.info`) |
| `EC.rng(seed)` | seeded random: templates render the same every time |
| `EC.hex`, `EC.rgba`, `EC.lerp`, `EC.EASES` | small tools |

`EC.nul` sets the anchor to (0, 0, 0), so a child at (0, 0) sits on the null's position.

## `CC.*` (lib/cc_frame.jsx)

The workbench injects `CC_CTX` (format, size, fps, duration, transparent, face, backdrop, draft, brand); templates read
it only through `CC.*`, so no template holds a frame size, a font name or a colour.

| Helper | Returns |
|---|---|
| `CC.frame()` | `{W, H, u, fps, duration, format, safe, face, side, sideBox, anchor, transparent}`: `u` = short side / 1080; `safe` box; `face` box grown to ± 0.16 W, ± 0.14 H; `side` = `left`, `right` or `below`; `anchor` at chest-to-shoulder height on that side |
| `CC.px(n)` | `n × u` |
| `CC.ctx()`, `CC.brand()`, `CC.mg()` | the context with defaults, the brand tokens, the `motion_graphics` block |
| `CC.color(i)`, `CC.pastel(i)` | content colour `i` (0 = the accent), its light version |
| `CC.ground()`, `CC.ink()` | full-frame ground, text colour |
| `CC.font(role)` | `{font, style}` of `display` or `body` for `EC.text` |
| `CC.blurSamples()`, `CC.shutter()` | 16 (8 in draft), 180 |
| `CC.clearOfFace(box)`, `CC.safe(fmt, W, H, transparent, rightFree)`, `CC.clamp` | placement checks |

## The persistent engine

Measured on the render machine, same task (a new comp, 20 layers with eased keys and Glow, 5 frames at 1080p):

| Way | Time | Processes |
|---|---|---|
| one command per call | 13.9–15.6 s | 66 |
| one JSX script | 2.0–5.7 s | 7 |
| one `effectcraft-cli mcp` process (`--persistent`) | 1.4–1.7 s | 1 (129 requests) |

Identical frames everywhere. Use `--persistent` for many small calls; a template is one script anyway. The persistent
engine always passes `max_side` to frame renders (without it the engine renders a 1080p comp at 960 x 540).
