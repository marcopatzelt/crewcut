"""Claude subscription or Anthropic API key (engines/connect.py, engines/claude_code.py, /api/engine/claude/auth)."""

import io
import json
import stat
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from crewcut import db, engines, episodes
from crewcut.conductor import queue
from crewcut.engines import connect

TOKEN = "sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abc"
KEY = "sk-ant-test-" + "k" * 40
ENV_KEY = "sk-ant-test-env-" + "e" * 40


@pytest.fixture
def engine_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWCUT_ENGINE_PREFIX", str(tmp_path / "engine"))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(connect, "_from_store", False)
    yield tmp_path / "engine"


def client():
    from crewcut.server.app import create_app
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def task(**opts):
    return engines.Task(prompt="hi", system="", cwd=connect.Path("."), engine_options=dict(opts))


def settings_of(cmd):
    return json.loads(cmd[cmd.index("--settings") + 1]) if "--settings" in cmd else None


# ---------- storage ----------

def test_the_key_is_stored_private_and_atomic(engine_dir):
    with pytest.raises(ValueError):
        connect.store_api_key("sk-ant-short")
    with pytest.raises(ValueError):
        connect.store_api_key("not-a-key-" + "x" * 40)
    assert not connect.has_api_key()
    connect.store_api_key("  " + KEY + "\n")
    f = connect.api_key_file()
    assert f.read_text() == KEY
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert not list(f.parent.glob("*.tmp"))                 # written to a temp file, then renamed
    helper = connect.helper_file()
    assert stat.S_IMODE(helper.stat().st_mode) == 0o700
    assert KEY not in helper.read_text() and str(f) in helper.read_text()
    assert connect.api_key_source() == "stored"
    assert connect.forget_api_key() is True and not f.exists() and not connect.has_api_key()


def test_the_helper_prints_the_key(engine_dir):
    import subprocess
    connect.store_api_key(KEY)
    out = subprocess.run([str(connect.helper_file())], capture_output=True, text=True, check=True).stdout
    assert out == KEY


def test_the_environment_key_wins_and_cannot_be_forgotten(engine_dir, monkeypatch):
    connect.store_api_key(KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", ENV_KEY)
    assert connect.api_key_source() == "environment"
    assert connect.forget_api_key() is False
    assert connect.has_api_key()


# ---------- the mode ----------

def test_the_default_mode_follows_the_credentials(engine_dir, monkeypatch):
    assert connect.auth_mode() == "subscription"            # nothing at all: the subscription asks to connect
    connect.store_api_key(KEY)
    assert connect.auth_mode() == "api_key"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    assert connect.auth_mode() == "subscription"             # a token wins while nothing is chosen


def test_the_choice_persists_and_needs_its_credential(engine_dir, monkeypatch):
    with pytest.raises(LookupError):
        connect.set_auth_mode("api_key")
    with pytest.raises(LookupError):
        connect.set_auth_mode("subscription")
    with pytest.raises(ValueError):
        connect.set_auth_mode("free")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    connect.store_api_key(KEY)
    assert connect.set_auth_mode("api-key") == "api_key"
    assert db.kv_get(connect.AUTH_KV) == "api_key" and connect.auth_mode() == "api_key"
    eng = engines.get("claude")
    assert eng.login_kind() == "api-key" and eng.login_status()[0]
    connect.set_auth_mode("subscription")
    assert eng.login_kind() == "subscription"


def test_api_key_mode_without_a_key_is_not_connected(engine_dir, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    db.kv_set(connect.AUTH_KV, "api_key")
    ok, why = engines.get("claude").login_status()
    assert not ok and "API key" in why


# ---------- the command and the child's environment ----------

def test_command_adds_the_helper_only_in_api_key_mode(engine_dir, monkeypatch):
    eng = engines.get("claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    connect.store_api_key(KEY)
    connect.set_auth_mode("subscription")
    t = task(settings={"crossSessionInbound": "accept"})
    assert settings_of(eng.command(t)) == {"crossSessionInbound": "accept"}
    assert eng.env_drop(t) == ["ANTHROPIC_API_KEY"]
    assert settings_of(eng.command(task())) is None

    connect.set_auth_mode("api_key")
    t = task(settings={"crossSessionInbound": "accept"})
    cmd = eng.command(t)
    assert settings_of(cmd) == {"crossSessionInbound": "accept", "apiKeyHelper": str(connect.helper_file())}
    assert t.engine_options["settings"] == {"crossSessionInbound": "accept"}   # merged, the job's own value untouched
    assert set(eng.env_drop(t)) == {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"}
    assert settings_of(eng.command(task())) == {"apiKeyHelper": str(connect.helper_file())}
    assert not any(KEY in a for a in cmd)


def test_an_environment_key_needs_no_helper(engine_dir, monkeypatch):
    eng = engines.get("claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", ENV_KEY)
    connect.set_auth_mode("api_key")
    t = task()
    cmd = eng.command(t)
    assert settings_of(cmd) is None and eng.env_drop(t) == ["CLAUDE_CODE_OAUTH_TOKEN"]
    assert not any(ENV_KEY in a for a in cmd)


def test_a_running_job_keeps_its_login(engine_dir, monkeypatch):
    eng = engines.get("claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    connect.store_api_key(KEY)
    connect.set_auth_mode("subscription")
    t = task()
    assert eng.auth_for(t) == "subscription"
    connect.set_auth_mode("api_key")
    assert eng.auth_for(t) == "subscription" and settings_of(eng.command(t)) is None


FAKE_RUN = r"""#!PYTHON
import json, os, sys
with open(os.environ["DUMP"], "w") as f:
    json.dump({"argv": sys.argv[1:], "token": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
               "key": bool(os.environ.get("ANTHROPIC_API_KEY"))}, f)
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "m",
                  "apiKeySource": "apiKeyHelper"}))
print(json.dumps({"type": "result", "subtype": "success", "result": "ok", "total_cost_usd": 0.01, "num_turns": 1}))
"""


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    p = tmp_path / "claude"
    p.write_text(FAKE_RUN.replace("#!PYTHON", "#!" + sys.executable))
    p.chmod(0o755)
    monkeypatch.setattr(type(engines.get("claude")), "binary", lambda self: str(p))
    dump = tmp_path / "dump.json"
    monkeypatch.setenv("DUMP", str(dump))
    return dump


@pytest.mark.parametrize("mode,token,key", [("subscription", True, False), ("api_key", False, False)])
def test_the_child_gets_only_the_chosen_login(engine_dir, monkeypatch, fake_run, mode, token, key):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("ANTHROPIC_API_KEY", ENV_KEY)
    connect.store_api_key(KEY)
    db.kv_set(connect.AUTH_KV, mode)
    if mode == "api_key":
        monkeypatch.delenv("ANTHROPIC_API_KEY")              # a stored key: the helper, no variable
    res = engines.get("claude").run(task(), stop=threading.Event())
    assert res.ok
    seen = json.loads(fake_run.read_text())
    assert seen["token"] is token and seen["key"] is key
    assert ("apiKeyHelper" in json.dumps(seen["argv"])) is (mode == "api_key")
    assert KEY not in json.dumps(seen["argv"]) and ENV_KEY not in json.dumps(seen["argv"])


def test_the_job_records_its_login_but_never_the_key(engine_dir, monkeypatch, fake_run, crew):
    from crewcut.engines import versions
    monkeypatch.setattr(versions, "note_job", lambda *args: None)
    monkeypatch.setattr(queue, "plugin_dir", lambda: None)
    connect.store_api_key(KEY)
    connect.set_auth_mode("api_key")
    episode = episodes.create("Synthetic episode")["id"]
    job = queue.get(queue.add(episode, "writer", "script", "Write"))
    queue._run_agent(job)
    done = queue.get(job["id"])
    assert done["data"]["auth"] == "api_key"
    assert done["data"]["engine_info"]["apiKeySource"] == "apiKeyHelper"
    assert queue.job_view(done)["auth"] == "api_key"
    with db.conn() as c:
        dump = json.dumps([dict(r) for r in c.execute("SELECT * FROM jobs")], default=str)
    assert KEY not in dump
    assert KEY not in open(done["log_path"]).read()


# ---------- the API ----------

def test_api_switches_and_never_returns_the_key(engine_dir, monkeypatch, crew):
    c = client()
    view = c.get("/api/engine/claude/auth").json()
    assert view == {"mode": "subscription", "subscription": {"connected": False, "source": None},
                    "api_key": {"present": False, "source": None}}
    assert c.post("/api/engine/claude/auth", json={"mode": "api_key"}).status_code == 409
    assert c.post("/api/engine/claude/auth", json={"mode": "nope"}).status_code == 400
    bad = c.post("/api/engine/claude/api-key", json={"key": "sk-ant-short", "extra": KEY})
    assert bad.status_code == 400 and KEY not in bad.text
    assert c.post("/api/engine/claude/api-key", json={"apikey": KEY}).status_code == 400
    r = c.post("/api/engine/claude/api-key", json={"key": KEY, "use": True})
    assert r.status_code == 200 and KEY not in r.text
    assert r.json()["mode"] == "api_key" and r.json()["api_key"] == {"present": True, "source": "stored"}
    login = c.get("/api/engine/login")
    assert login.json()["claude_auth"]["mode"] == "api_key" and login.json()["claude"]["connected"] is True
    assert KEY not in login.text and KEY not in c.get("/api/state").text
    assert c.post("/api/engine/claude/auth", json={"mode": "subscription"}).status_code == 409   # no token yet
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    r = c.post("/api/engine/claude/auth", json={"mode": "subscription"})
    assert r.status_code == 200 and r.json()["mode"] == "subscription"
    assert db.kv_get(connect.AUTH_KV) == "subscription"
    assert c.post("/api/engine/claude/api-key", json={"key": KEY, "use": True}).json()["mode"] == "api_key"
    with db.conn() as cn:
        notes = [r[0] for r in cn.execute("SELECT text FROM events WHERE kind = 'activity'")]
    assert "New work uses the API key now. Running work keeps its login." in notes
    assert "New work uses the Claude subscription now. Running work keeps its login." in notes
    r = c.delete("/api/engine/claude/api-key")
    assert r.status_code == 200 and r.json()["mode"] == "subscription" and not r.json()["api_key"]["present"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", ENV_KEY)
    assert c.delete("/api/engine/claude/api-key").status_code == 409
    assert ENV_KEY not in c.get("/api/engine/claude/auth").text
    assert c.post("/api/engine/claude/auth", json={"mode": "api_key"},
                  headers={"Origin": "https://evil.example"}).status_code == 403


# ---------- the CLI ----------

def test_cli_reads_the_key_from_stdin_only(engine_dir, monkeypatch, capsys):
    from crewcut import cli
    assert cli.main(["engine", "api-key"]) == 2
    monkeypatch.setattr(sys, "stdin", io.StringIO(KEY + "\n"))
    assert cli.main(["engine", "api-key", "--stdin", "--use"]) == 0
    out = capsys.readouterr()
    assert KEY not in out.out + out.err
    assert connect.api_key_file().read_text() == KEY and connect.auth_mode() == "api_key"
    assert cli.main(["engine", "auth", "subscription"]) == 4          # no subscription token
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    assert cli.main(["engine", "auth", "subscription"]) == 0
    assert "Claude subscription" in capsys.readouterr().out
    assert cli.main(["engine", "auth"]) == 0
    assert cli.main(["engine", "api-key", "--forget"]) == 0 and not connect.has_api_key()
    with pytest.raises(SystemExit):
        cli.main(["engine", "api-key", KEY])                            # never as an argument


def test_doctor_names_the_login_and_the_old_helper(engine_dir, monkeypatch, studio):
    from crewcut import doctor
    connect.store_api_key(KEY)
    (studio / ".claude").mkdir()
    (studio / ".claude" / "settings.json").write_text(json.dumps({"apiKeyHelper": "/x.sh"}))
    rows = doctor.checks(ci=True)
    line = next(r for r in rows if r["name"] == "Claude login")
    assert "API key" in line["detail"] and KEY not in json.dumps(rows)
    assert any("apiKeyHelper" in r["detail"] for r in rows)
