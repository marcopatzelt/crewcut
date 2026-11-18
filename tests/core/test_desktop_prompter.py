import json
import time

import pytest
from fastapi.testclient import TestClient

from crewcut import approvals, desktop_prompter, episodes, paths
from crewcut.conductor import flow
from crewcut.server.app import create_app


@pytest.fixture
def approved(crew, monkeypatch):
    monkeypatch.setattr(flow, "on_card_decided", lambda card: None)
    episode = episodes.create("Desktop test")["id"]
    source = paths.episode_dir(episode) / "brief/SCRIPT-v001.md"
    source.write_text("Synthetic spoken script.")
    card = approvals.propose(episode, "script", "script", "Read", file="brief/SCRIPT-v001.md")
    approvals.decide(card["id"], True)
    return episode, source


def test_request_only_records_pending_not_opened(approved):
    episode, _ = approved
    request = desktop_prompter.request_open(episode)
    assert request["status"] == "pending"
    assert desktop_prompter.status(request["id"])["episode"] == episode
    assert "url" not in request and "command" not in request


def test_changed_approved_script_is_refused(approved):
    episode, source = approved
    source.write_text("Changed")
    with pytest.raises(ValueError, match="changed"):
        desktop_prompter.request_open(episode)
    assert TestClient(create_app(), base_url="http://localhost").get(f"/api/episodes/{episode}/desktop-prompter").status_code == 409


def test_unapproved_script_is_refused(crew):
    episode = episodes.create("Draft")["id"]
    with pytest.raises(ValueError, match="Approve"):
        desktop_prompter.request_open(episode)


def test_expired_request_is_not_success(approved):
    request = desktop_prompter.request_open(approved[0])
    target = paths.state_dir() / "desktop-prompter" / f"{request['id']}.json"
    target.write_text(json.dumps({**request, "created": time.time() - 121}))
    assert desktop_prompter.status(request["id"])["status"] == "failed"


@pytest.mark.parametrize("value", ["../escape", "/tmp/file", "https://example.org", "x; touch /tmp/x"])
def test_reject_arbitrary_targets(value):
    with pytest.raises(ValueError):
        desktop_prompter.launch_info(value)
    with pytest.raises(ValueError):
        desktop_prompter.status(value)
