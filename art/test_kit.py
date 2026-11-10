"""A handful of quick pieces to prove the art pipeline end to end: materials, UVs, bevels,
export, bake and render. Not part of the game.

    blender --background --factory-startup --python art/test_kit.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import bl  # noqa: E402
from mathutils import Matrix  # noqa: E402


def main():
    bl.reset()
    asphalt = bl.material('asphalt', 'asphalt')
    sidewalk = bl.material('sidewalk', 'sidewalk')
    lawn = bl.material('lawn', 'lawn')
    concrete = bl.material('concrete', 'concrete')
    siding = bl.material('siding_blue', 'siding', tint=(0.42, 0.55, 0.66))
    brick = bl.material('brick', 'brick')
    shingles = bl.material('shingles', 'shingles')
    trim = bl.material('trim_white', 'painted_wood')
    fence = bl.material('fence_wood', 'fence_wood')
    plywood = bl.material('plywood', 'plywood')
    drum_paint = bl.material('drum_red', 'painted_metal', tint=(0.55, 0.07, 0.05))
    green_paint = bl.material('paint_olive', 'painted_metal', tint=(0.16, 0.19, 0.10))
    rust = bl.material('rusty_metal', 'rusty_metal')
    steel = bl.material('bare_metal', 'bare_metal')
    dark = bl.material('dark_steel', 'dark_steel')
    glass = bl.material('glass', 'glass')
    chain = bl.material('chainlink', 'chainlink', mask=True, two_sided=True)
    burlap = bl.material('burlap', 'burlap')
    corrugated = bl.material('corrugated', 'corrugated')
    rubber = bl.material('rubber', 'rubber')

    # Ground: a road, a kerb and pavement, and a lawn.
    ground = bl.Builder('ground')
    ground.box(asphalt, (-20, -4, -0.3), (20, 4, 0.0))
    ground.box(concrete, (-20, 4, -0.3), (20, 4.18, 0.15))
    ground.box(sidewalk, (-20, 4.18, -0.3), (20, 5.68, 0.15))
    ground.box(lawn, (-20, 5.68, -0.3), (20, 24, 0.12))
    ground.box(lawn, (-20, -24, -0.3), (20, -4, 0.02))
    ground.finish(bevel=0.012)

    # A jersey barrier.
    barrier = bl.Builder('barrier')
    profile = [(-0.305, 0.0), (0.305, 0.0), (0.305, 0.075), (0.18, 0.33), (0.115, 0.81),
               (-0.115, 0.81), (-0.18, 0.33), (-0.305, 0.075)]
    barrier.prism(concrete, profile, 3.0, axis='Y', offset=-1.5)
    barrier.finish(bevel=0.018, bevel_segments=3)

    # A crate.
    crate = bl.Builder('crate')
    crate.box(plywood, (-0.44, -0.44, 0.03), (0.44, 0.44, 0.87))
    for x in (-0.45, 0.45 - 0.07):
        for y in (-0.47, 0.44):
            crate.box(fence, (x, y, 0.0), (x + 0.07, y + 0.03, 0.9))
    for z in (0.0, 0.83):
        crate.box(fence, (-0.45, -0.47, z), (0.45, -0.44, z + 0.07))
        crate.box(fence, (-0.45, 0.44, z), (0.45, 0.47, z + 0.07))
        crate.box(fence, (-0.47, -0.45, z), (-0.44, 0.45, z + 0.07))
        crate.box(fence, (0.44, -0.45, z), (0.47, 0.45, z + 0.07))
    crate.finish(bevel=0.004)

    # An oil drum: turned on a lathe, with its two rolling hoops.
    drum = bl.Builder('drum')
    r = 0.286
    profile = [(0.0, 0.012), (r - 0.012, 0.012), (r - 0.012, 0.0), (r, 0.0), (r, 0.02), (r - 0.004, 0.03)]
    for hoop in (0.29, 0.59):
        profile += [(r - 0.004, hoop - 0.022), (r + 0.008, hoop - 0.008), (r + 0.008, hoop + 0.008),
                    (r - 0.004, hoop + 0.022)]
    profile += [(r - 0.004, 0.85), (r, 0.86), (r, 0.88), (r - 0.012, 0.88), (r - 0.012, 0.868), (0.0, 0.868)]
    drum.lathe(drum_paint, profile, segments=40)
    drum.cylinder(steel, 0.028, 0.012, centre=(0.17, 0.0, 0.874), segments=16)
    drum.finish(bevel=0.0015, smooth_angle=50)

    # A corner of a house: brick plinth, lap siding, a window, a pitched roof.
    house = bl.Builder('house')
    house.box(brick, (-3, -0.15, 0), (3, 0.15, 0.6))
    house.box(siding, (-3, -0.12, 0.6), (3, 0.12, 2.9))
    house.box(brick, (-3, 0.15, 0), (-2.7, 4, 0.6))
    house.box(siding, (-3, 0.12, 0.6), (-2.76, 4, 2.9))
    house.box(glass, (-0.6, -0.14, 1.1), (0.6, -0.10, 2.3))
    for lo, hi in (((-0.7, -0.17, 1.0), (0.7, -0.11, 1.1)), ((-0.7, -0.17, 2.3), (0.7, -0.11, 2.4)),
                   ((-0.7, -0.17, 1.1), (-0.6, -0.11, 2.3)), ((0.6, -0.17, 1.1), (0.7, -0.11, 2.3)),
                   ((-0.03, -0.16, 1.1), (0.03, -0.12, 2.3))):
        house.box(trim, lo, hi)
    house.box(trim, (-3.05, -0.2, 2.9), (3.05, 0.2, 3.05))
    house.prism(shingles, [(-0.5, 3.05), (4.2, 3.05), (4.2, 3.15), (1.85, 4.75), (-0.5, 3.15)],
                6.4, axis='X', offset=-3.2)
    house.finish(bevel=0.006)

    # A chain-link panel between two posts, on a rail.
    panel = bl.Builder('chainlink_panel')
    panel.quad(chain, (-1.5, 0, 0.05), (1.5, 0, 0.05), (1.5, 0, 1.95), (-1.5, 0, 1.95))
    for x in (-1.5, 1.5):
        panel.cylinder(steel, 0.03, 2.1, centre=(x, 0, 1.05), segments=14)
    panel.cylinder(steel, 0.021, 3.0, centre=(0, 0, 1.97), axis='X', segments=12)
    panel.finish(bevel=0.0)

    # A sandbag: a squashed, lumpy pillow.
    bag = bl.Builder('sandbag')
    bag.sphere(burlap, 0.5, centre=(0, 0, 0.09), segments=28, rings=16, scale=(0.72, 0.42, 0.2))
    sandbag = bag.finish(smooth_angle=80)
    bl.displace_noise(sandbag, 0.018, 9.0, seed=3)
    bl.box_uv(sandbag)

    # A sheet of corrugated iron leaning, and a tyre.
    sheet = bl.Builder('sheet')
    sheet.box(corrugated, (-0.5, -0.004, 0), (0.5, 0.004, 2.0))
    sheet.finish()
    tyre = bl.Builder('tyre')
    tyre.lathe(rubber, [(0.19, -0.1), (0.3, -0.105), (0.335, -0.07), (0.345, 0.0), (0.335, 0.07),
                        (0.3, 0.105), (0.19, 0.1), (0.185, 0.0), (0.19, -0.1)], segments=40, axis='Z')
    tyre.finish(smooth_angle=60)

    plate = bl.Builder('plate')
    plate.box(green_paint, (-0.5, -0.5, 0.0), (0.5, 0.5, 1.0))
    plate.box(rust, (0.6, -0.5, 0.0), (1.6, 0.5, 1.0))
    plate.box(dark, (1.7, -0.5, 0.0), (2.7, 0.5, 1.0))
    plate.finish(bevel=0.01)

    # A stand-in rifle: the engine's -Z is forward, which is +Y here; its origin is at the
    # trigger.
    rifle = bl.Builder('rifle_proxy')
    rifle.box(dark, (-0.022, -0.16, -0.012), (0.022, 0.22, 0.062))
    rifle.cylinder(dark, 0.011, 0.42, centre=(0, 0.42, 0.035), axis='Y', segments=14)
    rifle.cylinder(green_paint, 0.026, 0.26, centre=(0, 0.31, 0.03), axis='Y', segments=14)
    rifle.box(green_paint, (-0.02, -0.31, -0.06), (0.02, -0.16, 0.05))
    rifle.box(dark, (-0.016, -0.06, -0.11), (0.016, -0.012, -0.012))
    rifle.box(dark, (-0.013, 0.06, -0.2), (0.013, 0.125, -0.012))
    rifle.finish(bevel=0.003)

    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'test_kit.glb'))


main()
