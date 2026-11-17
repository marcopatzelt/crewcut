# The launch film: how it was built

[The 17-second launch film](../../docs/launch/crewcut-launch-web.mp4) (poster: [`docs/launch/poster.jpg`](../../docs/launch/poster.jpg))
was made with Crewcut's own motion tools: **EffectCraft** for layout, type, mattes, cameras and timing (driven by
`crewcut motion`), **Blender** for everything that must catch light (the 3D logo, the 3D word, the meadow), and a
sound track **synthesized by code**. It ran on one rented RTX 4090 and cost **1.75 $**, three review rounds included.

The film: 1920 x 1080, 60 fps, 17.5 s, 1050 frames. Everything needed to rebuild it is in this folder, except the
big rendered plates (649 MB) and the author's own pictures in the card grid; both are made again by the commands below.

## What made the difference

1. **Every transition is caused by a motion.** A click starts a burst, a swirl opens an iris, a click grows a circle
   in the next scene's ground colour. No plain cut or cross-fade between ideas.
2. **The camera never stops.** Slow pushes and drifts in every hold (2 to 8 % over a second).
3. **Real 3D where light matters** (Blender: Cycles, depth of field, motion blur); EffectCraft does 2D and 2.5D.
4. **Motion blur on everything that moves, never twice** (Blender plates bring their own).
5. **Colour comes from the content, the brand is an accent:** no single hue above about 30 % of the coloured pixels
   (`deliver_ad.sh` checks it).
6. **Authored paths, not physics,** for anything that must land on a frame (the flake swirl and converge).
7. **Compare frame by frame at 60 fps** around every transition before anyone else sees it.

## Beat sheet (global seconds)

| Beat | Global time | Content | Exit motion |
|---|---|---|---|
| 1-2 | 0-2.7 | dock, cursor hovers, click T0 = 0.92, pixel wave 0.97, disc + 3D logo 0.99, frame full 1.22, bristles tS = 1.62, release tR = 1.96, iris tI = 2.04-2.14 | swirl opens the iris |
| 3 | 2.7-6.85 | meadow + glass bar (slides in 2.07-2.30, approach 100 -> 108 % until 3.45), click 3.45, push 3.5-4.4 to 320 %, typing 3.95-4.95, pull back 5.55-6.25, click on glyph 6.55 | white circle from the click 6.6-6.85 |
| 4 | 6.85-10.05 | hero card springs (local 0-0.5), grid flies in (0.55-1.3), button 1.9, click 2.92 | dark circle from the click |
| 5 | 10.05-12.25 | word reel 0.05-1.2, lands on target, click 1.8 | light circle from the click |
| 6 | 12.25-15.05 | type "Ship" 0.1-0.45, "the_" 0.5-0.75, smash 1.0, push to 108 % | hard cut on motion |
| 7 | 15.05-17.5 | flakes converge until about 1.17, lockup slide 1.25 | end |

In rows 4 to 7 the times under "Content" are local to the beat (0 = the beat's start). Every Blender script takes `--t0` and its event
times (`--tin`, `--tshatter`, `--tsmash`) in the same seconds the comp uses: frame `f` of a plate shows comp time
`t0 + (f - 1) / 60`, so plates and comp line up by construction.

## Files

| File | What |
|---|---|
| `env.sh` | the shared settings every script sources: `WORK`, `OUT`, `ASSETS`, `PROJECT`, `VENV`, `BLENDER`, `FONT_DIR`, `HDRI` |
| `setup.sh` | one-time setup of the rented machine: ffmpeg, rsvg-convert, Blender 5.0.1, Manrope, a Python environment with Crewcut, numpy, scipy and Pillow; `effectcraft-cli` from an archive or `$EFFECTCRAFT_CLI`. Nothing is compiled |
| `prep.sh` | the PNG assets of the comp into `$ASSETS`: dock icons, the app icon, crew cards, your cards, the word-reel backdrop |
| `plates.sh`, `bl.sh` | the plates: pixel grid (Pillow), 3D Slate, 3D word, converge (Slate reversed), meadow; `bl.sh` runs one Blender script |
| `slate3d.py`, `type3d.py`, `meadow3d.py` | the Blender scene scripts (Blender 5.0.1, Cycles + OptiX) |
| `pixelgrid.py` | squares on a fixed grid that switch on and off as a wave from the click (beat 2) |
| `cards.py`, `crewcards.py` | rounded card PNGs from **a folder of your own images**, and pastel crew cards from SVG avatars (default `docs/brand/crew`) |
| `ad.sh` | the whole EffectCraft project (comps `Backdrop`, `World`, `Beat2`..`Beat7`, `Master`) through `crewcut motion` |
| `deliver_ad.sh` | renders the clip and the review sheets: 60 fps strips across every transition, a frame sheet, hue checks |
| `sfx.py` | the full sound track: every effect, the music bed, the reverb and the master (numpy + scipy, seeded) |
| `mux.sh` | picture and sound together: master, web file under 8 MB, poster frame, loudness check |
| `templates/` | the 13 EffectCraft templates the film runs (`crewcut motion --templates-dir`); parameters in each file's header |
| `assets/` | the four dock icons and the white Slate (`slate-white.svg`), drawn for Crewcut, MIT, an `.attribution` file next to each |

The green Slate and the crew avatars come from [`docs/brand/`](../../docs/brand/). The sound map with every cue is in
[`docs/launch/SOUNDS.md`](../../docs/launch/SOUNDS.md).

Not in the repository: the plates and renders (made again by `plates.sh` and `deliver_ad.sh`), the thumbnails, Shorts
covers and renders the author used as cards (bring your own with `CARDS_SRC`), and the reference clip (see below).

## Rebuild it on one rented RTX 4090

The machine the film was made on: 1 x RTX 4090, image `nvidia/cuda:12.4.1-runtime-ubuntu22.04`, 80 GB disk,
`NVIDIA_DRIVER_CAPABILITIES=all` (gives Blender OptiX), 72 CPU cores (EffectCraft renders on the CPU, so cores per
dollar matter more than the GPU for the comp). Copy the `effectcraft-cli` archive and, if you want your own cards, a
folder of images onto it. Then, on the machine:

```bash
git clone https://github.com/marcopatzelt/crewcut.git && cd crewcut/examples/launch-film
export WORK=/root/film                         # venv, project, plates and renders go here (default ./work)

bash setup.sh /root/effectcraft-cli.tar.gz     # or: EFFECTCRAFT_CLI=/path/to/effectcraft-cli bash setup.sh
                                               # FONTS=/root/fonts for your own Manrope V5 OTFs (the film's font files)
CARDS_SRC=/root/my-images bash prep.sh         # icons, crew cards, your cards, the word-reel backdrop
bash plates.sh                                 # Blender + pixel grid; one stage: bash plates.sh slate
bash ad.sh                                     # the EffectCraft project; a few beats: bash ad.sh beat4,beat5
bash deliver_ad.sh v1                          # the clip + strips + frame sheet + hue checks in $WORK/out/ad/v1
"$WORK/venv/bin/python" sfx.py --out "$WORK/out/audio"   # the sound track (also fine on a laptop)
bash mux.sh v1                                 # master, web file, poster, loudness (about -14 LUFS, true peak < -1 dBTP)
```

Fetch `$WORK/out/ad/v1/` and delete the machine right away. Idle GPU time while someone writes code is the expensive
part: build cheap, render in bursts.

Review the sheets, not only the clip: `strip-*.jpg` show every 2nd frame at 60 fps across each transition,
`framesheet.jpg` one frame every 0.25 s. With `REF=/path/to/local.mp4 bash deliver_ad.sh v2 sheets`,
`compare-beat*.jpg` put your frames next to a reference clip at matched times. Timing can be measured against
a reference clip; that clip stays on your own disk and **never enters this repository**. The
`--ref-times` in `deliver_ad.sh` fit that reference only.

## Measured timings

| Job | Time |
|---|---|
| EffectCraft `render frame`, 1080p, simple comp | about 70 ms; a 12-frame contact sheet about 3.5 s |
| Whole film comp build (`ad.sh`) | 14 s |
| Film render, 1050 frames, 6 chunk jobs on 72 CPU cores | about 3 min; with sheets and strips (`deliver_ad.sh`) about 5 min |
| 3D Slate (Cycles 128 spp, 1080p RGBA) | 5 to 6 s per frame; 101 frames about 10 min |
| 3D type "Video!" (96 spp) | about 3 s per frame; 170 frames about 8 min |
| Meadow (2304 x 1296, 64 spp, OIDN, about 1.5 M instances, wind) | about 20 s per frame per process; 3 processes in parallel, 300 frames about 35 min |
| Sound track (`sfx.py`) | about 10 s on a laptop CPU |

One lesson in numbers: an early beat 2 with EffectCraft's Shatter and Temporal Motion Blur took 72 s of wall time and
57 CPU minutes for 156 frames. The Blender plates replaced it.

## Cost

**1.75 $ for the whole film**, three review rounds, all tests and renders included: 2.9 hours of one RTX 4090 at
0.60 $ per hour. A beat of new 3D content costs roughly 0.10 to 0.30 $; a pure EffectCraft insert costs cents.

## Credits

| What | Source | Licence |
|---|---|---|
| Motion engine | EffectCraft (`effectcraft-cli`), the ArtCraft Team and the EffectCraft contributors | MIT OR Apache-2.0 |
| 3D plates | rendered with Blender (used as a tool) | the renders are ours |
| Sky of the meadow | Poly Haven HDRI "Kloofendal 48d Partly Cloudy (Pure Sky)", Greg Zaal and Jarod Guest; downloaded at run time, not in the repository | CC0 |
| Type | Manrope, Mikhail Sharanda | SIL Open Font License 1.1 |
| Sounds and music bed | synthesized by code (`sfx.py`), no recordings or sample packs | MIT |
| Dock icons, white Slate, scripts | drawn and written for Crewcut | MIT |
