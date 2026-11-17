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
  "backdrop_luma": [[0.62, ...], ...],  // overlays: luminance 0..1 of the speaker picture, 9 rows of 16 values (top
                                      // to bottom), one number for a colour base, null without a picture; templates
                                      // pick dark or light type from it (light type when it is null)
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
| `CC.meter(c, o)`, `CC.rowWidth` | digits that count like a meter (reels behind feathered windows, carries, whole digits on holds); the width of a row set character by character |
| `CC.textColor(i)` | the i-th palette colour that reads as type on the ground (a light yellow on a light ground is skipped) |
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
| `behindScale`, `behindMax`, `behindAt` | `1.6`, `300`, `"head"` | with `CC_CTX.layer` `"behind"`: `"head"` sets `behindMax` at head height (only the head covers the word); `"shoulders"` sets `behindScale` × `size` at the contract's shoulder anchor |

Cue: `cueAt` (the last word). Sounds: `pop` on the entrance. Type colour: dark or light from `backdrop_luma` under the
block, with two glyph shadows in the opposite tone. Limits: three words; a word wider than the free side at `minSize`
is set smaller, down to 64 px, so it never leaves its side; behind the shoulders a long word is mostly covered by the body
(in the matte test a seven-letter word at 224 px showed one letter on each side), which is why `"head"` is the
default: there the same word at 300 px lost one letter to the head and read at once.

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

### `number_roll` (full or overlay, 4.0 s, min 3)

A number that counts up like a meter. Every digit is a reel behind its own feathered window (it opens from a slit on
the first frame and closes at the exit). The value eases from `from` to the target (power `ease`) and lands exactly
at `landAt`: the units reel rolls with the value (blurred while fast) and ticks whole digits when slow, every other
reel turns only when the reel on its right carries from 9 to 0, and the units reel lands with a small settle. Digits
are set tight with their measured advances in the display font, whole on every hold, and the row (grown by the push)
is fitted inside the safe box, so nothing is ever clipped. Leading zeros stay hidden until the count reaches them; a
sign and separators (`+`, `,`, `.`) rise in place and show with the digit on their left. The unit is in the accent
colour; the line of text below drifts slower than the number (depth). The cut in lands on a camera move (the number
settles from 104 % while it counts, then the slow push). Full frame on the pack ground; with a transparent insert it
is an overlay on the free side like `keyword_pop`.

| Param | Default | Meaning |
|---|---|---|
| `value` | `"128"` | the number as shown: digits with `,` `.` or spaces; `prefix` goes in front (a sign or a currency) |
| `unit`, `label` | `"GB"`, `"of memory on one laptop"` | the unit after the number (accent, `unitScale` × size) and one line under it (body font) |
| `size`, `minSize`, `labelSize` | `160`, `110`, `50` | hero size, its floor when fitting, the line's size (never under 40) |
| `rollAt`, `roll`, `landAt`, `cueAt` | `0.0`, `1.3`, `null`, `null` | the count starts at `rollAt` and lands at `landAt` (default `rollAt + roll`); a cue lands it 1 frame before the cue |
| `from`, `ease` | `0`, `2.2` | the start value and the power of the ease-out |
| `outAt` | `null` | the exit: the reels run on upward while their windows close (default: the last `exit_s`) |

Cues: `cueAt` (the number complete 1 frame before it). Sounds: `reel_tick` at `rollAt`, `tick` at `landAt`.
Limits: whole numbers and decimals as written (the count runs over the digits, so `4.2` counts 0.0 to 4.2); no
negative counts; very large numbers (8+ digits) fit by shrinking toward `minSize`.

### `prompt_bar` (full with the speaker as backdrop, 5.0 s, 3 to 6)

"What I asked". The speaker's own picture (`CC_CTX.backdrop`, the piece of the cut) blurs, calms (less saturation,
a touch darker) and stays registered; a frosted glass bar (`CC.glass`, the one allowed plate: a blurred brighter
copy of the picture under a rounded matte, a veil, a rim and one soft shadow) rises in with a small scale settle; the
prompt is typed into it letter by letter with the newest letters in the accent colour and an accent caret that
follows the measured typing front and blinks afterwards; the camera pushes in on the bar while it types, holds, and
pulls back; the bar drops away and the picture clears. Frame 0 and the last frame equal the speaker frame, so the cut
in and out is invisible. Motion blur is on only while the camera moves (the stage is split into five time spans).

| Param | Default | Meaning |
|---|---|---|
| `text` | a 10-word prompt | the prompt; wrapped into at most `maxLines` (3) balanced lines by measured word widths |
| `size`, `minSize` | `54`, `42` | type size (body font); shrinks toward `minSize` before a fourth line would be needed |
| `typeAt`, `charS`, `typeEnd` | `0.7`, `0.045`, `null` | typing start and seconds per letter, or the end of typing (sets the speed) |
| `push` | `1.22` | the camera push; limited so the bar keeps 3 % of the frame free on each side |
| `backdropBlur`, `glassBlur`, `veil` | `26`, `44`, `46` | blur of the picture and of the glass, strength of the frosted veil |
| `outAt` | `null` | the bar's exit (default 0.45 s before the end, so the picture clears to the speaker frame) |

Sounds: `typing` at `typeAt`. Without a backdrop the bar sits on the pack ground. With `brand.mg.glass` false the
plate is left out and the text sits on the blurred picture. Limits: about 40 letters per line in 16:9 at 54 px and
25 in 9:16; longer prompts shrink to 42 px and three lines, then they get tight; prompts over ~120 letters belong in a
screenshot.

### `word_reel` (full, 3.5 s, min 3)

Steps or tools roll past like a slot machine: a column of words scrolls with motion blur, brakes and lands on the
current one; a thin accent selection frame with corner handles (an outline, never a fill) hugs the word in the
middle and resizes smoothly between the measured widths of the words passing it; the words fade with their distance
from the middle. The camera settles from 106 % into the hold and then pushes in; at the end the column runs on upward
and the frame closes. A short list wraps around, so the reel always travels at least `minTravel` lines.

| Param | Default | Meaning |
|---|---|---|
| `words`, `target` | nine production steps, `"Captions"` | the list and the one to land on (a word or an index) |
| `size`, `minSize` | `120`, `72` | hero size; the widest word plus its frame fits the safe width |
| `rollAt`, `landAt`, `cueAt`, `minTravel` | `0.0`, `null`, `null`, `5` | the roll; it lands at `landAt` (default by the distance, 0.9 to 1.5 s), 1.5 frames before a cue |
| `image` | `""` | optional picture behind (a screenshot): tilted, blurred, desaturated, drifting |
| `outAt` | `null` | the exit |

Cues: `cueAt` (the frame lands on the word). Sounds: `reel_tick` at `rollAt`, `click` at `landAt`. Limits: lists of
three or fewer show only one neighbour on each side; words over ~14 letters shrink toward `minSize`.
