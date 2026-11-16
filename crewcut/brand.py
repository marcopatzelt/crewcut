"""The style pack: the user's taste as data (brand/), or the neutral default (packs/neutral/).

Skills and tools read every colour, font, loudness and limit from here, never from code.
"""

from __future__ import annotations

import json
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
    return problems


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
