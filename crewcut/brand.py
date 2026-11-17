"""The style pack: the user's taste as data (brand/), or the neutral default (packs/neutral/).

Skills and tools read every colour, font, loudness and limit from here, never from code.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths

PACK_FILES = {
    "brand": "brand.json",
    "edit_style": "edit-style.json",
    "channel": "channel.json",
    "thumbnail": "thumbnail.json",
    "baseline": "baseline.json",
}

_RULE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.+?)\s*(?:\((?:source|Source):\s*(.+)\))?\s*$")


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def parse_rules(text: str) -> list[dict]:
    """Parse a rules/<step>.md file: '- 2026-11-11: rule text (source: ...)' per item."""
    out = []
    for line in text.splitlines():
        m = _RULE.match(line)
        if m:
            out.append({"date": m.group(1), "rule": m.group(2).strip(), "source": (m.group(3) or "").strip()})
    return out


def format_rule(date: str, rule: str, source: str) -> str:
    rule = " ".join(rule.split())
    source = " ".join(source.split())
    return f"- {date}: {rule} (source: {source})" if source else f"- {date}: {rule}"


# ---- colours in OKLCH (pure Python) --------------------------------------------------------------------------------
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_oklch(h: str) -> tuple[float, float, float]:
    """#RRGGBB -> (L 0..1, C, hue in degrees 0..360) in OKLCH (Björn Ottosson's OKLab)."""
    r, g, b = (_to_linear(int(h.lstrip("#")[i:i + 2], 16) / 255) for i in (0, 2, 4))
    lms = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
           0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def _oklch_linear(L: float, C: float, H: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
            -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
            -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc)


def oklch_to_hex(L: float, C: float, H: float) -> str:
    """OKLCH -> #RRGGBB. Outside the sRGB gamut the chroma is lowered (same lightness and hue) until it fits."""
    def inside(c: float) -> bool:
        return all(-1e-6 <= v <= 1 + 1e-6 for v in _oklch_linear(L, c, H))
    if not inside(C):
        lo, hi = 0.0, C
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if inside(mid) else (lo, mid)
        C = lo
    rgb = (min(1.0, max(0.0, _to_srgb(min(1.0, max(0.0, v))))) for v in _oklch_linear(L, C, H))
    return "#" + "".join(f"{round(v * 255):02X}" for v in rgb)


def derive_palette(accent: str) -> list[str]:
    """Four content colours from the accent: the accent, its complement and the two neighbours at +-40 degrees of
    hue, all at the accent's lightness and chroma in OKLCH (chroma lowered only where sRGB cannot show it)."""
    L, C, H = hex_to_oklch(accent)
    return ["#" + accent.lstrip("#").upper()] + [oklch_to_hex(L, C, (H + d) % 360) for d in (180, 40, -40)]


def pastel(color: str) -> str:
    """A light version of a colour (same hue in OKLCH) for grounds and gradients."""
    _, C, H = hex_to_oklch(color)
    return oklch_to_hex(0.93, min(0.05, C * 0.4), H)


MOTION_GRAPHICS = {          # brand.json motion_graphics: the defaults (palette null = derived from colors.accent)
    "palette": None, "pastels": True, "ground": "soft", "ink": None, "glass": True,
    "enter_s": 0.4, "exit_s": 0.25, "ease": "expo", "drift_pct_per_s": 2.0,
    "blur": {"shutter": 180, "samples": 16},
    "plate3d": {"material": "glossy", "bevel": 0.05, "extrude": 0.2},
}
EASES = ("linear", "easy", "smooth", "strong", "out", "expo", "in", "expoIn", "soft", "snap")   # EC.EASES in ec_lib.jsx


@dataclass
class Pack:
    dir: Path
    is_neutral: bool
    brand: dict = field(default_factory=dict)
    edit_style: dict = field(default_factory=dict)
    channel: dict = field(default_factory=dict)
    thumbnail: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    voice: str = ""

    def value(self, dotted: str, default: Any = None) -> Any:
        """Dotted lookup: 'edit_style.loudness_lufs', 'brand.colors.accent'. None counts as missing."""
        head, _, rest = dotted.partition(".")
        cur: Any = getattr(self, head, None)
        if not rest:
            return default if cur is None else cur
        for part in rest.split("."):
            if not isinstance(cur, dict) or cur.get(part) is None:
                return default
            cur = cur[part]
        return cur

    def source_of(self, dotted: str) -> str | None:
        """Where a value came from ('from your website, 16 Nov 2026'), if the pack says so."""
        head, _, rest = dotted.partition(".")
        d = getattr(self, head, None)
        if not isinstance(d, dict):
            return None
        return (d.get("sources") or {}).get(rest)

    def rules(self, step: str) -> list[dict]:
        p = self.dir / "rules" / f"{step}.md"
        return parse_rules(p.read_text(encoding="utf-8")) if p.is_file() else []

    def all_rules(self) -> dict[str, list[dict]]:
        d = self.dir / "rules"
        if not d.is_dir():
            return {}
        return {p.stem: parse_rules(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.md"))}

    def file(self, rel: str | None) -> Path | None:
        """A file named in the pack (logo, font, reference photo), resolved inside the pack folder."""
        if not rel:
            return None
        p = paths.inside(self.dir, rel)
        return p if p.exists() else None

    # ---- renderer tokens ------------------------------------------------------------------------------------
    def css_vars(self) -> dict[str, str]:
        """CSS custom properties for the 2D templates (templates/2d)."""
        b = self.brand
        c = b.get("colors", {})
        f = b.get("fonts", {})
        s = b.get("shape", {})
        m = b.get("motion", {})
        out = {f"--c-{k.replace('_', '-')}": str(v) for k, v in c.items() if v}
        disp, body = f.get("display", {}), f.get("body", {})
        out["--font-display"] = f'"{disp.get("family", "Inter")}", system-ui, sans-serif'
        out["--font-body"] = f'"{body.get("family", "Inter")}", system-ui, sans-serif'
        out["--weight-display"] = str(disp.get("weight", 800))
        out["--weight-body"] = str(body.get("weight", 500))
        out["--radius"] = f'{s.get("radius", 20)}px'
        out["--line"] = f'{s.get("line", 3)}px'
        out["--shadow"] = s.get("shadow_css") if s.get("shadow", "soft") != "none" else "none"
        out["--entrance-frames"] = str(m.get("entrance_frames", 10))
        return out

    def color_value(self, name: Any, default: str | None = None) -> str | None:
        """A pack colour name ("soft", "ink") or a #RRGGBB value as #RRGGBB; None (or `default`) when neither."""
        if isinstance(name, str) and _HEX.match(name):
            return name.upper()
        v = (self.brand.get("colors") or {}).get(name) if isinstance(name, str) else None
        return v.upper() if isinstance(v, str) and _HEX.match(v) else default

    def motion_graphics(self) -> dict:
        """brand.json `motion_graphics`, resolved for motion templates (CC_CTX brand.mg): `palette` as 3 to 5 colours
        (derived from colors.accent when null or missing), `pastels` as one light colour per palette colour, `ground`
        and `ink` as #RRGGBB, the rest with the defaults of MOTION_GRAPHICS."""
        raw = self.brand.get("motion_graphics")
        mg = _merge(MOTION_GRAPHICS, raw if isinstance(raw, dict) else {})
        accent = self.color_value("accent", "#E4572E")
        pal = mg.get("palette")
        if isinstance(pal, list) and pal and all(isinstance(c, str) and _HEX.match(c) for c in pal):
            palette = [c.upper() for c in pal]
        else:
            palette = derive_palette(accent)
        pas = mg.get("pastels")
        if isinstance(pas, list) and len(pas) == len(palette) and all(isinstance(c, str) and _HEX.match(c) for c in pas):
            pastels = [c.upper() for c in pas]
        elif pas is False:
            pastels = []
        else:
            pastels = [pastel(c) for c in palette]
        ground_name = mg.get("ground") or "soft"
        ground = self.color_value(ground_name, self.color_value("soft", "#F1F1EF"))
        ink_name = mg.get("ink") or ("paper" if ground_name == "ink" else "ink")
        ink = self.color_value(ink_name, self.color_value("ink", "#111111"))
        if not pastels:                     # pastels off: templates that want a light ground get the ground itself
            pastels = [ground] * len(palette)
        return {**mg, "palette": palette, "pastels": pastels, "ground": ground, "ink": ink,
                "blur": {**MOTION_GRAPHICS["blur"], **(mg.get("blur") or {})},
                "plate3d": {**MOTION_GRAPHICS["plate3d"], **(mg.get("plate3d") or {})}}

    def render_tokens(self) -> dict:
        """Everything a renderer needs, as one JSON object (passed to 2D pages as window.BRAND and to Blender)."""
        b = self.brand
        fonts = {}
        for role, spec in (b.get("fonts") or {}).items():
            files = [str(p) for p in (self.file(x) for x in spec.get("files", [])) if p]
            fonts[role] = {**spec, "files": files}
        logo = dict(b.get("logo") or {})
        for k in ("file", "mark"):
            p = self.file(logo.get(k))
            logo[k] = str(p) if p else None
        return {
            "name": b.get("name"),
            "colors": b.get("colors", {}),
            "fonts": fonts,
            "logo": logo,
            "shape": b.get("shape", {}),
            "motion": b.get("motion", {}),
            "motion_graphics": self.motion_graphics(),
            "stage3d": b.get("stage3d", {}),
            "css": self.css_vars(),
            "edit": {k: v for k, v in self.edit_style.items() if k != "sources"},
        }


def load(pack_dir: Path | str | None = None) -> Pack:
    """Load the active style pack. A user pack is merged over the neutral one, so missing keys keep defaults."""
    neutral = paths.neutral_pack_dir()
    d = Path(pack_dir) if pack_dir else paths.brand_dir()
    is_neutral = d.resolve() == neutral.resolve()
    data = {}
    for attr, name in PACK_FILES.items():
        base = _read_json(neutral / name)
        data[attr] = base if is_neutral else _merge(base, _read_json(d / name))
    voice_p = d / "voice.md"
    voice = voice_p.read_text(encoding="utf-8") if voice_p.is_file() else ""
    return Pack(dir=d, is_neutral=is_neutral, voice=voice, **data)


def check(pack: Pack | None = None) -> list[str]:
    """Problems a human should fix. Empty list = fine."""
    pack = pack or load()
    problems = []
    for key in ("ink", "paper", "accent"):
        v = pack.value(f"brand.colors.{key}")
        if not (isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v)):
            problems.append(f"brand.json colors.{key} must be a #RRGGBB colour, got {v!r}")
    if pack.value("edit_style.captions") not in ("none", "keywords", "full"):
        problems.append("edit-style.json captions must be none, keywords or full")
    lufs = pack.value("edit_style.loudness_lufs")
    if not isinstance(lufs, (int, float)) or not -24 <= lufs <= -9:
        problems.append("edit-style.json loudness_lufs should be between -24 and -9 (YouTube plays at about -14)")
    for role, spec in (pack.value("brand.fonts", {}) or {}).items():
        for f in spec.get("files", []):
            if not pack.file(f):
                problems.append(f"font file for {role} not found in the pack: {f}")
    logo = pack.value("brand.logo.file")
    if logo and not pack.file(logo):
        problems.append(f"logo file not found in the pack: {logo}")
    problems += _check_motion_graphics(pack)
    problems += _check_motion_style(pack)
    return problems


def _num_in(v: Any, lo: float, hi: float) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _check_motion_graphics(pack: Pack) -> list[str]:
    """brand.json motion_graphics (all keys optional; see docs/style-packs.md)."""
    mg = pack.value("brand.motion_graphics")
    if mg is None:
        return []
    if not isinstance(mg, dict):
        return ["brand.json motion_graphics must be an object"]
    out = []
    where = "brand.json motion_graphics"
    pal = mg.get("palette")
    if pal is not None and not (isinstance(pal, list) and 3 <= len(pal) <= 5
                                and all(isinstance(c, str) and _HEX.match(c) for c in pal)):
        out.append(f"{where}.palette must be null (derived from colors.accent) or 3 to 5 #RRGGBB colours")
    pas = mg.get("pastels")
    if pas is not None and not isinstance(pas, bool):
        n = len(pal) if isinstance(pal, list) else 4
        if not (isinstance(pas, list) and len(pas) == n and all(isinstance(c, str) and _HEX.match(c) for c in pas)):
            out.append(f"{where}.pastels must be true, false or one #RRGGBB colour per palette colour")
    for key in ("ground", "ink"):
        v = mg.get(key)
        if v is not None and pack.color_value(v) is None:
            out.append(f"{where}.{key} must be a pack colour name (soft, ink, ...) or #RRGGBB, got {v!r}")
    if mg.get("glass") is not None and not isinstance(mg.get("glass"), bool):
        out.append(f"{where}.glass must be true or false")
    for key, lo, hi in (("enter_s", 0.2, 1.0), ("exit_s", 0.1, 1.0), ("drift_pct_per_s", 0.0, 5.0)):
        if mg.get(key) is not None and not _num_in(mg[key], lo, hi):
            out.append(f"{where}.{key} must be a number from {lo:g} to {hi:g}")
    if mg.get("ease") is not None and mg["ease"] not in EASES:
        out.append(f"{where}.ease must be one of {', '.join(EASES)}")
    blur = mg.get("blur")
    if blur is not None:
        if not isinstance(blur, dict):
            out.append(f"{where}.blur must be an object {{\"shutter\": 180, \"samples\": 16}}")
        else:
            if blur.get("shutter") is not None and not _num_in(blur["shutter"], 0, 720):
                out.append(f"{where}.blur.shutter must be 0 to 720 degrees")
            if blur.get("samples") is not None and not (isinstance(blur["samples"], int) and 1 <= blur["samples"] <= 64):
                out.append(f"{where}.blur.samples must be a whole number from 1 to 64")
    if mg.get("plate3d") is not None and not isinstance(mg["plate3d"], dict):
        out.append(f"{where}.plate3d must be an object")
    return out


def _check_motion_style(pack: Pack) -> list[str]:
    """edit-style.json `motion` (lengths, preference, density limits) and `graphics_mix`."""
    out = []
    m = pack.value("edit_style.motion")
    if m is not None:
        where = "edit-style.json motion"
        if not isinstance(m, dict):
            return [f"{where} must be an object"]
        ins = m.get("insert_s")
        if ins is not None and not (isinstance(ins, list) and len(ins) == 2 and all(_num_in(v, 0.5, 60) for v in ins)
                                    and ins[0] < ins[1]):
            out.append(f"{where}.insert_s must be [shortest, longest] in seconds, e.g. [3, 6]")
        if m.get("overlay_min_s") is not None and not _num_in(m["overlay_min_s"], 0.5, 30):
            out.append(f"{where}.overlay_min_s must be seconds from 0.5 to 30")
        if m.get("prefer") is not None and m["prefer"] not in ("motion", "2d"):
            out.append(f"{where}.prefer must be \"motion\" or \"2d\"")
        for part in ("long", "short"):
            d = m.get(part)
            if d is None:
                continue
            if not isinstance(d, dict):
                out.append(f"{where}.{part} must be an object of limits")
                continue
            for k, v in d.items():
                if v is not None and not _num_in(v, 0, 1000):
                    out.append(f"{where}.{part}.{k} must be a number (or null for no limit)")
        heroes = m.get("heroes")
        if heroes is not None and not (isinstance(heroes, list) and all(isinstance(h, str) for h in heroes)):
            out.append(f"{where}.heroes must be a list of template names")
    mix = pack.value("edit_style.graphics_mix")
    if mix is not None:
        if not isinstance(mix, dict) or not all(_num_in(v, 0, 1) for v in mix.values()):
            out.append("edit-style.json graphics_mix must map insert kinds (motion, 2d, 3d, text) to shares 0 to 1")
    return out


def profile_rows(pack: Pack | None = None) -> list[dict]:
    """The read-only profile view: label, value, kind, source."""
    pack = pack or load()
    rows = []

    def row(label, dotted, kind="text"):
        v = pack.value(dotted)
        if v in (None, "", [], {}):
            return
        src = pack.source_of(dotted) or ("Crewcut default" if pack.is_neutral else None)
        rows.append({"label": label, "value": v, "kind": kind, "source": src})

    row("Channel", "channel.name")
    row("Niche", "channel.niche")
    row("Audience", "channel.audience")
    row("Language", "channel.language")
    row("Tone", "channel.tone")
    for k in ("accent", "ink", "paper"):
        row(k.capitalize(), f"brand.colors.{k}", "color")
    row("Display font", "brand.fonts.display.family")
    row("Logo", "brand.logo.file", "file")
    row("Captions", "edit_style.captions")
    row("Cuts per minute", "edit_style.pace_cuts_per_minute")
    row("Music", "edit_style.music")
    row("Loudness (LUFS)", "edit_style.loudness_lufs")
    row("Thumbnail layouts", "thumbnail.layouts")
    return rows
