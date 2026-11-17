"""Helpers for the motion graphics tests: stand-in templates in the studio's style pack, a fake engine backend, a fake
compute session with a fake rented machine. Nothing here runs effectcraft-cli, ffmpeg or a rented machine."""

from __future__ import annotations

import io
import json
import math
import re
import shlex
import shutil
from pathlib import Path

from PIL import Image

STUBS = {   # name: (kind, formats, version, sounds, params)
    "number_roll": ("full", ["landscape", "portrait", "stage"], 2, [{"at": "landAt", "sound": "hit"}],
                    {"comp": "Main", "value": "0", "unit": "", "label": "", "landAt": 1.0}),
    "keyword_pop": ("overlay", ["landscape", "portrait"], 1, [{"at": "in", "sound": "pop"}],
                    {"comp": "Main", "words": ["word"]}),
    "prompt_bar": ("full", ["landscape", "portrait", "stage"], 1, [{"at": "in", "sound": "whoosh"},
                                                                    {"at": "out", "sound": "typing"}],
                   {"comp": "Main", "text": "", "typeAt": 0.5}),
    "ranking": ("full", ["landscape"], 1, [], {"comp": "Main", "items": [], "image": ""}),
    "lower_third": ("overlay", ["landscape", "portrait"], 1, [{"at": "out", "sound": "whoosh"}],
                    {"comp": "Main", "name": "", "role": ""}),
}


def template_src(name: str, kind: str | None = "full", formats=None, version: int | None = 1, sounds=None,
                 params: dict | None = None, body: str = "return {ok: true};") -> str:
    lines = [f"/* @template {name}", " * @description A stand-in for tests."]
    if kind:
        lines.append(f" * @kind {kind}")
    if formats:
        lines.append(f" * @formats {json.dumps(formats)}")
    if version:
        lines.append(f" * @version {version}")
    if sounds:
        lines.append(f" * @sounds {json.dumps(sounds)}")
    lines.append(f" * @params {json.dumps(params or {'comp': 'Main'})}")
    lines.append(" * @end */")
    return "\n".join(lines) + f"\nfunction {name}(P) {{ {body} }}\n"


def install(studio: Path, names=None) -> Path:
    """Stand-in templates in the studio's own style pack (brand/templates/motion/). Returns that folder."""
    pack = studio / "brand"
    d = pack / "templates" / "motion"
    d.mkdir(parents=True, exist_ok=True)
    if not (pack / "brand.json").is_file():
        (pack / "brand.json").write_text("{}", encoding="utf-8")
    for name in names or STUBS:
        kind, formats, version, sounds, params = STUBS[name]
        (d / f"{name}.jsx").write_text(template_src(name, kind, formats, version, sounds, params), encoding="utf-8")
    return d


def frames_between(start: float, end: float, fps: int) -> range:
    """The frames EffectCraft renders for --start/--end: those starting inside [start, end)."""
    return range(math.ceil(start * fps - 1e-9), math.ceil(end * fps - 1e-9))


_PNG: dict = {}


def png_bytes(size, alpha: bool) -> bytes:
    key = (tuple(size), alpha)
    if key not in _PNG:
        buf = io.BytesIO()
        Image.new("RGBA" if alpha else "RGB", tuple(size)).save(buf, "PNG")
        _PNG[key] = buf.getvalue()
    return _PNG[key]


def write_frames(pattern: str, start: float, end: float, fps: int, size, alpha: bool) -> None:
    folder = Path(pattern).parent
    folder.mkdir(parents=True, exist_ok=True)
    data = png_bytes(size, alpha)
    for f in frames_between(start, end, fps):
        (folder / f"f_{f:05d}.png").write_bytes(data)


class FakeBackend:
    """Stands in for crewcut.motion.backend.Backend: records calls and writes what the engine would write."""

    def __init__(self, env: dict, calls: list, fps: int = 25, size=(1920, 1080), fail_render: bool = False):
        self.env, self.calls, self.fps, self.size, self.fail_render = env, calls, fps, size, fail_render

    def run_steps(self, steps, project=None, save=True, save_as=None):
        self.calls.append({"cmd": "project", "steps": steps, "save_as": save_as, "env": dict(self.env)})
        Path(save_as).write_text("{}", encoding="utf-8")
        return {"ok": True}

    def script(self, code, project=None, save=True, save_as=None, name="x.jsx", keep=None):
        self.calls.append({"cmd": "script", "code": code, "project": project, "env": dict(self.env)})
        return {"result": "null"}

    def render(self, project, out, comp=None, start=None, end=None, fmt=None, extra=None):
        self.calls.append({"cmd": "render", "out": out, "comp": comp, "start": start, "end": end, "fmt": fmt,
                           "extra": list(extra or []), "env": dict(self.env)})
        if self.fail_render:
            from crewcut.motion.backend import BackendError
            raise BackendError("effectcraft-cli: simulated failure")
        write_frames(out, start, end, self.fps, self.size, "rgba" in (extra or []))
        return {"rendered": [{"output": out}]}


def backend_factory(calls: list, **kw):
    return lambda env: FakeBackend(env, calls, **kw)


class NeedsApproval(Exception):
    exit_code = 3

    def __init__(self, card_id):
        super().__init__(card_id)
        self.card_id = card_id


class Refused(Exception):
    exit_code = 3


class FakeMachine:
    """A rented machine as a folder: put copies there, run understands the motion commands, get copies back."""

    def __init__(self, root: Path, engine: bool = True, fps: int = 25, size=(1920, 1080)):
        self.root, self.engine, self.fps, self.size = root, engine, fps, size
        self.puts, self.runs = [], []

    def _here(self, remote: str) -> Path:
        return self.root / remote.lstrip("/")

    def put(self, sources, dest="/work/"):
        self.puts.append(([Path(p).name for p in sources], dest))
        for p in sources:
            p = Path(p)
            target = self._here(dest) / p.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if p.is_dir():
                shutil.copytree(p, target, dirs_exist_ok=True)
            else:
                shutil.copy2(p, target)

    def run(self, cmd, timeout=600, doing=None):
        self.runs.append(cmd)
        if cmd.startswith("test -x"):
            return 0, "engine-ok" if self.engine else "engine-missing"
        m = re.match(r"sh (\S+)/render\.sh (\S+)", cmd)
        if m:
            folder = self._here(m.group(1))
            for line in (folder / "chunks.txt").read_text().splitlines():
                args = shlex.split(line.split(" && ", 1)[1].split(" > ")[0])
                out = args[args.index("--out") + 1]
                s, e = float(args[args.index("--start") + 1]), float(args[args.index("--end") + 1])
                write_frames(str(self._here(out)), s, e, self.fps, self.size, "rgba" in args)
            return 0, "done"
        return 0, ""

    def get(self, remote, local):
        src = self._here(remote.rstrip("/"))
        if src.is_dir():
            shutil.copytree(src, Path(local), dirs_exist_ok=True)
        return {"files": 0}


class FakeCompute:
    NeedsApproval = NeedsApproval
    Refused = Refused

    def __init__(self, root: Path, engine: bool = True, block: Exception | None = None, **machine):
        self.root, self.engine, self.block, self.machine_kw = root, engine, block, machine
        self.sessions, self.machines = [], []

    def session(self, **kw):
        compute = self

        class S:
            destroyed = False

            def __enter__(self):
                if compute.block:
                    raise compute.block
                compute.sessions.append((kw, self))
                return self

            def rent(self, gpus, max_minutes, **more):
                self.rented = (gpus, max_minutes, more)
                m = FakeMachine(compute.root / "remote", compute.engine, **compute.machine_kw)
                compute.machines.append(m)
                return [m]

            def __exit__(self, *exc):
                self.destroyed = True
                return False
        return S()
