"""Blender plates of a custom motion piece never rent without an accepted spend card (motion plan 3.3 check 4). The
cap of that card is the motion plan's number. Fake Vast API and fake SSH, nothing real is rented."""

from __future__ import annotations

import json

import pytest

from crewcut import approvals, db, paths
from crewcut.compute.errors import NeedsApproval
from crewcut.motion import plates

EP = "001-plates"


def _episode(studio):
    ep = paths.episode_dir(EP)
    (ep / "motion" / "m3" / "plates").mkdir(parents=True)
    (ep / "project.json").write_text(json.dumps({"id": EP, "format": "landscape"}))
    (ep / "motion" / "m3" / "plates" / "gpu3d.py").write_text("# a plate generator\n")
    plan = {"inserts": [{"id": "m3", "kind": "motion", "source": "motion/m3/comp.jsx", "start": 1, "end": 6,
                         "plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0},
                                     "frames": 4}]}]}
    return ep, plan


def test_a_plate_job_waits_for_the_spend_card(fake, fssh, studio):
    ep, plan = _episode(studio)
    todo = plates.jobs(ep, plan)
    assert [(j["insert"], j["id"], j["missing"]) for j in todo] == [("m3", "gpu", True)]
    assert todo[0]["out"].parent == ep / "render" / "plates" and len(todo[0]["hash"]) == plates.HASH_LEN
    ran = []
    with pytest.raises(NeedsApproval) as e:
        plates.rent(EP, todo, lambda m, j: ran.append(j["id"]), cap_usd=2.0, monitor=False, log=lambda *_: None)
    assert not fake.instances and not fake.created, "nothing is rented before the yes"
    assert ran == []
    card = approvals.get(e.value.card_id)
    assert card["kind"] == "spend" and card["status"] == "open" and card["data"]["cap_usd"] == 2.0
    assert "plates" in card["data"]["purpose"]
    db.update("cards", card["id"], status="accepted", decided_at=db.now())
    rows = plates.rent(EP, todo, lambda m, j: ran.append(j["id"]) or "ok", cap_usd=2.0, monitor=False,
                       log=lambda *_: None)
    assert ran == ["gpu"] and rows == [{"plate": "gpu", "insert": "m3", "result": "ok"}]
    assert not fake.by_label(fake.created[0]["label"]), "leaving the session deletes the machine"


def test_the_cap_comes_from_the_motion_plan(studio):
    ep, _plan = _episode(studio)
    assert plates.cap_for(ep) == 2.0
    (ep / "project.json").write_text(json.dumps({"id": EP, "format": "portrait", "kind": "short"}))
    assert plates.cap_for(ep) == 0.5


def test_a_changed_plate_script_gets_a_new_hash(studio):
    ep, plan = _episode(studio)
    h1 = plates.jobs(ep, plan)[0]["hash"]
    (ep / "motion" / "m3" / "plates" / "gpu3d.py").write_text("# changed\n")
    assert plates.jobs(ep, plan)[0]["hash"] != h1
    with pytest.raises(ValueError, match="not found"):
        plates.jobs(ep, {"inserts": [{"id": "m4", "kind": "motion", "plates": [{"id": "x", "script": "nope.py"}]}]})
