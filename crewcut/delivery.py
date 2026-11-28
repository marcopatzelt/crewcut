"""The delivery guide and the reading version of a script (docs/hormozi-voice.md, part 6).

A studio can describe how its reference speaker delivers a script (where he stresses, pauses, speeds up and slows
down, how he says numbers, contrasts and punch lines) in a delivery guide, together with the sentence shapes in the
text that force that delivery when the script is read aloud. While the studio names a guide, the Writer, the Critic
and the Showrunner are told to read it in the script step: the Writer applies its text shapes, the Critic checks them.

With a reading prefix, the Writer also writes a reading version of the full script once the script passes the style
gate: brief/<prefix>SCRIPT-vNNN.md (or <prefix>SHORT-vNNN.md), the same words as the script with three marks for the
speaker, who reads it once before he records:

- a stressed word in CAPITALS ("Das hat NEUN Minuten gedauert."),
- ` / ` a short pause, a beat that draws attention to what follows,
- ` // ` a long pause, before the reveal or after the punch line.

The marks never go into the script itself: the script and the cue sheet stay plain speaking text for the gate, the
Critic and the teleprompter. The prefix keeps the reading version out of every script glob, so neither the gate nor
the teleprompter's default mistakes it for the script; the teleprompter shows it when it is selected (`crewcut
prompter select`). `crewcut voice reading <file>` checks it: the same words as the script (marks and capitals aside),
marks only between words and never inside a [picture cue], at most `reading_max_stress` stressed words per sentence
and one long pause per paragraph, and at least one mark.

Settings (`[style_gate]` in config/crewcut.toml or `script.style_gate` in the style pack): `delivery_guide` (a file
inside the studio), `reading_prefix` (for example "LESEN-"; none = no reading version), `reading_max_stress`
(default 2).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PAUSE, LONG = "/", "//"
MARKS = (PAUSE, LONG)
DEFAULT_MAX_STRESS = 2
_SENTENCE_END = re.compile(r"[.!?][\"“”»«')\]]*$")


# ---- settings ------------------------------------------------------------------------------------------------------
def settings() -> dict:
    from . import stylegate
    cfg = stylegate.settings()
    try:
        most = max(1, int(cfg.get("reading_max_stress") or DEFAULT_MAX_STRESS))
    except (TypeError, ValueError):
        most = DEFAULT_MAX_STRESS
    prefix = str(cfg.get("reading_prefix") or "").strip()
    return {"delivery_guide": cfg.get("delivery_guide"), "reading_prefix": prefix or None,
            "reading_max_stress": most}


def _studio_file(rel) -> Path | None:
    from . import paths
    if not rel:
        return None
    p = Path(str(rel)).expanduser()
    p = p if p.is_absolute() else paths.studio_root() / p
    return p if p.is_file() else None


def guide_path(cfg: dict | None = None) -> Path | None:
    return _studio_file((cfg or settings()).get("delivery_guide"))


def reading_name(script: str, cfg: dict | None = None) -> str | None:
    """brief/<prefix><script name>, or None when the studio writes no reading version."""
    prefix = (cfg or settings()).get("reading_prefix")
    return f"{prefix}{Path(script).name}" if prefix else None


def script_of(reading: Path, cfg: dict | None = None) -> Path | None:
    prefix = (cfg or settings()).get("reading_prefix") or ""
    if not prefix or not reading.name.startswith(prefix):
        return None
    return reading.with_name(reading.name[len(prefix):])


def newest_full_script(episode: str) -> Path | None:
    """The newest full script of an episode (SCRIPT-vNNN or SHORT-vNNN, never a cue sheet)."""
    from . import paths, stylegate
    brief = paths.episode_dir(episode) / "brief"
    if not brief.is_dir():
        return None
    found = [p for p in brief.iterdir() if p.is_file() and (m := stylegate.NAME.match(p.name))
             and m.group("kind").upper() in ("SCRIPT", "SHORT")]
    return max(found, key=stylegate._version) if found else None


# ---- reading and checking ------------------------------------------------------------------------------------------
def _spoken_part(text: str) -> str:
    """Everything above the first line that is only `---` (the notes below it are not read aloud)."""
    return re.split(r"(?m)^---\s*$", text, maxsplit=1)[0]


def _letters(tok: str) -> str:
    return re.sub(r"[^A-Za-zÄÖÜäöüßẞ]", "", tok)


def _is_caps(tok: str) -> bool:
    letters = _letters(tok)
    return len(letters) >= 2 and letters == letters.upper() and letters != letters.lower()


def strip_marks(text: str) -> str:
    """The reading version without its pause marks (capitals stay: compare with casefold)."""
    lines = []
    for line in text.splitlines():
        lines.append(" ".join(t for t in line.split() if t not in MARKS))
    return "\n".join(lines)


def check(reading: Path, script: Path | None = None, cfg: dict | None = None) -> dict:
    """Is the reading version the script, word for word, with marks a speaker can follow?
    Returns {"pass", "file", "script", "problems": [{"text", "why"}], "stats"}."""
    cfg = cfg or settings()
    script = script or script_of(reading, cfg)
    out = {"pass": False, "file": str(reading), "script": str(script) if script else None, "problems": [],
           "stats": {}}
    problems = out["problems"]
    if script is None or not script.is_file():
        problems.append({"text": reading.name, "why": "no script next to it: the name must be the reading prefix "
                                                      "plus the script's file name"})
        return out
    r_text = _spoken_part(reading.read_text(encoding="utf-8"))
    s_text = _spoken_part(script.read_text(encoding="utf-8"))
    s_tokens = s_text.split()
    s_caps = {t.casefold() for t in s_tokens if _is_caps(t)}
    s_slash = {t.casefold() for t in s_tokens if "/" in t}     # "24/7" in the script is a word, not a mark
    r_tokens = [t for t in r_text.split() if t not in MARKS]
    a = [t.casefold() for t in r_tokens]
    b = [t.casefold() for t in s_tokens]
    if a != b:
        i = next((k for k, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
        got = " ".join(r_tokens[max(0, i - 4):i + 5])
        want = " ".join(s_tokens[max(0, i - 4):i + 5])
        problems.append({"text": got or "(end of the reading version)",
                         "why": f"the words differ from the script at word {i + 1}: the script says \"{want}\". "
                                "The reading version changes no word, only adds marks"})
    stress = pauses = longs = sentences = 0
    most = cfg.get("reading_max_stress") or DEFAULT_MAX_STRESS
    for para in re.split(r"\n\s*\n", r_text):
        toks = para.split()
        if not toks or para.lstrip().startswith(("#", "<!--")):
            continue
        if toks[0] in MARKS or toks[-1] in MARKS:
            problems.append({"text": para.strip()[:120], "why": "a pause mark stands between two words, never at "
                                                                "the start or the end of a paragraph"})
        para_long = 0
        in_cue = False
        sent_stress, sent = 0, []
        for k, t in enumerate(toks):
            if t.startswith("["):
                in_cue = True
            if t in MARKS:
                if in_cue:
                    problems.append({"text": para.strip()[:120], "why": "no marks inside a [picture cue]"})
                if k and toks[k - 1] in MARKS:
                    problems.append({"text": para.strip()[:120], "why": "two pause marks in a row: use one"})
                if t == LONG:
                    longs += 1
                    para_long += 1
                else:
                    pauses += 1
            elif "/" in t and t.casefold() not in s_slash and not in_cue:
                problems.append({"text": t, "why": "a pause mark stands alone with a space on both sides (\" / \")"})
            else:
                sent.append(t)
                if not in_cue and _is_caps(t) and t.casefold() not in s_caps:
                    stress += 1
                    sent_stress += 1
            if t.endswith("]"):
                in_cue = False
            if t not in MARKS and not in_cue and _SENTENCE_END.search(t):
                sentences += 1
                if sent_stress > most:
                    problems.append({"text": " ".join(sent)[:140],
                                     "why": f"{sent_stress} stressed words in one sentence: at most {most}, or "
                                            "nothing stands out"})
                sent_stress, sent = 0, []
        if sent_stress > most:
            problems.append({"text": " ".join(sent)[:140], "why": f"{sent_stress} stressed words in one sentence: at "
                                                                   f"most {most}"})
        if sent:
            sentences += 1
        if para_long > 1:
            problems.append({"text": para.strip()[:120], "why": f"{para_long} long pauses in one paragraph: at most "
                                                                "one, before the reveal or after the punch line"})
    if not (stress or pauses or longs):
        problems.append({"text": reading.name, "why": "no marks: put the stressed word in CAPITALS and \" / \" or "
                                                      "\" // \" where the speaker pauses"})
    out["stats"] = {"sentences": sentences, "stressed": stress, "pauses": pauses, "long_pauses": longs}
    out["pass"] = not problems
    return out


# ---- what the crew is told -----------------------------------------------------------------------------------------
def guide_line(cfg: dict | None = None) -> str:
    """For the voice block of the Writer, the Critic and the Showrunner. "" without a guide."""
    p = guide_path(cfg)
    if p is None:
        return ""
    return (f"- Read the delivery guide {p}: how the reference speaker delivers a script (stress, pauses, tempo, "
            "numbers, contrasts, punch lines) and, in its part on the script text, the sentence shapes that force "
            "that delivery when the text is read aloud. The Writer builds every hook, proof and punch line in those "
            "shapes; the Critic checks the shapes the guide marks as checkable. The script itself stays plain "
            "speaking text: no delivery marks in a script or a cue sheet.")


def writer_task(episode: str, cfg: dict | None = None) -> str:
    """What the gate adds to the Writer's task once the script passes, as a clause that starts with "write the reading
    version ..." (the caller puts it into its sentence). "" when the studio writes none or the newest full script
    already has a reading version that passes."""
    try:
        return _writer_task(episode, cfg or settings())
    except (OSError, UnicodeDecodeError, ValueError):   # the reading version must never stop the gate
        return ""


def _writer_task(episode: str, cfg: dict) -> str:
    if not cfg.get("reading_prefix"):
        return ""
    script = newest_full_script(episode)
    if script is None:
        return ""
    reading = script.with_name(reading_name(script.name, cfg))
    if reading.is_file() and check(reading, script, cfg)["pass"]:
        return ""
    guide = guide_path(cfg)
    return (f"write the reading version brief/{reading.name} of the full script {script.name}: the same words, "
            "nothing added or changed, with three marks for the speaker" + (f" (the guide {guide}, its part on the "
            "reading version)" if guide else "") + ": the stressed word in CAPITALS (at most "
            f"{cfg.get('reading_max_stress') or DEFAULT_MAX_STRESS} per sentence, usually the number, the contrast "
            "word or the last word of the punch line), \" / \" for a short pause and \" // \" for the long pause "
            f"before a reveal or after a punch line (at most one per paragraph). Run `crewcut voice reading "
            f"brief/{reading.name}` until it passes, and name the file in the card body so the speaker can read it "
            "once before he records.")


# ---- command line --------------------------------------------------------------------------------------------------
def cli(file: str, script: str | None = None, as_json: bool = False) -> int:
    path = Path(file)
    if not path.is_file():
        print(f"{path} not found.", file=sys.stderr)
        return 2
    cfg = settings()
    if script is None and not cfg.get("reading_prefix"):
        m = re.match(r"^(.+?)(?=(?:SCRIPT|SHORT)-v\d)", path.name, re.I)   # the prefix from the name itself
        cfg = {**cfg, "reading_prefix": m.group(1) if m else None}
    res = check(path, Path(script) if script else None, cfg)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        st = res["stats"]
        print(("PASS" if res["pass"] else "FAIL") + f" {path.name}: " + (
            f"{st.get('sentences', 0)} sentences, {st.get('stressed', 0)} stressed words, {st.get('pauses', 0)} "
            f"pauses, {st.get('long_pauses', 0)} long pauses" if st else "not checked"))
        for p in res["problems"][:12]:
            print(f"  \"{p['text']}\": {p['why']}")
    return 0 if res["pass"] else 1


def add_parser(sub: argparse._SubParsersAction) -> None:
    r = sub.add_parser("reading", help="check the reading version of a script (delivery marks)")
    r.add_argument("file")
    r.add_argument("--script", help="the script it belongs to (default: the file name without the reading prefix)")
    r.add_argument("--json", action="store_true")


__all__ = ["check", "guide_line", "guide_path", "newest_full_script", "reading_name", "script_of", "settings",
           "strip_marks", "writer_task"]
