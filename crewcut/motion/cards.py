"""The four motion cards and what a yes or a no does (``approvals.decide`` calls this).

    motion-plan   one per video: the three columns (have, build new, upgrade), density and budget, the cap. Rows can be
                  struck before the yes (``director.strike``). Shelf pieces may be built while it is open; new pieces
                  and upgrades wait for the yes (``director.motion_gate``).
    style-frame   one per custom piece: our frame next to the reference (or the library sample), per format. Nothing
                  animated is built before the yes (``custom.style_frame_gate``).
    template      "Keep it in your library?": the promoted piece with its sample loops and params. Yes sets
                  ``approved``; no takes the new version out again (``library.withdraw``).
    baseline      the bar moves to a better video: old and new episode with their named strengths. Only a yes moves
                  it, and never down (``ratchet.apply_baseline``).
"""

from __future__ import annotations

KINDS = ("motion-plan", "style-frame", "template", "baseline")


def precheck(card: dict) -> None:
    """Before a yes is stored: raise ValueError when the card no longer shows what would be approved."""
    kind = card.get("kind")
    if kind == "motion-plan":
        from . import director
        director.check_card(card)
    elif kind == "template":
        from . import library
        library.check_card(card)
    elif kind == "baseline":
        from . import ratchet
        ratchet.check_baseline_card(card)


def on_decided(card: dict) -> None:
    """After the answer is stored."""
    kind, accepted = card.get("kind"), card.get("status") == "accepted"
    if kind == "template":
        from . import library
        (library.approve if accepted else library.withdraw)(card)
    elif kind == "baseline" and accepted:
        from . import ratchet
        ratchet.apply_baseline(card)
