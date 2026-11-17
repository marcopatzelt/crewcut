# Motion templates (`templates/motion/`)

In-video motion graphics for Crewcut, rendered by EffectCraft (`effectcraft-cli`) through the harness
(`crewcut motion …`). A template is one `.jsx` file. It runs inside one engine script process with the helper
libraries `lib/ec_lib.jsx` (`EC.*`: layers, keys, eases, effects, springs, text animators) and `lib/cc_frame.jsx`
(`CC.*`: format, safe areas, face box, units, brand tokens). Launch-only templates live in
`examples/launch-film/templates/`; they are loud by design and are not for talking-head videos.

## The contract between the workbench and a template

### Header

```
/* @template keyword_pop
   @description One to three words that pop in beside the speaker, ...
   @kind overlay                      (full | overlay)
   @formats ["landscape", "portrait", "stage"]
   @version 1
   @sounds [{"at": "in", "sound": "whoosh"}]       ("in", "out" or a param name that holds seconds)
   @params { ...every param with its default... }
   @end */
```

- Every param has a default, so a template renders with `{}`. Unknown params are refused.
- Times in params are **seconds local to the insert** (0 = the first frame of the insert). Plan cues arrive as params
  of the same name (`"cues": {"landAt": {"word": "thirty"}}` becomes `landAt: 1.84`).
- A template never contains `1920`, `1080`, a font name such as `Manrope`, the Shatter effect, the Temporal Motion Blur
  effect, or a filled box behind words (the one allowed plate is the frosted glass of `CC.glass`). The lint in
  `skills/cut-check/scripts/motion_check.py` refuses them.

### Context (`CC_CTX`)

The workbench injects one global object before the template runs (`crewcut motion run-template NAME --params … --context JSON|@file`).
Templates read it only through `CC.*`:

```json
{
  "format": "landscape",              // landscape 1920x1080 | portrait 1080x1920 | stage 1080x960 (proof-top Shorts)
  "size": [1920, 1080],
  "fps": 25,
  "duration": 4.0,                    // seconds of the insert
  "transparent": false,               // overlay: RGBA frames, no ground
  "face": {"x": 0.5, "y": 0.38, "w": 0.32, "h": 0.28},   // face box centre and size, fractions of the frame; null = none
  "backdrop": null,                   // path of the speaker piece (ProRes) when the plan says "backdrop": "speaker"
  "backdrop_luma": {"cols": 16, "rows": 9, "values": [0.62, ...]},   // optional: luminance 0..1 of the speaker
                                      // picture (row-major grid, or one number for the free side); overlays pick dark
                                      // or light type from it, light type when it is missing
  "layer": null,                      // overlays: "behind" (the matte passed: composited under the person),
                                      // "beside" or null (next to the person)
  "plates": {},                       // Blender plates: {"id": {"first": ".../0001.png", "frames": 90, "ready": true}}
  "draft": false,                     // 8 blur samples, for the Editor's own looks
  "brand": {
    "colors": {"ink": "#111111", "paper": "#FFFFFF", "accent": "#E4572E", "soft": "#F1F1EF", ...},
    "fonts": {"display": {"family": "Inter", "weight": 800}, "body": {"family": "Inter", "weight": 500}},
    "shape": {"radius": 20, "line": 3},
    "mg": {
      "palette": ["#E4572E", "#2F6FDE", "#F2B84B", "#3BA58B"],  // content colours, first = accent
      "pastels": ["#F8D5C9", "#CDDBF7", "#FBEACB", "#CBE8DF"],  // light version of each (grounds, gradients)
      "ground": "#F1F1EF",            // full-frame ground
      "ink": "#111111",               // text on the ground
      "glass": true,                  // the frosted plate is allowed
      "enter_s": 0.4, "exit_s": 0.25, "ease": "expo", "drift_pct_per_s": 2.0,
      "blur": {"shutter": 180, "samples": 16},
      "plate3d": {"material": "glossy", "bevel": 0.05, "extrude": 0.2}
    }
  }
}
```

### `CC.frame(comp)`

Returns `{W, H, u, safe, face, side, sideBox, anchor, layer}`:

- `W`, `H`: the comp size; `u` = short side / 1080 (multiply every pixel size by `u`).
- `safe`: `{x, y, w, h}` inside the safe areas: 16:9 keeps 5 % free on every side and the bottom 8 % for overlays
  (player bar); 9:16 keeps top 10 %, bottom 20 %, right 18 % (`shorts.right_free_frac`), left 6 %; stage keeps 5 % on
  every side and the bottom 6 % (the seam to the face).
- `face`: the face box in pixels, grown to ± 0.16 of the width and ± 0.14 of the height around the face centre; no
  overlay may touch it.
- `side`: `"left"` or `"right"`, the larger free side next to the face, `"below"` when neither side is 30 % of the
  width (a centred close-up in 9:16), `"center"` without a face; `sideBox` its box inside `safe`; `anchor` a point at
  chest to shoulder height in it.
- With `CC_CTX.layer` `"behind"` (and a face): `side` is `"behind"`, `anchor` sits on the face's x at shoulder height
  (face centre + 0.22 H in 16:9, + 0.16 H in 9:16, + 0.20 H on the stage, clamped into `safe`), `sideBox` is a band
  across the whole safe width there, and the face box rule does not apply (the person covers the graphic).
  `"beside"` behaves like no layer.

Every template positions through `CC.frame`. Overlays sit on the free side at chest to shoulder height, never over
the face box, never a ring or frame around the head.

### Shared helpers (`lib/cc_frame.jsx`)

| Helper | What it does |
|---|---|
| `CC.measure(c, text, size, role)` | ink box and `advance` of a string in a pack font role (measured by the engine, cached); `CC.measureDone(c)` removes the helper layer. No per-character constants anywhere |
| `CC.fit(size, measured, maxW, minPx)` | the size that fits a measured width, never above the wanted size, never under the floor |
| `CC.text(c, o)` | a text layer in a pack font role (`display` or `body`) |
| `CC.tone(box)` | type colour: the pack ink on a full frame; on an overlay dark or light type from `backdrop_luma` under the box |
| `CC.legible(c, id, size, tone)` | two glyph shadows in the opposite tone, overlays only (never a box) |
| `CC.rise(c, id, o)` | the entrance of type: the word rises out of its own baseline (a feathered matte line), with motion blur and a scale settle of at most 4 %, and sinks back for the exit |
| `CC.rig`, `CC.child`, `CC.drift` | a null as a local camera; the slow push of a hold (1.5 to 3 % per second, linear) |
| `CC.stroke(c, o)` | an open stroke path on its own shape layer with a Trim Paths operator (lines that draw themselves) |
| `CC.glass(c, o)` | the one allowed plate: frosted glass over a picture comp (blurred copy, veil, rim, one shadow); null when the pack turns `glass` off |
| `CC.groundLayer(c)` | the full-frame ground: the pack ground lit at its edges by drifting pools of the palette; nothing on an overlay |
| `CC.landBy(cue)`, `CC.enterS()`, `CC.exitS()`, `CC.ease()` | timing from the pack: complete 1.5 frames before a cue, entrance 0.35 to 0.5 s, exit, ease |
| `CC.luma`, `CC.mix`, `CC.lumaUnder` | colour arithmetic and the luminance of the picture under a box |
| `CC.plate(id)` | a ready Blender plate from `CC_CTX.plates`, or null |

### Motion rules (from the handbook, binding)

- Entrance 0.35 to 0.5 s, ease `expo`; springs only on scale, overshoot at most 4 %.
- Exit 0.25 s ease `in`, or carried by the next camera move; never a plain fade of the whole frame.
- Holds never stand still: 1.5 to 3 % push per second, ease `linear`.
- Motion blur 180°, 16 samples (8 in draft); off on layers that only drift; no Temporal Motion Blur.
- Hero text 120 to 160 px (× `u`), nothing below 40 px after every scale and push.
- The word or number is complete 1 to 2 frames before its cue.
- Colours from `brand.mg.palette` in order; the accent only for the one thing that matters.

## The templates

All of them: every param has a default, times are seconds local to the insert, every size is × `u`, the type takes
the pack's `display` and `body` fonts, colours come from `brand.mg` (accent = `palette[0]` only for the one thing),
the hold pushes in at `drift_pct_per_s`, entrances are `enter_s` with `ease`, exits `exit_s`. The hue check
(`render palette --limit 0.30`) counts coloured pixels only: on a neutral full-frame ground with one accent element it
reports one hue at a coloured share under 1 %, which is the calm design, not a fault; read `coloured_share` with it.
For overlays it is run on the graphic alone (the speaker's picture brings its own colours).

### `keyword_pop` (overlay, 2.0 s, min 1.5)

One to three words beside the speaker. Each word rises out of its own baseline (a feathered matte line 0.42 em under
it, so descenders and the shadow stay whole) with motion blur and a 2.5 % scale settle; the block pushes in while it
holds; the words sink back through the baseline in `exit_s`, 0.04 s apart.

| Param | Default | Meaning |
|---|---|---|
| `words` | `["runs", "offline"]` | 1 to 3 words (more are dropped); one line when it fits at `size`, else one word per line |
| `accentWord` | `1` | index of the word in the accent colour, `-1` for none |
| `size`, `minSize` | `140`, `96` | hero size; the widest line is fitted into the free side, never under `minSize` |
| `inAt`, `cueAt`, `outAt` | `0.0`, `null`, `null` | start; a cue moves the start so the last word is complete 1.5 frames before it; the exit ends on the last frame |
| `stagger` | `0.07` | seconds between the words |
| `align` | `"auto"` | left on the right side, right on the left side, centred below the face or without one |
| `behindScale`, `behindMax`, `behindAt` | `1.6`, `300`, `"shoulders"` | with `CC_CTX.layer` `"behind"`: the size and where it sits (`"head"`: `behindMax` at head height) |

Cue: `cueAt` (the last word). Sounds: `pop` on the entrance. Type colour: dark or light from `backdrop_luma` under the
block, with two glyph shadows in the opposite tone. Limits: three words; a word wider than the free side at `minSize`
is set smaller, down to 64 px, so it never leaves its side; behind the shoulders a long word is mostly covered by the body
(a seven-letter word at 224 px showed two letters on each side in the matte test): use `behindAt: "head"` or a
shorter word there.

### `lower_third` (overlay, 4.5 s, min 3)

Name and role, low on the free side (portrait: in the band under the face). The name rises out of its baseline, a
thin accent stroke draws itself under the name's ink from the aligned edge (trim path, 0.55 s, `expo`), the role
follows 0.16 s later at 78 % opacity. No box, no plate. At the end the stroke retracts in the direction it was drawn
and both lines sink.

| Param | Default | Meaning |
|---|---|---|
| `name`, `role` | `"Jordan Lee"`, `"Editor and host"` | the two lines (display and body font) |
| `nameSize`, `roleSize`, `minNameSize` | `84`, `46`, `60` | sizes; the name is fitted to the free side, the role never under 40 |
| `inAt`, `cueAt`, `outAt` | `0.0`, `null`, `null` | the name is complete 1.5 frames before `cueAt` |
| `align` | `"auto"` | the outer edge of the free side (right-aligned on the right side) |
| `line` | `null` | stroke width in px (default 1.4 × the pack's `shape.line`) |
| `layer` | `"Lower third"` | layer name prefix (this template uses `name` for the person) |

Sounds: `whoosh` on the entrance. Limits: a name wider than the free side at `minNameSize` (about 22 characters at
60 px in 16:9) reaches across the body below the face box; it never touches the face box itself.
