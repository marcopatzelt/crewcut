"""3D scene "box": an accent ball in a box made of sheets, and a word.

action "open":   the box folds open, the lid flies off, the ball grows to full size ("without limits").
action "closed": the walls close in, the lid drops, the ball is pressed small ("held back").
Data: {format, frames, word, sub, action, cues: {word: frame}}. Keys: templates/3d/README.md.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage import *  # noqa: E402,F403

D = data(frames=90, word="Without limits", sub=None, action="open", cues={"word": 30})  # noqa: F405
PORTRAIT = D["format"] == "portrait"
WB = int(D["cues"]["word"])
OPEN = D["action"] != "closed"
sc = bpy.context.scene  # noqa: F405
clear()  # noqa: F405
stage(sc)  # noqa: F405
lights((0, 0, 0.16))  # noqa: F405

S, TH = 0.25, 0.013              # box edge, sheet thickness
R_SMALL, R_BIG = 0.1, 0.185      # ball radius pressed and free
ball = sphere(1.0, (0, 0, 0), ACCENT_GLOSS)  # noqa: F405


def wall(loc, rot_z):
    """A sheet standing on a hinge at its lower edge, so it can fold outward."""
    h = empty(loc)  # noqa: F405
    h.rotation_euler = (0, 0, rot_z)
    s = sheet(S, S, TH)  # noqa: F405
    s.parent = h
    s.location = (0, 0, S / 2)
    s.rotation_euler = (math.radians(90), 0, 0)
    return h


box_root = empty()  # noqa: F405
WALLS = [wall((0, S / 2, 0), 0.0), wall((-S / 2, 0, 0), math.radians(90)), wall((S / 2, 0, 0), math.radians(-90))]
NEAR = [(0, S / 2, 0), (-S / 2, 0, 0), (S / 2, 0, 0)]
FAR = [(0, 0.7, 0), (-0.75, 0, 0), (0.75, 0, 0)]
for h in WALLS:
    h.parent = box_root
lid = sheet(S + 0.02, S + 0.02, TH)  # noqa: F405
lid.parent = box_root
box_root.rotation_euler = (0, 0, math.radians(20))     # turned a little, so one sees into the box

if PORTRAIT:
    CAM, TGT = Vector((0.0, -3.5, 1.45)), Vector((0, 0, 0.22))  # noqa: F405
    TU, TV, TW, SV, SW = 0.0, 0.52, 0.6, 0.38, 0.55
else:
    CAM, TGT = Vector((-0.34, -2.4, 1.0)), Vector((-0.34, 0, 0.17))  # noqa: F405
    TU, TV, TW, SV, SW = -0.45, 0.14, 0.32, -0.12, 0.3
cam = camera(sc, CAM, TGT, lens=80, fstop=3.2, portrait=PORTRAIT)  # noqa: F405
FOCUS = (Vector((0, 0, 0.15)) - CAM).length  # noqa: F405
cam.data.dof.focus_distance = FOCUS
TD = FOCUS - 0.1                 # text slightly in front of the sharp plane
FONT = load_font()  # noqa: F405
T1 = text(cam, D["word"], TU, TV, TD, TW, FONT, max_height=None if PORTRAIT else 0.15)  # noqa: F405
T2 = text(cam, D["sub"], TU, SV, TD, SW, FONT, max_height=None if PORTRAIT else 0.07) if D["sub"] else None  # noqa: F405
drift = decor(cam)  # noqa: F405


def pose(fr):
    t = fr / D["fps"]
    cam.location = CAM + Vector((0, 0.012 * t, 0))  # noqa: F405
    bpy.context.view_layer.update()  # noqa: F405
    drift(t)
    show_text(T1, (fr - WB) / ENTER)  # noqa: F405
    if T2:
        show_text(T2, (fr - WB - ENTER) / ENTER)  # noqa: F405
    if OPEN:
        k = (fr - (WB - 8)) / 11
        unfold = spring(k, 1.1) if k > 0 else 0.0  # noqa: F405
        press = 0.02 * math.sin(fr * 1.8) if k <= 0 else 0.0          # before: the ball pushes against the walls
        for h, near in zip(WALLS, NEAR, strict=True):
            h.location = near
            h.rotation_euler[0] = math.radians(-95) * min(1.05, unfold)
        kk = max(0.0, k)
        lid.location = (0.04 * kk, 0.5 * kk * kk + 0.02 * kk, S + TH / 2 + 0.85 * ease(kk / 1.6))  # noqa: F405
        lid.rotation_euler = (-1.2 * min(kk, 2.2), 0.45 * min(kk, 2.2), 0)
        if kk > 2.6:
            lid.location = (0, 0, -5)                                   # gone
        grow = spring((fr - (WB - 6)) / 13, 2.0) if fr > WB - 6 else 0.0  # noqa: F405
        r = R_SMALL * (1 + press) + (R_BIG - R_SMALL) * grow
        squash = 1.0 if k > 0 else 0.88
    else:
        k = ease((fr - (WB - 26)) / 20)  # noqa: F405
        for h, near, far in zip(WALLS, NEAR, FAR, strict=True):
            h.location = Vector(far).lerp(Vector(near), k)  # noqa: F405
            h.rotation_euler[0] = 0
        lid.location = (0, 0, S + TH / 2 + 0.9 * (1 - ease((fr - (WB - 16)) / 14)))  # noqa: F405
        lid.rotation_euler = (0, 0, 0.45 * (1 - k))
        kd = ease((fr - (WB - 18)) / 14)  # noqa: F405
        r = R_BIG + (R_SMALL - R_BIG) * kd + 0.004 * math.sin(fr * 1.8) * kd
        squash = 1 - 0.12 * kd
    wide = (2 - squash) ** 0.5
    ball.scale = (r * wide, r * wide, r * squash)
    ball.location = (0, 0, r * squash + 0.002)


run(sc, pose, D, still=WB + 14)  # noqa: F405
