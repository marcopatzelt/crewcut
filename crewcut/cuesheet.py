"""Cue sheets: a script that fixes only the lines a speaker must say word for word.

A cue sheet replaces the full text a speaker reads. It fixes the opening, and per unit a hook (the first sentence) and
a punch line (the last); everything between them is bullets the speaker says freely, in their own words. Each unit is
built like a Short (hook, retain, reward); whether it also works alone as a Short is only a hint (`Short: yes` marks
the units that do). The teleprompter shows the fixed lines large and the bullets small; the style gate checks the plan
before recording and the transcript after it.

File: brief/CUES-vNNN.md (English) or brief/DREHZETTEL-vNNN.md (German), same numbering as scripts. Above the first
line that is only `---` stands the sheet, below it notes. Format (English and German markers built in):

    ## Opening                         ## Einstieg
    LINE1: …                           SATZ1: …
    PROOF: … / SITUATION: … / PROMISE: … / LOOP: … / PLAN: …
                                       BEWEIS: … / LAGE: … / ANSAGE: … / SCHLEIFE: … / PLAN: …
    ## Unit 1 | Proof: Screen | Short: yes      ## Einheit 1 | Beleg: Bildschirm | Short: ja
    HOOK: …
    • Proof: [what is on screen] cue words · more cue words
    PUNCH: …
    ASK: … (the channel's fixed ask)   BITTE: …
    BRIDGE: … (optional)               BRÜCKE: … (freiwillig)
    ## Payoff                          ## Einlösung
    PAYOFF: …                          EINLÖSUNG: …
    ## Close                           ## Schluss
    VERDICT: …                         URTEIL: …
    LINK: …

A fixed line may carry a picture cue in square brackets (`[Bild: floating pillow]`); it is not spoken. A bullet may
start with one: `• Proof: [both clocks] Fable 111 minutes, Opus 131`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

NAME = re.compile(r"^(?P<kind>CUES|DREHZETTEL)-v(?P<n>\d+)(?P<rest>[^/]*)\.md$", re.I)

# canonical role <- marker words (upper case, umlauts and their ASCII spelling)
FIXED = {
    "line1": ("LINE1", "SATZ1"), "proof": ("PROOF", "BEWEIS"), "situation": ("SITUATION", "LAGE"),
    "promise": ("PROMISE", "ANSAGE"), "loop": ("LOOP", "SCHLEIFE"), "plan": ("PLAN",),
    "hook": ("HOOK",), "punch": ("PUNCH",), "ask": ("ASK", "BITTE"), "bridge": ("BRIDGE", "BRÜCKE", "BRUECKE"),
    "payoff": ("PAYOFF", "EINLÖSUNG", "EINLOESUNG"), "verdict": ("VERDICT", "URTEIL"), "link": ("LINK",),
}
MARKER = {m: role for role, ms in FIXED.items() for m in ms}
WHERE = {"opening": {"line1", "proof", "situation", "promise", "loop", "plan"},
         "unit": {"hook", "punch", "ask", "bridge"}, "payoff": {"payoff"}, "close": {"verdict", "link"}}
PART = (("opening", re.compile(r"^(?:opening|einstieg)\b", re.I)),
        ("unit", re.compile(r"^(?:unit|einheit)\s+(\d+)\b", re.I)),
        ("payoff", re.compile(r"^(?:payoff|einlösung|einloesung)\b", re.I)),
        ("close", re.compile(r"^(?:close|ending|schluss)\b", re.I)))
FIXED_LINE = re.compile(r"^(?P<m>[A-ZÄÖÜ0-9]+)\s*:\s*(?P<t>.+)$")
BULLET_LINE = re.compile(r"^[•*\-]\s+(?:(?P<role>[A-Za-zÄÖÜäöüß]+)\s*:\s*)?(?P<t>.+)$")
PICTURE = re.compile(r"^\s*\[(?P<p>[^\]]+)\]\s*")
CUE_IN_TEXT = re.compile(r"\[[^\]]*\]")
QUESTION = re.compile(r"^(?P<q>[^?]{1,120}\?)\s*(?:·\s*)?")


@dataclass
class Line:
    kind: str                 # "fixed" or "bullet"
    role: str                 # fixed: canonical role (hook, punch, …); bullet: the speaker's tag, lower case ("" if none)
    text: str                 # as written, without the marker (fixed: spoken text plus picture cues)
    line: int                 # line number in the file
    picture: str | None = None   # what is on screen ([…] at the start, or the first cue inside a fixed line)
    question: str | None = None  # a bullet's leading question, said as written

    @property
    def spoken(self) -> str:
        """What is said: picture cues removed (fixed lines say this word for word)."""
        return " ".join(CUE_IN_TEXT.sub(" ", self.text).split())

    @property
    def groups(self) -> list[str]:
        """A bullet's cue word groups (separated by ' · '), without the picture and the leading question."""
        t = PICTURE.sub("", self.text, count=1)
        if self.question:
            t = t[len(self.question):].lstrip(" ·")
        return [g.strip() for g in t.split(" · ") if g.strip()]


@dataclass
class Part:
    kind: str                 # opening, unit, payoff, close
    number: int | None        # the unit's number
    heading: str              # the heading line without "## "
    meta: dict = field(default_factory=dict)   # "Proof: Screen | Short: yes" -> {"proof": "Screen", "short": "yes"}
    lines: list[Line] = field(default_factory=list)

    def fixed(self, role: str) -> list[Line]:
        return [x for x in self.lines if x.kind == "fixed" and x.role == role]

    @property
    def bullets(self) -> list[Line]:
        return [x for x in self.lines if x.kind == "bullet"]

    @property
    def short(self) -> bool:
        v = str(self.meta.get("short", "")).strip().lower()
        return v.startswith(("ja", "yes", "y", "j"))

    @property
    def label(self) -> str:
        return f"{self.kind} {self.number}" if self.number is not None else self.kind


@dataclass
class CueSheet:
    title: str | None
    parts: list[Part]
    notes: str
    errors: list[str] = field(default_factory=list)

    @property
    def units(self) -> list[Part]:
        return [p for p in self.parts if p.kind == "unit"]

    def part(self, kind: str) -> Part | None:
        return next((p for p in self.parts if p.kind == kind), None)

    def fixed_lines(self) -> list[tuple[Part, Line]]:
        return [(p, x) for p in self.parts for x in p.lines if x.kind == "fixed"]


def is_name(name: str) -> bool:
    return bool(NAME.match(Path(name).name))


def looks_like(text: str) -> bool:
    """A cue sheet by its content: a part heading and at least one HOOK line above the notes."""
    top = text.split("\n---\n", 1)[0]
    return bool(re.search(r"(?mi)^##\s+(?:opening|einstieg|unit\s+\d|einheit\s+\d)", top)
                and re.search(r"(?m)^HOOK\s*:", top))


def is_cue_sheet(path: str | Path, text: str | None = None) -> bool:
    if is_name(str(path)):
        return True
    if text is None:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return False
    return looks_like(text)


def _meta(rest: str) -> dict:
    out = {}
    for chunk in rest.split("|")[1:]:
        k, _, v = chunk.partition(":")
        if k.strip() and v.strip():
            key = {"beleg": "proof", "proof": "proof", "short": "short"}.get(k.strip().lower(), k.strip().lower())
            out[key] = v.strip()
    return out


def parse(text: str) -> CueSheet:
    """Read a cue sheet. Problems a writer must fix are collected in `errors`; parsing never raises."""
    top, sep, notes = text.partition("\n---\n")
    if not sep:
        m = re.search(r"(?m)^---\s*$", text)
        top, notes = (text[:m.start()], text[m.end():]) if m else (text, "")
    sheet = CueSheet(title=None, parts=[], notes=notes)
    cur: Part | None = None
    for i, raw in enumerate(top.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("<!--"):
            continue
        if s.startswith("# "):
            sheet.title = sheet.title or s[2:].strip()
            continue
        if s.startswith("## "):
            head = s[3:].strip()
            kind, number = None, None
            for k, rx in PART:
                m = rx.match(head)
                if m:
                    kind, number = k, (int(m.group(1)) if k == "unit" else None)
                    break
            if kind is None:
                sheet.errors.append(f"line {i}: unknown part '{head}' (Opening/Einstieg, Unit/Einheit N, "
                                    "Payoff/Einlösung, Close/Schluss)")
                cur = None
                continue
            cur = Part(kind, number, head, _meta(head))
            sheet.parts.append(cur)
            continue
        if cur is None:
            sheet.errors.append(f"line {i}: text before the first part heading")
            continue
        b = BULLET_LINE.match(s)
        if b:
            t = b.group("t").strip()
            pic = PICTURE.match(t)
            rest = t[pic.end():] if pic else t
            q = QUESTION.match(rest)
            question = q.group("q").strip() if q and "·" not in q.group("q") else None
            cur.lines.append(Line("bullet", (b.group("role") or "").lower(), t, i,
                                  picture=pic.group("p").strip() if pic else None, question=question))
            continue
        f = FIXED_LINE.match(s)
        if f and f.group("m").upper() in MARKER:
            role = MARKER[f.group("m").upper()]
            if role not in WHERE[cur.kind]:
                sheet.errors.append(f"line {i}: {f.group('m')} does not belong in {cur.label}")
            t = f.group("t").strip()
            cue = re.search(r"\[([^\]]+)\]", t)
            cur.lines.append(Line("fixed", role, t, i, picture=cue.group(1).strip() if cue else None))
            continue
        sheet.errors.append(f"line {i}: a line without a marker ({s[:40]}…): start it with a marker such as HOOK: or "
                            "a bullet '• '")
    _structure(sheet)
    return sheet


def _structure(sheet: CueSheet) -> None:
    e = sheet.errors
    kinds = [p.kind for p in sheet.parts]
    if not kinds or kinds[0] != "opening":
        e.append("the sheet starts with the opening (## Opening / ## Einstieg)")
    if "close" not in kinds:
        e.append("the sheet ends with the close (## Close / ## Schluss)")
    elif kinds[-1] != "close":
        e.append("the close is the last part")
    order = {"opening": 0, "unit": 1, "payoff": 2, "close": 3}
    if [order[k] for k in kinds] != sorted(order[k] for k in kinds):
        e.append("parts in this order: opening, units, payoff, close")
    units = sheet.units
    if len(units) < 2:
        e.append(f"{len(units)} unit(s): a cue sheet has at least two units")
    for n, u in enumerate(units, 1):
        if u.number != n:
            e.append(f"unit {u.number}: units are numbered 1, 2, 3 … in order")
        for role in ("hook", "punch"):
            if len(u.fixed(role)) != 1:
                e.append(f"unit {u.number}: exactly one {role.upper()} line ({len(u.fixed(role))} found)")
        if not u.bullets:
            e.append(f"unit {u.number}: at least one bullet between HOOK and PUNCH")
        roles = [x.role if x.kind == "fixed" else "bullet" for x in u.lines]
        if roles and roles[0] != "hook":
            e.append(f"unit {u.number}: HOOK is the first line")
        if "punch" in roles:
            after = roles[roles.index("punch") + 1:]
            if any(r not in ("ask", "bridge") for r in after):
                e.append(f"unit {u.number}: after PUNCH only the ask and the bridge")
            before = roles[1:roles.index("punch")]
            if any(r != "bullet" for r in before):
                e.append(f"unit {u.number}: between HOOK and PUNCH only bullets")
        if len(u.fixed("bridge")) > 1:
            e.append(f"unit {u.number}: at most one BRIDGE line (a bridge is optional; the count word is enough)")
    close = sheet.part("close")
    if close is not None:
        if len(close.fixed("verdict")) < 1 or len(close.fixed("link")) != 1:
            e.append("the close has a VERDICT line and one LINK line")
        elif close.lines[-1].role != "link":
            e.append("the LINK line is the last line")
    asks = [x for p in sheet.parts for x in p.lines if x.kind == "fixed" and x.role == "ask"]
    if len(asks) > 1:
        e.append(f"{len(asks)} ask lines: the fixed ask comes once per video")


def read(path: str | Path) -> CueSheet:
    return parse(Path(path).read_text(encoding="utf-8"))


def spoken_text(sheet: CueSheet) -> str:
    """The fixed lines in order, as plain text (for tools that only need the words that are certain to be said)."""
    return "\n".join(x.spoken for _, x in sheet.fixed_lines())


__all__ = ["CueSheet", "Line", "NAME", "Part", "is_cue_sheet", "is_name", "looks_like", "parse", "read",
           "spoken_text"]
