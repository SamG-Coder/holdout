"""The small things effects are drawn with: a tracer, a bullet hole, a scorch mark.

    blender --background --factory-startup --python art/fx_kit.py

Writes build/kits/fx.glb with the parts `tracer`, `decal_hole`, `decal_scorch` and `grenade`. A tracer is a
metre long along the engine's Z, to be stretched to length; decals lie flat, facing up, to be
laid on whatever was hit.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from lib import bl, tex  # noqa: E402
from lib.tex import F, fbm, saturate, smoothstep  # noqa: E402

TEX = os.path.join(bl.ROOT, 'build', 'tex', 'fx')


def radial(n):
    x, y = tex.grid(n)
    dx, dy = x - 0.5, y - 0.5
    return np.sqrt(dx * dx + dy * dy) * 2.0, np.arctan2(dy, dx)


def hole_texture(n=256):
    """A bullet strike: a dark pit, a ragged ring of broken surface round it, cracks running out."""
    r, angle = radial(n)
    ragged = fbm(n, 5, beta=1.6, lo=3) - 0.5
    spikes = (np.sin(angle * 7 + ragged * 6) * 0.5 + 0.5) * 0.12
    edge = r + ragged * 0.22 - spikes
    pit = 1.0 - smoothstep(0.10, 0.2, r + ragged * 0.05)
    ring = (1.0 - smoothstep(0.36, 0.52, edge)) * (1.0 - pit)
    alpha = saturate(1.0 - smoothstep(0.40, 0.5, edge))
    colour = tex.lerp(tex.rgb(0.34, 0.33, 0.31), tex.rgb(0.012, 0.012, 0.012), pit)
    colour = colour * (0.75 + 0.5 * fbm(n, 6, beta=1.4, lo=6)[..., None])
    height = -pit * 0.004 + ring * 0.0012 * (0.5 + fbm(n, 7, beta=1.3, lo=8))
    normal = tex.normal_from_height(height.astype(F), 0.07, wrap=False)
    roughness = np.full((n, n), 0.9, dtype=F)
    made = tex.TextureSet('decal_hole', colour, normal, roughness, alpha=alpha, tile_metres=0.07)
    return made.write(TEX)


def scorch_texture(n=512):
    """Where something exploded: soot, thick at the middle and thrown out in streaks."""
    r, angle = radial(n)
    ragged = fbm(n, 15, beta=2.0, lo=2) - 0.5
    streaks = fbm(n, 16, beta=1.2, lo=4)
    rays = np.sin(angle * 23 + streaks * 9) * 0.5 + 0.5
    reach = r + ragged * 0.3 - rays * 0.16 * smoothstep(0.3, 0.9, r)
    alpha = saturate(1.0 - smoothstep(0.5, 0.9, reach))
    dither = tex.white(n, 17)
    # Thinning towards the edge: a cut-out can't fade, but it can scatter.
    alpha = (alpha > dither * 0.85).astype(F) * (reach < 0.95)
    soot = tex.lerp(tex.rgb(0.045, 0.04, 0.035), tex.rgb(0.008, 0.008, 0.008), saturate(1.0 - reach * 1.4))
    colour = soot * (0.7 + 0.6 * streaks[..., None])
    height = (fbm(n, 18, beta=1.4, lo=6) - 0.5) * 0.002
    normal = tex.normal_from_height(height.astype(F), 1.6, wrap=False)
    roughness = np.full((n, n), 0.95, dtype=F)
    made = tex.TextureSet('decal_scorch', colour, normal, roughness, alpha=alpha, tile_metres=1.6)
    return made.write(TEX)


def main():
    bl.reset()
    hole_texture()
    scorch_texture()

    # A tracer: a slim glowing spindle. The game turns its glow up.
    glow = bl.material('tracer', flat=((1.0, 0.62, 0.25), 0.5, 0.0), emissive=(1.0, 0.55, 0.2), emissive_strength=1.0)
    b = bl.Builder('tracer')
    b.lathe(glow, [(0.0, -0.5), (0.0045, -0.42), (0.006, 0.0), (0.0035, 0.44), (0.0, 0.5)], segments=8, axis='Y')
    b.finish(uv=False, smooth_angle=80)

    hole = bl.material('decal_hole', 'decal_hole', tex_dir=TEX, mask=True)
    hole['unique_uv'] = True
    b = bl.Builder('decal_hole')
    s = 0.035
    b.quad(hole, (-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0))
    obj = b.finish(uv=False)
    bl.planar_uv(obj, (-s, -s, 0), (2 * s, 0, 0), (0, 2 * s, 0))

    scorch = bl.material('decal_scorch', 'decal_scorch', tex_dir=TEX, mask=True)
    scorch['unique_uv'] = True
    b = bl.Builder('decal_scorch')
    s = 1.25
    b.quad(scorch, (-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0))
    obj = b.finish(uv=False)
    bl.planar_uv(obj, (-s, -s, 0), (2 * s, 0, 0), (0, 2 * s, 0))

    # A hand grenade: a steel body the size of a fist, the fuze and its lever on top.
    body = bl.material('paint_olive', 'painted_metal', tint=(0.13, 0.15, 0.09))
    steel = bl.material('dark_steel', 'dark_steel')
    b = bl.Builder('grenade')
    b.lathe(body, [(0.0, -0.046), (0.018, -0.044), (0.03, -0.03), (0.0325, -0.008), (0.0325, 0.008), (0.03, 0.03),
                   (0.02, 0.043), (0.0, 0.046)], segments=18)
    b.cylinder(body, 0.0335, 0.006, centre=(0, 0, 0.0), segments=18)
    b.cylinder(steel, 0.011, 0.03, centre=(0, 0, 0.058), segments=10)
    b.box(steel, (-0.012, -0.012, 0.07), (0.012, 0.012, 0.076))
    b.box(steel, (-0.008, 0.008, 0.02), (0.008, 0.012, 0.076))
    b.box(steel, (-0.008, 0.012, 0.016), (0.008, 0.036, 0.02), matrix=None)
    b.tube(steel, [(0.012, 0.0, 0.066), (0.022, 0.0, 0.066), (0.03, 0.0, 0.058), (0.022, 0.0, 0.05), (0.014, 0.0, 0.058)],
           0.0012, segments=5)
    b.finish(bevel=0.0015, bevel_segments=1, smooth_angle=50)

    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'fx.glb'))


main()
