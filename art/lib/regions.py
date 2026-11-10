"""Cutting regions into a surface: a road into a lawn, a window into a car door.

A `Painter` holds an object's mesh open; each `paint` cuts the mesh along the edges of a convex
polygon seen along one axis, so that the region's outline is exact, and gives the faces inside
a material. `finish` writes the mesh back.
"""

import math

import bmesh
from mathutils import Vector

from . import bl


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


class Painter:
    def __init__(self, obj, margin=0.25):
        """`margin` is how far beyond a region's bounds a face's middle may be and still be
        looked at: at least half the size of the mesh's largest face."""
        self.obj = obj
        self.margin = margin
        self.bm = bmesh.new()
        self.bm.from_mesh(obj.data)

    def paint(self, material, polygon, axis='Z', keep=None, frame=None, frame_width=0.014, sink=0.0):
        """Gives `material` to what lies inside a convex `polygon` as seen along `axis`, among
        the faces `keep(centre, normal)` lets through. With `frame`, a border of that material
        is left round the edge, and `sink` sets the region back into the surface. Returns how
        many faces the region came to."""
        bm = self.bm
        polygon = [tuple(p) for p in polygon]
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
        if area < 0:
            polygon.reverse()
        margin = self.margin
        lo = (min(p[0] for p in polygon) - margin, min(p[1] for p in polygon) - margin)
        hi = (max(p[0] for p in polygon) + margin, max(p[1] for p in polygon) + margin)
        index = bl.slot(self.obj, material)

        def near(faces):
            found = []
            for face in faces:
                centre = face.calc_center_median()
                u, v = _flat(centre, axis)
                if lo[0] <= u <= hi[0] and lo[1] <= v <= hi[1] and (keep is None or keep(centre, face.normal)):
                    found.append(face)
            return found

        # Everything a cut makes lies within the faces it cut, so after the first look only
        # what the cuts return need be looked at again.
        faces = near(bm.faces)
        edges = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 1e-9:
                continue
            inward = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
            edges.append((a, inward))
            if not faces:
                continue
            geometry = list({v for f in faces for v in f.verts} | {e for f in faces for e in f.edges}) + faces
            cut = bmesh.ops.bisect_plane(bm, geom=geometry, dist=1e-6, plane_co=_lift(a[0], a[1], axis),
                                         plane_no=_lift(inward[0], inward[1], axis))
            faces = [item for item in cut['geom'] if isinstance(item, bmesh.types.BMFace)]
        inside = []
        for face in faces:
            if not face.is_valid:
                continue
            u, v = _flat(face.calc_center_median(), axis)
            if all((u - a[0]) * n[0] + (v - a[1]) * n[1] >= -1e-6 for a, n in edges):
                inside.append(face)
                face.material_index = index
        if inside and frame is not None:
            rim = bmesh.ops.inset_region(bm, faces=inside, thickness=frame_width, depth=-sink,
                                         use_even_offset=True, use_boundary=True)
            frame_index = bl.slot(self.obj, frame)
            for face in rim['faces']:
                face.material_index = frame_index
        return len(inside)

    def finish(self):
        self.bm.normal_update()
        self.bm.to_mesh(self.obj.data)
        self.bm.free()
        self.obj.data.update()
