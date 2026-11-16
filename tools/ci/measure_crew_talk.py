#!/usr/bin/env python3
"""Measure crew talk on the demo episode: three runs without, three with. Prepared; needs the user's yes to run.

Needs an engine login and the Crewcut image; spends subscription usage. Never run it on the user's own computer.

    python3 tools/ci/measure_crew_talk.py --runs 3 --out crew-talk.json

Each run starts from a fresh studio with the demo episode and its edit plan and plants a known weakness the demo allows
(a graphic six frames after its moment; the pause and the half word of the plan need a demo with recorded speech, which
the repository does not ship, so they are listed but planted only when such a demo is given), then gives the Critic
the cut check and lets the conductor carry on until a preview card is proposed or the time limit is reached. The
numbers come from the job and crew-message tables of that studio.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PLANTED = ["counter graphic six frames after its moment"]
NOT_PLANTABLE_IN_DEMO = ["pause 0.8 s too long at a join", "half word at a join"]


def plant(plan_path: Path) -> None:
    """Make the demo plan carry the three known weaknesses (data only, no media is touched)."""
    p = json.loads(plan_path.read_text(encoding="utf-8"))
    for ins in p.get("inserts", []):
        if ins.get("scene") == "counter":
            ins["start"] = round(float(ins["start"]) + 0.24, 2)   # six frames late at 25 fps
            break
    p.setdefault("_planted_for_measurement", PLANTED)
    plan_path.write_text(json.dumps(p, indent=1), encoding="utf-8")


def one_run(with_talk: bool, app: Path, limit_s: int) -> dict:
    studio = Path(tempfile.mkdtemp(prefix=f"talk-{'on' if with_talk else 'off'}-"))
    os.environ["CREWCUT_STUDIO"] = str(studio)
    (studio / "config").mkdir(parents=True)
    (studio / "config" / "crewcut.toml").write_text(f"[crew.talk]\nenabled = {str(with_talk).lower()}\n",
                                                   encoding="utf-8")
    shutil.copytree(app / "examples" / "demo", studio / "episodes" / "000-demo")
    plant(studio / "episodes" / "000-demo" / "edit" / "plan-v001.json")
    from crewcut import db
    from crewcut.conductor import queue
    queue._PLUGIN.clear()
    queue.add("000-demo", "critic", "edit", "Check the demo cut against the style pack and the plan with the cut-check "
              "skill. Report every finding; the Editor fixes them.")
    w = queue.Worker()
    t0 = time.time()
    while time.time() - t0 < limit_s:
        w.tick()
        with db.conn() as c:
            open_cards = c.execute("SELECT COUNT(*) AS n FROM cards WHERE kind = 'preview'").fetchone()["n"]
            busy = c.execute("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')").fetchone()["n"]
        if open_cards or not busy:
            break
        time.sleep(5)
    with db.conn() as c:
        jobs = db.rows(c.execute("SELECT identity, equiv_usd, data FROM jobs"))
        try:
            msgs = db.rows(c.execute("SELECT kind, topic, route FROM crew_messages"))
        except Exception:  # noqa: BLE001 - the table exists only when crew talk wrote something
            msgs = []
    per = {}
    for j in jobs:
        per.setdefault(j["identity"], 0.0)
        per[j["identity"]] += float(j["equiv_usd"] or 0)
    versions = len(list((studio / "episodes" / "000-demo" / "export").glob("*preview*.mp4")))
    return {"crew_talk": with_talk, "seconds": round(time.time() - t0, 1), "equiv_usd_by_member": per,
            "equiv_usd": round(sum(per.values()), 3), "jobs": len(jobs), "showrunner_turns":
            sum(1 for j in jobs if j["identity"] == "showrunner"), "preview_versions": versions,
            "crew_messages": len(msgs), "topics": len({m["topic"] for m in msgs}),
            "planted": PLANTED, "not_planted": NOT_PLANTABLE_IN_DEMO,
            "found_and_fixed": "count by hand from review/ and the log"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--limit-minutes", type=int, default=60)
    ap.add_argument("--out", default="crew-talk.json")
    a = ap.parse_args()
    if not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        print("No engine login: nothing measured.")
        return 4
    app = Path(os.environ.get("CREWCUT_APP", Path(__file__).resolve().parents[2]))
    results = []
    for i in range(a.runs):
        for with_talk in (False, True):
            r = one_run(with_talk, app, a.limit_minutes * 60)
            r["run"] = i + 1
            results.append(r)
            print(json.dumps(r))
    Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
