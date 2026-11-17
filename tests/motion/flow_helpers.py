"""Helpers for the motion workflow tests: an episode with a words file and a script in the temp studio, stand-in
templates on the shelf, a filled motion plan, frames made with Pillow. Nothing here runs the engine."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

SENTENCES = [
    "This video shows how a laptop hands a render to a rented GPU.",
    "One million tokens cost about thirty cents.",
    "The agent packs four jobs and sends them away.",
    "A card lights up in a data centre far from here.",
    "Frames come back while the laptop stays cool.",
    "The whole render took eight minutes.",
    "Nothing of my footage left the computer.",
    "Only code and fonts travelled.",
    "That is the trick.",
]

SCRIPT = """This video shows how a laptop hands a render to a rented GPU.

One million tokens cost about thirty cents.

---

Notes for the edit.
[[motion: number | "thirty cents"]]
[[motion: handoff | "packs four jobs"]]
"""

STANDINS = {   # name: (kind, formats, params)
    "number_roll": ("full", ["landscape", "portrait", "stage"],
                    {"comp": "Main", "value": "0", "unit": "", "label": "", "landAt": 1.0}),
    "keyword_pop": ("overlay", ["landscape", "portrait"], {"comp": "Main", "words": ["word"]}),
}


def words(sentences=SENTENCES, start: float = 0.5, step: float = 0.3, gap: float = 0.6) -> list[dict]:
    out, t = [], start
    for s in sentences:
        for w in s.split():
            out.append({"w": w, "s": round(t, 2), "e": round(t + step - 0.05, 2)})
            t += step
        t += gap
    return out


def template_src(name: str, kind: str = "full", formats=None, params=None, version: int | None = 1,
                 body: str = "return {ok: true};") -> str:
    lines = [f"/* @template {name}", " * @description A stand-in for tests.", f" * @kind {kind}",
             f" * @formats {json.dumps(formats or ['landscape', 'portrait'])}"]
    if version:
        lines.append(f" * @version {version}")
    lines += [f" * @params {json.dumps(params or {'comp': 'Main'})}", " * @end */"]
    return "\n".join(lines) + f"\nfunction {name}(P) {{ {body} }}\n"


def install_shelf(studio: Path, names=None) -> Path:
    """Stand-in templates in the studio's own style pack (brand/templates/motion/)."""
    pack = studio / "brand"
    d = pack / "templates" / "motion"
    d.mkdir(parents=True, exist_ok=True)
    if not (pack / "brand.json").is_file():
        (pack / "brand.json").write_text("{}", encoding="utf-8")
    for name in names or STANDINS:
        kind, formats, params = STANDINS[name]
        (d / f"{name}.jsx").write_text(template_src(name, kind, formats, params), encoding="utf-8")
    return d


def make_episode(title: str = "Local render", sentences=SENTENCES, script: str | None = SCRIPT) -> tuple[str, Path]:
    from crewcut import episodes, paths
    eid = episodes.create(title)["id"]
    ep = paths.episode_dir(eid)
    (ep / "work" / "words-v001.json").write_text(json.dumps(words(sentences)), encoding="utf-8")
    if script:
        (ep / "brief" / "SCRIPT-v001.md").write_text(script, encoding="utf-8")
    return eid, ep


def fill(plan: dict, chosen: bool = True, lesson: str | None = None) -> dict:
    """A finished plan: beat 2 from the shelf, beat 3 built new, the rest left to the speaker; two upgrades."""
    for b in plan["beats"]:
        b.update(purpose="follow the speaker", picture="the speaker, a slow punch-in", column="-")
    b2, b3 = plan["beats"][1], plan["beats"][2]
    b2.update(purpose="believe the number", picture="the price rolls and lands on thirty as the word is said",
              column="a", piece="number_roll", params={"value": "30", "unit": "cents"}, length_s=4.0)
    b3.update(purpose="see the hand-off", picture="four jobs leave the laptop, a card lights up, frames come back",
              column="b", piece="handoff", length_s=5.0)
    plan["new"] = [{"id": "handoff", "beat": 3, "brief": "Four jobs leave the laptop for a rented GPU.",
                    "why_new": "No shelf piece shows work moving between machines.", "kind": "full", "plates": 1,
                    "effort": "M", "cost_usd": 0.3, "cap_usd": 1.0, "struck": False}]
    plan["upgrades"] = [
        {"id": "u1", "upgrade": "Every exit from a full-frame piece is caused by a motion",
         "source": {"kind": "lesson", "ref": lesson} if lesson else
         {"kind": "baseline", "ref": "the last video cut hard out of every insert"},
         "effort": "S", "cost_usd": 0.0, "chosen": chosen, "struck": False},
        {"id": "u2", "upgrade": "The opening number as a heavy 3D word", "source": {"kind": "reference",
                                                                                   "ref": "ref-001"},
         "effort": "M", "cost_usd": 0.25, "chosen": False, "struck": False},
    ]
    return plan


def ready_plan(eid: str, **kw) -> Path:
    from crewcut.motion import director
    p = director.skeleton(eid)
    plan = fill(director.load(p), **kw)
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def image(path: Path, size=(320, 180), colours=((228, 87, 46), (47, 111, 222), (242, 184, 75), (59, 165, 139))) -> Path:
    """A frame with four colour bands (passes the one-hue check) or one colour (fails it)."""
    im = Image.new("RGB", size, (240, 240, 238))
    d = ImageDraw.Draw(im)
    w = size[0] // len(colours)
    for i, c in enumerate(colours):
        d.rectangle([i * w, 0, (i + 1) * w - 1, size[1] - 1], fill=c)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def bundle(ep: Path, iid: str, errors: int = 0, version: int = 1) -> Path:
    """A Critic bundle (review/motion-vNNN/bundle.json) that holds ``iid`` with ``errors`` ERROR findings."""
    d = ep / "review" / f"motion-v{version:03d}"
    d.mkdir(parents=True, exist_ok=True)
    findings = [{"insert": iid, "area": "Text", "level": "ERROR", "id": f"e{i}", "text": "text 30 px", "time": 1.0,
                 "fix": None} for i in range(errors)]
    findings.append({"insert": None, "area": "Density", "level": "ERROR", "id": "motion-rate", "text": "x",
                     "time": None, "fix": None})
    p = d / "bundle.json"
    p.write_text(json.dumps({"inserts": [{"id": iid}], "findings": findings}), encoding="utf-8")
    return p
