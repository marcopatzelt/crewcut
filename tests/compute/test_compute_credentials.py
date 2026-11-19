import httpx

from crewcut import paths
from crewcut.compute import scrub, vast
from crewcut.engines.base import scrub as scrub_log


def test_private_key_survives_new_clients_and_is_redacted(monkeypatch):
    monkeypatch.delenv('VAST_API_KEY', raising=False)
    assert not vast.has_key()
    key = 'synthetic-private-vast-credential-123456'
    p = paths.state_dir() / 'compute' / 'vast-api-key'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key + '\n')
    p.chmod(0o600)
    assert vast.has_key()
    def reply(request):
        assert request.headers['Authorization'] == 'Bearer ' + key
        return httpx.Response(200, json={'credit': 12.5})
    for _ in range(2):
        assert vast.Vast(transport=httpx.MockTransport(reply)).credit() == 12.5
    assert key not in scrub.scrub_text(key)
    assert key not in scrub_log(key)
    monkeypatch.setenv('VAST_API_KEY', 'explicit-environment-key')
    assert vast.credential() == 'explicit-environment-key'


def test_unconfigured_studio_does_not_discover_host_credentials(monkeypatch):
    monkeypatch.delenv('VAST_API_KEY', raising=False)
    assert vast.credential() == ''
