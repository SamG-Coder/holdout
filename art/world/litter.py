"""What lies on the ground in Alder Ridge in October of a year nobody raked: fallen leaves,
and the Directorate's leaflets.

    blender --background --factory-startup --python art/world/litter.py -- [--preview]

Writes build/kits/litter.glb: `leaves_a`, `leaves_b` and `leaves_c` (a drift, a scatter and a
few), each a cut-out sheet two metres square lying just clear of the ground, and `leaflets`.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

import numpy as np  # noqa: E402

from lib import bl, preview, tex  # noqa: E402
from lib.tex import F, saturate  # noqa: E402

TEX = os.path.join(bl.ROOT, 'build', 'tex', 'litter')
SIZE = 2.0

# The colours leaves turn, linear: gold, amber, russet, brown, the last of the green.
PALETTE = [(0.42, 0.25, 0.035), (0.46, 0.17, 0.025), (0.30, 0.075, 0.02), (0.16, 0.085, 0.035),
           (0.22, 0.2, 0.05), (0.36, 0.3, 0.06), (0.11, 0.06, 0.03)]


def leaves_texture(name, count, seed, n=1024, clump=0.0):
    """Leaves strewn over a square: `count` of them, each a pointed oval with a midrib, lying
    at any angle. `clump` draws them toward a drift across the middle."""
    rng = np.random.default_rng(seed)
    colour = np.zeros((n, n, 3), dtype=F)
    alpha = np.zeros((n, n), dtype=F)
    height = np.zeros((n, n), dtype=F)
    px = SIZE / n
    for index in range(count):
        length = rng.uniform(0.05, 0.095) / px
        width = length * rng.uniform(0.42, 0.62)
        if clump > 0 and rng.random() < clump:
            cx = rng.uniform(0.08, 0.92) * n
            cy = (0.5 + rng.normal(0, 0.11)) * n
        else:
            cx, cy = rng.uniform(0.06, 0.94) * n, rng.uniform(0.06, 0.94) * n
        angle = rng.uniform(0, math.tau)
        reach = int(length * 0.6) + 2
        x0, x1 = int(max(cx - reach, 0)), int(min(cx + reach, n))
        y0, y1 = int(max(cy - reach, 0)), int(min(cy + reach, n))
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        dx, dy = xs - cx, ys - cy
        u = (dx * math.cos(angle) + dy * math.sin(angle)) / (length * 0.5)
        v = (-dx * math.sin(angle) + dy * math.cos(angle)) / (width * 0.5)
        # A leaf: widest a little behind the middle, drawn to a point at the tip, with lobes.
        lobes = 1.0 + 0.16 * np.cos(u * rng.uniform(5.0, 9.0) + rng.uniform(0, 6.0))
        outline = (1.0 - np.abs(u) ** 1.7) * (0.75 + 0.25 * u) * lobes
        inside = (np.abs(u) < 1.0) & (np.abs(v) < np.clip(outline, 0.0, 2.0))
        if not inside.any():
            continue
        base = np.array(PALETTE[rng.integers(len(PALETTE))], dtype=F) * rng.uniform(0.7, 1.2)
        rib = np.exp(-(v * 7.0) ** 2) * 0.35 + np.exp(-((np.abs(v) - np.abs(u * 0.6) % 0.3) * 9.0) ** 2) * 0.12
        edge = np.clip(np.abs(v) / np.maximum(outline, 1e-3), 0, 1) ** 3
        shade = (1.0 - rib) * (1.0 - edge * 0.45) * (0.85 + 0.3 * rng.random())
        patch = base[None, None, :] * shade[..., None]
        # A blotch of rot on some.
        if rng.random() < 0.4:
            bu, bv = rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4)
            blotch = np.exp(-(((u - bu) * 2.5) ** 2 + ((v - bv) * 2.5) ** 2))
            patch = patch * (1.0 - 0.55 * blotch[..., None])
        region = (slice(y0, y1), slice(x0, x1))
        colour[region] = np.where(inside[..., None], patch, colour[region])
        alpha[region] = np.where(inside, 1.0, alpha[region])
        # Each lies a little over those before it, curled up at the edges.
        height[region] = np.where(inside, index * 2e-6 + (np.abs(v) ** 2) * 0.0012, height[region])
    normal = tex.normal_from_height(height.astype(F), SIZE, wrap=False)
    roughness = np.full((n, n), 0.82, dtype=F)
    made = tex.TextureSet(name, colour, normal, roughness, alpha=alpha, tile_metres=SIZE)
    return made.write(TEX)


def leaflets_texture(name='leaflets', n=1024, seed=5):
    """A dozen of the occupier's leaflets, thrown from a lorry and left: pale paper with a
    red band and lines of print, trodden and rained on."""
    rng = np.random.default_rng(seed)
    colour = np.zeros((n, n, 3), dtype=F)
    alpha = np.zeros((n, n), dtype=F)
    px = SIZE / n
    for _ in range(13):
        w, h = 0.148 / px, 0.21 / px
        cx, cy = rng.uniform(0.12, 0.88) * n, rng.uniform(0.12, 0.88) * n
        angle = rng.uniform(0, math.tau)
        reach = int(max(w, h) * 0.75) + 2
        x0, x1 = int(max(cx - reach, 0)), int(min(cx + reach, n))
        y0, y1 = int(max(cy - reach, 0)), int(min(cy + reach, n))
        ys, xs = np.mgrid[y0:y1, x0:x1]
        dx, dy = xs - cx, ys - cy
        u = (dx * math.cos(angle) + dy * math.sin(angle)) / (w * 0.5)
        v = (-dx * math.sin(angle) + dy * math.cos(angle)) / (h * 0.5)
        inside = (np.abs(u) < 1.0) & (np.abs(v) < 1.0)
        paper = np.ones(u.shape + (3,), dtype=F) * np.array([0.62, 0.6, 0.52], dtype=F) * rng.uniform(0.75, 1.0)
        band = (v > 0.62) & (v < 0.9)
        paper = np.where(band[..., None], np.array([0.42, 0.03, 0.025], dtype=F), paper)
        lines = (np.abs(((v + 1.0) * 9.0) % 1.0 - 0.5) < 0.16) & (v < 0.5) & (v > -0.8) & (np.abs(u) < 0.78)
        paper = np.where(lines[..., None], paper * 0.3, paper)
        stain = np.exp(-(((u - rng.uniform(-0.6, 0.6)) * 1.6) ** 2 + ((v - rng.uniform(-0.6, 0.6)) * 1.6) ** 2))
        paper = paper * (1.0 - 0.4 * stain[..., None])
        region = (slice(y0, y1), slice(x0, x1))
        colour[region] = np.where(inside[..., None], paper, colour[region])
        alpha[region] = np.where(inside, 1.0, alpha[region])
    normal = tex.normal_from_height(np.zeros((n, n), dtype=F), SIZE, wrap=False)
    roughness = np.full((n, n), 0.85, dtype=F)
    made = tex.TextureSet(name, colour, normal, roughness, alpha=alpha, tile_metres=SIZE)
    return made.write(TEX)


def sheet(name):
    """A square of ground's worth, lying two centimetres clear of whatever it is put on."""
    material = bl.material(name, name, tex_dir=TEX, mask=True, two_sided=True)
    material['unique_uv'] = True
    b = bl.Builder(name)
    half = SIZE / 2
    lift = 0.02
    b.quad(material, (-half, -half, lift), (half, -half, lift), (half, half, lift), (-half, half, lift))
    obj = b.finish(uv=False)
    bl.planar_uv(obj, (-half, -half, lift), (SIZE, 0, 0), (0, SIZE, 0))
    return obj


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    bl.reset()
    leaves_texture('leaves_a', 330, 11, clump=0.75)
    leaves_texture('leaves_b', 170, 23)
    leaves_texture('leaves_c', 60, 37)
    leaflets_texture()
    parts = [sheet(name) for name in ('leaves_a', 'leaves_b', 'leaves_c', 'leaflets')]
    if '--preview' in args:
        for index, obj in enumerate(parts):
            obj.location = (index * 2.3, 0, 0)
        import bpy
        bpy.context.view_layer.update()
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'litter.png'), parts, views=[(0, 70)],
                       size=(2000, 700), samples=16, zoom=1.5, ground=True)
        for obj in parts:
            obj.location = (0, 0, 0)
        bpy.context.view_layer.update()
    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'litter.glb'), parts)
    print('litter:', ' '.join(obj.name for obj in parts))


main()
