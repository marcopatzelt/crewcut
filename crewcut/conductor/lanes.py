"""The heavy lane: one heavy job at a time (render, transcription, assembly), across processes.

Agents call heavy tools through the `crewcut` command in their own processes, so the lane is a file lock in the studio
state, not a thread lock. A waiting tool says so in the Crew column.
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from .. import config, paths


@contextmanager
def heavy(what: str) -> Iterator[None]:
    slots = max(1, int(config.get("crewcut", "queue.heavy_parallel", 1)))
    files = [open(paths.state_dir() / f"heavy-{i}.lock", "w") for i in range(slots)]
    held = None
    job = os.environ.get("CREWCUT_JOB")
    announced = False
    try:
        while held is None:
            for f in files:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = f
                    break
                except BlockingIOError:
                    continue
            if held is None:
                if not announced and job and job.isdigit():
                    from . import queue
                    queue.set_doing(int(job), f"Waiting for the heavy lane: {what}")
                    announced = True
                time.sleep(2)
        if announced and job and job.isdigit():
            from . import queue
            queue.set_doing(int(job), what)
        yield
    finally:
        if held is not None:
            fcntl.flock(held, fcntl.LOCK_UN)
        for f in files:
            f.close()
