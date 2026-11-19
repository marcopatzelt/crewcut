"""Quality contract applied before each custom Blender plate render."""
from __future__ import annotations

import json
from pathlib import Path


def bootstrap(profile: dict, out: str, probe: bool, gpu: bool) -> str:
    """Executed by Blender before the user's script; no user code is interpolated."""
    code = '''
import bpy as _cc_bpy, json as _cc_json
from pathlib import Path as _cc_Path
_cc_profile = __PROFILE_VALUE__
_cc_out = __OUTPUT_VALUE__
_cc_probe = __PROBE_VALUE__
_cc_gpu = __GPU_VALUE__
if _cc_gpu:
    _cc_prefs = _cc_bpy.context.preferences.addons['cycles'].preferences
    _cc_devices = []
    for _cc_backend in ('OPTIX', 'CUDA'):
        try:
            _cc_prefs.compute_device_type = _cc_backend
            _cc_prefs.get_devices()
            _cc_devices = [d for d in _cc_prefs.devices if d.type == _cc_backend]
            if _cc_devices:
                for d in _cc_prefs.devices:
                    d.use = d.type == _cc_backend
                break
        except Exception:
            continue
    if not _cc_devices:
        raise RuntimeError('No usable NVIDIA render device; refusing a paid CPU fallback')
def _cc_before(s, *unused, p=_cc_profile, probe=_cc_probe, gpu=_cc_gpu):
    s.render.resolution_x, s.render.resolution_y = p['size']
    s.render.resolution_percentage = 50 if probe else 100
    s.cycles.samples = 32 if probe else p['samples']
    s.cycles.device = 'GPU' if gpu else 'CPU'
    s.cycles.use_denoising = True
def _cc_after(s, *unused, p=_cc_profile, out=_cc_out, probe=_cc_probe, gpu=_cc_gpu):
    record = {'profile': p, 'probe': probe, 'gpu': gpu, 'engine': s.render.engine,
              'samples': s.cycles.samples, 'scale': s.render.resolution_percentage,
              'size': [s.render.resolution_x, s.render.resolution_y], 'device': s.cycles.device}
    _cc_Path(out).mkdir(parents=True, exist_ok=True)
    (_cc_Path(out) / 'render-settings.json').write_text(_cc_json.dumps(record))
_cc_original_ops = _cc_bpy.ops.render
class _cc_RenderOps:
    def __getattr__(self, name):
        return getattr(_cc_original_ops, name)
    def render(self, *args, **kwargs):
        _cc_before(_cc_bpy.context.scene)
        result = _cc_original_ops.render(*args, **kwargs)
        _cc_after(_cc_bpy.context.scene)
        return result
_cc_bpy.ops.render = _cc_RenderOps()
'''
    for placeholder, value in (("__PROFILE_VALUE__", profile), ("__OUTPUT_VALUE__", out),
                               ("__PROBE_VALUE__", probe), ("__GPU_VALUE__", gpu)):
        code = code.replace(placeholder, repr(value))
    return "exec(" + repr(code) + ")"


def verify(folder: Path, frames: int, profile: dict, *, probe: bool = False, gpu: bool = False) -> tuple[bool, str]:
    """Check returned files, not merely the remote command's exit code."""
    from PIL import Image
    try:
        record = json.loads((folder / "render-settings.json").read_text())
        if record.get("profile") != profile or record.get("probe") is not probe or record.get("gpu") is not gpu:
            return False, "render settings do not match the requested quality"
        if record.get("scale") != (50 if probe else 100) or record.get("size") != profile["size"]:
            return False, "render dimensions do not match the requested quality"
        if record.get("engine") == "CYCLES" and (record.get("samples", 0) < (32 if probe else profile["samples"])
                or record.get("device") != ("GPU" if gpu else "CPU")):
            return False, "Cycles sampling or render device does not match"
        expected = [max(1, frames // 2)] if probe else range(1, frames + 1)
        size = tuple(int(x * (.5 if probe else 1)) for x in profile["size"])
        for n in expected:
            with Image.open(folder / f"{n:04d}.png") as image:
                if image.size != size:
                    return False, f"frame {n} has the wrong dimensions"
                image.verify()
        if not probe:
            (folder / "complete.json").write_text(json.dumps({"profile": profile, "frames": frames}))
        return True, "all returned frames and settings checked"
    except (OSError, ValueError, KeyError) as error:
        return False, f"returned plate is incomplete or invalid: {error}"
