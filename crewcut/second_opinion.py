"""A second opinion on the Critic's last verdict, from another model on the host computer.

When the Critic approves a script and everything else passes, the style gate asks a second reviewer before the card
goes to the user (a check of the studio's checker with `second_opinion: true` and an `answer_file`). The container
cannot run that model itself, so the request goes to the host helper (host/crewcut-host.sh, job "second-opinion"),
like the YouTube setup: a small signed request file that names the script, the Critic's verdict and the answer file,
all inside the studio. The helper runs its own command from the host's environment (CREWCUT_SECOND_OPINION_CMD) on its
own fixed prompt (host/prompts/second-opinion.md), at most CREWCUT_SECOND_OPINION_PARALLEL runs at a time (default 2),
and writes the raw output to studio/.crewcut/host/runs/<id>.json. tick() turns that output into the answer file:

    {"status": "ok", "agree": true|false, "points": [{"text", "why", "rewrite"}], "model", "checksum", "at"}
    {"status": "unavailable", "reason": "…", "at"}        the helper does not run, has no command, timed out, quota …
    {"status": "requested", "id", "at"}                      waiting

An unavailable second opinion never blocks: the card says why it is missing. A second opinion that disagrees sends its
points to the Writer like any other finding.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from . import db, paths

KIND = "second-opinion"
TIMEOUT_S = 900          # no answer after 15 minutes: unavailable
EVERY_S = 5.0            # how often tick() looks for answers
_last = 0.0


def box() -> Path:
    return paths.studio_root() / ".crewcut" / "host"


def prompt_file() -> Path:
    return paths.app_root() / "host" / "prompts" / "second-opinion.md"


def prompt_sha256() -> str:
    return hashlib.sha256(prompt_file().read_bytes()).hexdigest()


FIELDS = ("kind", "id", "at", "nonce", "prompt_sha256", "file", "verdict", "answer")


def sign(fields: dict) -> str:
    from .youtube import connect
    msg = ";".join(f"{k}={fields[k]}" for k in FIELDS)
    return hmac.new(connect.token().encode(), msg.encode(), hashlib.sha256).hexdigest()


def why_not() -> str | None:
    """Why no second opinion can be asked now, in one sentence; None when it can."""
    from .youtube import connect
    if not connect.token():
        return "the host helper has no key (CREWCUT_HOST_TOKEN; start Crewcut with ./start.sh once)"
    h = connect.helper()
    if not h:
        return "the host helper is not running (./start.sh starts it next to Docker)"
    if not h.get("second_opinion"):
        return "the host helper has no second-opinion command (CREWCUT_SECOND_OPINION_CMD on the host)"
    try:
        prompt_sha256()
    except OSError:
        return "the second-opinion prompt is missing (host/prompts/second-opinion.md)"
    return None


def _studio_rel(p: Path) -> str:
    """A path inside the studio, relative to it (the host maps it to its own studio folder)."""
    root = paths.studio_root().resolve()
    q = Path(p)
    if not q.is_absolute():
        q = root / q
    q = q.resolve()
    if q != root and root not in q.parents:
        raise ValueError(f"{p} is outside the studio")
    return q.relative_to(root).as_posix()


def _write(answer: Path, data: dict) -> None:
    answer.parent.mkdir(parents=True, exist_ok=True)
    tmp = answer.with_suffix(answer.suffix + ".tmp")
    tmp.write_text(json.dumps({**data, "at": int(time.time())}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(answer)


def _pending() -> list[dict]:
    try:
        return json.loads(db.kv_get("second_opinion:pending") or "[]")
    except ValueError:
        return []


def _set_pending(items: list[dict]) -> None:
    db.kv_set("second_opinion:pending", json.dumps(items))


def request(episode: str, script: Path, answer: Path, verdict: Path) -> dict:
    """Ask the host helper for a second opinion, or write why it cannot be had. Never raises for a missing helper."""
    answer = Path(answer)
    # the checker names the answer file as its own path; map a container path under the studio to this studio
    try:
        rel_answer = _studio_rel(answer)
        answer = paths.studio_root() / rel_answer
    except ValueError:
        return {"status": "error", "reason": f"answer file outside the studio: {answer}"}
    reason = why_not()
    if reason is None and not Path(verdict).is_file():
        reason = f"the Critic's verdict file is missing ({Path(verdict).name})"
    if reason:
        _write(answer, {"status": "unavailable", "reason": reason})
        return {"status": "unavailable", "reason": reason, "answer": rel_answer}
    rid = f"so-{int(time.time())}-{secrets.token_hex(3)}"
    fields = {"kind": KIND, "id": rid, "at": str(int(time.time())), "nonce": secrets.token_hex(16),
              "prompt_sha256": prompt_sha256(), "file": _studio_rel(script), "verdict": _studio_rel(verdict),
              "answer": rel_answer}
    fields["sig"] = sign(fields)
    d = box() / "requests"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{rid}.tmp"
    tmp.write_text("".join(f"{k}={v}\n" for k, v in fields.items()), encoding="utf-8")
    tmp.rename(d / f"{rid}.req")
    _write(answer, {"status": "requested", "id": rid})
    _set_pending(_pending() + [{"id": rid, "episode": episode, "answer": rel_answer, "at": int(time.time())}])
    return {"status": "requested", "id": rid, "answer": rel_answer}


JSON_OBJ = re.compile(r"\{.*\}", re.S)


def parse(raw: str) -> dict:
    """The answer file from the host command's output: a JSON object with agree and points, found in the command's
    own JSON envelope (a "response" or "result" text) or in the plain output."""
    text = raw or ""
    model = None
    try:
        env = json.loads(text)
        if isinstance(env, dict):
            st = str(env.get("status", "")).lower()
            if st and st not in ("ok", "success", "succeeded", "completed", "done"):
                return {"status": "unavailable", "reason": f"the second-opinion model answered {st}: "
                        + str(env.get("error") or env.get("message") or "")[:200]}
            model = env.get("model")
            if "agree" in env or "zustimmung" in env:
                text = json.dumps(env)
            else:
                text = str(env.get("response") or env.get("result") or env.get("text") or "")
    except ValueError:
        pass
    m = None
    for cand in sorted(JSON_OBJ.findall(text), key=len, reverse=True):
        try:
            m = json.loads(cand)
            break
        except ValueError:
            continue
    if not isinstance(m, dict):
        return {"status": "unavailable", "reason": "the second opinion gave no readable JSON answer"}
    agree = m.get("agree", m.get("zustimmung"))
    pts = []
    for p in m.get("points") or m.get("punkte") or []:
        if isinstance(p, dict):
            pts.append({"text": str(p.get("text") or p.get("satz") or ""), "why": p.get("why") or p.get("grund"),
                        "rewrite": p.get("rewrite") or p.get("neu")})
        elif str(p).strip():
            pts.append({"text": str(p)})
    return {"status": "ok", "agree": bool(agree) and not pts, "points": pts, "model": model or m.get("model"),
            "checksum": m.get("checksum") or m.get("pruefsumme")}


def tick(force: bool = False) -> list[dict]:
    """Turn finished host runs into answer files and let the style gate go on. Cheap: looks every few seconds."""
    global _last
    now = time.time()
    if not force and now - _last < EVERY_S:
        return []
    _last = now
    items = _pending()
    if not items:
        return []
    keep, done = [], []
    for it in items:
        out = box() / "runs" / f"{it['id']}.json"
        answer = paths.studio_root() / it["answer"]
        if out.is_file():
            data = parse(out.read_text(encoding="utf-8", errors="replace"))
        elif now - float(it.get("at", now)) > TIMEOUT_S:
            data = {"status": "unavailable", "reason": f"no answer from the second opinion within {TIMEOUT_S // 60} "
                    "minutes"}
        else:
            keep.append(it)
            continue
        _write(answer, data)
        done.append({**it, **data})
    _set_pending(keep)
    from . import stylegate
    for it in done:
        try:
            stylegate.after_second_opinion(it["episode"])
        except Exception:  # noqa: BLE001 - one episode's gate must not stop the others
            import traceback
            traceback.print_exc()
    return done


__all__ = ["KIND", "parse", "request", "tick", "why_not"]
