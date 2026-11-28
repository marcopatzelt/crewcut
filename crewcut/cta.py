"""The channel's asks as data, and the word a viewer comments to get the link.

- A Short may end with a comment ask (channel.json ``script.short_ask``, for example
  "Wenn du das auch willst, kommentier {WORD}."): the punch line, then exactly this sentence with one word in capitals
  that fits what the viewer gets. Unset (the default): no ask in a Short at all.
- A long video's one fixed ask may end with a fixed text (``script.craft.ask_ends_with``, for example
  "der Link ist in der Videobeschreibung"). Unset: the fixed ask is the subscribe line.
- The upload package names the word and the link (``cta_keyword``, ``cta_url``). The pinned comment and the
  description name the word; crewcut/youtube/replies.py answers a comment that contains the word with the link
  (template: ``upload.cta_reply``).
"""

from __future__ import annotations

import re

WORD = r"[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9-]{1,23}"
PLACEHOLDER = "{WORD}"
URL_MAX = 40            # links in Shorts comments are often not clickable: short enough to type
REPLY_MAX = 500         # far below YouTube's comment limit; a reply is one short line
DEFAULT_REPLY = "Here is the link: {url}"
_QUOTES = "\"'„“”»«‚‘’"
_WORD_RX = re.compile(rf"{WORD}")


def is_keyword(word) -> bool:
    return isinstance(word, str) and _WORD_RX.fullmatch(word) is not None


def has_keyword(text: str, word: str) -> bool:
    """The word as a whole word, any case: "gpu!" and "Gpu bitte" count, "GPUs" and "eGPU" do not."""
    if not text or not word:
        return False
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w])", text, re.I) is not None


def _flex(part: str) -> str:
    """A template part as a pattern: any run of spaces matches any run of spaces."""
    return r"\s+".join(re.escape(t) for t in part.split())


def ask_pattern(template: str, anchored: bool = True) -> re.Pattern | None:
    """The comment ask as a pattern. The text around {WORD} matches in any case and spacing; the word itself must be
    in capitals (group "word"). None when the template has no {WORD}."""
    if not template or PLACEHOLDER not in template:
        return None
    before, _, after = template.partition(PLACEHOLDER)
    after = after.strip().rstrip(".!")
    pat = (_flex(before) + (r"\s+" if before[-1:].isspace() else "") + f"[{_QUOTES}]?" + rf"(?-i:(?P<word>{WORD}))"
           + f"[{_QUOTES}]?" + (r"\s*" if after and not after[:1].isalnum() else r"\s+" if after else "")
           + _flex(after))
    if anchored:
        pat = rf"^\s*{pat}\s*[.!]?\s*$"
    return re.compile(pat, re.I)


def ask_word(sentence: str, template: str) -> str | None:
    """The word of the comment ask when the whole sentence is exactly the ask, else None."""
    rx = ask_pattern(template)
    m = rx.match(" ".join(str(sentence).replace("**", "").split())) if rx else None
    return m.group("word") if m else None


def mentions_ask(sentence: str, template: str) -> bool:
    """The sentence holds the comment ask somewhere (a second ask in the middle of a Short)."""
    rx = ask_pattern(template, anchored=False)
    if rx is None:
        return False
    head = template.partition(PLACEHOLDER)[0].split()
    verb = head[-1].lower() if head else ""
    text = " ".join(str(sentence).split())
    return bool(rx.search(text)) or bool(verb and re.search(rf"\b{re.escape(verb)}\b", text, re.I))


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(s).lower()).split())


def ends_with(sentence: str, suffix: str) -> bool:
    """The sentence ends with the fixed text (case, punctuation and spacing do not matter)."""
    tail = _norm(suffix)
    return bool(tail) and (_norm(sentence) == tail or _norm(sentence).endswith(" " + tail))


def _pack(pack=None):
    if pack is not None:
        return pack
    try:
        from . import brand
        return brand.load()
    except Exception:  # noqa: BLE001 - a broken style pack means: no channel asks, never a crash
        return None


def _value(pack, dotted: str) -> str:
    p = _pack(pack)
    try:
        v = p.value(dotted) if p is not None else None
    except Exception:  # noqa: BLE001
        v = None
    return v.strip() if isinstance(v, str) else ""


def short_ask(pack=None) -> str:
    """channel.json script.short_ask, or "" (no ask in a Short)."""
    v = _value(pack, "channel.script.short_ask")
    return v if PLACEHOLDER in v else ""


def ask_end(pack=None) -> str:
    """channel.json script.craft.ask_ends_with, or "" (the fixed ask is the subscribe line)."""
    return _value(pack, "channel.script.craft.ask_ends_with")


def reply_text(url: str, pack=None) -> str:
    """The reply under a keyword comment: channel.json upload.cta_reply with {url} filled in."""
    template = _value(pack, "channel.upload.cta_reply") or DEFAULT_REPLY
    if "{url}" not in template:
        template = f"{template} {{url}}"
    return " ".join(template.replace("{url}", url).split())[:REPLY_MAX]


def package_problems(pkg: dict) -> tuple[list[str], list[str]]:
    """Errors and warnings of a package's cta fields. No cta fields: nothing to check."""
    word, url = pkg.get("cta_keyword"), pkg.get("cta_url")
    if not word and not url:
        return [], []
    errs: list[str] = []
    warns: list[str] = []
    if not word or not url:
        errs.append("cta_keyword and cta_url go together: the word viewers comment and the link they get")
        return errs, warns
    if not is_keyword(word):
        errs.append(f"cta_keyword {word!r} must be one word in capitals (A to Z, Ä, Ö, Ü, digits, hyphen), "
                    "2 to 24 characters")
    if not isinstance(url, str) or not url.strip() or re.search(r"[\s<>]", url):
        errs.append("cta_url must be one link without spaces, < or >")
    elif len(url) > URL_MAX:
        warns.append(f"cta_url has {len(url)} characters; keep it under {URL_MAX}: links in Shorts comments are often "
                     "not clickable, so viewers type it")
    if is_keyword(word):
        if not has_keyword(pkg.get("description") or "", word):
            errs.append(f"the description must name the word {word} and what viewers get for it")
        if not pkg.get("related_comment"):
            errs.append(f"related_comment (the pinned comment) is missing: it names the word {word} and what "
                        "viewers get for it")
        elif not has_keyword(pkg["related_comment"], word):
            errs.append(f"the pinned comment (related_comment) must name the word {word}")
    return errs, warns


__all__ = ["DEFAULT_REPLY", "PLACEHOLDER", "URL_MAX", "WORD", "ask_end", "ask_pattern", "ask_word", "ends_with",
           "has_keyword", "is_keyword", "mentions_ask", "package_problems", "reply_text", "short_ask"]
