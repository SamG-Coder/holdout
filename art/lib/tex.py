"""Procedural texture synthesis in numpy: the building blocks every material is made from.

Everything here is *tileable*: noise is made in the frequency domain or on wrapping lattices, and
filters wrap around, so a texture made from these parts repeats without a seam.

Conventions:
  * images are float32 arrays, `[y, x]` for scalars and `[y, x, 3]` for colour, row 0 at the TOP;
  * colour is linear, not sRGB, until it is written;
  * a height field is in metres when a function says so, and 0..1 otherwise.
"""

import math
import os
import struct
import zlib

import numpy as np

F = np.float32


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

def rng(seed):
    return np.random.default_rng(int(seed) & 0x7FFFFFFF)


def saturate(x):
    return np.clip(x, 0.0, 1.0)


def _is_colour(x):
    return np.ndim(x) in (1, 3) and np.shape(x)[-1] == 3


def lerp(a, b, t):
    """Mixes `a` towards `b` by `t`. A scalar field mixes colours channel by channel."""
    if np.ndim(t) == 2 and (_is_colour(a) or _is_colour(b)):
        t = np.asarray(t)[..., None]
    a = np.asarray(a, dtype=F)
    b = np.asarray(b, dtype=F)
    return a + (b - a) * t


def smoothstep(lo, hi, x):
    t = saturate((x - lo) / max(hi - lo, 1e-12)) if np.isscalar(hi) and np.isscalar(lo) \
        else saturate((x - lo) / (hi - lo))
    return t * t * (3.0 - 2.0 * t)


def normalize01(x):
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.zeros_like(x, dtype=F)
    return ((x - lo) / (hi - lo)).astype(F)


def levels(x, lo=0.0, hi=1.0, gamma=1.0):
    y = saturate((x - lo) / max(hi - lo, 1e-12))
    return y ** gamma if gamma != 1.0 else y


def rgb(r, g=None, b=None):
    """A linear colour from 0..1 values."""
    if g is None:
        return np.array([r, r, r], dtype=F)
    return np.array([r, g, b], dtype=F)


def srgb(r, g, b):
    """A linear colour from an sRGB colour given 0..255, as a paint chart gives them."""
    c = np.array([r, g, b], dtype=np.float64) / 255.0
    return srgb_to_linear(c).astype(F)


def hexcolor(text):
    text = text.lstrip('#')
    return srgb(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1.0 / 2.4) - 0.055)


def luminance(c):
    return (c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722).astype(F)


def grid(n, m=None):
    """Texel centres as (x, y) arrays in 0..1."""
    m = n if m is None else m
    xs = (np.arange(n, dtype=F) + 0.5) / n
    ys = (np.arange(m, dtype=F) + 0.5) / m
    return np.meshgrid(xs, ys)


def ramp(x, stops):
    """Maps a scalar field through colour stops: [(position, colour), ...], linear between."""
    stops = sorted(stops, key=lambda s: s[0])
    positions = np.array([s[0] for s in stops], dtype=F)
    colours = np.array([np.broadcast_to(np.asarray(s[1], dtype=F), (3,)) for s in stops], dtype=F)
    out = np.empty(x.shape + (3,), dtype=F)
    for channel in range(3):
        out[..., channel] = np.interp(x, positions, colours[:, channel])
    return out


def hsv_shift(colour, hue=0.0, saturation=1.0, value=1.0):
    """Shifts a linear RGB image's hue (in turns), and scales saturation and value."""
    c = np.asarray(colour, dtype=F)
    mx = c.max(axis=-1)
    mn = c.min(axis=-1)
    d = mx - mn
    h = np.zeros_like(mx)
    mask = d > 1e-8
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        hr = ((g - b) / d) % 6.0
        hg = (b - r) / d + 2.0
        hb = (r - g) / d + 4.0
    h = np.where(mask & (mx == r), hr, h)
    h = np.where(mask & (mx == g) & (mx != r), hg, h)
    h = np.where(mask & (mx == b) & (mx != r) & (mx != g), hb, h)
    h = (h / 6.0 + hue) % 1.0
    s = np.where(mx > 1e-8, d / np.maximum(mx, 1e-8), 0.0) * saturation
    s = np.clip(s, 0.0, 1.0)
    v = mx * value
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = i.astype(np.int32) % 6
    out = np.empty_like(c)
    out[..., 0] = np.choose(i, [v, q, p, p, t, v])
    out[..., 1] = np.choose(i, [t, v, v, q, p, p])
    out[..., 2] = np.choose(i, [p, p, t, v, v, q])
    return out.astype(F)


# ---------------------------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------------------------

def _freq(n, m=None):
    m = n if m is None else m
    fx = np.fft.fftfreq(n) * n
    fy = np.fft.fftfreq(m) * m
    return np.meshgrid(fx, fy)


def fbm(n, seed, beta=2.0, lo=1.0, hi=None, aniso=(1.0, 1.0), m=None):
    """Fractal noise by spectral synthesis: power falls as 1/f^beta between `lo` and `hi` cycles
    per tile. `aniso` stretches it: (4, 1) makes features four times longer in x than in y.
    Returns 0..1."""
    m = n if m is None else m
    r = rng(seed)
    white = r.standard_normal((m, n))
    spectrum = np.fft.fft2(white)
    fx, fy = _freq(n, m)
    f = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    f[0, 0] = 1.0
    amplitude = f ** (-beta / 2.0)
    amplitude[f < lo] = 0.0
    if hi is not None:
        amplitude *= np.exp(-(f / hi) ** 4)
    amplitude[0, 0] = 0.0
    out = np.fft.ifft2(spectrum * amplitude).real
    return normalize01(out)


def band(n, seed, centre, width=None, aniso=(1.0, 1.0), m=None):
    """Noise with features of one size: a band of frequencies around `centre` cycles per tile."""
    m = n if m is None else m
    width = centre * 0.35 if width is None else width
    r = rng(seed)
    spectrum = np.fft.fft2(r.standard_normal((m, n)))
    fx, fy = _freq(n, m)
    f = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    amplitude = np.exp(-((f - centre) / width) ** 2)
    amplitude[0, 0] = 0.0
    return normalize01(np.fft.ifft2(spectrum * amplitude).real)


def white(n, seed, m=None):
    m = n if m is None else m
    return rng(seed).random((m, n), dtype=F)


def blur(img, sigma, sigma_y=None):
    """A wrapping Gaussian blur, by `sigma` texels (optionally different in y)."""
    sigma_y = sigma if sigma_y is None else sigma_y
    if sigma <= 0 and sigma_y <= 0:
        return img
    if img.ndim == 3:
        return np.stack([blur(img[..., c], sigma, sigma_y) for c in range(img.shape[2])], axis=-1)
    m, n = img.shape
    fx = np.fft.fftfreq(n)
    fy = np.fft.fftfreq(m)
    gx = np.exp(-2.0 * (math.pi * fx * sigma) ** 2)
    gy = np.exp(-2.0 * (math.pi * fy * sigma_y) ** 2)
    out = np.fft.ifft2(np.fft.fft2(img) * gy[:, None] * gx[None, :]).real
    return out.astype(F)


def warp(img, dx, dy):
    """Samples `img` displaced by (dx, dy) texels, wrapping, with bilinear filtering."""
    m, n = img.shape[:2]
    xs, ys = np.meshgrid(np.arange(n, dtype=F), np.arange(m, dtype=F))
    x = (xs + dx) % n
    y = (ys + dy) % m
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = (x - x0).astype(F)
    fy = (y - y0).astype(F)
    x0 %= n
    y0 %= m
    x1 = (x0 + 1) % n
    y1 = (y0 + 1) % m
    if img.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    bottom = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return (top * (1 - fy) + bottom * fy).astype(F)


def domain_warp(img, seed, amount, scale=4.0):
    """Warps an image by smooth noise: `amount` texels at most, with swirls `scale` to a tile."""
    n = img.shape[1]
    m = img.shape[0]
    dx = (fbm(n, seed, beta=3.0, lo=1, hi=scale * 2, m=m) - 0.5) * 2 * amount
    dy = (fbm(n, seed + 7919, beta=3.0, lo=1, hi=scale * 2, m=m) - 0.5) * 2 * amount
    return warp(img, dx, dy)


def cracks(lines, seed):
    """Makes the straight edges of a cell pattern wander as cracks do: warped broadly, then
    finely. `lines` is a 0..1 mask of thin lines."""
    n = lines.shape[1]
    out = domain_warp(lines, seed, n * 0.035, 5.0)
    out = domain_warp(out, seed + 31, n * 0.008, 24.0)
    return saturate(out * 1.3)


def worley(n, cells, seed, jitter=1.0, m=None, cells_y=None):
    """Cellular noise on a wrapping lattice of `cells` by `cells_y` points.

    Returns (f1, f2, cell_id): distances to the nearest and second nearest point, in cells, and a
    0..1 random value for the nearest point's cell."""
    m = n if m is None else m
    cells_y = cells if cells_y is None else cells_y
    r = rng(seed)
    px = (np.arange(cells)[None, :] + 0.5 + (r.random((cells_y, cells)) - 0.5) * jitter)
    py = (np.arange(cells_y)[:, None] + 0.5 + (r.random((cells_y, cells)) - 0.5) * jitter)
    ids = r.random((cells_y, cells))
    xs = (np.arange(n, dtype=np.float64) + 0.5) / n * cells
    ys = (np.arange(m, dtype=np.float64) + 0.5) / m * cells_y
    gx, gy = np.meshgrid(xs, ys)
    cx = np.floor(gx).astype(np.int32)
    cy = np.floor(gy).astype(np.int32)
    f1 = np.full((m, n), 1e9)
    f2 = np.full((m, n), 1e9)
    best = np.zeros((m, n))
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            ix = (cx + ox) % cells
            iy = (cy + oy) % cells_y
            # The point, unwrapped to lie beside this texel's cell.
            qx = px[iy, ix] + (cx + ox - ix)
            qy = py[iy, ix] + (cy + oy - iy)
            d = np.sqrt((qx - gx) ** 2 + (qy - gy) ** 2)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            best = np.where(closer, ids[iy, ix], best)
            f1 = np.where(closer, d, f1)
    return f1.astype(F), f2.astype(F), best.astype(F)


def speckle(n, seed, density, radius, softness=0.5, m=None):
    """Random soft dots: `density` of them per tile, about `radius` texels across. 0..1."""
    m = n if m is None else m
    r = rng(seed)
    count = int(density)
    img = np.zeros((m, n), dtype=F)
    xs = r.integers(0, n, count)
    ys = r.integers(0, m, count)
    np.add.at(img, (ys, xs), r.random(count).astype(F) * 0.7 + 0.3)
    img = blur(img, radius)
    peak = img.max()
    if peak > 0:
        img = img / peak
    return saturate(smoothstep(0.0, softness, img))


def scratches(n, seed, count, length=(0.05, 0.4), width=1.0, angle=None, spread=math.pi, m=None):
    """Thin straight scratches. `angle` (radians) with `spread` around it, or any direction.
    Lengths are fractions of the tile. Returns 0..1 coverage."""
    m = n if m is None else m
    r = rng(seed)
    img = np.zeros((m, n), dtype=F)
    for _ in range(int(count)):
        x0, y0 = r.random() * n, r.random() * m
        a = (r.random() * math.tau) if angle is None else angle + (r.random() - 0.5) * spread
        ln = (length[0] + (length[1] - length[0]) * r.random() ** 2) * n
        steps = max(int(ln), 2)
        t = np.arange(steps)
        xs = (x0 + np.cos(a) * t).astype(np.int64) % n
        ys = (y0 + np.sin(a) * t).astype(np.int64) % m
        # Fades at both ends, as a real scratch does.
        strength = (r.random() * 0.7 + 0.3) * np.sin(np.linspace(0, math.pi, steps)) ** 0.5
        np.maximum.at(img, (ys, xs), strength.astype(F))
    if width > 0.6:
        img = saturate(blur(img, width * 0.5) * (1.2 + width))
    return img


# ---------------------------------------------------------------------------------------------
# 3D noise, for texturing a model by where its surface is rather than by its UVs
# ---------------------------------------------------------------------------------------------

def _hash3(ix, iy, iz, seed):
    h = (ix.astype(np.uint32) * np.uint32(0x8da6b343)) ^ (iy.astype(np.uint32) * np.uint32(0xd8163841)) \
        ^ (iz.astype(np.uint32) * np.uint32(0xcb1ab31f)) ^ np.uint32((seed * 0x9E3779B1) & 0xFFFFFFFF)
    h ^= h >> np.uint32(15)
    h *= np.uint32(0x2c1b3c6d)
    h ^= h >> np.uint32(12)
    h *= np.uint32(0x297a2d39)
    h ^= h >> np.uint32(15)
    return h


def value3(p, seed):
    """Smooth value noise at 3D points `p` (..., 3), one lattice cell per unit. 0..1."""
    p = np.asarray(p, dtype=np.float64)
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * (3.0 - 2.0 * f)
    out = np.zeros(p.shape[:-1], dtype=np.float64)
    with np.errstate(over='ignore'):
        for dz in (0, 1):
            wz = u[..., 2] if dz else 1.0 - u[..., 2]
            for dy in (0, 1):
                wy = u[..., 1] if dy else 1.0 - u[..., 1]
                for dx in (0, 1):
                    wx = u[..., 0] if dx else 1.0 - u[..., 0]
                    h = _hash3(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz, seed)
                    out += wx * wy * wz * (h.astype(np.float64) / 4294967295.0)
    return out.astype(F)


def fbm3(p, seed, octaves=5, lacunarity=2.03, gain=0.5):
    """Fractal value noise at 3D points. 0..1 (roughly)."""
    p = np.asarray(p, dtype=np.float64)
    total = np.zeros(p.shape[:-1], dtype=F)
    amplitude, norm, frequency = 1.0, 0.0, 1.0
    for octave in range(octaves):
        total += value3(p * frequency + octave * 17.31, seed + octave * 101) * amplitude
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity
    return total / norm


# ---------------------------------------------------------------------------------------------
# From heights to maps
# ---------------------------------------------------------------------------------------------

def normal_from_height(height, tile_metres, wrap=True):
    """A tangent-space normal map from a height field in METRES over a tile `tile_metres` wide.
    Returns (m, n, 3) in -1..1, +Y of the texture pointing up the image (OpenGL convention, as
    glTF wants), with row 0 at the top."""
    m, n = height.shape
    scale_x = n / tile_metres
    scale_y = m / tile_metres * (m / n) if m != n else n / tile_metres
    if wrap:
        dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * scale_x
        dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * scale_y
    else:
        dx = np.gradient(height, axis=1) * scale_x
        dy = np.gradient(height, axis=0) * scale_y
    # Row index grows downward, so +v (up the image) is -row.
    nx = -dx
    ny = dy
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / length, ny / length, nz / length], axis=-1).astype(F)


def combine_normals(a, b):
    """Lays detail normal map `b` over `a` (both -1..1), keeping both sets of slopes."""
    out = np.stack([a[..., 0] / np.maximum(a[..., 2], 1e-4) + b[..., 0] / np.maximum(b[..., 2], 1e-4),
                    a[..., 1] / np.maximum(a[..., 2], 1e-4) + b[..., 1] / np.maximum(b[..., 2], 1e-4),
                    np.ones_like(a[..., 2])], axis=-1)
    return (out / np.linalg.norm(out, axis=-1, keepdims=True)).astype(F)


def cavity_from_height(height, radius, strength=1.0):
    """How shut-in each texel is, from a height field: 1 open, towards 0 down in the pits.
    `radius` in texels."""
    around = blur(height, radius)
    span = max(float(height.max() - height.min()), 1e-6)
    occluded = saturate((around - height) / span * 4.0 * strength)
    return (1.0 - occluded).astype(F)


# ---------------------------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------------------------

def brick_pattern(n, columns, rows, mortar=0.06, bevel=0.03, offset=0.5, seed=0, jitter=0.0):
    """A running bond of bricks. Returns (height 0..1, brick_id 0..1, mortar_mask 0..1).
    `mortar` and `bevel` are fractions of a brick's height."""
    x, y = grid(n)
    v = y * rows
    row = np.floor(v)
    fy = v - row
    u = x * columns + (row % 2) * offset
    col = np.floor(u)
    fx = u - col
    r = rng(seed)
    table = r.random((rows, columns)).astype(F)
    ids = table[row.astype(np.int32) % rows, col.astype(np.int32) % columns]
    aspect = (1.0 / columns) / (1.0 / rows)  # width over height of a brick
    ex = np.minimum(fx, 1.0 - fx) * aspect   # distance to the vertical joints, in brick heights
    ey = np.minimum(fy, 1.0 - fy)
    if jitter > 0:
        wobble = (fbm(n, seed + 3, beta=2.5, lo=4) - 0.5) * jitter
        ex = ex + wobble
        ey = ey + wobble
    edge = np.minimum(ex, ey)
    half = mortar * 0.5
    mortar_mask = 1.0 - smoothstep(half * 0.7, half * 1.3, edge)
    height = smoothstep(half, half + bevel, edge)
    return height.astype(F), ids, mortar_mask.astype(F)


def plank_pattern(n, count, gap=0.012, seed=0, vertical=True, length_cells=0, bevel=0.02):
    """Boards side by side. Returns (height 0..1, board_id 0..1, gap_mask 0..1, along 0..1).
    `gap` and `bevel` are fractions of a board's width. `length_cells` > 0 cuts each board into
    lengths, staggered, that many to a tile."""
    x, y = grid(n)
    across, along = (x, y) if vertical else (y, x)
    u = across * count
    board = np.floor(u)
    f = u - board
    r = rng(seed)
    table = r.random(count).astype(F)
    ids = table[board.astype(np.int32) % count]
    edge = np.minimum(f, 1.0 - f)
    if length_cells > 0:
        shift = r.random(count).astype(F)[board.astype(np.int32) % count]
        v = along * length_cells + shift
        piece = np.floor(v)
        fv = v - piece
        ids = (ids + piece * 0.6180339) % 1.0
        end = np.minimum(fv, 1.0 - fv) * (count / max(length_cells, 1))
        edge = np.minimum(edge, end)
    gap_mask = 1.0 - smoothstep(gap * 0.5, gap * 0.5 + 0.004, edge)
    height = smoothstep(gap * 0.5, gap * 0.5 + bevel, edge)
    return height.astype(F), ids.astype(F), gap_mask.astype(F), along.astype(F)


def wood_grain(n, seed, rings=22.0, vertical=True, knots=3, m=None):
    """Wood grain running along the boards. Returns (grain 0..1 dark in the late wood,
    pores 0..1)."""
    m = n if m is None else m
    aniso = (1.0, 0.06) if vertical else (0.06, 1.0)
    # Slow wander across the grain, long along it.
    wander = fbm(n, seed, beta=2.6, lo=1, hi=24, aniso=aniso, m=m)
    x, y = grid(n, m)
    across = x if vertical else y
    phase = across * rings + (wander - 0.5) * rings * 0.9
    r = rng(seed + 5)
    for _ in range(knots):
        kx, ky = r.random(), r.random()
        dx = np.minimum(np.abs(x - kx), 1 - np.abs(x - kx))
        dy = np.minimum(np.abs(y - ky), 1 - np.abs(y - ky))
        d = np.sqrt((dx * (1.0 if vertical else 0.35)) ** 2 + (dy * (0.35 if vertical else 1.0)) ** 2)
        phase += np.exp(-(d / 0.06) ** 2) * 6.0
    rings_ = 0.5 + 0.5 * np.sin(phase * math.tau)
    grain = rings_ ** 2.2
    fine = fbm(n, seed + 11, beta=1.2, lo=8, aniso=(1.0, 0.03) if vertical else (0.03, 1.0), m=m)
    pores = saturate((fine - 0.55) * 4.0)
    return saturate(grain * 0.75 + fine * 0.25).astype(F), pores.astype(F)


def weave(n, threads, seed=0, depth=1.0):
    """A plain weave of `threads` by `threads` yarns. Returns height 0..1."""
    x, y = grid(n)
    u = x * threads
    v = y * threads
    iu = np.floor(u)
    iv = np.floor(v)
    fu = u - iu
    fv = v - iv
    over = ((iu + iv) % 2) < 1.0
    warp_h = np.sin(fu * math.pi) * (0.55 + 0.45 * np.cos((fv - 0.5) * math.pi))
    weft_h = np.sin(fv * math.pi) * (0.55 + 0.45 * np.cos((fu - 0.5) * math.pi))
    h = np.where(over, np.maximum(warp_h, weft_h * 0.55), np.maximum(weft_h, warp_h * 0.55))
    irregular = fbm(n, seed, beta=1.5, lo=threads * 0.25)
    return saturate(h * (0.85 + 0.3 * irregular) * depth).astype(F)


# ---------------------------------------------------------------------------------------------
# Writing images
# ---------------------------------------------------------------------------------------------

def _png_bytes(data, channels):
    m, n = data.shape[:2]
    raw = np.empty((m, n * channels + 1), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = data.reshape(m, n * channels)
    colour_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]

    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', n, m, 8, colour_type, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw.tobytes(), 6))
            + chunk(b'IEND', b''))


def write_png(path, image, is_colour=False):
    """Writes an 8-bit PNG. `image` is 0..1: (m, n), (m, n, 3) or (m, n, 4). Colour is converted
    from linear to sRGB (alpha left alone)."""
    image = np.asarray(image, dtype=np.float64)
    if image.ndim == 2:
        image = image[..., None]
    if is_colour:
        image = image.copy()
        image[..., :3] = linear_to_srgb(image[..., :3])
    data = np.clip(np.rint(image * 255.0), 0, 255).astype(np.uint8)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, 'wb') as file:
        file.write(_png_bytes(np.ascontiguousarray(data), data.shape[2]))


def read_png(path):
    """Reads an 8-bit, non-interlaced PNG written by `write_png`. Returns 0..1 floats, raw."""
    with open(path, 'rb') as file:
        blob = file.read()
    assert blob[:8] == b'\x89PNG\r\n\x1a\n', path
    at = 8
    idat = b''
    width = height = channels = 0
    while at < len(blob):
        length, tag = struct.unpack('>I4s', blob[at:at + 8])
        body = blob[at + 8:at + 8 + length]
        if tag == b'IHDR':
            width, height, depth, colour_type = struct.unpack('>IIBB', body[:10])
            assert depth == 8, 'only 8-bit PNGs'
            channels = {0: 1, 4: 2, 2: 3, 6: 4}[colour_type]
        elif tag == b'IDAT':
            idat += body
        at += 12 + length
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(height, width * channels + 1)
    out = np.zeros((height, width * channels), dtype=np.uint8)
    previous = np.zeros(width * channels, dtype=np.uint8)
    for row in range(height):
        kind = raw[row, 0]
        line = raw[row, 1:].astype(np.int32)
        if kind == 0:
            current = line
        elif kind == 2:
            current = (line + previous) & 255
        elif kind == 1:
            current = line.copy()
            for i in range(channels, len(current)):
                current[i] = (current[i] + current[i - channels]) & 255
        else:
            raise ValueError(f'{path}: PNG filter {kind} is not supported')
        out[row] = current
        previous = current
    return (out.reshape(height, width, channels).astype(F) / 255.0)


class TextureSet:
    """The maps of one material, and where they were written."""

    def __init__(self, name, colour, normal, roughness, metallic=None, cavity=None, alpha=None,
                 tile_metres=1.0):
        self.name = name
        self.colour = saturate(np.asarray(colour, dtype=F))
        self.normal = np.asarray(normal, dtype=F)
        self.roughness = saturate(np.asarray(roughness, dtype=F))
        shape = self.roughness.shape
        self.metallic = np.zeros(shape, dtype=F) if metallic is None else saturate(np.asarray(metallic, dtype=F))
        self.cavity = np.ones(shape, dtype=F) if cavity is None else saturate(np.asarray(cavity, dtype=F))
        self.alpha = None if alpha is None else saturate(np.asarray(alpha, dtype=F))
        self.tile_metres = tile_metres
        self.paths = {}

    def write(self, folder):
        """Writes `NAME_color.png`, `NAME_normal.png` and `NAME_orm.png` (occlusion, roughness,
        metallic in R, G, B, as glTF packs them)."""
        os.makedirs(folder, exist_ok=True)
        colour = self.colour
        if self.alpha is not None:
            colour = np.concatenate([colour, self.alpha[..., None]], axis=-1)
        self.paths['color'] = os.path.join(folder, f'{self.name}_color.png')
        write_png(self.paths['color'], colour, is_colour=True)
        self.paths['normal'] = os.path.join(folder, f'{self.name}_normal.png')
        write_png(self.paths['normal'], self.normal * 0.5 + 0.5)
        orm = np.stack([self.cavity, self.roughness, self.metallic], axis=-1)
        self.paths['orm'] = os.path.join(folder, f'{self.name}_orm.png')
        write_png(self.paths['orm'], orm)
        return self

    def preview(self, light=(0.5, 0.6, 0.62)):
        """A quick lit picture of the material, for a contact sheet: sRGB-ready linear colour."""
        l = np.asarray(light, dtype=F)
        l = l / np.linalg.norm(l)
        ndl = saturate(self.normal @ l)
        h = l + np.array([0, 0, 1], dtype=F)
        h = h / np.linalg.norm(h)
        ndh = saturate(self.normal @ h)
        shininess = 2.0 / np.maximum(self.roughness ** 4, 1e-4)
        spec = (ndh ** np.minimum(shininess, 2000.0)) * (1.0 - self.roughness) ** 2
        f0 = lerp(np.full(self.colour.shape, 0.04, dtype=F), self.colour, self.metallic)
        diffuse = self.colour * (1.0 - self.metallic[..., None])
        lit = diffuse * (ndl[..., None] * 1.6 + 0.25 * self.cavity[..., None]) + f0 * spec[..., None] * 3.0
        if self.alpha is not None:
            checker_x, checker_y = grid(self.colour.shape[1], self.colour.shape[0])
            checker = (((checker_x * 16).astype(int) + (checker_y * 16).astype(int)) % 2) * 0.15 + 0.35
            lit = lerp(np.repeat(checker[..., None], 3, axis=-1).astype(F), lit, (self.alpha > 0.5).astype(F))
        return saturate(lit)
