"""Words for comparing what was said with what was expected. Language-neutral: lower case, no punctuation.

Speech recognition spells some words differently from the script (numbers, names). Those pairs live in
config/speech.toml [spelling] (the studio can add its own) and compare as equal.
"""

from __future__ import annotations

import re

from .. import config

_WORD = re.compile(r"[\w.'’\-]+", re.UNICODE)

# Built in: number words that recognizers write as digits (and the other way round).
_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10",
    "eins": "1", "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6", "sieben": "7", "acht": "8",
    "neun": "9", "zehn": "10",
}


def spelling() -> dict[str, str]:
    """Equal-meaning spellings: built-in number words plus config/speech.toml [spelling]."""
    out = dict(_NUMBERS)
    for k, v in (config.load("speech").get("spelling") or {}).items():
        out[str(k).lower()] = str(v).lower()
    return out


def tokens(text: str, same: dict[str, str] | None = None) -> list[str]:
    """'Cloud-Code, 5.5!' -> ['cloud', 'code', '5.5']. Hyphenated words split; dots stay inside numbers."""
    out = []
    for w in _WORD.findall(text.lower().replace("’", "'")):
        w = w.strip(".'-")
        for part in w.split("-"):
            part = part.strip(".'")
            if part:
                out.append((same or {}).get(part, part))
    return out


def raw_words(text: str) -> list[str]:
    """The words as written (with punctuation attached), for rebuilding text."""
    return text.split()
