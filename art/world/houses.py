"""The houses of Alder Ridge: ordinary American suburban homes of the 1990s, built from a few
parameters: lap siding on a concrete footing, white trim, shingled gable roofs with proper
eaves, sash windows, a front door under a porch roof, an attached garage.

    blender --background --factory-startup --python art/world/houses.py -- [--preview]

Writes build/kits/houses.glb. Each house is one part, standing on the ground at its own origin
with its street front on its +Y side (which the engine sees as -Z).

Houses are shells: there is nothing inside them, and their windows are dark glass. The garage
of `house_safe` is the exception: it is open, with a room inside, where the game begins.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from mathutils import Matrix, Vector  # noqa: E402

from lib import bl, preview  # noqa: E402

FOOTING = 0.45
STOREY = 2.75
WALL = 0.25


class Palette:
    """The materials of one house."""

    def __init__(self, name, siding, roof, trim=(0.9, 0.9, 0.88), door=(0.35, 0.06, 0.05), brick_footing=False):
        self.siding = bl.material(f'siding_{name}', 'siding', tint=siding)
        self.roof = bl.material(f'shingles_{name}', 'shingles', tint=roof)
        self.trim = bl.material(f'trim_{name}', 'painted_wood', tint=trim)
        self.door = bl.material(f'door_{name}', 'painted_wood', tint=door)
        self.footing = bl.material('brick', 'brick') if brick_footing else bl.material('concrete', 'concrete')
        self.glass = bl.material('glass', 'glass')
        self.concrete = bl.material('concrete', 'concrete')
        self.metal = bl.material('gutter_white', 'painted_metal', tint=(0.86, 0.86, 0.84))
        self.garage = bl.material('garage_door', 'painted_metal', tint=(0.82, 0.8, 0.76))
        self.plaster = bl.material('plaster', 'plaster')
        self.dark = bl.material('dark_steel', 'dark_steel')
        self.plywood = bl.material('plywood', 'plywood')
        self.brick = bl.material('brick', 'brick')


def wall(b, mat, a, bpt, low, high, openings=(), thickness=WALL, inner=None):
    """A wall from point `a` to point `bpt` on the ground plan, from height `low` to `high`,
    with rectangular openings: each (start along the wall, sill height, width, height), in order
    along it and not overlapping. The wall's outside is to the right of the way from a to b...
    which is to say, walk the plan anticlockwise. Returns each opening's outer rectangle as
    (origin, along, up, outward)."""
    a, bpt = Vector((a[0], a[1], 0)), Vector((bpt[0], bpt[1], 0))
    along = (bpt - a).normalized()
    length = (bpt - a).length
    outward = Vector((along.y, -along.x, 0))
    turn = Matrix(((along.x, -outward.x, 0, a.x), (along.y, -outward.y, 0, a.y), (0, 0, 1, 0), (0, 0, 0, 1)))
    # In the wall's own frame: x along it, y from its outer face inward, z up.

    def piece(x0, x1, z0, z1):
        if x1 - x0 > 1e-4 and z1 - z0 > 1e-4:
            b.box(mat, (x0, 0, z0), (x1, thickness, z1), matrix=turn)

    found = []
    cursor = 0.0
    for start, sill, width, height in openings:
        piece(cursor, start, low, high)
        piece(start, start + width, low, sill)
        piece(start, start + width, sill + height, high)
        cursor = start + width
        origin = a + along * start + Vector((0, 0, sill))
        found.append((origin, along * width, Vector((0, 0, height)), outward))
    piece(cursor, length, low, high)
    return found


def window(b, p, rect, depth=0.1, sash=True, boarded=False, shutters=False):
    """Fills an opening with a window: casing proud of the wall, glass set back in it, a sill,
    and the bars of its sashes."""
    origin, across, up, outward = rect
    along = across.normalized()
    width, height = across.length, up.length
    frame = Matrix(((along.x, outward.x, 0, origin.x), (along.y, outward.y, 0, origin.y), (0, 0, 1, origin.z), (0, 0, 0, 1)))
    # In the window's frame: x across it, y outward from the wall's face, z up.
    b.box(p.glass, (0, -depth - 0.01, 0), (width, -depth, height), matrix=frame)
    # Jambs lining the opening, and the casing round it on the wall's face.
    lining = 0.03
    for x0, x1 in ((0, lining), (width - lining, width)):
        b.box(p.trim, (x0, -depth, 0), (x1, 0.0, height), matrix=frame)
    b.box(p.trim, (0, -depth, height - lining), (width, 0.0, height), matrix=frame)
    case = 0.09
    b.box(p.trim, (-case, 0, -0.02), (0, 0.025, height + case), matrix=frame)
    b.box(p.trim, (width, 0, -0.02), (width + case, 0.025, height + case), matrix=frame)
    b.box(p.trim, (-case - 0.02, 0, height), (width + case + 0.02, 0.035, height + case + 0.02), matrix=frame)
    b.box(p.trim, (-case - 0.03, -depth, -0.045), (width + case + 0.03, 0.06, 0.0), matrix=frame)
    if sash:
        bar = 0.035
        b.box(p.trim, (0, -depth, height * 0.5 - bar), (width, -depth + 0.035, height * 0.5 + bar), matrix=frame)
        if width > 1.2:
            for x in (width / 3, 2 * width / 3):
                b.box(p.trim, (x - bar * 0.6, -depth, 0), (x + bar * 0.6, -depth + 0.03, height), matrix=frame)
        else:
            b.box(p.trim, (width * 0.5 - 0.012, -depth, height * 0.5), (width * 0.5 + 0.012, -depth + 0.02, height), matrix=frame)
    if boarded:
        b.box(p.plywood, (-0.05, 0.03, -0.03), (width + 0.05, 0.045, height + 0.06), matrix=frame)
        for z in (height * 0.25, height * 0.75):
            b.box(p.plywood, (-0.12, 0.045, z - 0.05), (width + 0.12, 0.065, z + 0.05), matrix=frame)
    if shutters:
        for x0 in (-case - 0.36, width + case + 0.02):
            b.box(p.door, (x0, 0, 0), (x0 + 0.34, 0.03, height), matrix=frame)
            for i in range(7):
                z = 0.06 + i * (height - 0.12) / 7
                b.box(p.door, (x0 + 0.03, 0.03, z), (x0 + 0.31, 0.04, z + 0.05), matrix=frame)


def door(b, p, rect, depth=0.12, mat=None, glazed=False):
    """A panelled front door in its frame, with its handle and a threshold."""
    origin, across, up, outward = rect
    along = across.normalized()
    width, height = across.length, up.length
    mat = mat or p.door
    frame = Matrix(((along.x, outward.x, 0, origin.x), (along.y, outward.y, 0, origin.y), (0, 0, 1, origin.z), (0, 0, 0, 1)))
    b.box(mat, (0.04, -depth - 0.045, 0.02), (width - 0.04, -depth, height - 0.04), matrix=frame)
    # Raised panels: two tall over two short, or glass above.
    inset = 0.14
    middle = width * 0.5
    for x0, x1 in ((inset, middle - 0.04), (middle + 0.04, width - inset)):
        b.box(mat, (x0, -depth, 0.2), (x1, -depth + 0.012, 0.85), matrix=frame)
        if glazed:
            b.box(p.glass, (x0, -depth, 1.05), (x1, -depth + 0.006, height - 0.22), matrix=frame)
        else:
            b.box(mat, (x0, -depth, 1.0), (x1, -depth + 0.012, height - 0.22), matrix=frame)
    b.cylinder(p.dark, 0.028, 0.05, centre=(width - 0.11, -depth + 0.03, 1.0), axis='Y', segments=14, matrix=frame)
    case = 0.1
    for x0, x1 in ((0, 0.04), (width - 0.04, width)):
        b.box(p.trim, (x0, -depth - 0.03, 0), (x1, 0.0, height), matrix=frame)
    b.box(p.trim, (0, -depth - 0.03, height - 0.04), (width, 0.0, height), matrix=frame)
    b.box(p.trim, (-case, 0, 0), (0, 0.03, height + case), matrix=frame)
    b.box(p.trim, (width, 0, 0), (width + case, 0.03, height + case), matrix=frame)
    b.box(p.trim, (-case - 0.02, 0, height), (width + case + 0.02, 0.04, height + case + 0.02), matrix=frame)
    b.box(p.concrete, (-0.05, -depth, -0.03), (width + 0.05, 0.08, 0.02), matrix=frame)


def garage_door(b, p, rect, depth=0.15, open_share=0.0):
    """A sectional garage door: four ribbed sections in a cased opening. `open_share` raises
    it: at 1 it is out of sight."""
    origin, across, up, outward = rect
    along = across.normalized()
    width, height = across.length, up.length
    frame = Matrix(((along.x, outward.x, 0, origin.x), (along.y, outward.y, 0, origin.y), (0, 0, 1, origin.z), (0, 0, 0, 1)))
    shown = height * (1.0 - open_share)
    sections = 4
    for i in range(sections):
        z0 = height - shown + i * height / sections
        z1 = z0 + height / sections - 0.012
        if z1 > height:
            z1 = height
        if z0 >= height - 1e-3:
            continue
        b.box(p.garage, (0.02, -depth - 0.04, z0), (width - 0.02, -depth, z1), matrix=frame)
        cells = 4
        for c in range(cells):
            x0 = 0.12 + c * (width - 0.16) / cells
            x1 = x0 + (width - 0.16) / cells - 0.1
            if z1 - z0 > 0.2:
                b.box(p.garage, (x0, -depth, z0 + 0.08), (x1, -depth + 0.012, z1 - 0.08), matrix=frame)
    case = 0.12
    b.box(p.trim, (-case, 0, 0), (0, 0.03, height + case), matrix=frame)
    b.box(p.trim, (width, 0, 0), (width + case, 0.03, height + case), matrix=frame)
    b.box(p.trim, (-case, 0, height), (width + case, 0.04, height + case), matrix=frame)
    for x0, x1 in ((0, 0.02), (width - 0.02, width)):
        b.box(p.trim, (x0, -depth - 0.04, 0), (x1, 0, height), matrix=frame)
    b.box(p.trim, (0, -depth - 0.04, height - 0.02), (width, 0, height), matrix=frame)


def gable_roof(b, p, x0, x1, y0, y1, eave, pitch, ridge_along='X', overhang=0.45, rake=0.3):
    """A gable roof over a rectangle: two shingled slopes with eaves and rakes, fascia boards,
    and the triangles of wall under each end. Returns the ridge's height."""
    slope = math.tan(math.radians(pitch))
    if ridge_along == 'X':
        span, length = (y1 - y0), (x1 - x0)
    else:
        span, length = (x1 - x0), (y1 - y0)
    rise = span * 0.5 * slope
    thick = 0.16
    drop = overhang * slope
    # One slope in a frame where u runs along the ridge, v out from the ridge, w up.
    section = [(0.0, rise), (span * 0.5 + overhang, -drop), (span * 0.5 + overhang, -drop - 0.19),
               (span * 0.5 + overhang - 0.03, -drop - 0.19), (0.0, rise - thick * math.sqrt(1 + slope * slope))]

    def frame(side):
        if ridge_along == 'X':
            cy = (y0 + y1) * 0.5
            return Matrix(((1, 0, 0, x0 - rake), (0, side, 0, cy), (0, 0, 1, eave), (0, 0, 0, 1)))
        cx = (x0 + x1) * 0.5
        return Matrix(((0, side, 0, cx), (1, 0, 0, y0 - rake), (0, 0, 1, eave), (0, 0, 0, 1)))

    for side in (-1, 1):
        faces = b.prism(p.roof, [(v, w) for v, w in section], length + 2 * rake, axis='X', matrix=frame(side))
        # Only the top carries shingles, which is the first face made: the edges and the
        # underside are painted boards.
        trim_index = b._index(p.trim)
        for face in faces[1:]:
            face.material_index = trim_index
    # The ridge cap.
    cap = [(-0.14, rise - 0.03), (0.0, rise + 0.035), (0.14, rise - 0.03)]
    if ridge_along == 'X':
        b.prism(p.roof, cap, length + 2 * rake, axis='X', offset=x0 - rake,
                matrix=Matrix.Translation((0, (y0 + y1) * 0.5, eave)))
    else:
        b.prism(p.roof, cap, length + 2 * rake, axis='Y', offset=y0 - rake,
                matrix=Matrix.Translation(((x0 + x1) * 0.5, 0, eave)))
    # Gable ends: the triangle of siding under each rake, with a vent.
    for end in (0, 1):
        if ridge_along == 'X':
            x = x0 if end == 0 else x1 - WALL
            b.prism(p.siding, [(y0, eave), (y1, eave), ((y0 + y1) * 0.5, eave + rise)], WALL, axis='X', offset=x)
            vx = x0 - 0.02 if end == 0 else x1
            b.box(p.trim, (vx, (y0 + y1) * 0.5 - 0.28, eave + rise * 0.42), (vx + 0.02, (y0 + y1) * 0.5 + 0.28, eave + rise * 0.42 + 0.5))
        else:
            y = y0 if end == 0 else y1 - WALL
            b.prism(p.siding, [(x0, eave), (x1, eave), ((x0 + x1) * 0.5, eave + rise)], WALL, axis='Y', offset=y)
            vy = y0 - 0.02 if end == 0 else y1
            b.box(p.trim, ((x0 + x1) * 0.5 - 0.28, vy, eave + rise * 0.42), ((x0 + x1) * 0.5 + 0.28, vy + 0.02, eave + rise * 0.42 + 0.5))
    # Gutters along both eaves, and a downpipe at one end of each.
    for side in (-1, 1):
        if ridge_along == 'X':
            y = (y0 + y1) * 0.5 + side * (span * 0.5 + overhang + 0.05)
            b.box(p.metal, (x0 - rake, y - 0.06, eave - drop - 0.14), (x1 + rake, y + 0.06, eave - drop - 0.04))
            px = x1 - 0.1 if side > 0 else x0 + 0.1
            wall_y = (y0 + y1) * 0.5 + side * (span * 0.5 + 0.05)
            b.tube(p.metal, [(px, y, eave - drop - 0.1), (px, wall_y, eave - drop - 0.45), (px, wall_y, 0.25),
                             (px, wall_y + side * 0.2, 0.1)], 0.04, segments=8)
        else:
            x = (x0 + x1) * 0.5 + side * (span * 0.5 + overhang + 0.05)
            b.box(p.metal, (x - 0.06, y0 - rake, eave - drop - 0.14), (x + 0.06, y1 + rake, eave - drop - 0.04))
            py = y1 - 0.1 if side > 0 else y0 + 0.1
            wall_x = (x0 + x1) * 0.5 + side * (span * 0.5 + 0.05)
            b.tube(p.metal, [(x, py, eave - drop - 0.1), (wall_x, py, eave - drop - 0.45), (wall_x, py, 0.25),
                             (wall_x + side * 0.2, py, 0.1)], 0.04, segments=8)
    return eave + rise


def block(b, p, x0, x1, y0, y1, storeys, fronts, corner_boards=True, base=0.0):
    """The walls of one rectangular part of a house, with its footing and corner boards.
    `fronts` gives each side's openings by storey: {'S': [[...ground], [...upper]], ...} with
    sides N (the +Y street front), S, E (+X) and W. Returns the openings of each side, as
    `window` and `door` take them, and the height of the eaves."""
    top = FOOTING + STOREY * storeys
    b.box(p.footing, (x0 - 0.03, y0 - 0.03, base - 0.3), (x1 + 0.03, y1 + 0.03, FOOTING))
    # Walked anticlockwise seen from above, the outside is on the right.
    sides = {'S': ((x0, y0), (x1, y0)), 'E': ((x1, y0), (x1, y1)), 'N': ((x1, y1), (x0, y1)), 'W': ((x0, y1), (x0, y0))}
    found = {}
    for name, (a, c) in sides.items():
        per_storey = fronts.get(name, [])
        found[name] = []
        for storey in range(storeys):
            low = FOOTING + STOREY * storey
            openings = sorted(per_storey[storey] if storey < len(per_storey) else [])
            placed = [(start, low + sill, width, height) for start, sill, width, height in openings]
            found[name].append(wall(b, p.siding, a, c, low, low + STOREY, placed))
    if corner_boards:
        # A board up each face at every corner, standing a little proud of the siding.
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            sx = -1 if x == x0 else 1
            sy = -1 if y == y0 else 1
            xs = sorted((x, x + sx * 0.014))
            ys = sorted((y + sy * 0.014, y - sy * 0.11))
            b.box(p.trim, (xs[0], ys[0], FOOTING), (xs[1], ys[1], top))
            xs = sorted((x + sx * 0.014, x - sx * 0.11))
            ys = sorted((y, y + sy * 0.014))
            b.box(p.trim, (xs[0], ys[0], FOOTING), (xs[1], ys[1], top))
    # A frieze under the eaves, and a band board where the storeys meet.
    b.box(p.trim, (x0 - 0.014, y0 - 0.014, top - 0.2), (x1 + 0.014, y1 + 0.014, top))
    if storeys > 1:
        b.box(p.trim, (x0 - 0.012, y0 - 0.012, FOOTING + STOREY - 0.09), (x1 + 0.012, y1 + 0.012, FOOTING + STOREY + 0.09))
    return found, top


def stoop(b, p, x, y, width, depth, steps=3):
    """Concrete steps up to a door, rising to the footing's height. `y` is the wall's face;
    they run out along +Y."""
    rise = FOOTING / steps
    b.box(p.concrete, (x - width / 2, y, -0.2), (x + width / 2, y + depth, FOOTING - 0.02))
    for i in range(steps - 1):
        z = FOOTING - 0.02 - rise * (i + 1)
        b.box(p.concrete, (x - width / 2, y + depth + i * 0.3, -0.2), (x + width / 2, y + depth + (i + 1) * 0.3, z))


def porch_roof(b, p, x0, x1, y, depth, height, posts=2):
    """A lean-to roof over a porch, on square posts."""
    b.prism(p.roof, [(y - 0.02, height + 0.55), (y + depth + 0.25, height), (y + depth + 0.25, height - 0.12), (y - 0.02, height + 0.43)],
            x1 - x0 + 0.4, axis='X', offset=x0 - 0.2)
    b.box(p.trim, (x0 - 0.1, y + depth - 0.12, height - 0.3), (x1 + 0.1, y + depth + 0.02, height - 0.1))
    for i in range(posts):
        x = x0 + 0.08 + i * (x1 - x0 - 0.16) / max(posts - 1, 1)
        b.box(p.trim, (x - 0.07, y + depth - 0.12, FOOTING - 0.02), (x + 0.07, y + depth + 0.02, height - 0.1))
        b.box(p.trim, (x - 0.1, y + depth - 0.15, FOOTING - 0.02), (x + 0.1, y + depth + 0.05, FOOTING + 0.12))
        b.box(p.trim, (x - 0.1, y + depth - 0.15, height - 0.42), (x + 0.1, y + depth + 0.05, height - 0.3))


def chimney(b, p, x, y, base, top, width=0.75, depth=0.6):
    b.box(p.brick, (x - width / 2, y - depth / 2, base), (x + width / 2, y + depth / 2, top))
    b.box(p.concrete, (x - width / 2 - 0.05, y - depth / 2 - 0.05, top), (x + width / 2 + 0.05, y + depth / 2 + 0.05, top + 0.08))
    b.box(p.dark, (x - 0.14, y - 0.14, top + 0.08), (x + 0.14, y + 0.14, top + 0.28))


def condenser(b, p, x, y):
    """An air conditioner's outdoor unit, on its pad."""
    b.box(p.concrete, (x - 0.5, y - 0.5, 0.0), (x + 0.5, y + 0.5, 0.08))
    b.box(p.metal, (x - 0.4, y - 0.4, 0.08), (x + 0.4, y + 0.4, 0.82))
    for i in range(9):
        z = 0.16 + i * 0.07
        b.box(p.dark, (x - 0.41, y - 0.36, z), (x + 0.41, y + 0.36, z + 0.03))
    b.cylinder(p.dark, 0.3, 0.02, centre=(x, y, 0.83), segments=24)


def two_storey(name, palette, mirror=False, boarded=(), safe=False):
    """A two-storey house, 9.6 m wide, with a garage on its east side and a porch at the front
    door."""
    p = palette
    b = bl.Builder(name)
    w, d = 9.6, 8.2
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    win = (0.95, 1.45)
    fronts = {
        # The street front: living-room window, door, window; three windows above.
        'N': [[(1.0, 0.75, 1.9, 1.5), (4.3, 0.0, 1.0, 2.1), (6.6, 0.85, *win)],
              [(1.2, 0.85, *win), (4.3, 0.85, *win), (7.3, 0.85, *win)]],
        'S': [[(0.9, 0.85, *win), (3.4, 0.0, 1.8, 2.1), (6.9, 1.2, 0.9, 1.0)],
              [(1.2, 0.85, *win), (4.4, 1.25, 0.65, 0.8), (7.0, 0.85, *win)]],
        'W': [[(1.4, 0.85, *win), (5.4, 0.85, *win)], [(1.4, 0.85, *win), (5.4, 0.85, *win)]],
        'E': [[], [(2.2, 0.85, *win)]],
    }
    found, eave = block(b, p, x0, x1, y0, y1, 2, fronts)
    count = 0
    for side, storeys in found.items():
        for storey, rects in enumerate(storeys):
            for rect in rects:
                if rect[2].length > 2.0 and rect[1].length < 1.2 and side == 'N':
                    door(b, p, rect)
                elif rect[2].length > 2.0:
                    # Sliding patio doors at the back.
                    window(b, p, rect, sash=False)
                else:
                    window(b, p, rect, boarded=count in boarded, shutters=(side == 'N'))
                count += 1
    ridge = gable_roof(b, p, x0, x1, y0, y1, eave, 30, ridge_along='X')
    chimney(b, p, x0 + 1.4, -0.6, eave, ridge + 0.6)
    # The porch: steps up to the door, under a roof on two posts.
    door_x = x1 - 4.3 - 0.5
    stoop(b, p, door_x, y1, 2.6, 1.5)
    porch_roof(b, p, door_x - 1.3, door_x + 1.3, y1, 1.5, FOOTING + 2.45)
    b.box(p.dark, (door_x + 0.75, y1, FOOTING + 1.75), (door_x + 0.87, y1 + 0.1, FOOTING + 2.0))
    condenser(b, p, x0 - 0.9, y0 + 1.5)

    # The garage: one storey, its own gable to the street.
    gw, gd = 6.4, 6.8
    gx0, gx1, gy0, gy1 = x1, x1 + gw, y1 - gd - 0.6, y1 - 0.6
    garage_fronts = {'N': [[(0.75, 0.0, 4.9, 2.15)]], 'E': [[(2.6, 0.95, *win)]],
                     'S': [[(4.6, 0.0, 0.95, 2.05)]] if safe else [[]]}
    # The garage stands on a slab at ground level, not on the house's footing.
    saved = globals()['FOOTING']
    globals()['FOOTING'] = 0.12
    gfound, geave = block(b, p, gx0, gx1, gy0, gy1, 1, garage_fronts)
    garage_door(b, p, gfound['N'][0][0], open_share=0.0 if not safe else 0.0)
    window(b, p, gfound['E'][0][0], boarded=safe)
    if safe:
        # The back door stands open: the way out to the yards. Inside, a floor and lined walls.
        origin, across, up, outward = gfound['S'][0][0]
        b.box(p.trim, (origin.x - 0.1, origin.y - 0.03, origin.z), (origin.x, origin.y, origin.z + 2.15))
        b.box(p.trim, (origin.x + 0.95, origin.y - 0.03, origin.z), (origin.x + 1.05, origin.y, origin.z + 2.15))
        b.box(p.trim, (origin.x - 0.1, origin.y - 0.03, origin.z + 2.05), (origin.x + 1.05, origin.y, origin.z + 2.15))
        b.box(p.door, (origin.x + 0.93, origin.y - 0.92, origin.z + 0.02), (origin.x + 0.975, origin.y - 0.02, origin.z + 2.03))
        b.box(p.concrete, (gx0 + WALL, gy0 + WALL, 0.0), (gx1 - WALL, gy1 - WALL, 0.12))
        b.box(p.plaster, (gx0 + WALL, gy0 + WALL, 0.12 + STOREY - 0.05), (gx1 - WALL, gy1 - WALL, 0.12 + STOREY + 0.08))
    globals()['FOOTING'] = saved
    gable_roof(b, p, gx0, gx1, gy0, gy1, geave, 28, ridge_along='Y')
    # The driveway's apron.
    b.box(p.concrete, (gx0 + 0.6, gy1, -0.2), (gx1 - 0.6, gy1 + 0.6, 0.11))
    obj = b.finish(bevel=0.006, bevel_segments=1)
    if mirror:
        bl.transform_mesh(obj, Matrix.Scale(-1, 4, (1, 0, 0)))
    return obj


def ranch(name, palette, boarded=()):
    """A long single-storey house with a low roof and a garage in its west end."""
    p = palette
    b = bl.Builder(name)
    w, d = 16.0, 8.4
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    win = (1.2, 1.3)
    fronts = {
        'N': [[(1.3, 0.9, *win), (4.2, 0.75, 2.2, 1.45), (7.6, 0.0, 1.0, 2.1), (10.3, 0.0, 4.9, 2.15)]],
        'S': [[(1.4, 0.9, *win), (5.0, 0.0, 1.8, 2.1), (8.4, 0.9, *win), (12.6, 0.9, *win)]],
        'W': [[(3.0, 0.9, *win)]],
        'E': [[(2.0, 0.9, *win), (5.2, 1.2, 0.7, 0.8)]],
    }
    found, eave = block(b, p, x0, x1, y0, y1, 1, fronts)
    count = 0
    for side, storeys in found.items():
        for rect in storeys[0]:
            width, height = rect[1].length, rect[2].length
            if width > 4.0:
                garage_door(b, p, rect)
            elif height > 2.0 and width < 1.2:
                door(b, p, rect, glazed=True)
            elif height > 2.0:
                window(b, p, rect, sash=False)
            else:
                window(b, p, rect, boarded=count in boarded, shutters=(side == 'N' and width < 1.5))
            count += 1
    ridge = gable_roof(b, p, x0, x1, y0, y1, eave, 23, ridge_along='X', overhang=0.6)
    chimney(b, p, x1 - 2.2, 0.8, eave, ridge + 0.5)
    door_x = x1 - 7.6 - 0.5
    stoop(b, p, door_x, y1, 2.4, 1.3)
    porch_roof(b, p, door_x - 2.6, door_x + 1.4, y1, 1.3, FOOTING + 2.3, posts=3)
    condenser(b, p, x1 + 0.9, y0 + 2.0)
    b.box(p.concrete, (x0 + 0.5, y1, -0.2), (x0 + 5.6, y1 + 0.6, FOOTING - 0.02))
    return b.finish(bevel=0.006, bevel_segments=1)


def cottage(name, palette, boarded=()):
    """A narrow two-storey house with its gable to the street and a porch right across it."""
    p = palette
    b = bl.Builder(name)
    w, d = 7.6, 10.0
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    win = (0.95, 1.5)
    fronts = {
        'N': [[(1.0, 0.0, 1.0, 2.1), (3.4, 0.8, 1.9, 1.5)], [(1.3, 0.85, *win), (5.3, 0.85, *win)]],
        'S': [[(1.2, 0.85, *win), (4.6, 0.0, 0.95, 2.05)], [(3.3, 0.85, *win)]],
        'W': [[(1.5, 0.85, *win), (5.0, 0.85, *win), (8.0, 1.2, 0.7, 0.8)], [(1.5, 0.85, *win), (6.0, 0.85, *win)]],
        'E': [[(2.0, 0.85, *win), (6.5, 0.85, *win)], [(2.0, 0.85, *win), (6.5, 0.85, *win)]],
    }
    found, eave = block(b, p, x0, x1, y0, y1, 2, fronts)
    count = 0
    for side, storeys in found.items():
        for rects in storeys:
            for rect in rects:
                if rect[2].length > 2.0:
                    door(b, p, rect, glazed=(side == 'S'))
                else:
                    window(b, p, rect, boarded=count in boarded)
                count += 1
    ridge = gable_roof(b, p, x0, x1, y0, y1, eave, 36, ridge_along='Y')
    chimney(b, p, x0 + 0.9, -1.5, eave, ridge + 0.4)
    # The porch: a deck right across the front, with a rail.
    depth = 2.0
    b.box(p.concrete, (x0, y1, -0.2), (x1, y1 + depth, FOOTING - 0.02))
    stoop(b, p, x1 - 1.5, y1 + depth - 1.2, 1.6, 1.2)
    porch_roof(b, p, x0, x1, y1, depth, FOOTING + 2.5, posts=4)
    for xa, xb in ((x0 + 0.1, x1 - 2.4),):
        b.box(p.trim, (xa, y1 + depth - 0.1, FOOTING + 0.85), (xb, y1 + depth - 0.03, FOOTING + 0.93))
        b.box(p.trim, (xa, y1 + depth - 0.1, FOOTING + 0.1), (xb, y1 + depth - 0.03, FOOTING + 0.16))
        n = int((xb - xa) / 0.13)
        for i in range(n + 1):
            x = xa + i * (xb - xa) / n
            b.box(p.trim, (x - 0.018, y1 + depth - 0.085, FOOTING + 0.16), (x + 0.018, y1 + depth - 0.045, FOOTING + 0.85))
    condenser(b, p, x1 + 0.9, y0 + 2.5)
    return b.finish(bevel=0.006, bevel_segments=1)


def shed(name, palette):
    """A garden shed."""
    p = palette
    b = bl.Builder(name)
    saved = globals()['FOOTING']
    globals()['FOOTING'] = 0.1
    found, eave = block(b, p, -1.5, 1.5, -1.2, 1.2, 1, {'N': [[(0.9, 0.0, 1.2, 1.9)]], 'E': [[(0.8, 1.1, 0.7, 0.6)]]})
    door(b, p, found['N'][0][0], depth=0.06, mat=p.trim)
    window(b, p, found['E'][0][0], sash=False)
    globals()['FOOTING'] = saved
    gable_roof(b, p, -1.5, 1.5, -1.2, 1.2, eave - 0.55, 28, ridge_along='X', overhang=0.2, rake=0.15)
    return b.finish(bevel=0.005, bevel_segments=1)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    bl.reset()
    palettes = {
        'blue': Palette('blue', (0.36, 0.47, 0.56), (0.5, 0.5, 0.52), door=(0.42, 0.07, 0.05)),
        'cream': Palette('cream', (0.82, 0.76, 0.6), (0.62, 0.5, 0.42), door=(0.1, 0.2, 0.14), brick_footing=True),
        'green': Palette('green', (0.4, 0.47, 0.36), (0.42, 0.42, 0.44), door=(0.5, 0.36, 0.12)),
        'grey': Palette('grey', (0.6, 0.61, 0.62), (0.34, 0.34, 0.36), door=(0.1, 0.14, 0.3)),
        'white': Palette('white', (0.92, 0.92, 0.9), (0.52, 0.42, 0.38), door=(0.12, 0.12, 0.13), brick_footing=True),
        'tan': Palette('tan', (0.66, 0.56, 0.44), (0.45, 0.4, 0.36), door=(0.28, 0.1, 0.06)),
        'red': Palette('red', (0.5, 0.16, 0.13), (0.3, 0.3, 0.31), trim=(0.88, 0.86, 0.8), door=(0.9, 0.88, 0.82)),
    }
    made = [
        two_storey('house_a_blue', palettes['blue']),
        two_storey('house_a_cream', palettes['cream'], mirror=True, boarded=(0, 2, 5)),
        two_storey('house_a_grey', palettes['grey'], boarded=(1,)),
        two_storey('house_safe', palettes['tan'], safe=True, boarded=(0, 2, 3, 4, 5)),
        ranch('house_b_green', palettes['green']),
        ranch('house_b_white', palettes['white'], boarded=(0, 1, 6)),
        ranch('house_b_tan', palettes['tan']),
        cottage('house_c_white', palettes['white']),
        cottage('house_c_red', palettes['red'], boarded=(1, 2)),
        cottage('house_c_blue', palettes['blue'], boarded=(4,)),
        shed('shed_green', palettes['green']),
        shed('shed_red', palettes['red']),
    ]
    if '--preview' in args:
        shown = [made[1], made[4], made[8]]
        for index, obj in enumerate(shown):
            obj.location = (index * 24 - 24, 0, 0)
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'houses.png'), shown,
                       views=[(20, 14), (200, 16)], size=(2000, 760), samples=32, zoom=1.5, ground=True)
        for obj in made:
            obj.location = (0, 0, 0)
    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'houses.glb'), made)


main()
