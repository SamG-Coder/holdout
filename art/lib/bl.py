"""Blender helpers for building HOLDOUT's assets from code: materials from the texture library,
mesh building with bmesh, world-scale UVs, and export to glTF for the engine.

Blender's axes are used throughout: X right, Y away from the viewer, Z up, in metres. The glTF
writer turns that into the engine's Y up, so Blender's +Y becomes the engine's -Z: an asset's
front, the way it faces when placed with no turn, is its +Y side here.
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
TEX_DIR = os.path.join(ROOT, 'build', 'tex')

# How much surface one repeat of each tiling texture covers, in metres: as art/lib/materials.py
# makes them.
TILE_METRES = {
    'asphalt': 2.0, 'concrete': 2.0, 'sidewalk': 1.5, 'dirt': 2.0, 'lawn': 2.0, 'gravel': 1.0,
    'siding': 1.6, 'brick': 1.2, 'shingles': 1.8, 'plaster': 2.0, 'stucco': 1.5,
    'fence_wood': 1.2, 'painted_wood': 1.0, 'plywood': 1.2, 'floor_wood': 1.0,
    'painted_metal': 1.0, 'corrugated': 1.0, 'rusty_metal': 1.0, 'dark_steel': 0.5,
    'bare_metal': 0.5, 'glass': 1.0, 'plastic': 0.4, 'rubber': 0.3, 'chainlink': 0.48,
    'canvas': 0.3, 'burlap': 0.25, 'carpet': 1.0, 'fabric': 0.2, 'ceramic_tile': 0.9,
    'car_paint': 1.5, 'burnt_metal': 1.2,
}


# ---------------------------------------------------------------------------------------------
# Scene housekeeping
# ---------------------------------------------------------------------------------------------

def reset():
    """Empties the file: every object, mesh, material and image."""
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                       bpy.data.images, bpy.data.node_groups, bpy.data.cameras, bpy.data.lights):
        for item in list(collection):
            collection.remove(item)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


# ---------------------------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------------------------

_images = {}


def load_image(path, colour):
    key = os.path.normcase(os.path.abspath(path))
    if key not in _images or _images[key].name not in bpy.data.images:
        image = bpy.data.images.load(path, check_existing=True)
        image.colorspace_settings.name = 'sRGB' if colour else 'Non-Color'
        _images[key] = image
    return _images[key]


def _gltf_output_group():
    """The node group the glTF writer reads occlusion from."""
    name = 'glTF Material Output'
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    group.interface.new_socket('Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
    group.nodes.new('NodeGroupInput')
    return group


def material(name, texture=None, tint=(1.0, 1.0, 1.0), roughness=1.0, metallic=1.0,
             mask=False, two_sided=False, emissive=None, emissive_strength=1.0, tex_dir=None,
             flat=None):
    """A material for the engine, made once by name.

    `texture` names a texture set in build/tex (`NAME_color.png`, `NAME_normal.png`,
    `NAME_orm.png`); `tint` multiplies its colour, `roughness` and `metallic` scale its maps.
    `flat=(colour, roughness, metallic)` makes a material with no textures instead. `mask` cuts it
    out by the colour map's alpha."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    mat.use_backface_culling = not two_sided

    if flat is not None:
        colour, flat_roughness, flat_metallic = flat
        bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
        bsdf.inputs['Roughness'].default_value = flat_roughness
        bsdf.inputs['Metallic'].default_value = flat_metallic
    else:
        folder = tex_dir or TEX_DIR
        uv = nodes.new('ShaderNodeTexCoord')
        colour = nodes.new('ShaderNodeTexImage')
        colour.image = load_image(os.path.join(folder, f'{texture}_color.png'), True)
        links.new(uv.outputs['UV'], colour.inputs['Vector'])
        if tuple(tint) != (1.0, 1.0, 1.0):
            mix = nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs['Factor'].default_value = 1.0
            links.new(colour.outputs['Color'], mix.inputs['A'])
            mix.inputs['B'].default_value = (*tint, 1.0)
            links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
        else:
            links.new(colour.outputs['Color'], bsdf.inputs['Base Color'])
        if mask:
            # A hard threshold is how the glTF writer knows the material is cut out (alpha mode
            # MASK, cut-off 0.5) rather than blended.
            cut = nodes.new('ShaderNodeMath')
            cut.operation = 'GREATER_THAN'
            links.new(colour.outputs['Alpha'], cut.inputs[0])
            cut.inputs[1].default_value = 0.5
            links.new(cut.outputs['Value'], bsdf.inputs['Alpha'])

        orm = nodes.new('ShaderNodeTexImage')
        orm.image = load_image(os.path.join(folder, f'{texture}_orm.png'), False)
        links.new(uv.outputs['UV'], orm.inputs['Vector'])
        split = nodes.new('ShaderNodeSeparateColor')
        links.new(orm.outputs['Color'], split.inputs['Color'])

        def scaled(output, factor, target):
            if factor == 1.0:
                links.new(output, target)
                return
            scale = nodes.new('ShaderNodeMath')
            scale.operation = 'MULTIPLY'
            links.new(output, scale.inputs[0])
            scale.inputs[1].default_value = factor
            links.new(scale.outputs['Value'], target)

        scaled(split.outputs['Green'], roughness, bsdf.inputs['Roughness'])
        scaled(split.outputs['Blue'], metallic, bsdf.inputs['Metallic'])
        occlusion = nodes.new('ShaderNodeGroup')
        occlusion.node_tree = _gltf_output_group()
        links.new(split.outputs['Red'], occlusion.inputs['Occlusion'])

        normal_image = nodes.new('ShaderNodeTexImage')
        normal_image.image = load_image(os.path.join(folder, f'{texture}_normal.png'), False)
        links.new(uv.outputs['UV'], normal_image.inputs['Vector'])
        normal_map = nodes.new('ShaderNodeNormalMap')
        links.new(normal_image.outputs['Color'], normal_map.inputs['Color'])
        links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])

    if emissive is not None:
        bsdf.inputs['Emission Color'].default_value = (*emissive, 1.0)
        bsdf.inputs['Emission Strength'].default_value = emissive_strength
    if mask:
        mat.blend_method = 'CLIP'
        if hasattr(mat, 'alpha_threshold'):
            mat.alpha_threshold = 0.5
    mat['tile_metres'] = TILE_METRES.get(texture, 1.0) if texture else 1.0
    return mat


def slot(obj, mat):
    """The index of a material's slot on an object, adding it if need be."""
    for index, existing in enumerate(obj.data.materials):
        if existing == mat:
            return index
    obj.data.materials.append(mat)
    return len(obj.data.materials) - 1


# ---------------------------------------------------------------------------------------------
# Building meshes
# ---------------------------------------------------------------------------------------------

class Builder:
    """Gathers geometry into one mesh, each face with a material, then makes an object of it."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.materials = []
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        # Faces whose UVs were laid out as they were made (round things, unwrapped along their
        # own length and girth) and must not be projected flat afterwards.
        self.keep = self.bm.faces.layers.int.new('keep_uv')

    def _tile(self, mat):
        return float(mat.get('tile_metres', 1.0)) if mat is not None else 1.0

    def _wrap_face(self, verts, uvs, mat):
        """Adds a face with its own UVs (in metres, divided here by the material's tile)."""
        try:
            face = self.bm.faces.new(verts)
        except ValueError:
            return None
        tile = self._tile(mat)
        for loop, uv in zip(face.loops, uvs):
            loop[self.uv].uv = (uv[0] / tile, uv[1] / tile)
        face[self.keep] = 1
        return face

    def _index(self, mat):
        if mat not in self.materials:
            self.materials.append(mat)
        return self.materials.index(mat)

    def _tag(self, faces, mat):
        index = self._index(mat)
        for face in faces:
            face.material_index = index
        return faces

    def _new_faces(self, before):
        return [f for f in self.bm.faces if f.index < 0 or f not in before]

    def box(self, mat, lo, hi, matrix=None):
        """An axis-aligned box from corner `lo` to corner `hi`, then moved by `matrix`."""
        lo, hi = Vector(lo), Vector(hi)
        size = hi - lo
        centre = (lo + hi) * 0.5
        made = bmesh.ops.create_cube(self.bm, size=1.0)
        verts = made['verts']
        bmesh.ops.scale(self.bm, vec=size, verts=verts)
        bmesh.ops.translate(self.bm, vec=centre, verts=verts)
        faces = list({f for v in verts for f in v.link_faces})
        if matrix is not None:
            bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)
            self._unmirror(faces, matrix)
        return self._tag(faces, mat)

    def cylinder(self, mat, radius, depth, centre=(0, 0, 0), axis='Z', segments=24,
                 radius_top=None, caps=True, matrix=None):
        """A cylinder or cone frustum of `depth` along `axis`, centred on `centre`."""
        radius_top = radius if radius_top is None else radius_top
        half = depth * 0.5
        profile = [(radius, -half), (radius_top, half)]
        if caps:
            profile = [(0.0, -half)] + profile + [(0.0, half)]
        return self.lathe(mat, profile, segments=segments, axis=axis, centre=centre, matrix=matrix)

    def sphere(self, mat, radius, centre=(0, 0, 0), segments=24, rings=12, scale=(1, 1, 1)):
        """A ball, or with `scale` an ellipsoid, unwrapped round its girth."""
        profile = [(max(radius * math.sin(math.pi * i / rings), 0.0) if 0 < i < rings else 0.0,
                    -radius * math.cos(math.pi * i / rings)) for i in range(rings + 1)]
        faces = self.lathe(mat, profile, segments=segments)
        verts = list({v for f in faces for v in f.verts})
        bmesh.ops.scale(self.bm, vec=Vector(scale), verts=verts)
        bmesh.ops.translate(self.bm, vec=Vector(centre), verts=verts)
        return faces

    def prism(self, mat, outline, depth, axis='Y', offset=0.0, matrix=None):
        """Extrudes a closed 2D outline into a solid. With axis 'Y' the outline is in X and Z and
        runs along Y from `offset`; with 'X' it is in Y and Z; with 'Z' it is in X and Y. The
        outline should go anticlockwise as drawn."""
        def lift(p, d):
            if axis == 'Y':
                return Vector((p[0], d, p[1]))
            if axis == 'X':
                return Vector((d, p[0], p[1]))
            return Vector((p[0], p[1], d))

        near = [self.bm.verts.new(lift(p, offset)) for p in outline]
        far = [self.bm.verts.new(lift(p, offset + depth)) for p in outline]
        faces = []
        count = len(outline)
        for i in range(count):
            j = (i + 1) % count
            faces.append(self.bm.faces.new((near[i], near[j], far[j], far[i])))
        faces.append(self.bm.faces.new(list(reversed(near))))
        faces.append(self.bm.faces.new(far))
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        if matrix is not None:
            bmesh.ops.transform(self.bm, matrix=matrix, verts=near + far)
            self._unmirror(faces, matrix)
        return self._tag(faces, mat)

    def quad(self, mat, a, b, c, d):
        """One four-sided face through four points, anticlockwise seen from its front."""
        verts = [self.bm.verts.new(Vector(p)) for p in (a, b, c, d)]
        return self._tag([self.bm.faces.new(verts)], mat)

    def polygon(self, mat, points):
        verts = [self.bm.verts.new(Vector(p)) for p in points]
        return self._tag([self.bm.faces.new(verts)], mat)

    def lathe(self, mat, profile, segments=32, axis='Z', centre=(0, 0, 0), matrix=None):
        """Turns a profile of (radius, height) points about an axis into a surface of revolution.
        Points with radius 0 close the ends. It is unwrapped round its widest girth and along
        its profile, so a tiling texture runs round it unbroken; flat ends are left to be
        projected flat."""
        girth = math.tau * max(max(r for r, _ in profile), 1e-6)
        rings = []
        along = [0.0]
        for (r0, h0), (r1, h1) in zip(profile, profile[1:]):
            along.append(along[-1] + math.hypot(r1 - r0, h1 - h0))
        for radius, height in profile:
            if radius <= 1e-9:
                rings.append([self.bm.verts.new(Vector((0, 0, height)))])
            else:
                rings.append([self.bm.verts.new(Vector((radius * math.cos(math.tau * s / segments),
                                                         radius * math.sin(math.tau * s / segments),
                                                         height))) for s in range(segments)])
        faces = []
        index = self._index(mat)
        for level, (lower, upper) in enumerate(zip(rings, rings[1:])):
            flat = abs(profile[level][1] - profile[level + 1][1]) < 1e-7
            v0, v1 = along[level], along[level + 1]
            for s in range(segments):
                t = (s + 1) % segments
                u0, u1 = girth * s / segments, girth * (s + 1) / segments
                if len(lower) == 1 and len(upper) == 1:
                    continue
                if len(lower) == 1:
                    verts, uvs = (lower[0], upper[s], upper[t]), ((u0, v0), (u0, v1), (u1, v1))
                elif len(upper) == 1:
                    verts, uvs = (lower[s], lower[t], upper[0]), ((u0, v0), (u1, v0), (u0, v1))
                else:
                    verts = (lower[s], lower[t], upper[t], upper[s])
                    uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                face = self._wrap_face(verts, uvs, mat)
                if face is None:
                    continue
                if flat:
                    face[self.keep] = 0
                face.material_index = index
                faces.append(face)
        verts = [v for ring in rings for v in ring]
        turn = {'Z': Matrix.Identity(4), 'X': Matrix.Rotation(math.radians(90), 4, 'Y'),
                'Y': Matrix.Rotation(math.radians(-90), 4, 'X')}[axis]
        bmesh.ops.transform(self.bm, matrix=Matrix.Translation(Vector(centre)) @ turn, verts=verts)
        if matrix is not None:
            bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        return faces

    def tube(self, mat, points, radius, segments=10, closed=False, caps=True, matrix=None):
        """A round pipe along a polyline, mitred at its corners."""
        points = [Vector(p) for p in points]
        count = len(points)
        rings = []
        previous_normal = None
        for i, point in enumerate(points):
            before = points[i - 1] if (i > 0 or closed) else None
            after = points[(i + 1) % count] if (i < count - 1 or closed) else None
            d_in = (point - before).normalized() if before is not None else None
            d_out = (after - point).normalized() if after is not None else None
            tangent = ((d_in or d_out) + (d_out or d_in)).normalized()
            if tangent.length < 1e-6:
                tangent = d_out or d_in
            # A frame carried along the pipe, so that it doesn't twist.
            if previous_normal is None:
                helper = Vector((0, 0, 1)) if abs(tangent.z) < 0.9 else Vector((1, 0, 0))
                normal = tangent.cross(helper).normalized()
            else:
                normal = (previous_normal - tangent * previous_normal.dot(tangent)).normalized()
            previous_normal = normal
            binormal = tangent.cross(normal).normalized()
            # Widen across a corner so the pipe keeps its width through the mitre.
            stretch = 1.0
            if d_in is not None and d_out is not None:
                cos_half = max(math.sqrt(max((1.0 + d_in.dot(d_out)) * 0.5, 0.0)), 0.3)
                stretch = 1.0 / cos_half
            ring = []
            for s in range(segments):
                angle = math.tau * s / segments
                offset = (normal * math.cos(angle) + binormal * math.sin(angle)) * radius
                if stretch != 1.0 and d_in is not None and d_out is not None:
                    bend = (d_out - d_in)
                    if bend.length > 1e-6:
                        bend.normalize()
                        offset += bend * offset.dot(bend) * (stretch - 1.0)
                ring.append(self.bm.verts.new(point + offset))
            rings.append(ring)
        faces = []
        lengths = [0.0]
        for a, b in zip(points, points[1:]):
            lengths.append(lengths[-1] + (b - a).length)
        if closed:
            lengths.append(lengths[-1] + (points[0] - points[-1]).length)
        pairs = [(rings[i], rings[i + 1], lengths[i], lengths[i + 1]) for i in range(count - 1)]
        if closed:
            pairs.append((rings[-1], rings[0], lengths[-2], lengths[-1]))
        girth = math.tau * radius
        for lower, upper, v0, v1 in pairs:
            for s in range(segments):
                t = (s + 1) % segments
                u0, u1 = girth * s / segments, girth * (s + 1) / segments
                face = self._wrap_face((lower[s], lower[t], upper[t], upper[s]),
                                       ((u0, v0), (u1, v0), (u1, v1), (u0, v1)), mat)
                if face is not None:
                    faces.append(face)
        if caps and not closed:
            faces.append(self.bm.faces.new(list(reversed(rings[0]))))
            faces.append(self.bm.faces.new(rings[-1]))
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        if matrix is not None:
            self.transform(faces, matrix)
        return self._tag(faces, mat)

    def _unmirror(self, faces, matrix):
        """A matrix that mirrors turns faces inside out: turn them back, or the engine, which
        draws only the fronts of faces, shows what lies behind them."""
        if matrix.determinant() < 0:
            bmesh.ops.reverse_faces(self.bm, faces=list(faces))

    def transform(self, faces, matrix):
        verts = list({v for f in faces for v in f.verts})
        bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)
        self._unmirror(faces, matrix)
        return faces

    def append_object(self, obj, matrix=None):
        """Takes in another object's mesh, with its materials."""
        temp = bmesh.new()
        temp.from_mesh(obj.data)
        if matrix is not None:
            bmesh.ops.transform(temp, matrix=matrix, verts=temp.verts)
            if matrix.determinant() < 0:
                bmesh.ops.reverse_faces(temp, faces=list(temp.faces))
        remap = [self._index(m) for m in obj.data.materials] or [0]
        mesh = bpy.data.meshes.new('_append')
        for face in temp.faces:
            face.material_index = remap[min(face.material_index, len(remap) - 1)]
        temp.to_mesh(mesh)
        temp.free()
        self.bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)

    def finish(self, bevel=0.0, bevel_segments=2, smooth_angle=35.0, weld=True, uv=True,
               location=(0, 0, 0)):
        """Makes the object: welds, bevels its sharp edges, shades smooth across shallow ones,
        and lays out world-scale UVs for its tiling materials."""
        if weld:
            bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        if uv:
            self.project_uvs()
        mesh = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for mat in self.materials:
            mesh.materials.append(mat)
        obj = bpy.data.objects.new(self.name, mesh)
        link(obj)
        obj.location = Vector(location)
        if bevel > 0.0:
            add_bevel(obj, bevel, bevel_segments)
        shade(obj, smooth_angle)
        return obj

    def project_uvs(self, faces=None, force=False):
        """World-scale UVs for flat faces: each is laid flat with the texture's up running up
        the surface (straight up a wall, up the slope of a roof), one repeat every tile of its
        material. Faces unwrapped as they were made are left alone unless `force`."""
        up = Vector((0, 0, 1))
        self.bm.normal_update()
        for face in (self.bm.faces if faces is None else faces):
            if face[self.keep] and not force:
                continue
            mat = self.materials[face.material_index] if self.materials else None
            if mat is not None and mat.get('unique_uv'):
                continue
            size = self._tile(mat)
            normal = face.normal if face.normal.length > 1e-9 else Vector((0, 0, 1))
            if abs(normal.z) > 0.92:
                tangent = Vector((1, 0, 0))
                bitangent = Vector((0, 1, 0)) if normal.z > 0 else Vector((0, -1, 0))
            else:
                bitangent = (up - normal * up.dot(normal)).normalized()
                tangent = bitangent.cross(normal).normalized()
            for loop in face.loops:
                position = loop.vert.co
                loop[self.uv].uv = (position.dot(tangent) / size, position.dot(bitangent) / size)


def text(string, size, mat, extrude=0.003, facing='+Y', align='CENTER'):
    """Lettering as a mesh, in Blender's own typeface: `size` metres tall, standing upright
    and read from the side it faces (`+Y`, `-Y`, `+X` or `-X`), or lying flat facing up (`+Z`).
    Its middle is at the origin. Take it into a builder with `append_object` and remove it."""
    curve = bpy.data.curves.new('text', 'FONT')
    curve.body = string
    curve.size = size
    curve.extrude = extrude
    curve.align_x = align
    curve.align_y = 'CENTER'
    obj = bpy.data.objects.new('text', curve)
    link(obj)
    select_only([obj])
    bpy.ops.object.convert(target='MESH')
    obj = bpy.context.view_layer.objects.active
    obj.data.materials.append(mat)
    stand = Matrix.Rotation(math.radians(90), 4, 'X')
    turn = {'-Y': 0, '+X': 90, '+Y': 180, '-X': 270}
    if facing in turn:
        obj.data.transform(Matrix.Rotation(math.radians(turn[facing]), 4, 'Z') @ stand)
    obj.data.update()
    return obj


def add_text(builder, string, size, mat, at, facing='+Y', extrude=0.003, matrix=None):
    """Puts lettering into a builder, its middle at `at`."""
    made = text(string, size, mat, extrude, facing)
    place = Matrix.Translation(Vector(at))
    builder.append_object(made, place if matrix is None else matrix @ place)
    mesh = made.data
    bpy.data.objects.remove(made)
    bpy.data.meshes.remove(mesh)


def add_bevel(obj, width, segments=2, angle=30.0):
    """Rounds an object's sharp edges, applied at once, with normals weighted so that the flat
    faces stay flat."""
    modifier = obj.modifiers.new('bevel', 'BEVEL')
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = 'ANGLE'
    modifier.angle_limit = math.radians(angle)
    modifier.harden_normals = True
    modifier.miter_outer = 'MITER_ARC'
    apply_modifiers(obj)


def apply_modifiers(obj):
    select_only([obj])
    for modifier in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError as error:
            print(f'warning: {obj.name}: could not apply {modifier.name}: {error}')
            obj.modifiers.remove(modifier)


def shade(obj, smooth_angle=35.0):
    """Smooth shading across edges shallower than `smooth_angle` degrees, sharp across the rest."""
    mesh = obj.data
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    select_only([obj])
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth_angle), keep_sharp_edges=False)
    except (AttributeError, RuntimeError, TypeError):
        bpy.ops.object.shade_smooth()


def boolean(obj, cutter, operation='DIFFERENCE', remove_cutter=True):
    """Cuts `cutter` out of `obj` (or joins or intersects them), applied at once."""
    modifier = obj.modifiers.new('boolean', 'BOOLEAN')
    modifier.operation = operation
    modifier.object = cutter
    modifier.solver = 'EXACT'
    # A cutter is often several overlapping pieces: the solver must be told, or it guesses.
    modifier.use_self = True
    apply_modifiers(obj)
    if remove_cutter:
        mesh = cutter.data
        bpy.data.objects.remove(cutter)
        bpy.data.meshes.remove(mesh)
    return obj


def join(objects, name=None):
    """Joins objects into the first, keeping every material."""
    objects = [o for o in objects if o is not None]
    select_only(objects)
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    if name:
        obj.name = name
        obj.data.name = name
    return obj


def duplicate(obj, name, matrix=None):
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = name
    copy.data.name = name
    link(copy)
    if matrix is not None:
        copy.matrix_world = matrix @ copy.matrix_world
    return copy


def apply_transform(obj):
    """Bakes an object's place, turn and scale into its mesh, leaving it at the origin."""
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    if obj.matrix_world.determinant() < 0:
        obj.data.flip_normals()


def transform_mesh(obj, matrix):
    obj.data.transform(matrix)
    if matrix.determinant() < 0:
        obj.data.flip_normals()
    obj.data.update()


def subdivide(obj, levels=1, simple=False):
    modifier = obj.modifiers.new('subdivide', 'SUBSURF')
    modifier.levels = levels
    modifier.render_levels = levels
    modifier.subdivision_type = 'SIMPLE' if simple else 'CATMULL_CLARK'
    apply_modifiers(obj)


def displace_noise(obj, strength, scale, seed=0, axis=None):
    """Pushes an object's vertices about by smooth noise, along their normals or one axis: for
    dents, lumps and sag."""
    from mathutils import noise
    offset = Vector((seed * 13.7, seed * 7.3, seed * 3.1))
    mesh = obj.data
    mesh.calc_loop_triangles() if hasattr(mesh, 'calc_loop_triangles') else None
    normals = [v.normal.copy() for v in mesh.vertices]
    for vertex, normal in zip(mesh.vertices, normals):
        value = noise.noise((vertex.co + offset) * scale)
        direction = Vector(axis) if axis is not None else normal
        vertex.co += direction * value * strength
    mesh.update()


# ---------------------------------------------------------------------------------------------
# UVs
# ---------------------------------------------------------------------------------------------

def box_uv(obj, tile=None, only_material=None):
    """World-scale UVs for tiling textures: each face is laid flat with the texture's up running
    up the surface (straight up a wall, up the slope of a roof), one repeat every `tile` metres,
    which by default is each material's own."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name='UVMap')
    uv_layer = mesh.uv_layers.active.data
    up = Vector((0, 0, 1))
    matrix = obj.matrix_world
    rotation = matrix.to_3x3()
    for polygon in mesh.polygons:
        mat = mesh.materials[polygon.material_index] if mesh.materials else None
        if only_material is not None and mat != only_material:
            continue
        if mat is not None and mat.get('unique_uv'):
            continue
        size = tile if tile is not None else (mat.get('tile_metres', 1.0) if mat else 1.0)
        normal = (rotation @ polygon.normal).normalized()
        if abs(normal.z) > 0.92:
            tangent = Vector((1, 0, 0))
            bitangent = Vector((0, 1, 0)) if normal.z > 0 else Vector((0, -1, 0))
        else:
            bitangent = (up - normal * up.dot(normal)).normalized()
            tangent = bitangent.cross(normal).normalized()
        for loop_index in polygon.loop_indices:
            position = matrix @ mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv_layer[loop_index].uv = (position.dot(tangent) / size, position.dot(bitangent) / size)


def planar_uv(obj, origin, u_axis, v_axis, only_material=None):
    """Projects UVs flat: 0..1 across `u_axis` and `v_axis` (vectors whose lengths are the size
    covered) from `origin`. For signs, posters and decals."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name='UVMap')
    uv_layer = mesh.uv_layers.active.data
    origin, u_axis, v_axis = Vector(origin), Vector(u_axis), Vector(v_axis)
    for polygon in mesh.polygons:
        mat = mesh.materials[polygon.material_index] if mesh.materials else None
        if only_material is not None and mat != only_material:
            continue
        for loop_index in polygon.loop_indices:
            position = mesh.vertices[mesh.loops[loop_index].vertex_index].co - origin
            uv_layer[loop_index].uv = (position.dot(u_axis) / u_axis.length_squared,
                                       position.dot(v_axis) / v_axis.length_squared)


# ---------------------------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------------------------

def export_glb(path, objects=None):
    """Writes objects (all of them by default) as one binary glTF, with fixed options so that a
    change of Blender's defaults can't change the file. Each top-level object is a named part
    the level can place by its own origin."""
    objects = list(bpy.data.objects) if objects is None else objects
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    select_only(objects)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials='EXPORT',
        export_image_format='AUTO',
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_extras=False,
    )
    size = os.path.getsize(path) / 1e6
    triangles = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objects if o.type == 'MESH')
    print(f'wrote {path}: {len(objects)} objects, {triangles} triangles, {size:.1f} MB', flush=True)
