"""The second opinion through the real host helper (host/crewcut-host.sh --once) with a fake command: the signed
request from the container, the run in the helper's own folder, the answer file, refusals that answer at once, a
stale run mark, and a helper that stops when the app that started it is gone. Nothing real is started."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from crewcut import paths, second_opinion, stylegate

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "host" / "crewcut-host.sh"
TOKEN = "test-host-token-0123456789abcdef"

pytestmark = pytest.mark.skipif(
    not (shutil.which("openssl") and (shutil.which("sha256sum") or shutil.which("shasum"))),
    reason="openssl and sha256sum are needed for the helper")


@pytest.fixture
def host(tmp_path, monkeypatch, studio):
    monkeypatch.setenv("CREWCUT_HOST_TOKEN", TOKEN)
    monkeypatch.setattr(stylegate, "after_second_opinion", lambda episode: None)
    fake = tmp_path / "bin"
    fake.mkdir()
    neon = fake / "neon"
    # like a real wrapper: reads $INPUT_FILE, notes where it ran, prints the JSON answer
    neon.write_text("#!/bin/sh\npwd > \"$INPUT_FILE.cwd\"\ngrep -q 'Hook line.' \"$INPUT_FILE\" || exit 1\n"
                    "printf '%s' '{\"agree\": false, \"points\": [{\"text\": \"Hook line.\", \"why\": \"says nothing\","
                    " \"rewrite\": \"\"}], \"model\": \"fake-neon\"}'\n")
    neon.chmod(0o755)
    so_dir = tmp_path / "second-opinion"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CREWCUT_STUDIO_DIR": str(studio),
           "CREWCUT_HOST_TOKEN": TOKEN, "CREWCUT_HOST_BY": "desktop app", "CREWCUT_SECOND_OPINION_CMD": str(neon),
           "CREWCUT_SECOND_OPINION_DIR": str(so_dir), "CREWCUT_SECOND_OPINION_PARALLEL": "2"}
    brief = studio / "episodes" / "001" / "brief"
    brief.mkdir(parents=True)
    (brief / "CUES-v001.md").write_text("Hook line.\n---\nnotes\n")
    (brief / "CUES-v001.kritik.json").write_text('{"verdict": "pass"}')
    return {"env": env, "brief": brief, "so_dir": so_dir}


def run_helper(env):
    r = subprocess.run([str(HELPER), "--once"], env=env, capture_output=True, text=True, timeout=30)
    assert TOKEN not in r.stdout + r.stderr
    return r


def wait_for(path: Path, s: float = 15) -> Path:
    end = time.time() + s
    while time.time() < end and not path.is_file():
        time.sleep(0.1)
    assert path.is_file(), path
    return path


def ask(host):
    b = host["brief"]
    return second_opinion.request("001", b / "CUES-v001.md", b / "CUES-v001.second.json", b / "CUES-v001.kritik.json",
                                  checksum="sum-1")


def test_the_heartbeat_names_who_runs_the_helper_and_the_doctor_says_so(host):
    run_helper(host["env"])
    beat = json.loads((second_opinion.box() / "helper.json").read_text())
    assert beat["by"] == "desktop app" and beat["second_opinion"] is True and beat["second_opinion_parallel"] == 2
    assert second_opinion.why_not() is None
    assert second_opinion.ready() == "the host helper (desktop app) can ask a second model, at most 2 at a time"


def test_a_signed_request_runs_the_command_in_its_own_folder_and_the_answer_reaches_the_card(host):
    run_helper(host["env"])
    req = ask(host)
    assert req["status"] == "requested"
    run_helper(host["env"])
    out = wait_for(second_opinion.box() / "runs" / f"{req['id']}.json")
    for _ in range(50):  # the run ends a moment after its output is in place
        if not list((second_opinion.box() / "runs").glob("*.running")):
            break
        time.sleep(0.1)
    assert json.loads(out.read_text())["model"] == "fake-neon"
    assert Path(f"{second_opinion.box()}/runs/{req['id']}.input.cwd").read_text().strip() == str(host["so_dir"])
    [done] = second_opinion.tick(force=True)
    answer = json.loads((host["brief"] / "CUES-v001.second.json").read_text())
    assert done["status"] == answer["status"] == "ok" and answer["agree"] is False and answer["checksum"] == "sum-1"
    assert answer["points"][0]["text"] == "Hook line." and answer["model"] == "fake-neon"


def test_a_refused_request_answers_at_once_instead_of_after_fifteen_minutes(host):
    run_helper(host["env"])
    req = ask(host)
    other = dict(host["env"], CREWCUT_HOST_TOKEN="another-key-0123456789abcdef0123")
    run_helper(other)
    out = json.loads(wait_for(second_opinion.box() / "runs" / f"{req['id']}.json").read_text())
    assert out["status"] == "unavailable" and "not signed by this Crewcut" in out["error"]
    [done] = second_opinion.tick(force=True)
    assert done["status"] == "unavailable" and "not signed by this Crewcut" in done["reason"]
    no_cmd = {k: v for k, v in host["env"].items() if k != "CREWCUT_SECOND_OPINION_CMD"}
    run_helper(host["env"])
    req2 = ask(host)
    run_helper(no_cmd)
    out2 = json.loads(wait_for(second_opinion.box() / "runs" / f"{req2['id']}.json").read_text())
    assert "No second-opinion command" in out2["error"]


def test_a_stale_run_mark_does_not_block_the_next_runs(host):
    runs = second_opinion.box() / "runs"
    runs.mkdir(parents=True)
    old = time.time() - 3600
    for i in (1, 2):
        mark = runs / f"so-old-{i}.running"
        mark.touch()
        os.utime(mark, (old, old))
    run_helper(host["env"])
    assert not list(runs.glob("*.running"))
    req = ask(host)
    run_helper(host["env"])
    assert json.loads(wait_for(runs / f"{req['id']}.json").read_text()).get("status") != "unavailable"


def test_the_helper_stops_when_the_app_that_started_it_is_gone(host, studio):
    parent = subprocess.Popen(["sleep", "1"])
    env = dict(host["env"], CREWCUT_HOST_PARENT=str(parent.pid))
    helper = subprocess.Popen([str(HELPER)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(paths.state_dir() / "host" / "helper.json")
        parent.wait()
        assert helper.wait(timeout=10) == 0
        assert not (paths.state_dir() / "host" / "helper.json").exists()
    finally:
        if helper.poll() is None:
            helper.kill()
