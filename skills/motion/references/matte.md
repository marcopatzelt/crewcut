# Behind the speaker

A graphic can sit **behind** the speaker: a big word behind the shoulders, a chart behind the head. That needs a
person matte (an alpha picture per frame) of the user's footage. A bad matte is worse than none: a light rim around
the hair or a hard cut-out edge looks cheap at once. So every matte passes an edge gate, and when it fails, the graphic
goes **beside** the speaker on its own. Full technical detail: `docs/motion-matte.md`.

## When to ask for it

- Only when "behind" carries the idea: a word that is bigger than the person, a world the speaker stands in, depth
  that a flat overlay cannot give. Not for decoration, not more than once or twice per video.
- The shot suits it: head and shoulders, a calm background, the speaker not leaving the frame. A desk edge or a
  microphone in front of the body usually fails the "frame edges" check.
- Write it into the motion plan row (column b or c) with its cost; the plan entry gets `"layer": "behind"`.
- Design the graphic so that it **also works beside the speaker**: the fallback uses the same comp, placed on the free
  side (`CC.frame().side`).

## What runs where

| Step | Where | What |
|---|---|---|
| Cut the picture of the shot | here | the span plus 0.5 s before and after, one video stream, no sound, no metadata, into `<episode>/render/matte/<shot>.mp4` |
| Separate the speaker | one rented RTX 4090 | RobustVideoMatting (GPL-3.0), downloaded on the machine at a pinned commit and run as its own program; Crewcut sends a command line and fetches PNGs, it never ships or imports the model's code |
| Edge gate, 200 % crops, the decision | here | numpy and Pillow; light work |
| Speaker picture, graphic, person on top | here | ffmpeg; the person covers the speaker picture exactly, same crop, size and position |

`crewcut render matte` runs the steps (the parts: `python -m crewcut.motion.matte_cli export|run|check`, see the doc).

## What goes to the rented machine

Only the picture of each shot, and only after a `spend` card that names each clip by its checksum and says in plain
words: "The picture of shot s03, 4.2 s, without sound, goes to the rented machine to separate the speaker from the
background; it is deleted with the machine. Nothing else from the recording goes up." Never the sound, the camera
originals, transcripts, other videos, keys or the studio state. On the machine, clips and frames are deleted as soon as
the model has run; the machine is destroyed when the session ends.

## The gate

Every 10th frame (and the one after it, for flicker) is measured. `check/edge-check.json` holds every number;
`check/edges-200.jpg` shows hair top, left and right shoulder at 200 % over grey and over a saturated blue.

| Check | Fails when |
|---|---|
| halo | more than 10 % of the rim is brighter than both the person and the ground: old background shining through |
| hard edge | the contour is a binary cut-out: more than 60 % overall, or 30 % in the hair |
| frame edges | the matte stops short of a frame border the body runs into, or shows a long straight edge inside the picture |
| flicker | the edge changes while the picture stands still |
| coverage | the person covers under 3 % or over 85 % of the frame |
| size | the matte is not exactly the picture's size: the person would be shrunk or moved, a floating cut-out |

The limits are first settings, measured on synthetic pictures; they are adjusted on real footage. Look at
`edges-200.jpg` yourself before the first real episode with a matte goes out, and put it in front of the Critic.

## The fallback

`decision.json` per shot says `"behind"` (every check passed) or `"beside"` with the reason (each failed check in one
sentence) and the side with more room next to the face. Nothing waits for a person: the graphic is placed beside the
speaker automatically and the plan output names the reason. Tell the user in one line on the preview card: "m4 went
beside the speaker: the hair edge had a light rim."

## Cost

One RTX 4090 at the usual cap; the setup (torch, the model, the checkpoint) once per machine, then per shot: upload,
decode, matte, fetch. A few short shots should stay well under $0.50; the first real run measures it. Batch every
matte of a video into one rental, together with the plates when possible (`cost.md`).
