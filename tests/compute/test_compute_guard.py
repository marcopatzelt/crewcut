"""The guard and the label filter: only our labelled machines are ever destroyed."""

from __future__ import annotations

import json
import time

import pytest

from crewcut import db, ledger
from crewcut.compute import cli, guard, rentals, state
from crewcut.compute import session as session_fn
from crewcut.compute.errors import NeedsApproval

EP = "002-guard"


def accept(card_id: int) -> None:
    db.update("cards", card_id, status="accepted", decided_at=db.now())


def rented(fake, gpus=1, minutes=30, cap=3.0, detached=False):
    s = session_fn(episode=EP, step="edit", purpose="test", cap_usd=cap, monitor=False, detached=detached).open()
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=gpus, max_minutes=minutes, final=gpus > 1)
    accept(e.value.card_id)
    return s, s.rent(gpus=gpus, max_minutes=minutes, final=gpus > 1)


def test_no_key_skips(studio):
    assert "skipped" in guard.sweep()


def test_sweep_touches_only_our_label(fake):
    label = state.label()
    foreign = fake.add_instance("someone-else")
    unlabelled = fake.add_instance(None, ip="host-8.test")
    other_studio = fake.add_instance("crewcut-ffffff", ip="host-7.test")
    orphan = fake.add_instance(label, ip="host-6.test", price=0.5, age_s=600)
    r = guard.sweep()
    assert r["ok"] and r["destroyed"] == [orphan]
    assert set(fake.instances) == {foreign, unlabelled, other_studio}
    assert r["foreign"] == 3
    assert "0 own machines left" in r["proof"]
    row = rentals.by_instance(orphan)
    assert row["status"] == "destroyed"
    booked = [x for x in ledger.rows() if x["ref"] == f"vast:{orphan}"]
    assert booked and booked[0]["amount_usd"] == pytest.approx(0.5 * 600 / 3600, abs=0.01)


def test_live_session_is_kept_and_a_dead_one_is_closed(fake, fssh, clock):
    s, (m,) = rented(fake)
    r = guard.sweep()
    assert m.instance in r["kept"] and not r["destroyed"]
    clock.advance(minutes=10)          # the heartbeat is stale: the renting process is gone
    r = guard.sweep()
    assert m.instance in r["destroyed"]
    assert not fake.instances
    assert state.get_session(s.id)["closed"]
    assert "0 own machines left" in state.get_session(s.id)["proof"]


def test_detached_session_lives_until_its_deadline(fake, fssh, clock):
    s, (m,) = rented(fake, minutes=30, detached=True)
    state.touch(m.rental, busy=True)   # a long render runs: busy machines are never idle
    clock.advance(minutes=20)
    assert m.instance in guard.sweep()["kept"]
    clock.advance(minutes=11)
    r = guard.sweep()
    assert m.instance in r["destroyed"]
    assert not fake.instances
    assert rentals.get(m.rental)["status"] == "destroyed"
    assert state.get_session(s.id)["closed"], "a detached session closes with its last machine"


def test_detached_session_cap_is_enforced_by_the_guard(fake, fssh, clock):
    s, machines = rented(fake, gpus=2, minutes=240, cap=0.3, detached=True)
    clock.advance(minutes=30)          # about $0.81/h x 0.5 h = $0.41 > $0.30
    r = guard.sweep()
    assert sorted(r["destroyed"]) == sorted(m.instance for m in machines)
    assert "cap" in (state.get_session(s.id)["stopped"] or "")


def test_vanished_machine_is_booked(fake, fssh, clock):
    s, (m,) = rented(fake, detached=True)
    del fake.instances[m.instance]     # the watchdog on the machine deleted it
    clock.advance(minutes=5)
    r = guard.sweep()
    assert m.instance in r["booked_gone"]
    assert rentals.get(m.rental)["status"] == "destroyed"
    assert any(x["ref"] == f"vast:{m.instance}" for x in ledger.rows(EP))


def test_unconfirmed_destroy_is_retried(fake, fssh, clock):
    s, (m,) = rented(fake)
    fake.ignore_destroy.add(m.instance)
    s.close()
    assert rentals.get(m.rental)["status"] == "lost"
    assert "1 own machine left" in state.get_session(s.id)["proof"]
    fake.ignore_destroy.clear()
    r = guard.sweep()
    assert m.instance in r["destroyed"]
    assert not fake.instances


def test_destroy_all_ours_leaves_foreign_machines(fake, fssh, capsys):
    s, machines = rented(fake, gpus=2, detached=True)
    foreign = fake.add_instance("someone-else")
    stray = fake.add_instance(state.label(), ip="host-5b.test")
    assert cli.main(["destroy", "--all-ours", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["left"] == 0 and "0 own machines left" in d["proof"] and "1 other machine in" in d["proof"]
    assert set(fake.instances) == {foreign}
    assert stray not in fake.instances
    assert state.get_session(s.id)["closed"]


def test_cli_guard_once(fake, capsys):
    fake.add_instance("someone-else")
    assert cli.main(["guard", "--once"]) == 0
    assert "1 other machine in the account (not touched)" in capsys.readouterr().out


def test_background_guard_starts_once_and_sweeps(fake):
    orphan = fake.add_instance(state.label(), ip="host-6.test")
    t1 = guard.start_background(every=3600)
    t2 = guard.start_background(every=3600)
    try:
        assert t1 is t2 and t1.daemon
        for _ in range(100):
            if orphan not in fake.instances:
                break
            time.sleep(0.02)
        assert orphan not in fake.instances
    finally:
        guard.stop_background()
    assert not t1.is_alive()


def test_an_idle_machine_is_deleted_and_a_busy_one_kept(fake, fssh, clock):
    s, (m,) = rented(fake, minutes=120, detached=True)
    state.touch(m.rental, busy=False)                       # the last command ended now
    clock.advance(minutes=4)
    assert m.instance in guard.sweep()["kept"]
    clock.advance(minutes=2)                                # 6 min without work > idle_minutes (5)
    assert m.instance in guard.sweep()["destroyed"]
    assert rentals.get(m.rental)["status"] == "destroyed"


def test_several_gpus_only_for_the_final_render(fake, fssh, clock):
    from crewcut.compute.errors import Refused
    s = session_fn(episode=EP, step="edit", purpose="test", cap_usd=3.0, monitor=False).open()
    with pytest.raises(Refused, match="final render"):
        s.rent(gpus=4, max_minutes=30)
