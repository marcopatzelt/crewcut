# Ready-made graphics libraries

Crewcut's crew starts a graphic from a ready-made building block before it builds one from scratch. Three free
libraries give those blocks. Every block takes the studio's own style (colours, font, motion), never the look of its
source. This page is for people who make videos with Crewcut and for the agents that build the graphics.

Words on this page:

| Word | Meaning |
|---|---|
| building block | a finished graphic with settings (params): a keyword, a card, a chapter card, a snippet, a diagram |
| HyperFrames | HeyGen's open-source program (Apache-2.0) that renders an HTML page frame by frame to video |
| Lottie | a file format (JSON) for vector animation; many designers export it from After Effects |
| HDRI | a photo of a whole surrounding (360 degrees) that lights a 3D scene like the real place |
| CC0 | a licence that gives a file to everyone: free, also commercially, no credit needed |
| studio style | the four colours, the font and the motion of your channel (`crewcut motion style`) |
| alpha | the transparent part of a picture; an overlay with alpha lies on top of the speaker |

```
crewcut motion libraries        what is there: HyperFrames templates, your private imported templates, 3D assets
crewcut motion style            the studio style every block takes
```

The Designer and the Editor read `crewcut motion libraries` first in the edit step (their prompts say so, and so does
the designer job of every approved insert). They build from scratch only when no block shows the picture, and they
say why in the motion plan.

## The studio style

`crewcut/motion/studio_style.py` reads it from your style pack:

| What | Where | Default |
|---|---|---|
| palette: `ink`, `paper`, `accent`, `highlight` | `channel.json` `graphics.palette`, else `brand.json` `graphics.palette`, else `brand.json` `colors` | the pack's ink, paper and accent; highlight = accent |
| fonts: display (800) and body (500) | `brand.json` `fonts.display`, `fonts.body` (family, weight, files) | Inter |
| entrance | `channel.json` `graphics.motion.ease`, `enter_s` | `cubic-bezier(0.2, 0, 0, 1)` ("emphasized"), 0.4 s (10 frames) |
| exit | `graphics.motion.out_ease`, `exit_s`, else `edit-style.json` `graphics.motion.out_bezier` | `cubic-bezier(0.3, 0, 0.8, 0.15)`, 0.28 s (7 frames) |
| stagger between the elements of one graphic | `graphics.motion.stagger_s` | 0.08 s (2 frames) |
| push (the one transition of an overlay) | `graphics.motion.push_px` | 28 px from the speaker's side, opacity 0 to 100 %, scale 96 to 100 % |
| safe areas | `edit-style.json` `graphics.safe_area` (pixels per format) | 16:9 5 % (overlays 8 % at the bottom); 9:16 6 % left, 18 % right, 10 % top, 20 % bottom |
| smallest text | `edit-style.json` `min_text_px`, Shorts `graphics.text.min_px_short` | 40 px |
| drift of a hold | `brand.json` `motion_graphics.drift_pct_per_s` | 0: 2D stands still |

The highlight is for the keyword and numbers on ink or on video (with an ink halo). On a paper ground the accent takes
its role. A converter maps the colours of an imported file to these four roles.

## 1. HyperFrames templates (overlays and UI inserts)

Five templates in `templates/hyperframes/<name>/`, one per graphic type. Your pack can hold its own in
`brand/templates/hyperframes/<name>/`; a pack template wins over the app's of the same name.

| Scene | Type | Kind | What it shows |
|---|---|---|---|
| `hf-keyword` | a | overlay | one keyword (at most 4 words) or a number with a unit beside the speaker, on an ink halo |
| `hf-card` | b | overlay | the one box form: a definition or a lower third; `variant: "tag"` is the name tag of a proof film |
| `hf-chapter` | c | full | the counted point: the number large, the word under it, the pack's stored shapes at the edges |
| `hf-diagram` | d | full | two to four boxes joined by drawn arrows on a calm paper ground; one box fills with the accent on its cue |
| `hf-snippet` | e | overlay | a short chat (name and text, no bubbles) or a few code lines on the dark box; a marked line gets a band |

An edit plan uses one as a 2D insert:

```json
{"id": "k3", "kind": "2d", "scene": "hf-keyword", "transparent": true, "start": {"word": "kostet", "offset": -0.5},
 "end": 14.2, "cues": {"land": {"word": "dreißig"}}, "data": {"words": ["30 Cent"], "sub": "pro Million Tokens"},
 "beat": 4, "column": "a"}
```

- `transparent: true` for the overlays (keyword, card, snippet), `false` for the full-frame templates (chapter,
  diagram). A full frame shows a style frame first, like every full-frame 2D insert.
- `data` takes only the template's params (`crewcut motion hf show hf-keyword`); a wrong key is refused with the list.
- `cues` take only the template's cues (most have `land`: the moment the graphic is complete, 1 frame before the
  spoken word).
- Colours, font, curves and safe areas are not params: they come from the studio style and are the same everywhere.

```
crewcut motion hf list                                 the templates
crewcut motion hf show hf-card                         params, cues, kinds
crewcut motion hf sample hf-card --out DIR --at 1.2    one still in your style (frames without --at)
crewcut motion hf lint hf-card                         HyperFrames' own check of the built page
crewcut render 2d <plan>                               renders the plan's 2D inserts, HyperFrames ones included
```

How it renders (`crewcut/render/hyperframes.py`): Crewcut builds a small HyperFrames project per insert (the template,
your font files in `assets/fonts/`, the studio style and the params inlined), runs `hyperframes render --format
png-sequence --fps <plan fps>` and keeps the frames like every 2D insert in `render/inserts/<id>-<hash>/`. The 2D
encoder makes the clip: QuickTime Animation with alpha for an overlay, H.264 for a full frame. A changed param, template,
style or HyperFrames version renders again; nothing else does.

Install: the Crewcut image has HyperFrames, pinned in `tools/hyperframes/package-lock.json`, with its pinned
Chrome (`chrome-headless-shell` on amd64, Playwright's headless shell on arm64). Telemetry and the update check are
off; nothing is fetched while it renders. Without it, a HyperFrames insert stops with one sentence and everything else
still renders.

Templates are HTML with GSAP timelines. A new one needs `index.html` (with the line `<!--CC:HEAD-->` in its head,
the root `#root` with `data-composition-id="main"`, one `.clip`), a `template.json` (title, type, kind, formats,
params with defaults, cues) and the helper `window.CC` from `templates/hyperframes/_lib/cc.js`: no fixed colour, font
or size in the template, no clock, no random numbers, no network.

## 2. Imported templates: Lottie and After Effects (private)

Free templates from Mixkit or LottieFiles (later bought ones) may be used in videos but not passed on. They live only
in your studio: `library/templates-private/<name>/`. The app and its public repository never hold them; a CI check
(`tools/ci/no_private_templates.py`) fails on After Effects, Premiere or Resolve template files, on any
`templates-private` folder and on Lottie files without an open licence.

```
crewcut motion imports add FILE --name lower_third_slide --licence "Mixkit Free License" --source <item page>
crewcut motion imports list
crewcut motion imports use lower_third_slide <episode> m4 --text "Title=Kontextfenster"
crewcut motion imports convert FILE --out converted.json        the conversion report only
```

`add` copies the file into `original/` unchanged and writes `template.json` (source, licence, date, report).

- **Lottie** (`.json`, `.lottie`): converted to `converted.json`: every colour to a palette role (greys to ink or
  paper, the saturated colour that paints the most area to the accent, other saturated colours to the highlight),
  every font to your display font (bold styles) or body font, the frame rate to 25 with every time in frames scaled
  (the animation keeps its length), embedded glyphs and web font links removed. Expressions are reported, not
  rewritten. With the engine here, EffectCraft imports it once and renders `preview.png`.
- **After Effects** (`.aep`, `.aepx`): EffectCraft's own importer, first as a dry run. Only an import that loses
  nothing is kept (`--allow-losses` keeps the rest); templates with third-party plugins (Element 3D, Trapcode, Saber,
  ...) are refused by the dry run. One script then sets every comp to 25 fps and every text layer to your display
  font. The colours inside the project are not rewritten: the template is marked `needs_adaptation` and the Designer
  adapts it in EffectCraft. **This path is partial.**
- `.mogrt`, `.ffx` and Resolve templates have no path on Linux and are refused.

`use` copies the converted Lottie (with this episode's texts, by layer name) to `motion/<insert>/<name>.json` and
prints the plan entry: a motion insert with the template `lottie_clip`, which imports the file in EffectCraft, fits it
into the safe area (`fit: "contain"`) or the whole frame (`"cover"`), plays it at its own speed and holds its last
frame:

```json
{"id": "m4", "kind": "motion", "scene": "lottie_clip", "transparent": true, "start": 31.2, "end": 34.0,
 "data": {"file": "motion/m4/lower_third_slide.json"}}
```

Licences to check per item: Mixkit "Free License" allows commercial use including YouTube, without credit, and no
passing on ("Restricted" items are private only). The Lottie Simple License allows commercial use; changed files are
derived works. Keep the item's page as `--source`.

## 3. Blender with Poly Haven and ambientCG (CC0)

`crewcut/render/blender_lib/crewcut_assets.py` fetches HDRIs and texture sets from Poly Haven and materials from
ambientCG through their public APIs and keeps them in a cache. It uses only Python's standard library, so it runs inside
Blender too.

```
crewcut render assets fetch polyhaven:hdri/studio_small_09 ambientcg:Paper005 --res 2k
crewcut render assets list
```

In a Blender plate (`skills/motion/references/blender-plates.md`):

```python
import crewcut_assets as ca
ca.world_hdri(ca.hdri("studio_small_09", "2k"), strength=0.9, rotation=200)
paper = ca.material_from(ca.material("ambientcg:Paper005", "2K"), name="paper", tint="#FAF9F5")
```

- The plate bootstrap puts the module on Blender's path and sets the cache: here the studio's
  `.crewcut/cache/assets3d`, on a rented machine `/work/assets` (setup.sh makes it and checks that Poly Haven answers).
- On a rented GPU the plate fetches the files there, straight from the sources: they never go up through your
  connection. Only plate scripts, their arguments, the module and font files go up.
- Every file is checked: Poly Haven's MD5, a complete ambientCG zip; only the hosts of the two sources are contacted,
  over https, with a neutral User-Agent (`crewcut-assets/1.0`) and no personal data.
- The template 3D scenes (`templates/3d/`) do not use it yet: changing `stage.py` would render every cached 3D insert
  again. A plate script uses it today.

Licences: Poly Haven (https://polyhaven.com/license) and ambientCG (https://docs.ambientcg.com/license/) are CC0 1.0.

## Tests

| Where | What |
|---|---|
| `tests/render/test_hyperframes.py` | templates, the style in the built page, the plan entry, the frames of a fake renderer (no browser) |
| `tests/render/test_hyperframes_render.py` | the real HyperFrames: lint, a few frames per template and format, size, count, alpha, one still each (CI job `hyperframes`, `CREWCUT_HF_RENDER=1`) |
| `tests/motion/test_imports.py` | the Lottie converter, the private folder, the After Effects path with a fake engine, the repository check |
| `tests/motion/test_imports_engine.py` | the real EffectCraft: the open sample Lottie in the palette, `lottie_clip`, an `.aep` round trip (CI job `motion-imports`, and the image) |
| `tests/render/test_assets3d.py` | specs, cache, checksums, zips, hosts, the plate bootstrap (no network) |
| `tests/render/test_assets3d_blender.py` | real Blender on the CPU: one HDRI and one material light a small Cycles frame (CI job `blender-assets`) |
| `tests/smoke/render.sh` | in the image after a merge: one still of every HyperFrames template in both formats |
