# Writing a template or a custom comp

A library template (`templates/motion/<name>.jsx`, or the pack's `brand/templates/motion/<name>.jsx`) and a custom comp
(`episodes/<id>/motion/<insert-id>/comp.jsx`) are the same thing: one ES5 script file with a header and one function of
the header's name. Both render through the same code, both are cached by the same kind of hash, and a good custom comp
becomes a template by `crewcut motion promote` without a rewrite. The contract is `templates/motion/README.md`; this
page is how to write one well.

## 1. The header

```
/* @template side_words
   @description One to three words rise beside the speaker and leave with the next camera move.
   @kind overlay
   @formats ["landscape", "portrait", "stage"]
   @version 1
   @sounds [{"at": "land", "sound": "pop"}]
   @params {"comp": "Main", "words": ["runs", "offline"], "land": 0.6, "out": null, "size": 140, "stagger": 0.08,
            "accent": 1}
   @end */
```

| Tag | Rule |
|---|---|
| `@template` | the name; the file must hold `function <name>(P)` |
| `@description` | one sentence of what one sees |
| `@kind` | `full` (own ground, not transparent) or `overlay` (RGBA over the speaker) |
| `@formats` | the formats it renders well in: `landscape` (16:9), `portrait` (9:16), `stage` (1080 x 960 in a Short) |
| `@version` | a whole number; a change to a library template is a new version (the old file stays as `<name>.v<N>.jsx`) |
| `@sounds` | a list of `{"at": …, "sound": …}`; `at` is `"in"`, `"out"` or a param name that holds seconds; sounds from the synthesized kit: `whoosh`, `tick`, `typing`, `pop`, `click`, `hit`, `riser`, `reel_tick`, `bell`. At most one per motion in a talking video |
| `@params` | JSON with **every** param and its default, so the template renders with `{}` |

`crewcut motion template show <name>` prints what the parser read. A header that does not parse is left out of the
library silently: check it with `template list` after every edit.

## 2. Params

- **Times are seconds local to the insert** (0 = its first frame). Plan cues arrive as params of the same name:
  `"cues": {"land": {"word": "offline"}}` becomes `land: 0.62`. Name a cue param after what happens at it (`land`,
  `click`, `handoff`), not `t1`.
- **Everything episode-specific is a param with a default:** texts, numbers, counts, which item is the accent. A custom
  comp that hard-codes "4 jobs" cannot be promoted.
- **No sizes in pixels of a frame, no colours, no font names** in params or code. Sizes are in 1080-units
  (`CC.px(140)`); colours come from `CC.color(i)`, `CC.pastel(i)`, `CC.ground()`, `CC.ink()`; fonts from
  `CC.font("display")`. A param may pick a palette index (`"accent": 1`), never a hex value.
- Unknown params are refused at run time: a typo fails loudly.
- Promotion renders every claimed format with the defaults and with a second param set (texts twice as long). Design
  for long text from the start: measure (`EC.dims`), wrap, or scale down to the `min_text_px` floor, never below.

## 3. Formats and the frame

Every position goes through `CC.frame()`: `W`, `H`, `u`, the `safe` box, the `face` box, the free `side`, its `sideBox`
and an `anchor` at chest-to-shoulder height. No template contains `1920` or `1080`; the lint refuses them. A full-frame
template lays its own ground (`CC.ground()`), an overlay draws only its elements. Overlays never touch the face box.

## 4. The rules in code

- Entrance 0.35 to 0.5 s (`CC.mg().enter_s`), ease `expo`; springs only on scale, overshoot at most 4 %.
- Exit `CC.mg().exit_s` with ease `in`, or carried by the next camera move. Never a fade of the whole frame.
- Holds never stand still: a linear push of `CC.mg().drift_pct_per_s` per second.
- Motion blur: switch it on (`mb: true`) on layers that move fast; leave it off on layers that only drift.
- The word or number is complete 1 to 2 frames before its cue.
- No box, chip or pill behind a word. The lint flags a filled or rounded rect tied to a text layer as a candidate.
- No Shatter, no Temporal Motion Blur, no font names: lint errors.
- Seeded randomness only (`EC.rng(seed)`): the same params give the same frames.

## 5. An annotated example

```js
/* @template side_words
   @description One to three words rise beside the speaker and leave with the next camera move.
   @kind overlay
   @formats ["landscape", "portrait", "stage"]
   @version 1
   @sounds [{"at": "land", "sound": "pop"}]
   @params {"comp": "Main", "words": ["runs", "offline"], "land": 0.6, "out": null, "size": 140, "stagger": 0.08,
            "accent": 1}
   @end */
function side_words(P) {
  var F = CC.frame();                          // the insert's frame: W, H, u, safe, face, side, anchor
  var mg = CC.mg();                            // the pack's motion tokens: enter_s, exit_s, drift_pct_per_s
  var f = CC.font("display");                  // {font, style} from the pack, never a name here
  var c = P.comp;
  var px = CC.px(P.size);                      // 140 units: 140 px at 1080 lines, scaled for other sizes
  var lineH = px * 1.1;
  var done = P.land - 2 / F.fps;               // the last word is complete 2 frames before the spoken word
  var out = P.out === null ? F.duration - mg.exit_s : P.out;
  var drift = px * mg.drift_pct_per_s / 100;   // the hold rises slowly: never a still frame
  var x = F.anchor[0];
  var top = F.anchor[1] - (P.words.length - 1) * lineH / 2;
  var ids = [];
  for (var i = 0; i < P.words.length; i++) {
    var y = top + i * lineH;
    var tEnd = done - (P.words.length - 1 - i) * P.stagger;   // staggered, the last one lands on the cue
    var tStart = Math.max(0, tEnd - mg.enter_s);
    var id = EC.text(c, {text: P.words[i], font: f.font, style: f.style, size: px, justify: "center",
                         fill: i === P.accent ? CC.color(0) : CC.ink(),   // the accent only on the word that matters
                         mb: true, "in": tStart, out: out + mg.exit_s});
    // enter from below (expo), drift while holding (linear), leave upwards (in)
    EC.keys(c, id, "transform/position", [
      [tStart, [x, y + 0.35 * px]], [tEnd, [x, y]],
      [out, [x, y - drift * (out - tEnd)]], [out + mg.exit_s, [x, y - drift * (out - tEnd) - 0.5 * px]]
    ], ["expo", "linear", "in"]);
    EC.keys(c, id, "transform/opacity", [[tStart, 0], [tEnd, 100], [out, 100], [out + mg.exit_s, 0]],
            ["expo", "linear", "in"]);
    ids.push(id);
  }
  return {layers: ids};                        // what the template made, for the build log
}
```

Run it alone: `crewcut motion --templates-dir <folder> run-template side_words --params '{"words": ["runs",
"offline"], "land": 0.62}' --context @ctx.json`, then `crewcut motion render sheet` over its length. The workbench
passes the context itself in a plan render.

## 6. `CC_CTX`: what the template is told

```json
{"format": "landscape", "size": [1920, 1080], "fps": 25, "duration": 4.0, "transparent": true,
 "face": {"x": 0.5, "y": 0.38, "w": 0.32, "h": 0.28}, "backdrop": null, "draft": false,
 "brand": {"colors": {…}, "fonts": {"display": {"family": "…", "weight": 800}}, "shape": {…},
           "mg": {"palette": […], "pastels": […], "ground": "#…", "ink": "#…", "glass": true,
                  "enter_s": 0.4, "exit_s": 0.25, "ease": "expo", "drift_pct_per_s": 2.0,
                  "blur": {"shutter": 180, "samples": 16}, "plate3d": {…}}}}
```

Read it only through `CC.*`. Without a context (a quick test) `CC` falls back to a landscape insert with neutral
tokens. `backdrop` is the speaker piece (ProRes) for `"backdrop": "speaker"` inserts; frame 0 of the comp must equal
it.

## 7. A custom comp

- `crewcut motion new <episode> <id> --from brief.md` writes the folder and a `comp.jsx` skeleton (empty ground and a
  drift) that renders in both formats. Build on it; keep the header true.
- Plates live in `plates/*.py` next to it and are named in the plan entry (`"plates": [{"id", "script", "args",
  "frames"}]`). The workbench renders them before the comp, into `render/plates/<id>-<hash>/`. Take the plate folder
  as a param, so the same comp renders with a half-size probe still or with the full sequence.
- `refs/` holds reference clips for timing and look only. Never load them into the comp.
- When it passes review and would fit a second video: `crewcut motion promote`. Promotion checks that every
  episode-specific value is a param with a default and renders the samples for the library.
