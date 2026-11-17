# Wallpaper credits

Five landscapes rendered for Crewcut on 16.11.2026 in Blender 5.0.1 Cycles (OptiX, OpenImageDenoise) on one rented
RTX 4090 (Vast.ai, label `crewcut-wallpaper`, deleted after the run). 5120 x 2880, 320 samples with adaptive
sampling. The scene code (`blender/wallpaper.py`) and the 5K masters stay with the design mock, outside this repo.
A light colour grade (exposure, saturation, contrast, a slight tint) was applied afterwards with ImageMagick.

All third-party assets are **CC0** (public domain). No attribution is required; we give it anyway.

| Wallpaper | Sky (HDRI, Poly Haven, CC0) | Authors |
|---|---|---|
| `meadow-day` | [Kloofendal 48d Partly Cloudy (Pure Sky)](https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky), 16k | Greg Zaal, Jarod Guest |
| `green-dusk` | [Qwantani Dusk 2 (Pure Sky)](https://polyhaven.com/a/qwantani_dusk_2_puresky), 16k | Greg Zaal, Jarod Guest |
| `mint-dawn` | [Kloofendal Misty Morning (Pure Sky)](https://polyhaven.com/a/kloofendal_misty_morning_puresky), 16k | Greg Zaal |
| `golden-hills` | [Kloppenheim 06 (Pure Sky)](https://polyhaven.com/a/kloppenheim_06_puresky), 16k | Greg Zaal, Jarod Guest |
| `rhine-evening` | [Belfast Sunset (Pure Sky)](https://polyhaven.com/a/belfast_sunset_puresky), 16k | Dimitrios Savva, Greg Zaal, Jarod Guest |

Used in every wallpaper:

- Trees: [Island Tree 01](https://polyhaven.com/a/island_tree_01) (Poly Haven, CC0), Rico Cilliers, Rob Tuytel.
  Scattered by geometry nodes along field edges and in small woods.
- Ground: [Grass004](https://ambientcg.com/view?id=Grass004) (ambientCG, CC0), colour and normal map, with procedural
  large-scale colour variation.
- Terrain, haze, valley fog and river: procedural, written for this project.

Downloaded but not used in the final renders (close-up grass looked dark and fake at this scale):
Poly Haven `grass_medium_01`, `grass_medium_02`, `dandelion_01`, `celandine_01` (all CC0).

Files in this folder: `<name>-2560.jpg` (2560 x 1440) and `<name>-1280.jpg` (1280 x 720), copied unchanged by
`tools/sample/build_media.py`. The app uses `green-dusk` (dark) and `mint-dawn` (light); `tests/web-sample/media.json`
lists all five.
