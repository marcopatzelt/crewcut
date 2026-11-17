#!/usr/bin/env python3
"""The whole sound track of the Crewcut launch film (17.5 s, 60 fps): every sound effect, the music bed, the room
reverb and the master, synthesized here with numpy and scipy. No recordings, samples or downloads, so no third-party
rights (docs/launch/SOUNDS.md has the sound map). Deterministic (seeded); about 10 s on a laptop CPU, no GPU.

    python3 sfx.py --out DIR [--no-bed] [--lufs -14] [--tp -1.0] [--bed-lu -9]

Writes into DIR: sfx.flac (SFX stem, with reverb), bed.flac (music bed stem), mix.wav + mix.flac (master:
-14 LUFS integrated, true peak <= -1 dBTP, 48 kHz 24 bit), mix-nobed.flac, cues.json, cues.md. Needs ffmpeg on PATH.
Cue times are global seconds of the film (frame f at 60 fps = f / 60 s = f * 800 samples at 48 kHz), taken from
ad.sh and the template timings; README.md has the beat sheet. After a timing change in ad.sh, edit cues() and the
measured lists TYPE3, TYPE6 and REEL.

Crewcut's in-video sound kit (crewcut/motion/sfx.py) is a numpy-only port of some of these recipes.
"""
import argparse, json, math, os
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
DUR = 17.5
N = int(DUR * SR)
rng = np.random.default_rng(7)


# ── basic helpers ──────────────────────────────────────────────────────────────────────────────────────────────
def T(dur):
    return np.arange(int(round(dur * SR))) / SR


def db(x):
    return 10 ** (x / 20)


def hz(note):
    """'D6' -> Hz (A4 = 440)."""
    names = {'C': -9, 'C#': -8, 'D': -7, 'D#': -6, 'E': -5, 'F': -4, 'F#': -3, 'G': -2, 'G#': -1, 'A': 0, 'A#': 1, 'B': 2}
    n, o = note[:-1], int(note[-1])
    return 440.0 * 2 ** ((names[n] + 12 * (o - 4)) / 12)


def norm(x, peak=1.0):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def fade(x, a=0.002, r=0.01):
    x = x.copy(); n = len(x) if x.ndim == 1 else x.shape[0]
    na, nr = min(int(a * SR), n), min(int(r * SR), n)
    if na: x[:na] *= np.linspace(0, 1, na)[:, None] if x.ndim > 1 else np.linspace(0, 1, na)
    if nr: x[n - nr:] *= np.linspace(1, 0, nr)[:, None] if x.ndim > 1 else np.linspace(1, 0, nr)
    return x


def noise(n, color='white'):
    w = rng.standard_normal(n + 64)
    if color == 'white':
        return w[:n]
    X = np.fft.rfft(w); f = np.fft.rfftfreq(len(w), 1 / SR); f[0] = f[1]
    X /= np.sqrt(f) if color == 'pink' else f
    y = np.fft.irfft(X, len(w))[:n]
    return y / (np.std(y) + 1e-12)


def lp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, min(fc, SR / 2 * 0.95), 'low', fs=SR, output='sos'), x, axis=0)


def hp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, 'high', fs=SR, output='sos'), x, axis=0)


def bp(x, f1, f2, order=2):
    return signal.sosfilt(signal.butter(order, [f1, min(f2, SR / 2 * 0.95)], 'band', fs=SR, output='sos'), x, axis=0)


def shaped(n, fc, bw, color='pink', nper=1024):
    """Noise through a time-varying band (Gaussian in octaves). fc, bw (octaves, FWHM): arrays of length n or scalars."""
    fc = np.broadcast_to(np.asarray(fc, float), (n,)); bw = np.broadcast_to(np.asarray(bw, float), (n,))
    x = noise(n + nper, color)
    f, tt, Z = signal.stft(x, SR, nperseg=nper, noverlap=nper - nper // 4)
    i = np.clip((tt * SR).astype(int), 0, n - 1)
    lf = np.log2(np.maximum(f, 10.0))[:, None]
    sig = (bw[i] / 2.355)[None, :]
    Z = Z * np.exp(-0.5 * ((lf - np.log2(fc[i])[None, :]) / sig) ** 2)
    _, y = signal.istft(Z, SR, nperseg=nper, noverlap=nper - nper // 4)
    y = y[:n]
    return y / (np.std(y) + 1e-12)


def glide(a, b, u, curve='log'):
    u = np.clip(u, 0, 1)
    return a * (b / a) ** u if curve == 'log' else a + (b - a) * u


def smooth(u):
    u = np.clip(u, 0, 1); return u * u * (3 - 2 * u)


def pan_st(x, p):
    """Mono -> stereo, constant power; p in [-1, 1] scalar or per-sample array."""
    p = np.clip(np.broadcast_to(np.asarray(p, float), x.shape), -1, 1)
    a = (p + 1) * math.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], axis=1) * math.sqrt(2)


def xpan(x_px):
    """Screen x (1920 wide) -> pan, kept subtle."""
    return float(np.clip((x_px - 960) / 960 * 0.7, -0.8, 0.8))


def modes(dur, freqs, decays, amps, ph=None):
    t = T(dur); y = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps):
        y += a * np.sin(2 * np.pi * f * t + (rng.uniform(0, 6.28) if ph is None else ph)) * np.exp(-t / d)
    return y


# ── sound designs (each returns a stereo array, peak about 1) ─────────────────────────────────────────────────
def whoosh(dur, peak=0.55, f_lo=350, f_hi=2600, bw=1.6, pan0=0.0, pan1=0.0, body=0.0, rise=2.2, fall=0.35,
           am_rate=None, am_depth=0.0, width=0.25, f_end=None):
    n = int(dur * SR); u = np.arange(n) / n
    up = u < peak
    env = np.where(up, (u / peak) ** rise, np.exp(-(u - peak) / max((1 - peak) * fall, 1e-3)))
    env *= np.clip((1 - u) / 0.04, 0, 1)                       # land on zero
    f_end = f_end or f_lo * 1.3
    fc = np.where(up, glide(f_lo, f_hi, smooth(u / peak)), glide(f_hi, f_end, smooth((u - peak) / (1 - peak))))
    b = bw * (0.75 + 0.5 * env)
    L, R = shaped(n, fc, b), shaped(n, fc * 1.04, b)            # two noises = stereo air
    mid = (L + R) / 2; side = (L - R) / 2
    y = np.stack([mid + width * side, mid - width * side], 1) * env[:, None]
    if am_rate is not None:                                     # rotation / flutter
        ph = np.cumsum(np.broadcast_to(np.asarray(am_rate, float), (n,))) / SR
        y *= (1 - am_depth + am_depth * (0.5 + 0.5 * np.cos(2 * np.pi * ph)))[:, None]
    if body:
        r = bp(noise(n, 'pink'), 45, 170, 3) * env ** 1.5
        y += body * np.stack([r, r], 1) / (np.max(np.abs(r)) + 1e-9)
    p = pan0 + (pan1 - pan0) * smooth(u)
    a = (np.clip(p, -1, 1) + 1) * math.pi / 4
    y = np.stack([y[:, 0] * np.cos(a), y[:, 1] * np.sin(a)], 1) * math.sqrt(2)
    return norm(fade(y, 0.003, 0.01))


def click(soft=True, release=0.075, bright=1.0):
    """Mouse click: press + quieter release, small plastic modes."""
    def one(level, shift):
        d = 0.06; t = T(d)
        tr = hp(noise(len(t)), 1800) * np.exp(-t / 0.0006)
        fr = np.array([2300, 3650, 5100, 6900]) * shift * rng.uniform(0.96, 1.04, 4)
        m = modes(d, fr, [0.009, 0.006, 0.004, 0.003], [1, 0.6, 0.35, 0.2 * bright])
        th = np.sin(2 * np.pi * 170 * t) * np.exp(-t / 0.010) * 0.5
        y = 0.6 * tr + m + th
        if soft: y = lp(y, 5200 * bright)
        return level * y
    a = one(1.0, 1.0); b = one(0.35, 1.12)
    y = np.zeros(int((release + 0.07) * SR)); y[:len(a)] += a; s = int(release * SR); y[s:s + len(b)] += b
    return norm(np.stack([y, y], 1))


def tick(space=False):
    """Keyboard key: transient, plastic modes, thock, bottom-out."""
    d = 0.07; t = T(d)
    tr = hp(noise(len(t)), 2500) * np.exp(-t / 0.0005)
    base = rng.uniform(0.9, 1.12)
    fr = (np.array([700, 1150, 1700]) if space else np.array([1500, 2450, 3900, 5600])) * base
    m = modes(d, fr, [0.012, 0.008, 0.005, 0.004][:len(fr)], [1, 0.7, 0.45, 0.25][:len(fr)])
    th = np.sin(2 * np.pi * (230 if space else 340) * base * t) * np.exp(-t / (0.016 if space else 0.008)) * (0.9 if space else 0.45)
    y = 0.5 * tr + 0.8 * m + th
    k = int(rng.uniform(0.006, 0.010) * SR)                    # bottom-out
    y[k:] += 0.35 * (hp(noise(len(t) - k), 1200) * np.exp(-np.arange(len(t) - k) / SR / 0.0008))
    y = lp(y, 7000)
    return norm(np.stack([y, y], 1)) * db(rng.uniform(-2, 0))


def reel_tick(i=0):
    d = 0.05; t = T(d)
    tr = bp(noise(len(t)), 1500, 9000) * np.exp(-t / 0.0007)
    m = modes(d, np.array([1900, 3100, 4700]) * (1 + 0.01 * i), [0.007, 0.005, 0.003], [1, 0.5, 0.3])
    y = 0.6 * tr + m
    return norm(np.stack([y, y], 1))


def pop(f0=420, f1=1300, dur=0.11, up=True, noise_amt=0.15):
    """Bubble pop (up=True: rising 'bloop'; False: falling 'pop')."""
    t = T(dur)
    f = f0 + (f1 - f0) * (1 - np.exp(-t / 0.018)) if up else f1 + (f0 - f1) * np.exp(-t / 0.012)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (1 - np.exp(-t / 0.0015)) * np.exp(-t / (dur * 0.28))
    y = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * env
    y += noise_amt * hp(noise(len(t)), 2000) * np.exp(-t / 0.002)
    return norm(np.stack([y, y], 1))


def thump(f0=95, f1=48, dur=0.45, tau=0.12, click_amt=0.25, drive=2.0):
    t = T(dur)
    f = f1 + (f0 - f1) * np.exp(-t / 0.05)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * (1 - np.exp(-t / 0.002)) * np.exp(-t / tau)
    y = np.tanh(drive * y) / np.tanh(drive)
    y += click_amt * lp(noise(len(t)), 900) * np.exp(-t / 0.006)
    return norm(np.stack([y, y], 1))


def riser(dur, root='D3'):
    """Noise + gliding tone, ends hard at the hit (the hit sound covers the cut)."""
    n = int(dur * SR); u = np.arange(n) / n
    fc = glide(260, 7500, u ** 1.4)
    nz = shaped(n, fc, 1.4 - 0.5 * u) * u ** 3
    f = hz(root) * 2 ** (2 * u ** 1.6)                         # two octaves up
    tone = np.zeros(n)
    for k, a in [(1, 1), (2, 0.5), (3, 0.33), (4, 0.25), (6, 0.12)]:
        for det in (-0.006, 0.006):
            tone += a * np.sin(2 * np.pi * np.cumsum(f * k * (1 + det)) / SR + rng.uniform(0, 6))
    tone = tone / np.max(np.abs(tone)) * u ** 2.6 * 0.5
    top = hp(noise(n), 6000) * u ** 5 * 0.25
    y = nz + tone + top
    y = np.stack([y, y], 1)
    y[:, 0] += 0.25 * shaped(n, fc * 1.1, 1.2) * u ** 3; y[:, 1] -= 0.25 * shaped(n, fc * 0.92, 1.2) * u ** 3
    return norm(fade(y, 0.05, 0.004))


GLASS = ['D6', 'E6', 'F#6', 'A6', 'B6', 'D7', 'E7', 'F#7', 'A7']


def grain(f, dur, att=0.004, glass=True):
    t = T(dur)
    env = (1 - np.exp(-t / att)) * np.exp(-t / (dur * 0.3))
    y = np.sin(2 * np.pi * f * t) * env
    if glass: y += 0.18 * np.sin(2 * np.pi * f * 2.76 * t) * env * np.exp(-t / 0.04)
    return y


def shimmer(dur, dens0=15, dens1=90, lvl0=0.3, lvl1=1.0, notes=GLASS, spread=0.8, fizz=0.0, reverse=False):
    """Glassy granular shimmer; density and level grow over time (or shrink when reverse)."""
    n = int(dur * SR); y = np.zeros((n + SR, 2))
    t = 0.0
    while t < dur:
        u = t / dur
        d = dens0 + (dens1 - dens0) * u
        t += rng.exponential(1 / d)
        if t >= dur: break
        f = hz(rng.choice(notes)) * 2 ** (rng.uniform(-6, 6) / 1200)
        g = grain(f, rng.uniform(0.05, 0.22)) * (lvl0 + (lvl1 - lvl0) * u) * rng.uniform(0.4, 1.0)
        s = int(t * SR); y[s:s + len(g)] += pan_st(g, rng.uniform(-spread, spread))
    y = y[:n]
    if fizz:
        u = np.arange(n) / n
        fz = hp(noise(n), 3500) * (rng.random(n) < 0.004 + 0.02 * u) * 6
        fz = lp(fz, 11000) * (0.3 + 0.7 * u) * fizz
        y += np.stack([fz, np.roll(fz, 37)], 1)
    if reverse: y = y[::-1]
    return norm(fade(y, 0.01, 0.03))


def shing(dur=1.2, notes=('D6', 'A6', 'D7', 'F#7')):
    """Glassy opening: a soft cluster of bell partials with a quick air swish."""
    t = T(dur); y = np.zeros((len(t), 2))
    for i, nn in enumerate(notes):
        f = hz(nn)
        for k, a, d in [(1, 1, 0.5), (2.76, 0.25, 0.18), (5.4, 0.1, 0.08)]:
            s = np.sin(2 * np.pi * f * k * t + rng.uniform(0, 6)) * a * np.exp(-t / d) * (1 - np.exp(-t / 0.003))
            y += pan_st(s * (0.8 ** i), (-0.5, 0.4, -0.2, 0.6)[i % 4])
    air = shaped(len(t), glide(3000, 9000, np.minimum(t / 0.15, 1)), 1.5) * np.exp(-t / 0.12) * 0.6
    y += np.stack([air, air], 1)
    return norm(fade(y, 0.002, 0.05))


def bell(note, dur=1.6, bright=1.0):
    t = T(dur); f = hz(note); y = np.zeros(len(t))
    for k, a, d in [(1, 1, 0.9), (2.0, 0.35, 0.5), (3.0, 0.12, 0.3), (4.2, 0.18 * bright, 0.18), (5.4, 0.08 * bright, 0.1)]:
        for det in (-0.0012, 0.0012):
            y += a * np.sin(2 * np.pi * f * k * (1 + det) * t) * np.exp(-t / d)
    y *= 1 - np.exp(-t / 0.002)
    return norm(y)


def impact():
    """Deep impact: sub drop, punch, crack, low body, a short room."""
    dur = 1.6; t = T(dur)
    f = 44 + 34 * np.exp(-t / 0.09)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.2)
    sub = np.tanh(1.8 * sub) / np.tanh(1.8)                         # harmonics: the low end reads on small speakers too
    punch = np.sin(2 * np.pi * np.cumsum(110 + 90 * np.exp(-t / 0.02)) / SR) * np.exp(-t / 0.05)
    body = bp(noise(len(t), 'pink'), 60, 380, 3) * np.exp(-t / 0.09); body /= np.max(np.abs(body))
    crack = bp(noise(len(t)), 900, 9000) * np.exp(-t / 0.012)
    crack /= np.max(np.abs(crack))
    m = np.tanh(1.4 * (1.0 * sub + 0.6 * punch + 0.5 * body)) + 0.3 * crack
    y = np.stack([m, m], 1)
    sw = hp(noise(len(t)), 300) * np.exp(-t / 0.05) * 0.12          # a little width on the attack
    y[:, 0] += sw; y[:, 1] -= sw
    return norm(fade(y, 0.0005, 0.2))


def splash(dur=0.9, pan_c=0.3):
    """Wet paint splash: a fast band-noise burst, a splat, and rising droplets thrown to one side."""
    n = int(dur * SR); t = np.arange(n) / SR; y = np.zeros((n, 2))
    burst = shaped(n, glide(2600, 1100, np.minimum(t / 0.25, 1)), 1.8) * (1 - np.exp(-t / 0.002)) * np.exp(-t / 0.07)
    burst *= 1 + 0.5 * np.sin(2 * np.pi * 37 * t + 1) * np.exp(-t / 0.08)
    y += pan_st(burst, pan_c) * 0.8
    splat = lp(noise(n), 700, 4) * np.exp(-t / 0.035); splat /= np.max(np.abs(splat))
    y += pan_st(splat * 0.7, pan_c * 0.6)
    k = 0
    while k < 30:                                               # droplets, denser early, thrown to the right
        tt = 0.015 + rng.exponential(0.12)
        if tt > dur - 0.1: continue
        f0 = rng.uniform(500, 1400); dd = rng.uniform(0.012, 0.03)
        d = pop(f0, f0 * rng.uniform(1.8, 2.8), dd * 3, up=True, noise_amt=0.05)[:, 0]
        d *= rng.uniform(0.08, 0.4) * math.exp(-tt / 0.3)
        s = int(tt * SR); e = min(n, s + len(d)); y[s:e] += pan_st(d[:e - s], np.clip(pan_c + rng.normal(0.25, 0.3), -1, 1))
        k += 1
    return norm(fade(y, 0.0005, 0.05))


def wind(dur):
    n = int(dur * SR); t = np.arange(n) / SR
    fc = 520 * 2 ** (0.5 * np.sin(2 * np.pi * 0.13 * t) + 0.3 * np.sin(2 * np.pi * 0.31 * t + 1))
    a = 0.7 + 0.3 * np.sin(2 * np.pi * 0.21 * t + 0.5) * np.sin(2 * np.pi * 0.07 * t)
    L = shaped(n, fc, 2.6) * a; R = shaped(n, fc * 1.07, 2.6) * a[::-1]
    leaves = hp(noise(n), 4000) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.17 * t)) * 0.08
    return norm(np.stack([L + leaves, R + np.roll(leaves, 4000)], 1))


def whoomp():
    """Reverse air swell into a soft low thump (used where the flakes snap into the logo)."""
    pre = 0.22; n = int(pre * SR); u = np.arange(n) / n
    sw = shaped(n, glide(400, 2200, u), 1.6) * u ** 3
    hit = thump(85, 46, 0.6, 0.13, 0.15)
    y = np.zeros((n + len(hit), 2)); y[:n] += np.stack([sw, sw], 1) * 0.5; y[n:] += hit
    air = lp(noise(len(hit)), 1300) * np.exp(-np.arange(len(hit)) / SR / 0.05) * 0.25
    y[n:, 0] += air; y[n:, 1] += air
    return norm(fade(y, 0.01, 0.1)), pre                       # (sound, offset of the hit inside it)


# ── music bed ──────────────────────────────────────────────────────────────────────────────────────────────────
def pad_chord(notes, dur, fc=1500.0, att=0.25, rel=0.25):
    t = T(dur); y = np.zeros((len(t), 2))
    for nn in notes:
        f = hz(nn)
        for det, p in [(-0.004, -0.6), (0.0, 0.0), (0.004, 0.6)]:
            v = np.zeros(len(t)); ph0 = rng.uniform(0, 6.28)
            for k in range(1, 40):
                fk = f * k * (1 + det)
                if fk > 7000: break
                g = (1 / k) / math.sqrt(1 + (fk / fc) ** 4)
                v += g * np.sin(2 * np.pi * fk * t + ph0 * k)
            y += pan_st(v, p * 0.7)
    env = np.minimum(1, t / att) * np.minimum(1, (dur - t) / rel)
    return y * env[:, None] / len(notes)


BED = [  # (start, end, chord, cutoff) -- chord changes sit on the cuts / big motions
    (0.97, 2.10, ['D3', 'A3', 'E4', 'F#4'], 1300),
    (2.04, 6.90, ['G3', 'B3', 'D4', 'F#4', 'A4'], 1700),
    (6.80, 10.10, ['B2', 'F#3', 'A3', 'D4', 'E4'], 1600),
    (10.00, 12.55, ['A2', 'E3', 'A3', 'D4', 'E4'], 1500),
    (13.278, 15.15, ['F#3', 'A3', 'D4', 'E4', 'A4'], 2200),
    (15.275, 17.50, ['D3', 'A3', 'C#4', 'E4', 'F#4', 'A4'], 2000),
]


def bed():
    y = np.zeros((N, 2))
    for i, (a, b, ch, fc) in enumerate(BED):
        att = 0.35 if i == 0 else (0.012 if a > 13 else 0.12)
        c = pad_chord(ch, b - a, fc, att=att, rel=0.3 if b < 17 else 0.6)
        s = int(a * SR); y[s:s + len(c)] += c[:N - s]
    return hp(y, 110, 2)


# ── loudness (ITU-R BS.1770-4) and true peak ───────────────────────────────────────────────────────────────────
KW = [(np.array([1.53512485958697, -2.69169618940638, 1.19839281085285]), np.array([1.0, -1.69065929318241, 0.73248077421585])),
      (np.array([1.0, -2.0, 1.0]), np.array([1.0, -1.99004745483398, 0.99007225036621]))]


def lufs(x):
    y = x
    for b, a in KW: y = signal.lfilter(b, a, y, axis=0)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    z = np.array([np.mean(y[i:i + blk] ** 2, axis=0).sum() for i in range(0, len(y) - blk + 1, hop)])
    l = -0.691 + 10 * np.log10(z + 1e-20)
    z1 = z[l > -70]
    if not len(z1): return -99.0
    rel = -0.691 + 10 * np.log10(z1.mean()) - 10
    z2 = z[l > rel]
    return float(-0.691 + 10 * np.log10(z2.mean()))


def true_peak(x):
    return float(20 * np.log10(np.max(np.abs(signal.resample_poly(x, 4, 1, axis=0))) + 1e-12))


def limiter(x, ceil_db, look=0.0025, rel=0.08):
    """Look-ahead limiter on the 4x oversampled peak."""
    c = db(ceil_db)
    up = np.abs(signal.resample_poly(x, 4, 1, axis=0)).max(axis=1)
    pk = up[: len(x) * 4].reshape(len(x), 4).max(axis=1)
    g = np.minimum(1.0, c / np.maximum(pk, 1e-9))
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    L = int(look * SR) // 2 * 2
    gm = minimum_filter1d(g, 2 * L + 1, origin=-L)               # min over [n, n + 2L]
    gm = uniform_filter1d(gm, L + 1, origin=L // 2)              # mean over [n - L, n]: never above g[n]
    r = math.exp(-1 / (rel * SR)); out = np.empty_like(gm); prev = 1.0
    for i, v in enumerate(gm):
        prev = v if v < prev else v + (prev - v) * r
        out[i] = prev
    return x * out[:, None], float(20 * np.log10(out.min()))


# ── the cue sheet ──────────────────────────────────────────────────────────────────────────────────────────────
# Keystroke times measured from the rendered video (first frame where a character's ink shows; spaces between).
# Formula that matches within a frame: typeStart + (i + 0.5) * (typeEnd - typeStart) / n, rounded to a frame.
TYPE3 = [(3.983, 'M'), (4.033, 'a'), (4.083, 'k'), (4.150, 'e'), (4.200, ' '), (4.250, 'm'), (4.317, 'y'), (4.367, ' '),
         (4.417, 'n'), (4.483, 'e'), (4.533, 'x'), (4.583, 't'), (4.650, ' '), (4.700, 'v'), (4.750, 'i'), (4.817, 'd'),
         (4.867, 'e'), (4.917, 'o')]
TYPE6 = [(12.367, 'S'), (12.450, 'h'), (12.550, 'i'), (12.633, 'p'), (12.783, 't'), (12.900, 'h'), (12.967, 'e')]
# Word-reel: frames where the selection box jumps to the next word (measured; the first change keeps the width)
REEL = [10.183, 10.233, 10.267, 10.317, 10.383, 10.467, 10.600, 10.833]


def cues():
    C = []
    def add(t, name, snd, gain, pan=None, rev=0.15, at=0.0, what=''):
        C.append(dict(t=round(t, 4), name=name, snd=snd, gain=gain, pan=pan, rev=rev, at=at, what=what))
    # Beat 2 (0-2.7): dock, click, burst, 3D logo, bristles, swirl, iris
    add(0.05, 'cursor-in', whoosh(0.32, 0.45, 900, 3800, 1.4, 0.8, 0.25, rise=1.6, fall=0.4), -25, rev=0.1, what='cursor flies into the dock')
    add(0.36, 'hover-1', pop(900, 1500, 0.06, up=True, noise_amt=0.0), -30, xpan(1286), rev=0.2, what='hover: camera icon lifts')
    add(0.56, 'hover-2', pop(820, 1400, 0.06, up=True, noise_amt=0.0), -31, xpan(1124), rev=0.2, what='hover: folder icon lifts')
    add(0.40, 'riser', riser(0.59), -17, rev=0.2, what='riser into the burst (ends on the burst frame 0.99)')
    add(0.92, 'dock-click', click(True, 0.06), -14, xpan(966), rev=0.12, what='soft click on the Crewcut icon')
    add(0.97, 'dock-pop', pop(380, 1250, 0.12, up=True, noise_amt=0.2), -19, 0.0, rev=0.25, what='icon pops into pixels')
    add(0.99, 'burst-thump', thump(110, 52, 0.5, 0.11, 0.3), -16, rev=0.2, what='disc + rings burst, soft low hit')
    add(0.99, 'burst-bloom', whoosh(0.55, 0.12, 2200, 900, 2.2, 0, 0, rise=1.0, fall=0.45, width=0.9, f_end=500), -17, rev=0.35, what='colour bloom fills the frame')
    add(1.04, 'logo-spin', whoosh(0.30, 0.35, 700, 2400, 1.3, -0.25, 0.2, rise=1.4, fall=0.4,
                                  am_rate=np.concatenate([np.full(int(0.12 * SR), 15.0), np.linspace(15, 3, int(0.18 * SR))]), am_depth=0.65), -17, rev=0.2, what='3D Slate spins in (540 deg)')
    add(1.30, 'logo-glint', shing(0.7, ('A6', 'D7', 'F#7')), -27, 0.2, rev=0.3, what='light sweeps across the logo')
    add(1.62, 'bristles', shimmer(0.36, 12, 110, 0.15, 1.0, fizz=0.5, spread=0.6), -19, rev=0.3, what='bristles grow out of the logo (glassy fizz)')
    add(1.93, 'swirl', whoosh(0.20, 0.55, 600, 3400, 1.5, -0.6, 0.6, rise=2.0, fall=0.5, am_rate=22, am_depth=0.4, width=0.8), -15, rev=0.3, what='flakes release and swirl')
    add(2.04, 'iris-shing', shing(1.3), -16, 0.0, rev=0.5, what='iris opens into the meadow (glassy shimmer)')
    add(2.04, 'iris-air', whoosh(0.5, 0.15, 2000, 6000, 2.0, 0, 0, rise=1.2, fall=0.5, width=0.9, f_end=2500), -21, rev=0.3, what='air of the opening iris')
    # Beat 3 (2.7-6.85): meadow, glass bar, push in, typing, pull back, click, white wipe
    add(2.04, 'meadow-wind', wind(4.85), -31, rev=0.0, what='meadow air (bed under beat 3)')
    add(2.06, 'bar-in', whoosh(0.28, 0.6, 500, 1900, 1.4, 0, 0, rise=1.8, fall=0.4), -24, rev=0.15, what='glass bar slides up')
    add(2.80, 'cursor-in-3', whoosh(0.45, 0.35, 800, 3000, 1.4, 0.8, xpan(652), rise=1.5, fall=0.4), -26, rev=0.1, what='cursor flies to the bar')
    add(3.45, 'bar-click', click(True, 0.07), -15, xpan(646), rev=0.12, what='click into the bar')
    add(3.47, 'push-in', whoosh(0.95, 0.5, 260, 2300, 1.8, -0.1, 0.0, body=0.45, rise=2.0, fall=0.45), -14, rev=0.25, what='camera pushes into the bar (100 -> 320 %)')
    for i, (tt, ch) in enumerate(TYPE3):
        add(tt, f'type-{i:02d}', tick(ch == ' '), -19 if ch != ' ' else -20, 0.05 + 0.02 * i, rev=0.08, what=f'typing "{ch}"')
    add(5.55, 'pull-back', whoosh(0.70, 0.18, 1800, 300, 1.8, 0, 0, body=0.3, rise=1.0, fall=0.55, f_end=250), -15, rev=0.25, what='camera pulls back out (expo)')
    add(6.00, 'cursor-in-3b', whoosh(0.42, 0.35, 800, 3000, 1.4, 0.8, xpan(1336), rise=1.5, fall=0.4), -26, rev=0.1, what='cursor flies to the glyph')
    add(6.55, 'glyph-click', click(True, 0.06), -15, xpan(1330), rev=0.12, what='click on the glyph')
    add(6.58, 'wipe-white', whoosh(0.34, 0.45, 900, 4200, 1.8, xpan(1330), 0, rise=2.0, fall=0.35, width=0.7), -16, rev=0.3, what='white circle grows from the click')
    # Beat 4 (6.85-10.05): hero card, grid flies in, button, click, dark wipe
    add(6.86, 'hero-pop', pop(300, 760, 0.16, up=True, noise_amt=0.1), -17, 0.0, rev=0.25, what='hero card springs in')
    add(6.90, 'hero-wobble', whoosh(0.45, 0.2, 500, 1100, 1.2, 0, 0, rise=1.0, fall=0.6, am_rate=6.5, am_depth=0.6), -28, rev=0.1, what='spring wobble')
    add(7.30, 'grid-pull', whoosh(0.95, 0.3, 2400, 700, 2.0, 0, 0, body=0.35, rise=1.6, fall=0.5, width=0.9, f_end=400), -15, rev=0.25, what='camera pulls back, grid flies in')
    for i in range(26):
        col = i % 7
        add(7.42 + 0.035 * i + rng.uniform(-0.008, 0.008), f'card-{i:02d}',
            whoosh(0.09, 0.4, 2000 + 300 * (i % 5), 5200, 1.0, 0, 0, rise=1.3, fall=0.4), -31 + rng.uniform(-2, 1),
            (col - 3) / 3 * 0.7, rev=0.05, what='card flutter (staggered 35 ms)')
    add(8.30, 'cursor-in-4', whoosh(0.45, 0.3, 800, 3000, 1.4, 0.85, xpan(1100), rise=1.5, fall=0.4), -26, rev=0.1, what='cursor flies to Upload')
    add(8.75, 'button-pop', pop(500, 1100, 0.1, up=True), -22, xpan(1100), rev=0.2, what='Upload button pops in')
    add(9.77, 'upload-click', click(True, 0.06), -15, xpan(1100), rev=0.12, what='click on Upload')
    add(9.79, 'wipe-dark', whoosh(0.30, 0.45, 300, 1600, 1.8, xpan(1100), 0, body=0.5, rise=2.0, fall=0.35, width=0.7), -14, rev=0.3, what='dark circle grows from the click')
    # Beat 5 (10.05-12.25): word reel, lock, click, light wipe
    add(10.08, 'reel-roll', whoosh(1.0, 0.1, 1800, 700, 1.8, 0, 0, rise=1.0, fall=0.5, am_rate=np.linspace(30, 2, int(1.0 * SR)), am_depth=0.5), -22, rev=0.15, what='reel starts to roll')
    for k, tt in enumerate(REEL[:-1]):
        add(tt, f'reel-tick-{k}', reel_tick(k), -21 + 0.6 * k, 0.0, rev=0.1, what='next word reaches the centre')
    add(REEL[-1], 'reel-lock', click(True, 0.05, bright=0.6), -16, 0.0, rev=0.2, what='box lands on "Upload"')
    add(11.30, 'cursor-in-5', whoosh(0.38, 0.3, 800, 3000, 1.4, 0.8, xpan(1010), rise=1.5, fall=0.4), -26, rev=0.1, what='cursor flies to the word')
    add(11.85, 'reel-click', click(True, 0.06), -15, xpan(1004), rev=0.12, what='click on "Upload"')
    add(11.95, 'wipe-light', whoosh(0.30, 0.5, 1100, 5200, 1.8, xpan(1004), 0, rise=2.0, fall=0.35, width=0.7), -16, rev=0.3, what='light circle grows from the click')
    # Beat 6 (12.25-15.05): typing, cursor swoop, 3D word smash, splash, pops
    for i, (tt, ch) in enumerate(TYPE6):
        add(tt, f'type6-{i}', tick(), -18, -0.35 + 0.05 * i, rev=0.08, what=f'typing "{ch}"')
    add(12.80, 'cursor-swoop', whoosh(0.45, 0.65, 700, 3600, 1.5, -0.7, xpan(880), rise=2.2, fall=0.3), -23, rev=0.12, what='cursor swoops in (echo trail)')
    add(13.23, 'smash-click', click(True, 0.05), -17, xpan(880), rev=0.1, what='click right before the smash')
    add(13.11, 'glyphs-fly', whoosh(0.20, 0.25, 3200, 700, 1.6, -0.2, 0.2, body=0.4, rise=1.2, fall=0.5, f_end=300), -16, rev=0.2, what='3D letters fly in from the camera')
    add(13.283, 'impact', impact(), -14, 0.0, rev=0.35, what='"Video!" lands: deep impact')
    add(13.30, 'splash', splash(0.9, xpan(1240)), -17, rev=0.3, what='coral/pink paint splash, thrown to the right')
    for i in range(6):
        add(13.30 + 0.025 * i, f'glyph-{i}', thump(180 + 15 * i, 120, 0.12, 0.03, 0.4), -27, -0.4 + 0.12 * i, rev=0.1, what='letters settle')
    add(13.345, 'flower-pop', pop(420, 1150, 0.12, up=True, noise_amt=0.1), -21, -0.75, rev=0.25, what='lilac flower pops')
    add(13.38, 'card-pop', pop(600, 1300, 0.08, up=True), -24, xpan(1150), rev=0.2, what='small crew card pops')
    add(13.41, 'star-pop', pop(520, 1250, 0.12, up=True, noise_amt=0.1), -21, 0.7, rev=0.25, what='yellow star pops')
    add(13.43, 'star-glint', shing(0.6, ('F#7', 'A7')), -29, 0.7, rev=0.3, what='star glint')
    # Beat 7 (15.05-17.5): converge, whoomp, logo, chime
    add(15.05, 'converge', shimmer(0.24, 140, 20, 1.0, 0.25, fizz=0.4, reverse=True), -18, rev=0.3, what='flakes swirl back in (reverse shimmer)')
    add(15.05, 'converge-air', whoosh(0.24, 0.92, 700, 3000, 1.6, 0.6, -0.1, rise=2.4, fall=0.3, am_rate=np.linspace(6, 24, int(0.24 * SR)), am_depth=0.35, width=0.8), -16, rev=0.2, what='swirl sucks in')
    w, off = whoomp()
    add(15.28, 'whoomp', w, -14, 0.0, rev=0.35, at=off, what='flakes snap into the logo: whoomp')
    add(15.31, 'retract', shimmer(0.28, 60, 5, 0.6, 0.1, notes=['D6', 'A6', 'D7'], fizz=0.3, spread=0.4), -27, rev=0.3, what='bristles retract')
    add(16.29, 'slide', whoosh(0.42, 0.3, 700, 2200, 1.4, 0.0, -0.35, rise=1.4, fall=0.45), -24, rev=0.15, what='logo slides aside')
    add(16.31, 'chime-1', np.stack([bell('D6', 1.2)] * 2, 1), -17, -0.2, rev=0.45, what='chime (D6)')
    add(16.40, 'chime-2', np.stack([bell('A6', 1.1, 0.8)] * 2, 1), -21, 0.25, rev=0.5, what='chime (A6) as "Crewcut" builds in')
    return C


# ── render ─────────────────────────────────────────────────────────────────────────────────────────────────────
def room_ir(dur=1.3, rt=0.9):
    n = int(dur * SR); t = np.arange(n) / SR
    ir = np.stack([noise(n), noise(n)], 1) * np.exp(-6.9 * t / rt)[:, None]
    ir = lp(ir, 6500) * 0.6 + lp(ir, 2500) * 0.4
    ir[: int(0.012 * SR)] = 0                                   # pre-delay
    return ir / np.sqrt((ir ** 2).sum(axis=0).mean())


def render(cl):
    dry = np.zeros((N + 3 * SR, 2)); send = np.zeros_like(dry)
    for c in cl:
        s = c['snd'] if c['snd'].ndim == 2 else np.stack([c['snd']] * 2, 1)
        if c['pan'] is not None:
            m = s.mean(axis=1); s = pan_st(m, c['pan']) * 0.85 + s * 0.15
        s = s * db(c['gain'])
        i = int(round((c['t'] - c['at']) * SR))
        if i < 0: s = s[-i:]; i = 0
        dry[i:i + len(s)] += s; send[i:i + len(s)] += s * c['rev']
    wet = signal.fftconvolve(hp(send, 250, 2), room_ir(), axes=0)[: len(dry)]   # no low end in the room: no mud
    out = dry + 0.5 * wet
    out = out[:N]
    out[-int(0.08 * SR):] *= np.linspace(1, 0, int(0.08 * SR))[:, None]
    return out


def duck(bedx, sfx, depth_db=7.0):
    e = np.abs(sfx).max(axis=1)
    e = signal.sosfilt(signal.butter(1, 6, 'low', fs=SR, output='sos'), e)
    e = e / (np.percentile(e, 99.5) + 1e-9)
    g = db(-depth_db * np.clip(e, 0, 1))
    return bedx * g[:, None]


def write(path, x, wav=True):
    tmp = path + '.f32.wav'
    wavfile.write(tmp, SR, x.astype(np.float32))
    if wav: os.system(f'ffmpeg -v error -y -i "{tmp}" -c:a pcm_s24le "{path}"')
    os.system(f'ffmpeg -v error -y -i "{tmp}" -c:a flac -sample_fmt s32 -bits_per_raw_sample 24 "{path[:-4]}.flac"')
    os.remove(tmp)


def compress(x, thr_db, ratio=2.5, att=0.008, rel=0.18, knee=6.0):
    """Gentle bus compressor (RMS detector on 1 ms blocks, soft knee); glues the hits before the limiter."""
    B = 48; nb = len(x) // B + 1
    p = np.pad((x ** 2).mean(axis=1), (0, nb * B - len(x))).reshape(nb, B).mean(axis=1)
    lv = 10 * np.log10(p + 1e-12)
    a, r = math.exp(-B / (att * SR)), math.exp(-B / (rel * SR))
    env = np.empty(nb); e = -120.0
    for i, v in enumerate(lv):
        e = v + (e - v) * (a if v > e else r); env[i] = e
    over = env - thr_db
    gr = np.where(over <= -knee / 2, 0, np.where(over >= knee / 2, over * (1 / ratio - 1),
                  (1 / ratio - 1) * (over + knee / 2) ** 2 / (2 * knee)))
    g = np.interp(np.arange(len(x)), np.arange(nb) * B + B / 2, db(gr))
    return x * g[:, None]


def master(x, target, tp):
    x = hp(x, 30, 4)                                            # nothing below 30 Hz: no rumble, more headroom
    x = compress(x / np.max(np.abs(x)), -16, 2.5)
    g = 0.0
    for _ in range(8):
        y, gr = limiter(x * db(g), tp - 0.7)                   # margin: AAC encoding adds up to ~0.5 dB of true peak
        L = lufs(y); g += target - L
        if abs(target - L) < 0.05: break
    return y, L, true_peak(y), gr, g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--no-bed', action='store_true')
    ap.add_argument('--lufs', type=float, default=-14.0); ap.add_argument('--tp', type=float, default=-1.0)
    ap.add_argument('--bed-lu', type=float, default=-9.0, help='bed loudness relative to the SFX stem')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    cl = cues()
    sfx = render(cl)
    b = bed()
    b *= db(lufs(sfx) + a.bed_lu - lufs(b))
    b = duck(b, sfx)
    rep = {}
    for name, x in [('mix', sfx + b), ('mix-nobed', sfx)]:
        y, L, P, gr, g = master(x, a.lufs, a.tp)
        rep[name] = dict(lufs=round(L, 2), true_peak=round(P, 2), max_gain_reduction_db=round(gr, 2), gain_db=round(g, 2))
        write(os.path.join(a.out, name + '.wav'), y, wav=(name == 'mix'))
        if name == 'mix': gm = g
    write(os.path.join(a.out, 'sfx.wav'), sfx * db(gm), wav=False); write(os.path.join(a.out, 'bed.wav'), b * db(gm), wav=False)
    json.dump([{k: v for k, v in c.items() if k != 'snd'} | {'frame': round(c['t'] * 60)} for c in cl],
              open(os.path.join(a.out, 'cues.json'), 'w'), indent=0)
    import re
    groups = {'type': 'typing ticks, beat 3 ("Make my next video", 18 keys)', 'type6': 'typing ticks, beat 6 ("Ship" + "the", 7 keys)',
              'card': 'card flutter, 26 cards 35 ms apart', 'reel-tick': 'reel ticks, one per word change (7)', 'glyph': 'letters settle (6 soft thuds)'}
    grp = lambda name: (re.match(r'^(.*)-\d+$', name) or [None, None])[1]
    with open(os.path.join(a.out, 'cues.md'), 'w') as f:
        f.write('| Time (s) | Frame | Cue | What | Gain (dB) |\n|---|---|---|---|---|\n')
        done = set()
        for c in sorted(cl, key=lambda c: c['t']):
            g = grp(c['name'])
            if g in groups:
                if g in done: continue
                done.add(g); ts = [x['t'] for x in cl if grp(x['name']) == g]
                f.write(f"| {min(ts):.3f}-{max(ts):.3f} | {round(min(ts) * 60)}-{round(max(ts) * 60)} | {g} | {groups[g]} | {c['gain']:.0f} |\n")
                continue
            f.write(f"| {c['t']:.3f} | {round(c['t'] * 60)} | {c['name']} | {c['what']} | {c['gain']:.0f} |\n")
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()
