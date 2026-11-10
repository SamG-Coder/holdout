"""The MK4 carbine: the resistance's rifle, and the player's. A gas-operated 5.56 mm carbine
with a free-floated slotted fore-end, a red-dot sight, folding iron sights, a laser unit and
an angled fore-grip; black anodised receivers with tan furniture, worn by years of use.

    blender --background --factory-startup --python art/weapons/carbine.py -- [--preview]

Modelled in metres with the muzzle towards +Y, +Z up and +X to the firer's right. The origin
is on the centre line at the trigger pin; the bore runs 35 mm above it.

Writes build/kits/carbine.glb with these parts:
  carbine_body    everything that doesn't move
  carbine_mag     the magazine, with its top round
  carbine_bolt    the bolt carrier, seen through the ejection port
  carbine_charge  the charging handle
  carbine_dot     the sight's red dot
  carbine_whole   the whole rifle as one piece, for someone else's hands
  casing_556      a spent case
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from lib import bake, bl, preview  # noqa: E402

BORE = 0.035
RAIL_TOP = 0.0655
OUT = os.path.join(bl.ROOT, 'build', 'kits')
TEX = os.path.join(bl.ROOT, 'build', 'tex', 'weapons')


def slot(name, colour):
    return bl.material(name, flat=(colour, 0.5, 0.0))


def rail(builder, mat, y0, y1, top=RAIL_TOP):
    """A length of accessory rail: a dovetailed bar with a cross slot every 10 mm."""
    base = top - 0.0094
    bar = [(-0.0078, base), (0.0078, base), (0.0078, base + 0.0030), (0.0106, base + 0.0058),
           (0.0106, top - 0.0030), (-0.0106, top - 0.0030), (-0.0106, base + 0.0058), (-0.0078, base + 0.0030)]
    builder.prism(mat, bar, y1 - y0, axis='Y', offset=y0)
    tooth = [(-0.0106, top - 0.0030), (0.0106, top - 0.0030), (0.0106, top - 0.0016), (0.0090, top),
             (-0.0090, top), (-0.0106, top - 0.0016)]
    pitch, land = 0.010, 0.0048
    count = int((y1 - y0 - land) / pitch) + 1
    start = y0 + ((y1 - y0) - ((count - 1) * pitch + land)) * 0.5
    for index in range(count):
        builder.prism(mat, tooth, land, axis='Y', offset=start + index * pitch)


def octagon(radius, flat_top=None, centre=BORE):
    """The fore-end's outline: eight sides about the bore, its top cut flat for the rail."""
    points = []
    for index in range(8):
        angle = math.radians(22.5 + 45 * index)
        points.append((radius * math.cos(angle) / math.cos(math.radians(22.5)) * 0.924,
                       centre + radius * math.sin(angle) / math.cos(math.radians(22.5)) * 0.924))
    if flat_top is not None:
        points = [(x, min(z, flat_top)) for x, z in points]
    return points


def build():
    bl.reset()
    anodized = slot('anodized', (0.03, 0.03, 0.03))
    steel = slot('steel', (0.06, 0.06, 0.06))
    bright = slot('bright', (0.5, 0.5, 0.5))
    tan = slot('tan', (0.36, 0.27, 0.16))
    black_polymer = slot('black_polymer', (0.02, 0.02, 0.02))
    rubber = slot('rubber', (0.02, 0.02, 0.02))
    brass = slot('brass', (0.8, 0.6, 0.25))
    copper = slot('copper', (0.7, 0.35, 0.2))
    # The sight's dot glows by its own material: the engine reads a material's glow as one
    # colour, not from a texture.
    dot = bl.material('carbine_dot', flat=((1.0, 0.05, 0.02), 0.4, 0.0), emissive=(1.0, 0.05, 0.02))
    lens = slot('lens', (0.05, 0.07, 0.1))
    parts = {}

    # ----- Upper receiver ---------------------------------------------------------------
    b = bl.Builder('upper')
    section = [(-0.0165, 0.0122), (0.0165, 0.0122), (0.0176, 0.030), (0.0176, 0.0455), (0.0128, 0.0561),
               (-0.0128, 0.0561), (-0.0176, 0.0455), (-0.0176, 0.030)]
    b.prism(anodized, section, 0.190, axis='Y', offset=-0.105)
    # The barrel nut's housing, and the lugs the pins pass through.
    b.cylinder(anodized, 0.0185, 0.014, centre=(0, 0.092, BORE), axis='Y', segments=32)
    b.box(anodized, (-0.0165, 0.070, 0.0005), (0.0165, 0.092, 0.0125))
    b.box(anodized, (-0.0165, -0.105, 0.004), (0.0165, -0.088, 0.0125))
    # Behind the ejection port a wedge turns spent cases away from the firer's face.
    b.prism(anodized, [(0.0176, -0.060), (0.0176, -0.038), (0.0262, -0.0405), (0.0262, -0.046)], 0.021,
            axis='Z', offset=0.0265)
    # The forward assist: its housing runs back along the right side.
    b.cylinder(anodized, 0.0078, 0.046, centre=(0.0205, -0.082, 0.0405), axis='Y', segments=20)
    b.cylinder(steel, 0.0056, 0.010, centre=(0.0205, -0.109, 0.0405), axis='Y', segments=16)
    b.cylinder(steel, 0.0070, 0.0025, centre=(0.0205, -0.1145, 0.0405), axis='Y', segments=16)
    rail(b, anodized, -0.1045, 0.0845)
    upper = b.finish(bevel=0.0005, bevel_segments=2, uv=False)
    port = bl.Builder('cut')
    port.box(anodized, (0.0035, -0.036, 0.0245), (0.03, 0.036, 0.0445))
    bl.boolean(upper, port.finish(uv=False))
    parts['upper'] = upper

    # The dust cover, hanging open under the port, on its hinge rod.
    b = bl.Builder('dust_cover')
    b.box(anodized, (0.0176, -0.037, 0.0035), (0.0192, 0.037, 0.0232))
    b.cylinder(steel, 0.0015, 0.082, centre=(0.0186, 0.0, 0.0238), axis='Y', segments=10)
    b.box(anodized, (0.0192, -0.006, 0.006), (0.0202, 0.006, 0.012))
    parts['dust_cover'] = b.finish(bevel=0.0003, uv=False)

    # ----- Bolt carrier and charging handle: the parts that move ------------------------
    b = bl.Builder('carbine_bolt')
    b.cylinder(bright, 0.0118, 0.150, centre=(0, -0.012, BORE), axis='Y', segments=28)
    # Its flats and the row of gas vents, as grooves turned in the side.
    for y in (-0.018, -0.008, 0.002):
        b.cylinder(steel, 0.0122, 0.0022, centre=(0, y, BORE), axis='Y', segments=28)
    b.box(bright, (0.0085, -0.03, BORE - 0.006), (0.0128, 0.03, BORE + 0.006))
    parts['bolt'] = b.finish(bevel=0.0003, uv=False)

    b = bl.Builder('carbine_charge')
    b.box(anodized, (-0.006, -0.112, 0.0478), (0.006, 0.06, 0.0556))
    b.box(anodized, (-0.0225, -0.1245, 0.0468), (0.0225, -0.1085, 0.0566))
    b.box(anodized, (-0.0265, -0.1215, 0.0478), (-0.0225, -0.1105, 0.0556))
    b.box(steel, (-0.0245, -0.1235, 0.0500), (-0.0115, -0.1205, 0.0540))
    parts['charge'] = b.finish(bevel=0.0005, uv=False)

    # ----- Lower receiver ---------------------------------------------------------------
    b = bl.Builder('lower')
    profile = [(-0.118, 0.0118), (0.0925, 0.0118), (0.0945, -0.002), (0.0925, -0.057), (0.0300, -0.049),
               (0.0285, -0.022), (0.0220, -0.0165), (-0.0120, -0.0165), (-0.0140, -0.0245), (-0.0460, -0.0245),
               (-0.0580, -0.0100), (-0.0850, 0.0000), (-0.1180, 0.0040)]
    b.prism(anodized, profile, 0.030, axis='X', offset=-0.015)
    # The magazine well stands a little proud, with a flared mouth.
    b.prism(anodized, [(0.0900, -0.058), (0.0320, -0.0505), (0.0320, -0.0440), (0.0900, -0.0500)], 0.034,
            axis='X', offset=-0.017)
    b.box(anodized, (-0.0158, 0.0305, -0.045), (0.0158, 0.0925, 0.004))
    # The tower the buffer tube screws into.
    b.cylinder(anodized, 0.0192, 0.020, centre=(0, -0.108, BORE), axis='Y', segments=32)
    b.box(anodized, (-0.0125, -0.118, 0.004), (0.0125, -0.098, BORE))
    # The trigger guard.
    b.prism(anodized, [(0.0285, -0.0445), (0.0285, -0.0480), (-0.0140, -0.0530), (-0.0140, -0.0495)], 0.012,
            axis='X', offset=-0.006)
    # Fences round the magazine catch, and the catch itself.
    b.box(anodized, (0.015, 0.024, -0.012), (0.0172, 0.048, 0.004))
    b.cylinder(steel, 0.0046, 0.004, centre=(0.0178, 0.036, -0.004), axis='X', segments=16)
    # The bolt catch, on the left.
    b.box(steel, (-0.0186, 0.024, 0.000), (-0.015, 0.035, 0.022))
    b.box(steel, (-0.0200, 0.0245, 0.012), (-0.0186, 0.0345, 0.0215))
    # The selector: its drum through the receiver, and the lever on the left.
    b.cylinder(steel, 0.0050, 0.036, centre=(0, -0.036, 0.0035), axis='X', segments=18)
    b.box(steel, (-0.0208, -0.058, 0.0010), (-0.0180, -0.034, 0.0060))
    # Pins, standing a hair proud on both sides.
    for y, z, radius in ((0.0855, 0.0052, 0.0034), (-0.0975, 0.0085, 0.0034), (0.0020, -0.0010, 0.0021),
                         (-0.0200, 0.0040, 0.0021)):
        b.cylinder(steel, radius, 0.0312, centre=(0, y, z), axis='X', segments=14)
    parts['lower'] = b.finish(bevel=0.0006, bevel_segments=2, uv=False)

    b = bl.Builder('trigger')
    b.prism(steel, [(0.0040, -0.0160), (0.0105, -0.0160), (0.0095, -0.0280), (0.0060, -0.0395), (0.0020, -0.0420),
                    (0.0010, -0.0400), (0.0040, -0.0300)], 0.0064, axis='X', offset=-0.0032)
    parts['trigger'] = b.finish(bevel=0.0008, bevel_segments=3, uv=False)

    # ----- Buffer tube and stock --------------------------------------------------------
    b = bl.Builder('buffer_tube')
    b.cylinder(anodized, 0.0146, 0.190, centre=(0, -0.213, BORE), axis='Y', segments=32)
    b.box(anodized, (-0.0048, -0.305, BORE - 0.0205), (0.0048, -0.125, BORE - 0.012))
    # The castle nut, notched, and the end plate behind it.
    b.cylinder(steel, 0.0182, 0.0085, centre=(0, -0.1235, BORE), axis='Y', segments=24)
    b.box(steel, (-0.0150, -0.1195, BORE - 0.027), (0.0150, -0.1175, BORE + 0.019))
    tube = b.finish(bevel=0.0004, uv=False)
    notches = bl.Builder('cut')
    for index in range(6):
        turn = Matrix.Translation((0, 0, BORE)) @ Matrix.Rotation(math.radians(60 * index), 4, 'Y') \
            @ Matrix.Translation((0, 0, -BORE))
        notches.box(steel, (-0.002, -0.129, BORE + 0.0155), (0.002, -0.1235, BORE + 0.02), matrix=turn)
    bl.boolean(tube, notches.finish(uv=False))
    parts['buffer_tube'] = tube

    b = bl.Builder('stock')
    profile = [(-0.136, 0.0580), (-0.298, 0.0580), (-0.3105, 0.0500), (-0.3125, -0.0460), (-0.3010, -0.0560),
               (-0.2180, -0.0115), (-0.1360, 0.0090)]
    b.prism(tan, profile, 0.041, axis='X', offset=-0.0205)
    stock = b.finish(uv=False)
    # Lightening cut through its web, and the bore for the tube.
    cut = bl.Builder('cut')
    cut.prism(tan, [(-0.236, -0.0090), (-0.292, -0.0380), (-0.292, 0.0060), (-0.236, 0.0060)], 0.06, axis='X', offset=-0.03)
    cut.cylinder(tan, 0.0152, 0.20, centre=(0, -0.20, BORE), axis='Y', segments=28)
    bl.boolean(stock, cut.finish(uv=False))
    bl.add_bevel(stock, 0.0032, 3)
    bl.shade(stock, 40)
    parts['stock'] = stock
    b = bl.Builder('stock_fittings')
    # The latch under the stock, and the rubber butt pad with its grooves.
    b.box(tan, (-0.010, -0.206, -0.0165), (0.010, -0.150, -0.004))
    b.box(steel, (-0.0035, -0.196, -0.0195), (0.0035, -0.158, -0.0160))
    b.box(rubber, (-0.0195, -0.3225, -0.0500), (0.0195, -0.3110, 0.0535))
    for index in range(7):
        z = -0.040 + index * 0.0135
        b.box(rubber, (-0.0200, -0.3240, z), (0.0200, -0.3220, z + 0.0075))
    parts['stock_fittings'] = b.finish(bevel=0.0012, bevel_segments=2, uv=False)

    # ----- Pistol grip ------------------------------------------------------------------
    b = bl.Builder('grip')
    profile = [(-0.0125, -0.0245), (-0.0200, -0.0560), (-0.0330, -0.1150), (-0.0420, -0.1190), (-0.0720, -0.1130),
               (-0.0745, -0.1060), (-0.0560, -0.0500), (-0.0580, -0.0230), (-0.0640, -0.0105), (-0.0470, -0.0245)]
    b.prism(tan, profile, 0.0285, axis='X', offset=-0.01425)
    grip = b.finish(bevel=0.0058, bevel_segments=4, smooth_angle=50, uv=False)
    parts['grip'] = grip
    b = bl.Builder('grip_screw')
    b.cylinder(steel, 0.0042, 0.003, centre=(0, -0.057, -0.1165), axis='Z', segments=14)
    parts['grip_screw'] = b.finish(bevel=0.0003, uv=False)

    # ----- Fore-end, barrel and what hangs from them -------------------------------------
    b = bl.Builder('handguard')
    b.prism(anodized, octagon(0.0218, flat_top=RAIL_TOP - 0.0094), 0.308, axis='Y', offset=0.097)
    b.cylinder(anodized, 0.0212, 0.012, centre=(0, 0.098, BORE), axis='Y', segments=32)
    handguard = b.finish(uv=False)
    cut = bl.Builder('cut')
    cut.cylinder(anodized, 0.0183, 0.34, centre=(0, 0.26, BORE), axis='Y', segments=28)
    # Slots: seven rows round the tube, each slot 32 mm long, to bolt accessories into and to
    # let the barrel cool.
    for row, angle in enumerate((0, 45, 90, 135, 180, 225, 315)):
        if angle == 270:
            continue
        turn = Matrix.Translation((0, 0, BORE)) @ Matrix.Rotation(math.radians(angle - 90), 4, 'Y') \
            @ Matrix.Translation((0, 0, -BORE))
        stagger = 0.0 if row % 2 == 0 else 0.02
        for index in range(7):
            y = 0.122 + stagger + index * 0.040
            if y + 0.032 > 0.395:
                continue
            cut.box(anodized, (-0.0035, y, BORE - 0.026), (0.0035, y + 0.032, BORE - 0.014), matrix=turn)
            cut.cylinder(anodized, 0.0035, 0.012, centre=(0, y, BORE - 0.020), axis='Z', segments=12, matrix=turn)
            cut.cylinder(anodized, 0.0035, 0.012, centre=(0, y + 0.032, BORE - 0.020), axis='Z', segments=12, matrix=turn)
    bl.boolean(handguard, cut.finish(uv=False))
    bl.add_bevel(handguard, 0.0005, 2)
    bl.shade(handguard, 30)
    parts['handguard'] = handguard
    b = bl.Builder('handguard_rail')
    rail(b, anodized, 0.0975, 0.4045)
    # The screws that clamp it to the barrel nut.
    for y in (0.104, 0.116):
        for x in (-1, 1):
            b.cylinder(steel, 0.0030, 0.003, centre=(x * 0.0205, y, BORE - 0.011), axis='X', segments=12)
    parts['handguard_rail'] = b.finish(bevel=0.0004, uv=False)

    b = bl.Builder('barrel')
    b.lathe(steel, [(0.0, 0.080), (0.0128, 0.080), (0.0128, 0.104), (0.0100, 0.108), (0.0100, 0.262),
                    (0.0094, 0.264), (0.0094, 0.300), (0.0092, 0.302), (0.0092, 0.440), (0.0082, 0.4415),
                    (0.0082, 0.4565)], segments=28, axis='Y', centre=(0, 0, BORE))
    # The gas block and the tube that carries gas back to the bolt.
    b.cylinder(steel, 0.0128, 0.030, centre=(0, 0.279, BORE), axis='Y', segments=24)
    b.box(steel, (-0.0062, 0.264, BORE + 0.008), (0.0062, 0.294, BORE + 0.0185))
    b.cylinder(steel, 0.0024, 0.176, centre=(0, 0.180, BORE + 0.0150), axis='Y', segments=10)
    for y in (0.270, 0.288):
        b.cylinder(bright, 0.0020, 0.003, centre=(0, y, BORE - 0.0128), axis='Z', segments=10)
    parts['barrel'] = b.finish(bevel=0.0004, uv=False)

    b = bl.Builder('flash_hider')
    b.lathe(steel, [(0.0050, 0.4555), (0.0090, 0.4555), (0.0112, 0.4585), (0.0112, 0.4965), (0.0103, 0.5005),
                    (0.0058, 0.5005), (0.0058, 0.4660), (0.0050, 0.4640), (0.0050, 0.4555)], segments=30,
            axis='Y', centre=(0, 0, BORE))
    b.cylinder(steel, 0.0118, 0.004, centre=(0, 0.4580, BORE), axis='Y', segments=6)
    hider = b.finish(uv=False)
    cut = bl.Builder('cut')
    # Five slots, the bottom left closed so that the blast doesn't kick up dust.
    for index in range(5):
        turn = Matrix.Translation((0, 0, BORE)) @ Matrix.Rotation(math.radians(-72 + 36 * index + 36), 4, 'Y') \
            @ Matrix.Translation((0, 0, -BORE))
        cut.box(steel, (-0.0014, 0.4700, BORE), (0.0014, 0.4940, BORE + 0.02), matrix=turn)
    bl.boolean(hider, cut.finish(uv=False))
    bl.add_bevel(hider, 0.0003, 2)
    bl.shade(hider, 40)
    parts['flash_hider'] = hider

    # An angled fore-grip under the fore-end.
    b = bl.Builder('foregrip')
    profile = [(0.300, 0.0138), (0.180, 0.0138), (0.172, 0.0060), (0.188, -0.0140), (0.224, -0.0245),
               (0.262, -0.0170), (0.296, 0.0020)]
    b.prism(tan, profile, 0.030, axis='X', offset=-0.015)
    parts['foregrip'] = b.finish(bevel=0.0045, bevel_segments=4, smooth_angle=50, uv=False)

    # The laser unit on the rail ahead of the sight: a tan box with two emitters and its knobs.
    b = bl.Builder('laser')
    b.box(tan, (-0.0190, 0.300, RAIL_TOP - 0.002), (0.0190, 0.372, RAIL_TOP + 0.0150))
    b.box(black_polymer, (-0.0125, 0.304, RAIL_TOP - 0.0085), (0.0125, 0.368, RAIL_TOP - 0.002))
    for x in (-0.0090, 0.0095):
        b.cylinder(black_polymer, 0.0062, 0.006, centre=(x, 0.3745, RAIL_TOP + 0.0070), axis='Y', segments=18)
        b.cylinder(lens, 0.0048, 0.0015, centre=(x, 0.3780, RAIL_TOP + 0.0070), axis='Y', segments=18)
    b.cylinder(black_polymer, 0.0058, 0.004, centre=(0.0, 0.336, RAIL_TOP + 0.0165), axis='Z', segments=18)
    b.cylinder(black_polymer, 0.0048, 0.006, centre=(0.0215, 0.318, RAIL_TOP + 0.0065), axis='X', segments=16)
    b.box(black_polymer, (-0.0100, 0.3030, RAIL_TOP + 0.0150), (0.0100, 0.3200, RAIL_TOP + 0.0170))
    parts['laser'] = b.finish(bevel=0.0012, bevel_segments=2, uv=False)

    # ----- Sights -----------------------------------------------------------------------
    # The red-dot sight: an open tube on a riser. There is no glass in it, so that it can be
    # looked through.
    sight_z = RAIL_TOP + 0.0360
    b = bl.Builder('sight')
    b.lathe(anodized, [(0.0130, -0.0340), (0.0172, -0.0340), (0.0172, -0.0270), (0.0160, -0.0250), (0.0160, 0.0210),
                       (0.0176, 0.0230), (0.0176, 0.0300), (0.0130, 0.0300), (0.0130, -0.0340)], segments=36,
            axis='Y', centre=(0, 0, sight_z))
    # Turrets: elevation on top, windage on the right, the brightness dial on the left.
    b.cylinder(anodized, 0.0078, 0.0085, centre=(0, 0.006, sight_z + 0.0195), axis='Z', segments=22)
    b.cylinder(steel, 0.0050, 0.002, centre=(0, 0.006, sight_z + 0.0245), axis='Z', segments=16)
    b.cylinder(anodized, 0.0078, 0.0085, centre=(0.0195, 0.006, sight_z), axis='X', segments=22)
    b.cylinder(steel, 0.0050, 0.002, centre=(0.0245, 0.006, sight_z), axis='X', segments=16)
    b.cylinder(anodized, 0.0115, 0.010, centre=(-0.0205, -0.006, sight_z), axis='X', segments=26)
    # The mount: a clamp on the rail and a web up to the tube.
    b.box(anodized, (-0.0135, -0.0260, RAIL_TOP - 0.0080), (0.0135, 0.0220, RAIL_TOP + 0.0030))
    b.box(anodized, (-0.0080, -0.0220, RAIL_TOP + 0.0030), (0.0080, 0.0180, sight_z - 0.0150))
    b.box(steel, (0.0135, -0.0120, RAIL_TOP - 0.0070), (0.0185, 0.0080, RAIL_TOP + 0.0010))
    b.cylinder(steel, 0.0045, 0.006, centre=(0.0200, -0.002, RAIL_TOP - 0.0030), axis='X', segments=6)
    parts['sight'] = b.finish(bevel=0.0005, bevel_segments=2, uv=False)

    b = bl.Builder('carbine_dot')
    b.sphere(dot, 0.00042, centre=(0, 0.0, sight_z), segments=10, rings=6)
    parts['dot'] = b.finish(uv=False)

    # Folding iron sights, folded down.
    b = bl.Builder('rear_sight')
    b.box(steel, (-0.0125, -0.1000, RAIL_TOP - 0.0080), (0.0125, -0.0660, RAIL_TOP + 0.0020))
    b.box(steel, (-0.0080, -0.0990, RAIL_TOP + 0.0020), (0.0080, -0.0520, RAIL_TOP + 0.0085))
    b.cylinder(steel, 0.0040, 0.030, centre=(0, -0.0960, RAIL_TOP + 0.0050), axis='X', segments=14)
    b.cylinder(bright, 0.0030, 0.004, centre=(0.0140, -0.0830, RAIL_TOP - 0.0030), axis='X', segments=12)
    parts['rear_sight'] = b.finish(bevel=0.0006, uv=False)
    b = bl.Builder('front_sight')
    b.box(steel, (-0.0125, 0.3780, RAIL_TOP - 0.0080), (0.0125, 0.4030, RAIL_TOP + 0.0020))
    b.box(steel, (-0.0075, 0.3330, RAIL_TOP + 0.0020), (0.0075, 0.4020, RAIL_TOP + 0.0080))
    b.cylinder(steel, 0.0040, 0.030, centre=(0, 0.3990, RAIL_TOP + 0.0050), axis='X', segments=14)
    parts['front_sight'] = b.finish(bevel=0.0006, uv=False)

    # ----- Magazine ---------------------------------------------------------------------
    b = bl.Builder('carbine_mag')
    profile = [(0.0880, 0.0020), (0.0900, -0.0600), (0.0990, -0.1200), (0.1140, -0.1800), (0.1165, -0.1900),
               (0.0530, -0.2030), (0.0495, -0.1940), (0.0385, -0.1200), (0.0325, -0.0600), (0.0325, 0.0020)]
    b.prism(tan, profile, 0.0222, axis='X', offset=-0.0111)
    # The floor plate, a little wider, and ribs down the sides for the hand.
    b.prism(tan, [(0.1185, -0.1905), (0.0505, -0.2045), (0.0495, -0.2105), (0.1195, -0.1965)], 0.0262,
            axis='X', offset=-0.0131)
    for index in range(5):
        t = index / 4.0
        z = -0.075 - t * 0.095
        shift = 0.003 + t * 0.021
        b.prism(tan, [(0.0370 + shift, z), (0.0890 + shift, z + 0.0040), (0.0890 + shift, z + 0.0075),
                      (0.0370 + shift, z + 0.0035)], 0.0238, axis='X', offset=-0.0119)
    # Steel feed lips, and the top round waiting under them.
    b.box(steel, (-0.0102, 0.0340, 0.0010), (-0.0062, 0.0860, 0.0060))
    b.box(steel, (0.0062, 0.0340, 0.0010), (0.0102, 0.0860, 0.0060))
    b.lathe(brass, [(0.0, 0.0360), (0.0046, 0.0362), (0.0048, 0.0380), (0.0048, 0.0660), (0.0032, 0.0700),
                    (0.0032, 0.0760)], segments=16, axis='Y', centre=(0.0, 0, 0.0030))
    b.lathe(copper, [(0.0030, 0.0760), (0.0028, 0.0830), (0.0016, 0.0900), (0.0, 0.0930)], segments=16, axis='Y',
            centre=(0.0, 0, 0.0030))
    parts['mag'] = b.finish(bevel=0.0007, bevel_segments=2, uv=False)

    # ----- A spent case -----------------------------------------------------------------
    b = bl.Builder('casing_556')
    b.lathe(brass, [(0.0, -0.0225), (0.0040, -0.0225), (0.0048, -0.0215), (0.0040, -0.0205), (0.0048, -0.0195),
                    (0.0048, 0.0090), (0.0032, 0.0135), (0.0032, 0.0225), (0.0027, 0.0225), (0.0027, 0.0100),
                    (0.0, 0.0090)], segments=18, axis='Y')
    parts['casing'] = b.finish(bevel=0.0, uv=False)
    return parts


def paint(parts):
    """Unwraps the parts into three atlases and paints each with its materials."""
    recipes = {
        'anodized': (bake.anodized, dict(wear=0.42, grime=0.45)),
        'steel': (bake.steel, dict(wear=0.5, grime=0.45, rust=0.12)),
        'bright': (bake.bright_steel, dict()),
        'tan': (bake.polymer, dict(colour=(0.30, 0.225, 0.135), wear=0.5, grime=0.55)),
        'black_polymer': (bake.polymer, dict(colour=(0.022, 0.022, 0.024), wear=0.45, grime=0.4)),
        'rubber': (bake.rubber, dict()),
        'brass': (bake.brass, dict(tarnish=0.35)),
        'copper': (bake.copper, dict()),
        'lens': (bake.glass_dark, dict()),
    }
    groups = {
        'carbine_a': ['upper', 'dust_cover', 'charge', 'lower', 'trigger', 'buffer_tube'],
        'carbine_b': ['handguard', 'handguard_rail', 'barrel', 'flash_hider', 'foregrip', 'laser', 'front_sight'],
        'carbine_c': ['stock', 'stock_fittings', 'grip', 'grip_screw', 'sight', 'rear_sight', 'mag', 'bolt',
                      'casing'],
    }
    for seed, (name, members) in enumerate(groups.items()):
        atlas = bake.Atlas(name, [parts[m] for m in members], size=1024, seed=17 + seed * 31,
                           edge_radius=0.0036, ao_distance=0.03)
        for slot_name, (function, options) in recipes.items():
            atlas.recipe(slot_name, function, **options)
        atlas.bake(TEX)


def assemble(parts):
    """Joins what never moves into the body, and makes a one-piece copy of the whole rifle."""
    moving = {'mag': 'carbine_mag', 'bolt': 'carbine_bolt', 'charge': 'carbine_charge', 'dot': 'carbine_dot',
              'casing': 'casing_556'}
    for key, name in moving.items():
        parts[key].name = name
        parts[key].data.name = name
    whole_parts = [bl.duplicate(parts[key], f'_whole_{key}') for key in parts if key != 'casing']
    whole = bl.join(whole_parts, 'carbine_whole')
    body = bl.join([parts[key] for key in parts if key not in moving], 'carbine_body')
    return [body, whole] + [parts[key] for key in moving]


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parts = build()
    if '--shape' in args:
        # The bare model, to check its shape before spending time painting it.
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'carbine_shape.png'), list(parts.values()),
                       views=[(90, 8), (-55, 22)], size=(1600, 800), samples=32, zoom=1.9)
        return
    paint(parts)
    objects = assemble(parts)
    if '--preview' in args:
        body = [o for o in objects if o.name != 'carbine_whole' and o.name != 'casing_556']
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'carbine.png'), body,
                       views=[(90, 8), (-55, 22), (125, 25)], size=(1600, 800), samples=64, zoom=1.9)
    bl.export_glb(os.path.join(OUT, 'carbine.glb'), objects)


main()
