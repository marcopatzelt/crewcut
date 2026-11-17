# Pictures on the landing page

**Wallpapers** (`wallpapers/`): landscapes rendered for Crewcut on 16 November 2026 in Blender 5.0.1 Cycles on one
rented RTX 4090, 5120 x 2880, scaled to 2560 and 1280 px wide. Terrain, haze, valley fog and river are procedural,
written for this project. All third-party assets are CC0 (public domain); no attribution is required, we give it anyway:

| Wallpaper | Sky (HDRI, Poly Haven, CC0) | Authors |
|---|---|---|
| `green-dusk` | [Qwantani Dusk 2 (Pure Sky)](https://polyhaven.com/a/qwantani_dusk_2_puresky) | Greg Zaal, Jarod Guest |
| `mint-dawn` | [Kloofendal Misty Morning (Pure Sky)](https://polyhaven.com/a/kloofendal_misty_morning_puresky) | Greg Zaal |

Trees: [Island Tree 01](https://polyhaven.com/a/island_tree_01) (Poly Haven, CC0), Rico Cilliers, Rob Tuytel.
Ground: [Grass004](https://ambientcg.com/view?id=Grass004) (ambientCG, CC0).

**The meadow** (`meadow/`, the hero and the close): a seamless 8-second loop rendered for this page on 17 November 2026
with Blender 5.0.1 Cycles on one rented RTX 4090, 3840 x 2160 at 30 fps, from
[`examples/launch-film/meadow3d.py`](../../examples/launch-film/meadow3d.py) (Geometry Nodes grass with wind, daisies
and cornflowers, a still camera 0.8 m above the ground, rolling ground towards the horizon; scene script written for
Crewcut, MIT). The wind noise runs on a circle, so the last frame leads into the first with no cut. The page shows the
same daylight meadow in light and dark mode. How it is made: [`site/tools/meadow/`](../tools/meadow/) (`web.sh` renders,
`encode_web.sh` encodes). AV1 at 3840 and 2560 px, H.264 at 2560 px, a 1080 x 1920 crop for phones, posters in WebP
and JPEG.

| Part | Source | Licence |
|---|---|---|
| Sky by day | HDRI [Kloofendal 48d Partly Cloudy (Pure Sky)](https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky), Poly Haven; Greg Zaal (original), Jarod Guest (sky edits) | CC0 |
| Grass, flowers, light, camera | `examples/launch-film/meadow3d.py`, rendered with Blender (used as a tool) | MIT (script); the renders are ours |

**Frames** (`frames/`): 3D scenes the studio rendered for a commercial, cut so that no words show (in the GPU card).

**The app** (`app/`, `crew/`): screenshots of the Crewcut web UI, edge to edge as the app looks now, with the sample
data of `tests/web-sample` (the author's own videos), rendered in CI (screens run 44122818211, commit 5cdbd17). The hero
is `docs/readme/crewcut-dark.png` whole (2880 x 2000), the home the README's `crewcut-episodes-{light,dark}.png` whole,
the phone crops are cut from the same images. The crew tiles are parts of the UI from screens run 43982257994.

## Film

**The launch film** (`film/`, from `docs/launch/`): made with Crewcut's own motion tools on 17 November 2026, rendered
on one rented RTX 4090 (1.75 $ including three review rounds). How it was built: `examples/launch-film/`.

| Part | Source | Licence |
|---|---|---|
| Comp, type, timing | [EffectCraft](https://github.com/storytold/effectcraft) (`effectcraft-cli`) | MIT OR Apache-2.0 |
| 3D (Slate, the meadow, the word "Video!") | Blender 5.0.1 Cycles, scene scripts written for Crewcut | Blender GPL-3.0 (tool); scripts MIT |
| Sky over the meadow | HDRI [Kloofendal 48d Partly Cloudy (Pure Sky)](https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky), Poly Haven | CC0, Greg Zaal (original), Jarod Guest (sky edits) |
| Type | Manrope, Mikhail Sharanda | SIL Open Font License 1.1 |
| Slate, crew, cursor, dock icons | drawn for Crewcut (`docs/brand/`) | MIT |
| Every sound and the music bed | synthesized by code (`examples/launch-film/sfx.py`), no recordings or sample packs; the full sound map is in [`docs/launch/SOUNDS.md`](../../docs/launch/SOUNDS.md) | MIT |
