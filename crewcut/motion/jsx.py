"""Turning Python values into JavaScript source for EffectCraft scripts (``effectcraft-cli script``)."""

from __future__ import annotations

import json
import math
from typing import Any


def js(value: Any) -> str:
    """A JavaScript literal for a JSON-like Python value. Rejects NaN/inf (EffectCraft would reject them too)."""
    def check(v: Any) -> None:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"not a finite number: {v}")
        if isinstance(v, dict):
            for x in v.values():
                check(x)
        if isinstance(v, (list, tuple)):
            for x in v:
                check(x)
    check(value)
    return json.dumps(value, ensure_ascii=False)


def wrap_program(body: str, lib: str = "") -> str:
    """A complete script: the helper library, then ``body`` inside a function whose return value
    becomes the script result as a JSON string (``__R``). One undo group, so a failing script can be undone."""
    return (
        lib + "\n"
        "app.beginUndoGroup('crewcut-motion');\n"
        "var __R = (function () {\n" + body + "\n})();\n"
        "app.endUndoGroup();\n"
        "JSON.stringify(__R === undefined ? null : __R);\n"
    )


def parse_result(reply: Any) -> Any:
    """The value a wrapped program returned: the CLI reply's ``result`` holds a JSON string."""
    if not isinstance(reply, dict):
        return reply
    r = reply.get("result")
    if isinstance(r, str):
        try:
            return json.loads(r)
        except json.JSONDecodeError:
            return r
    return r
