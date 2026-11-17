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

Returns `{W, H, u, safe, face, side, sideBox}`:

- `W`, `H`: the comp size; `u` = short side / 1080 (multiply every pixel size by `u`).
- `safe`: `{x, y, w, h}` inside the safe areas: 16:9 keeps 5 % free on every side and the bottom 8 % for overlays
  (player bar); 9:16 keeps top 10 %, bottom 20 %, right 18 % (`shorts.right_free_frac`), left 6 %; stage keeps 5 % on
  every side and the bottom 6 % (the seam to the face).
- `face`: the face box in pixels, grown to ± 0.16 of the width and ± 0.14 of the height around the face centre; no
  overlay may touch it.
- `side`: `"left"` or `"right"`, the larger free side next to the face; `sideBox` its box inside `safe`.

Every template positions through `CC.frame`. Overlays sit on the free side at chest to shoulder height, never over
the face box, never a ring or frame around the head.

### Motion rules (from the handbook, binding)

- Entrance 0.35 to 0.5 s, ease `expo`; springs only on scale, overshoot at most 4 %.
- Exit 0.25 s ease `in`, or carried by the next camera move; never a plain fade of the whole frame.
- Holds never stand still: 1.5 to 3 % push per second, ease `linear`.
- Motion blur 180°, 16 samples (8 in draft); off on layers that only drift; no Temporal Motion Blur.
- Hero text 120 to 160 px (× `u`), nothing below 40 px after every scale and push.
- The word or number is complete 1 to 2 frames before its cue.
- Colours from `brand.mg.palette` in order; the accent only for the one thing that matters.
