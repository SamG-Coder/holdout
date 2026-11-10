"""The people of HOLDOUT, made with MakeHuman's Blender plugin (MPFB 2, CC0 assets) and dressed
in equipment built here to fit them.

    blender --background --python art/characters/people.py -- KIND OUT.blend [--preview]

KIND is one of:
  soldier   a Directorate rifleman: field uniform, helmet, balaclava and goggles, plate carrier
  rebel_a   a resistance fighter in a padded jacket and jeans, beanie and chest rig
  rebel_b   another, in a work shirt and cap
  arms      the player's own arms, for the first-person view: sleeves and gloved hands

The .blend then goes through the engine's export tool (tools/blender/solstice_export.py), which
bakes its materials and checks it: see art/build_characters.py.

MakeHuman's people face -Y here, with +X to their left, in metres.
"""

import glob
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from lib import bake, bl, preview, tex  # noqa: E402

TEX = os.path.join(bl.ROOT, 'build', 'tex', 'people')


# ---------------------------------------------------------------------------------------------
# Making the person
# ---------------------------------------------------------------------------------------------

def make_human(name, body, skin, clothes, extras=()):
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
    from bl_ext.blender_org.mpfb.services.locationservice import LocationService
    data = LocationService.get_user_data()

    def asset(pattern):
        found = sorted(glob.glob(os.path.join(data, pattern)))
        if not found:
            sys.exit(f'people.py: no MPFB asset matches {pattern}: install the system assets')
        return found[0]

    for thing in list(bpy.data.objects):
        bpy.data.objects.remove(thing)
    basemesh = HumanService.create_human(macro_detail_dict=body)
    basemesh.name = name
    HumanService.add_builtin_rig(basemesh, 'game_engine')
    HumanService.set_character_skin(asset(f'skins/{skin}/*.mhmat'), basemesh, skin_type='ENHANCED_SSS',
                                    material_instances=True)
    for kind, pattern in extras:
        HumanService.add_mhclo_asset(asset(pattern), basemesh, asset_type=kind, subdiv_levels=0,
                                     material_type='MAKESKIN')
    for item in clothes:
        HumanService.add_mhclo_asset(asset(f'clothes/{item}/*.mhclo'), basemesh, asset_type='Clothes',
                                     subdiv_levels=0, material_type='MAKESKIN')
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    # The body's shape is a mix of shape keys: bake it in, so the mesh can be cut and copied.
    if basemesh.data.shape_keys:
        bl.select_only([basemesh])
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    return basemesh, rig


def find(part):
    return next(o for o in bpy.data.objects if o.type == 'MESH' and part in o.name)


def weights(obj, bones):
    """Each vertex's summed weight to the bones named (exactly, or by prefix ending in `*`)."""
    wanted = set()
    for group in obj.vertex_groups:
        for bone in bones:
            if group.name == bone or (bone.endswith('*') and group.name.startswith(bone[:-1])):
                wanted.add(group.index)
    out = [0.0] * len(obj.data.vertices)
    for vertex in obj.data.vertices:
        out[vertex.index] = sum(g.weight for g in vertex.groups if g.group in wanted)
    return out


def in_group(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        return set()
    return {v.index for v in obj.data.vertices if any(g.group == group.index and g.weight > 0.5 for g in v.groups)}


def shell(source, keep, name, material, offset=0.003, smooth=0, rig=None):
    """A new object from the faces of `source` whose vertices `keep(vertex)` accepts, pushed
    out along their normals: a second skin that bends as the first does, since it keeps every
    weight."""
    copy = source.copy()
    copy.data = source.data.copy()
    copy.name = name
    copy.data.name = name
    bpy.context.scene.collection.objects.link(copy)
    for modifier in list(copy.modifiers):
        if modifier.type != 'ARMATURE':
            copy.modifiers.remove(modifier)
    kept = {v.index for v in source.data.vertices if keep(v)}
    bm = bmesh.new()
    bm.from_mesh(copy.data)
    doomed = [f for f in bm.faces if not all(v.index in kept for v in f.verts)]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    for _ in range(smooth):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    for vertex in bm.verts:
        vertex.co += vertex.normal * offset
    bm.to_mesh(copy.data)
    bm.free()
    copy.data.materials.clear()
    copy.data.materials.append(material)
    for polygon in copy.data.polygons:
        polygon.material_index = 0
        polygon.use_smooth = True
    return copy


def remove_faces(obj, doomed_vertex):
    """Deletes the faces of `obj` that touch only vertices `doomed_vertex(vertex)` accepts: skin
    that a glove or a mask now covers."""
    doomed = {v.index for v in obj.data.vertices if doomed_vertex(v)}
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    faces = [f for f in bm.faces if all(v.index in doomed for v in f.verts)]
    bmesh.ops.delete(bm, geom=faces, context='FACES')
    bm.to_mesh(obj.data)
    bm.free()


def bind(obj, rig, bone):
    """Hangs a rigid piece of equipment from one bone."""
    obj.parent = rig
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    group = obj.vertex_groups.new(name=bone)
    group.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')
    modifier = obj.modifiers.new('Armature', 'ARMATURE')
    modifier.object = rig
    return obj


def ellipse_at(obj, z, band=0.012, bones=None, limit_x=None):
    """The ellipse that fits round a mesh at a height: its centre and half-widths in X and Y."""
    weight = weights(obj, bones) if bones else None
    xs, ys = [], []
    for vertex in obj.data.vertices:
        if abs(vertex.co.z - z) > band:
            continue
        if weight is not None and weight[vertex.index] < 0.5:
            continue
        if limit_x is not None and abs(vertex.co.x) > limit_x:
            continue
        xs.append(vertex.co.x)
        ys.append(vertex.co.y)
    if len(xs) < 6:
        raise ValueError(f'nothing of {obj.name} at height {z}')
    return ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5), (max(xs) - min(xs)) * 0.5, (max(ys) - min(ys)) * 0.5


def band(builder, mat, low, high, start, end, thickness, grow=0.0, segments=28):
    """A curved slab wrapped part of the way round a body: from the ellipse `low` =
    (z, (cx, cy), rx, ry) to the ellipse `high`, between the angles `start` and `end` in degrees
    (0 is the front, 90 the body's left), `grow` metres out from the ellipse and `thickness`
    thick. A full turn makes a closed belt."""
    full = abs((end - start) - 360.0) < 1e-6

    def point(ellipse, angle, out):
        z, (cx, cy), rx, ry = ellipse
        a = math.radians(angle)
        return Vector((cx + (rx + out) * math.sin(a), cy - (ry + out) * math.cos(a), z))

    steps = max(int(segments * abs(end - start) / 360.0), 2)
    angles = [start + (end - start) * i / steps for i in range(steps + 1)]
    inner, outer = grow, grow + thickness
    for a0, a1 in zip(angles, angles[1:]):
        builder.quad(mat, point(low, a0, outer), point(low, a1, outer), point(high, a1, outer), point(high, a0, outer))
        builder.quad(mat, point(low, a1, inner), point(low, a0, inner), point(high, a0, inner), point(high, a1, inner))
        builder.quad(mat, point(high, a0, outer), point(high, a1, outer), point(high, a1, inner), point(high, a0, inner))
        builder.quad(mat, point(low, a1, outer), point(low, a0, outer), point(low, a0, inner), point(low, a1, inner))
    if not full:
        for angle, flip in ((start, False), (end, True)):
            corners = [point(low, angle, inner), point(low, angle, outer), point(high, angle, outer), point(high, angle, inner)]
            builder.quad(mat, *(reversed(corners) if flip else corners))


def on_ellipse(ellipse, angle, out=0.0):
    """A place on a body's ellipse, and the turn that faces a box there outward."""
    z, (cx, cy), rx, ry = ellipse
    a = math.radians(angle)
    position = Vector((cx + (rx + out) * math.sin(a), cy - (ry + out) * math.cos(a), z))
    return Matrix.Translation(position) @ Matrix.Rotation(a, 4, 'Z')


def ribbon(builder, mat, points, width, thickness, up=(0, 0, 1)):
    """A flat strap along a path: `width` across, `thickness` deep."""
    points = [Vector(p) for p in points]
    up = Vector(up)
    rings = []
    for i, point in enumerate(points):
        before = points[max(i - 1, 0)]
        after = points[min(i + 1, len(points) - 1)]
        tangent = (after - before).normalized()
        side = tangent.cross(up)
        if side.length < 1e-5:
            side = tangent.cross(Vector((0, 1, 0)))
        side.normalize()
        normal = side.cross(tangent).normalized()
        rings.append([point + side * width * 0.5 + normal * thickness * 0.5,
                      point - side * width * 0.5 + normal * thickness * 0.5,
                      point - side * width * 0.5 - normal * thickness * 0.5,
                      point + side * width * 0.5 - normal * thickness * 0.5])
    for a, b in zip(rings, rings[1:]):
        for k in range(4):
            builder.quad(mat, a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k])
    builder.quad(mat, *reversed(rings[0]))
    builder.quad(mat, *rings[-1])


def finish(builder, bevel=0.0015, segments=2, smooth_angle=40):
    obj = builder.finish(bevel=bevel, bevel_segments=segments, smooth_angle=smooth_angle, uv=False)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def slot(name, colour=(0.5, 0.5, 0.5)):
    return bl.material(name, flat=(colour, 0.6, 0.0))


def eye_height(basemesh):
    points = [basemesh.data.vertices[i].co for i in in_group(basemesh, 'joint-l-eye')]
    if points:
        centre = sum(points, Vector()) / len(points)
        return centre.z, centre.y, abs(centre.x)
    head = bpy.data.objects[basemesh.parent.name].data.bones['head']
    return head.head_local.z + 0.085, head.head_local.y - 0.085, 0.032


def head_ellipse(basemesh, z):
    return ellipse_at(basemesh, z, band=0.012, bones=['head'])


# ---------------------------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------------------------

def helmet(basemesh, rig, mats, cover='helmet'):
    """A ballistic helmet sized to the head, with its rim, side rails, shroud and chin strap."""
    eye_z, eye_y, _ = eye_height(basemesh)
    (cx, cy), rx, ry = head_ellipse(basemesh, eye_z + 0.03)
    body = in_group(basemesh, 'body')
    head_weight = weights(basemesh, ['head'])
    top = max(v.co.z for v in basemesh.data.vertices if v.index in body and head_weight[v.index] > 0.5)
    centre = Vector((cx, cy + 0.004, eye_z + 0.028))
    radii = Vector((rx + 0.021, ry + 0.022, top - centre.z + 0.019))
    b = bl.Builder('helmet')
    b.sphere(mats[cover], 1.0, centre=centre, segments=36, rings=22, scale=radii)
    obj = b.finish(uv=False, smooth_angle=60)
    # Cut it off at the brow, lower at the back.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    normal = Vector((0.0, -0.34, -1.0)).normalized()
    cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                                 plane_co=Vector((0, cy, eye_z + 0.016)), plane_no=normal, clear_outer=True)
    del cut
    bm.to_mesh(obj.data)
    bm.free()
    solid = obj.modifiers.new('solid', 'SOLIDIFY')
    solid.thickness = 0.011
    solid.offset = -1.0
    bl.apply_modifiers(obj)
    bl.add_bevel(obj, 0.0025, 3)
    bl.shade(obj, 50)

    b = bl.Builder('helmet_fittings')
    hard, strap = mats['hard'], mats['strap']
    # The shroud on the brow for a night-vision mount.
    b.box(hard, (-0.022, centre.y - radii.y - 0.006, centre.z + 0.028), (0.022, centre.y - radii.y + 0.012, centre.z + 0.074))
    b.box(hard, (-0.012, centre.y - radii.y - 0.010, centre.z + 0.036), (0.012, centre.y - radii.y - 0.004, centre.z + 0.066))
    # Rails along both sides, and the band that holds goggles.
    for side in (-1, 1):
        b.box(hard, (side * (radii.x - 0.004) - 0.005, centre.y - 0.060, centre.z + 0.018),
              (side * (radii.x - 0.004) + 0.005, centre.y + 0.050, centre.z + 0.034))
        for y in (-0.045, -0.005, 0.035):
            b.cylinder(hard, 0.004, 0.012, centre=(side * (radii.x - 0.001), centre.y + y, centre.z + 0.026), axis='X', segments=10)
    # Chin strap: down from each side, under the chin.
    chin_z = eye_z - 0.118
    path = [(radii.x - 0.012, centre.y + 0.01, eye_z + 0.012), (rx * 0.92, cy - 0.02, eye_z - 0.06),
            (rx * 0.5, cy - ry * 0.72, chin_z), (0.0, cy - ry * 0.86, chin_z - 0.006)]
    path = path + [(-x, y, z) for x, y, z in reversed(path[:-1])]
    ribbon(b, strap, path, 0.016, 0.003, up=(0, -1, 0.2))
    b.box(hard, (-0.016, cy - ry * 0.9, chin_z - 0.016), (0.016, cy - ry * 0.80, chin_z + 0.006))
    fittings = finish(b, bevel=0.0015)
    return [bind(obj, rig, 'head'), bind(fittings, rig, 'head')], (centre, radii)


def goggles(basemesh, rig, mats):
    """Dust goggles: a dark curved lens in a frame, on a strap round the head."""
    eye_z, _, _ = eye_height(basemesh)
    centre, rx, ry = head_ellipse(basemesh, eye_z)
    b = bl.Builder('goggles')
    low = (eye_z - 0.028, centre, rx, ry)
    high = (eye_z + 0.027, centre, rx, ry)
    band(b, mats['hard'], low, high, -62, 62, 0.014, grow=0.004, segments=64)
    lens_low = (eye_z - 0.021, centre, rx, ry)
    lens_high = (eye_z + 0.020, centre, rx, ry)
    band(b, mats['lens'], lens_low, lens_high, -52, 52, 0.004, grow=0.0165, segments=64)
    band(b, mats['strap'], (eye_z - 0.014, centre, rx, ry), (eye_z + 0.014, centre, rx, ry), 60, 300, 0.003,
         grow=0.006, segments=48)
    return [bind(finish(b, bevel=0.002, segments=3), rig, 'head')]


def plate_carrier(suit, rig, mats, pouches=True):
    """A plate carrier fitted to the torso: plates front and back, a cummerbund, shoulder
    straps, and its pouches: magazines across the belly, a radio, a medical kit."""
    spine = ['spine_01', 'spine_02', 'spine_03', 'pelvis']
    bones = rig.data.bones
    chest_z = bones['spine_03'].tail_local.z + 0.055
    waist_z = bones['spine_01'].head_local.z + 0.035
    mid_z = (chest_z + waist_z) * 0.5
    chest = (chest_z,) + ellipse_at(suit, chest_z - 0.03, bones=spine, limit_x=0.2)
    waist = (waist_z,) + ellipse_at(suit, waist_z, bones=spine, limit_x=0.2)
    middle = (mid_z,) + ellipse_at(suit, mid_z, bones=spine, limit_x=0.2)
    fabric, hard, strap = mats['vest'], mats['hard'], mats['strap']
    b = bl.Builder('carrier')
    # Plate bags, front and back, and the cummerbund between them.
    band(b, fabric, middle, chest, -44, 44, 0.028, grow=0.008)
    band(b, fabric, waist, middle, -40, 40, 0.026, grow=0.008)
    band(b, fabric, middle, chest, 136, 224, 0.028, grow=0.008)
    band(b, fabric, waist, middle, 140, 220, 0.026, grow=0.008)
    band(b, fabric, waist, (mid_z - 0.01,) + middle[1:], 0, 360, 0.012, grow=0.004, segments=40)
    carrier = finish(b, bevel=0.006, segments=3, smooth_angle=50)

    b = bl.Builder('carrier_fittings')
    # Shoulder straps over to the back plate.
    shoulder_z = bones['clavicle_l'].head_local.z + 0.045
    for side in (-1, 1):
        x = side * 0.092
        front = on_ellipse(chest, side * 26, 0.02).translation
        back = on_ellipse(chest, 180 - side * 26, 0.02).translation
        top = Vector((x, (front.y + back.y) * 0.5, shoulder_z))
        ribbon(b, strap, [front, front.lerp(top, 0.6) + Vector((0, -0.02, 0.012)), top,
                          back.lerp(top, 0.6) + Vector((0, 0.02, 0.012)), back], 0.05, 0.008, up=(side, 0, 0))
    # Webbing rows across the front, for things to hang from.
    for row in range(3):
        z = waist_z + 0.03 + row * 0.04
        level = (z,) + waist[1:]
        band(b, strap, level, (z + 0.022,) + waist[1:], -38, 38, 0.003, grow=0.035, segments=40)
    if pouches:
        mag, tan = mats['pouch'], mats['mag']
        # Three magazine pouches across the belly, a magazine standing in each.
        for angle in (-24, 0, 24):
            place = on_ellipse((waist_z + 0.075,) + waist[1:], angle, 0.036)
            b.box(mag, (-0.036, -0.036, -0.062), (0.036, 0.0, 0.058), matrix=place)
            b.box(tan, (-0.030, -0.027, 0.058), (0.030, -0.006, 0.086), matrix=place)
            b.box(strap, (-0.012, -0.040, -0.02), (0.012, -0.034, 0.07), matrix=place)
        # A flat pouch high on the chest.
        place = on_ellipse((chest_z - 0.075,) + chest[1:], 0, 0.036)
        b.box(mag, (-0.075, -0.022, -0.045), (0.075, 0.0, 0.045), matrix=place)
        b.box(hard, (-0.02, -0.025, 0.02), (0.02, -0.021, 0.032), matrix=place)
        # The radio on the left of the back, with its aerial.
        place = on_ellipse((mid_z + 0.02,) + middle[1:], 118, 0.02)
        b.box(mag, (-0.035, -0.045, -0.085), (0.035, 0.0, 0.07), matrix=place)
        b.box(hard, (-0.028, -0.038, 0.07), (0.028, -0.006, 0.105), matrix=place)
        b.cylinder(hard, 0.0035, 0.26, centre=(0.018, -0.022, 0.235), axis='Z', segments=8, matrix=place)
        b.cylinder(hard, 0.007, 0.02, centre=(-0.014, -0.022, 0.112), axis='Z', segments=12, matrix=place)
        # A medical kit on the right hip, and a pack low on the back plate.
        place = on_ellipse((waist_z + 0.05,) + waist[1:], -96, 0.02)
        b.box(mag, (-0.05, -0.05, -0.06), (0.05, 0.0, 0.06), matrix=place)
        b.box(mats['red'], (-0.014, -0.052, 0.012), (0.014, -0.049, 0.02), matrix=place)
        b.box(mats['red'], (-0.004, -0.052, 0.002), (0.004, -0.049, 0.03), matrix=place)
        place = on_ellipse((mid_z,) + middle[1:], 180, 0.036)
        b.box(mag, (-0.115, -0.07, -0.13), (0.115, 0.0, 0.13), matrix=place)
        b.box(strap, (-0.12, -0.074, 0.02), (0.12, -0.068, 0.04), matrix=place)
        b.box(strap, (-0.12, -0.074, -0.07), (0.12, -0.068, -0.05), matrix=place)
    fittings = finish(b, bevel=0.004, segments=3, smooth_angle=50)
    return [bind(carrier, rig, 'spine_03'), bind(fittings, rig, 'spine_03')]


def chest_rig(suit, rig, mats):
    """A light chest rig: a panel of magazine pouches on a harness."""
    spine = ['spine_01', 'spine_02', 'spine_03', 'pelvis']
    bones = rig.data.bones
    top_z = bones['spine_03'].head_local.z + 0.11
    low_z = bones['spine_02'].head_local.z + 0.0
    top = (top_z,) + ellipse_at(suit, top_z, bones=spine, limit_x=0.2)
    low = (low_z,) + ellipse_at(suit, low_z, bones=spine, limit_x=0.2)
    fabric, strap = mats['vest'], mats['strap']
    b = bl.Builder('chest_rig')
    band(b, fabric, low, top, -50, 50, 0.014, grow=0.008)
    band(b, strap, (low_z + 0.03,) + low[1:], (low_z + 0.07,) + low[1:], 48, 312, 0.004, grow=0.008, segments=40)
    for angle in (-30, -10, 10, 30):
        place = on_ellipse(((low_z + top_z) * 0.5 - 0.01,) + low[1:], angle, 0.022)
        b.box(mats['pouch'], (-0.034, -0.034, -0.065), (0.034, 0.0, 0.05), matrix=place)
        b.box(mats['mag'], (-0.028, -0.026, 0.05), (0.028, -0.006, 0.076), matrix=place)
    shoulder_z = bones['clavicle_l'].head_local.z + 0.04
    chest = (bones['spine_03'].tail_local.z + 0.02,) + ellipse_at(suit, bones['spine_03'].tail_local.z, bones=spine, limit_x=0.2)
    for side in (-1, 1):
        front = on_ellipse(top, side * 30, 0.012).translation
        back = on_ellipse((low_z + 0.05,) + low[1:], 180 - side * 20, 0.012).translation
        over = Vector((side * 0.085, (front.y + back.y) * 0.5, shoulder_z))
        up_front = on_ellipse(chest, side * 24, 0.014).translation
        up_back = on_ellipse(chest, 180 - side * 24, 0.014).translation
        ribbon(b, strap, [front, up_front, over, up_back, back], 0.04, 0.005, up=(side, 0, 0))
    return [bind(finish(b, bevel=0.004, segments=3, smooth_angle=50), rig, 'spine_03')]


def belt_and_holster(suit, rig, mats):
    """A duty belt, with a pistol holstered on the right thigh."""
    bones = rig.data.bones
    z = bones['pelvis'].tail_local.z - 0.012
    waist = ellipse_at(suit, z, bones=['pelvis', 'spine_01', 'thigh_l', 'thigh_r'], limit_x=0.22)
    b = bl.Builder('belt')
    band(b, mats['strap'], (z - 0.024,) + waist, (z + 0.024,) + waist, 0, 360, 0.006, grow=0.004, segments=44)
    place = on_ellipse((z,) + waist, 0, 0.012)
    b.box(mats['hard'], (-0.024, -0.008, -0.02), (0.024, 0.0, 0.02), matrix=place)
    belt = bind(finish(b, bevel=0.002), rig, 'pelvis')

    thigh = bones['thigh_r']
    top = thigh.head_local
    direction = (thigh.tail_local - thigh.head_local).normalized()
    at = top + direction * 0.17 + Vector((-0.085, 0.0, 0.0))
    turn = Matrix.Translation(at) @ direction.to_track_quat('-Z', 'Y').to_matrix().to_4x4()
    b = bl.Builder('holster')
    b.box(mats['hard'], (-0.018, -0.04, -0.105), (0.018, 0.045, 0.055), matrix=turn)
    b.box(mats['pistol'], (-0.014, 0.01, 0.055), (0.014, 0.05, 0.12), matrix=turn)
    b.box(mats['pistol'], (-0.014, -0.045, 0.085), (0.014, 0.05, 0.11), matrix=turn)
    # Straps round the thigh.
    for along in (0.13, 0.22):
        centre = top + direction * along
        points = [centre + Vector((0.088 * math.cos(math.tau * i / 16), 0.088 * math.sin(math.tau * i / 16), 0))
                  for i in range(17)]
        ribbon(b, mats['strap'], points, 0.03, 0.004, up=(0, 0, 1))
    # The drop from the belt.
    ribbon(b, mats['strap'], [at + Vector((0.0, 0, 0.06)), Vector((waist[0][0] - waist[1] - 0.008, at.y, z - 0.01))],
           0.045, 0.004, up=(0, 1, 0))
    holster = bind(finish(b, bevel=0.003, segments=3), rig, 'thigh_r')
    return [belt, holster]


def knee_pads(rig, mats):
    out = []
    for side in ('l', 'r'):
        knee = rig.data.bones[f'calf_{side}'].head_local
        centre = (knee.x, knee.y + 0.012)
        b = bl.Builder(f'kneepad_{side}')
        band(b, mats['hard'], (knee.z - 0.045, centre, 0.056, 0.064), (knee.z + 0.062, centre, 0.062, 0.068), -66, 66,
             0.011, grow=0.004, segments=40)
        for dz in (-0.022, 0.04):
            band(b, mats['strap'], (knee.z + dz - 0.011, centre, 0.056, 0.064), (knee.z + dz + 0.011, centre, 0.058, 0.066),
                 64, 296, 0.003, grow=0.003, segments=30)
        out.append(bind(finish(b, bevel=0.005, segments=3, smooth_angle=60), rig, f'calf_{side}'))
    return out


def boot_shafts(rig, mats):
    """The legs of tall boots, over the shoes: laced leather to mid-calf."""
    out = []
    for side in ('l', 'r'):
        calf = rig.data.bones[f'calf_{side}']
        ankle, knee = calf.tail_local, calf.head_local
        b = bl.Builder(f'boot_{side}')
        low = ankle + (knee - ankle) * -0.02
        high = ankle + (knee - ankle) * 0.42
        band(b, mats['boot'], (low.z, (low.x, low.y + 0.014), 0.062, 0.078), (high.z, (high.x, high.y + 0.016), 0.07, 0.08),
             0, 360, 0.005, grow=0.004, segments=28)
        for i in range(5):
            t = 0.12 + i * 0.19
            at = low + (high - low) * t
            b.box(mats['strap'], (at.x - 0.022, at.y - 0.076 - 0.004 * t, at.z - 0.003), (at.x + 0.022, at.y - 0.066, at.z + 0.003))
        out.append(bind(finish(b, bevel=0.002, smooth_angle=60), rig, f'calf_{side}'))
    return out


def armband(rig, mats, side='l', material='red'):
    upper = rig.data.bones[f'upperarm_{side}']
    direction = (upper.tail_local - upper.head_local).normalized()
    centre = upper.head_local + (upper.tail_local - upper.head_local) * 0.5
    turn = Matrix.Translation(centre) @ direction.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    b = bl.Builder(f'armband_{side}')
    b.lathe(mats[material], [(0.064, -0.035), (0.0665, -0.035), (0.0665, 0.035), (0.064, 0.035), (0.064, -0.035)],
            segments=24, matrix=turn)
    return [bind(finish(b, bevel=0.0), rig, f'upperarm_{side}')]


def backpack(suit, rig, mats):
    spine = ['spine_01', 'spine_02', 'spine_03', 'pelvis']
    bones = rig.data.bones
    z = (bones['spine_03'].tail_local.z + bones['spine_01'].head_local.z) * 0.5 + 0.02
    middle = (z,) + ellipse_at(suit, z, bones=spine, limit_x=0.2)
    place = on_ellipse(middle, 180, 0.03)
    b = bl.Builder('backpack')
    b.box(mats['vest'], (-0.14, -0.13, -0.2), (0.14, 0.0, 0.19), matrix=place)
    b.box(mats['pouch'], (-0.10, -0.175, -0.17), (0.10, -0.13, 0.02), matrix=place)
    b.box(mats['strap'], (-0.145, -0.135, 0.06), (0.145, -0.128, 0.085), matrix=place)
    for side in (-1, 1):
        b.box(mats['pouch'], (side * 0.14 - 0.03, -0.10, -0.16), (side * 0.14 + 0.03, -0.02, -0.02), matrix=place)
    pack = finish(b, bevel=0.018, segments=4, smooth_angle=60)
    shoulder_z = bones['clavicle_l'].head_local.z + 0.05
    chest = (bones['spine_03'].tail_local.z,) + ellipse_at(suit, bones['spine_03'].tail_local.z, bones=spine, limit_x=0.2)
    b = bl.Builder('pack_straps')
    for side in (-1, 1):
        front_low = on_ellipse(middle, side * 40, 0.012).translation
        front = on_ellipse(chest, side * 30, 0.014).translation
        back = on_ellipse(chest, 180 - side * 28, 0.03).translation
        over = Vector((side * 0.1, (front.y + back.y) * 0.5, shoulder_z))
        ribbon(b, mats['strap'], [front_low, front, over, back], 0.05, 0.008, up=(side, 0, 0))
    straps = finish(b, bevel=0.003)
    return [bind(pack, rig, 'spine_03'), bind(straps, rig, 'spine_03')]


def gloves(basemesh, rig, mats):
    """Gloves: a second skin over each hand and wrist."""
    body = in_group(basemesh, 'body')
    out = []
    for side in ('l', 'r'):
        bones = [f'hand_{side}'] + [f'{f}_0{j}_{side}' for f in ('thumb', 'index', 'middle', 'ring', 'pinky') for j in (1, 2, 3)]
        hand = weights(basemesh, bones)
        fore = weights(basemesh, [f'lowerarm_{side}'])
        wrist_z = rig.data.bones[f'hand_{side}'].head_local.z

        def keep(v, hand=hand, fore=fore, wrist_z=wrist_z):
            if v.index not in body:
                return False
            return hand[v.index] > 0.35 or (fore[v.index] > 0.5 and v.co.z < wrist_z + 0.075)

        out.append(shell(basemesh, keep, f'glove_{side}', mats['glove'], offset=0.0018))
    return out


def balaclava(basemesh, rig, mats):
    body = in_group(basemesh, 'body')
    head = weights(basemesh, ['head', 'neck_01'])
    neck_z = rig.data.bones['neck_01'].head_local.z

    def keep(v):
        return v.index in body and head[v.index] > 0.4 and v.co.z > neck_z - 0.03

    return [shell(basemesh, keep, 'balaclava', mats['balaclava'], offset=0.0035, smooth=2)]


def beanie(basemesh, rig, mats):
    eye_z, _, _ = eye_height(basemesh)
    body = in_group(basemesh, 'body')
    head = weights(basemesh, ['head'])

    def keep(v):
        # Down over the ears at the sides and back, above the brows in front.
        brim = eye_z + 0.034 + max(0.0, -v.co.y - 0.02) * 0.1 - max(0.0, v.co.y + 0.02) * 0.35
        return v.index in body and head[v.index] > 0.5 and v.co.z > brim

    cap = shell(basemesh, keep, 'beanie', mats['knit'], offset=0.012, smooth=1)
    return [cap]


def cap(basemesh, rig, mats):
    """A baseball cap: a crown over the skull, and a peak."""
    eye_z, eye_y, _ = eye_height(basemesh)
    body = in_group(basemesh, 'body')
    head = weights(basemesh, ['head'])

    def keep(v):
        # Down to the brow in front, and lower behind, as a cap sits.
        return v.index in body and head[v.index] > 0.5 and v.co.z > eye_z + 0.04 - max(0.0, v.co.y + 0.02) * 0.45

    # Smoothing draws a shell in on itself: only a little, or the crown sinks into the skull.
    crown = shell(basemesh, keep, 'cap', mats['knit'], offset=0.012, smooth=1)
    centre, rx, ry = head_ellipse(basemesh, eye_z + 0.05)
    b = bl.Builder('cap_peak')
    z = eye_z + 0.047
    outline = []
    for i in range(13):
        a = math.radians(-58 + 116 * i / 12)
        outline.append((centre[0] + (rx + 0.004) * math.sin(a), centre[1] - (ry + 0.004) * math.cos(a)))
    front = [(x * 0.92, y - 0.078 + abs(x) * 0.5) for x, y in reversed(outline)]
    b.prism(mats['knit'], outline + front, 0.004, axis='Z', offset=z)
    peak = bind(finish(b, bevel=0.0012), rig, 'head')
    return [crown, peak]


# ---------------------------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------------------------

def camo(surface, mask, colours=((0.085, 0.09, 0.095), (0.036, 0.04, 0.046), (0.125, 0.125, 0.118)), scale=9.0, grime=0.5):
    """Uniform cloth in a three-colour disruptive pattern."""
    m = mask.astype('float32')
    a = surface.noise(scale, 51, octaves=3)
    b = surface.noise(scale * 1.7, 52, octaves=3)
    base = tex.lerp(tex.rgb(*colours[0]), tex.rgb(*colours[1]), tex.smoothstep(0.50, 0.53, a))
    base = tex.lerp(base, tex.rgb(*colours[2]), tex.smoothstep(0.585, 0.61, b))
    bake.fabric(surface, mask, colour=(1.0, 1.0, 1.0), grime=grime, weave=1100.0)
    surface.colour = tex.lerp(surface.colour, surface.colour * base * 1.15, m)


def leather(surface, mask, colour=(0.02, 0.018, 0.016)):
    bake.polymer(surface, mask, colour=colour, wear=0.6, grime=0.6, texture=1.6)
    m = mask.astype('float32')
    creases = surface.noise(260.0, 61, octaves=3)
    surface.paint(m * tex.smoothstep(0.55, 0.8, creases) * 0.5, None, surface.roughness * 0.7)


def amber_lens(surface, mask):
    m = mask.astype('float32')
    smear = surface.noise(60.0, 71)
    surface.paint(m, tex.rgb(0.13, 0.065, 0.02), 0.06 + smear * 0.1, 1.0)
    surface.paint(m * surface.dust(0.5, 40.0, 72) * 0.6, tex.rgb(0.2, 0.17, 0.13), 0.7, 0.0)


SOLDIER_RECIPES = {
    'helmet': (camo, dict(colours=((0.075, 0.08, 0.085), (0.034, 0.037, 0.042), (0.11, 0.11, 0.105)), scale=14.0)),
    'vest': (bake.fabric, dict(colour=(0.042, 0.046, 0.044), grime=0.55, weave=700.0)),
    'pouch': (bake.fabric, dict(colour=(0.036, 0.04, 0.038), grime=0.55, weave=700.0)),
    'strap': (bake.fabric, dict(colour=(0.024, 0.026, 0.026), grime=0.5, weave=1400.0)),
    'hard': (bake.polymer, dict(colour=(0.022, 0.023, 0.024), wear=0.55, grime=0.55)),
    'lens': (amber_lens, dict()),
    'balaclava': (bake.fabric, dict(colour=(0.018, 0.018, 0.02), grime=0.3, weave=1800.0)),
    'glove': (bake.fabric, dict(colour=(0.03, 0.03, 0.03), grime=0.5, weave=1600.0)),
    'boot': (leather, dict()),
    'shoe': (leather, dict()),
    'mag': (bake.polymer, dict(colour=(0.03, 0.03, 0.032), wear=0.5, grime=0.4)),
    'pistol': (bake.polymer, dict(colour=(0.02, 0.02, 0.022), wear=0.5, grime=0.4)),
    'red': (bake.fabric, dict(colour=(0.42, 0.035, 0.02), grime=0.35, weave=1200.0)),
    'knit': (bake.fabric, dict(colour=(0.05, 0.05, 0.055), grime=0.3, weave=500.0)),
}

REBEL_RECIPES = dict(SOLDIER_RECIPES)
REBEL_RECIPES.update({
    'vest': (bake.fabric, dict(colour=(0.16, 0.13, 0.085), grime=0.6, weave=700.0)),
    'pouch': (bake.fabric, dict(colour=(0.14, 0.115, 0.075), grime=0.6, weave=700.0)),
    'strap': (bake.fabric, dict(colour=(0.07, 0.06, 0.045), grime=0.5, weave=1400.0)),
    'mag': (bake.polymer, dict(colour=(0.30, 0.225, 0.135), wear=0.5, grime=0.5)),
    'glove': (bake.fabric, dict(colour=(0.075, 0.06, 0.045), grime=0.6, weave=1600.0)),
    'red': (bake.fabric, dict(colour=(0.55, 0.52, 0.45), grime=0.5, weave=1200.0)),
})


def mats():
    return {name: slot(name) for name in SOLDIER_RECIPES}


def paint(name, objects, recipes, size=1024, seed=5, unwrap=True):
    atlas = bake.Atlas(name, objects, size=size, seed=seed, edge_radius=0.004, ao_distance=0.08, margin=0.003)
    for slot_name, (function, options) in recipes.items():
        atlas.recipe(slot_name, function, **options)
    atlas.bake(TEX, unwrap=unwrap)


def one_skin(basemesh):
    """Puts the whole body on its one skin material: its lips, ears and nails share that
    material's picture anyway, and each material costs the game a texture of its own."""
    for polygon in basemesh.data.polygons:
        polygon.material_index = 0
    while len(basemesh.data.materials) > 1:
        basemesh.data.materials.pop(index=len(basemesh.data.materials) - 1)


# ---------------------------------------------------------------------------------------------
# The cast
# ---------------------------------------------------------------------------------------------

def soldier():
    body = {"gender": 1.0, "age": 0.5, "muscle": 0.72, "weight": 0.55, "proportions": 0.55, "height": 0.6,
            "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.34, "caucasian": 0.33, "african": 0.33}}
    basemesh, rig = make_human('soldier', body, 'young_caucasian_male', ['male_casualsuit01', 'shoes04'])
    suit, shoes = find('casualsuit'), find('shoes')
    m = mats()
    gear = []
    gear += balaclava(basemesh, rig, m)
    gear += gloves(basemesh, rig, m)
    made, _ = helmet(basemesh, rig, m)
    gear += made
    gear += goggles(basemesh, rig, m)
    gear += plate_carrier(suit, rig, m)
    gear += belt_and_holster(suit, rig, m)
    gear += knee_pads(rig, m)
    gear += boot_shafts(rig, m)
    gear += armband(rig, m, 'l', 'red')
    # Nothing of the body shows: it goes, and its seven materials with it.
    bpy.data.objects.remove(basemesh)
    shoes.data.materials.clear()
    shoes.data.materials.append(m['shoe'])
    suit.data.materials.clear()
    suit.data.materials.append(slot('uniform'))
    paint('soldier_uniform', [suit], {'uniform': (camo, dict(scale=7.0, grime=0.55))}, seed=3, unwrap=False)
    paint('soldier_gear', gear + [shoes], SOLDIER_RECIPES, seed=9)
    # One mesh, one material: each mesh's material becomes a texture of its own in the game.
    bl.join(gear + [shoes], 'soldier_gear')
    return rig


def rebel(kind):
    extras = [('Eyes', 'eyes/low-poly/*.mhclo'), ('Eyebrows', 'eyebrows/eyebrow001/*.mhclo')]
    if kind == 'rebel_a':
        # Mara: who runs the cell.
        body = {"gender": 0.0, "age": 0.5, "muscle": 0.62, "weight": 0.45, "proportions": 0.5, "height": 0.52,
                "cupsize": 0.4, "firmness": 0.6, "race": {"asian": 0.1, "caucasian": 0.8, "african": 0.1}}
        skin, outfit, shoes = 'middleage_caucasian_female', 'male_casualsuit05', 'shoes02'
        extras.append(('Hair', 'hair/ponytail01/*.mhclo'))
    else:
        body = {"gender": 1.0, "age": 0.42, "muscle": 0.65, "weight": 0.45, "proportions": 0.55, "height": 0.62,
                "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.05, "caucasian": 0.15, "african": 0.8}}
        skin, outfit, shoes = 'young_african_male', 'male_casualsuit03', 'shoes02'
    basemesh, rig = make_human(kind, body, skin, [outfit, shoes], extras=extras)
    suit = find('casualsuit')
    m = mats()
    gear = []
    gear += gloves(basemesh, rig, m)
    if kind == 'rebel_a':
        gear += chest_rig(suit, rig, m)
        gear += backpack(suit, rig, m)
    else:
        gear += cap(basemesh, rig, m)
        gear += chest_rig(suit, rig, m)
        gear += belt_and_holster(suit, rig, m)
    gear += armband(rig, m, 'r', 'red')
    one_skin(basemesh)
    paint(f'{kind}_gear', gear, REBEL_RECIPES, seed=21 if kind == 'rebel_a' else 33)
    bl.join(gear, f'{kind}_gear')
    return rig


def arms():
    """The player's arms: a rebel's sleeves and gloved hands, and nothing else of them."""
    body = {"gender": 1.0, "age": 0.5, "muscle": 0.62, "weight": 0.5, "proportions": 0.5, "height": 0.55,
            "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.0, "caucasian": 0.9, "african": 0.1}}
    basemesh, rig = make_human('arms', body, 'young_caucasian_male', ['male_casualsuit05'])
    suit = find('casualsuit')
    m = mats()
    made = gloves(basemesh, rig, m)
    arm_bones = ['upperarm_l', 'lowerarm_l', 'hand_l', 'upperarm_r', 'lowerarm_r', 'hand_r']
    arm = weights(suit, arm_bones)
    remove_faces(suit, lambda v: arm[v.index] < 0.55)
    bm = bmesh.new()
    bm.from_mesh(suit.data)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(suit.data)
    bm.free()
    bpy.data.objects.remove(basemesh)
    paint('arms_gear', made, REBEL_RECIPES, seed=44)
    bl.join(made, 'arms_gear')
    return rig


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    kind, output = args[0], os.path.abspath(args[1])
    if kind == 'soldier':
        soldier()
    elif kind in ('rebel_a', 'rebel_b'):
        rebel(kind)
    elif kind == 'arms':
        arms()
    else:
        sys.exit(f'people.py: no such person: {kind}')
    if '--preview' in args:
        preview.render(os.path.join(bl.ROOT, 'build', 'previews', f'{kind}.png'),
                       [o for o in bpy.data.objects if o.type == 'MESH'],
                       views=[(180, 5), (145, 10), (0, 8)], size=(900, 1200), samples=48, zoom=1.0)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=output)
    print(f'people.py: saved {output}')


main()
