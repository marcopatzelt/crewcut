"""The ready-made libraries a graphic starts from, before anyone builds one from scratch (docs/motion-libraries.md):

1. HyperFrames templates (``templates/hyperframes/``, scene ``hf-<name>`` of a 2D insert): keyword or number beside
   the speaker, card, chapter card, chat or code snippet, calm diagram. Text, UI and data only.
2. Private imported templates (``studio/library/templates-private/``): Lottie files and After Effects projects from
   free marketplaces, converted to the pack's palette, fonts and fps (``crewcut motion imports``).
3. CC0 3D assets for Blender (Poly Haven HDRIs and textures, ambientCG materials), fetched by their public APIs and
   cached (``crewcut render assets``); used by plates and 3D scenes on the rented GPU.

``crewcut motion libraries`` prints all three; the Designer's and the Editor's prompts in the edit step say to read it
first. Nothing here renders or downloads.
"""

from __future__ import annotations

from typing import Any

ORDER = ("hyperframes", "imports", "assets3d")


def rows() -> dict[str, Any]:
    from ..render import assets3d, hyperframes
    from . import imports
    try:
        hf = hyperframes.listing()
    except Exception as e:  # noqa: BLE001 - one broken library never hides the others
        hf = [{"error": str(e)}]
    try:
        imp = [{k: e.get(k) for k in ("name", "title", "kind", "insert_kind", "licence", "source", "needs_adaptation",
                                       "texts", "folder")} for e in imports.entries()]
    except Exception as e:  # noqa: BLE001
        imp = [{"error": str(e)}]
    try:
        cached = assets3d.cached()
    except Exception as e:  # noqa: BLE001
        cached = [{"error": str(e)}]
    return {"hyperframes": {"available": hyperframes.available(), "version": hyperframes.pinned_version(),
                            "templates": hf},
            "imports": {"folder": str(imports.private_dir()), "templates": imp},
            "assets3d": {"sources": assets3d.SOURCES, "cache": str(assets3d.cache_dir()), "cached": cached}}


def lines(data: dict[str, Any] | None = None) -> list[str]:
    d = data or rows()
    hf = d["hyperframes"]
    out = [f"HyperFrames {hf['version']} ({'installed' if hf['available'] else 'not installed here'}): "
           "2D inserts with scene hf-<name>, \"transparent\": true for overlays"]
    for t in hf["templates"]:
        if "error" in t:
            out.append(f"  error: {t['error']}")
            continue
        out.append(f"  {t['scene']:<14} type {t.get('type')}  {t.get('kind'):<7} {t.get('title')}  "
                   f"params: {', '.join(t.get('params') or {})}")
    imp = d["imports"]
    out.append(f"Private imported templates ({imp['folder']}): motion scene lottie_clip via "
               "`crewcut motion imports use NAME EPISODE INSERT_ID`")
    if not imp["templates"]:
        out.append("  none yet (crewcut motion imports add FILE --name N --licence L --source URL)")
    for t in imp["templates"]:
        if "error" in t:
            out.append(f"  error: {t['error']}")
            continue
        flag = "  (After Effects: adapt colours in EffectCraft)" if t.get("needs_adaptation") else ""
        out.append(f"  {t['name']:<24} {t.get('kind'):<7} {t.get('insert_kind') or '-':<8} {t.get('licence')}{flag}")
    a = d["assets3d"]
    out.append(f"CC0 3D assets (cache {a['cache']}): `crewcut render assets fetch polyhaven:hdri/<id>` or "
               "`ambientcg:<id>`; in a Blender plate `import crewcut_assets`")
    cached = [c for c in a["cached"] if "error" not in c]
    out.append("  cached: " + (", ".join(f"{c['spec']} ({c.get('resolution')})" for c in cached[:12]) or "none yet"))
    return out


def prompt_line() -> str:
    """One line for the Designer's and the Editor's prompts in the edit step."""
    return ("LIBRARIES FIRST: before building a graphic from scratch, run `crewcut motion libraries` and take a "
            "ready-made block when one shows the picture: a HyperFrames template (2D insert, scene hf-keyword, hf-card, "
            "hf-chapter, hf-snippet, hf-diagram; params only, the studio style is fixed), a private imported template "
            "(`crewcut motion imports use`), and for Blender a CC0 HDRI or material (`import crewcut_assets` in a plate; "
            "`crewcut render assets fetch`). Build new only when none fits, and say in the motion plan why.")
