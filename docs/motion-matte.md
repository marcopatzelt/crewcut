# Behind the speaker

A graphic can sit **behind** the speaker: a big word behind the shoulders, a chart behind the head. For that, Crewcut
needs a matte of the speaker (an alpha picture per frame: 1 = person, 0 = background, values between for hair and soft
edges). The matte comes from a video matting model on a rented GPU. A gate on this machine checks its edges. If the
edges are not clean, the graphic goes **beside** the speaker instead, on its own, and the reason is recorded.

Code: `crewcut/motion/matte.py` (functions), `crewcut/motion/matte_cli.py` (command line). Tests:
`tests/motion/test_matte.py`, `tests/compute/test_compute_picture.py`.

## What runs where

| Step | Where | Program |
|---|---|---|
| Cut the picture of the shot | this machine | ffmpeg: `export_shot` |
| Separate the speaker from the background | one rented RTX 4090 | RobustVideoMatting, its own `inference.py` |
| Edge check, 200 % crops, decision | this machine | numpy and Pillow: `edge_check`, `decide` |
| Speaker picture, graphic, person on top | this machine | ffmpeg: `composite_graph`, `composite_args` |

The matting never runs on this machine. The edge check reads every 10th frame (and the frame after it) of the clip and
the matte; it is light.

## What goes to the rented machine, and what never does

Goes up, only after a yes:

- the picture of each shot: a clip that Crewcut itself cut into `<episode>/render/matte/<shot>.mp4`. It holds one
  video stream and nothing else: no sound, no subtitles, no data, no metadata (no camera or location tags). The span
  plus 0.5 s before and after (a whole number of frames), so the model settles before the span starts.

Never goes up, also in this session:

- sound, the camera originals, `originals/`, `audio/`, `inbox/`, `broll/`, `export/`, `work/` (transcripts),
  any other video or audio file, the studio state, keys. The general rules in [compute.md](compute.md#privacy) stay.

The rule lives in `crewcut/compute/privacy.py`. A video file passes only when all of these hold:

1. it lies directly in an episode's `render/matte/` folder;
2. ffprobe finds exactly one video stream and nothing else;
3. its sha256 is named on an **accepted spend card of the running compute session**, and that card says in plain words:

   > The picture of shot s03, 4.2 s, without sound, goes to the rented machine to separate the speaker from the
   > background; it is deleted with the machine. Nothing else from the recording goes up.

The session makes that card itself (`compute.session(..., picture={"files": [...]})`). Inside an approved budget, where
renting needs no new card, it still makes one for the picture (it adds no money to the budget). A yes for other files
does not count: the card names each clip by its sha256.

On the machine, the clip and its decoded frames are deleted as soon as RVM has run (`trap ... EXIT`), the results are
deleted after the fetch, and the machine itself is deleted when the session ends (and by its watchdog and the local
guard, as for every rental).

## The model: RobustVideoMatting

[RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) (RVM) is a recurrent video matting model: it
carries information from frame to frame, so the matte is stable over time and needs no green screen and no first-frame
mask. MatAnyone is not used: its S-Lab licence does not allow commercial use.

**Licence.** RVM's code is GPL-3.0. Crewcut is MIT. So Crewcut does not ship RVM, does not copy its code and never
imports it. The rented machine downloads RVM and runs RVM's own `inference.py` as a separate program over SSH; Crewcut
only sends a command line and fetches PNG files. The pin:

| What | Value |
|---|---|
| Repository | `https://github.com/PeterL1n/RobustVideoMatting.git` |
| Commit | `53d74c6826735f01f4406b5ca9075eee27bec094` (master, 13 Mar 2023) |
| Checkpoint | `rvm_resnet50.pth` from release v1.0.0, 107 905 875 bytes |
| Checkpoint sha256 | `c191a807251164c073dce5fa408e7a816070d539b882b2a3150330a9fec112ce` |
| Python packages | `torch==2.5.1`, `torchvision==0.20.1` (CUDA 12.4 index), `numpy==1.26.4`, `av==12.3.0`, `pims==0.7`, `tqdm==4.67.1` |

**Settings.** Variant `resnet50`: the larger model, which RVM describes as slightly better than `mobilenetv3`; on an
RTX 4090 the speed difference does not matter for short inserts. Downsample ratio: the first model stage sees 768 px on the long side, so **0.4 at 1920x1080** (and 1080x1920), 0.6 at 1280x720, 0.2 at 3840x2160; the second stage refines at full resolution. RVM's guide suggests about 480 px (0.25 at 1080p) for head-and-shoulders shots; on a real 1080p shot with curly hair in front of a light wall (17 Nov 2026) 0.25 left small dark specks outside the shoulder edge, 0.4 removed them and kept finer strands at the same flicker. `--seq-chunk 12` (RVM's example value). Input is a PNG sequence that ffmpeg
decodes on the machine, so RVM's video reader (PyAV, pims) is only imported, not used.

### The remote commands

`remote_commands(jobs)` builds every command as one `bash -c '...'` string (unit-tested, `bash -n` checked):

1. **setup** (once per machine): install `git curl ffmpeg python3 python3-venv` when missing; clone RVM and check out
   the pinned commit (stop if `HEAD` differs); download the checkpoint and check its sha256 (stop if wrong); make a
   venv in `/opt/rvm/venv`; `pip install` the packages above; check that torch sees CUDA and that RVM's modules import.
   Prints `MATTE_SETUP_OK`.
2. **matte** (per shot): decode `/work/matte/in/<shot>.mp4` to PNGs, run

   ```
   /opt/rvm/venv/bin/python inference.py --variant resnet50 --checkpoint /opt/rvm/rvm_resnet50.pth --device cuda \
     --input-source /work/matte/frames/<shot> --downsample-ratio 0.4 --output-type png_sequence \
     --output-alpha /work/matte/out/<shot>/pha --output-foreground /work/matte/out/<shot>/fgr --seq-chunk 12 \
     --disable-progress
   ```

   check that alpha and foreground have as many frames as the clip, delete the clip and the frames, print
   `MATTE_OK <shot> <frames>`.
3. **clean** (per shot, after the fetch): delete `/work/matte/out/<shot>`.
4. **wipe**: delete `/work/matte`.

The session's own setup runs with `--blender none`: this job needs no Blender.

Output per shot in `<episode>/render/matte/<shot>/`: `pha/0000.png ...` (8-bit gray alpha), `fgr/0000.png ...` (RGB
foreground: RVM's estimate of the person's colours, with the old background removed from mixed edge pixels).

## The gate

`edge_check(frames_dir, alpha_dir, out_dir, face)` measures every 10th frame (and the next one, for flicker) and writes
`check/edge-check.json` with every number, `check/crops/*.png` and `check/edges-200.jpg`. All limits are in one dict,
`THRESHOLDS`, with a comment each. Pixel sizes are for 1080 lines and grow with taller pictures.

| Check | What is measured | Fails when |
|---|---|---|
| halo | The picture with the matte over a dark ground (4 % grey) and over a saturated blue. In the rim (3 px around the 0.5 alpha contour), a pixel is "bright" when its luminance is more than 0.20 above both the person just inside (4 to 10 px inside, averaged locally) and the ground: old background shining through. | more than 10 % of the rim is bright in any checked frame |
| hard edge | Contour pixels that are opaque (alpha >= 0.98) right next to a fully clear pixel (<= 0.02): a binary cut-out. Overall, and in the hair zone (above the top quarter of the face box, or the top 12 % of the picture under the head). | more than 60 % overall or 30 % in the hair, in any checked frame |
| frame edges | (1) Where the body runs towards a frame border, the border line must hold at least half the coverage of the lines 4 to 8 px inside; and a matte that ends abruptly (as wide as further in) within 15 % of the picture before a border counts as stopping short. (2) No straight horizontal or vertical matte edge inside the picture longer than 6 % of the width (height), at least 12 px. | either, in any checked frame |
| flicker | Between a frame and the next: mean absolute alpha change within 3 px of the contour, weighted by how still the picture is there (weight 1 where the picture did not change, 0 where it changed by 6 % or more). A matte that follows the speaker's movement scores near 0; one that changes while the picture stands still scores high. The plain ratio "alpha change / picture change" is listed too. | mean over the pairs above 0.05 |
| coverage | The person's share of the frame. | below 3 % (empty matte) or above 85 % (full-frame matte) |
| size | The matte must have exactly the picture's size: the person sits on the speaker 1:1. | any other size |

On synthetic pictures (a head with a noisy soft hair edge, shoulders out of the bottom of the frame, a light wall) a
correct soft matte scores halo 0 %, hard edge under 1 %, flicker 0.003. A matte grown 3 px over a white wall scores
halo about 55 %; a binary matte hard edge 100 %; a matte cut 20 px above the bottom a 20 px border gap and a 147 px
straight edge; a matte that shrinks every other frame flicker about 0.2. Dark hair on a white wall with a correct
matte peaks near 0.16 above the person in mixed pixels, under the 0.20 limit. **These limits are first settings:
measure them on real footage and adjust `THRESHOLDS`.**

**200 % crops for a person.** Hair top, left shoulder, right shoulder, each over mid grey and over the saturated blue,
scaled 2x with nearest neighbour (every source pixel is a 2x2 block), from the frame with the worst halo; side by side
in `edges-200.jpg`. Look at them before the first real episode goes out.

## The fallback: beside the speaker

`decide(check)` returns `"behind"` when every check passed. Otherwise it returns `"beside"`, with `.reason` (every
failed check in one sentence each) and `.side`: the side of the frame with more room next to the face (or next to the
person, without a face box). `write_decision()` stores it as `render/matte/<shot>/decision.json`. `matte_rented` does
this for every shot after the machine is gone; a shot whose matte failed on the machine, or whose check could not run,
also goes beside with that reason. Nothing waits for a person: the fallback is automatic.

## The composite

`composite_graph(place, fps)` gives the ffmpeg filter graph for one insert span, in this order:

1. the speaker picture, with the cut's crop, size and position (`Place`);
2. the graphic (RGBA, output frame size, at 0:0);
3. the person: RVM's foreground with RVM's alpha (`alphamerge`), with **the same** crop, size and position as the
   speaker picture. The person is never scaled down or moved: it covers the speaker picture exactly.

`composite_args(speaker, graphic, matte_dir, start_s, end_s, clip_start_s, fps, place, out)` adds the inputs: the
speaker from `start_s`, the graphic (an RGBA video, a PNG sequence with `%`, or a looping still), and the PNG sequences
from frame `round((start_s - clip_start_s) * fps)`. Spans should start on a frame boundary of the episode's rate (the
export margin is a whole number of frames, so the matte lines up frame by frame). The alpha is scaled with bicubic
(same geometry as the picture, no ringing at hard edges).

## Command line

```
python -m crewcut.motion.matte_cli export <source> --episode ID --id SHOT --start S --end E [--fps N] [--face X,Y,W,H]
python -m crewcut.motion.matte_cli run --episode ID --shots SHOT[,SHOT] --cap USD [--minutes 45] [--every N] [--no-check]
python -m crewcut.motion.matte_cli check --episode ID --id SHOT [--face X,Y,W,H] [--every N] [--keep-frames]
python -m crewcut.motion.matte_cli check --frames DIR --alpha DIR --out DIR [--face X,Y,W,H] [--every N]
```

`--json` on each. Exit codes: 0 ok (also when the gate decides "beside"), 1 error, 2 usage, 3 waiting for the spend
card or refused (cap, rights, privacy), 4 missing key.

## Cost

One RTX 4090 at the usual cap of $0.60 per hour (often $0.30 to $0.45), deleted when the session ends.

| Part | Time | Note |
|---|---|---|
| Boot, SSH, probe, Crewcut setup without Blender | a few minutes | as for every rental |
| Matte setup: torch with CUDA (about 2.5 GB of packages), RVM, checkpoint (108 MB) | measure | once per machine |
| Per shot: upload, decode, RVM, fetch | measure | RVM itself is fast on a 4090; writing and fetching PNGs dominates |

A run with a few short inserts should stay well under $0.50; measure it on the first real run. Traffic: the clip goes
up (H.264 at CRF 10, roughly 10 MB per second of 1080p picture, measure), and alpha plus foreground PNGs come down
(the foreground PNGs are a few MB per 1080p frame, so about 1 GB per 12 s shot at 25 fps; measure). Vast bills network
traffic separately on some hosts.

## Untested on a real machine

- The whole remote sequence on a real rented RTX 4090: package versions with the host's driver, the image's Python
  (the fallback image has Python 3.10; Python 3.13 has no wheel for numpy 1.26.4), the download times, RVM's output
  names and bit depth.
- The gate's limits on real RVM mattes of real speakers (hair against bright walls, glasses, hands, a desk edge in
  front of the speaker: a straight desk edge fails "frame edges" and sends the graphic beside).
- Frame alignment between the speaker picture in the cut and the matte on sources with a variable frame rate.

## First real test (17 Nov 2026)

One 6-second 1080p25 head-and-shoulders shot (curly hair, light wall, hands moving), RTX 4090, RVM resnet50, 174
frames in under a minute on the GPU (setup with the torch download about 3 minutes).

| Ratio | Halo (worst, limit 0.10) | Hard edge | Frame edges | Flicker (mean, limit 0.05) | Gate |
|---|---|---|---|---|---|
| 0.25 | 0.006 | 0.0 | pass | 0.0502 | beside (flicker) |
| 0.4 | 0.004 | 0.0004 | pass | 0.0499 | behind |

At 200 % the shoulders are clean at 0.4; the hair over a graphic shows no bright rim, but over a flat test ground
(the crops of `edges-200.jpg`, made from the original picture) a faint light fringe from the bright background
stays in the finest strands. The flicker value sits on the limit for both ratios: the limit is calibrated on drawn
pictures and one real shot. It needs more real shots (and a person looking at the 200 % crops) before it can be
called right; until then the gate decides close cases with little margin.
