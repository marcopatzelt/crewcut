#!/usr/bin/env python3
"""Pixel-grid plates for the click in beat 2: squares on a FIXED grid that switch on and off as a wave running
outwards from the click. Nothing flies.

  python3 pixelgrid.py --out DIR [--cx 960 --cy 540] [--color 0f6e5c] [--cell 54] [--frames 40] [--seed 7]

Writes two RGBA sequences (60 fps, straight alpha); frame 1 = 3 frames after the click (comp time 0.97):
  DIR/outline_0001.png ...  outlined squares (brand colour, some white) -> put them UNDER the disc and the rings
  DIR/fill_0001.png ...     filled squares, white at 8-20 % -> OVER the rings, UNDER the centre disc and the logo
"""
import argparse
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

a = argparse.ArgumentParser()
a.add_argument("--out", required=True); a.add_argument("--cx", type=float, default=960); a.add_argument("--cy", type=float, default=540)
a.add_argument("--color", default="0f6e5c"); a.add_argument("--cell", type=int, default=54); a.add_argument("--frames", type=int, default=40)
a.add_argument("--seed", type=int, default=7); a.add_argument("--w", type=int, default=1920); a.add_argument("--h", type=int, default=1080)
A = a.parse_args()
os.makedirs(A.out, exist_ok=True)
col = tuple(int(A.color[i:i + 2], 16) for i in (0, 2, 4))
C, W, H = A.cell, A.w, A.h
ox, oy = (A.cx - C / 2) % C - C, (A.cy - C / 2) % C - C          # the click sits in the middle of a cell
cells = [(i, j, ox + i * C, oy + j * C) for j in range(H // C + 3) for i in range(W // C + 3)]


def rnd(*k):
    return random.Random(repr((A.seed,) + k)).random()


def front(f):                       # radius of the wave in px; past the frame edge after 12 frames (0.2 s)
    return 70 + 1150 * (max(f, 0) / 12.0) ** 1.3


BAND = 300.0
for f in range(A.frames):
    R = front(f)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0)); do = ImageDraw.Draw(out)
    fil = Image.new("RGBA", (W, H), (0, 0, 0, 0)); df = ImageDraw.Draw(fil)
    for i, j, x, y in cells:
        d = math.hypot(x + C / 2 - A.cx, y + C / 2 - A.cy)
        behind = R - d                                              # > 0: the wave has already passed
        if 0 <= behind <= BAND:
            dens = 0.60 * (1 - behind / BAND) ** 0.7 * (0.35 + 0.65 * min(1.0, 260.0 / max(d, 1)) ** 0.5)
            if rnd(i, j, f // 2) < dens:                            # flicker: a new choice every 2 frames
                white = rnd(i, j, "w") < 0.14
                c = (255, 255, 255) if white else col
                al = int(255 * (0.55 + 0.4 * rnd(i, j, "a")))
                do.rectangle([x + 1, y + 1, x + C - 2, y + C - 2], outline=c + (al,), width=3)
        if behind > BAND * 0.4 and rnd(i, j, "f") < 0.13:           # filled cells stay for a moment
            age = f - (12.0 * ((d + BAND * 0.4 - 70) / 1150.0) ** (1 / 1.3) if d + BAND * 0.4 > 70 else 0)
            life = 14 + 18 * rnd(i, j, "l")
            k = 1 - age / life
            if k > 0:
                df.rectangle([x, y, x + C - 1, y + C - 1], fill=(255, 255, 255, int(255 * (0.08 + 0.12 * rnd(i, j, "o")) * min(1.0, k * 2))))
    glow = out.filter(ImageFilter.GaussianBlur(5))
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.45)))
    out = Image.alpha_composite(glow, out)
    out.save(os.path.join(A.out, f"outline_{f + 1:04d}.png")); fil.save(os.path.join(A.out, f"fill_{f + 1:04d}.png"))
print("ok", A.frames, "frames in", A.out)
