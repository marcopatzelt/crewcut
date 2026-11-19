"""Cards: one decision, one yes. Approving a file approves exactly that version (sha256 at the time of the card)."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from . import brand, config, db, events, ledger, paths

KINDS = ("topic", "title", "proof", "script", "mix", "preview", "final", "thumbnail", "publish", "spend", "rule",
         "profile", "other", "motion-plan", "style-frame", "template", "baseline")
MOTION_KINDS = ("motion-plan", "style-frame", "template", "baseline")   # what a yes does: crewcut/motion/cards.py


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
    if kind == "style-frame":
        from .motion import quality
        quality.check_card({"episode": episode, "data": data or {}, "file": file}, submit=True)
    p = _resolve_file(episode, file)
    if p is not None:
        if not p.is_file():
            raise FileNotFoundError(f"card file not found: {file}")
        digest = sha256(p)
    if kind == "publish" and episode and episode != "_onboarding" and not standing("shorts"):
        from . import episodes
        try:
            if episodes.read(episode).get("kind") == "short":
                data = {**(data or {}), "standing_offer": True}  # the quiet second button on a Short's card
        except FileNotFoundError:
            pass
    if episode and episode != "_onboarding":
        from . import humanize
        hz = humanize.for_card(paths.episode_dir(episode), kind, file)  # raises humanize.Missing for a script card
        if hz:
            data = {**(data or {}), "humanizer": hz}
    cid = db.insert("cards", episode=episode, step=step, kind=kind, identity=identity, title=title, body=body,
                    file=file, sha256=digest, preview=preview, options=options or [], data=data or {},
                    status="open", created=db.now(), job=job)
    if episode:
        db.insert("messages", at=db.now(), episode=episode, author=identity or "showrunner", text=title, card=cid,
                  job=job)
    card = get(cid)
    events.emit("card", episode=episode, identity=identity, text=title, data=view(card))
    if job:
        db.update("jobs", job, status="waiting", doing=f"Waiting for your yes: {title}")
        from .conductor import queue
        j = queue.get(job)
        if j:
            events.emit("activity", episode=episode, identity=identity, data=queue.job_view(j))
    return card


def get(card_id: int) -> dict | None:
    return db.get("cards", card_id)


def view(card: dict) -> dict:
    """A card as the UI sees it: plus the URL of its file."""
    out = dict(card)
    if card.get("file"):
        out["file_url"] = f"/api/files/{card.get('episode') or '_onboarding'}/{card['file']}"
    return out


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
    if accepted and card["kind"] in MOTION_KINDS:
        from .motion import cards as motion_cards
        motion_cards.precheck(card)
    if accepted and card["kind"] in ("preview", "final"):
        from .motion import quality
        quality.check_animations(card["episode"])
    db.update("cards", card_id, status="accepted" if accepted else "declined", choice=choice, reason=reason,
              decided_at=db.now())
    card = get(card_id)
    if accepted and card["kind"] == "rule":
        _write_rule(card)
    if card["kind"] in MOTION_KINDS:
        from .motion import cards as motion_cards
        motion_cards.on_decided(card)
    if accepted and card["kind"] == "publish" and choice == 1 and (card.get("data") or {}).get("standing_offer"):
        grant_standing("shorts", card)
    if card.get("job"):
        j = db.get("jobs", card["job"])
        if j and j["status"] == "waiting":
            db.update("jobs", card["job"], status="done", ended=j.get("ended") or db.now(),
                      doing="Answered: " + ("yes" if accepted else "change requested"))
            from .conductor import queue
            events.emit("activity", episode=card["episode"], identity=card["identity"],
                        data=queue.job_view(queue.get(card["job"])))
    events.emit("card", episode=card["episode"], identity=card["identity"], text=card["title"], data=view(card))
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


# ---- standing approval (Shorts only, never the default) -------------------------------------------------------------
# The user may say once "publish Shorts without asking" (or press the second button on a Short's publish card). It
# covers only Shorts, only after the Critic's Short check found 0 errors, only without third-party material, and not
# the first Short after the style pack changed. Every Short still goes up private first, is read back, and only then
# becomes public or scheduled. Each use is logged as an accepted publish card with the package checksum.
STANDING_KEY = "standing:{scope}"


def pack_fingerprint() -> str:
    h = hashlib.sha256()
    base = paths.brand_dir()
    for p in sorted(base.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def standing(scope: str = "shorts") -> dict | None:
    import json
    raw = db.kv_get(STANDING_KEY.format(scope=scope))
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def grant_standing(scope: str, card: dict | None = None) -> dict:
    import json
    s = {"scope": scope, "since": db.now(), "card": (card or {}).get("id"), "pack": pack_fingerprint()}
    db.kv_set(STANDING_KEY.format(scope=scope), json.dumps(s))
    events.emit("log", text=f"Standing approval for {scope} switched on")
    return s


def revoke_standing(scope: str = "shorts") -> None:
    db.kv_set(STANDING_KEY.format(scope=scope), "")
    events.emit("log", text=f"Standing approval for {scope} switched off")


def standing_covers(episode: str, pkg: dict) -> tuple[bool, str]:
    """(covered, why not) for publishing this Short under the standing approval."""
    from . import episodes
    s = standing("shorts")
    if not s:
        return False, "no standing approval"
    p = episodes.read(episode)
    if p.get("kind") != "short":
        return False, "only Shorts are covered; long videos always need a card"
    if pkg.get("third_party"):
        return False, "the Short contains material or a person from someone else"
    if s.get("pack") != pack_fingerprint():
        return False, "the style pack changed since the standing approval: this first Short needs a card"
    check = short_check_result(episode)
    if check is None:
        return False, "the Critic's Short check has not run on this version"
    if check:
        return False, f"the Critic's Short check found {check} error(s)"
    return True, ""


def short_check_result(episode: str) -> int | None:
    """Errors in the newest Short check report (review/short-check-*.json), or None when there is none."""
    import json
    rev = paths.episode_dir(episode) / "review"
    reps = sorted(rev.glob("short-check*.json"), key=lambda q: q.stat().st_mtime) if rev.is_dir() else []
    if not reps:
        return None
    try:
        d = json.loads(reps[-1].read_text(encoding="utf-8"))
    except ValueError:
        return None
    errs = d.get("errors")
    return len(errs) if isinstance(errs, list) else int(errs or 0)


def accept_under_standing(episode: str, package_rel: str) -> dict:
    """Record a publish under the standing approval as an accepted card for exactly this package (for the log)."""
    p = _resolve_file(episode, package_rel)
    card = propose(episode, "upload", "publish", "Published under your standing approval", file=package_rel,
                   data={"standing": True}, identity="publisher")
    db.update("cards", card["id"], status="accepted", decided_at=db.now(),
              reason="standing approval for Shorts", sha256=sha256(p) if p else None)
    return get(card["id"])


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
    if identity == "showrunner" and os.environ.get("CREWCUT_CREW_MODE") == "subagents":
        # one session holds the whole crew; the plugin's guard hook checks the subagent (agent_type). Money and
        # publishing stay gated below by the cards, checksums and caps in any mode.
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
