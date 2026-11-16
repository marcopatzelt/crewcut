"""Rented GPUs, never required: estimate both ways, rent with a yes and a cap, run, fetch, destroy, guard.

    from crewcut import compute
    est = compute.estimate(kind="blender", frames=840)
    with compute.session(episode="003-x", step="edit", purpose="3D scenes", cap_usd=1.5) as s:
        m = s.rent(gpus=2, max_minutes=60)[0]
        m.put([path], "/work/"); rc, out = m.run("cmd", timeout=600); m.get("/work/out/", local_dir)
    compute.guard.sweep()

See docs/compute.md.
"""

from __future__ import annotations

from . import guard, local
from .errors import ComputeError, MissingKey, NeedsApproval, NoMachine, Refused
from .estimate import estimate, local_is_fine
from .local import record as record_probe
from .session import Machine, Session, session

__all__ = ["ComputeError", "Machine", "MissingKey", "NeedsApproval", "NoMachine", "Refused", "Session", "estimate",
           "guard", "local", "local_is_fine", "record_probe", "session"]
