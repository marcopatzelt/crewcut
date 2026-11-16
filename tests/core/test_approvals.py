import pytest

from crewcut import approvals, brand, episodes, ledger


@pytest.fixture
def ep(crew):
    return episodes.create("Local models on a laptop")["id"]


def test_file_card_locks_the_version(ep, studio, monkeypatch):
    from crewcut.conductor import flow
    monkeypatch.setattr(flow, "on_card_decided", lambda card: None)
    f = studio / "episodes" / ep / "brief" / "SCRIPT-v001.md"
    f.write_text("hello")
    card = approvals.propose(ep, "script", "script", "Approve the script", file="brief/SCRIPT-v001.md")
    assert card["sha256"] and card["status"] == "open"
    f.write_text("changed after the card")
    with pytest.raises(ValueError):
        approvals.decide(card["id"], True)
    f.write_text("hello")
    assert approvals.decide(card["id"], True)["status"] == "accepted"


def test_card_file_cannot_escape_the_episode(ep):
    with pytest.raises(ValueError):
        approvals.propose(ep, "script", "script", "x", file="../../etc/passwd")


def test_rule_card_writes_user_pack(ep, studio, monkeypatch):
    from crewcut.conductor import flow
    monkeypatch.setattr(flow, "on_card_decided", lambda card: None)
    card = approvals.propose_rule("cut", "Never zoom into other people's clips.", "user, no zoom", episode=ep)
    approvals.decide(card["id"], True)
    rules = brand.load().rules("cut")
    assert rules and rules[-1]["rule"] == "Never zoom into other people's clips."
    assert (studio / "brand" / "brand.json").is_file()


def test_spend_needs_a_card_then_runs_inside_budget(ep, monkeypatch):
    from crewcut.conductor import flow
    monkeypatch.setattr(flow, "on_card_decided", lambda card: None)
    monkeypatch.setenv("CREWCUT_IDENTITY", "editor")
    ok, card_id, _ = approvals.require_spend(ep, 0.6, "Rent a GPU?", data={"cap_usd": 1.5, "step": "edit"})
    assert not ok and card_id
    assert approvals.get(card_id)["data"]["budget_usd"] == 1.5
    approvals.decide(card_id, True)
    ok, card_id2, _ = approvals.require_spend(ep, 0.6, "Rent a GPU?")
    assert ok and card_id2 is None
    ledger.add("gpu", 1.2, "render", episode=ep)
    ok, card_id3, _ = approvals.require_spend(ep, 0.6, "Rent a GPU?")
    assert not ok and card_id3  # 1.2 spent + 0.6 > 1.5 budget


def test_spend_right_lives_in_the_identity(ep, monkeypatch):
    monkeypatch.setenv("CREWCUT_IDENTITY", "writer")
    with pytest.raises(approvals.RightsError):
        approvals.require_spend(ep, 0.1, "x")


def test_month_cap_blocks_without_card(ep, monkeypatch):
    monkeypatch.setenv("CREWCUT_IDENTITY", "editor")
    ledger.add("gpu", ledger.month_cap() - 0.05, "earlier renders")
    ok, card_id, reason = approvals.require_spend(ep, 0.6, "Rent a GPU?")
    assert not ok and card_id is None and "cap" in reason


def test_declined_spend_means_local_is_fine(ep, monkeypatch):
    from crewcut.compute import state
    from crewcut.conductor import queue
    jobs = []
    monkeypatch.setattr(queue, "add", lambda *a, **k: jobs.append((a, k)) or 1)
    monkeypatch.setenv("CREWCUT_IDENTITY", "editor")
    ok, card_id, _ = approvals.require_spend(ep, 0.6, "Rent a GPU?", data={"cap_usd": 1.5, "step": "edit"})
    monkeypatch.delenv("CREWCUT_IDENTITY")
    approvals.decide(card_id, False, reason="Local is fine. Render on this machine.")
    assert state.local_is_fine(ep)
    assert jobs and "Local is fine for this episode" in jobs[-1][0][3]
