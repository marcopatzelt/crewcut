"""Connect YouTube once through Claude in Chrome: the card, the signed request, the host helper's checks, and the
sign-in link at the end. The helper runs here with a fake `claude` and a fake browser on PATH and without a terminal
window; nothing real is started."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from crewcut import approvals, db, paths
from crewcut.youtube import auth, connect

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "host" / "crewcut-host.sh"
TOKEN = "test-host-token-0123456789abcdef"

needs_tools = pytest.mark.skipif(not (shutil.which("openssl") and (shutil.which("sha256sum") or shutil.which("shasum"))),
                                 reason="openssl and sha256sum are needed for the helper")


@pytest.fixture
def host(tmp_path, monkeypatch, studio):
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", TOKEN)
    fake = tmp_path / "bin"
    fake.mkdir()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    # the fake Claude Code "downloads" the client file the way Chrome would, then ends
    (fake / "claude").write_text("#!/bin/sh\n"
                                 f"printf '{{\"installed\":{{\"client_id\":\"x.apps.googleusercontent.com\"}}}}' "
                                 f"> '{downloads}/client_secret_123.json'\n"
                                 f"echo \"$@\" > '{tmp_path}/claude-args'\n")
    (fake / "google-chrome").write_text("#!/bin/sh\nexit 0\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path), "CREWCUT_STUDIO_DIR": str(studio),
           "CREWCUT_HOST_TOKEN": TOKEN, "CREWCUT_HOST_HEADLESS": "1", "CREWCUT_DOWNLOADS": str(downloads),
           "CREWCUT_HOST_COLLECT_S": "20"}
    return {"env": env, "downloads": downloads, "tmp": tmp_path}


def run_helper(env):
    return subprocess.run([str(HELPER), "--once"], env=env, capture_output=True, text=True, timeout=30)


def statuses():
    return [s["state"] for s in connect.statuses()]


def test_the_card_names_what_is_missing(studio, monkeypatch):
    monkeypatch.delenv("CREWCUT_HOST_TOKEN", raising=False)
    card = connect.propose("_onboarding")
    assert card["kind"] == "other" and card["data"]["connect"] == "youtube"
    assert card["data"]["button"] == "Set it up in my Chrome"
    assert "start.sh" in card["data"]["blocker"]
    with pytest.raises(RuntimeError):
        connect.request_setup()


def test_codex_gets_the_manual_way(studio, monkeypatch):
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", TOKEN)
    monkeypatch.setattr(connect, "_engine", lambda: "codex")
    assert "docs/youtube.md" in connect.why_not()


@needs_tools
def test_signed_request_starts_the_fixed_setup_and_brings_the_client_file(host, studio):
    assert run_helper(host["env"]).returncode == 0  # first beat: the container sees the helper
    assert connect.helper()["claude"].endswith("/claude")
    assert connect.why_not() is None
    req = connect.request_setup()
    assert run_helper(host["env"]).returncode == 0
    dest = studio / "config" / "youtube-client.json"
    for _ in range(40):
        if dest.is_file():
            break
        time.sleep(0.25)
    assert dest.is_file() and json.loads(dest.read_text())["installed"]["client_id"]
    assert oct(dest.stat().st_mode & 0o777) == "0o600"
    assert not (host["downloads"] / "client_secret_123.json").exists()
    args = (host["tmp"] / "claude-args").read_text()
    assert "--chrome" in args and "--disallowedTools Bash Write Edit" in args and "Google Cloud console" in args
    assert [s for s in connect.statuses() if s["id"] == req["id"]][-1]["state"] == "done"


@needs_tools
def test_helper_refuses_unsigned_old_repeated_and_foreign_requests(host, studio):
    run_helper(host["env"])
    box = paths.state_dir() / "host" / "requests"

    def write(fields):
        box.mkdir(parents=True, exist_ok=True)
        (box / f"{fields['id']}.req").write_text("".join(f"{k}={v}\n" for k, v in fields.items()))

    base = {"kind": "youtube-setup", "at": str(int(time.time())), "prompt_sha256": connect.prompt_sha256()}
    write({**base, "id": "a1", "nonce": "n1", "sig": "0" * 64})                                    # wrong signature
    old = {**base, "id": "a2", "nonce": "n2", "at": str(int(time.time()) - 600)}
    write({**old, "sig": connect.sign(old)})                                                        # too old
    other = {**base, "id": "a3", "nonce": "n3", "kind": "run-anything"}
    write({**other, "sig": connect.sign(other)})                                                    # unknown job
    foreign = {**base, "id": "a4", "nonce": "n4", "prompt_sha256": "f" * 64}
    write({**foreign, "sig": connect.sign(foreign)})                                                # other prompt
    run_helper(host["env"])
    states = {s["id"]: s for s in connect.statuses()}
    assert all(states[i]["state"] == "rejected" for i in ("a1", "a2", "a3", "a4"))
    assert "not signed" in states["a1"]["text"] and "too old" in states["a2"]["text"]
    assert "differs" in states["a4"]["text"]
    ok = {**base, "id": "a5", "nonce": "n5"}
    write({**ok, "sig": connect.sign(ok)})
    write({**ok, "id": "a6", "sig": connect.sign({**ok, "id": "a6"})})                              # same nonce again
    run_helper(host["env"])
    states = {s["id"]: s for s in connect.statuses()}
    assert states["a5"]["state"] in ("running", "done")
    assert states["a6"]["state"] == "rejected" and "used before" in states["a6"]["text"]
    assert not (host["tmp"] / "claude-args").read_text().count("run-anything")
    assert not list(box.glob("*.req"))


def test_accepting_the_card_writes_the_request_and_the_watcher_posts_the_sign_in_link(studio, monkeypatch, crew):
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", TOKEN)
    monkeypatch.setattr(connect, "why_not", lambda: None)
    card = connect.propose("_onboarding")
    approvals.decide(card["id"], True)
    reqs = list((paths.state_dir() / "host" / "requests").glob("*.req"))
    assert len(reqs) == 1 and "sig=" in reqs[0].read_text() and TOKEN not in reqs[0].read_text()
    assert db.kv_get("youtube_connect_episode") == "_onboarding"
    (studio / "config").mkdir(exist_ok=True)
    auth.client_file().write_text('{"installed": {"client_id": "x"}}')
    monkeypatch.setattr(auth, "start", lambda: "https://accounts.google.com/o/oauth2/auth?x=1")
    w = connect.Watcher()
    w.tick("_onboarding")
    with db.conn() as c:
        texts = [r["text"] for r in c.execute("SELECT text FROM messages WHERE episode = '_onboarding'")]
    assert any("accounts.google.com" in t for t in texts)


def test_agents_never_get_the_host_key(monkeypatch):
    from crewcut.engines import base
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", TOKEN)
    assert "CREWCUT_HOST_TOKEN" in base.SERVER_ONLY_ENV
    assert TOKEN not in base.scrub(f"value {TOKEN} leaked")
    assert os.environ["CREWCUT_HOST_TOKEN"] == TOKEN
