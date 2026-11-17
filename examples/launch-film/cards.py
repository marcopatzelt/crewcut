#!/usr/bin/env python3
"""Rounded-corner card PNGs (RGBA) for the grid in beat 4, made from a folder of YOUR images (thumbnails,
screenshots, renders; JPG or PNG). No images ship with the repository: the film used the author's own.

    python3 cards.py SRC_DIR OUT_DIR [width]      (prep.sh runs it with CARDS_SRC)"""
import os, sys
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 640
os.makedirs(out, exist_ok=True)
for f in sorted(os.listdir(src)):
    if not f.lower().endswith((".jpg", ".png")): continue
    im = Image.open(os.path.join(src, f)).convert("RGB")
    h = round(im.height * W / im.width); im = im.resize((W, h), Image.LANCZOS)
    r = round(W * 0.05)
    m = Image.new("L", (W * 4, h * 4), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, W * 4 - 1, h * 4 - 1], radius=r * 4, fill=255)
    m = m.resize((W, h), Image.LANCZOS)
    o = im.convert("RGBA"); o.putalpha(m); o.save(os.path.join(out, os.path.splitext(f)[0] + ".png"))
    print(f, W, h)
