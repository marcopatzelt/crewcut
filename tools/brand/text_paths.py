#!/usr/bin/env python3
"""Turn the few words of the brand files into SVG paths, so the static files look the same without the font installed.

    uv run --with fonttools python tools/brand/text_paths.py

Font: Inter (SIL Open Font License), from web/node_modules/@fontsource/inter. Writes tools/brand/text-paths.json:
{key: {"d": path at font size 100 with the baseline at y=0, "width": advance width, "cap": cap height}}.
"""
import json
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "web" / "node_modules" / "@fontsource" / "inter" / "files"
TEXTS = {
    "wordmark": ("Crewcut", 800, -0.025),
    "tagline": ("Your Claude Code subscription, now a YouTube crew.", 600, -0.012),
    "subline": ("Seven AI agents take your video from idea to upload. You record and say yes.", 500, -0.005),
}


def shape(text: str, weight: int, tracking: float) -> dict:
    font = TTFont(FONTS / f"inter-latin-{weight}-normal.woff")
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    kern = {}
    if "kern" in font:
        for table in font["kern"].kernTables:
            kern.update(table.kernTable)
    scale = 100 / upm
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    x = 0.0
    prev = None
    for ch in text:
        name = cmap[ord(ch)]
        if prev is not None:
            x += kern.get((prev, name), 0) * scale
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        x += hmtx[name][0] * scale + tracking * 100
        prev = name
    cap = font["OS/2"].sCapHeight * scale
    return {"d": pen.getCommands(), "width": round(x - tracking * 100, 1), "cap": round(cap, 1)}


def main() -> None:
    out = {key: shape(*spec) for key, spec in TEXTS.items()}
    path = Path(__file__).with_name("text-paths.json")
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: " + ", ".join(f"{k} {v['width']}" for k, v in out.items()))


if __name__ == "__main__":
    main()
