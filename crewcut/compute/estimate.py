"""Estimate a job both ways (here and on rented GPUs) and decide whether to suggest renting.

Rules (PLAN 4.5):
- The numbers are real: local time from a probe measured on this machine when one exists, else the config default
  (and then `local_measured` is false); rented time from the config numbers (or measured rented probes); price from
  live offers when a Vast key exists, else from config.
- With its own GPU the machine works locally: no suggestion.
- Suggest renting only when it saves a lot (more than `suggest.min_minutes_saved` and more than `suggest.min_speedup`
  times faster), at most once per job, and never again in an episode after the user said "local is fine".
- The referral link shows only with a suggestion, only without a Vast key (a key means an account), and only when the
  config has a link. Its note says what it is.
"""

from __future__ import annotations

import math
import os

from . import local, rentals, settings, state, vast


def fmt_duration(seconds: float) -> str:
    s = max(0.0, float(seconds))
    if s < 90:
        return f"about {max(1, round(s))} s"
    m = s / 60
    if m < 90:
        return f"about {round(m)} min"
    h = m / 60
    if h < 10:
        return f"about {h:.1f} h".replace(".0 h", " h")
    if h < 48:
        return f"about {round(h)} h"
    return f"about {h / 24:.1f} days".replace(".0 days", " days")


def _auto_gpus(frames: int, spf: float, overhead_s: float) -> int:
    target = settings.num("estimate.target_minutes") * 60 - overhead_s
    need = math.ceil(frames * spf / max(60.0, target)) if frames > 0 else 1
    return max(1, min(int(settings.num("limits.max_gpus")), need))


def estimate(kind: str = "blender", frames: int = 0, local_sec_per_frame: float | None = None,
             gpus: int | None = None, *, scene: str | None = None, gpu_sec_per_frame: float | None = None,
             episode: str | None = None, job: str | int | None = None, provider=None, remember: bool = True) -> dict:
    """Both estimates, the suggestion and the one sentence for a card. See docs/compute.md.

    episode and job default to CREWCUT_EPISODE and CREWCUT_JOB. With remember=True a shown suggestion is stored, so
    the same job does not get it twice.
    """
    frames = max(0, int(frames))
    k = settings.kind(kind)
    unit = str(k.get("unit") or "frames")
    episode = episode if episode is not None else (os.environ.get("CREWCUT_EPISODE") or None)
    job = job if job is not None else (os.environ.get("CREWCUT_JOB") or None)

    if local_sec_per_frame is not None:
        l_spf, l_measured, l_source = float(local_sec_per_frame), True, "given by the caller"
    else:
        l_spf, l_measured, l_source = local.sec_per_frame(kind, scene)

    g_spf = gpu_sec_per_frame or local.measured(kind, where="rented", scene=scene) or k.get("gpu_sec_per_frame")
    g_worst = max(float(k.get("gpu_sec_per_frame_worst") or 0), float(g_spf or 0)) or None
    if l_spf is None or g_spf is None:
        raise ValueError(f"no seconds-per-{unit[:-1] if unit.endswith('s') else unit} numbers for kind {kind!r}: "
                         "measure a probe or pass local_sec_per_frame and gpu_sec_per_frame")
    g_spf = float(g_spf)

    overhead = settings.num("estimate.overhead_minutes") * 60
    live = rentals.live_prices(provider) if (provider is not None or vast.has_key()) else None
    n = int(gpus) if gpus else _auto_gpus(frames, g_spf, overhead)
    if live and not gpus:
        n = min(n, len(live))  # never plan more GPUs than there are offers right now
    n = max(1, n)
    per_machine = math.ceil(frames / n) if frames else 0
    local_s = frames * l_spf
    rented_s = per_machine * g_spf + overhead
    rented_worst_s = per_machine * float(g_worst or g_spf) + overhead

    if live:
        prices, price_source = (live[:n] + [live[-1]] * n)[:n], "live offers"
    else:
        prices, price_source = [settings.num("estimate.price_per_hour")] * n, "config"
    per_hour = sum(prices)
    rented_usd = per_hour * rented_s / 3600
    rented_worst = per_hour * rented_worst_s / 3600

    saved = local_s - rented_s
    speedup = local_s / rented_s if rented_s > 0 else 0.0
    own_gpu = local.has_gpu()
    worth = (saved > settings.num("suggest.min_minutes_saved") * 60 and speedup > settings.num("suggest.min_speedup")
             and not own_gpu)
    if own_gpu:
        why = "this machine has its own GPU: work locally"
    elif not worth:
        why = (f"renting saves only {fmt_duration(max(0.0, saved))[6:]}" if saved > 0 else "renting is not faster")
    elif state.local_is_fine(episode):
        why = "you said local is fine for this episode"
    elif state.was_suggested(job):
        why = "already suggested once for this job"
    else:
        why = f"renting saves {fmt_duration(saved)[6:]} and is {speedup:.0f}x faster"
    suggest = worth and not state.local_is_fine(episode) and not state.was_suggested(job)
    if suggest and job is not None and remember:
        state.mark_suggested(job)

    ref = vast.referral_url()
    referral = {"url": ref, "note": vast.REFERRAL_NOTE} if (suggest and ref and not vast.has_key()) else None

    here = fmt_duration(local_s) + " here" + ("" if l_measured else " (not measured on this machine yet)")
    sentence = (f"{frames} {unit}: {here}, or {fmt_duration(rented_s)} on {n} rented GPU{'s' if n > 1 else ''} "
                f"for about ${rented_usd:.2f}.")
    return {
        "kind": kind, "frames": frames, "unit": unit,
        "local_seconds": round(local_s, 1), "local_measured": l_measured, "local_source": l_source,
        "local_sec_per_frame": round(l_spf, 3),
        "rented_seconds": round(rented_s, 1), "rented_usd": round(rented_usd, 2),
        "rented_usd_worst": round(rented_worst, 2), "gpu_sec_per_frame": round(g_spf, 3),
        "gpus": n, "price_per_hour": round(per_hour / n, 4), "price_source": price_source,
        "suggest_rent": suggest, "reason": why, "sentence": sentence, "referral": referral,
    }


def local_is_fine(episode: str) -> None:
    """The user said "local is fine": no more rent suggestions in this episode."""
    state.set_local_fine(episode)
