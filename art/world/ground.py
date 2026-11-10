"""The ground of Alder Ridge: its roads, kerbs, pavements, drives and lawns as one surface cut
to the plan in art/levels/alder_layout.py, and the far country round it.

    blender --background --factory-startup --python art/world/ground.py -- [--preview]

Writes build/kits/alder_ground.glb: one part for each material (`ground_asphalt`,
`ground_lawn`...), so that each can say what it is underfoot, and `ground_far`.
The parts share one origin: place them all at 0 0 0.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'levels'))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector, noise  # noqa: E402

import alder_layout as plan  # noqa: E402
from lib import bl, preview, regions  # noqa: E402

CELL = 2.0
M = {}


def materials():
    M.update(
        lawn=bl.material('lawn', 'lawn'),
        asphalt=bl.material('asphalt', 'asphalt'),
        asphalt_patch=bl.material('asphalt_patch', 'asphalt', tint=(0.62, 0.62, 0.64)),
        sidewalk=bl.material('sidewalk', 'sidewalk'),
        concrete=bl.material('concrete', 'concrete'),
        gravel=bl.material('gravel', 'gravel'),
        dirt=bl.material('dirt', 'dirt'),
        mark_white=bl.material('road_paint_white', 'plaster', tint=(0.72, 0.72, 0.7)),
        mark_yellow=bl.material('road_paint_yellow', 'plaster', tint=(0.74, 0.55, 0.08)),
        far=bl.material('lawn_far', 'lawn', tint=(0.62, 0.7, 0.5)),
    )


def flat_ground():
    """A grid over the plan's bounds, in Blender's axes: X east, Y north."""
    x0, z0, x1, z1 = plan.BOUNDS
    columns = int(round((x1 - x0) / CELL))
    rows = int(round((z1 - z0) / CELL))
    bm = bmesh.new()
    verts = [[bm.verts.new((x0 + i * CELL, -(z0 + j * CELL), 0.0)) for i in range(columns + 1)] for j in range(rows + 1)]
    for j in range(rows):
        for i in range(columns):
            bm.faces.new((verts[j][i], verts[j + 1][i], verts[j + 1][i + 1], verts[j][i + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if bm.faces and next(iter(bm.faces)).normal.z < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new('ground')
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(M['lawn'])
    obj = bpy.data.objects.new('ground', mesh)
    bl.link(obj)
    return obj


def cut_to_plan(obj):
    """Paints every region of the plan onto the grid. Ramps take a material of their own for
    now, so that they can be told from the level ground they are made of."""
    painter = regions.Painter(obj, margin=CELL * 0.75)
    levels = {M['lawn'].name: plan.HIGH}
    for region in plan.REGIONS:
        material = M[region['material']]
        if region['level'] == plan.RAMP:
            name = 'ramp:' + material.name
            ramp = bpy.data.materials.get(name)
            if ramp is None:
                ramp = material.copy()
                ramp.name = name
            material = ramp
        levels[material.name] = region['level']
        polygon = [(x, -z) for x, z in region['polygon']]
        keep = None
        if region['clip'] is not None:
            cx0, cz0, cx1, cz1 = region['clip']
            keep = lambda c, n, a=cx0, b=cx1, lo=-cz1, hi=-cz0: a - 1e-4 <= c.x <= b + 1e-4 and lo - 1e-4 <= c.y <= hi + 1e-4  # noqa: E731
        painter.paint(material, polygon, 'Z', keep)
    painter.finish()
    return levels


def terrace(obj, levels):
    """Drops the roadway below the kerb: every face goes to the height of its level, and a
    wall is built wherever two neighbours no longer meet. A ramp's corners that touch the
    roadway go down to it, the rest stay up."""
    source = bmesh.new()
    source.from_mesh(obj.data)
    source.verts.ensure_lookup_table()
    names = [m.name for m in obj.data.materials]
    level_of = [levels.get(name, plan.HIGH) for name in names]
    touches_low = [any(level_of[f.material_index] == plan.LOW for f in v.link_faces) for v in source.verts]

    def corner_height(face, vert):
        level = level_of[face.material_index]
        if level == plan.LOW:
            return 0.0
        if level == plan.RAMP and touches_low[vert.index]:
            return 0.0
        return plan.KERB

    out = bmesh.new()
    made = {}

    def corner(face, vert):
        key = (vert.index, corner_height(face, vert))
        if key not in made:
            made[key] = out.verts.new((vert.co.x, vert.co.y, key[1]))
        return made[key]

    for face in source.faces:
        try:
            new = out.faces.new([corner(face, v) for v in face.verts])
        except ValueError:
            continue
        new.material_index = face.material_index
    kerb = bl.slot(obj, M['sidewalk'])
    walls = []
    for edge in source.edges:
        if len(edge.link_faces) != 2:
            continue
        f1, f2 = edge.link_faces
        a, b = edge.verts
        loop = [corner(f1, a), corner(f1, b), corner(f2, b), corner(f2, a)]
        unique = []
        for vert in loop:
            if vert not in unique:
                unique.append(vert)
        if len(unique) < 3:
            continue
        try:
            wall = out.faces.new(unique)
        except ValueError:
            continue
        wall.material_index = kerb
        walls.append(wall)
    source.free()
    bmesh.ops.recalc_face_normals(out, faces=list(out.faces))
    up = sum(1 for f in out.faces if f.normal.z > 0.5)
    down = sum(1 for f in out.faces if f.normal.z < -0.5)
    if down > up:
        bmesh.ops.reverse_faces(out, faces=list(out.faces))
    out.to_mesh(obj.data)
    out.free()
    obj.data.update()
    # Ramps are of the material they were copied from.
    mesh = obj.data
    for index, material in enumerate(list(mesh.materials)):
        if material.name.startswith('ramp:'):
            real = bl.slot(obj, bpy.data.materials[material.name[5:]])
            for polygon in mesh.polygons:
                if polygon.material_index == index:
                    polygon.material_index = real
    return len(walls)


def split_by_material(obj):
    """One object for each material in use, named for it."""
    parts = []
    mesh = obj.data
    used = sorted({polygon.material_index for polygon in mesh.polygons})
    for index in used:
        material = mesh.materials[index]
        if material.name.startswith('ramp:'):
            continue
        key = next(k for k, m in M.items() if m == material)
        part = bl.duplicate(obj, 'ground_' + key)
        bm = bmesh.new()
        bm.from_mesh(part.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != index], context='FACES')
        bm.to_mesh(part.data)
        bm.free()
        part.data.materials.clear()
        part.data.materials.append(material)
        for polygon in part.data.polygons:
            polygon.material_index = 0
        parts.append(part)
    return parts


def far_country():
    """The land beyond the town: level near at hand, rising to the wooded ridge it is named
    for. It lies just under the town's own ground wherever that reaches."""
    x0, z0, x1, z1 = plan.BOUNDS
    reach = 900.0
    step = 12.0
    count = int(reach * 2 / step)
    bm = bmesh.new()
    grid = []
    for j in range(count + 1):
        row = []
        for i in range(count + 1):
            x = -reach + 65.0 + i * step
            z = -reach - 20.0 + j * step
            inside = x0 + 1.0 < x < x1 - 1.0 and z0 + 1.0 < z < z1 - 1.0
            # How far outside the town's edge this is.
            dx = max(x0 - 60.0 - x, 0.0, x - (x1 + 60.0))
            dz = max(z0 - 60.0 - z, 0.0, z - (z1 + 60.0))
            away = math.hypot(dx, dz)
            rise = min(away / 520.0, 1.0)
            rise = rise * rise * (3 - 2 * rise)
            lumps = noise.noise(Vector((x * 0.004, z * 0.004, 0.3))) * 0.5 + 0.5
            ridges = noise.noise(Vector((x * 0.011, z * 0.011, 4.7))) * 0.5 + 0.5
            hill = rise * (38.0 + 95.0 * lumps + 30.0 * ridges * rise)
            # The ridge stands highest to the north and east; the south-west opens to the valley.
            bearing = math.atan2(-z, x)
            hill *= 0.55 + 0.45 * math.cos(bearing - math.radians(60))
            height = -0.35 if inside else plan.KERB - 0.02 + hill + min(away, 40.0) * 0.004
            row.append(bm.verts.new((x, -z, height)))
        grid.append(row)
    for j in range(count):
        for i in range(count):
            bm.faces.new((grid[j][i], grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if sum(f.normal.z for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new('ground_far')
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(M['far'])
    obj = bpy.data.objects.new('ground_far', mesh)
    bl.link(obj)
    bl.box_uv(obj)
    bl.shade(obj, 60)
    return obj


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    bl.reset()
    materials()
    ground = flat_ground()
    levels = cut_to_plan(ground)
    print('cut:', len(ground.data.polygons), 'faces')
    walls = terrace(ground, levels)
    print('terraced:', walls, 'kerb faces')
    bl.box_uv(ground)
    bl.shade(ground, 35)
    parts = split_by_material(ground)
    bpy.data.objects.remove(ground)
    far = far_country()
    for part in parts:
        print(' ', part.name, len(part.data.polygons), 'faces')
    if '--preview' in args:
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', 'ground.png'), parts, views=[(0, 89.9), (150, 30)],
                       size=(2000, 1500), samples=24, zoom=1.35)
    bl.export_glb(os.path.join(bl.ROOT, 'build', 'kits', 'alder_ground.glb'), parts + [far])
    print('ground:', ' '.join(part.name for part in parts + [far]))


main()
