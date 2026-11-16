"""Errors of the compute module. The CLI maps them to exit codes (see docs/architecture.md)."""

from __future__ import annotations


class ComputeError(Exception):
    """Something went wrong while renting or using a machine. Exit code 1."""

    exit_code = 1


class NoMachine(ComputeError):
    """No usable offer, or every tried machine failed its checks."""


class NeedsApproval(ComputeError):
    """A spend card is open. The agent waits for the user's yes (`crewcut card wait <id>`) and tries again. Exit 3."""

    exit_code = 3

    def __init__(self, card_id: int, reason: str = "waiting for a yes on the spend card"):
        self.card_id = int(card_id)
        self.reason = reason
        super().__init__(f"{reason} (card {card_id})")


class Refused(ComputeError):
    """Blocked by a rule: month cap, session cap, missing right, privacy, no credit. Exit 3."""

    exit_code = 3

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class MissingKey(ComputeError):
    """No provider key. Exit 4."""

    exit_code = 4
