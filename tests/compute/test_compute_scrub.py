"""Secret scrub, the remote scripts and the SSH key."""

from __future__ import annotations

import subprocess

from crewcut.compute import remote, scrub, ssh


def test_scrub_text_patterns(monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "vastkey-0123456789abcdef0123")
    text = ("CONTAINER_API_KEY=abc123def456ghi\n"
            "export CLAUDE_CODE_OAUTH_TOKEN='tok-0123456789abcdef'\n"
            "x sk-ant-oat01-ABCDEFGHIJKLMNOPQRSTUVWXYZ y\n"
            "authorization: Bearer qwertyuiop12345\n"
            "the key vastkey-0123456789abcdef0123 leaked\n")
    out = scrub.scrub_text(text)
    for secret in ("abc123def456ghi", "tok-0123456789abcdef", "sk-ant-oat01", "qwertyuiop12345",
                   "vastkey-0123456789abcdef0123"):
        assert secret not in out
    assert "CONTAINER_API_KEY=[REMOVED]" in out
    assert scrub.scrub_text("nothing secret here") == "nothing secret here"


def test_scrub_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-SECRETSECRETSECRET")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "log.txt").write_text("ANTHROPIC_API_KEY=sk-ant-api03-SECRETSECRETSECRET\n")
    media = b"\x89PNG CONTAINER_API_KEY=keep-pattern-in-media sk-ant-api03-SECRETSECRETSECRET"
    (tmp_path / "frame.png").write_bytes(media)
    (tmp_path / "ok.txt").write_text("fine\n")
    (tmp_path / "link").symlink_to("/etc/hostname")
    changed = scrub.scrub_dir(tmp_path)
    assert sorted(changed) == ["a/log.txt", "frame.png"]
    assert b"SECRETSECRET" not in (tmp_path / "frame.png").read_bytes()
    assert b"keep-pattern-in-media" in (tmp_path / "frame.png").read_bytes(), "media is only checked for exact values"
    assert not (tmp_path / "link").exists()


def test_scripts_parse_and_hold_no_key():
    for name, text in (("setup.sh", remote.setup_file().read_text()), ("watchdog", remote.WATCHDOG),
                       ("onstart", remote.onstart(1_800_000_000)), ("prepare", remote.PREPARE)):
        r = subprocess.run(["bash", "-n"], input=text, text=True, capture_output=True)
        assert r.returncode == 0, f"{name}: {r.stderr}"
    on = remote.onstart(1_800_000_000)
    assert "1800000000" in on and "CONTAINER_API_KEY" in on
    assert "-K -" in remote.WATCHDOG, "the instance key goes to curl on stdin"
    assert len(on) < 4000, "Vast limits the onstart text"


def test_ssh_key_is_made_once(studio, monkeypatch):
    calls = []

    def runner(argv, timeout=60, input=None):
        calls.append(argv)
        f = argv[argv.index("-f") + 1]
        open(f, "w").write("PRIVATE\n")
        open(f + ".pub", "w").write("ssh-ed25519 AAAAfake crewcut-compute\n")
        return 0, "", ""

    ssh.use_runner(runner)
    try:
        pub = ssh.ensure_key()
        assert pub.startswith("ssh-ed25519 ") and "PRIVATE" not in pub
        assert ssh.ensure_key() == pub
        assert len(calls) == 1
        assert (ssh.key_path().stat().st_mode & 0o077) == 0
    finally:
        ssh.use_runner(None)


def test_argv_builders_use_the_studio_key(studio):
    a = ssh.ssh_argv("host.test", 2222, 7, "echo ok")
    assert a[0] == "ssh" and "-i" in a and "BatchMode=yes" in a and a[-2:] == ["root@host.test", "echo ok"]
    up = ssh.rsync_up_argv(["x.py"], "host.test", 2222, 7, "/work/")
    assert up[0] == "rsync" and up[-1] == "root@host.test:/work/"
