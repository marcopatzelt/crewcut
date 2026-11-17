#!/usr/bin/env python3
"""Pastel crew cards (avatars on soft tiles), rounded RGBA PNGs named crew-<name>.png, from a folder of SVG avatars
you supply. The film used Crewcut's crew avatars from docs/brand/crew (prep.sh's default). Needs rsvg-convert.

    python3 crewcards.py CREW_SVG_DIR OUT_DIR"""
import os, sys, subprocess
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
tiles = ["#FFD9C2", "#FFEBA8", "#D9CCFF", "#BFE3FF", "#FFC9D9", "#CDEFD9", "#FFE0B8", "#D4E8FF"]
W, H = 640, 800
for i, f in enumerate(sorted(x for x in os.listdir(src) if x.endswith(".svg"))):
    png = os.path.join(out, "_" + f.replace(".svg", ".png"))
    subprocess.run(["rsvg-convert", "-w", "420", os.path.join(src, f), "-o", png], check=True)
    av = Image.open(png).convert("RGBA")
    c = tiles[i % len(tiles)]; rgb = tuple(int(c[k:k + 2], 16) for k in (1, 3, 5))
    card = Image.new("RGBA", (W, H), rgb + (255,))
    g = Image.new("RGBA", (W, H), (255, 255, 255, 0)); d = ImageDraw.Draw(g)
    for y in range(H): d.line([(0, y), (W, y)], fill=(255, 255, 255, int(70 * (1 - y / H))))
    card = Image.alpha_composite(card, g)
    card.alpha_composite(av, ((W - av.width) // 2, (H - av.height) // 2 + 20))
    m = Image.new("L", (W * 4, H * 4), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=32 * 4, fill=255)
    card.putalpha(m.resize((W, H), Image.LANCZOS)); card.save(os.path.join(out, "crew-" + f.replace(".svg", ".png"))); os.remove(png)
    print(f)
