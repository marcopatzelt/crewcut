"""`crewcut open`: open Crewcut in its own app window once the server answers (host side).

The same steps as host/open-app.sh, which ./start.sh runs: print the address, wait until the server answers, then open
an app window (`--app=URL`) of Chrome, Edge, Brave, Arc or Chromium with the user's own browser profile, so no first-run
dialog appears. Without one of them, or with CREWCUT_OPEN=browser, the default browser opens a normal tab;
CREWCUT_OPEN=none (or --no-open) only prints the address. Standard library only: it runs on a computer that has
nothing of Crewcut installed but this package.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

MODES = ("app", "browser", "none")
MAC_APPS = ("Google Chrome", "Microsoft Edge", "Brave Browser", "Arc", "Chromium")
LINUX_BINS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
              "microsoft-edge-stable", "brave-browser", "brave")
LINUX_DEFAULTS = {"google-chrome": ("google-chrome", "google-chrome-stable"), "chromium": ("chromium", "chromium-browser"),
                  "edge": ("microsoft-edge", "microsoft-edge-stable"), "brave": ("brave-browser", "brave")}
FLATPAKS = ("com.google.Chrome", "org.chromium.Chromium", "com.microsoft.Edge", "com.brave.Browser")


def default_url() -> str:
    port = os.environ.get("CREWCUT_PORT") or _env_file_value("CREWCUT_PORT") or "4747"
    return f"http://localhost:{port}"


def _env_file_value(key: str) -> str | None:
    """CREWCUT_PORT from .env in the current folder (the checkout ./start.sh uses), without printing anything else."""
    try:
        lines = Path(".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or None
    return None


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/", timeout=3) as r:
            return 200 <= r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except (OSError, ValueError):
        return False


def wait(url: str, timeout: float) -> bool:
    if answers(url):
        return True
    print("Waiting for Crewcut to answer, then it opens in its own window (the first start takes a few minutes)...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(2)
        if answers(url):
            return True
    return False


def _detach(cmd: list[str]) -> bool:
    try:
        kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "posix":
            kw["start_new_session"] = True
        subprocess.Popen(cmd, **kw)  # noqa: S603 - fixed program names, the URL is one argument
        return True
    except OSError:
        return False


def _windows_like() -> bool:
    if sys.platform == "win32":
        return True
    if platform.system() == "Linux":
        try:
            return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
        except OSError:
            return False
    return False


def _mac_app_dirs() -> list[Path]:
    return [Path("/Applications"), Path.home() / "Applications"]


def app_command(url: str) -> list[str] | None:
    """The command that opens an app window on this computer, or None when no Chromium-based browser is there."""
    system = platform.system()
    if _windows_like():
        cmd = shutil.which("cmd.exe") or shutil.which("cmd")
        return [cmd, "/c", "start", "", "msedge", f"--app={url}"] if cmd else None
    if system == "Darwin":
        for app in MAC_APPS:
            if any((base / f"{app}.app").is_dir() for base in _mac_app_dirs()):
                return ["open", "-na", app, "--args", f"--app={url}", "--window-size=1440,900"]
        return None
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    order = list(LINUX_BINS)
    try:
        default = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        default = ""
    for key, bins in LINUX_DEFAULTS.items():
        if key in default:
            order = [*bins, *order]
            break
    for name in order:
        path = shutil.which(name)
        if path:
            return [path, f"--app={url}"]
    flatpak = shutil.which("flatpak")
    if flatpak:
        for app_id in FLATPAKS:
            if subprocess.run([flatpak, "info", app_id], capture_output=True).returncode == 0:
                return [flatpak, "run", app_id, f"--app={url}"]
    return None


def open_url(url: str, mode: str) -> str:
    """Opens url as mode says; returns what it did: "app", "browser" or "none"."""
    if mode == "none":
        return "none"
    headless = (platform.system() == "Linux" and not _windows_like()
                and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))
    if headless:
        return "none"
    if mode == "app":
        cmd = app_command(url)
        if cmd and _detach(cmd):
            return "app"
    try:
        return "browser" if webbrowser.open(url) else "none"
    except webbrowser.Error:
        return "none"


def main(url: str | None = None, no_open: bool = False, timeout: float | None = None) -> int:
    url = url or default_url()
    mode = "none" if no_open else (os.environ.get("CREWCUT_OPEN") or "app").strip().lower()
    if mode not in MODES:
        print(f"crewcut open: CREWCUT_OPEN must be app, browser or none (not '{mode}'); using app", file=sys.stderr)
        mode = "app"
    print(f"Crewcut: {url}")
    if mode == "none":
        return 0
    limit = timeout if timeout is not None else float(os.environ.get("CREWCUT_OPEN_TIMEOUT") or 900)
    if not wait(url, limit):
        print(f"Crewcut did not answer within {int(limit // 60)} minutes. Open {url} when it is up; "
              "'docker compose logs -f' shows what it is doing.")
        return 1
    if open_url(url, mode) == "none":
        print(f"Open {url} in a browser on this computer.")
    return 0
