"""Motion templates: parameterised JSX files run inside EffectCraft.

A template is ``<name>.jsx`` holding a header and one function of the same name::

    /* @template burst_rings
     * @description Click burst: rings expand from a point...
     * @params {"comp": "Main", "t": 0.5, "center": [960, 540]}
     * @formats ["landscape", "portrait", "stage"]
     * @kind overlay
     * @sounds [{"at": "in", "sound": "whoosh"}]
     * @version 1
     * @end */
    function burst_rings(P) { ...; return {layers: [...]}; }

``@template``, ``@description`` and ``@params`` (JSON defaults) are the base header. ``@formats``, ``@kind``,
``@sounds`` and ``@version`` are optional; when present they are checked and returned with the template info.

``run`` merges ``--params`` over the header defaults (unknown params are refused), prepends the shared helper
library and runs the function in one EffectCraft process (one undo group).

Search path, earlier folders win: the ``--templates-dir`` folders (``:``-separated), then the style pack's
``brand/templates/motion/``, then the app's ``templates/motion/``. The helper library is the pack's
``templates/motion/lib/ec_lib.jsx`` when the pack has one, else the app's. ``EC_ASSETS`` (cursor and other shared
images) is the template folder's own ``assets/`` when it has one, else the app's ``templates/motion/assets``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .. import paths
from .jsx import js, parse_result, wrap_program

HEADER = re.compile(r"/\*\s*@template\s+(?P<name>[A-Za-z0-9_]+)(?P<body>.*?)\*/", re.S)
TAG = re.compile(r"(?:^|\n)[ \t]*\*?[ \t]*@(?P<tag>[A-Za-z]+)\b")
FORMATS = ("landscape", "portrait", "stage")
KINDS = ("full", "overlay")
LIB = Path("lib") / "ec_lib.jsx"


class TemplateError(ValueError):
    pass


def app_dir() -> Path:
    """The app's motion templates: ``templates/motion``."""
    return paths.templates_dir() / "motion"


def pack_dir() -> Path:
    """The active style pack's motion templates: ``<pack>/templates/motion`` (may not exist)."""
    return paths.brand_dir() / "templates" / "motion"


def assets_dir() -> Path:
    """Shared images for templates (``EC_ASSETS``): ``templates/motion/assets``."""
    return app_dir() / "assets"


def search_path(extra: str | None = None) -> list[str]:
    """Template folders in lookup order: ``extra`` (``:``-separated), the pack, the app. Missing folders are left out."""
    dirs: list[str] = []
    if extra:
        dirs += [os.path.expanduser(d) for d in extra.split(os.pathsep) if d]
    dirs += [str(pack_dir()), str(app_dir())]
    out: list[str] = []
    for d in dirs:
        if os.path.isdir(d) and os.path.abspath(d) not in {os.path.abspath(x) for x in out}:
            out.append(d)
    return out


def _clean(text: str) -> str:
    """Header text without the leading ``*`` of each comment line."""
    return "\n".join(line.strip().lstrip("*").strip() for line in text.splitlines()).strip()


def _tags(body: str) -> dict[str, str]:
    """``@tag value`` sections of a header body (a value runs to the next ``@tag`` at the start of a line)."""
    marks = list(TAG.finditer(body))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.setdefault(m.group("tag"), body[m.end():end])
    return out


def _json_tag(name: str, tag: str, raw: str) -> Any:
    try:
        return json.loads(_clean(raw))
    except json.JSONDecodeError as e:
        raise TemplateError(f"template {name}: @{tag} is not JSON ({e})") from e


def parse_header(text: str) -> dict[str, Any]:
    """Name, description, default params and the optional ``formats``, ``kind``, ``sounds``, ``version`` of a
    template source. Optional fields that the header leaves out are ``None``."""
    m = HEADER.search(text)
    if not m:
        raise TemplateError("missing /* @template NAME ... */ header")
    name = m.group("name")
    tags = _tags(m.group("body"))
    defaults: dict[str, Any] = {}
    if "params" in tags:
        defaults = _json_tag(name, "params", tags["params"])
        if not isinstance(defaults, dict):
            raise TemplateError(f"template {name}: @params must be a JSON object")
    description = " ".join(line.strip().lstrip("*").strip() for line in tags.get("description", "").splitlines()).strip()
    if not re.search(r"function\s+" + re.escape(name) + r"\s*\(", text):
        raise TemplateError(f"template {name}: no function {name}(P)")

    formats = None
    if "formats" in tags:
        formats = _json_tag(name, "formats", tags["formats"])
        if not (isinstance(formats, list) and formats and all(f in FORMATS for f in formats)):
            raise TemplateError(f"template {name}: @formats must be a JSON list of {', '.join(FORMATS)}")
    kind = None
    if "kind" in tags:
        kind = _clean(tags["kind"])
        if kind not in KINDS:
            raise TemplateError(f"template {name}: @kind must be {' or '.join(KINDS)}, got {kind!r}")
    sounds = None
    if "sounds" in tags:
        sounds = _json_tag(name, "sounds", tags["sounds"])
        ok = isinstance(sounds, list) and all(
            isinstance(s, dict) and isinstance(s.get("at"), (str, int, float)) and not isinstance(s.get("at"), bool)
            and isinstance(s.get("sound"), str) and s["sound"] for s in sounds)
        if not ok:
            raise TemplateError(f'template {name}: @sounds must be a JSON list of {{"at": ..., "sound": "..."}}')
    version = None
    if "version" in tags:
        raw = _clean(tags["version"])
        if not raw.isdigit() or int(raw) < 1:
            raise TemplateError(f"template {name}: @version must be a whole number >= 1, got {raw!r}")
        version = int(raw)
    return {"name": name, "description": description, "defaults": defaults, "formats": formats, "kind": kind,
            "sounds": sounds, "version": version}


def discover(extra: str | None = None) -> dict[str, dict[str, Any]]:
    """All templates on the search path (earlier folders win). Files whose header does not parse are left out."""
    found: dict[str, dict[str, Any]] = {}
    for d in search_path(extra):
        for f in sorted(os.listdir(d)):
            if not f.endswith(".jsx"):
                continue
            p = os.path.join(d, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    h = parse_header(fh.read())
            except TemplateError:
                continue
            if h["name"] not in found:
                h["path"] = p
                found[h["name"]] = h
    return found


def lib_path() -> Path:
    """The shared helper library: the pack's own ``lib/ec_lib.jsx`` if it has one, else the app's."""
    for d in (pack_dir(), app_dir()):
        p = d / LIB
        if p.is_file():
            return p
    raise TemplateError(f"{LIB} not found in templates/motion")


def lib_source() -> str:
    return lib_path().read_text(encoding="utf-8")


def merge(defaults: dict[str, Any], params: dict[str, Any], strict: bool = True) -> dict[str, Any]:
    """Defaults overlaid with ``params``. Unknown keys are refused (a typo must not silently do nothing)."""
    unknown = sorted(set(params) - set(defaults))
    if strict and unknown:
        raise TemplateError(f"unknown parameters {unknown}; accepted: {sorted(defaults)}")
    out = json.loads(json.dumps(defaults))
    out.update(params)
    return out


def program(name: str, params: dict[str, Any], extra: str | None = None, strict: bool = True) -> tuple[str, dict]:
    """The full script for template ``name`` with ``params``, and the merged params."""
    ts = discover(extra)
    if name not in ts:
        raise TemplateError(f"unknown template {name!r}; available: {', '.join(sorted(ts)) or 'none'}")
    t = ts[name]
    merged = merge(t["defaults"], params, strict=strict)
    with open(t["path"], encoding="utf-8") as fh:
        src = fh.read()
    assets = os.path.join(os.path.dirname(t["path"]), "assets")
    if not os.path.isdir(assets):
        assets = str(assets_dir())
    body = f"{src}\nreturn {name}({js(merged)});"
    return wrap_program(body, lib_source() + f"\nvar EC_ASSETS = {js(assets)};\n"), merged


def run(backend: Any, project: str, name: str, params: dict[str, Any] | None = None, extra: str | None = None,
        strict: bool = True, save: bool = True) -> dict[str, Any]:
    """Run template ``name`` in ``project`` through ``backend`` (one engine process, one undo group) and save.
    Returns ``{"template", "params", "result"}``; ``result`` is what the template function returned."""
    code, merged = program(name, params or {}, extra, strict=strict)
    res = parse_result(backend.script(code, project=project, save=save, name=f"{name}.jsx"))
    return {"template": name, "params": merged, "result": res}
