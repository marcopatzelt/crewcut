"""3D scene "scale": a balance. Left, a stack of sheets; right, accent blocks drop into the pan one by one until that
side goes down ("A outweighs B").
Data: {format, frames, word, sub, count, cues: {word: frame}}. Keys: templates/3d/README.md.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage import *  # noqa: E402,F403

D = data(frames=110, word="Compute", sub="beats rules by hand", count=3, cues={"word": 60})  # noqa: F405
PORTRAIT = D["format"] == "portrait"
WB = int(D["cues"]["word"])
NB = max(1, min(6, int(D["count"])))
sc = bpy.context.scene  # noqa: F405
clear()  # noqa: F405
stage(sc)  # noqa: F405
lights((0, 0, 0.3))  # noqa: F405

ARM, PIVOT, HANG, PAN = 0.26, 0.48, 0.19, 0.11     # half beam, pivot height, pan below the beam, pan radius
cylinder(0.11, 0.024, (0, 0, 0.012), BASE, bevel=0.005)  # noqa: F405
cylinder(0.065, 0.02, (0, 0, 0.034), BASE_DEEP, bevel=0.004)  # noqa: F405
cylinder(0.015, PIVOT - 0.04, (0, 0, 0.04 + (PIVOT - 0.04) / 2), BASE, bevel=0.003)  # noqa: F405
beam = empty((0, 0, PIVOT))  # noqa: F405
box((2 * ARM + 0.05, 0.032, 0.028), (0, 0, 0), BASE, bevel=0.006, seg=3, parent=beam)  # noqa: F405
cylinder(0.028, 0.048, (0, 0, 0), ACCENT_GLOSS, rot=(math.radians(90), 0, 0), parent=beam, bevel=0.004)  # noqa: F405


def pan():
    e = empty()  # noqa: F405
    cylinder(0.005, HANG, (0, 0, -HANG / 2), BASE_DEEP, parent=e, bevel=0)  # noqa: F405
    cylinder(PAN, 0.013, (0, 0, -HANG), BASE, parent=e, bevel=0.004, verts=96)  # noqa: F405
    cylinder(0.011, 0.011, (0, 0, 0), BASE_DEEP, rot=(math.radians(90), 0, 0), parent=e, bevel=0.002)  # noqa: F405
    return e


LEFT, RIGHT = pan(), pan()
for i in range(5):                                            # left: sheets stacked by hand
    s = sheet(0.14, 0.19, 0.011)  # noqa: F405
    s.parent = LEFT
    s.location = (0.004 * (i % 2), 0.003 * i, -HANG + 0.012 + i * 0.0125)
    s.rotation_euler = (0, 0, math.radians((-8, 6, -3, 10, -12)[i]))
BS = 0.07                                                     # block edge
BLOCKS = []
for i in range(NB):
    b = box((BS, BS, BS), (0, 0, 0), ACCENT, bevel=0.008, seg=4)  # noqa: F405
    b.parent = RIGHT
    b.rotation_euler = (0, 0, math.radians((10, -14, 6, -8, 12, -4)[i % 6]))
    BLOCKS.append(b)
LAND = [WB - 2 - (NB - 1 - i) * 9 for i in range(NB)]        # the last block lands just before the word

if PORTRAIT:
    CAM, TGT = Vector((0.0, -4.1, 1.15)), Vector((0, 0, 0.34))  # noqa: F405
    TU, TV, TW, SV, SW = 0.0, 0.6, 0.6, 0.47, 0.6
else:
    CAM, TGT = Vector((-0.3, -3.0, 0.9)), Vector((-0.3, 0, 0.32))  # noqa: F405
    TU, TV, TW, SV, SW = -0.52, 0.13, 0.28, -0.08, 0.28
cam = camera(sc, CAM, TGT, lens=80, fstop=4.0, portrait=PORTRAIT)  # noqa: F405
FOCUS = (Vector((0, 0, 0.3)) - CAM).length  # noqa: F405
cam.data.dof.focus_distance = FOCUS
FONT = load_font()  # noqa: F405
T1 = text(cam, D["word"], TU, TV, FOCUS + 0.15, TW, FONT, max_height=None if PORTRAIT else 0.15)  # noqa: F405
T2 = text(cam, D["sub"], TU, SV, FOCUS + 0.15, SW, FONT, max_height=None if PORTRAIT else 0.07) if D["sub"] else None  # noqa: F405
drift = decor(cam)  # noqa: F405
W0, STEP = math.radians(-9), math.radians(24) / NB


def angle(fr):
    w = W0 + (math.radians(1.0) * math.sin(fr * 0.2) if fr < LAND[0] else 0.0)    # before: the beam sways a little
    for land in LAND:
        if fr >= land:
            d = (fr - land) / D["fps"]
            w += STEP * (1 - math.exp(-d * 6) * math.cos(d * 12))                   # each block pushes, then settles
    return w


def pose(fr):
    t = fr / D["fps"]
    cam.location = CAM + Vector((0, 0.01 * t, 0))  # noqa: F405
    bpy.context.view_layer.update()  # noqa: F405
    drift(t)
    show_text(T1, (fr - WB) / ENTER)  # noqa: F405
    if T2:
        show_text(T2, (fr - WB - ENTER) / ENTER)  # noqa: F405
    w = angle(fr)
    beam.rotation_euler = (0, w, 0)
    LEFT.location = (-ARM * math.cos(w), 0, PIVOT + ARM * math.sin(w))
    RIGHT.location = (ARM * math.cos(w), 0, PIVOT - ARM * math.sin(w))
    for i, b in enumerate(BLOCKS):
        p = (fr - (LAND[i] - 9)) / 9
        if p < 0:
            b.location = (0, 0, 3)                                   # above the frame
            continue
        p = min(1.0, p)
        rest = Vector((0.008 * (i % 2) - 0.004, 0.006 * ((i + 1) % 2), -HANG + 0.007 + BS / 2 + i * (BS + 0.001)))  # noqa: F405
        b.location = rest + Vector((0, 0, 0.7 * (1 - p * p)))  # noqa: F405


run(sc, pose, D, still=WB + 12)  # noqa: F405
