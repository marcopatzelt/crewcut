"""Colour grades for the meadow loop. Input and output: float32 sRGB 0..1, H x W x 3.
day:  the film's look with a gentle graduated sky (deeper blue towards the top, like a grad filter), so white type
      over the sky needs less tint on the page.
dusk: the same frames as golden hour: a darker, deeper sky from blue-teal at the top to a warm glow at the horizon,
      warm-lit clouds, darker grass with golden back-lit tips."""
import numpy as np

HZ = 0.382  # horizon, fraction of the frame height from the top

def to_lin(c): return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def masks(lin, hz=HZ):
    H, W, _ = lin.shape
    y = (np.arange(H, dtype=np.float32) / (H - 1))[:, None]
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    green = (g - np.maximum(r, b)) / (lum + 0.02)            # > 0 on grass
    above = sstep(hz + 0.015, hz - 0.02, y)                  # 1 above the horizon
    sky = above * np.clip(1 - green * 2.2, 0, 1) * sstep(0.10, 0.35, lum)
    cloud = np.clip((r / (b + 1e-4) - 0.62) / 0.3, 0, 1)     # white clouds 1, blue sky 0
    return y, lum, sky, cloud

def text_safe(lin, y, a, g, y_full=0.31, y_zero=None, hz=HZ):
    """Upper sky only: compress luminance with L' = a * L^g, so white type keeps 4.5:1 over the brightest cloud;
    full strength above y_full (fraction of the frame height), easing to none at the horizon."""
    y_zero = hz - 0.004 if y_zero is None else y_zero
    L = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    Ln = a * np.power(np.maximum(L, 1e-5), g)
    k = np.minimum(1.0, Ln / np.maximum(L, 1e-5))
    w = sstep(y_zero, y_full, y) * np.ones_like(L)
    return lin * (1 - w[..., None] + w[..., None] * k[..., None])

def day(img, hz=HZ):
    lin = to_lin(img.astype(np.float32))
    y, lum, sky, cloud = masks(lin, hz)
    # graduated sky, as with a grad filter: the open blue gets deeper towards the top, the clouds a little darker
    k = (sstep(hz, 0.0, y) ** 0.9)[..., None] * np.ones_like(lum)[..., None]
    c = cloud[..., None]
    f_open = np.array([0.42, 0.56, 0.84])
    f_cloud = np.array([0.74, 0.77, 0.84])
    f = 1 + ((f_open * (1 - c) + f_cloud * c) - 1) * k
    s = sky[..., None]
    out = lin * (1 - s) + lin * f * s
    return to_srgb(out)

def dusk(img, hz=HZ):
    lin = to_lin(img.astype(np.float32))
    y, lum, sky, cloud = masks(lin, hz)
    W = lin.shape[1]
    x = (np.arange(W, dtype=np.float32) / (W - 1))[None, :]
    # sky: deep blue at the top, a dusky violet in the middle, a warm glow at the horizon; clouds lit from below
    t = np.broadcast_to(np.clip(y / hz, 0, 1), lum.shape)[..., None]      # 0 top .. 1 horizon
    top = np.array([0.010, 0.026, 0.070])
    mid = np.array([0.075, 0.060, 0.105])
    low = np.array([0.62, 0.30, 0.10])
    a = np.clip(t / 0.6, 0, 1)
    b2 = np.clip((t - 0.6) / 0.4, 0, 1) ** 1.7
    base = (top * (1 - a) + mid * a) * (1 - b2) + low * b2
    cl = (cloud * sstep(0.25, 0.9, lum))[..., None]
    lit = np.array([0.24, 0.14, 0.15]) * (1 - t) + np.array([0.95, 0.56, 0.27]) * t   # mauve high, peach low
    shade = (lum[..., None] / (np.percentile(lum, 97) + 1e-4)) ** 0.8
    sky_rgb = base * (1 - cl) + (base * 0.5 + lit * (0.2 + 0.65 * shade)) * cl
    # ground: a little less green, darker, warm light, golden back-lit tips, cool deep shadows
    gl0 = (0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2])[..., None]
    g = gl0 + (lin - gl0) * 0.72
    g = g * np.array([1.22, 0.95, 0.52]) * 0.32
    gl = (0.2126 * g[..., 0] + 0.7152 * g[..., 1] + 0.0722 * g[..., 2])[..., None]
    hi = sstep(0.010, 0.08, gl)
    g = g * (1 - hi) + (g * np.array([1.75, 1.22, 0.42])) * hi
    g = g + np.array([0.000, 0.003, 0.006]) * (1 - sstep(0.0, 0.04, gl))
    s = sky[..., None]
    out = g * (1 - s) + sky_rgb * s
    # warm haze along the horizon (scattered low sun), strongest left of centre where the sun stands
    band = np.exp(-((y - hz) / 0.045) ** 2) * (0.5 + 0.5 * np.exp(-((x - 0.3) / 0.33) ** 2))
    out = out + band[..., None] * np.array([0.13, 0.062, 0.022])
    v = 1 - 0.30 * (((x - 0.5) / 0.7) ** 2 + ((y - 0.42) / 0.85) ** 2)
    out = out * np.clip(v, 0.55, 1)[..., None]
    out = text_safe(out, y, 0.332, 0.657, hz=hz)
    return to_srgb(out)
