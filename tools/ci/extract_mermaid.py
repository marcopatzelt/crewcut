#!/usr/bin/env python3
"""Write every ```mermaid block of the given Markdown files to <out>/<file>-<n>.mmd (CI renders them to prove they parse).

    extract_mermaid.py <out dir> <file.md> [<file.md> ...]
"""
import re
import sys
from pathlib import Path

BLOCK = re.compile(r"```mermaid\n(.*?)```", re.S)


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in argv[1:]:
        for i, m in enumerate(BLOCK.finditer(Path(f).read_text(encoding="utf-8"))):
            (out / f"{Path(f).stem}-{i}.mmd").write_text(m.group(1), encoding="utf-8")
            n += 1
    print(f"{n} mermaid block(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
