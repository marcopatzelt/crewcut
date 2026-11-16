#!/usr/bin/env python3
"""Measure the two crew modes on the demo episode: separate runs against the Showrunner with subagents.

Needs an engine login (CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY) and the Crewcut image; it spends subscription
usage. Run it in the image (the nightly workflow runs it on a manual dispatch with measure_crew=true and a login secret):

    python3 tools/ci/measure_crew_modes.py --out /out/crew-modes.json

The same task goes to the Editor once per mode, each in a fresh studio with the demo episode: read the edit plan, check
it against the style pack, render the 2D inserts and assemble the preview. Measured: success, wall time, turns, tokens,
the API-equivalent cost Claude Code reports, and whether the preview file exists.
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

TASK = ("Build the demo episode's preview from its edit plan (edit/plan-v001.json) with the edit skill: check the plan, "
        "render the 2D inserts locally, assemble the preview, then report in two sentences what you did. Do not propose "
        "cards and do not rent anything.")


def run_mode(mode: str, app: Path) -> dict:
    studio = Path(tempfile.mkdtemp(prefix=f"crew-{mode}-"))
    os.environ["CREWCUT_STUDIO"] = str(studio)
    (studio / "config").mkdir(parents=True)
    (studio / "config" / "crewcut.toml").write_text(f'[engine.claude]\ncrew = "{mode}"\n', encoding="utf-8")
    shutil.copytree(app / "examples" / "demo", studio / "episodes" / "000-demo")
    from crewcut import db, engines, team
    from crewcut.conductor import queue
    team._load_all.cache_clear()
    queue._PLUGIN.clear()
    jid = db.insert("jobs", episode="000-demo", step="edit", identity="editor", kind="agent", task=TASK, heavy=0,
                    status="queued", created=db.now(), data={})
    job = db.get("jobs", jid)
    eng = engines.get("claude")
    task = queue.build_task(job, eng, {})
    t0 = time.time()
    res = eng.run(task)
    out = studio / "episodes" / "000-demo" / "export" / "demo-v001-preview.mp4"
    return {"mode": mode, "ok": res.ok, "seconds": round(time.time() - t0, 1), "turns": res.turns,
            "usage": res.usage, "equiv_usd": res.cost_usd, "preview_exists": out.is_file(), "error": res.error[:300],
            "agent": task.agent}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="crew-modes.json")
    ap.add_argument("--modes", default="runs,subagents")
    a = ap.parse_args()
    if not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        print("No engine login: nothing measured.")
        return 4
    app = Path(os.environ.get("CREWCUT_APP", Path(__file__).resolve().parents[2]))
    results = [run_mode(m.strip(), app) for m in a.modes.split(",") if m.strip()]
    Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    for r in results:
        print(f"{r['mode']:<10} ok={r['ok']} {r['seconds']} s, {r['turns']} turns, ~${r['equiv_usd']:.2f} API equivalent,"
              f" preview={'yes' if r['preview_exists'] else 'no'}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
