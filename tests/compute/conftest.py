"""Fakes for the compute tests: a fake Vast API (httpx.MockTransport), a fake SSH/rsync runner and a fake clock.
Nothing here talks to the network or rents anything."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import httpx
import pytest

from crewcut.compute import remote, ssh, state, vast

FAKE_KEY = "fake-vast-key-0123456789abcdef"
PROBE_BYTES = 5 * 1024 * 1024


class FakeClock:
    def __init__(self):
        self.t = time.time()

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += float(s)

    def advance(self, minutes: float = 0, seconds: float = 0) -> None:
        self.t += minutes * 60 + seconds


def offer(oid: int, ip: str, price: float, gpu: str = "RTX 4090", machine: int | None = None) -> dict:
    return {"id": oid, "machine_id": machine or oid * 10, "gpu_name": gpu, "num_gpus": 1, "dph_total": price,
            "public_ipaddr": ip, "reliability2": 0.995, "geolocation": "Sweden, SE", "end_date": None,
            "inet_down": 900, "inet_up": 500}


class FakeVast:
    """Answers the endpoints Crewcut uses, keeps instances in memory, records every call."""

    key = FAKE_KEY

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.offers = [offer(1, "host-1.test", 0.40), offer(2, "host-2.test", 0.42), offer(3, "host-3.test", 0.45),
                       offer(4, "host-1.test", 0.39, machine=99),   # same host IP as offer 1
                       offer(5, "host-5.test", 0.50, gpu="RTX 3090")]
        self.instances: dict[int, dict] = {}
        self.next_id = 5000
        self.credit = 50.0
        self.keys: list[str] = []
        self.calls: list[tuple[str, str, object]] = []
        self.created: list[dict] = []
        self.pull_fails_for: set[str] = set()   # images that cannot be pulled
        self.ignore_destroy: set[int] = set()
        self.lock = threading.Lock()

    def add_instance(self, label: str | None, ip: str = "host-9.test", price: float = 0.3, age_s: float = 3600) -> int:
        with self.lock:
            self.next_id += 1
            iid = self.next_id
            self.instances[iid] = {"id": iid, "label": label, "actual_status": "running", "public_ipaddr": ip,
                                   "ports": {"22/tcp": [{"HostPort": "40022"}]}, "dph_total": price,
                                   "gpu_name": "RTX 4090", "start_date": self.clock.now() - age_s}
            return iid

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == f"Bearer {FAKE_KEY}"
        method, path = request.method, request.url.path
        body = json.loads(request.content) if request.content else None
        with self.lock:
            self.calls.append((method, path, body))
        if method == "POST" and path == "/api/v0/bundles/":
            return httpx.Response(200, json={"offers": [dict(o) for o in self.offers]})
        m = re.fullmatch(r"/api/v0/asks/(\d+)/", path)
        if method == "PUT" and m:
            o = next((x for x in self.offers if x["id"] == int(m.group(1))), None)
            if o is None:
                return httpx.Response(400, json={"success": False, "msg": "no such ask"})
            with self.lock:
                self.next_id += 1
                iid = self.next_id
                pull_fail = body["image"] in self.pull_fails_for
                self.instances[iid] = {
                    "id": iid, "label": body["label"], "image": body["image"],
                    "actual_status": "loading" if pull_fail else "running",
                    "status_msg": "Error response from daemon: pull access denied" if pull_fail else "",
                    "public_ipaddr": o["public_ipaddr"], "ports": {"22/tcp": [{"HostPort": "40022"}]},
                    "dph_total": o["dph_total"], "gpu_name": o["gpu_name"], "machine_id": o["machine_id"],
                    "start_date": self.clock.now()}
                self.created.append({"instance": iid, "offer": o["id"], **body})
            return httpx.Response(200, json={"success": True, "new_contract": iid})
        if method == "GET" and path == "/api/v1/instances/":
            return httpx.Response(200, json={"instances": [dict(i) for i in self.instances.values()],
                                             "next_token": None})
        m = re.fullmatch(r"/api/v0/instances/(\d+)/", path)
        if m and method == "GET":
            return httpx.Response(200, json={"instances": self.instances.get(int(m.group(1)))})
        if m and method == "DELETE":
            iid = int(m.group(1))
            if iid not in self.instances:
                return httpx.Response(404, json={"success": False})
            if iid not in self.ignore_destroy:
                with self.lock:
                    del self.instances[iid]
            return httpx.Response(200, json={"success": True})
        if path == "/api/v0/users/current/":
            return httpx.Response(200, json={"credit": self.credit, "api_key": FAKE_KEY, "email": "x@example.org"})
        if path == "/api/v0/ssh/" and method == "GET":
            return httpx.Response(200, json=[{"id": n, "public_key": k} for n, k in enumerate(self.keys)])
        if path == "/api/v0/ssh/" and method == "POST":
            self.keys.append(body["ssh_key"])
            return httpx.Response(200, json={"success": True})
        if re.fullmatch(r"/api/v0/instances/\d+/ssh/", path):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": "not faked"})

    def by_label(self, label: str) -> list[int]:
        return [i for i, x in self.instances.items() if x.get("label") == label]


class FakeSSH:
    """Plays ssh-keygen, ssh and rsync. Hosts can be made unreachable or fail the upload probe."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.uploads: list[tuple[list[str], str]] = []
        self.unreachable: set[str] = set()
        self.probe_fail: set[str] = set()
        self.setup_rc = 0
        self.setup_out = ("== watchdog\nwatchdog: running\ninstance key for self-delete: present\n"
                          "GPU 0: NVIDIA RTX 4090\nblender: Blender 5.0.1\napp: present\nSETUP_OK\n")
        self.run_out = "rendered 12 frames\n"
        self.remote_files: dict[str, bytes] = {"frame_0001.png": b"\x89PNG fake"}
        self.lock = threading.Lock()

    def __call__(self, argv, timeout=60, input=None):
        argv = [str(a) for a in argv]
        with self.lock:
            self.calls.append(argv)
        prog = argv[0]
        if prog == "ssh-keygen":
            f = Path(argv[argv.index("-f") + 1])
            f.write_text("PRIVATE KEY (fake)\n")
            f.with_name(f.name + ".pub").write_text("ssh-ed25519 AAAAC3FakePublicKeyBody crewcut-compute\n")
            return 0, "", ""
        if prog == "ssh":
            host, cmd = argv[-2].split("@", 1)[1], argv[-1]
            if host in self.unreachable:
                return 255, "", "ssh: connect to host: Connection refused"
            if cmd in ("echo ok", remote.PREPARE):
                return 0, "ok\n", ""
            if cmd.startswith("stat -c %s /tmp/crewcut-probe.bin"):
                return 0, ("0" if host in self.probe_fail else str(PROBE_BYTES)) + "\n", ""
            if cmd.startswith(f"bash {remote.SETUP_REMOTE}"):
                return self.setup_rc, self.setup_out, ""
            return 0, self.run_out, ""
        if prog == "rsync":
            dest = argv[-1]
            if dest.startswith("root@"):
                host = dest.split("@", 1)[1].split(":", 1)[0]
                if host in self.unreachable:
                    return 255, "", "connection refused"
                with self.lock:
                    self.uploads.append((argv[argv.index("-e") + 2:-1], dest))
                return 0, "", ""
            d = Path(dest)
            for rel, data in self.remote_files.items():
                p = d / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            return 0, "", ""
        return 127, "", f"unknown program {prog}"


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def studio(tmp_path, monkeypatch, clock):
    root = tmp_path / "studio"
    monkeypatch.setenv("CREWCUT_STUDIO", str(root))
    monkeypatch.delenv("CREWCUT_APP", raising=False)
    for k in ("VAST_API_KEY", "CREWCUT_IDENTITY", "CREWCUT_JOB", "CREWCUT_EPISODE", "ANTHROPIC_API_KEY",
              "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY", "CONTAINER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CREWCUT_LOCAL_GPU", "0")
    monkeypatch.setattr(state, "clock", clock.now)
    monkeypatch.setattr(state, "sleep", clock.sleep)
    return root


@pytest.fixture
def fake(studio, monkeypatch, clock):
    monkeypatch.setenv("VAST_API_KEY", FAKE_KEY)
    fv = FakeVast(clock)
    vast.use_transport(httpx.MockTransport(fv.handler))
    yield fv
    vast.use_transport(None)


@pytest.fixture
def fssh(fake):
    r = FakeSSH()
    ssh.use_runner(r)
    yield r
    ssh.use_runner(None)


def write_config(studio: Path, name: str, text: str) -> None:
    d = studio / "config"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.toml").write_text(text, encoding="utf-8")


@pytest.fixture
def studio_config(studio):
    return lambda name, text: write_config(studio, name, text)
