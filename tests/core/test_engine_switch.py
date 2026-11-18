from fastapi.testclient import TestClient

from crewcut import db, engines
from crewcut.server.app import create_app


def test_switch_requires_login_and_keeps_other_connection(monkeypatch):
    connected = {'claude': True, 'codex': False}
    for name in connected:
        cls = type(engines.get(name))
        monkeypatch.setattr(cls, 'installed', lambda self: True)
        monkeypatch.setattr(cls, 'login_status', lambda self: (connected[self.name], 'test'))
    client = TestClient(create_app(start_worker=False), base_url='http://localhost:4747')
    assert client.post('/api/engine/codex/use').status_code == 409
    assert engines.current_name() == 'claude'
    connected['codex'] = True
    response = client.post('/api/engine/codex/use')
    assert response.status_code == 200
    assert response.json()['chosen'] == 'codex'
    assert response.json()['claude']['connected']
    assert db.kv_get('engine') == 'codex'
    assert client.get('/api/state').json()['app']['engine'] == 'codex'
    assert client.post('/api/engine/claude/use').json()['chosen'] == 'claude'
    assert connected['codex']
    assert client.post('/api/engine/unknown/use').status_code == 400
    with db.conn() as connection:
        assert connection.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
