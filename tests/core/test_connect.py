"""Connect Claude and Codex without a terminal (crewcut/engines/connect.py and the /api/engine routes)."""

import json
import stat
import sys

import pytest
from fastapi.testclient import TestClient

from crewcut.engines import connect

TOKEN = "sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abc"

# A stand-in for the real CLI's terminal UI: it switches its terminal to raw mode, echoes the pasted code masked (as
# the real one does, with charset bytes), and submits only on an Enter key that arrives on its own; text and Enter in
# one chunk count as pasted text, as in the real CLI.
FAKE_CLAUDE = r"""#!PYTHON
import os, sys, termios, tty, json
if sys.argv[1:2] == ["auth"]:
    print(json.dumps({"loggedIn": True, "email": "me@example.org", "authMethod": "oauth_token", "secret": "x"}))
    sys.exit(0)
assert sys.argv[1:2] == ["setup-token"]
if os.environ.get("BROWSER") != "true" or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
    print("bad environment"); sys.exit(9)
out = sys.stdout
out.write("\x1b[1mBrowser didn't open? Use the url below to sign in:\x1b[0m\r\n\r\n")
out.write("https://evil.example/oauth/authorize?x=1\r\n")
out.write("\x1b]8;;https://claude.ai/oauth/authorize?code=true&client_id=abc&state=xyz\x07"
          "https://claude.ai/oauth/authorize?code=true&client_id=abc&state=xyz\x1b]8;;\x07\r\n\r\n")
out.write("Paste code here if prompted > "); out.flush()
fd = sys.stdin.fileno()
tty.setraw(fd)
typed = ""
while True:
    chunk = os.read(fd, 4096).decode()
    if chunk == "\r":
        break
    typed += chunk.replace("\r", "")
    out.write("\r\x1b[2KPaste code here if prompted > \x1b(B\x0f" + "*" * max(0, len(typed) - 6) + typed[-6:])
    out.flush()
if typed != "goodcode#state1":
    out.write("\r\n\x1b[31mOAuth error: Invalid code\x1b[0m\r\n"); out.flush(); sys.exit(1)
out.write("\r\n\x1b[32mLong-lived authentication token created successfully\x1b[0m\r\n\r\n")
out.write("Your OAuth token (valid for 1 year):\r\n\r\nsk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abc\r\n")
out.flush()
"""


@pytest.fixture
def fake_claude(tmp_path):
    p = tmp_path / "claude"
    p.write_text(FAKE_CLAUDE.replace("#!PYTHON", "#!" + sys.executable))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


@pytest.fixture
def engine_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWCUT_ENGINE_PREFIX", str(tmp_path / "engine"))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(connect, "_from_store", False)
    yield tmp_path / "engine"


def test_root_under_rootless_docker_stays_root_in_the_sandbox(tmp_path, monkeypatch):
    calls = []
    run_as = tmp_path / "crewcut-user"
    run_as.write_text("0:0\n")
    monkeypatch.setattr(connect, "RUN_AS", run_as)
    monkeypatch.setenv("CREWCUT_STUDIO", str(tmp_path))
    monkeypatch.setattr(connect.os, "geteuid", lambda: 0)
    monkeypatch.setattr(connect.os, "setuid", lambda u: calls.append(u))
    monkeypatch.delenv("IS_SANDBOX", raising=False)
    connect.drop_to_studio_owner()
    assert calls == [] and connect.os.environ["IS_SANDBOX"] == "1"
    run_as.write_text("1234:1235\n")
    monkeypatch.setattr(connect.os, "setgroups", lambda g: None)
    monkeypatch.setattr(connect.os, "setgid", lambda g: calls.append(("gid", g)))
    connect.drop_to_studio_owner()
    assert calls == [("gid", 1235), 1234]


def test_root_switches_to_the_studio_owner(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "RUN_AS", tmp_path / "missing")
    monkeypatch.setenv("CREWCUT_STUDIO", str(tmp_path))
    monkeypatch.setattr(connect.os, "geteuid", lambda: 0)
    monkeypatch.setattr(connect.os, "setgroups", lambda g: calls.append(("groups", g)))
    monkeypatch.setattr(connect.os, "setgid", lambda g: calls.append(("gid", g)))
    monkeypatch.setattr(connect.os, "setuid", lambda u: calls.append(("uid", u)))
    monkeypatch.setenv("HOME", "/root")
    connect.drop_to_studio_owner()
    uid = tmp_path.stat().st_uid or 1000
    assert calls[-1] == ("uid", uid) and calls[0] == ("groups", [])
    assert connect.os.environ["HOME"] == str(tmp_path / ".crewcut" / "home")


def test_only_anthropic_sign_in_links_count():
    assert connect.sign_in_url("go to https://evil.example/a then") is None
    assert connect.sign_in_url("\x1b[1mhttps://claude.ai/oauth/authorize?code=true&x=1\x1b[0m.") == \
        "https://claude.ai/oauth/authorize?code=true&x=1"
    assert connect.sign_in_url("https://platform.claude.com/oauth/code/callback?code=1") is not None
    assert connect.sign_in_url("https://claude.ai.evil.example/x") is None


def test_the_sign_in_gives_a_link_then_a_token(fake_claude, engine_dir, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-old-token-that-must-not-leak-0000")
    s = connect.ClaudeSignIn(fake_claude)
    url = s.start(timeout=10)
    assert url == "https://claude.ai/oauth/authorize?code=true&client_id=abc&state=xyz"
    with pytest.raises(ValueError):
        s.finish("no")  # too short: refused before it reaches the CLI
    assert s.finish("goodcode#state1", timeout=10) == TOKEN


def test_a_wrong_code_says_so_without_echoing_the_code(fake_claude, engine_dir):
    s = connect.ClaudeSignIn(fake_claude)
    s.start(timeout=10)
    with pytest.raises(RuntimeError) as err:
        s.finish("wrongcode#state1", timeout=10)
    text = str(err.value)
    assert text == "Claude did not accept the code. Claude Code says: OAuth error: Invalid code"
    assert "*" not in text and "state1" not in text and "\x1b" not in text


def test_spaces_and_line_breaks_from_copying_are_dropped(fake_claude, engine_dir):
    s = connect.ClaudeSignIn(fake_claude)
    s.start(timeout=10)
    assert s.finish("  goodcode#\nstate1 \n", timeout=10) == TOKEN


def test_cleaning_drops_charset_switches_and_control_bytes():
    assert connect.clean("a\x1b(B\x0fb\x1b[31mc\x1b[0m\r\n") == "abc\n\n"
    assert connect.cli_error("Paste > \x1b(B\x0f*****IgFcAg\r\nOAuth error: 400\r\n") == "OAuth error: 400"
    assert connect.cli_error("Paste > *****IgFcAg error") is None


def test_the_stored_token_is_private_and_the_environment_wins(engine_dir, monkeypatch):
    connect.store_token(TOKEN)
    f = connect.token_file()
    assert f.read_text() == TOKEN and stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert connect.token_source() == "stored"
    assert connect.forget_token() and not f.exists()
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in __import__("os").environ
    # from .env or the desktop app: not ours to remove, and it beats a stored one
    connect.store_token(TOKEN)
    monkeypatch.setattr(connect, "_from_store", False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-from-the-environment-000000000")
    assert connect.load_stored_token() is False and connect.token_source() == "environment"
    assert connect.forget_token() is False
    with pytest.raises(ValueError):
        connect.store_token("not a token")


def test_the_account_keeps_only_harmless_fields(fake_claude):
    assert connect.claude_account(TOKEN, fake_claude) == {
        "email": "me@example.org", "authMethod": "oauth_token"}


def test_cli_connect_prints_json_lines_and_the_token_for_the_desktop_app(fake_claude, engine_dir, monkeypatch,
                                                                       capsys):
    from crewcut import engines
    eng = engines.get("claude")
    monkeypatch.setattr(type(eng), "binary", lambda self: fake_claude)
    monkeypatch.setattr(connect, "drop_to_studio_owner", lambda: None)  # the image's tests run as root
    monkeypatch.setattr(connect.sys, "stdin", __import__("io").StringIO("goodcode#state1\n"))
    assert connect.cli_connect("claude", print_token=True) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert lines[0] == {"step": "url", "url": "https://claude.ai/oauth/authorize?code=true&client_id=abc&state=xyz"}
    assert lines[-1]["step"] == "done" and lines[-1]["token"] == TOKEN
    assert not connect.token_file().exists()  # the desktop app keeps it, not the volume


def test_web_ui_connects_claude_and_stores_the_token(crew, engine_dir, fake_claude, monkeypatch):
    from crewcut import engines
    from crewcut.conductor import queue
    from crewcut.server.app import create_app
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)
    monkeypatch.setattr(type(engines.get("claude")), "binary", lambda self: fake_claude)
    c = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    before = c.get("/api/engine/login").json()
    assert before["claude"]["connected"] is False and before["claude"]["source"] is None
    assert c.post("/api/engine/claude/code", json={"code": "goodcode#state1"}).status_code == 409  # no sign-in yet
    r = c.post("/api/engine/claude/connect")
    assert r.status_code == 200 and r.json()["url"].startswith("https://claude.ai/oauth/authorize")
    assert c.post("/api/engine/claude/code", json={"code": "x"}).status_code == 400  # a typo keeps the sign-in
    r = c.post("/api/engine/claude/code", json={"code": "goodcode#state1"})
    assert r.status_code == 200 and r.json()["account"]["email"] == "me@example.org"
    assert connect.token_file().read_text() == TOKEN
    after = c.get("/api/engine/login").json()["claude"]
    assert after["connected"] is True and after["source"] == "stored"
    assert c.get("/api/state").json()["app"]["engine_ok"] is True
    assert c.post("/api/engine/claude/disconnect").json()["claude"]["connected"] is False
    assert not connect.token_file().exists()
    # a cross-site page cannot start a sign-in
    assert c.post("/api/engine/claude/connect", headers={"Origin": "https://evil.example"}).status_code == 403
