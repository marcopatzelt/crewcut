"""Cards: one decision, one yes. Approving a file approves exactly that version (sha256 at the time of the card)."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from . import brand, config, db, events, ledger, paths

KINDS = ("topic", "title", "proof", "script", "mix", "preview", "final", "thumbnail", "publish", "spend", "rule",
         "profile", "other")


class RightsError(PermissionError):
    pass


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _resolve_file(episode: str | None, file: str | None) -> Path | None:
    if not file:
        return None
    base = paths.episode_dir(episode) if episode and not episode.startswith("_") else paths.studio_root()
    p = Path(file)
    if p.is_absolute():
        p = p.resolve()
        root = paths.studio_root().resolve()
        if root not in p.parents:
            raise ValueError("a card can only show files inside the studio folder")
        return p
    return paths.inside(base, file)


def propose(episode: str | None, step: str | None, kind: str, title: str, body: str = "", file: str | None = None,
            options: list[str] | None = None, data: dict | None = None, identity: str | None = None,
            preview: str | None = None, job: int | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown card kind {kind}; use one of {', '.join(KINDS)}")
    identity = identity or os.environ.get("CREWCUT_IDENTITY")
    job = job or (int(os.environ["CREWCUT_JOB"]) if os.environ.get("CREWCUT_JOB", "").isdigit() else None)
    digest = None
    p = _resolve_file(episode, file)
    if p is not None:
        if not p.is_file():
            raise FileNotFoundError(f"card file not found: {file}")
        digest = sha256(p)
    cid = db.insert("cards", episode=episode, step=step, kind=kind, identity=identity, title=title, body=body,
                    file=file, sha256=digest, preview=preview, options=options or [], data=data or {},
                    status="open", created=db.now(), job=job)
    if episode:
        db.insert("messages", at=db.now(), episode=episode, author=identity or "showrunner", text=title, card=cid,
                  job=job)
    card = get(cid)
    events.emit("card", episode=episode, identity=identity, text=title, data=card)
    if job:
        db.update("jobs", job, status="waiting", doing=f"Waiting for your yes: {title}")
        events.emit("activity", episode=episode, identity=identity, data={"job": job, "status": "waiting"})
    return card


def get(card_id: int) -> dict | None:
    return db.get("cards", card_id)


def list_cards(episode: str | None = None, status: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM cards WHERE 1=1", []
    if episode:
        q += " AND episode = ?"
        args.append(episode)
    if status:
        q += " AND status = ?"
        args.append(status)
    with db.conn() as c:
        return db.rows(c.execute(q + " ORDER BY id", args))


def decide(card_id: int, accepted: bool, choice: int | None = None, reason: str | None = None) -> dict:
    card = get(card_id)
    if card is None:
        raise KeyError(f"no card {card_id}")
    if card["status"] != "open":
        return card
    if accepted and card.get("sha256"):
        p = _resolve_file(card["episode"], card["file"])
        if p is None or not p.is_file() or sha256(p) != card["sha256"]:
            raise ValueError("The file changed after this card was made. Approving it would approve something you did "
                             "not see; the agent makes a new version and a new card.")
    if accepted and card["options"] and choice is not None and not 0 <= choice < len(card["options"]):
        raise ValueError("choice out of range")
    db.update("cards", card_id, status="accepted" if accepted else "declined", choice=choice, reason=reason,
              decided_at=db.now())
    card = get(card_id)
    if accepted and card["kind"] == "rule":
        _write_rule(card)
    if card.get("job"):
        j = db.get("jobs", card["job"])
        if j and j["status"] == "waiting":
            db.update("jobs", card["job"], status="done", ended=j.get("ended") or db.now(),
                      doing="Answered: " + ("yes" if accepted else "change requested"))
    events.emit("card", episode=card["episode"], identity=card["identity"], text=card["title"], data=card)
    from .conductor import flow  # late import: the conductor reacts to the answer (next step, new version, ...)
    flow.on_card_decided(card)
    return card


def wait(card_id: int, timeout: float | None = None, every: float = 2.0) -> str:
    """Block until the card is decided. Returns accepted, declined or expired (timeout)."""
    def check():
        c = get(card_id)
        return c["status"] if c and c["status"] != "open" else None
    st = db.wait_until(check, timeout=timeout, every=every)
    return st or "expired"


# ---- rules ---------------------------------------------------------------------------------------------------------
def ensure_user_pack() -> Path:
    """Create studio/brand from the neutral pack the first time something user-owned is written."""
    dst = paths.user_brand_dir()
    if not (dst / "brand.json").is_file():
        src = paths.neutral_pack_dir()
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dst / item.name
            if target.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    return dst


def _write_rule(card: dict) -> None:
    data = card.get("data") or {}
    step, rule, source = data.get("step") or card.get("step"), data.get("rule"), data.get("source", "")
    if not (step and rule):
        return
    d = ensure_user_pack() / "rules"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{Path(step).name}.md"
    text = p.read_text(encoding="utf-8") if p.is_file() else f"# Rules for {step}\n\n"
    if not text.endswith("\n"):
        text += "\n"
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    p.write_text(text + brand.format_rule(date, rule, source) + "\n", encoding="utf-8")


def propose_rule(step: str, rule: str, source: str, episode: str | None = None, identity: str | None = None) -> dict:
    return propose(episode, step, "rule", f"New rule for {step}: {rule}", body=f"Source: {source}",
                   data={"step": step, "rule": rule, "source": source}, identity=identity)


# ---- rights and money ----------------------------------------------------------------------------------------------
def require_right(right: str, identity: str | None = None) -> None:
    """Raise RightsError if the running identity may not do this. A human at the command line (no identity) may."""
    from . import team
    identity = identity or os.environ.get("CREWCUT_IDENTITY")
    if not identity:
        return
    ident = team.get(identity)
    if ident is None or not ident.get(f"may_{right}", False):
        raise RightsError(f"{identity} may not {right}. Ask the crew member who may (see team/README.md).")


def budget_for(episode: str | None) -> float:
    """Sum of accepted spend budgets for this episode (or for no episode)."""
    total = 0.0
    for c in list_cards(episode=episode, status="accepted"):
        if c["kind"] == "spend":
            total += float((c.get("data") or {}).get("budget_usd", 0) or 0)
    return round(total, 4)


def require_spend(episode: str | None, amount_usd: float, title: str, body: str = "", data: dict | None = None,
                  identity: str | None = None, reserved_usd: float = 0.0) -> tuple[bool, int | None, str]:
    """Is this spend covered? Returns (ok, card_id, reason).

    ok when the month cap has room and the episode's accepted budget covers what was spent, what is reserved by
    running rentals and the new amount. Otherwise a spend card is proposed (unless the month cap blocks it).
    """
    require_right("spend", identity)
    amount_usd = float(amount_usd)
    if ledger.month_left() - reserved_usd < amount_usd:
        return False, None, (f"The month cap of ${ledger.month_cap():.2f} is reached or too close. Renting stops. "
                             "Raise money.cap_month_usd in studio/config/crewcut.toml to continue.")
    spent = ledger.totals(episode).get("episode_usd", 0.0) if episode else 0.0
    if spent + reserved_usd + amount_usd <= budget_for(episode) + 1e-9:
        return True, None, "inside the approved budget"
    default_budget = float(config.get("crewcut", "money.default_episode_budget_usd", 5.0))
    cap = (data or {}).get("cap_usd")
    budget = round(max(amount_usd, float(cap) if cap else min(default_budget, ledger.month_left())), 2)
    d = {**(data or {}), "amount_usd": round(amount_usd, 4), "budget_usd": budget}
    card = propose(episode, (data or {}).get("step"), "spend", title, body=body, data=d, identity=identity)
    return False, card["id"], "waiting for a yes on the spend card"
