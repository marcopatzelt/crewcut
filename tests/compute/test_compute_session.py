"""Renting against the fake Vast API and the fake SSH runner: approval, cap, deadlines, probe, privacy, scrub."""

from __future__ import annotations

import json

import pytest

from crewcut import approvals, db, ledger
from crewcut.compute import Refused, cli, rentals, state, vast
from crewcut.compute import session as session_fn
from crewcut.compute.errors import ComputeError, NeedsApproval

EP = "001-test"


def accept(card_id: int) -> None:
    """The user's yes, as approvals.decide stores it (without waking the conductor)."""
    db.update("cards", card_id, status="accepted", decided_at=db.now())


def approved_session(fake, cap_usd=1.5, **kw):
    """Open a session and say yes to its spend card, as the user would."""
    s = session_fn(episode=EP, step="edit", purpose="3D scenes", cap_usd=cap_usd, monitor=False, **kw).open()
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=kw.get("gpus", 1))
    accept(e.value.card_id)
    return s


def messages(episode=EP) -> list[str]:
    with db.conn() as c:
        return [r["text"] for r in c.execute("SELECT text FROM messages WHERE episode = ? ORDER BY id", (episode,))]


def test_approval_flow_then_rent_and_leave(fake, fssh):
    with session_fn(episode=EP, step="edit", purpose="3D scenes", cap_usd=1.5, monitor=False) as s:
        with pytest.raises(NeedsApproval) as e:
            s.rent(gpus=2, max_minutes=60)
        card = approvals.get(e.value.card_id)
        assert card["kind"] == "spend" and card["status"] == "open"
        assert card["data"]["source"] == "compute" and card["data"]["amount_usd"] > 0
        assert not fake.instances, "nothing is rented before the yes"
        with pytest.raises(NeedsApproval) as again:
            s.rent(gpus=2, max_minutes=60)
        assert again.value.card_id == card["id"], "no second card while one is open"
        accept(card["id"])

        machines = s.rent(gpus=2, max_minutes=60)
        assert len(machines) == 2
        ips = {rentals.detail(rentals.get(m.rental))["host_ip"] for m in machines}
        assert len(ips) == 2, "never two machines on one host IP"
        assert all(rentals.get(m.rental)["status"] == "ready" for m in machines)
        assert [m.name for m in machines] == ["Rented GPU 1 of 2", "Rented GPU 2 of 2"]
        body = fake.created[0]
        assert body["label"] == state.label() and body["label"].startswith("crewcut-")
        assert "watchdog" in body["onstart"] and body["env"]["CREWCUT_DEADLINE"]
        assert fake.key not in json.dumps(fake.created), "the Vast key never goes to a machine"
        rc, out = machines[0].run("nvidia-smi -L", doing="rendering")
        assert rc == 0 and "rendered" in out
        assert fake.keys, "the studio key was registered"
    assert not fake.by_label(state.label()), "leaving the block destroys every machine"
    rows = [r for r in ledger.rows(EP) if r["kind"] == "gpu"]
    assert sum(1 for r in rows if r["ref"].startswith("vast:")) == 2
    proof = [r for r in rows if r["ref"].startswith("proof:")]
    assert proof and "0 own machines left" in proof[0]["detail"]
    assert "credit before" in proof[0]["detail"]
    assert all(r["status"] == "destroyed" for r in rentals.live()) or not rentals.live()


def test_cli_rent_waits_then_runs_fetches_destroys(fake, fssh, capsys, tmp_path):
    assert cli.main(["rent", "--episode", EP, "--gpus", "1", "--minutes", "30"]) == 3
    out = capsys.readouterr().out
    assert "spend card" in out
    card = approvals.list_cards(EP, status="open")[0]
    accept(card["id"])
    assert cli.main(["rent", "--episode", EP, "--gpus", "1", "--minutes", "30", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    mid = d["machines"][0]["machine"]
    scene = tmp_path / "scene.py"
    scene.write_text("print('scene')\n")
    assert cli.main(["put", str(mid), str(scene), "/work/"]) == 0
    assert cli.main(["run", str(mid), "--doing", "rendering", "--", "blender -b -P /work/scene.py"]) == 0
    assert "rendered" in capsys.readouterr().out
    fssh.remote_files = {"out/frame_0001.png": b"PNG", "out/log.txt": b"token sk-ant-oat01-AAAAAAAAAAAAAAAAAAAA\n"}
    dest = tmp_path / "render"
    assert cli.main(["fetch", str(mid), "/work/out/", str(dest)]) == 0
    assert "Removed secrets from 1" in capsys.readouterr().out
    assert b"sk-ant-" not in (dest / "out" / "log.txt").read_bytes()
    assert cli.main(["destroy", str(mid)]) == 0
    assert "0 own machines left" in capsys.readouterr().out
    assert not fake.instances
    assert cli.main(["ledger", "--episode", EP]) == 0
    assert "Rented GPU" in capsys.readouterr().out


def test_missing_key_is_exit_4(studio, capsys):
    assert cli.main(["rent", "--episode", EP]) == 4
    out = capsys.readouterr().out
    assert vast.KEYS_PAGE in out and "VAST_API_KEY" in out
    assert vast.REFERRAL_NOTE in out


def test_month_cap_refuses_without_a_card(fake, fssh, studio_config, capsys):
    studio_config("crewcut", "[money]\ncap_month_usd = 0.05\n")
    assert cli.main(["rent", "--episode", EP]) == 3
    assert "month cap" in capsys.readouterr().out
    assert not approvals.list_cards(EP)
    assert not fake.instances


def test_identity_without_spend_right_is_refused(fake, fssh, monkeypatch):
    from crewcut import team
    monkeypatch.setenv("CREWCUT_IDENTITY", "writer")
    monkeypatch.setattr(team, "get", lambda i: {"id": i, "may_spend": False})
    s = session_fn(episode=EP, purpose="x", cap_usd=1, monitor=False).open()
    with pytest.raises(Refused, match="may not spend"):
        s.rent()
    monkeypatch.setattr(team, "get", lambda i: {"id": i, "may_spend": True})
    with pytest.raises(NeedsApproval):
        s.rent()


def test_cap_stop_destroys_all_and_says_so(fake, fssh, clock):
    s = approved_session(fake, cap_usd=0.5)
    machines = s.rent(gpus=2, max_minutes=120)
    assert len(fake.by_label(state.label())) == 2
    clock.advance(minutes=20)
    assert s.check() is None
    clock.advance(minutes=30)          # about $0.41/h x 2 x 50 min = $0.68 > $0.50
    reason = s.check()
    assert reason and "cap" in reason
    assert not fake.by_label(state.label())
    assert all(rentals.get(m.rental)["status"] == "destroyed" for m in machines)
    assert any("Stopped renting" in t for t in messages())
    with pytest.raises(Refused):
        machines[0].run("echo hi")
    s.close()
    booked = sum(r["amount_usd"] for r in ledger.rows(EP) if r["kind"] == "gpu")
    assert booked == pytest.approx(s.spent(), abs=0.01)


def test_deadline_destroys_the_machine(fake, fssh, clock):
    s = approved_session(fake, cap_usd=3)
    (m,) = s.rent(gpus=1, max_minutes=10)
    clock.advance(minutes=11)
    assert s.check() is None, "a deadline is not a cap stop"
    assert rentals.get(m.rental)["status"] == "destroyed"
    assert not fake.instances


def test_failed_probe_blocks_the_host_and_takes_the_next_offer(fake, fssh):
    fssh.probe_fail.add("host-1.test")
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    assert rentals.detail(rentals.get(m.rental))["host_ip"] == "host-2.test"
    assert "host-1.test" in state.blocked()["hosts"]
    assert len(fake.created) == 2 and len(fake.instances) == 1
    s.close()
    assert sum(1 for r in ledger.rows(EP) if (r["ref"] or "").startswith("vast:")) == 2, "dropped machines cost too"


def test_unreachable_running_host_is_blocked(fake, fssh):
    fssh.unreachable.add("host-1.test")
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    assert rentals.detail(rentals.get(m.rental))["host_ip"] == "host-2.test"
    assert "host-1.test" in state.blocked()["hosts"]
    s.close()


def test_never_on_a_host_ip_with_a_machine_of_this_account(fake, fssh):
    fake.add_instance("someone-else", ip="host-1.test")
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    assert rentals.detail(rentals.get(m.rental))["host_ip"] != "host-1.test"
    s.close()
    assert len(fake.instances) == 1, "the foreign machine is untouched"


def test_image_pull_failure_falls_back_without_blocking(fake, fssh, studio):
    from crewcut.compute import settings
    fake.pull_fails_for.add(settings.get("vast.image"))
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    assert fake.created[-1]["image"] == settings.get("vast.fallback_image")
    assert state.image_failed_recently()
    assert not state.blocked()["hosts"]
    s.close()


def test_systematic_setup_failure_stops(fake, fssh):
    fssh.setup_rc = 2
    fssh.setup_out = "SETUP_FAIL 2: watchdog script missing\n"
    s = approved_session(fake)
    with pytest.raises(ComputeError, match="will not fix"):
        s.rent(gpus=1)
    assert len(fake.created) == 1
    assert not fake.instances


def test_credit_must_cover_the_worst_case(fake, fssh):
    fake.credit = 0.10
    s = approved_session(fake)
    with pytest.raises(Refused, match="credit"):
        s.rent(gpus=1)
    assert not fake.instances


def test_uploads_are_code_and_fonts_only(fake, fssh, tmp_path, studio):
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    ok = tmp_path / "scene.py"
    ok.write_text("x = 1\n")
    assert m.put([ok], "/work/") == 1
    for name, data in (("take.mp4", b"\0"), (".env", b"A=1"), ("voice.wav", b"\0")):
        p = tmp_path / name
        p.write_bytes(data)
        with pytest.raises(Refused):
            m.put([p], "/work/")
    leaky = tmp_path / "notes.txt"
    leaky.write_text("key sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV\n")
    with pytest.raises(Refused):
        m.put([leaky], "/work/")
    for folder in ("originals", "work"):
        raw = studio / "episodes" / EP / folder
        raw.mkdir(parents=True)
        (raw / "words.json").write_text("[]")
        with pytest.raises(Refused):
            m.put([raw / "words.json"], "/work/")
    scene_dir = studio / "episodes" / EP / "render" / "d1"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene.json").write_text("{}")
    assert m.put([scene_dir], "/work/") == 1
    s.close()


def test_fetch_scrubs_secrets_before_they_land(fake, fssh, tmp_path, monkeypatch):
    s = approved_session(fake)
    (m,) = s.rent(gpus=1)
    fssh.remote_files = {
        "frame_0001.png": b"\x89PNG" + fake.key.encode(),
        "setup.log": f"CONTAINER_API_KEY=abcdef0123456789\nAuthorization: Bearer xyz123\nvast {fake.key}\n".encode(),
        "clean.txt": b"nothing here\n",
    }
    dest = tmp_path / "out"
    r = m.get("/work/out/", dest)
    assert sorted(r["scrubbed"]) == ["frame_0001.png", "setup.log"]
    log = (dest / "setup.log").read_text()
    assert "abcdef0123456789" not in log and "xyz123" not in log and fake.key not in log
    assert fake.key.encode() not in (dest / "frame_0001.png").read_bytes()
    assert (dest / "clean.txt").read_text() == "nothing here\n"
    assert any("Removed secrets" in t for t in messages())
    s.close()


def test_credit_call_keeps_only_the_credit(fake):
    v = vast.from_env()
    assert v.credit() == 50.0


def test_one_money_question_and_a_budget_approved_by_another_tool(fake, fssh):
    # the render workbench asks first, from the estimate (its own spend card)
    other = approvals.propose(EP, "edit", "spend", "Rent a GPU for the 3D scenes",
                              data={"amount_usd": 0.6, "budget_usd": 1.0})
    s = session_fn(episode=EP, step="edit", purpose="3D scenes", cap_usd=5.0, monitor=False).open()
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1, max_minutes=240)
    assert e.value.card_id == other["id"], "no second card while one is open"
    accept(other["id"])
    (m,) = s.rent(gpus=1, max_minutes=240)       # worst case about $1.57 > the $1.00 budget
    assert s.cap_usd == pytest.approx(1.0), "the session stays inside the approved budget"
    assert len(approvals.list_cards(EP)) == 1
    s.close()


def test_a_tiny_budget_left_asks_again(fake, fssh):
    small = approvals.propose(EP, "edit", "spend", "Small", data={"amount_usd": 0.05, "budget_usd": 0.05})
    accept(small["id"])
    s = session_fn(episode=EP, step="edit", purpose="x", cap_usd=2.0, monitor=False).open()
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1, max_minutes=60)
    assert e.value.card_id != small["id"]
    assert s.cap_usd == 2.0
