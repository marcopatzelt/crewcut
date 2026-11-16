"""3D scene "stack": sheets (documents without text) fall onto a stack, or fly off it, and a word.

action "fall":  the sheets fall one after the other; the last one lands just before the word ("many rules").
action "clear": from the top, sheets fly out of the frame until `keep` are left ("I delete what is not needed").
Data: {format, frames, count, word, sub, action, keep, lead, cues: {word: frame}}. Keys: templates/3d/README.md.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage import *  # noqa: E402,F403

D = data(frames=90, count=10, word="Rules", sub=None, action="fall", keep=3, lead=0, cues={"word": 30})  # noqa: F405
PORTRAIT = D["format"] == "portrait"
WB = int(D["cues"]["word"])
N = max(1, min(30, int(D["count"])))
CLEAR = D["action"] == "clear"
KEEP = max(0, min(N, int(D.get("keep") or 0)))
sc = bpy.context.scene  # noqa: F405
clear()  # noqa: F405
stage(sc)  # noqa: F405
lights((0, 0, 0.1))  # noqa: F405

BX, BY, TH = 0.3, 0.4, 0.016
rnd = random.Random(int(D.get("seed") or 5))
SHEETS = []
for i in range(N):
    s = sheet(BX, BY, TH)  # noqa: F405
    rest = Vector((rnd.uniform(-0.012, 0.012), rnd.uniform(-0.012, 0.012), TH / 2 + i * (TH + 0.0014) + 0.001))  # noqa: F405
    turn = math.radians(rnd.uniform(-10, 10) + (-16 if i == N - 1 else 0))
    SHEETS.append((s, rest, turn))
HEIGHT = N * (TH + 0.0014)

if PORTRAIT:
    CAM, TGT = Vector((0.0, -3.3, 1.5)), Vector((0, 0, 0.15))  # noqa: F405
    TU, TV, TW, SV, SW = 0.0, 0.48, 0.5, 0.3, 0.55
else:
    CAM, TGT = Vector((-0.32, -2.1, 1.05)), Vector((-0.32, 0, 0.13))  # noqa: F405
    TU, TV, TW, SV, SW = -0.46, 0.15, 0.3, -0.12, 0.3
cam = camera(sc, CAM, TGT, lens=80, fstop=3.2, portrait=PORTRAIT)  # noqa: F405
FOCUS = (Vector((0, 0, HEIGHT * 0.6)) - CAM).length  # noqa: F405
cam.data.dof.focus_distance = FOCUS
TD = FOCUS - 0.1                 # seen from above: text behind the sharp plane would sink under the floor
FONT = load_font()  # noqa: F405
T1 = text(cam, D["word"], TU, TV, TD, TW, FONT, max_height=None if PORTRAIT else 0.15)  # noqa: F405
T2 = text(cam, D["sub"], TU, SV, TD, SW, FONT, max_height=None if PORTRAIT else 0.07) if D["sub"] else None  # noqa: F405
drift = decor(cam)  # noqa: F405
STEP = 2.6 if CLEAR else max(2.0, min(4.0, (WB + 6) / N))


def pose(fr):
    t = fr / D["fps"]
    cam.location = CAM + Vector((0, 0.012 * t, 0))  # noqa: F405
    bpy.context.view_layer.update()  # noqa: F405
    drift(t)
    show_text(T1, (fr - WB) / ENTER)  # noqa: F405
    if T2:
        show_text(T2, (fr - WB - ENTER) / ENTER)  # noqa: F405
    for i, (s, rest, turn) in enumerate(SHEETS):
        if not CLEAR:
            start = WB - 4 - (N - 1 - i) * STEP - 8
            p = (fr - start) / 8
            if p < 0:
                s.location = (0, 0, -9)                                  # not yet in the picture
                continue
            p = min(p, 1.0)
            after = max(0.0, (fr - start - 8) / 5)
            bounce = 0.009 * math.sin(min(after, 1.0) * math.pi) if after < 1 else 0.0
            s.location = rest + Vector((0, 0, 0.85 * (1 - p * p) + bounce))  # noqa: F405
            s.rotation_euler = (math.radians(12) * (1 - p), math.radians(-9) * (1 - p), turn + 0.45 * (1 - p))
        else:
            s.location = rest
            s.rotation_euler = (0, 0, turn)
            if i < KEEP:
                continue
            j = N - 1 - i
            start = WB - 6 - int(D.get("lead") or 0) + j * STEP          # lead: frames before the word the first one flies
            q = ease((fr - start) / 12) if fr >= start else 0.0  # noqa: F405
            if q > 0:
                s.location = rest + Vector((1.4 * q * q + 0.1 * q, 0.3 * q, 0.5 * q))  # noqa: F405
                s.rotation_euler = (0.45 * q, -0.85 * q, turn + 1.2 * q)


run(sc, pose, D, still=WB + 20)  # noqa: F405
