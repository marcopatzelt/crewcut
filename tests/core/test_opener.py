"""`crewcut open` and host/open-app.sh (run by ./start.sh): print the address, wait for the server, open an app window."""

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from crewcut import cli, opener

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def linux(monkeypatch):
    """A Linux desktop with a screen, the server up, and nothing started for real."""
    started: list[list[str]] = []
    monkeypatch.setattr(opener.platform, "system", lambda: "Linux")
    monkeypatch.setattr(opener, "_windows_like", lambda: False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("CREWCUT_OPEN", raising=False)
    monkeypatch.delenv("CREWCUT_PORT", raising=False)
    monkeypatch.setattr(opener, "answers", lambda url: True)
    monkeypatch.setattr(opener, "_detach", lambda cmd: started.append(cmd) or True)
    monkeypatch.setattr(opener.webbrowser, "open", lambda url: started.append(["default-browser", url]) or True)
    monkeypatch.setattr(opener.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""))
    return started


def which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


def test_no_open_only_prints_the_address(linux, capsys, monkeypatch):
    monkeypatch.chdir(ROOT / "tests")  # no .env here
    assert cli.main(["open", "--no-open"]) == 0
    assert capsys.readouterr().out.strip() == "Crewcut: http://localhost:4747"
    assert linux == []


def test_open_none_and_the_port(linux, capsys, monkeypatch):
    monkeypatch.setenv("CREWCUT_OPEN", "none")
    monkeypatch.setenv("CREWCUT_PORT", "5050")
    assert opener.main() == 0
    assert "http://localhost:5050" in capsys.readouterr().out and linux == []


def test_app_window_of_the_first_chromium_browser(linux, monkeypatch):
    monkeypatch.setattr(opener.shutil, "which", which_only("chromium", "brave-browser"))
    assert opener.main("http://localhost:4747") == 0
    assert linux == [["/usr/bin/chromium", "--app=http://localhost:4747"]]  # own profile: no --user-data-dir


def test_the_default_browser_goes_first(linux, monkeypatch):
    monkeypatch.setattr(opener.shutil, "which", which_only("google-chrome", "brave-browser"))
    monkeypatch.setattr(opener.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "brave-browser.desktop\n", ""))
    opener.main("http://localhost:4747")
    assert linux == [["/usr/bin/brave-browser", "--app=http://localhost:4747"]]


def test_without_a_chromium_browser_the_default_browser_opens(linux, monkeypatch):
    monkeypatch.setattr(opener.shutil, "which", lambda name: None)
    opener.main("http://localhost:4747")
    assert linux == [["default-browser", "http://localhost:4747"]]


def test_browser_mode_opens_a_tab(linux, monkeypatch):
    monkeypatch.setenv("CREWCUT_OPEN", "browser")
    monkeypatch.setattr(opener.shutil, "which", which_only("google-chrome"))
    opener.main("http://localhost:4747")
    assert linux == [["default-browser", "http://localhost:4747"]]


def test_mac_uses_open_with_the_first_installed_app(monkeypatch, tmp_path):
    (tmp_path / "Microsoft Edge.app").mkdir()
    (tmp_path / "Chromium.app").mkdir()
    monkeypatch.setattr(opener.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(opener, "_windows_like", lambda: False)
    monkeypatch.setattr(opener, "_mac_app_dirs", lambda: [tmp_path])
    assert opener.app_command("http://localhost:4747") == [
        "open", "-na", "Microsoft Edge", "--args", "--app=http://localhost:4747", "--window-size=1440,900"]


def test_windows_uses_edge(monkeypatch):
    monkeypatch.setattr(opener, "_windows_like", lambda: True)
    monkeypatch.setattr(opener.shutil, "which", which_only("cmd.exe"))
    assert opener.app_command("http://localhost:4747") == [
        "/usr/bin/cmd.exe", "/c", "start", "", "msedge", "--app=http://localhost:4747"]


def test_no_screen_only_prints(linux, monkeypatch, capsys):
    monkeypatch.delenv("DISPLAY")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(opener.shutil, "which", which_only("google-chrome"))
    assert opener.main("http://localhost:4747") == 0
    assert linux == [] and "Open http://localhost:4747 in a browser" in capsys.readouterr().out


def test_waits_for_the_server_and_gives_up_with_a_hint(linux, monkeypatch, capsys):
    monkeypatch.setattr(opener, "answers", lambda url: False)
    now = [0.0]
    monkeypatch.setattr(opener.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    monkeypatch.setattr(opener.time, "monotonic", lambda: now[0])
    assert opener.main("http://localhost:4747", timeout=60) == 1
    out = capsys.readouterr().out
    assert "Waiting for Crewcut" in out and "did not answer within 1 minutes" in out and linux == []


# ---------- the shell side: host/open-app.sh, as ./start.sh runs it ----------

def stub(dir_: Path, name: str, body: str) -> None:
    p = dir_ / name
    p.write_text(f"#!/bin/sh\n{body}\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def run_open_app(tmp_path, *args, env=None, browsers=("google-chrome",)):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    log = tmp_path / "opened.txt"
    stub(bin_, "curl", "exit 0")
    stub(bin_, "uname", "echo Linux")
    stub(bin_, "xdg-settings", "echo firefox.desktop")
    stub(bin_, "xdg-open", f'echo "xdg-open $*" >> "{log}"')
    for b in browsers:
        stub(bin_, b, f'echo "{b} $*" >> "{log}"')
    # Only the stubs and a few plain tools: a browser installed on the machine that runs the tests is never found.
    for tool in ("nohup", "grep", "sed", "date", "sleep", "cat", "sh"):
        real = shutil.which(tool)
        if real and not (bin_ / tool).exists():
            (bin_ / tool).symlink_to(real)
    e = {"PATH": str(bin_), "HOME": str(tmp_path), "DISPLAY": ":0", **(env or {})}
    r = subprocess.run([shutil.which("bash"), str(ROOT / "host/open-app.sh"), *args], capture_output=True, text=True, env=e,
                       timeout=30)
    for _ in range(50):  # the browser starts in the background
        if log.exists() or "--no-open" in args or (env or {}).get("CREWCUT_OPEN") == "none":
            break
        time.sleep(0.1)
    return r, (log.read_text() if log.exists() else "")


def test_open_app_sh_opens_an_app_window(tmp_path):
    r, opened = run_open_app(tmp_path, "http://localhost:4747")
    assert r.returncode == 0 and "Crewcut: http://localhost:4747" in r.stdout
    assert opened.strip() == "google-chrome --app=http://localhost:4747"


def test_open_app_sh_no_open_and_browser_mode(tmp_path):
    r, opened = run_open_app(tmp_path, "--no-open", env={"CREWCUT_PORT": "4800"})
    assert r.stdout.strip() == "Crewcut: http://localhost:4800" and opened == ""
    r, opened = run_open_app(tmp_path, "http://localhost:4747", env={"CREWCUT_OPEN": "browser"})
    assert opened.strip() == "xdg-open http://localhost:4747"


def test_open_app_sh_without_chromium_uses_the_default_browser(tmp_path):
    r, opened = run_open_app(tmp_path, "http://localhost:4747", browsers=())
    assert opened.strip() == "xdg-open http://localhost:4747"


@pytest.mark.skipif(not (ROOT / "start.sh").exists(), reason="start.sh is not in the image (it runs on the host)")
def test_start_sh_takes_no_open_and_refuses_unknown_options():
    r = subprocess.run(["bash", str(ROOT / "start.sh"), "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "--no-open" in r.stdout and "CREWCUT_OPEN" in r.stdout
    r = subprocess.run(["bash", str(ROOT / "start.sh"), "--bogus"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    text = (ROOT / "start.sh").read_text()
    assert "host/open-app.sh" in text and "xdg-open" not in text  # one opener, shared with `crewcut open`
    assert os.access(ROOT / "host/open-app.sh", os.X_OK)
