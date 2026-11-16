#!/usr/bin/env python3
"""Summarise a Taste report and apply the waivers: prints the FAILs that are not waived and exits 1 if any are left.

    taste_waivers.py <report.txt> <waivers.json>
Waivers: {"waivers": [{"check": "<check name as in the report>", "reason": "<why it does not apply to an app>"}]}
"""
import json
import re
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    text = Path(argv[0]).read_text(encoding="utf-8", errors="replace") if Path(argv[0]).is_file() else ""
    waivers = json.loads(Path(argv[1]).read_text(encoding="utf-8")).get("waivers", []) if Path(argv[1]).is_file() else []
    waived = {w["check"]: w.get("reason", "") for w in waivers}
    fails = sorted(set(re.findall(r"^\s*FAIL\s+([\w-]+)", text, re.M)))
    warns = sorted(set(re.findall(r"^\s*WARN\s+([\w-]+)", text, re.M)))
    open_fails = [f for f in fails if f not in waived]
    print(f"Taste: {len(fails)} failing checks ({len(fails) - len(open_fails)} waived), {len(warns)} warnings")
    for f in open_fails:
        print(f"  FAIL {f}")
    for f in fails:
        if f in waived:
            print(f"  waived {f}: {waived[f]}")
    if not text:
        print("  no report (the checker did not run)")
    return 1 if open_fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
