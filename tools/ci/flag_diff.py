#!/usr/bin/env python3
"""Compare the flags in two --help texts: prints new and removed flags, exit 1 when anything changed.

    flag_diff.py <old help file> <new help file> [<label>]
"""
import re
import sys
from pathlib import Path

FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]+)")


def flags(text: str) -> set[str]:
    return set(FLAG.findall(text))


def main(argv: list[str]) -> int:
    old_p, new_p = Path(argv[0]), Path(argv[1])
    label = argv[2] if len(argv) > 2 else new_p.name
    old = flags(old_p.read_text(encoding="utf-8")) if old_p.is_file() else set()
    new = flags(new_p.read_text(encoding="utf-8"))
    added, removed = sorted(new - old), sorted(old - new)
    if not old:
        print(f"{label}: no earlier snapshot; {len(new)} flags now")
        return 0
    if not added and not removed:
        print(f"{label}: no flag changes ({len(new)} flags)")
        return 0
    print(f"{label}: flags changed")
    for f in added:
        print(f"  new: {f}")
    for f in removed:
        print(f"  removed: {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
