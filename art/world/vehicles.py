"""The vehicles of Alder Ridge: what its people left at the kerb, and what the Directorate
drove in with.

    blender --background --factory-startup --python art/world/vehicles.py --
        [--only NAME,NAME] [--preview] [--no-export]

Writes build/kits/vehicles.glb. Each vehicle is one part standing on its wheels at its own
origin, nose toward +Y (which the engine sees as -Z).

Cars are skinned over a few cross-sections and subdivided into a smooth shell; their glass,
lamps and shut lines are then cut into that shell as regions seen from the side, the front or
above. The Directorate's trucks are flat plate, built from boxes.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from lib import bl, preview  # noqa: E402

M = {}
BUILT = {}


def materials():
    paint = lambda name, tint: bl.material('car_' + name, 'car_paint', tint=tint)  # noqa: E731
    M.update(
        blue=paint('blue', (0.09, 0.15, 0.27)),
        white=paint('white', (0.72, 0.72, 0.7)),
        maroon=paint('maroon', (0.3, 0.045, 0.05)),
        silver=paint('silver', (0.5, 0.52, 0.54)),
        black_paint=paint('black', (0.035, 0.035, 0.04)),
        tan=paint('tan', (0.5, 0.42, 0.3)),
        green=paint('green', (0.08, 0.2, 0.13)),
        red=paint('red', (0.5, 0.06, 0.04)),
        glass=bl.material('car_glass', flat=((0.016, 0.02, 0.022), 0.07, 0.0)),
        rubber=bl.material('rubber', 'rubber'),
        trim=bl.material('plastic_black', 'plastic', tint=(0.03, 0.03, 0.03)),
        rim=bl.material('bare_metal', 'bare_metal'),
        dark=bl.material('dark_steel', 'dark_steel'),
        burnt=bl.material('burnt_metal', 'burnt_metal'),
        rust=bl.material('rusty_metal', 'rusty_metal'),
        soot=bl.material('soot', flat=((0.012, 0.011, 0.01), 0.95, 0.0)),
        lens=bl.material('lens_clear', flat=((0.78, 0.8, 0.82), 0.1, 0.35)),
        lens_red=bl.material('lens_red', flat=((0.3, 0.012, 0.01), 0.16, 0.0)),
        lens_amber=bl.material('lens_amber', flat=((0.75, 0.3, 0.02), 0.16, 0.0)),
        plate=bl.material('paint_white', flat=((0.85, 0.85, 0.82), 0.6, 0.0)),
        ink=bl.material('ink', flat=((0.02, 0.02, 0.02), 0.8, 0.0)),
        mark=bl.material('paint_white', flat=((0.85, 0.85, 0.82), 0.6, 0.0)),
        stripe=bl.material('paint_flat_red', flat=((0.55, 0.04, 0.03), 0.6, 0.0)),
        army=bl.material('paint_directorate', 'painted_metal', tint=(0.2, 0.225, 0.22)),
        army_dark=bl.material('paint_directorate_dark', 'painted_metal', tint=(0.09, 0.1, 0.1)),
        canvas=bl.material('canvas_grey', 'canvas', tint=(0.21, 0.23, 0.22)),
        beacon=bl.material('lamp_red', flat=((1.0, 0.1, 0.05), 0.3, 0.0), emissive=(1.0, 0.08, 0.04)),
        lamp=bl.material('lamp_white', flat=((1.0, 0.96, 0.86), 0.3, 0.0), emissive=(1.0, 0.93, 0.78)),
    )


def look_of(paint):
    """What each part of a vehicle is made of, for a vehicle of one colour."""
    return dict(paint=M[paint], glass=M['glass'], trim=M['trim'], rubber=M['rubber'], rim=M['rim'],
                dark=M['dark'], lens=M['lens'], lens_red=M['lens_red'], lens_amber=M['lens_amber'],
                plate=M['plate'], ink=M['ink'], under=M['trim'], burnt=False)


def burnt_look():
    """After the fire: nothing left but steel."""
    b, s = M['burnt'], M['soot']
    return dict(paint=b, glass=s, trim=s, rubber=s, rim=b, dark=s, lens=s, lens_red=s, lens_amber=s,
                plate=b, ink=b, under=s, burnt=True)


# ---------------------------------------------------------------------------------------------
# Shells
# ---------------------------------------------------------------------------------------------

def sect(y, top, roof_x, roof_z, belt_x, belt_z, wide, wide_z=0.62, sill_z=0.30, floor_z=0.20,
         tuck=0.1):
    """One cross-section of a body at `y`, as half an outline from the middle of the top to
    the middle of the floor: the top at `top`, the edge of the roof or bonnet, the belt line
    under the glass, the widest point, the sill, the floor."""
    return (y, [(0.0, top), (roof_x * 0.55, top - (top - roof_z) * 0.15), (roof_x, roof_z),
                (belt_x, belt_z), (wide, wide_z), (wide - 0.012, sill_z), (wide - tuck, floor_z),
                (0.0, floor_z)])


def loft(name, stations, material, levels=2, creases=None, end_crease=0.0, ring_creases=None):
    """Skins the cross-sections into a closed shell, mirrored about X, and subdivides it
    smooth. `creases` sharpens the edges running the length of the body along a row of the
    outline."""
    bm = bmesh.new()
    rings = []
    for y, half in stations:
        ring = [bm.verts.new((x, y, z)) for x, z in half]
        ring += [bm.verts.new((-x, y, z)) for x, z in reversed(half[1:-1])]
        rings.append(ring)
    count = len(rings[0])
    rows = len(stations[0][1])
    for a, b in zip(rings, rings[1:]):
        for i in range(count):
            j = (i + 1) % count
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    layer = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    for row, sharp in (creases or {}).items():
        both = {row, count - row} if 0 < row < rows - 1 else {row}
        for a, b in zip(rings, rings[1:]):
            for r in both:
                edge = bm.edges.get((a[r], b[r]))
                if edge is not None:
                    edge[layer] = sharp
    for station, sharp in (ring_creases or {}).items():
        ring = rings[station]
        for i in range(count):
            edge = bm.edges.get((ring[i], ring[(i + 1) % count]))
            if edge is not None:
                edge[layer] = sharp
    if end_crease:
        for ring in (rings[0], rings[-1]):
            for i in range(count):
                edge = bm.edges.get((ring[i], ring[(i + 1) % count]))
                if edge is not None:
                    edge[layer] = end_crease
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bl.link(obj)
    bl.subdivide(obj, levels)
    return obj


def carve(obj, build, material):
    """Cuts a shape out of a shell; the cut faces take `material`."""
    b = bl.Builder('cutter')
    build(b, material)
    cutter = b.finish(uv=False)
    modifier = obj.modifiers.new('carve', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.object = cutter
    modifier.solver = 'EXACT'
    # The cutter's pieces overlap: the solver must be told, or it guesses.
    modifier.use_self = True
    if hasattr(modifier, 'material_mode'):
        modifier.material_mode = 'TRANSFER'
    bl.apply_modifiers(obj)
    mesh = cutter.data
    bpy.data.objects.remove(cutter)
    bpy.data.meshes.remove(mesh)


def _flat(point, axis):
    if axis == 'X':
        return (point.y, point.z)
    if axis == 'Y':
        return (point.x, point.z)
    return (point.x, point.y)


def _lift(u, v, axis):
    if axis == 'X':
        return Vector((0.0, u, v))
    if axis == 'Y':
        return Vector((u, 0.0, v))
    return Vector((u, v, 0.0))


def paint(obj, material, polygon, axis, keep, frame=None, frame_width=0.014, sink=0.0):
    """Gives `material` to the part of a shell inside a convex `polygon` as seen along `axis`,
    among the faces `keep(centre, normal)` lets through: the shell is cut along the polygon's
    edges so that its outline is exact. With `frame`, a border of that material is left round
    the edge, and `sink` sets the region back a little into the shell."""
    polygon = [tuple(p) for p in polygon]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
    if area < 0:
        polygon.reverse()
    lo = (min(p[0] for p in polygon) - 0.25, min(p[1] for p in polygon) - 0.25)
    hi = (max(p[0] for p in polygon) + 0.25, max(p[1] for p in polygon) + 0.25)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    index = bl.slot(obj, material)

    def near():
        found = []
        for face in bm.faces:
            centre = face.calc_center_median()
            u, v = _flat(centre, axis)
            if lo[0] <= u <= hi[0] and lo[1] <= v <= hi[1] and keep(centre, face.normal):
                found.append(face)
        return found

    edges = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-9:
            continue
        inward = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
        edges.append((a, inward))
        faces = near()
        geometry = list({v for f in faces for v in f.verts} | {e for f in faces for e in f.edges}) + faces
        if geometry:
            bmesh.ops.bisect_plane(bm, geom=geometry, dist=1e-6, plane_co=_lift(a[0], a[1], axis),
                                   plane_no=_lift(inward[0], inward[1], axis))
    bm.normal_update()
    inside = []
    for face in near():
        u, v = _flat(face.calc_center_median(), axis)
        if all((u - a[0]) * n[0] + (v - a[1]) * n[1] >= -1e-6 for a, n in edges):
            inside.append(face)
            face.material_index = index
    if inside and frame is not None:
        rim = bmesh.ops.inset_region(bm, faces=inside, thickness=frame_width, depth=-sink,
                                     use_even_offset=True, use_boundary=True)
        frame_index = bl.slot(obj, frame)
        for face in rim['faces']:
            face.material_index = frame_index
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(inside)


def paint_where(obj, material, test):
    """Gives `material` to every face `test(centre, normal)` picks."""
    index = bl.slot(obj, material)
    mesh = obj.data
    for polygon in mesh.polygons:
        if test(polygon.center, polygon.normal):
            polygon.material_index = index


def cube_uv(obj):
    """World-scale UVs for a curved shell: each face is projected along whichever axis it most
    faces, so that a tiling texture runs unbroken over the curve of a panel."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name='UVMap')
    uv_layer = mesh.uv_layers.active.data
    for polygon in mesh.polygons:
        mat = mesh.materials[polygon.material_index] if mesh.materials else None
        size = mat.get('tile_metres', 1.0) if mat else 1.0
        n = polygon.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for loop_index in polygon.loop_indices:
            p = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if az >= ax and az >= ay:
                uv = (p.x, p.y if n.z > 0 else -p.y)
            elif ax >= ay:
                uv = (p.y if n.x > 0 else -p.y, p.z)
            else:
                uv = (-p.x if n.y > 0 else p.x, p.z)
            uv_layer[loop_index].uv = (uv[0] / size, uv[1] / size)


class Probe:
    """Finds where the shell's surface is, to stand things on it."""

    def __init__(self, obj):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        self.tree = BVHTree.FromBMesh(bm)
        self.bm = bm

    def hit(self, origin, direction):
        location, normal, _, _ = self.tree.ray_cast(Vector(origin), Vector(direction).normalized(), 20.0)
        return location, normal

    def side(self, y, z, side):
        """The x of the shell's flank at a height, on the right (+1) or the left (-1)."""
        location, _ = self.hit((3.0 * side, y, z), (-side, 0, 0))
        return location.x if location is not None else 0.9 * side

    def top(self, x, y):
        location, _ = self.hit((x, y, 5.0), (0, 0, -1))
        return location.z if location is not None else 1.0

    def nose(self, x, z, end):
        """The y of the front (+1) or the back (-1) at a height."""
        location, _ = self.hit((x, 6.0 * end, z), (0, -end, 0))
        return location.y if location is not None else 2.3 * end


# ---------------------------------------------------------------------------------------------
# Wheels
# ---------------------------------------------------------------------------------------------

def wheel(b, look, x, y, radius, width, side, style='alloy', tyre=True, lugs=0):
    """A wheel on an axle along X, its outer face toward `side`. `lugs` puts that many tread
    blocks round a heavy tyre."""
    centre = (x, y, radius)
    rr = radius * (0.64 if style == 'alloy' else 0.56)
    w = width
    if tyre:
        shoulder = 0.04 if lugs == 0 else 0.06
        profile = [(rr, -w / 2 + 0.014), (rr + 0.02, -w / 2), (radius - 0.03, -w / 2),
                   (radius - 0.007, -w / 2 + shoulder * 0.45), (radius, -w / 2 + shoulder)]
        if lugs == 0:
            for groove in (-w * 0.2, 0.0, w * 0.2):
                profile += [(radius, groove - 0.008), (radius - 0.007, groove - 0.005),
                            (radius - 0.007, groove + 0.005), (radius, groove + 0.008)]
        profile += [(radius, w / 2 - shoulder), (radius - 0.007, w / 2 - shoulder * 0.45), (radius - 0.03, w / 2),
                    (rr + 0.02, w / 2), (rr, w / 2 - 0.014), (rr, -w / 2 + 0.014)]
        b.lathe(look['rubber'], profile, segments=40, axis='X', centre=centre)
        for k in range(lugs):
            for half in (-1, 1):
                angle = math.tau * (k + (0.5 if half > 0 else 0.0)) / lugs
                turn = Matrix.Translation(centre) @ Matrix.Rotation(angle, 4, 'X')
                x0, x1 = sorted((half * 0.02, half * (w / 2 - 0.012)))
                b.box(look['rubber'], (x0, -0.045, radius - 0.012), (x1, 0.045, radius + 0.016), matrix=turn)
    face = side * (w / 2 - 0.014)
    back = -face
    lip = rr + 0.005
    if style == 'alloy':
        dish = face - side * 0.055
        b.lathe(look['rim'], [(0.0, dish), (rr - 0.03, dish), (rr - 0.012, face), (lip, face), (lip, back), (0.0, back)],
                segments=40, axis='X', centre=centre)
        b.cylinder(look['dark'], rr - 0.04, 0.008, centre=(x + dish + side * 0.004, y, radius), axis='X', segments=28)
        b.cylinder(look['rim'], 0.07, 0.05, centre=(x + face - side * 0.03, y, radius), axis='X', segments=18)
        for k in range(5):
            turn = Matrix.Translation(centre) @ Matrix.Rotation(math.radians(72 * k + 18), 4, 'X')
            x0, x1 = sorted((face - side * 0.04, face - side * 0.006))
            b.box(look['rim'], (x0, -0.032, 0.05), (x1, 0.032, rr - 0.008), matrix=turn)
    else:
        # A pressed steel wheel: a deep dish with a ring of nuts round the hub.
        dish = face - side * 0.11
        b.lathe(look['rim'], [(0.0, face - side * 0.02), (0.1, face - side * 0.02), (0.13, dish), (rr - 0.06, dish),
                              (rr - 0.012, face), (lip, face), (lip, back), (0.0, back)],
                segments=40, axis='X', centre=centre)
        b.cylinder(look['dark'], 0.06, 0.05, centre=(x + face, y, radius), axis='X', segments=14)
        for k in range(8):
            angle = math.tau * k / 8
            b.cylinder(look['dark'], 0.014, 0.03,
                       centre=(x + face - side * 0.015, y + math.cos(angle) * 0.085, radius + math.sin(angle) * 0.085),
                       axis='X', segments=6)


# ---------------------------------------------------------------------------------------------
# Civilian cars
# ---------------------------------------------------------------------------------------------

def plate(b, look, text, x, y, z, end):
    """A number plate on the nose (+1) or the tail (-1)."""
    y0, y1 = sorted((y, y + end * 0.012))
    b.box(look['plate'], (x - 0.155, y0, z - 0.078), (x + 0.155, y1, z + 0.078))
    if not look['burnt']:
        bl.add_text(b, text, 0.085, look['ink'], (x, y + end * 0.013, z - 0.004), facing='+Y' if end > 0 else '-Y',
                    extrude=0.001)


def both_sides(obj, material, polygon, **options):
    """Paints a region seen from the side onto both flanks."""
    for side in (1, -1):
        paint(obj, material, polygon, 'X', lambda c, n, s=side: n.x * s > 0.3 and c.x * s > 0.2, **options)


def mirrored(polygon):
    return [(-u, v) for u, v in polygon]


def car(name, spec, look):
    """Builds one car from its `spec` (see SEDAN below) in the colours of `look`."""
    burnt = look['burnt']
    body = loft(name, spec['stations'], look['paint'], levels=spec.get('levels', 3), creases=spec.get('creases'),
                end_crease=spec.get('end_crease', 0.0), ring_creases=spec.get('ring_creases'))
    wheels = spec['wheels']
    radius, width, track = wheels['radius'], wheels['width'], wheels['track']
    arch = wheels.get('arch', radius + 0.055)

    def arches(b, material):
        for axle in wheels['axles']:
            b.cylinder(material, arch, 4.0, centre=(0, axle, radius + 0.01), axis='X', segments=48)
            # The tunnel is squared off below the axle, so that the sill meets it cleanly.
            b.box(material, (-2.0, axle - arch, -0.5), (2.0, axle + arch, radius))
    print('  shell', len(body.data.polygons))
    carve(body, arches, look['under'])
    print('  arches cut', len(body.data.polygons))
    for lo, hi in spec.get('cuts', []):
        carve(body, lambda b, material, lo=lo, hi=hi: b.box(material, lo, hi), look['under'])

    # Underneath, and the lower edge of the body.
    paint_where(body, look['under'], lambda c, n: n.z < -0.55 and c.z < spec.get('under_z', 0.45))

    for region in spec['regions']:
        kind = region['kind']
        material = look[region['mat']]
        frame = look[region['frame']] if region.get('frame') else None
        options = dict(frame=frame, frame_width=region.get('frame_width', 0.014), sink=region.get('sink', 0.0))
        if kind == 'side':
            both_sides(body, material, region['poly'], **options)
        elif kind == 'top':
            keep = region.get('keep', lambda c, n: n.z > 0.2)
            paint(body, material, region['poly'], 'Z', keep, **options)
        elif kind == 'front':
            polys = [region['poly']] + ([mirrored(region['poly'])] if region.get('mirror') else [])
            for poly in polys:
                paint(body, material, poly, 'Y', lambda c, n: n.y > 0.25 and c.y > 0, **options)
        elif kind == 'back':
            polys = [region['poly']] + ([mirrored(region['poly'])] if region.get('mirror') else [])
            for poly in polys:
                paint(body, material, poly, 'Y', lambda c, n: n.y < -0.25 and c.y < 0, **options)

    cube_uv(body)
    bl.shade(body, 42)
    probe = Probe(body)

    w = bl.Builder(name + '_wheels')
    for axle in wheels['axles']:
        for side in (1, -1):
            wheel(w, look, side * track, axle, radius, width, side, style=wheels.get('style', 'alloy'), tyre=not burnt)
    wheel_obj = w.finish(bevel=0.0, smooth_angle=40)

    p = bl.Builder(name + '_parts')
    spec['parts'](p, look, probe)
    parts = p.finish(bevel=0.006, bevel_segments=2, smooth_angle=40)
    probe.bm.free()

    obj = bl.join([body, parts, wheel_obj], name)
    if burnt:
        # No tyres: it has settled onto its rims.
        rr = radius * (0.64 if wheels.get('style', 'alloy') == 'alloy' else 0.56)
        bl.transform_mesh(obj, Matrix.Translation((0, 0, -(radius - rr - 0.005))))
    return obj


def seam(y0, z0, y1, z1, width=0.007):
    """A shut line between two points on the flank, as a thin four-sided region."""
    dy, dz = y1 - y0, z1 - z0
    length = math.hypot(dy, dz)
    ny, nz = -dz / length * width / 2, dy / length * width / 2
    return [(y0 - ny, z0 - nz), (y1 - ny, z1 - nz), (y1 + ny, z1 + nz), (y0 + ny, z0 + nz)]


def line(u0, v0, u1, v1, width=0.007):
    return seam(u0, v0, u1, v1, width)


def fittings(mirror, handles, plates, wipers, exhaust, text, mirror_size=(0.15, 0.1)):
    """What every car carries on its shell: door mirrors at `mirror` (y, z), handles at each
    (y, z), plates at the heights `plates` (front, back), wipers lying from x to x at
    `wipers` (y, [(x0, x1)...]), and an exhaust at `exhaust` (x, z)."""
    def build(b, look, probe):
        my, mz = mirror
        mw, mh = mirror_size
        for side in (1, -1):
            x = probe.side(my, mz, side)
            x0, x1 = sorted((x - side * 0.02, x + side * 0.06))
            b.box(look['trim'], (x0, my - 0.02, mz - 0.03), (x1, my + 0.02, mz))
            x0, x1 = sorted((x + side * 0.045, x + side * (0.045 + mw)))
            b.box(look['paint'], (x0, my - 0.04, mz - 0.03), (x1, my + 0.035, mz - 0.03 + mh))
            g0, g1 = sorted((x + side * 0.058, x + side * (0.032 + mw)))
            b.box(look['glass'], (g0, my - 0.046, mz - 0.018), (g1, my - 0.038, mz - 0.042 + mh))
            for y, z in handles:
                x = probe.side(y, z, side)
                x0, x1 = sorted((x - side * 0.01, x + side * 0.016))
                b.box(look['trim'], (x0, y - 0.06, z - 0.015), (x1, y + 0.06, z + 0.015))
        plate(b, look, text, 0.0, probe.nose(0.0, plates[0], 1), plates[0], 1)
        plate(b, look, text, 0.0, probe.nose(0.0, plates[1], -1), plates[1], -1)
        wy, spans = wipers
        for x0, x1 in spans:
            b.tube(look['trim'], [(x0, wy, probe.top(x0, wy) + 0.012), (x1, wy - 0.06, probe.top(x1, wy - 0.06) + 0.012)],
                   0.007, segments=6)
        ex, ez = exhaust
        b.cylinder(look['rim'], 0.028, 0.16, centre=(ex, probe.nose(ex, ez + 0.02, -1) + 0.02, ez), axis='Y', segments=12)
    return build


SEDAN = dict(
    stations=[
        sect(2.38, 0.66, 0.58, 0.645, 0.70, 0.59, 0.76, wide_z=0.47, sill_z=0.31, floor_z=0.26),
        sect(2.27, 0.715, 0.68, 0.695, 0.80, 0.64, 0.865, wide_z=0.50, sill_z=0.28, floor_z=0.21),
        sect(1.90, 0.79, 0.72, 0.765, 0.84, 0.71, 0.895, wide_z=0.57),
        sect(1.42, 0.865, 0.74, 0.84, 0.85, 0.79, 0.905, wide_z=0.61),
        sect(0.95, 0.925, 0.73, 0.90, 0.85, 0.87, 0.91),
        sect(0.20, 1.425, 0.55, 1.385, 0.84, 0.915, 0.91),
        sect(-0.50, 1.455, 0.56, 1.415, 0.84, 0.925, 0.91),
        sect(-1.20, 1.415, 0.54, 1.375, 0.83, 0.935, 0.905),
        sect(-1.84, 1.035, 0.70, 1.005, 0.84, 0.945, 0.90),
        sect(-2.26, 0.995, 0.71, 0.965, 0.83, 0.885, 0.875, wide_z=0.60),
        sect(-2.39, 0.93, 0.62, 0.91, 0.74, 0.82, 0.79, wide_z=0.56, sill_z=0.36, floor_z=0.30),
    ],
    levels=3,
    creases={2: 0.25, 3: 0.5, 4: 0.3, 5: 0.5},
    end_crease=0.35,
    wheels=dict(radius=0.325, width=0.215, track=0.795, axles=(1.42, -1.33)),
    regions=[
        # Shut lines first, so that the glass and lamps cut across them.
        dict(kind='side', mat='trim', poly=seam(0.80, 0.26, 0.80, 0.92)),
        dict(kind='side', mat='trim', poly=seam(-0.47, 0.26, -0.47, 0.93)),
        dict(kind='side', mat='trim', poly=seam(-0.985, 0.66, -0.985, 0.94)),
        dict(kind='top', mat='trim', poly=line(0.76, 0.96, 0.74, 2.02), keep=lambda c, n: n.z > 0.2 and c.z < 1.0),
        dict(kind='top', mat='trim', poly=line(-0.76, 0.96, -0.74, 2.02), keep=lambda c, n: n.z > 0.2 and c.z < 1.0),
        dict(kind='top', mat='trim', poly=line(-0.74, 2.02, 0.74, 2.02), keep=lambda c, n: n.z > 0.2 and c.z < 1.0),
        dict(kind='top', mat='trim', poly=line(-0.72, -1.88, -0.72, -2.26), keep=lambda c, n: n.z > 0.2 and c.z < 1.1),
        dict(kind='top', mat='trim', poly=line(0.72, -1.88, 0.72, -2.26), keep=lambda c, n: n.z > 0.2 and c.z < 1.1),
        # Glass.
        dict(kind='side', mat='glass', frame='trim', sink=0.004,
             poly=[(0.74, 0.955), (0.12, 1.345), (-0.42, 1.365), (-0.42, 0.965)]),
        dict(kind='side', mat='glass', frame='trim', sink=0.004,
             poly=[(-0.52, 0.965), (-0.52, 1.365), (-1.08, 1.335), (-1.36, 1.05), (-1.36, 0.975)]),
        dict(kind='top', mat='glass', frame='trim', frame_width=0.02,
             keep=lambda c, n: n.y > 0.25 and n.z > 0.2 and c.z > 0.9,
             poly=[(-0.70, 0.86), (0.70, 0.86), (0.50, 0.25), (-0.50, 0.25)]),
        dict(kind='top', mat='glass', frame='trim', frame_width=0.02,
             keep=lambda c, n: n.y < -0.25 and n.z > 0.2 and c.z > 1.0,
             poly=[(-0.50, -1.27), (0.50, -1.27), (0.66, -1.80), (-0.66, -1.80)]),
        # Lamps and grille.
        dict(kind='front', mat='lens', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.40, 0.575), (0.86, 0.60), (0.86, 0.70), (0.44, 0.685)]),
        dict(kind='front', mat='trim', poly=[(-0.34, 0.565), (0.34, 0.565), (0.36, 0.665), (-0.36, 0.665)]),
        dict(kind='front', mat='trim', poly=[(-0.56, 0.27), (0.56, 0.27), (0.60, 0.36), (-0.60, 0.36)]),
        dict(kind='back', mat='lens_red', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.42, 0.76), (0.86, 0.76), (0.86, 0.90), (0.42, 0.88)]),
        dict(kind='back', mat='trim', poly=[(-0.6, 0.30), (0.6, 0.30), (0.6, 0.40), (-0.6, 0.40)]),
    ],
    parts=fittings(mirror=(0.795, 0.985), handles=[(-0.33, 0.86), (-0.87, 0.86)], plates=(0.40, 0.66),
                   wipers=(0.86, [(-0.62, -0.05), (0.02, 0.59)]), exhaust=(-0.52, 0.25), text='614 KDR'),
)

PICKUP = dict(
    stations=[
        sect(2.78, 0.90, 0.66, 0.88, 0.78, 0.80, 0.84, wide_z=0.62, sill_z=0.46, floor_z=0.40),
        sect(2.66, 1.00, 0.78, 0.98, 0.88, 0.90, 0.94, wide_z=0.68, sill_z=0.42, floor_z=0.36),
        sect(2.30, 1.09, 0.81, 1.065, 0.905, 1.00, 0.96, wide_z=0.74, sill_z=0.42, floor_z=0.36),
        sect(1.75, 1.14, 0.81, 1.115, 0.915, 1.06, 0.968, wide_z=0.78, sill_z=0.42, floor_z=0.36),
        sect(1.22, 1.18, 0.80, 1.155, 0.915, 1.12, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(0.62, 1.80, 0.63, 1.76, 0.895, 1.16, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(0.00, 1.835, 0.64, 1.795, 0.895, 1.17, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(-0.60, 1.815, 0.63, 1.775, 0.895, 1.18, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(-0.67, 1.30, 0.92, 1.29, 0.955, 1.20, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(-1.60, 1.30, 0.93, 1.29, 0.957, 1.20, 0.97, wide_z=0.80, sill_z=0.42, floor_z=0.36),
        sect(-2.62, 1.30, 0.93, 1.29, 0.955, 1.19, 0.965, wide_z=0.80, sill_z=0.44, floor_z=0.38),
        sect(-2.76, 1.28, 0.90, 1.27, 0.93, 1.14, 0.94, wide_z=0.78, sill_z=0.52, floor_z=0.46),
    ],
    levels=3,
    creases={2: 0.3, 3: 0.5, 4: 0.3, 5: 0.5},
    end_crease=0.45,
    ring_creases={7: 0.75, 8: 0.75},
    under_z=0.6,
    wheels=dict(radius=0.39, width=0.26, track=0.83, axles=(1.75, -1.60), arch=0.46),
    cuts=[((-0.80, -2.64, 0.88), (0.80, -0.90, 2.4))],
    regions=[
        dict(kind='side', mat='trim', poly=seam(1.02, 0.44, 1.02, 1.17)),
        dict(kind='side', mat='trim', poly=seam(-0.44, 0.44, -0.44, 1.19)),
        dict(kind='side', mat='trim', poly=seam(-0.70, 0.44, -0.70, 1.30, 0.014)),
        dict(kind='top', mat='trim', poly=line(0.80, 1.24, 0.79, 2.50), keep=lambda c, n: n.z > 0.2 and c.z < 1.25),
        dict(kind='top', mat='trim', poly=line(-0.80, 1.24, -0.79, 2.50), keep=lambda c, n: n.z > 0.2 and c.z < 1.25),
        dict(kind='side', mat='glass', frame='trim', sink=0.004,
             poly=[(1.00, 1.195), (0.54, 1.705), (-0.38, 1.725), (-0.38, 1.21)]),
        dict(kind='top', mat='glass', frame='trim', frame_width=0.02,
             keep=lambda c, n: n.y > 0.25 and n.z > 0.15 and c.z > 1.15,
             poly=[(-0.76, 1.14), (0.76, 1.14), (0.58, 0.66), (-0.58, 0.66)]),
        dict(kind='back', mat='glass', frame='trim', frame_width=0.02,
             poly=[(-0.60, 1.40), (0.60, 1.40), (0.54, 1.69), (-0.54, 1.69)]),
        dict(kind='front', mat='lens', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.50, 0.86), (0.93, 0.86), (0.93, 1.02), (0.50, 1.02)]),
        dict(kind='front', mat='trim', poly=[(-0.46, 0.80), (0.46, 0.80), (0.46, 1.02), (-0.46, 1.02)]),
        dict(kind='front', mat='rim', poly=[(-0.98, 0.46), (0.98, 0.46), (0.98, 0.64), (-0.98, 0.64)]),
        dict(kind='back', mat='lens_red', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.81, 0.86), (0.95, 0.86), (0.95, 1.2), (0.81, 1.2)]),
        dict(kind='back', mat='trim', poly=line(-0.79, 0.68, -0.79, 1.27)),
        dict(kind='back', mat='trim', poly=line(0.79, 0.68, 0.79, 1.27)),
        dict(kind='back', mat='trim', poly=line(-0.79, 0.68, 0.79, 0.68)),
        dict(kind='back', mat='rim', poly=[(-0.98, 0.50), (0.98, 0.50), (0.98, 0.64), (-0.98, 0.64)]),
    ],
    parts=fittings(mirror=(1.03, 1.25), handles=[(-0.30, 1.08)], plates=(0.55, 0.57),
                   wipers=(1.12, [(-0.66, -0.06), (0.02, 0.62)]), exhaust=(0.62, 0.42), text='PJT 2291',
                   mirror_size=(0.13, 0.16)),
)

VAN = dict(
    stations=[
        sect(2.52, 0.84, 0.66, 0.82, 0.76, 0.74, 0.84, wide_z=0.58, sill_z=0.42, floor_z=0.36),
        sect(2.40, 0.96, 0.79, 0.94, 0.89, 0.86, 0.945, wide_z=0.64, sill_z=0.37, floor_z=0.31),
        sect(2.05, 1.05, 0.82, 1.025, 0.92, 0.96, 0.97, wide_z=0.70, sill_z=0.37, floor_z=0.31),
        sect(1.62, 1.12, 0.84, 1.09, 0.93, 1.03, 0.975, wide_z=0.74, sill_z=0.37, floor_z=0.31),
        sect(0.95, 1.90, 0.75, 1.86, 0.94, 1.09, 0.975, wide_z=0.76, sill_z=0.37, floor_z=0.31),
        sect(0.00, 1.96, 0.77, 1.92, 0.945, 1.10, 0.975, wide_z=0.76, sill_z=0.37, floor_z=0.31),
        sect(-1.20, 1.96, 0.77, 1.92, 0.945, 1.10, 0.975, wide_z=0.76, sill_z=0.37, floor_z=0.31),
        sect(-2.34, 1.94, 0.76, 1.90, 0.94, 1.10, 0.97, wide_z=0.76, sill_z=0.38, floor_z=0.32),
        sect(-2.50, 1.84, 0.70, 1.80, 0.90, 1.08, 0.935, wide_z=0.74, sill_z=0.44, floor_z=0.38),
    ],
    levels=3,
    creases={2: 0.45, 3: 0.2, 4: 0.3, 5: 0.5},
    end_crease=0.6,
    under_z=0.55,
    wheels=dict(radius=0.35, width=0.23, track=0.845, axles=(1.55, -1.45), arch=0.41),
    regions=[
        dict(kind='side', mat='trim', poly=seam(1.50, 0.76, 1.50, 1.12)),
        dict(kind='side', mat='trim', poly=seam(0.46, 0.38, 0.46, 1.86)),
        dict(kind='side', mat='trim', poly=seam(-0.80, 0.38, -0.80, 1.86)),
        dict(kind='side', mat='trim', poly=seam(0.46, 1.86, -0.80, 1.86)),
        dict(kind='side', mat='trim', poly=seam(-0.80, 1.02, 0.30, 1.02, 0.02)),
        dict(kind='top', mat='trim', poly=line(-0.80, 1.66, 0.80, 1.66), keep=lambda c, n: n.z > 0.2 and c.z < 1.2),
        dict(kind='side', mat='glass', frame='trim', sink=0.004,
             poly=[(1.50, 1.15), (1.04, 1.80), (0.54, 1.82), (0.54, 1.16)]),
        dict(kind='top', mat='glass', frame='trim', frame_width=0.022,
             keep=lambda c, n: n.y > 0.3 and c.z > 1.1,
             poly=[(-0.82, 1.58), (0.82, 1.58), (0.68, 1.00), (-0.68, 1.00)]),
        dict(kind='back', mat='trim', poly=line(0.0, 0.52, 0.0, 1.88)),
        dict(kind='back', mat='glass', mirror=True, frame='trim', frame_width=0.018,
             poly=[(0.07, 1.26), (0.70, 1.26), (0.66, 1.76), (0.07, 1.76)]),
        dict(kind='front', mat='lens', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.52, 0.72), (0.93, 0.74), (0.93, 0.91), (0.54, 0.91)]),
        dict(kind='front', mat='trim', poly=[(-0.44, 0.70), (0.44, 0.70), (0.46, 0.89), (-0.46, 0.89)]),
        dict(kind='front', mat='trim', poly=[(-0.9, 0.36), (0.9, 0.36), (0.9, 0.56), (-0.9, 0.56)]),
        dict(kind='back', mat='lens_red', mirror=True, frame='trim', frame_width=0.008,
             poly=[(0.80, 0.86), (0.93, 0.86), (0.93, 1.36), (0.80, 1.36)]),
        dict(kind='back', mat='trim', poly=[(-0.92, 0.38), (0.92, 0.38), (0.92, 0.54), (-0.92, 0.54)]),
    ],
    parts=fittings(mirror=(1.52, 1.30), handles=[(0.60, 1.02), (-0.66, 1.02)], plates=(0.60, 0.72),
                   wipers=(1.54, [(-0.70, -0.06), (0.04, 0.68)]), exhaust=(-0.6, 0.36), text='W 40871',
                   mirror_size=(0.13, 0.2)),
)


# ---------------------------------------------------------------------------------------------
# The Directorate's vehicles
# ---------------------------------------------------------------------------------------------

def army_look():
    return dict(paint=M['army'], glass=M['glass'], trim=M['army_dark'], rubber=M['rubber'], rim=M['army_dark'],
                dark=M['army_dark'], lens=M['lens'], lens_red=M['lens_red'], lens_amber=M['lens_amber'],
                plate=M['plate'], ink=M['ink'], under=M['army_dark'], burnt=False)


def emblem_side(b, material, x, y, z, size, side):
    """The Directorate's mark on a flank: a hexagon, open, with a chevron pointing up in it."""
    offset = x if side > 0 else x - 0.003
    ring = lambda scale: [(y + size * scale * math.cos(math.radians(30 + 60 * i)),  # noqa: E731
                           z + size * scale * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    outer, inner = ring(1.0), ring(0.78)
    for i in range(6):
        j = (i + 1) % 6
        b.prism(material, [outer[i], outer[j], inner[j], inner[i]], 0.003, axis='X', offset=offset)
    s = size
    b.prism(material, [(y - 0.5 * s, z - 0.3 * s), (y, z + 0.32 * s), (y + 0.5 * s, z - 0.3 * s), (y + 0.5 * s, z - 0.52 * s),
                       (y, z + 0.08 * s), (y - 0.5 * s, z - 0.52 * s)], 0.003, axis='X', offset=offset)


def pane(b, material, x0, x1, foot, head, thick=0.012):
    """A flat pane of glass standing on a sloping face: from `foot` (y, z) up to `head`
    (y, z), across from x0 to x1, a little proud of the face."""
    (y0, z0), (y1, z1) = foot, head
    rise = math.hypot(y1 - y0, z1 - z0)
    lean = math.atan2(y0 - y1, z1 - z0)
    place = Matrix.Translation(((0.0, (y0 + y1) / 2, (z0 + z1) / 2))) @ Matrix.Rotation(lean, 4, 'X')
    forward = 1.0 if y0 >= 0 or y1 >= y0 else 1.0
    b.box(material, (x0, -0.003 * forward, -rise / 2), (x1, thick * forward, rise / 2), matrix=place)


def truck(name, kind, wreck=False):
    """The Directorate's six-wheeled lorry: `kind` 'cargo' carries a canvas tilt, 'jammer'
    the signals cabin and mast that have silenced Alder Ridge. A `wreck` is what the charge
    leaves of it: burnt out, its mast down."""
    look = army_look()
    A, D, G = M['army'], M['army_dark'], M['glass']
    lens, lens_red, lens_amber, mark, stripe, rust = (M['lens'], M['lens_red'], M['lens_amber'], M['mark'],
                                                      M['stripe'], M['rust'])
    panel, beacon, lamp = M['plate'], M['beacon'], M['lamp']
    if wreck:
        A, D, G = M['burnt'], M['soot'], M['soot']
        lens = lens_red = lens_amber = beacon = lamp = M['soot']
        mark = stripe = rust = panel = M['burnt']
        look = burnt_look()
    radius, width, track = 0.56, 0.36, 1.03
    axles = (2.35, -1.55, -2.85)
    b = bl.Builder(name)

    # The chassis: two rails, cross members, axles, the shaft between them.
    for side in (1, -1):
        b.box(D, (side * 0.43 - 0.05, -3.84, 0.84), (side * 0.43 + 0.05, 3.36, 1.05))
        for axle in axles:
            b.box(D, (side * 0.62 - 0.04, axle - 0.62, 0.66), (side * 0.62 + 0.04, axle + 0.62, 0.72))
            b.box(D, (side * 0.62 - 0.05, axle - 0.08, 0.56), (side * 0.62 + 0.05, axle + 0.08, 0.84))
    for y in (-3.6, -2.2, -0.9, 0.6, 2.9):
        b.box(D, (-0.43, y - 0.05, 0.87), (0.43, y + 0.05, 1.01))
    for axle in axles:
        b.cylinder(D, 0.085, 2.0, centre=(0, axle, radius), axis='X', segments=12)
        b.sphere(D, 0.2, centre=(0, axle, radius), segments=16, rings=8, scale=(1.0, 1.1, 1.0))
    b.cylinder(D, 0.045, 5.3, centre=(0, -0.3, 0.68), axis='Y', segments=10)
    # Fuel on the left, a locker and the batteries on the right, steps up to both doors.
    b.cylinder(A, 0.3, 1.25, centre=(-0.9, 0.35, 0.74), axis='Y', segments=22)
    for y in (-0.05, 0.75):
        b.box(D, (-1.22, y - 0.03, 0.43), (-0.58, y + 0.03, 1.05))
    b.cylinder(D, 0.05, 0.05, centre=(-0.9, 0.9, 1.05), axis='Z', segments=10)
    b.box(A, (0.6, -0.25, 0.48), (1.2, 0.95, 1.02))
    b.box(D, (1.2, -0.2, 0.52), (1.206, 0.9, 0.98))
    for side in (1, -1):
        for z in (0.5, 0.82):
            b.box(D, (side * 1.0 - 0.24, 1.0, z), (side * 1.0 + 0.24, 1.42, z + 0.03))
        for y in (1.02, 1.4):
            b.box(D, (side * 1.2 - 0.02, y - 0.015, 0.5), (side * 1.2 + 0.02, y + 0.015, 1.1))

    # The bumper, with its hooks and marker lamps.
    b.box(D, (-1.23, 3.4, 0.72), (1.23, 3.58, 1.0))
    for side in (1, -1):
        b.box(D, (side * 0.5 - 0.03, 3.58, 0.8), (side * 0.5 + 0.03, 3.7, 0.92))
        b.box(lens_amber, (side * 1.05 - 0.07, 3.58, 0.82), (side * 1.05 + 0.07, 3.6, 0.9))

    # The bonnet and its grille.
    b.prism(A, [(1.52, 1.06), (3.38, 1.06), (3.38, 1.74), (3.22, 1.88), (1.52, 1.97)], 1.5, axis='X', offset=-0.75)
    b.box(D, (-0.6, 3.378, 1.14), (0.6, 3.39, 1.72))
    for i in range(8):
        z = 1.17 + i * 0.068
        b.box(A, (-0.6, 3.385, z), (0.6, 3.405, z + 0.03))
    for x in (-0.3, 0.0, 0.3):
        b.box(A, (x - 0.02, 3.385, 1.14), (x + 0.02, 3.41, 1.72))
    for side in (1, -1):
        b.box(D, (side * 0.4 - 0.005, 1.6, 1.94), (side * 0.4 + 0.005, 3.2, 1.9), matrix=None) if False else None
        # Mudguards over the front wheels, and the lamps that stand on them.
        x0, x1 = sorted((side * 0.75, side * 1.25))
        b.box(A, (x0, 1.62, 1.2), (x1, 3.3, 1.26))
        b.box(A, (x0, 3.26, 0.98), (x1, 3.32, 1.26))
        b.prism(A, [(1.56, 0.86), (1.62, 0.86), (1.66, 1.26), (1.6, 1.26)], abs(x1 - x0), axis='X', offset=x0)
        b.box(A, (side * 0.98 - 0.15, 3.12, 1.26), (side * 0.98 + 0.15, 3.38, 1.56))
        b.cylinder(lens, 0.105, 0.03, centre=(side * 0.98, 3.385, 1.41), axis='Y', segments=20)
        b.cylinder(D, 0.125, 0.02, centre=(side * 0.98, 3.378, 1.41), axis='Y', segments=20)
        b.box(lens_amber, (side * 1.19 - 0.04, 3.3, 1.28), (side * 1.19 + 0.04, 3.345, 1.36))

    # The cab.
    b.prism(A, [(-0.32, 1.06), (1.52, 1.06), (1.52, 1.97), (1.3, 2.7), (-0.32, 2.7)], 2.4, axis='X', offset=-1.2)
    b.box(A, (-1.22, -0.34, 2.7), (1.22, 1.33, 2.75))
    b.box(A, (-1.2, 1.3, 2.66), (1.2, 1.52, 2.7))
    for x0, x1 in ((-1.1, -0.04), (0.04, 1.1)):
        pane(b, G, x0, x1, (1.5, 2.04), (1.325, 2.62))
    for side in (1, -1):
        offset = side * 1.2 - (0.004 if side > 0 else 0.008)
        b.prism(G, [(-0.14, 2.03), (1.4, 2.03), (1.26, 2.6), (-0.14, 2.6)], 0.012, axis='X', offset=offset)
        # The door: its outline, a handle, and whose lorry it is.
        x = side * 1.2
        x0, x1 = sorted((x, x + side * 0.004))
        for y in (-0.22, 1.46):
            b.box(D, (x0, y - 0.006, 1.12), (x1, y + 0.006, 2.66))
        b.box(D, (x0, -0.22, 1.114), (x1, 1.46, 1.126))
        hx0, hx1 = sorted((x, x + side * 0.03))
        b.box(D, (hx0, -0.12, 1.86), (hx1, 0.04, 1.9))
        emblem_side(b, mark, x + side * 0.002, 0.62, 1.62, 0.2, side)
        sx0, sx1 = sorted((x, x + side * 0.003))
        b.box(stripe, (sx0, -0.2, 1.24), (sx1, 1.44, 1.3))
        # Mirrors on their arms.
        b.tube(D, [(x, 1.44, 2.5), (x + side * 0.28, 1.5, 2.5), (x + side * 0.28, 1.5, 2.0), (x, 1.44, 2.0)], 0.014, segments=6)
        mx0, mx1 = sorted((x + side * 0.2, x + side * 0.36))
        b.box(D, (mx0, 1.49, 2.06), (mx1, 1.53, 2.44))
        b.box(G, (mx0 + 0.012, 1.482, 2.075), (mx1 - 0.012, 1.49, 2.425))
    b.box(G, (-0.5, -0.332, 2.1), (0.5, -0.32, 2.5))
    # The exhaust stands behind the cab, under a guard.
    b.tube(D, [(0.98, -0.2, 0.8), (0.98, -0.46, 0.9), (0.98, -0.46, 3.05), (0.98, -0.56, 3.14)], 0.055, segments=12)
    b.cylinder(rust, 0.085, 1.0, centre=(0.98, -0.46, 2.2), axis='Z', segments=14)
    # The air filter, on the left wing.
    b.cylinder(D, 0.16, 0.42, centre=(-1.0, 1.9, 1.5), axis='Z', segments=16)
    b.cylinder(D, 0.05, 0.3, centre=(-1.0, 1.9, 1.84), axis='Z', segments=10)
    plate(b, look, 'D-7 1164', 0.0, 3.58, 0.86, 1)

    # The back end: lamps, flaps, the hitch.
    for side in (1, -1):
        b.box(lens_red, (side * 1.05 - 0.09, -3.9, 0.95), (side * 1.05 + 0.09, -3.87, 1.03))
        for axle in (-1.55, -2.85):
            pass
        b.box(M['rubber'], (side * 1.03 - 0.2, -3.62, 0.3), (side * 1.03 + 0.2, -3.6, 1.0))
    b.box(D, (-1.2, -3.88, 0.84), (1.2, -3.78, 1.04))
    b.box(D, (-0.08, -4.0, 0.74), (0.08, -3.84, 0.9))
    plate(b, look, 'D-7 1164', 0.62, -3.88, 0.94, -1)

    extra = []
    if kind == 'cargo':
        # A flat bed with drop sides, under a tilt on five hoops.
        b.box(D, (-1.23, -3.86, 1.05), (1.23, -0.42, 1.2))
        for side in (1, -1):
            x0, x1 = sorted((side * 1.18, side * 1.23))
            b.box(A, (x0, -3.86, 1.2), (x1, -0.42, 1.82))
            for i in range(6):
                y = -3.7 + i * 0.63
                rx0, rx1 = sorted((side * 1.23, side * 1.25))
                b.box(A, (rx0, y - 0.035, 1.2), (rx1, y + 0.035, 1.82))
            rx0, rx1 = sorted((side * 1.23, side * 1.255))
            b.box(A, (rx0, -3.86, 1.76), (rx1, -0.42, 1.82))
        b.box(A, (-1.23, -0.47, 1.2), (1.23, -0.42, 1.82))
        b.box(A, (-1.23, -3.86, 1.2), (1.23, -3.81, 1.82))
        for x in (-0.6, 0.0, 0.6):
            b.box(A, (x - 0.04, -3.88, 1.2), (x + 0.04, -3.86, 1.82))
        hoops = [-0.48, -1.31, -2.14, -2.97, -3.8]
        stations = []

        def hoop(y, sag):
            return (y, [(0.0, 3.1 - sag), (0.5, 3.07 - sag), (0.98, 2.93 - sag * 0.7), (1.255 - sag * 0.3, 2.68),
                        (1.262 - sag * 0.5, 2.2), (1.262, 1.74), (0.0, 1.74)])
        stations.append(hoop(hoops[0] + 0.04, 0.03))
        for index, y in enumerate(hoops):
            stations.append(hoop(y, 0.0))
            if index < len(hoops) - 1:
                stations.append(hoop((y + hoops[index + 1]) / 2, 0.055))
        stations.append(hoop(hoops[-1] - 0.04, 0.03))
        tilt = loft(name + '_tilt', stations, M['canvas'], levels=2, creases={5: 0.9, 3: 0.2}, end_crease=0.8)
        cube_uv(tilt)
        bl.shade(tilt, 50)
        extra.append(tilt)
        # The straps that hold it down.
        for side in (1, -1):
            for y in hoops[1:-1]:
                sx0, sx1 = sorted((side * 1.262, side * 1.272))
                b.box(D, (sx0, y - 0.02, 1.5), (sx1, y + 0.02, 2.0))
    else:
        # The signals cabin.
        b.box(A, (-1.23, -3.86, 1.05), (1.23, -0.44, 3.02))
        b.box(D, (-1.25, -3.88, 1.05), (1.25, -0.42, 1.12))
        b.box(D, (-1.25, -3.88, 2.98), (1.25, -0.42, 3.04))
        for side in (1, -1):
            x0, x1 = sorted((side * 1.23, side * 1.245))
            for y in (-3.3, -2.7, -1.6, -1.0):
                b.box(A, (x0, y - 0.03, 1.12), (x1, y + 0.03, 2.98))
            # Louvres over the cooling fans.
            for i in range(6):
                z = 2.3 + i * 0.07
                lx0, lx1 = sorted((side * 1.23, side * 1.26))
                b.box(D, (lx0, -1.5, z), (lx1, -1.1, z + 0.03))
            emblem_side(b, mark, side * 1.232, -2.15, 2.2, 0.34, side)
            sx0, sx1 = sorted((side * 1.23, side * 1.233))
            b.box(stripe, (sx0, -3.84, 1.3), (sx1, -0.46, 1.38))
        # The door at the back, the steps up to it.
        b.box(D, (-0.42, -3.872, 1.16), (0.42, -3.86, 2.86))
        b.box(A, (-0.4, -3.884, 1.18), (0.4, -3.87, 2.84))
        b.box(D, (0.26, -3.91, 1.96), (0.3, -3.884, 2.1))
        b.box(G, (-0.18, -3.892, 2.3), (0.18, -3.884, 2.6))
        for i in range(3):
            z = 0.34 + i * 0.3
            b.box(D, (-0.4, -4.2 + i * 0.1, z), (0.4, -3.96 + i * 0.1, z + 0.03))
        for x in (-0.4, 0.4):
            b.tube(D, [(x, -4.2, 0.34), (x, -3.9, 1.0)], 0.018, segments=6)
        # The panel on the left flank where the cables come in: this is what must be broken.
        b.box(D, (-1.3, -3.2, 1.45), (-1.23, -2.5, 2.05))
        b.box(A, (-1.315, -3.17, 1.48), (-1.3, -2.53, 2.02))
        for i in range(4):
            b.cylinder(D, 0.03, 0.06, centre=(-1.34, -3.05 + i * 0.14, 1.62), axis='X', segments=10)
        b.box(beacon, (-1.33, -2.66, 1.88), (-1.312, -2.6, 1.94))
        b.box(lamp, (-1.33, -2.76, 1.88), (-1.312, -2.7, 1.94))
        b.tube(D, [(-1.36, -3.05, 1.62), (-1.5, -3.05, 1.3), (-1.5, -3.3, 0.06), (-1.9, -4.4, 0.04), (-2.6, -4.9, 0.04)], 0.022,
               segments=8)
        b.tube(D, [(-1.36, -2.91, 1.62), (-1.46, -2.91, 1.2), (-1.46, -2.6, 0.06), (-2.2, -1.9, 0.04), (-3.2, -1.7, 0.04)], 0.022,
               segments=8)
        # On the roof: a rail, the air conditioner, and the mast.
        for side in (1, -1):
            b.tube(D, [(side * 1.18, -3.8, 3.04), (side * 1.18, -3.8, 3.3), (side * 1.18, -0.5, 3.3), (side * 1.18, -0.5, 3.04)],
                   0.018, segments=6)
            for y in (-2.7, -1.6):
                b.tube(D, [(side * 1.18, y, 3.04), (side * 1.18, y, 3.3)], 0.014, segments=6)
        b.box(A, (-0.5, -1.3, 3.04), (0.5, -0.6, 3.34))
        b.box(D, (-0.42, -1.31, 3.1), (0.42, -1.3, 3.28))
        b.box(D, (-0.4, -3.2, 3.04), (0.4, -2.4, 3.16))
        mast_y = -2.8
        if wreck:
            # The foot of the mast still stands; the rest lies across the forecourt where it
            # fell, its yard and panels broken off round it.
            b.cylinder(D, 0.2, 0.26, centre=(0, mast_y, 3.26), axis='Z', segments=16)
            b.cylinder(A, 0.11, 1.2, centre=(0, mast_y, 3.85), axis='Z', segments=16)
            b.tube(A, [(0.05, mast_y, 4.4), (-1.6, mast_y - 0.5, 2.5), (-3.4, mast_y - 1.1, 0.16)], 0.095, segments=12)
            b.tube(A, [(-3.6, mast_y - 1.2, 0.12), (-6.6, mast_y - 2.2, 0.1)], 0.07, segments=10)
            b.box(D, (-7.6, mast_y - 3.3, 0.04), (-6.0, mast_y - 3.2, 0.12),
                  matrix=Matrix.Rotation(math.radians(24), 4, 'Z'))
            for x, y, turn in ((-6.9, mast_y - 1.4, 30), (-5.6, mast_y - 3.4, -50), (-7.8, mast_y - 2.9, 80),
                               (-4.4, mast_y + 0.4, 12)):
                place = Matrix.Translation((x, y, 0.05)) @ Matrix.Rotation(math.radians(turn), 4, 'Z')
                b.box(panel, (-0.13, -0.65, 0.0), (0.13, 0.65, 0.08), matrix=place)
            b.lathe(panel, [(0.0, 0.0), (0.2, 0.012), (0.38, 0.05), (0.5, 0.11), (0.5, 0.125), (0.36, 0.07), (0.18, 0.035),
                            (0.0, 0.025)], segments=28, axis='Z', centre=(-2.3, mast_y + 1.5, 0.03))
            # The cabin's roof is blown open.
            b.box(D, (-0.9, -3.3, 3.0), (0.9, -1.9, 3.06))
            for x, y, turn, tilt in ((1.7, -2.0, 20, 14), (-1.9, -3.4, -35, -22)):
                place = (Matrix.Translation((x, y, 0.06)) @ Matrix.Rotation(math.radians(turn), 4, 'Z')
                         @ Matrix.Rotation(math.radians(tilt), 4, 'X'))
                b.box(A, (-0.6, -0.5, 0.0), (0.6, 0.5, 0.03), matrix=place)
        else:
            b.cylinder(D, 0.2, 0.26, centre=(0, mast_y, 3.26), axis='Z', segments=16)
            b.cylinder(A, 0.11, 2.3, centre=(0, mast_y, 4.4), axis='Z', segments=16)
            b.cylinder(D, 0.13, 0.08, centre=(0, mast_y, 5.5), axis='Z', segments=16)
            b.cylinder(A, 0.085, 1.9, centre=(0, mast_y, 6.45), axis='Z', segments=14)
            b.cylinder(D, 0.105, 0.08, centre=(0, mast_y, 7.36), axis='Z', segments=14)
            b.cylinder(A, 0.06, 1.7, centre=(0, mast_y, 8.2), axis='Z', segments=12)
            # Guys from the collars to the corners of the roof.
            for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                b.tube(D, [(0.1 * sx, mast_y + 0.1 * sy, 5.5), (1.15 * sx, mast_y + (0.95 if sy > 0 else -0.95) * 1.0, 3.06)], 0.006,
                       segments=4)
            # The head of the mast: a yard with four panels, two whips, a beacon.
            top = 8.6
            b.box(D, (-1.5, mast_y - 0.04, top - 0.04), (1.5, mast_y + 0.04, top + 0.04))
            b.box(D, (-0.04, mast_y - 0.9, top - 0.34), (0.04, mast_y + 0.9, top - 0.26))
            for x in (-1.42, -0.62, 0.62, 1.42):
                b.box(panel, (x - 0.13, mast_y + 0.05, top - 0.75), (x + 0.13, mast_y + 0.13, top + 0.55))
                b.box(D, (x - 0.03, mast_y - 0.04, top - 0.3), (x + 0.03, mast_y + 0.06, top + 0.3))
            for y in (-0.86, 0.86):
                b.box(panel, (-0.13, mast_y + y - 0.04, top - 1.0), (0.13, mast_y + y + 0.04, top - 0.05))
            for x in (-1.0, 1.0):
                b.tube(D, [(x, mast_y, top + 0.04), (x, mast_y, top + 1.9)], 0.008, segments=5)
                b.cylinder(D, 0.022, 0.2, centre=(x, mast_y, top + 0.14), axis='Z', segments=8)
            b.cylinder(D, 0.045, 0.08, centre=(0, mast_y, 9.09), axis='Z', segments=10)
            b.sphere(beacon, 0.06, centre=(0, mast_y, 9.17), segments=12, rings=6)
            # A dish half way up, looking out over the town.
            dish_z = 6.3
            b.box(D, (0.06, mast_y - 0.03, dish_z - 0.03), (0.4, mast_y + 0.03, dish_z + 0.03))
            b.lathe(panel, [(0.0, 0.0), (0.2, 0.012), (0.38, 0.05), (0.5, 0.11), (0.5, 0.125), (0.36, 0.07), (0.18, 0.035),
                                 (0.0, 0.025)], segments=28, axis='X', centre=(0.4, mast_y, dish_z))
            b.tube(D, [(0.42, mast_y, dish_z), (0.72, mast_y, dish_z)], 0.012, segments=6)
            b.cylinder(D, 0.035, 0.07, centre=(0.74, mast_y, dish_z), axis='X', segments=10)
            # The feeder cable down the mast.
            b.tube(D, [(0.0, mast_y - 0.13, 8.5), (0.0, mast_y - 0.13, 3.2), (0.0, mast_y - 0.3, 3.08)], 0.016, segments=6)
        # Jacks down at the four corners: it is not going anywhere.
        for side in (1, -1):
            for y in (-0.75, -3.55):
                x0, x1 = sorted((side * 0.48, side * 1.5))
                b.box(D, (x0, y - 0.06, 0.88), (x1, y + 0.06, 1.0))
                b.cylinder(D, 0.05, 0.86, centre=(side * 1.45, y, 0.47), axis='Z', segments=10)
                b.cylinder(D, 0.17, 0.04, centre=(side * 1.45, y, 0.02), axis='Z', segments=14)
    body = b.finish(bevel=0.012, bevel_segments=2, smooth_angle=40)

    w = bl.Builder(name + '_wheels')
    for axle in axles:
        for side in (1, -1):
            wheel(w, look, side * track, axle, radius, width, side, style='steel', lugs=20 if not wreck else 0,
                  tyre=not (wreck and side < 0))
    wheels = w.finish(bevel=0.0, smooth_angle=40)
    return bl.join([body, wheels] + extra, name)


def patrol(name):
    """The Directorate's patrol car: a square four-by-four with a lamp bar and a whip aerial."""
    look = army_look()
    A, D, G = M['army'], M['army_dark'], M['glass']
    radius, width, track = 0.42, 0.28, 0.82
    axles = (1.36, -1.3)
    half = 0.93
    b = bl.Builder(name + '_body')
    b.prism(A, [(-2.12, 0.6), (2.02, 0.6), (2.18, 0.74), (2.18, 1.12), (2.08, 1.22), (0.86, 1.3), (0.48, 1.95), (-2.02, 1.95),
                (-2.12, 1.84)], half * 2, axis='X', offset=-half)
    body = b.finish(bevel=0.03, bevel_segments=3, smooth_angle=40)

    def arches(cutter, material):
        for axle in axles:
            cutter.cylinder(material, radius + 0.085, 4.0, centre=(0, axle, radius + 0.02), axis='X', segments=40)
            cutter.box(material, (-2.0, axle - radius - 0.085, -0.5), (2.0, axle + radius + 0.085, radius))
    carve(body, arches, D)

    p = bl.Builder(name + '_parts')
    # Glass.
    for x0, x1 in ((-0.84, -0.03), (0.03, 0.84)):
        pane(p, G, x0, x1, (0.83, 1.37), (0.52, 1.9))
    for side in (1, -1):
        x = side * half
        offset = x - (0.004 if side > 0 else 0.008)
        p.prism(G, [(0.72, 1.36), (0.44, 1.86), (-0.42, 1.86), (-0.42, 1.36)], 0.012, axis='X', offset=offset)
        p.prism(G, [(-0.52, 1.36), (-0.52, 1.86), (-1.28, 1.86), (-1.28, 1.36)], 0.012, axis='X', offset=offset)
        p.prism(G, [(-1.4, 1.4), (-1.4, 1.84), (-1.98, 1.84), (-1.98, 1.4)], 0.012, axis='X', offset=offset)
        x0, x1 = sorted((x, x + side * 0.004))
        for y in (0.8, -0.47, -1.34):
            p.box(D, (x0, y - 0.005, 0.68 if y > -1.0 else 1.0), (x1, y + 0.005, 1.9))
        for y in (-0.36, -1.22):
            hx0, hx1 = sorted((x, x + side * 0.028))
            p.box(D, (hx0, y - 0.07, 1.2), (hx1, y + 0.07, 1.235))
        emblem_side(p, M['mark'], x + side * 0.002, 0.16, 1.0, 0.17, side)
        sx0, sx1 = sorted((x, x + side * 0.003))
        p.box(M['stripe'], (sx0, -1.3, 0.72), (sx1, 0.76, 0.77))
        # Wheel-arch flares.
        for axle in axles:
            points = []
            for i in range(11):
                angle = math.radians(-10 + i * 20)
                points.append((x + side * 0.02, axle + math.cos(angle) * (radius + 0.1), radius + 0.02 + math.sin(angle) * (radius + 0.1)))
            p.tube(D, points, 0.035, segments=8)
        # Mirrors.
        mx0, mx1 = sorted((x + side * 0.02, x + side * 0.2))
        p.box(D, (mx0, 0.82, 1.36), (mx1, 0.88, 1.56))
        p.box(G, (min(mx0, mx1) + 0.02, 0.812, 1.375), (max(mx0, mx1) - 0.012, 0.82, 1.545))
        # Lamps.
        p.cylinder(M['lens'], 0.095, 0.03, centre=(side * 0.68, 2.185, 0.98), axis='Y', segments=18)
        p.cylinder(D, 0.115, 0.02, centre=(side * 0.68, 2.178, 0.98), axis='Y', segments=18)
        p.box(M['lens_amber'], (side * 0.68 - 0.08, 2.18, 0.8), (side * 0.68 + 0.08, 2.196, 0.85))
        p.box(M['lens_red'], (side * 0.78 - 0.07, -2.136, 1.0), (side * 0.78 + 0.07, -2.12, 1.22))
    p.box(G, (-0.62, -2.136, 1.42), (0.62, -2.126, 1.84))
    # Grille, bumpers and the bar that guards them.
    p.box(D, (-0.5, 2.18, 0.86), (0.5, 2.194, 1.1))
    for i in range(5):
        p.box(A, (-0.5, 2.19, 0.88 + i * 0.045), (0.5, 2.204, 0.9 + i * 0.045))
    p.box(D, (-0.95, 2.16, 0.5), (0.95, 2.34, 0.7))
    p.box(D, (-0.95, -2.26, 0.52), (0.95, -2.1, 0.7))
    for x in (-0.42, 0.42):
        p.tube(D, [(x, 2.34, 0.56), (x, 2.42, 0.7), (x, 2.42, 1.2), (x, 2.26, 1.26)], 0.025, segments=8)
    p.tube(D, [(-0.42, 2.42, 1.06), (0.42, 2.42, 1.06)], 0.022, segments=8)
    plate(p, look, 'D-2 0417', 0.0, 2.34, 0.6, 1)
    plate(p, look, 'D-2 0417', -0.5, -2.26, 0.62, -1)
    # The spare on the back door.
    wheel(p, look, 0.0, 0.0, radius, width, 1, style='steel', lugs=16) if False else None
    # On the roof: a rack, a bar of lamps, the aerial.
    p.tube(D, [(-0.8, 0.3, 2.04), (0.8, 0.3, 2.04), (0.8, -1.8, 2.04), (-0.8, -1.8, 2.04)], 0.016, segments=6, closed=True)
    for y in (0.3, -0.75, -1.8):
        for x in (-0.8, 0.8):
            p.tube(D, [(x, y, 1.95), (x, y, 2.04)], 0.014, segments=6)
        p.tube(D, [(-0.8, y, 2.04), (0.8, y, 2.04)], 0.012, segments=6)
    p.box(D, (-0.62, 0.34, 1.98), (0.62, 0.46, 2.1))
    for i in range(4):
        x = -0.45 + i * 0.3
        p.box(M['lens'], (x - 0.11, 0.455, 2.0), (x + 0.11, 0.468, 2.085))
    p.box(M['army_dark'], (-0.5, -1.5, 2.05), (0.3, -0.5, 2.3))
    p.box(M['canvas'], (-0.52, -1.52, 2.06), (0.32, -0.48, 2.32))
    p.cylinder(D, 0.03, 0.12, centre=(0.78, -1.9, 2.0), axis='Z', segments=8)
    p.tube(D, [(0.78, -1.9, 2.06), (0.78, -1.93, 3.1), (0.78, -2.0, 4.0)], 0.007, segments=5)
    # Snorkel up the screen pillar.
    p.tube(D, [(half + 0.03, 1.5, 1.2), (half + 0.06, 0.95, 1.3), (half + 0.06, 0.6, 1.98), (half + 0.06, 0.62, 2.12)], 0.045, segments=8)
    parts = p.finish(bevel=0.008, bevel_segments=2, smooth_angle=40)

    w = bl.Builder(name + '_wheels')
    for axle in axles:
        for side in (1, -1):
            wheel(w, look, side * track, axle, radius, width, side, style='steel', lugs=16)
    # The spare, flat against the back door.
    spare = bl.Builder(name + '_spare')
    wheel(spare, look, 0.0, 0.0, radius, width, 1, style='steel', lugs=16)
    spare_obj = spare.finish(bevel=0.0, smooth_angle=40)
    bl.transform_mesh(spare_obj, Matrix.Translation((0.25, -2.12 - width / 2 - 0.02, 1.22))
                      @ Matrix.Rotation(math.radians(-90), 4, 'Z') @ Matrix.Translation((0, 0, -radius)))
    wheels = w.finish(bevel=0.0, smooth_angle=40)
    return bl.join([body, parts, wheels, spare_obj], name)


# ---------------------------------------------------------------------------------------------

def register(only):
    def add(name, function):
        if only and name not in only:
            return
        BUILT[name] = function()
        print('built', name, len(BUILT[name].data.polygons), 'faces')

    for colour in ('blue', 'white', 'maroon', 'silver'):
        add('sedan_' + colour, lambda c=colour: car('sedan_' + c, SEDAN, look_of(c)))
    add('sedan_burnt', lambda: car('sedan_burnt', SEDAN, burnt_look()))
    for colour in ('red', 'tan'):
        add('pickup_' + colour, lambda c=colour: car('pickup_' + c, PICKUP, look_of(c)))
    add('pickup_burnt', lambda: car('pickup_burnt', PICKUP, burnt_look()))
    for colour in ('white', 'green'):
        add('van_' + colour, lambda c=colour: car('van_' + c, VAN, look_of(c)))
    add('truck_cargo', lambda: truck('truck_cargo', 'cargo'))
    add('truck_jammer', lambda: truck('truck_jammer', 'jammer'))
    add('truck_jammer_wreck', lambda: truck('truck_jammer_wreck', 'jammer', wreck=True))
    add('patrol', lambda: patrol('patrol'))


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    only = args[args.index('--only') + 1].split(',') if '--only' in args else None
    bl.reset()
    materials()
    register(only)
    if '--preview' in args:
        names = list(BUILT)
        for start in range(0, len(names), 3):
            shown = [BUILT[name] for name in names[start:start + 3]]
            x = 0.0
            for obj in shown:
                half = max(obj.dimensions.x, 1.0) / 2
                x += half
                obj.location = (x, 0, 0)
                x += half + 1.0
            bpy.context.view_layer.update()
            stem = os.path.join(bl.ROOT, 'build', 'previews', f'vehicles_{start // 3}')
            preview.render(stem + '.png', shown, views=[(35, 14), (215, 20)], size=(1800, 900), samples=32, zoom=1.5,
                           ground=True)
            for obj in shown:
                obj.location = (0, 0, 0)
            bpy.context.view_layer.update()
    if '--no-export' not in args:
        bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'vehicles.glb'), list(BUILT.values()))
    print('vehicles:', ' '.join(BUILT))


main()
