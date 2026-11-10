"""The things that fill Alder Ridge: fences, the Directorate's fortifications, street
furniture, what was left in the yards, the safehouse's kit, and the signs of both sides.

    blender --background --factory-startup --python art/world/props.py -- [--preview NAME,NAME]

Writes build/kits/props.glb. Each prop is one part, standing on the ground at its own origin.
Things with a front face +Y (which the engine sees as -Z).
"""

import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from mathutils import Matrix, Vector  # noqa: E402

import bpy  # noqa: E402
from lib import bl, preview  # noqa: E402

M = {}


def materials():
    tile = lambda name, texture, **kw: bl.material(name, texture, **kw)  # noqa: E731
    M.update(
        concrete=tile('concrete', 'concrete'),
        wood=tile('fence_wood', 'fence_wood'),
        plywood=tile('plywood', 'plywood'),
        white=tile('trim_white', 'painted_wood'),
        steel=tile('bare_metal', 'bare_metal'),
        dark=tile('dark_steel', 'dark_steel'),
        rust=tile('rusty_metal', 'rusty_metal'),
        chain=tile('chainlink', 'chainlink', mask=True, two_sided=True),
        burlap=tile('burlap', 'burlap'),
        corrugated=tile('corrugated', 'corrugated'),
        rubber=tile('rubber', 'rubber'),
        glass=tile('glass', 'glass'),
        olive=tile('paint_olive', 'painted_metal', tint=(0.13, 0.15, 0.09)),
        grey=tile('paint_grey', 'painted_metal', tint=(0.3, 0.31, 0.32)),
        slate=tile('paint_slate', 'painted_metal', tint=(0.12, 0.13, 0.15)),
        red=tile('paint_red', 'painted_metal', tint=(0.5, 0.05, 0.04)),
        yellow=tile('paint_yellow', 'painted_metal', tint=(0.75, 0.55, 0.06)),
        blue=tile('paint_blue', 'painted_metal', tint=(0.08, 0.2, 0.42)),
        green=tile('paint_green', 'painted_metal', tint=(0.1, 0.3, 0.16)),
        cream=tile('paint_cream', 'painted_metal', tint=(0.8, 0.78, 0.7)),
        black=tile('plastic_black', 'plastic', tint=(0.03, 0.03, 0.03)),
        bin=tile('plastic_bin', 'plastic', tint=(0.07, 0.16, 0.1)),
        orange=tile('plastic_orange', 'plastic', tint=(0.85, 0.22, 0.03)),
        tarp=tile('canvas_olive', 'canvas', tint=(0.2, 0.23, 0.14)),
        tarp_blue=tile('canvas_blue', 'canvas', tint=(0.1, 0.22, 0.5)),
        sandcloth=tile('canvas_sand', 'canvas', tint=(0.46, 0.4, 0.29)),
        dirt=tile('dirt', 'dirt'),
        banner=tile('canvas_red', 'canvas', tint=(0.5, 0.03, 0.025)),
        cloth=tile('fabric_grey', 'fabric', tint=(0.4, 0.4, 0.38)),
        paper=tile('paper', 'plaster', tint=(0.86, 0.82, 0.7)),
        ink=bl.material('ink', flat=((0.02, 0.02, 0.02), 0.8, 0.0)),
        paint_white=bl.material('paint_white', flat=((0.85, 0.85, 0.82), 0.6, 0.0)),
        paint_red=bl.material('paint_flat_red', flat=((0.55, 0.04, 0.03), 0.6, 0.0)),
        lamp=bl.material('lamp_white', flat=((1.0, 0.96, 0.86), 0.3, 0.0), emissive=(1.0, 0.93, 0.78)),
        lamp_warm=bl.material('lamp_warm', flat=((1.0, 0.7, 0.35), 0.3, 0.0), emissive=(1.0, 0.62, 0.25)),
        lamp_red=bl.material('lamp_red', flat=((1.0, 0.1, 0.05), 0.3, 0.0), emissive=(1.0, 0.08, 0.04)),
    )


def rz(degrees, at=(0, 0, 0)):
    return Matrix.Translation(Vector(at)) @ Matrix.Rotation(math.radians(degrees), 4, 'Z')


# ---------------------------------------------------------------------------------- Fences

def fence_wood(name='fence_wood', length=2.4, broken=False):
    """A length of board fence, 1.8 m tall, between two posts."""
    b = bl.Builder(name)
    rng = random.Random(len(name) * 7 + int(broken))
    for x in (-length / 2, length / 2):
        b.box(M['wood'], (x - 0.05, -0.05, -0.3), (x + 0.05, 0.05, 1.85))
    for z in (0.35, 1.45):
        b.box(M['wood'], (-length / 2, 0.02, z - 0.045), (length / 2, 0.06, z + 0.045))
    boards = int(length / 0.15)
    for i in range(boards):
        x = -length / 2 + (i + 0.5) * length / boards
        if broken and rng.random() < 0.3:
            continue
        top = 1.8 + rng.uniform(-0.015, 0.015)
        lean = rng.uniform(-1.5, 1.5) if broken else rng.uniform(-0.3, 0.3)
        turn = Matrix.Translation((x, 0, 0.05)) @ Matrix.Rotation(math.radians(lean), 4, 'Y')
        b.prism(M['wood'], [(-0.07, 0), (0.07, 0), (0.07, top - 0.1), (0.0, top - 0.05), (-0.07, top - 0.1)], 0.02,
                axis='Y', offset=-0.02, matrix=turn)
    return b.finish(bevel=0.003, bevel_segments=1)


def fence_gate():
    """A board gate, standing open."""
    b = bl.Builder('fence_gate')
    b.box(M['wood'], (-0.55, -0.05, -0.3), (-0.45, 0.05, 1.85))
    b.box(M['wood'], (0.45, -0.05, -0.3), (0.55, 0.05, 1.85))
    swing = rz(-70, (-0.45, 0, 0))
    b.box(M['wood'], (0.0, -0.02, 0.1), (0.88, 0.0, 1.75), matrix=swing)
    for z in (0.3, 1.5):
        b.box(M['wood'], (0.0, 0.0, z - 0.04), (0.88, 0.035, z + 0.04), matrix=swing)
    b.box(M['dark'], (0.78, -0.03, 0.95), (0.86, -0.02, 1.0), matrix=swing)
    return b.finish(bevel=0.003, bevel_segments=1)


def fence_picket(length=2.4):
    b = bl.Builder('fence_picket')
    for x in (-length / 2, length / 2):
        b.box(M['white'], (x - 0.045, -0.045, -0.2), (x + 0.045, 0.045, 1.05))
    for z in (0.25, 0.75):
        b.box(M['white'], (-length / 2, 0.015, z - 0.035), (length / 2, 0.05, z + 0.035))
    count = int(length / 0.14)
    for i in range(count):
        x = -length / 2 + (i + 0.5) * length / count
        b.prism(M['white'], [(x - 0.04, 0.08), (x + 0.04, 0.08), (x + 0.04, 0.9), (x, 0.98), (x - 0.04, 0.9)], 0.018,
                axis='Y', offset=-0.018)
    return b.finish(bevel=0.003, bevel_segments=1)


def fence_chain(length=3.0, wire=True):
    """Chain-link on steel posts, 2.4 m tall, topped with barbed wire on outriggers."""
    b = bl.Builder('fence_chain' if wire else 'fence_chain_plain')
    b.quad(M['chain'], (-length / 2, 0, 0.05), (length / 2, 0, 0.05), (length / 2, 0, 2.35), (-length / 2, 0, 2.35))
    for x in (-length / 2, length / 2):
        b.cylinder(M['steel'], 0.035, 2.7, centre=(x, 0, 1.05), segments=12)
        if wire:
            b.tube(M['steel'], [(x, 0, 2.38), (x, 0.28, 2.66)], 0.018, segments=8)
    for z in (0.08, 2.36):
        b.cylinder(M['steel'], 0.02, length, centre=(0, 0, z), axis='X', segments=10)
    if wire:
        for k in range(3):
            y, z = 0.09 + k * 0.09, 2.47 + k * 0.09
            b.tube(M['steel'], [(-length / 2, y, z), (0, y, z - 0.03), (length / 2, y, z)], 0.004, segments=5, caps=False)
    return b.finish(bevel=0.0, smooth_angle=60)


def wire_coil(length=3.0):
    """A coil of razor wire, pulled out along the ground."""
    b = bl.Builder('wire_coil')
    turns, radius = 9, 0.42
    points = []
    for i in range(turns * 14 + 1):
        t = i / 14
        angle = t * math.tau
        points.append((-length / 2 + t * length / turns, radius * math.cos(angle) * (1 + 0.04 * math.sin(t * 3.1)),
                       radius + 0.02 + radius * math.sin(angle)))
    b.tube(M['steel'], points, 0.006, segments=5, caps=False)
    # Barbs: a short spike every so often.
    for i in range(0, len(points), 3):
        p = Vector(points[i])
        b.box(M['steel'], (p.x - 0.012, p.y - 0.003, p.z - 0.012), (p.x + 0.012, p.y + 0.003, p.z + 0.012))
    return b.finish(bevel=0.0, smooth_angle=60)


# ---------------------------------------------------------------------------------- Fortifications

def jersey():
    b = bl.Builder('jersey')
    profile = [(-0.305, 0.0), (0.305, 0.0), (0.305, 0.075), (0.18, 0.33), (0.115, 0.81), (-0.115, 0.81), (-0.18, 0.33), (-0.305, 0.075)]
    b.prism(M['concrete'], profile, 3.0, axis='Y', offset=-1.5)
    obj = b.finish(bevel=0.018, bevel_segments=3)
    bl.transform_mesh(obj, Matrix.Rotation(math.radians(90), 4, 'Z'))
    return obj


def sandbag(b, x, y, z, turn, rng, length=0.62, width=0.3, height=0.16):
    """One sandbag, slumped."""
    faces = b.sphere(M['burlap'], 0.5, centre=(0, 0, 0), segments=12, rings=8,
                     scale=(length * rng.uniform(0.96, 1.06), width * rng.uniform(0.95, 1.08), height * rng.uniform(0.95, 1.1)))
    b.transform(faces, Matrix.Translation((x, y, z + height * 0.48)) @ Matrix.Rotation(math.radians(turn + rng.uniform(-6, 6)), 4, 'Z'))


def sandbags(name, length=2.4, courses=7, corner=False):
    """A wall of sandbags, two bags thick, laid like bricks."""
    b = bl.Builder(name)
    rng = random.Random(len(name) * 13 + courses)
    step = 0.56
    count = int(length / step)
    runs = [((0, 0), 0)] if not corner else [((0, 0), 0), ((length / 2 - 0.15, -length / 2 + 0.15), 90)]
    for (ox, oy), turn in runs:
        along = Vector((math.cos(math.radians(turn)), math.sin(math.radians(turn)), 0))
        across = Vector((-along.y, along.x, 0))
        for course in range(courses):
            shift = (course % 2) * step * 0.5
            for row in (-0.15, 0.15):
                for i in range(count + (course % 2 == 0 and 0 or -1) + 1):
                    t = -length / 2 + shift + (i + 0.5) * step
                    if abs(t) > length / 2 - 0.2:
                        continue
                    p = Vector((ox, oy, 0)) + along * t + across * row
                    sandbag(b, p.x, p.y, course * 0.15, turn, rng)
    return b.finish(bevel=0.0, smooth_angle=80)


def hesco():
    """An earth-filled barrier: a wire cage lined with cloth, a little over a metre each way."""
    b = bl.Builder('hesco')
    b.box(M['sandcloth'], (-0.55, -0.55, 0.0), (0.55, 0.55, 1.3))
    b.lathe(M['dirt'], [(0.0, 1.4), (0.3, 1.38), (0.52, 1.31), (0.54, 1.25)], segments=14)
    for i in range(6):
        t = -0.56 + i * 0.224
        for z in (0.0, 1.34):
            pass
        for sx, sy in ((1, 0), (0, 1)):
            for side in (-0.565, 0.565):
                a = (t, side, 0.0) if sx else (side, t, 0.0)
                c = (t, side, 1.34) if sx else (side, t, 1.34)
                b.tube(M['steel'], [a, c], 0.005, segments=5)
    for z in (0.02, 0.35, 0.68, 1.0, 1.33):
        b.tube(M['steel'], [(-0.565, -0.565, z), (0.565, -0.565, z), (0.565, 0.565, z), (-0.565, 0.565, z)], 0.005, segments=5, closed=True)
    return b.finish(bevel=0.02, bevel_segments=2)


def guard_booth():
    """A sentry's hut: a steel cabin with windows all round and its door open."""
    b = bl.Builder('guard_booth')
    w, d, h = 1.9, 1.9, 2.5
    wall_t = 0.06
    b.box(M['concrete'], (-w / 2 - 0.1, -d / 2 - 0.1, 0.0), (w / 2 + 0.1, d / 2 + 0.1, 0.12))
    for (x0, y0, x1, y1), door in (((-w / 2, d / 2 - wall_t, w / 2, d / 2), False), ((-w / 2, -d / 2, w / 2, -d / 2 + wall_t), False),
                                   ((-w / 2, -d / 2, -w / 2 + wall_t, d / 2), False), ((w / 2 - wall_t, -d / 2, w / 2, d / 2), True)):
        b.box(M['slate'], (x0, y0, 0.12), (x1, y1, 1.05 if not door else 0.12))
        b.box(M['slate'], (x0, y0, 2.05), (x1, y1, h))
        if not door:
            b.box(M['glass'], (x0 + (0 if x1 - x0 < 0.1 else 0.08), y0 + (0 if y1 - y0 < 0.1 else 0.08), 1.05),
                  (x1 - (0 if x1 - x0 < 0.1 else 0.08), y1 - (0 if y1 - y0 < 0.1 else 0.08), 2.05))
    for x in (-w / 2, w / 2 - 0.08):
        for y in (-d / 2, d / 2 - 0.08):
            b.box(M['slate'], (x, y, 0.12), (x + 0.08, y + 0.08, h))
    b.box(M['slate'], (-w / 2 - 0.25, -d / 2 - 0.25, h), (w / 2 + 0.25, d / 2 + 0.35, h + 0.1))
    b.box(M['lamp'], (-0.3, d / 2 + 0.2, h - 0.04), (0.3, d / 2 + 0.3, h))
    bl.add_text(b, 'HALT', 0.26, M['paint_white'], (0, d / 2 + 0.005, 0.7), '+Y')
    # A stool and a shelf inside.
    b.box(M['dark'], (-0.7, -0.7, 0.9), (0.6, -0.4, 0.94))
    b.cylinder(M['dark'], 0.17, 0.05, centre=(0.0, 0.1, 0.62), segments=16)
    b.cylinder(M['steel'], 0.02, 0.5, centre=(0.0, 0.1, 0.37), segments=8)
    return b.finish(bevel=0.006, bevel_segments=1)


def boom_gate(lowered=True):
    """A barrier arm across the road, striped red and white."""
    b = bl.Builder('boom_gate' if lowered else 'boom_gate_up')
    b.box(M['yellow'], (-0.2, -0.2, 0.0), (0.2, 0.2, 1.05))
    b.box(M['dark'], (-0.24, -0.24, 0.0), (0.24, 0.24, 0.1))
    arm = Matrix.Translation((0, 0, 0.95)) @ Matrix.Rotation(math.radians(0 if lowered else -78), 4, 'Y')
    for i in range(10):
        b.box(M['red'] if i % 2 == 0 else M['cream'], (0.2 + i * 0.5, -0.045, -0.045), (0.7 + i * 0.5, 0.045, 0.045), matrix=arm)
    b.box(M['dark'], (-0.75, -0.08, -0.14), (-0.2, 0.08, 0.14), matrix=arm)
    b.cylinder(M['lamp_red'], 0.04, 0.03, centre=(5.15, 0, 0.0), axis='X', segments=12, matrix=arm)
    return b.finish(bevel=0.006, bevel_segments=1)


def watchtower():
    """A scaffold tower with a sandbagged platform under a tin roof."""
    b = bl.Builder('watchtower')
    s, h = 1.3, 4.4
    for x in (-s, s):
        for y in (-s, s):
            b.cylinder(M['steel'], 0.045, h + 2.3, centre=(x, y, (h + 2.3) / 2), segments=10)
    for z in (1.4, 2.9):
        for a, c in (((-s, -s), (s, -s)), ((s, -s), (s, s)), ((s, s), (-s, s)), ((-s, s), (-s, -s))):
            b.tube(M['steel'], [(a[0], a[1], z), (c[0], c[1], z)], 0.028, segments=8)
            b.tube(M['steel'], [(a[0], a[1], z - 1.35), (c[0], c[1], z)], 0.022, segments=6)
    b.box(M['wood'], (-s - 0.15, -s - 0.15, h), (s + 0.15, s + 0.15, h + 0.08))
    for a, c in (((-s, -s), (s, -s)), ((s, -s), (s, s)), ((s, s), (-s, s)), ((-s, s), (-s, -s))):
        mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
        along = 90 if a[0] == c[0] else 0
        b.box(M['burlap'], (-s, -0.16, h + 0.08), (s, 0.16, h + 0.95), matrix=rz(along, (mid[0], mid[1], 0)))
        b.box(M['corrugated'], (-s - 0.05, -0.012, h + 0.08), (s + 0.05, 0.012, h + 0.7),
              matrix=rz(along, (mid[0] * 1.14, mid[1] * 1.14, 0)))
    b.prism(M['corrugated'], [(-s - 0.5, h + 2.15), (s + 0.5, h + 2.45), (s + 0.5, h + 2.48), (-s - 0.5, h + 2.18)],
            2 * s + 0.9, axis='Y', offset=-s - 0.45)
    # The ladder up one side.
    for x in (-0.25, 0.25):
        b.tube(M['steel'], [(x, -s - 0.5, 0.0), (x, -s - 0.12, h + 1.0)], 0.022, segments=8)
    for i in range(14):
        t = (i + 0.5) / 14.5
        b.tube(M['steel'], [(-0.25, -s - 0.5 + 0.38 * t * (h + 1) / (h + 1), t * (h + 1)), (0.25, -s - 0.5 + 0.38 * t, t * (h + 1))], 0.014, segments=6)
    b.cylinder(M['dark'], 0.11, 0.2, centre=(s - 0.1, s + 0.05, h + 1.6), axis='Y', segments=14)
    b.cylinder(M['lamp'], 0.1, 0.01, centre=(s - 0.1, s + 0.155, h + 1.6), axis='Y', segments=14)
    return b.finish(bevel=0.0, smooth_angle=50)


def floodlight():
    """A work light on a tripod mast: four lamps on a bar."""
    b = bl.Builder('floodlight')
    b.cylinder(M['yellow'], 0.035, 3.6, centre=(0, 0, 1.9), segments=10)
    for angle in (90, 210, 330):
        a = math.radians(angle)
        b.tube(M['yellow'], [(0, 0, 1.1), (0.8 * math.cos(a), 0.8 * math.sin(a), 0.03)], 0.02, segments=8)
    b.box(M['dark'], (-0.7, -0.03, 3.65), (0.7, 0.03, 3.72))
    for x in (-0.52, -0.18, 0.18, 0.52):
        b.box(M['dark'], (x - 0.14, -0.02, 3.72), (x + 0.14, 0.12, 3.98))
        b.box(M['lamp'], (x - 0.12, 0.12, 3.74), (x + 0.12, 0.125, 3.96))
    return b.finish(bevel=0.004, bevel_segments=1, smooth_angle=50)


def generator():
    """A towed diesel generator on its skid."""
    b = bl.Builder('generator')
    b.box(M['dark'], (-1.0, -0.5, 0.0), (1.0, 0.5, 0.12))
    b.box(M['olive'], (-0.9, -0.45, 0.12), (0.9, 0.45, 1.05))
    for i in range(8):
        b.box(M['dark'], (-0.91, -0.38, 0.3 + i * 0.08), (-0.9, 0.38, 0.34 + i * 0.08))
    b.box(M['grey'], (0.3, 0.45, 0.45), (0.8, 0.47, 0.9))
    b.tube(M['rust'], [(0.55, 0.0, 1.05), (0.55, 0.0, 1.35), (0.75, 0.0, 1.45)], 0.04, segments=10)
    b.box(M['red'], (-0.6, 0.5, 0.0), (-0.25, 0.75, 0.45))
    return b.finish(bevel=0.012, bevel_segments=2)


def tank_trap():
    """A steel hedgehog: three beams welded across each other."""
    b = bl.Builder('tank_trap')
    for turn in (Matrix.Rotation(math.radians(54.7), 4, 'Y'), Matrix.Rotation(math.radians(120), 4, 'Z') @ Matrix.Rotation(math.radians(54.7), 4, 'Y'),
                 Matrix.Rotation(math.radians(240), 4, 'Z') @ Matrix.Rotation(math.radians(54.7), 4, 'Y')):
        place = Matrix.Translation((0, 0, 0.58)) @ turn
        b.box(M['rust'], (-0.06, -0.006, -0.95), (0.06, 0.006, 0.95), matrix=place)
        b.box(M['rust'], (-0.006, -0.06, -0.95), (0.006, 0.06, 0.95), matrix=place)
    return b.finish(bevel=0.0)


def crate(name, mat, size=(0.9, 0.9, 0.9), military=False):
    b = bl.Builder(name)
    w, d, h = size
    b.box(mat, (-w / 2, -d / 2, 0.02), (w / 2, d / 2, h))
    if military:
        b.box(M['dark'], (-w / 2 - 0.006, -d / 2 - 0.006, h * 0.72), (w / 2 + 0.006, d / 2 + 0.006, h * 0.74))
        for x in (-w * 0.3, w * 0.3):
            b.box(M['steel'], (x - 0.03, d / 2, h * 0.62), (x + 0.03, d / 2 + 0.015, h * 0.8))
        for side in (-1, 1):
            b.tube(M['dark'], [(side * (w / 2 + 0.005), -0.1, h * 0.55), (side * (w / 2 + 0.05), -0.1, h * 0.5),
                               (side * (w / 2 + 0.05), 0.1, h * 0.5), (side * (w / 2 + 0.005), 0.1, h * 0.55)], 0.008, segments=6)
    else:
        f = M['wood']
        for x in (-w / 2 - 0.012, w / 2 - 0.05):
            for y in (-d / 2 - 0.025, d / 2):
                b.box(f, (x, y, 0.0), (x + 0.062, y + 0.025, h + 0.01))
        for z in (0.0, h - 0.06):
            b.box(f, (-w / 2, -d / 2 - 0.025, z), (w / 2, -d / 2, z + 0.07))
            b.box(f, (-w / 2, d / 2, z), (w / 2, d / 2 + 0.025, z + 0.07))
            b.box(f, (-w / 2 - 0.025, -d / 2, z), (-w / 2, d / 2, z + 0.07))
            b.box(f, (w / 2, -d / 2, z), (w / 2 + 0.025, d / 2, z + 0.07))
    return b.finish(bevel=0.005, bevel_segments=1)


def ammo_box():
    """A steel ammunition can, lid latched: what the player picks rounds up from."""
    b = bl.Builder('ammo_box')
    b.box(M['olive'], (-0.15, -0.075, 0.0), (0.15, 0.075, 0.18))
    b.box(M['olive'], (-0.155, -0.08, 0.17), (0.155, 0.08, 0.2))
    b.box(M['dark'], (0.15, -0.03, 0.08), (0.162, 0.03, 0.19))
    b.tube(M['dark'], [(-0.08, 0, 0.2), (-0.08, 0, 0.225), (0.08, 0, 0.225), (0.08, 0, 0.2)], 0.006, segments=6)
    bl.add_text(b, '5.56 MM', 0.035, M['yellow'], (0, 0.0752, 0.1), '+Y', extrude=0.0005)
    return b.finish(bevel=0.004, bevel_segments=1)


def pallet():
    b = bl.Builder('pallet')
    for y in (-0.5, 0, 0.5):
        b.box(M['wood'], (-0.6, y - 0.05, 0.0), (0.6, y + 0.05, 0.1))
    for i in range(7):
        x = -0.54 + i * 0.18
        b.box(M['wood'], (x - 0.05, -0.55, 0.1), (x + 0.05, 0.55, 0.122))
    return b.finish(bevel=0.003, bevel_segments=1)


def drum(name, mat, holes=False):
    b = bl.Builder(name)
    r = 0.286
    profile = [(0.0, 0.012), (r - 0.012, 0.012), (r - 0.012, 0.0), (r, 0.0), (r, 0.02), (r - 0.004, 0.03)]
    for hoop in (0.29, 0.59):
        profile += [(r - 0.004, hoop - 0.022), (r + 0.008, hoop - 0.008), (r + 0.008, hoop + 0.008), (r - 0.004, hoop + 0.022)]
    if holes:
        profile += [(r - 0.004, 0.85), (r, 0.86), (r, 0.88), (r - 0.012, 0.88), (r - 0.012, 0.3), (0.0, 0.3)]
    else:
        profile += [(r - 0.004, 0.85), (r, 0.86), (r, 0.88), (r - 0.012, 0.88), (r - 0.012, 0.868), (0.0, 0.868)]
        b.cylinder(M['steel'], 0.028, 0.012, centre=(0.17, 0.0, 0.874), segments=16)
    b.lathe(mat, profile, segments=32)
    return b.finish(bevel=0.0015, smooth_angle=50)


# ---------------------------------------------------------------------------------- The street

def street_light():
    b = bl.Builder('street_light')
    b.cylinder(M['grey'], 0.11, 0.5, centre=(0, 0, 0.25), segments=14)
    b.lathe(M['grey'], [(0.085, 0.5), (0.055, 8.2)], segments=14)
    b.tube(M['grey'], [(0, 0, 8.1), (0, 0.6, 8.75), (0, 2.0, 8.9)], 0.04, segments=10)
    b.box(M['grey'], (-0.16, 1.7, 8.8), (0.16, 2.45, 8.95))
    b.box(M['glass'], (-0.13, 1.8, 8.775), (0.13, 2.38, 8.8))
    return b.finish(bevel=0.005, bevel_segments=1, smooth_angle=50)


def utility_pole():
    """A wooden power pole with a cross-arm, insulators and a transformer."""
    b = bl.Builder('utility_pole')
    b.lathe(M['wood'], [(0.16, -0.5), (0.12, 9.6), (0.0, 9.6)], segments=14)
    b.box(M['wood'], (-1.2, -0.06, 8.7), (1.2, 0.06, 8.84))
    for x in (-1.05, -0.45, 0.45, 1.05):
        b.lathe(M['glass'], [(0.03, 8.84), (0.045, 8.9), (0.03, 8.96), (0.04, 9.0), (0.0, 9.02)], segments=10, centre=(x, 0, 0))
    b.cylinder(M['grey'], 0.24, 0.75, centre=(0.0, 0.34, 7.6), segments=18)
    b.box(M['dark'], (-0.05, 0.1, 7.4), (0.05, 0.3, 7.8))
    b.tube(M['dark'], [(0.15, 0.34, 7.98), (0.3, 0.2, 8.4), (0.45, 0.0, 8.86)], 0.012, segments=6)
    return b.finish(bevel=0.0, smooth_angle=50)


def wire_span(length=30.0):
    """Power lines between two poles `length` apart, sagging: four along the cross-arms."""
    b = bl.Builder('wire_span')
    for x in (-1.05, -0.45, 0.45, 1.05):
        points = []
        for i in range(13):
            t = i / 12
            points.append((x, -length / 2 + t * length, 8.98 - 1.1 * 4 * t * (1 - t)))
        b.tube(M['dark'], points, 0.011, segments=5, caps=False)
    return b.finish(bevel=0.0, smooth_angle=80)


def sign(name, body, post_height=2.2):
    """A road sign on a steel post: `body(builder, height)` draws its face."""
    b = bl.Builder(name)
    b.box(M['steel'], (-0.025, -0.02, 0.0), (0.025, 0.02, post_height + 0.4))
    body(b, post_height)
    return b.finish(bevel=0.002, bevel_segments=1)


def stop_face(b, h):
    octagon = [(0.38 * math.cos(math.radians(22.5 + 45 * i)), h + 0.38 * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    b.prism(M['red'], octagon, 0.006, axis='Y', offset=0.02)
    b.prism(M['cream'], [(x * 0.94, h + (z - h) * 0.94) for x, z in octagon], 0.002, axis='Y', offset=0.018)
    bl.add_text(b, 'STOP', 0.24, M['paint_white'], (0, 0.0262, h), '+Y', extrude=0.0006)


def street_name(text_top, text_side):
    def face(b, h):
        b.box(M['green'], (-0.5, -0.008, h + 0.2), (0.5, 0.008, h + 0.4))
        bl.add_text(b, text_top, 0.11, M['paint_white'], (0, 0.0085, h + 0.3), '+Y', extrude=0.0005)
        bl.add_text(b, text_top, 0.11, M['paint_white'], (0, -0.0085, h + 0.3), '-Y', extrude=0.0005)
        b.box(M['green'], (-0.008, -0.5, h - 0.02), (0.008, 0.5, h + 0.18))
        bl.add_text(b, text_side, 0.11, M['paint_white'], (0.0085, 0, h + 0.08), '+X', extrude=0.0005)
        bl.add_text(b, text_side, 0.11, M['paint_white'], (-0.0085, 0, h + 0.08), '-X', extrude=0.0005)
    return face


def notice_board(name, lines, colour='paint_red', width=1.5, height=1.1):
    """A board on two posts with lettering: the occupier's orders to the town."""
    b = bl.Builder(name)
    for x in (-width / 2 + 0.08, width / 2 - 0.08):
        b.box(M['steel'], (x - 0.03, -0.03, 0.0), (x + 0.03, 0.03, 1.3 + height))
    b.box(M['cream'], (-width / 2, 0.03, 1.2), (width / 2, 0.05, 1.2 + height))
    b.box(M[colour], (-width / 2, 0.05, 1.2 + height - 0.2), (width / 2, 0.052, 1.2 + height))
    size = min(0.15, (height - 0.3) / max(len(lines), 1) * 0.7)
    for i, line in enumerate(lines):
        z = 1.2 + height - 0.32 - i * size * 1.45
        bl.add_text(b, line, size if i else size * 1.15, M['ink'], (0, 0.0505, z), '+Y', extrude=0.0005)
    return b.finish(bevel=0.003, bevel_segments=1)


def emblem(b, mat, centre, size, facing_y=0.0):
    """The Directorate's mark: a hexagon, open, with a chevron pointing up inside it."""
    cx, cz = centre
    outer = [(cx + size * math.cos(math.radians(30 + 60 * i)), cz + size * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    inner = [(cx + size * 0.78 * math.cos(math.radians(30 + 60 * i)), cz + size * 0.78 * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    for i in range(6):
        j = (i + 1) % 6
        b.prism(mat, [outer[i], outer[j], inner[j], inner[i]], 0.003, axis='Y', offset=facing_y)
    s = size
    b.prism(mat, [(cx - 0.5 * s, cz - 0.3 * s), (cx, cz + 0.32 * s), (cx + 0.5 * s, cz - 0.3 * s), (cx + 0.5 * s, cz - 0.52 * s),
                  (cx, cz + 0.08 * s), (cx - 0.5 * s, cz - 0.52 * s)], 0.003, axis='Y', offset=facing_y)


def banner():
    """The occupier's banner, hung from a pole: red, with their mark in white."""
    b = bl.Builder('banner')
    b.cylinder(M['steel'], 0.03, 1.6, centre=(0, 0, 4.1), axis='X', segments=10)
    b.box(M['banner'], (-0.7, -0.012, 1.0), (0.7, 0.012, 4.08))
    b.box(M['ink'], (-0.7, 0.012, 3.75), (0.7, 0.014, 3.95))
    b.box(M['ink'], (-0.7, 0.012, 1.1), (0.7, 0.014, 1.3))
    emblem(b, M['paint_white'], (0, 2.55), 0.5, 0.012)
    return b.finish(bevel=0.0)


def flag_pole():
    b = bl.Builder('flag_pole')
    b.lathe(M['steel'], [(0.05, 0.0), (0.03, 7.0), (0.045, 7.05), (0.0, 7.1)], segments=12)
    b.box(M['banner'], (0.03, -0.01, 5.5), (2.1, 0.01, 6.9))
    emblem(b, M['paint_white'], (1.05, 6.2), 0.42, 0.01)
    emblem(b, M['paint_white'], (1.05, 6.2), 0.42, -0.013)
    return b.finish(bevel=0.0, smooth_angle=50)


def mailbox():
    b = bl.Builder('mailbox')
    b.box(M['wood'], (-0.045, -0.045, 0.0), (0.045, 0.045, 1.05))
    b.prism(M['grey'], [(-0.09, 1.05), (0.09, 1.05), (0.09, 1.2), (0.06, 1.27), (0.0, 1.29), (-0.06, 1.27), (-0.09, 1.2)], 0.46, axis='Y', offset=-0.2)
    b.box(M['red'], (0.09, 0.05, 1.12), (0.1, 0.07, 1.3))
    return b.finish(bevel=0.004, bevel_segments=1)


def trash_bin(tipped=False):
    """A wheeled rubbish bin."""
    b = bl.Builder('trash_bin_tipped' if tipped else 'trash_bin')
    turn = Matrix.Translation((0, 0, 0.3)) @ Matrix.Rotation(math.radians(90), 4, 'X') @ Matrix.Translation((0, 0, -0.02)) if tipped else Matrix.Identity(4)
    b.prism(M['bin'], [(-0.24, 0.08), (0.24, 0.08), (0.29, 1.0), (-0.29, 1.0)], 0.56, axis='Y', offset=-0.28, matrix=turn)
    b.box(M['bin'], (-0.31, -0.31, 1.0), (0.31, 0.33, 1.05), matrix=turn)
    for x in (-0.27, 0.27):
        b.cylinder(M['black'], 0.1, 0.04, centre=(x, -0.27, 0.1), axis='X', segments=14, matrix=turn)
    b.tube(M['bin'], [(-0.22, -0.33, 0.98), (0.22, -0.33, 0.98)], 0.015, segments=8, matrix=turn)
    return b.finish(bevel=0.012, bevel_segments=2)


def dumpster():
    b = bl.Builder('dumpster')
    b.prism(M['green'], [(-0.9, 0.15), (0.9, 0.15), (0.9, 1.25), (-0.9, 1.45)], 1.9, axis='X', offset=-0.95)
    b.prism(M['black'], [(-0.92, 1.47), (0.92, 1.27), (0.92, 1.31), (-0.92, 1.51)], 1.94, axis='X', offset=-0.97)
    for x in (-0.99, 0.95):
        b.box(M['green'], (x, -0.3, 0.75), (x + 0.04, 0.3, 0.9))
    for x in (-0.8, 0.8):
        for y in (-0.75, 0.75):
            b.cylinder(M['black'], 0.075, 0.05, centre=(x, y, 0.075), axis='X', segments=12)
    return b.finish(bevel=0.012, bevel_segments=2)


def hydrant():
    b = bl.Builder('hydrant')
    b.lathe(M['yellow'], [(0.0, 0.0), (0.14, 0.0), (0.14, 0.05), (0.095, 0.07), (0.095, 0.5), (0.12, 0.52), (0.12, 0.56),
                          (0.09, 0.6), (0.05, 0.69), (0.02, 0.71), (0.02, 0.75), (0.0, 0.75)], segments=18)
    for side in (-1, 1):
        b.cylinder(M['yellow'], 0.05, 0.1, centre=(side * 0.13, 0, 0.4), axis='X', segments=12)
    b.cylinder(M['yellow'], 0.06, 0.1, centre=(0, 0.13, 0.36), axis='Y', segments=12)
    return b.finish(bevel=0.003, bevel_segments=1, smooth_angle=50)


def cone():
    b = bl.Builder('cone')
    b.box(M['orange'], (-0.18, -0.18, 0.0), (0.18, 0.18, 0.03))
    b.lathe(M['orange'], [(0.14, 0.03), (0.105, 0.3), (0.035, 0.7), (0.0, 0.7)], segments=16)
    b.lathe(M['paint_white'], [(0.107, 0.3), (0.085, 0.42), (0.087, 0.42), (0.109, 0.3)], segments=16)
    return b.finish(bevel=0.003, bevel_segments=1, smooth_angle=50)


def tyres(count=3):
    b = bl.Builder('tyre_stack')
    rng = random.Random(count)
    for i in range(count):
        faces = b.lathe(M['rubber'], [(0.19, -0.1), (0.3, -0.105), (0.335, -0.07), (0.345, 0.0), (0.335, 0.07), (0.3, 0.105),
                                      (0.19, 0.1), (0.185, 0.0), (0.19, -0.1)], segments=28)
        b.transform(faces, Matrix.Translation((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0.105 + i * 0.21)))
    return b.finish(bevel=0.0, smooth_angle=60)


def rubble(seed=1):
    """A heap of broken masonry and timber."""
    b = bl.Builder(f'rubble_{seed}')
    rng = random.Random(seed)
    for _ in range(26):
        size = Vector((rng.uniform(0.12, 0.5), rng.uniform(0.1, 0.35), rng.uniform(0.06, 0.22)))
        r = rng.uniform(0, 1.1)
        a = rng.uniform(0, math.tau)
        at = Vector((r * math.cos(a), r * math.sin(a), max(0.03, (1.15 - r) * rng.uniform(0.1, 0.42))))
        turn = Matrix.Translation(at) @ Matrix.Rotation(rng.uniform(0, math.tau), 4, 'Z') @ Matrix.Rotation(rng.uniform(-0.6, 0.6), 4, 'X')
        b.box(rng.choice([M['concrete'], M['concrete'], M['concrete'], M['plywood']]), -size / 2, size / 2, matrix=turn)
    for _ in range(5):
        a = rng.uniform(0, math.tau)
        turn = Matrix.Translation((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(0.15, 0.4))) @ \
            Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, 'Y')
        b.box(M['wood'], (-0.9, -0.045, -0.02), (0.9, 0.045, 0.02), matrix=turn)
    return b.finish(bevel=0.008, bevel_segments=1)


# ---------------------------------------------------------------------------------- Yards

def swing_set():
    b = bl.Builder('swing_set')
    for x in (-1.5, 1.5):
        for y in (-0.9, 0.9):
            b.tube(M['blue'], [(x, y, 0.0), (x, 0.0, 2.2)], 0.03, segments=8)
    b.tube(M['blue'], [(-1.6, 0, 2.2), (1.6, 0, 2.2)], 0.035, segments=10)
    for x, swing in ((-0.7, 0.18), (0.6, -0.1)):
        for dx in (-0.2, 0.2):
            b.tube(M['steel'], [(x + dx, 0, 2.2), (x + dx, swing, 0.55)], 0.005, segments=5)
        b.box(M['black'], (x - 0.24, swing - 0.08, 0.52), (x + 0.24, swing + 0.08, 0.55))
    return b.finish(bevel=0.0, smooth_angle=50)


def picnic_table():
    b = bl.Builder('picnic_table')
    for y in (-0.33, -0.11, 0.11, 0.33):
        b.box(M['wood'], (-0.9, y - 0.1, 0.72), (0.9, y + 0.1, 0.76))
    for side in (-1, 1):
        for y in (0.62, 0.84):
            b.box(M['wood'], (-0.9, side * y - 0.1, 0.42), (0.9, side * y + 0.1, 0.46))
    for x in (-0.65, 0.65):
        b.box(M['wood'], (x - 0.04, -0.95, 0.36), (x + 0.04, 0.95, 0.42))
        for side in (-1, 1):
            b.tube(M['wood'], [(x, side * 0.3, 0.72), (x, side * 0.75, 0.0)], 0.045, segments=4)
    return b.finish(bevel=0.004, bevel_segments=1)


def barbecue():
    b = bl.Builder('barbecue')
    b.lathe(M['dark'], [(0.0, 0.62), (0.2, 0.66), (0.27, 0.78), (0.28, 0.88), (0.27, 0.98), (0.2, 1.08), (0.03, 1.13), (0.0, 1.13)], segments=20)
    for a in (90, 210, 330):
        r = math.radians(a)
        b.tube(M['steel'], [(0.14 * math.cos(r), 0.14 * math.sin(r), 0.7), (0.3 * math.cos(r), 0.3 * math.sin(r), 0.0)], 0.012, segments=6)
    b.box(M['dark'], (-0.04, -0.015, 1.13), (0.04, 0.015, 1.17))
    return b.finish(bevel=0.0, smooth_angle=50)


def lawn_chair(fallen=False):
    b = bl.Builder('lawn_chair_fallen' if fallen else 'lawn_chair')
    turn = Matrix.Translation((0, 0, 0.27)) @ Matrix.Rotation(math.radians(-88), 4, 'X') if fallen else Matrix.Identity(4)
    b.box(M['white'], (-0.27, -0.25, 0.4), (0.27, 0.25, 0.43), matrix=turn)
    b.box(M['white'], (-0.27, -0.27, 0.43), (0.27, -0.24, 0.9), matrix=turn)
    for x in (-0.25, 0.25):
        for y in (-0.23, 0.23):
            b.box(M['white'], (x - 0.018, y - 0.018, 0.0), (x + 0.018, y + 0.018, 0.4), matrix=turn)
        b.box(M['white'], (x - 0.025, -0.25, 0.62), (x + 0.025, 0.22, 0.645), matrix=turn)
    return b.finish(bevel=0.006, bevel_segments=2)


def woodpile():
    b = bl.Builder('woodpile')
    rng = random.Random(5)
    for row in range(5):
        for i in range(9 - row % 2):
            x = -0.8 + i * 0.2 + (row % 2) * 0.1
            faces = b.cylinder(M['wood'], rng.uniform(0.075, 0.1), 0.45, centre=(0, 0, 0), axis='Y', segments=8)
            b.transform(faces, Matrix.Translation((x, rng.uniform(-0.02, 0.02), 0.1 + row * 0.17)))
    return b.finish(bevel=0.0, smooth_angle=50)


def washing_line():
    """A line between two posts, with sheets left out on it."""
    b = bl.Builder('washing_line')
    for x in (-2.2, 2.2):
        b.cylinder(M['steel'], 0.025, 2.0, centre=(x, 0, 1.0), segments=8)
        b.box(M['steel'], (x - 0.02, -0.35, 1.95), (x + 0.02, 0.35, 1.99))
    b.tube(M['steel'], [(-2.2, 0, 1.97), (0, 0, 1.9), (2.2, 0, 1.97)], 0.004, segments=5)
    for x0, x1, mat, drop in ((-1.7, -0.5, M['cloth'], 1.2), (-0.2, 0.9, M['paper'], 1.0), (1.1, 1.7, M['tarp_blue'], 0.7)):
        b.box(mat, (x0, -0.006, 1.92 - drop), (x1, 0.006, 1.92))
    return b.finish(bevel=0.0)


# ---------------------------------------------------------------------------------- The safehouse

def workbench():
    b = bl.Builder('workbench')
    b.box(M['wood'], (-0.95, -0.36, 0.86), (0.95, 0.36, 0.92))
    for x in (-0.88, 0.88):
        for y in (-0.3, 0.3):
            b.box(M['wood'], (x - 0.04, y - 0.04, 0.0), (x + 0.04, y + 0.04, 0.86))
    b.box(M['wood'], (-0.9, -0.32, 0.2), (0.9, 0.32, 0.23))
    b.box(M['plywood'], (-0.95, -0.38, 0.92), (0.95, -0.36, 1.9))
    # A vice, a toolbox, and tools on the board behind.
    b.box(M['blue'], (0.55, 0.12, 0.92), (0.75, 0.32, 1.02))
    b.box(M['steel'], (0.58, 0.3, 1.02), (0.72, 0.4, 1.1))
    b.box(M['red'], (-0.8, -0.2, 0.92), (-0.35, 0.05, 1.12))
    for x, length in ((-0.6, 0.3), (-0.45, 0.24), (-0.3, 0.35), (-0.1, 0.28), (0.1, 0.2)):
        b.box(M['steel'], (x - 0.012, -0.36, 1.6 - length), (x + 0.012, -0.35, 1.6))
        b.box(M['red'], (x - 0.018, -0.365, 1.6 - length - 0.1), (x + 0.018, -0.345, 1.6 - length))
    b.cylinder(M['red'], 0.12, 0.34, centre=(0.3, -0.05, 0.4), segments=16)
    return b.finish(bevel=0.004, bevel_segments=1)


def shelving():
    b = bl.Builder('shelving')
    for x in (-0.6, 0.6):
        for y in (-0.22, 0.22):
            b.box(M['grey'], (x - 0.02, y - 0.02, 0.0), (x + 0.02, y + 0.02, 1.9))
    rng = random.Random(8)
    for z in (0.15, 0.6, 1.05, 1.5):
        b.box(M['plywood'], (-0.62, -0.24, z), (0.62, 0.24, z + 0.025))
        x = -0.55
        while x < 0.4:
            w = rng.uniform(0.15, 0.32)
            h = rng.uniform(0.12, 0.34)
            mat = rng.choice([M['paper'], M['paper'], M['olive'], M['red'], M['blue'], M['dark']])
            b.box(mat, (x, -0.18, z + 0.025), (x + w, 0.16, z + 0.025 + h))
            x += w + rng.uniform(0.02, 0.1)
    return b.finish(bevel=0.004, bevel_segments=1)


def map_table():
    """A trestle table with the cell's map of the town pinned to it, a radio and a lantern."""
    b = bl.Builder('map_table')
    b.box(M['plywood'], (-0.9, -0.5, 0.74), (0.9, 0.5, 0.77))
    for x in (-0.7, 0.7):
        for side in (-1, 1):
            b.tube(M['wood'], [(x, side * 0.1, 0.74), (x, side * 0.42, 0.0)], 0.03, segments=4)
    b.box(M['paper'], (-0.6, -0.38, 0.77), (0.35, 0.36, 0.772))
    # The streets, inked in, and the target ringed in red.
    for a, c in (((-0.5, 0.0), (0.3, 0.0)), ((-0.35, -0.3), (-0.35, 0.28)), ((0.05, -0.32), (0.05, 0.3)), ((-0.5, 0.2), (0.0, 0.2))):
        b.box(M['ink'], (min(a[0], c[0]) - 0.006, min(a[1], c[1]) - 0.006, 0.772), (max(a[0], c[0]) + 0.006, max(a[1], c[1]) + 0.006, 0.7725))
    b.lathe(M['paint_red'], [(0.05, 0.7722), (0.062, 0.7722), (0.062, 0.773), (0.05, 0.773), (0.05, 0.7722)], segments=20, centre=(0.2, 0.0, 0))
    # The radio set.
    b.box(M['olive'], (0.45, -0.3, 0.77), (0.85, 0.0, 0.98))
    b.box(M['dark'], (0.47, 0.0, 0.8), (0.83, 0.006, 0.95))
    b.cylinder(M['dark'], 0.004, 0.6, centre=(0.8, -0.25, 1.28), segments=6)
    for x in (0.55, 0.65, 0.75):
        b.cylinder(M['steel'], 0.015, 0.02, centre=(x, 0.012, 0.86), axis='Y', segments=10)
    # A hurricane lantern, lit.
    b.lathe(M['red'], [(0.0, 0.77), (0.07, 0.77), (0.075, 0.82), (0.05, 0.84)], segments=14, centre=(-0.7, 0.3, 0))
    b.lathe(M['lamp_warm'], [(0.045, 0.84), (0.06, 0.9), (0.045, 0.97)], segments=14, centre=(-0.7, 0.3, 0))
    b.lathe(M['red'], [(0.05, 0.97), (0.03, 1.02), (0.0, 1.03)], segments=14, centre=(-0.7, 0.3, 0))
    return b.finish(bevel=0.003, bevel_segments=1, smooth_angle=50)


def bedroll():
    b = bl.Builder('bedroll')
    b.box(M['tarp'], (-0.35, -0.95, 0.0), (0.35, 0.95, 0.08))
    b.box(M['cloth'], (-0.3, 0.45, 0.08), (0.3, 0.9, 0.17))
    b.cylinder(M['tarp_blue'], 0.11, 0.6, centre=(0, -0.8, 0.19), axis='X', segments=14)
    return b.finish(bevel=0.03, bevel_segments=3)


def boxes():
    b = bl.Builder('boxes')
    rng = random.Random(3)
    for x, y, z, s in ((0, 0, 0, 0.5), (0.55, 0.05, 0, 0.42), (0.1, 0.02, 0.5, 0.4), (-0.5, 0.2, 0, 0.36)):
        turn = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rng.uniform(-0.3, 0.3), 4, 'Z')
        b.box(M['paper'], (-s / 2, -s / 2, 0), (s / 2, s / 2, s * 0.8), matrix=turn)
        b.box(M['wood'], (-0.03, -s / 2 - 0.001, 0), (0.03, s / 2 + 0.001, s * 0.8 + 0.001), matrix=turn)
    return b.finish(bevel=0.004, bevel_segments=1)


def graffiti(name, lines, mat='paint_white', size=0.34):
    """Words sprayed on a wall: stand it a hair off the wall it is on."""
    b = bl.Builder(name)
    for i, line in enumerate(lines):
        bl.add_text(b, line, size, M[mat], (0, 0, 1.6 - i * size * 1.25), '+Y', extrude=0.0004,
                    matrix=Matrix.Rotation(math.radians(-3 + i * 2), 4, 'Y'))
    return b.finish(bevel=0.0, uv=False)


# ---------------------------------------------------------------------------------- The filling station

def canopy():
    """The filling station's canopy: a flat roof on four steel columns, its fascia lettered."""
    b = bl.Builder('station_canopy')
    w, d, h = 16.0, 9.0, 5.0
    for x in (-5.0, 5.0):
        for y in (-2.2, 2.2):
            b.box(M['cream'], (x - 0.2, y - 0.2, 0.0), (x + 0.2, y + 0.2, h))
            b.box(M['concrete'], (x - 0.35, y - 0.35, 0.0), (x + 0.35, y + 0.35, 0.5))
    b.box(M['cream'], (-w / 2, -d / 2, h), (w / 2, d / 2, h + 0.9))
    b.box(M['red'], (-w / 2 - 0.02, -d / 2 - 0.02, h + 0.55), (w / 2 + 0.02, d / 2 + 0.02, h + 0.75))
    b.box(M['plaster' if 'plaster' in M else 'cream'], (-w / 2 + 0.3, -d / 2 + 0.3, h - 0.02), (w / 2 - 0.3, d / 2 - 0.3, h))
    bl.add_text(b, 'CASCADE FUEL', 0.5, M['ink'], (0, d / 2 + 0.005, h + 0.27), '+Y', extrude=0.01)
    bl.add_text(b, 'CASCADE FUEL', 0.5, M['ink'], (0, -d / 2 - 0.005, h + 0.27), '-Y', extrude=0.01)
    for x in (-4.0, 0.0, 4.0):
        b.box(M['glass'], (x - 0.9, -0.3, h - 0.03), (x + 0.9, 0.3, h - 0.02))
    # The islands the pumps stand on.
    for x in (-5.0, 5.0):
        b.box(M['concrete'], (x - 0.6, -3.6, 0.0), (x + 0.6, 3.6, 0.16))
    return b.finish(bevel=0.01, bevel_segments=1)


def pump():
    b = bl.Builder('station_pump')
    b.box(M['cream'], (-0.35, -0.25, 0.0), (0.35, 0.25, 1.5))
    b.box(M['red'], (-0.37, -0.27, 1.5), (0.37, 0.27, 2.05))
    for side in (-1, 1):
        y = side * 0.25
        b.box(M['dark'], (-0.26, min(y, y + side * 0.012), 1.0), (0.26, max(y, y + side * 0.012), 1.4))
        b.box(M['dark'], (-0.26, min(y, y + side * 0.012), 0.5), (0.26, max(y, y + side * 0.012), 0.9))
    for x in (-0.4, 0.4):
        b.tube(M['black'], [(x, 0, 1.3), (x * 1.5, 0, 0.5), (x * 1.3, 0, 0.3), (x, 0, 0.95)], 0.016, segments=6)
        b.box(M['dark'], (x - 0.03, -0.05, 0.9), (x + 0.03, 0.05, 1.12))
    return b.finish(bevel=0.01, bevel_segments=2)


def store():
    """The filling station's shop: a flat-roofed block, its windows boarded, its door forced."""
    b = bl.Builder('station_store')
    w, d, h = 13.0, 8.0, 3.6
    t = 0.25
    block = M['paint_white']
    plaster = bl.material('stucco_cream', 'stucco', tint=(0.78, 0.74, 0.64))
    b.box(M['concrete'], (-w / 2, -d / 2, -0.2), (w / 2, d / 2, 0.1))
    # Back and side walls, solid; the front, with its openings.
    b.box(plaster, (-w / 2, -d / 2, 0.1), (w / 2, -d / 2 + t, h))
    b.box(plaster, (-w / 2, -d / 2, 0.1), (-w / 2 + t, d / 2, h))
    b.box(plaster, (w / 2 - t, -d / 2, 0.1), (w / 2, d / 2, h))
    openings = [(1.0, 3.6), (5.2, 1.6), (7.4, 4.4)]
    cursor = 0.0
    for start, width in openings:
        b.box(plaster, (-w / 2 + cursor, d / 2 - t, 0.1), (-w / 2 + start, d / 2, h))
        b.box(plaster, (-w / 2 + start, d / 2 - t, 2.7), (-w / 2 + start + width, d / 2, h))
        if width > 2:
            b.box(plaster, (-w / 2 + start, d / 2 - t, 0.1), (-w / 2 + start + width, d / 2, 0.7))
            b.box(M['plywood'], (-w / 2 + start - 0.05, d / 2 - 0.02, 0.65), (-w / 2 + start + width + 0.05, d / 2 + 0.02, 2.75))
            for z in (1.1, 2.2):
                b.box(M['wood'], (-w / 2 + start - 0.1, d / 2 + 0.02, z), (-w / 2 + start + width + 0.1, d / 2 + 0.05, z + 0.1))
        cursor = start + width
    b.box(plaster, (-w / 2 + cursor, d / 2 - t, 0.1), (w / 2, d / 2, h))
    b.box(M['concrete'], (-w / 2 - 0.1, -d / 2 - 0.1, h), (w / 2 + 0.1, d / 2 + 0.1, h + 0.25))
    b.box(M['red'], (-w / 2 - 0.12, d / 2 + 0.02, h - 0.7), (w / 2 + 0.12, d / 2 + 0.1, h - 0.1))
    bl.add_text(b, 'CASCADE FOOD MART', 0.34, M['paint_white'], (0, d / 2 + 0.102, h - 0.4), '+Y', extrude=0.004)
    # Inside: a floor, a ceiling, a counter and emptied shelves.
    b.box(M['plaster' if 'plaster' in M else 'cream'], (-w / 2 + t, -d / 2 + t, h - 0.05), (w / 2 - t, d / 2 - t, h))
    b.box(M['grey'], (2.2, -1.0, 0.1), (5.2, -0.3, 1.1))
    for x in (-4.5, -2.5, -0.5):
        b.box(M['grey'], (x - 0.25, -3.0, 0.1), (x + 0.25, 1.8, 1.6))
        for z in (0.5, 0.9, 1.3):
            b.box(M['cream'], (x - 0.45, -3.0, z), (x + 0.45, 1.8, z + 0.03))
    b.box(M['grey'], (w / 2 - 0.5, -d / 2 - 0.1, h + 0.25), (w / 2 + 0.6, -d / 2 + 1.0, h + 1.1))
    del block
    return b.finish(bevel=0.008, bevel_segments=1)


def price_sign():
    b = bl.Builder('station_sign')
    for x in (-0.7, 0.7):
        b.box(M['cream'], (x - 0.1, -0.1, 0.0), (x + 0.1, 0.1, 6.5))
    b.box(M['red'], (-1.3, -0.15, 5.0), (1.3, 0.15, 6.9))
    b.box(M['cream'], (-1.2, -0.16, 3.1), (1.2, 0.16, 4.9))
    for facing, y in (('+Y', 0.151), ('-Y', -0.151)):
        bl.add_text(b, 'CASCADE', 0.42, M['paint_white'], (0, y, 6.25), facing, extrude=0.004)
        bl.add_text(b, 'FUEL', 0.42, M['paint_white'], (0, y, 5.6), facing, extrude=0.004)
        bl.add_text(b, 'NO FUEL', 0.36, M['ink'], (0, y * 1.07, 4.3), facing, extrude=0.004)
        bl.add_text(b, 'BY ORDER', 0.24, M['ink'], (0, y * 1.07, 3.6), facing, extrude=0.004)
    return b.finish(bevel=0.01, bevel_segments=1)


BUILDERS = {}


def register():
    def add(function, *args, **kwargs):
        obj = function(*args, **kwargs)
        BUILDERS[obj.name] = obj
        return obj

    add(fence_wood)
    add(fence_wood, 'fence_wood_broken', broken=True)
    add(fence_gate)
    add(fence_picket)
    add(fence_chain)
    add(fence_chain, wire=False)
    add(wire_coil)
    add(jersey)
    add(sandbags, 'sandbag_wall', 2.4, 7)
    add(sandbags, 'sandbag_low', 2.4, 4)
    add(sandbags, 'sandbag_corner', 2.4, 7, corner=True)
    add(hesco)
    add(guard_booth)
    add(boom_gate)
    add(boom_gate, lowered=False)
    add(watchtower)
    add(floodlight)
    add(generator)
    add(tank_trap)
    add(crate, 'crate_wood', M['plywood'])
    add(crate, 'crate_military', M['olive'], (1.2, 0.6, 0.5), military=True)
    add(crate, 'crate_long', M['olive'], (1.6, 0.45, 0.4), military=True)
    add(ammo_box)
    add(pallet)
    add(drum, 'drum_red', M['red'])
    add(drum, 'drum_blue', M['blue'])
    add(drum, 'drum_rust', M['rust'])
    add(drum, 'drum_fire', M['rust'], holes=True)
    add(street_light)
    add(utility_pole)
    add(wire_span)
    add(sign, 'stop_sign', stop_face)
    add(sign, 'sign_juniper', street_name('JUNIPER CT', 'ALDER ST'), post_height=2.6)
    add(sign, 'sign_mill', street_name('MILL RD', 'ALDER ST'), post_height=2.6)
    add(notice_board, 'notice_curfew', ['CURFEW', '2100 - 0600', 'VIOLATORS WILL', 'BE DETAINED'])
    add(notice_board, 'notice_checkpoint', ['CHECKPOINT', 'HALT - PAPERS', 'ENGINES OFF'], width=1.7)
    add(notice_board, 'notice_order', ['ORDER IS SAFETY', 'REPORT. COMPLY.', 'PROSPER.'], colour='ink', width=1.8)
    add(banner)
    add(flag_pole)
    add(mailbox)
    add(trash_bin)
    add(trash_bin, tipped=True)
    add(dumpster)
    add(hydrant)
    add(cone)
    add(tyres)
    add(rubble, 1)
    add(rubble, 2)
    add(swing_set)
    add(picnic_table)
    add(barbecue)
    add(lawn_chair)
    add(lawn_chair, fallen=True)
    add(woodpile)
    add(washing_line)
    add(workbench)
    add(shelving)
    add(map_table)
    add(bedroll)
    add(boxes)
    add(graffiti, 'graffiti_here', ["WE'RE STILL", 'HERE'])
    add(graffiti, 'graffiti_air', ['DEAD AIR', "CAN'T LAST"], mat='paint_red', size=0.3)
    add(canopy)
    add(pump)
    add(store)
    add(price_sign)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    bl.reset()
    materials()
    M['plaster'] = bl.material('plaster', 'plaster')
    register()
    if '--preview' in args:
        at = args.index('--preview')
        wanted = args[at + 1] if len(args) > at + 1 else 'all'
        names = list(BUILDERS) if wanted == 'all' else wanted.split(',')
        sheets = [names[i:i + 8] for i in range(0, len(names), 8)]
        azimuth = float(args[args.index('--azimuth') + 1]) if '--azimuth' in args else 205.0
        zoom = float(args[args.index('--zoom') + 1]) if '--zoom' in args else 1.9
        for index, sheet in enumerate(sheets):
            shown = [BUILDERS[name] for name in sheet]
            x = 0.0
            for obj in shown:
                half = max(obj.dimensions.x, obj.dimensions.y, 0.8) / 2
                x += half
                obj.location = (x, 0, 0)
                x += half + 0.5
            bpy.context.view_layer.update()
            stem = 'props' if len(sheets) == 1 else f'props_{index}'
            preview.render(os.path.join(bl.ROOT, 'build', 'previews', stem + '.png'), shown, views=[(azimuth, 16)],
                           size=(2000, 760), samples=24, zoom=zoom, ground=True)
            print('sheet', index, ' '.join(sheet))
            for obj in shown:
                obj.location = (0, 0, 0)
            bpy.context.view_layer.update()
        if '--no-export' in args:
            return
    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'props.glb'), list(BUILDERS.values()))
    print('props:', ' '.join(BUILDERS))


main()
