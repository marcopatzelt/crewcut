"""The cost book. Real money only: rented GPUs and paid APIs. Subscription runs are not money (see jobs.equiv_usd)."""

from __future__ import annotations

from datetime import UTC, datetime

from . import config, db, events

KINDS = ("gpu", "api", "other")


def add(kind: str, amount_usd: float, detail: str = "", episode: str | None = None, step: str | None = None,
        ref: str | None = None) -> int:
    if kind not in KINDS:
        raise ValueError(f"unknown cost kind {kind}")
    i = db.insert("costs", at=db.now(), episode=episode, step=step, kind=kind, amount_usd=round(float(amount_usd), 4),
                  detail=detail, ref=ref)
    events.emit("cost", episode=episode, text=detail, data={"id": i, "kind": kind, "amount_usd": amount_usd})
    return i


def month_cap() -> float:
    return float(config.get("crewcut", "money.cap_month_usd", 20.0))


def _sum(where: str, args: tuple) -> float:
    with db.conn() as c:
        r = c.execute(f"SELECT COALESCE(SUM(amount_usd), 0) AS s FROM costs WHERE {where}", args).fetchone()
        return round(float(r["s"]), 4)


def totals(episode: str | None = None) -> dict:
    t = datetime.now(UTC)
    today = t.strftime("%Y-%m-%d")
    month = t.strftime("%Y-%m")
    out = {
        "today_usd": _sum("substr(at, 1, 10) = ?", (today,)),
        "month_usd": _sum("substr(at, 1, 7) = ?", (month,)),
        "cap_month_usd": month_cap(),
    }
    if episode:
        out["episode_usd"] = _sum("episode = ?", (episode,))
    return out


def by_episode() -> dict[str, float]:
    with db.conn() as c:
        return {r["episode"]: round(float(r["s"]), 4) for r in
                c.execute("SELECT episode, SUM(amount_usd) AS s FROM costs WHERE episode IS NOT NULL GROUP BY episode")}


def rows(episode: str | None = None, limit: int = 200) -> list[dict]:
    with db.conn() as c:
        if episode:
            q = c.execute("SELECT * FROM costs WHERE episode = ? ORDER BY id DESC LIMIT ?", (episode, limit))
        else:
            q = c.execute("SELECT * FROM costs ORDER BY id DESC LIMIT ?", (limit,))
        return db.rows(q)


def month_left() -> float:
    return round(month_cap() - totals()["month_usd"], 4)
