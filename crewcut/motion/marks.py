"""The Writer's motion marks in a script: ``[[motion: number | "30 cents per million tokens"]]``.

Marks are wishes for the motion director, not orders. They live below the script's ``---`` line (the notes for the
edit; the teleprompter shows only the text above it), at most ``MAX_MARKS`` per script. The first part says what kind
of picture the Writer imagines, the quoted part names the spoken words it belongs to (the director finds them in the
words file). Pure Python (re only), so the script check in ``skills/script`` can import it.
"""

from __future__ import annotations

import re

MAX_MARKS = 5
MARK = re.compile(r"\[\[\s*motion\s*:(?P<body>.*?)\]\]", re.I | re.S)
RULE = re.compile(r"^\s*---\s*$")


def split(text: str) -> tuple[str, str, int]:
    """(spoken part, notes part, line number of the ``---`` line or 0 when there is none)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if RULE.match(line):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1:]), i + 1
    return text, "", 0


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _parse_body(body: str) -> tuple[str, str]:
    what, _, rest = body.partition("|")
    quote = rest.strip().strip('"“”\'').strip()
    return " ".join(what.split()), " ".join(quote.split())


def parse(text: str) -> list[dict]:
    """The marks below the ``---`` line, in order: ``[{"n", "what", "quote", "line"}]``. ``line`` is the line number
    in the whole script."""
    _spoken, notes, rule_line = split(text)
    if not rule_line:
        return []
    out = []
    for m in MARK.finditer(notes):
        what, quote = _parse_body(m.group("body"))
        out.append({"n": len(out) + 1, "what": what, "quote": quote, "line": rule_line + _line_of(notes, m.start())})
    return out


def problems(text: str) -> list[str]:
    """What the script check reports about marks: marks above ``---``, more than ``MAX_MARKS``, a mark without its
    words. Empty list = fine."""
    out = []
    spoken, _notes, rule_line = split(text)
    above = list(MARK.finditer(spoken if rule_line else text))
    if above:
        out.append(f"{len(above)} motion mark(s) in the spoken text (line {_line_of(text, above[0].start())}): "
                   "marks go below the --- line")
    marks = parse(text)
    if len(marks) > MAX_MARKS:
        out.append(f"{len(marks)} motion marks; at most {MAX_MARKS} (they are wishes: keep the strongest)")
    for m in marks:
        if not m["what"]:
            out.append(f"motion mark on line {m['line']} does not say what kind of picture it wishes")
        if not m["quote"]:
            out.append(f'motion mark on line {m["line"]} names no spoken words: [[motion: {m["what"] or "kind"} | '
                       '"the words it belongs to"]]')
    return out
