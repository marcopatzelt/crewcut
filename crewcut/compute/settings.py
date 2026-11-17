"""Compute settings: config/compute.toml merged with studio/config/compute.toml, with safe built-in defaults."""

from __future__ import annotations

from typing import Any

from .. import config

DEFAULTS: dict[str, Any] = {
    "provider": "vast",
    "vast_referral": "",
    "vast_template": "",
    "label_prefix": "crewcut",
    "vast": {
        "gpus": ["RTX 4090"], "premium_gpus": ["RTX 5090", "RTX PRO 6000", "L40S", "A100", "H100", "H200", "B200"],
        "max_price_per_gpu_hour": 0.60, "max_price_per_hour": 0.80, "regions": [], "min_reliability": 0.98,
        "min_inet_down_mbps": 300, "min_inet_up_mbps": 100, "min_hours_left": 4, "verified": True, "disk_gb": 40,
        "image": "", "fallback_image": "nvidia/cuda:12.4.1-runtime-ubuntu22.04", "blender_version": "5.0.1",
    },
    "limits": {
        "default_max_minutes": 60, "session_cap_usd": 3.0, "max_gpus": 8, "ssh_wait_minutes": 4,
        "image_wait_minutes": 10, "setup_minutes": 12, "probe_mb": 5, "guard_grace_minutes": 2, "check_seconds": 20,
        "guard_every_minutes": 3, "idle_minutes": 5, "idle_minutes_final": 2, "build_max_gpus": 1,
    },
    "estimate": {"price_per_hour": 0.45, "overhead_minutes": 8, "target_minutes": 30, "offers_cache_minutes": 5},
    "suggest": {"min_minutes_saved": 15, "min_speedup": 3.0},
    "kinds": {"blender": {"unit": "frames", "gpu_sec_per_frame": 45, "gpu_sec_per_frame_worst": 70,
                          "local_sec_per_frame": 144}},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict[str, Any]:
    return _merge(DEFAULTS, config.load("compute"))


def get(dotted: str, default: Any = None) -> Any:
    cur: Any = load()
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def num(dotted: str) -> float:
    """A number setting; falls back to the built-in default when the user's value is not a number."""
    v = get(dotted)
    try:
        return float(v)
    except (TypeError, ValueError):
        cur: Any = DEFAULTS
        for part in dotted.split("."):
            cur = cur[part]
        return float(cur)


def kind(name: str) -> dict[str, Any]:
    return dict(get(f"kinds.{name}", {}) or {})
