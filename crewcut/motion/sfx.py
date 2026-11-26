"""Crewcut's sound kit: short sound effects for videos, made by code at first use, so the repository holds no audio
file and no licence question comes with them.

``ensure_kit()`` writes the kit once into ``studio/.crewcut/sfx/`` (48 kHz, 24-bit WAV) and keeps ``kit.json`` there
with the kit version, the seed and the sha256 of every file. A file is made again only when it is missing or changed,
or when the kit version or the seed changes. Same seed, same machine: the same bytes.

The recipes are NumPy-only ports of the launch film's sound track (``examples/launch-film/sfx.py``, which uses SciPy):
filtered noise, damped modes and gliding sines. Filters here are RBJ biquads (second-order Butterworth sections) run
sample by sample, and the moving noise band of the whoosh is shaped frame by frame with the FFT.

The assembly uses ``hit``, ``typing`` and ``whoosh`` when neither the plan nor the style pack names a file
(``crewcut.render.assemble``). The quiet set ``pop_soft``, ``whoosh_soft`` and ``swoosh`` belongs to the effect layer
on picture events (``crewcut.render.sfx_events``), which stays off until the user has listened to it and approved it.
Nobody has listened to these files yet: ``docs/sfx-listening.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import wave
import zlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import paths

SR = 48000
BITS = 24
KIT_VERSION = 1
DEFAULT_SEED = 7
PEAK_DB = -1.5                    # every file peaks here (the limit is -1 dBFS)


# ---- helpers ----------------------------------------------------------------------------------------------------
def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * SR))) / SR


def _db(x: float) -> float:
    return 10 ** (x / 20)


def _hz(note: str) -> float:
    """'D6' -> Hz (A4 = 440)."""
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
    return 440.0 * 2 ** ((names[note[:-1]] + 12 * (int(note[-1]) - 4)) / 12)


def _norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x)))
    return x * (peak / m) if m > 0 else x


def _fade(x: np.ndarray, a: float = 0.002, r: float = 0.01) -> np.ndarray:
    x = x.copy()
    n = x.shape[0]
    na, nr = min(int(a * SR), n), min(int(r * SR), n)
    shape = (-1, 1) if x.ndim > 1 else (-1,)
    if na:
        x[:na] *= np.linspace(0, 1, na).reshape(shape)
    if nr:
        x[n - nr:] *= np.linspace(1, 0, nr).reshape(shape)
    return x


def _noise(rng: np.random.Generator, n: int, color: str = "white") -> np.ndarray:
    w = rng.standard_normal(n + 64)
    if color == "white":
        return w[:n]
    X = np.fft.rfft(w)
    f = np.fft.rfftfreq(len(w), 1 / SR)
    f[0] = f[1]
    X /= np.sqrt(f) if color == "pink" else f
    y = np.fft.irfft(X, len(w))[:n]
    return y / (np.std(y) + 1e-12)


def _biquad(x: np.ndarray, kind: str, fc: float, q: float = 1 / math.sqrt(2)) -> np.ndarray:
    """One RBJ low- or high-pass section (q = 1/sqrt(2): second-order Butterworth), causal, along axis 0."""
    fc = min(fc, SR / 2 * 0.95)
    w0 = 2 * math.pi * fc / SR
    c, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    if kind == "low":
        b0, b1, b2 = (1 - c) / 2, 1 - c, (1 - c) / 2
    else:
        b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
    a0, a1, a2 = 1 + alpha, -2 * c, 1 - alpha
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    if x.ndim > 1:
        return np.stack([_biquad(x[:, k], kind, fc, q) for k in range(x.shape[1])], axis=1)
    out = []
    x1 = x2 = y1 = y2 = 0.0
    for v in x.tolist():
        y = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, y
        out.append(y)
    return np.asarray(out)


def _lp(x: np.ndarray, fc: float) -> np.ndarray:
    return _biquad(x, "low", fc)


def _hp(x: np.ndarray, fc: float) -> np.ndarray:
    return _biquad(x, "high", fc)


def _bp(x: np.ndarray, f1: float, f2: float) -> np.ndarray:
    return _lp(_hp(x, f1), f2)


def _shaped(rng: np.random.Generator, n: int, fc, bw, color: str = "pink", nper: int = 1024) -> np.ndarray:
    """Noise through a band that moves over time: a Gaussian in octaves around fc with width bw (octaves, FWHM).
    fc and bw are arrays of length n or scalars. Short-time FFT, Hann windows at a quarter-frame hop, overlap-add."""
    fc = np.broadcast_to(np.asarray(fc, float), (n,))
    bw = np.broadcast_to(np.asarray(bw, float), (n,))
    hop = nper // 4
    x = _noise(rng, n + nper, color)
    xp = np.pad(x, (nper // 2, nper))
    win = np.hanning(nper + 1)[:-1]
    frames = np.lib.stride_tricks.sliding_window_view(xp, nper)[::hop]
    centre = np.clip(np.arange(len(frames)) * hop, 0, n - 1)        # frame centre in samples of the result
    f = np.fft.rfftfreq(nper, 1 / SR)
    lf = np.log2(np.maximum(f, 10.0))[None, :]
    sig = (bw[centre] / 2.355)[:, None]
    gain = np.exp(-0.5 * ((lf - np.log2(fc[centre])[:, None]) / sig) ** 2)
    y_frames = np.fft.irfft(np.fft.rfft(frames * win, axis=1) * gain, n=nper, axis=1) * win
    y = np.zeros(len(xp))
    wsum = np.zeros(len(xp))
    for i, fr in enumerate(y_frames):
        y[i * hop:i * hop + nper] += fr
        wsum[i * hop:i * hop + nper] += win ** 2
    y = (y / np.maximum(wsum, 1e-3))[nper // 2:nper // 2 + n]
    return y / (np.std(y) + 1e-12)


def _glide(a: float, b: float, u):
    return a * (b / a) ** np.clip(u, 0, 1)


def _smooth(u):
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def _modes(rng: np.random.Generator, dur: float, freqs, decays, amps) -> np.ndarray:
    t = _t(dur)
    y = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps, strict=False):
        y += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / d)
    return y


# ---- the sounds (each returns mono (n,) or stereo (n, 2), peak about 1) ------------------------------------------
def whoosh(rng: np.random.Generator, dur: float = 0.45, peak: float = 0.45, f_lo: float = 500, f_hi: float = 2600,
           bw: float = 1.5, rise: float = 1.8, fall: float = 0.4, width: float = 0.6) -> np.ndarray:
    """Air past the ear: pink noise in a band that rises to the peak and falls after it; two noises give width."""
    n = int(round(dur * SR))
    u = np.arange(n) / n
    up = u < peak
    env = np.where(up, (u / peak) ** rise, np.exp(-(u - peak) / max((1 - peak) * fall, 1e-3)))
    env *= np.clip((1 - u) / 0.04, 0, 1)                            # land on zero
    f_end = f_lo * 1.3
    fc = np.where(up, _glide(f_lo, f_hi, _smooth(u / peak)), _glide(f_hi, f_end, _smooth((u - peak) / (1 - peak))))
    b = bw * (0.75 + 0.5 * env)
    left, right = _shaped(rng, n, fc, b), _shaped(rng, n, fc * 1.04, b)
    mid, side = (left + right) / 2, (left - right) / 2
    y = np.stack([mid + width * side, mid - width * side], 1) * env[:, None]
    return _norm(_fade(y, 0.003, 0.01))


def tick(rng: np.random.Generator, space: bool = False) -> np.ndarray:
    """One key: transient, plastic modes, thock, bottom-out. Also one step of a counter roll."""
    d = 0.07
    t = _t(d)
    tr = _hp(_noise(rng, len(t)), 2500) * np.exp(-t / 0.0005)
    base = rng.uniform(0.9, 1.12)
    fr = (np.array([700, 1150, 1700]) if space else np.array([1500, 2450, 3900, 5600])) * base
    m = _modes(rng, d, fr, [0.012, 0.008, 0.005, 0.004][:len(fr)], [1, 0.7, 0.45, 0.25][:len(fr)])
    th = np.sin(2 * np.pi * (230 if space else 340) * base * t) * np.exp(-t / (0.016 if space else 0.008)) * (0.9 if space else 0.45)
    y = 0.5 * tr + 0.8 * m + th
    k = int(rng.uniform(0.006, 0.010) * SR)                         # bottom-out
    y[k:] += 0.35 * (_hp(_noise(rng, len(t) - k), 1200) * np.exp(-np.arange(len(t) - k) / SR / 0.0008))
    return _norm(_lp(y, 7000)) * _db(rng.uniform(-2, 0))


def typing(rng: np.random.Generator, dur: float = 1.2) -> np.ndarray:
    """A run of ticks, 50 to 75 ms apart (typing, or a counter rolling); the assembly trims it to the entry's length."""
    n = int(round(dur * SR))
    y = np.zeros(n + int(0.1 * SR))
    at = 0.0
    while at < dur - 0.07:
        k = tick(rng)
        s = int(at * SR)
        y[s:s + len(k)] += k
        at += rng.uniform(0.05, 0.075)
    return _norm(_fade(y[:n], 0.0, 0.02))


def pop(rng: np.random.Generator, f0: float = 420, f1: float = 1300, dur: float = 0.11, noise_amt: float = 0.15) -> np.ndarray:
    """Bubble pop: a sine with a fast rising pitch glide ("bloop"), its second harmonic, a little noise."""
    t = _t(dur)
    f = f0 + (f1 - f0) * (1 - np.exp(-t / 0.018))
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (1 - np.exp(-t / 0.0015)) * np.exp(-t / (dur * 0.28))
    y = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * env
    y += noise_amt * _hp(_noise(rng, len(t)), 2000) * np.exp(-t / 0.002)
    return _norm(y)


def click(rng: np.random.Generator, release: float = 0.06, bright: float = 1.0) -> np.ndarray:
    """Soft mouse click: press and a quieter release, small plastic modes, low-passed."""
    def one(level: float, shift: float) -> np.ndarray:
        d = 0.06
        t = _t(d)
        tr = _hp(_noise(rng, len(t)), 1800) * np.exp(-t / 0.0006)
        fr = np.array([2300, 3650, 5100, 6900]) * shift * rng.uniform(0.96, 1.04, 4)
        m = _modes(rng, d, fr, [0.009, 0.006, 0.004, 0.003], [1, 0.6, 0.35, 0.2 * bright])
        th = np.sin(2 * np.pi * 170 * t) * np.exp(-t / 0.010) * 0.5
        return level * _lp(0.6 * tr + m + th, 5200 * bright)
    a, b = one(1.0, 1.0), one(0.35, 1.12)
    y = np.zeros(int(round((release + 0.07) * SR)))
    y[:len(a)] += a
    s = int(release * SR)
    y[s:s + len(b)] += b[:len(y) - s]
    return _norm(y)


def hit(rng: np.random.Generator, f0: float = 110, f1: float = 52, dur: float = 0.5, tau: float = 0.11,
        click_amt: float = 0.3, drive: float = 2.0) -> np.ndarray:
    """Soft low hit for talk videos (the film's burst thump, not its big impact): a falling sine, a little
    saturation so phone speakers hear it, a short dull click on top."""
    t = _t(dur)
    f = f1 + (f0 - f1) * np.exp(-t / 0.05)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * (1 - np.exp(-t / 0.002)) * np.exp(-t / tau)
    y = np.tanh(drive * y) / np.tanh(drive)
    y += click_amt * _lp(_noise(rng, len(t)), 900) * np.exp(-t / 0.006)
    return _norm(_fade(y, 0.0, 0.03))


def riser(rng: np.random.Generator, dur: float = 1.0, root: str = "D3") -> np.ndarray:
    """Build-up into a moment: a noise band sweeping up, a two-octave gliding tone stack, a hiss top; ends hard."""
    n = int(round(dur * SR))
    u = np.arange(n) / n
    fc = _glide(260, 7500, u ** 1.4)
    nz = _shaped(rng, n, fc, 1.4 - 0.5 * u) * u ** 3
    f = _hz(root) * 2 ** (2 * u ** 1.6)
    tone = np.zeros(n)
    for k, a in [(1, 1), (2, 0.5), (3, 0.33), (4, 0.25), (6, 0.12)]:
        for det in (-0.006, 0.006):
            tone += a * np.sin(2 * np.pi * np.cumsum(f * k * (1 + det)) / SR + rng.uniform(0, 6))
    tone = tone / np.max(np.abs(tone)) * u ** 2.6 * 0.5
    top = _hp(_noise(rng, n), 6000) * u ** 5 * 0.25
    y = np.stack([nz + tone + top] * 2, 1)
    y[:, 0] += 0.25 * _shaped(rng, n, fc * 1.1, 1.2) * u ** 3
    y[:, 1] -= 0.25 * _shaped(rng, n, fc * 0.92, 1.2) * u ** 3
    return _norm(_fade(y, 0.05, 0.004))


def reel_tick(rng: np.random.Generator, i: int = 0) -> np.ndarray:
    """A short mechanical click: one word or digit of a reel arriving in the centre."""
    d = 0.05
    t = _t(d)
    tr = _bp(_noise(rng, len(t)), 1500, 9000) * np.exp(-t / 0.0007)
    m = _modes(rng, d, np.array([1900, 3100, 4700]) * (1 + 0.01 * i), [0.007, 0.005, 0.003], [1, 0.5, 0.3])
    return _norm(_fade(0.6 * tr + m, 0.0, 0.004))


def bell(rng: np.random.Generator, note: str = "D6", dur: float = 1.2, bright: float = 1.0) -> np.ndarray:
    """A "done" chime: additive bell partials with a slight detune."""
    t = _t(dur)
    f = _hz(note)
    y = np.zeros(len(t))
    for k, a, d in [(1, 1, 0.9), (2.0, 0.35, 0.5), (3.0, 0.12, 0.3), (4.2, 0.18 * bright, 0.18), (5.4, 0.08 * bright, 0.1)]:
        for det in (-0.0012, 0.0012):
            y += a * np.sin(2 * np.pi * f * k * (1 + det) * t) * np.exp(-t / d)
    y *= 1 - np.exp(-t / 0.002)
    return _norm(_fade(y, 0.0, 0.05))


def pop_soft(rng: np.random.Generator) -> np.ndarray:
    """A quiet, round pop for text or a number appearing: lower and shorter than `pop`, almost no noise, no click."""
    t = _t(0.09)
    f = 300 + (820 - 300) * (1 - np.exp(-t / 0.014))
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.022)
    y = (np.sin(ph) + 0.10 * np.sin(2 * ph)) * env
    y += 0.04 * _lp(_hp(_noise(rng, len(t)), 1500), 6000) * np.exp(-t / 0.003)
    return _norm(_fade(_lp(y, 5000), 0.001, 0.015))


def whoosh_soft(rng: np.random.Generator) -> np.ndarray:
    """The quiet whoosh of a part change (chapter card): shorter, darker and narrower than `whoosh`."""
    return whoosh(rng, dur=0.36, peak=0.55, f_lo=380, f_hi=1500, bw=1.1, rise=1.6, fall=0.35, width=0.45)


def swoosh(rng: np.random.Generator) -> np.ndarray:
    """A short swipe for a B-roll change: a quick falling band of air, lighter than the whoosh."""
    return whoosh(rng, dur=0.24, peak=0.3, f_lo=700, f_hi=2200, bw=0.9, rise=1.2, fall=0.5, width=0.5)


# name -> (recipe, length in seconds, what it is for)
SOUNDS: dict[str, tuple[Callable[[np.random.Generator], np.ndarray], float, str]] = {
    "whoosh": (whoosh, 0.45, "a keyword or lower third moving in, a camera move"),
    "tick": (tick, 0.07, "one keystroke, or one step of a counter"),
    "typing": (typing, 1.2, "typing under text, a counter rolling"),
    "pop": (pop, 0.11, "something small appearing: an icon, a card, a chip"),
    "click": (click, 0.13, "a mouse click on screen"),
    "hit": (hit, 0.5, "a strong moment in a talk video: a number lands"),
    "riser": (riser, 1.0, "the build-up into a reveal (not in a talk segment)"),
    "reel_tick": (reel_tick, 0.05, "a word reel or digit wheel arriving on its next item"),
    "bell": (bell, 1.2, "a \"done\" moment"),
    "pop_soft": (pop_soft, 0.09, "the effect layer: text or a number appears (quiet)"),
    "whoosh_soft": (whoosh_soft, 0.36, "the effect layer: a part change, before the pop (quiet)"),
    "swoosh": (swoosh, 0.24, "the effect layer: a B-roll or picture change (quiet)"),
}


# ---- the kit on disk ----------------------------------------------------------------------------------------------
def default_dir() -> Path:
    """studio/.crewcut/sfx"""
    return paths.state_dir() / "sfx"


def make(name: str, seed: int = DEFAULT_SEED) -> np.ndarray:
    """One kit sound as floats at PEAK_DB, deterministic for (name, seed)."""
    recipe = SOUNDS[name][0]
    rng = np.random.default_rng([seed, zlib.crc32(name.encode())])
    return _norm(recipe(rng), _db(PEAK_DB))


def _write_wav(path: Path, x: np.ndarray) -> None:
    ch = 1 if x.ndim == 1 else x.shape[1]
    full = 2 ** (BITS - 1) - 1
    q = np.clip(np.round(x * full), -full - 1, full).astype("<i4")
    data = q.reshape(-1).view(np.uint8).reshape(-1, 4)[:, :3].tobytes() if BITS == 24 else q.astype("<i2").tobytes()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(BITS // 8)
        w.setframerate(SR)
        w.writeframes(data)
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def ensure_kit(dest: Path | None = None, seed: int = DEFAULT_SEED) -> dict[str, Path]:
    """Make the kit in `dest` (default studio/.crewcut/sfx) where needed; return {name: path of its WAV}."""
    d = Path(dest) if dest is not None else default_dir()
    d.mkdir(parents=True, exist_ok=True)
    manifest = d / "kit.json"
    old = _read_manifest(manifest)
    same_kit = old.get("version") == KIT_VERSION and old.get("seed") == seed and old.get("rate") == SR \
        and old.get("bits") == BITS
    old_files = (old.get("files") or {}) if same_kit else {}
    files: dict[str, dict] = {}
    out: dict[str, Path] = {}
    for name in SOUNDS:
        p = d / f"{name}.wav"
        rec = old_files.get(p.name)
        if not (isinstance(rec, dict) and p.is_file() and _sha256(p) == rec.get("sha256")):
            x = make(name, seed)
            _write_wav(p, x)
            rec = {"sha256": _sha256(p), "seconds": round(x.shape[0] / SR, 4), "channels": 1 if x.ndim == 1 else 2}
        files[p.name] = rec
        out[name] = p
    new = {"version": KIT_VERSION, "seed": seed, "rate": SR, "bits": BITS, "files": files}
    if new != old:
        tmp = manifest.with_name(f".kit.json.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(new, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, manifest)
    return out


def kit_path(name: str, dest: Path | None = None, seed: int = DEFAULT_SEED) -> Path:
    """The WAV of one kit sound, made first if needed."""
    if name not in SOUNDS:
        raise KeyError(f"no kit sound {name!r}; the kit has {', '.join(SOUNDS)}")
    return ensure_kit(dest, seed)[name]
