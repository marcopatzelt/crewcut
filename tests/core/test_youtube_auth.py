import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from google_auth_oauthlib.flow import Flow

from crewcut import db
from crewcut.youtube import auth


def test_redirect_uses_public_port_without_changing_server_port(monkeypatch):
    monkeypatch.setenv("CREWCUT_PORT", "4747")
    monkeypatch.setenv("CREWCUT_PUBLIC_PORT", "4757")
    assert auth.redirect_uri() == "http://localhost:4757/oauth/youtube"


def test_prompter_uses_public_port(crew, monkeypatch):
    from crewcut import episodes, prompter
    monkeypatch.setenv("CREWCUT_PROMPTER_PORT", "4748")
    monkeypatch.setenv("CREWCUT_PUBLIC_PROMPTER_PORT", "4758")
    monkeypatch.setenv("CREWCUT_LAN_HOST", "localhost")
    episode = episodes.create("Synthetic recording")
    assert prompter.url_for(episode["id"]).startswith("http://localhost:4758/p/")


def test_prompter_studio_host_overrides_detected_wifi(crew, monkeypatch):
    from crewcut import config, prompter
    monkeypatch.setenv("CREWCUT_LAN_HOST", "192.168.1.20")
    monkeypatch.setattr(config, "get", lambda *args: "100.64.0.10")
    assert prompter.lan_host() == "100.64.0.10"


def test_pkce_survives_a_new_flow_instance(studio, monkeypatch):
    auth.client_file().parent.mkdir(parents=True)
    auth.client_file().write_text(json.dumps({"installed": {
        "client_id": "synthetic-client", "client_secret": "synthetic-secret",
        "auth_uri": "https://accounts.example.test/authorize",
        "token_uri": "https://accounts.example.test/token",
    }}))
    url = auth.start()
    query = parse_qs(urlparse(url).query)
    verifier = db.kv_get("youtube_oauth_verifier")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert query["code_challenge"] == [challenge]
    assert query["code_challenge_method"] == ["S256"]
    seen = []

    def exchange(flow, **kwargs):
        seen.append((flow.code_verifier, kwargs["code"]))

    monkeypatch.setattr(Flow, "fetch_token", exchange)
    monkeypatch.setattr(Flow, "credentials", property(lambda flow: SimpleNamespace(to_json=lambda: '{"test":true}')))
    auth.finish("synthetic-code", query["state"][0])
    assert seen == [(verifier, "synthetic-code")]
    assert auth.token_file().stat().st_mode & 0o777 == 0o600
    assert db.kv_get("youtube_oauth_state") == ""
    assert db.kv_get("youtube_oauth_verifier") == ""
    with pytest.raises(PermissionError):
        auth.finish("synthetic-code", query["state"][0])


def test_missing_verifier_requires_a_new_login(studio):
    db.kv_set("youtube_oauth_state", "synthetic-state")
    with pytest.raises(PermissionError, match="incomplete"):
        auth.finish("synthetic-code", "synthetic-state")
    assert not auth.token_file().exists()


def test_foreign_callback_cannot_use_the_pending_verifier(studio):
    db.kv_set("youtube_oauth_state", "synthetic-state")
    db.kv_set("youtube_oauth_verifier", "synthetic-verifier")
    with pytest.raises(PermissionError):
        auth.finish("synthetic-code", "different-state")
    assert not auth.token_file().exists()
    assert db.kv_get("youtube_oauth_verifier") == "synthetic-verifier"


def test_credentials_write_is_private_before_replacement(studio, monkeypatch):
    original_replace = Path.replace
    seen = []

    def replace(source, destination):
        seen.append(source.stat().st_mode & 0o777)
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", replace)
    auth._save_credentials(SimpleNamespace(to_json=lambda: '{"synthetic":true}'))
    assert seen == [0o600]
    assert auth.token_file().stat().st_mode & 0o777 == 0o600


def test_failed_credentials_write_keeps_previous_login(studio, monkeypatch):
    auth._save_credentials(SimpleNamespace(to_json=lambda: '{"synthetic":"previous"}'))
    before = auth.token_file().read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        auth._save_credentials(SimpleNamespace(to_json=lambda: '{"synthetic":"new"}'))
    assert auth.token_file().read_bytes() == before
    assert not list(auth.token_file().parent.glob(".youtube-token-*"))
