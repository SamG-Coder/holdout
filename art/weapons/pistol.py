"""The P9 pistol: the sidearm every Directorate officer carried, and a good many of the
resistance carry now. A striker-fired 9 mm with a steel slide on a polymer frame.

    blender --background --factory-startup --python art/weapons/pistol.py -- [--shape] [--preview]

Writes build/kits/pistol.glb with the parts:

  pistol_body     the frame, grip, trigger and controls
  pistol_slide    the slide with its sights and the barrel: it runs back as the pistol fires
  pistol_mag      the magazine
  pistol_whole    all of it in one piece

The pistol points along +Y with its top toward +Z; the origin is at the trigger, and the bore
is 30 mm above it.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from mathutils import Matrix  # noqa: E402

from lib import bake, bl, preview  # noqa: E402

BORE = 0.030
TOP = 0.0462
OUT = os.path.join(bl.ROOT, 'build', 'kits')
TEX = os.path.join(bl.ROOT, 'build', 'tex', 'weapons')
# How the grip leans: the magazine goes in and out along this line.
RAKE = math.radians(15.9)


def slot(name, colour):
    return bl.material(name, flat=(colour, 0.5, 0.0))


def build():
    bl.reset()
    steel = slot('steel', (0.06, 0.06, 0.06))
    bright = slot('bright', (0.5, 0.5, 0.5))
    polymer = slot('black_polymer', (0.02, 0.02, 0.02))
    white = slot('sight_white', (0.8, 0.8, 0.78))
    brass = slot('brass', (0.8, 0.6, 0.25))
    parts = {}

    # ----- The slide --------------------------------------------------------------------
    b = bl.Builder('slide')
    half = 0.0129
    section = [(-half, 0.0145), (half, 0.0145), (half, 0.0405), (half - 0.0032, TOP), (-half + 0.0032, TOP),
               (-half, 0.0405)]
    b.prism(steel, section, 0.186, axis='Y', offset=-0.103)
    # The nose is cut back under the muzzle.
    b.prism(steel, [(0.083, 0.0145), (0.088, 0.0200), (0.088, 0.0405), (0.083, 0.0405)], 2 * half, axis='X', offset=-half)
    # Grasping grooves at the back, standing a little proud of the flat.
    for i in range(8):
        y = -0.097 + i * 0.0042
        for side in (-1, 1):
            x0, x1 = sorted((side * half, side * (half + 0.0005)))
            b.prism(steel, [(y, 0.0165), (y + 0.0022, 0.0165), (y + 0.0034, 0.0395), (y + 0.0012, 0.0395)], x1 - x0,
                    axis='X', offset=x0)
    # The ejection port, and the hood of the barrel that shows through it.
    b.box(bright, (0.0015, -0.040, 0.0370), (half + 0.0002, -0.008, TOP + 0.0002))
    b.box(steel, (0.0015, -0.0415, 0.0365), (half + 0.0003, -0.040, TOP + 0.0003))
    # The extractor.
    b.box(steel, (half, -0.058, 0.0330), (half + 0.0006, -0.040, 0.0360))
    # Sights: a notch behind, a blade in front, each with its white marks.
    for x in (-0.0062, 0.0062):
        b.box(steel, (x - 0.0030, -0.0990, TOP), (x + 0.0030, -0.0890, TOP + 0.0052))
        b.box(white, (x - 0.0010, -0.0992, TOP + 0.0022), (x + 0.0010, -0.0990, TOP + 0.0040))
    b.box(steel, (-0.0092, -0.0990, TOP), (0.0092, -0.0890, TOP + 0.0018))
    b.prism(steel, [(0.066, TOP), (0.078, TOP), (0.076, TOP + 0.0050), (0.068, TOP + 0.0050)], 0.0036, axis='X',
            offset=-0.0018)
    b.box(white, (-0.0010, 0.0668, TOP + 0.0022), (0.0010, 0.0672, TOP + 0.0042), matrix=None)
    # The back plate, and the striker's indicator in it.
    b.box(polymer, (-0.0085, -0.1036, 0.0190), (0.0085, -0.1030, 0.0400))
    b.cylinder(bright, 0.0016, 0.0008, centre=(0, -0.1038, 0.0300), axis='Y', segments=10)
    # The barrel: its muzzle stands just proud of the slide, with the guide rod's end below.
    b.lathe(steel, [(0.0045, 0.0), (0.0068, 0.0), (0.0068, 0.004), (0.0045, 0.004), (0.0045, 0.0)], segments=24, axis='Y',
            centre=(0, 0.0858, BORE))
    b.cylinder(polymer, 0.0046, 0.001, centre=(0, 0.0866, BORE), axis='Y', segments=16)
    b.cylinder(steel, 0.0036, 0.004, centre=(0, 0.0868, 0.0188), axis='Y', segments=14)
    parts['slide'] = b.finish(bevel=0.0007, bevel_segments=2, uv=False)

    # ----- The frame --------------------------------------------------------------------
    b = bl.Builder('frame')
    fw = 0.0135
    # The dust cover under the slide, with a rail for a lamp.
    b.prism(polymer, [(-0.104, 0.0145), (0.082, 0.0145), (0.082, 0.0040), (0.078, 0.0020), (-0.104, 0.0020)], 2 * fw,
            axis='X', offset=-fw)
    b.box(polymer, (-fw, 0.046, -0.0010), (fw, 0.076, 0.0022))
    for y in (0.052, 0.060, 0.068):
        b.box(polymer, (-fw - 0.0004, y, -0.0012), (fw + 0.0004, y + 0.004, 0.0026))
    # The grip, raked back, swelling a little to fill the hand.
    # Its foot is square to the rake, as the magazine's is. Two pieces, each convex.
    grip = [(-0.041, 0.004), (-0.041, -0.010), (-0.066, -0.098), (-0.116, -0.084), (-0.111, -0.036), (-0.103, 0.004)]
    b.prism(polymer, grip, 0.0290, axis='X', offset=-0.0145)
    tang = [(-0.041, 0.002), (-0.041, 0.0145), (-0.112, 0.0145), (-0.119, 0.0080), (-0.104, -0.0040)]
    b.prism(polymer, tang, 0.0290, axis='X', offset=-0.0145)
    # Panels of stippling on both sides and the back strap.
    for side in (-1, 1):
        x0, x1 = sorted((side * 0.0145, side * 0.0152))
        b.prism(polymer, [(-0.052, -0.020), (-0.070, -0.088), (-0.108, -0.078), (-0.100, -0.020)], x1 - x0, axis='X',
                offset=x0)
    # The trigger guard, squared at the front.
    b.tube(polymer, [(0, 0.046, 0.0000), (0, 0.047, -0.0300), (0, 0.040, -0.0370), (0, -0.032, -0.0380),
                     (0, -0.049, -0.0270)], 0.0045, segments=8)
    # The trigger, with its safety blade.
    lean = Matrix.Translation((0, 0.004, 0.0)) @ Matrix.Rotation(math.radians(-14), 4, 'X')
    b.prism(polymer, [(-0.0035, 0.002), (0.0030, 0.002), (0.0052, -0.014), (0.0030, -0.026), (-0.0010, -0.026),
                      (0.0006, -0.014)], 0.0074, axis='X', offset=-0.0037, matrix=lean)
    b.box(steel, (-0.0012, 0.0010, -0.0250), (0.0012, 0.0052, -0.0060), matrix=lean)
    # Controls on the left side: the slide stop, the take-down catch, the magazine release.
    b.box(steel, (-fw - 0.0018, -0.062, 0.0085), (-fw, -0.030, 0.0125))
    b.box(steel, (-fw - 0.0026, -0.066, 0.0080), (-fw, -0.058, 0.0140))
    b.box(steel, (-fw - 0.0010, 0.006, 0.0040), (-fw, 0.018, 0.0085))
    b.box(steel, (fw, 0.006, 0.0040), (fw + 0.0010, 0.018, 0.0085))
    b.cylinder(steel, 0.0044, 0.0325, centre=(0, -0.0485, -0.0130), axis='X', segments=14)
    # The pins.
    for y, z in ((-0.006, 0.0085), (-0.092, 0.0060), (-0.084, -0.022)):
        b.cylinder(steel, 0.0016, 2 * fw + 0.0012, centre=(0, y, z), axis='X', segments=10)
    parts['frame'] = b.finish(bevel=0.0009, bevel_segments=2, uv=False)

    # ----- The magazine -----------------------------------------------------------------
    b = bl.Builder('mag')
    # A steel tube up inside the grip, a polymer foot under it, and the top round showing.
    place = Matrix.Translation((0, -0.0905, -0.0915)) @ Matrix.Rotation(-RAKE, 4, 'X')
    b.box(steel, (-0.0105, -0.0190, 0.0), (0.0105, 0.0160, 0.104), matrix=place)
    b.box(polymer, (-0.0142, -0.0290, -0.0085), (0.0142, 0.0250, 0.0005), matrix=place)
    b.box(polymer, (-0.0142, 0.0180, -0.0085), (0.0142, 0.0300, -0.0030), matrix=place)
    b.cylinder(brass, 0.0048, 0.019, centre=(0, 0.004, 0.1055), axis='Y', segments=14, matrix=place)
    parts['mag'] = b.finish(bevel=0.0007, bevel_segments=2, uv=False)
    return parts


def paint(parts):
    recipes = {
        'steel': (bake.steel, dict(wear=0.55, grime=0.4, rust=0.06)),
        'bright': (bake.bright_steel, dict()),
        'black_polymer': (bake.polymer, dict(colour=(0.022, 0.022, 0.024), wear=0.4, grime=0.4)),
        'sight_white': (bake.polymer, dict(colour=(0.7, 0.7, 0.66), wear=0.2, grime=0.3)),
        'brass': (bake.brass, dict(tarnish=0.3)),
    }
    atlas = bake.Atlas('pistol_a', list(parts.values()), size=1024, seed=53, edge_radius=0.0030, ao_distance=0.02)
    for slot_name, (function, options) in recipes.items():
        atlas.recipe(slot_name, function, **options)
    atlas.bake(TEX)


def assemble(parts):
    names = {'frame': 'pistol_body', 'slide': 'pistol_slide', 'mag': 'pistol_mag'}
    for key, name in names.items():
        parts[key].name = name
        parts[key].data.name = name
    whole = bl.join([bl.duplicate(parts[key], f'_whole_{key}') for key in parts], 'pistol_whole')
    return [parts['frame'], parts['slide'], parts['mag'], whole]


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parts = build()
    if '--shape' in args:
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'pistol_shape.png'), list(parts.values()),
                       views=[(90, 6), (-60, 20)], size=(1400, 900), samples=32, zoom=1.7)
        return
    paint(parts)
    objects = assemble(parts)
    if '--preview' in args:
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'pistol.png'), objects[:3],
                       views=[(90, 6), (-60, 20)], size=(1400, 900), samples=48, zoom=1.7)
    bl.export_glb(os.path.join(OUT, 'pistol.glb'), objects)


main()
