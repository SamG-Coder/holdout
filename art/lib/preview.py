"""Quick studio pictures of an asset, rendered by Cycles, to judge it before it goes near the
engine.

    preview.render('build/previews/rifle.png', objects, views=[(35, 15), (215, 20)])
"""

import math
import os

import bpy
from mathutils import Vector


def _bounds(objects):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != 'MESH':
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo.x, point.x), min(lo.y, point.y), min(lo.z, point.z)))
            hi = Vector((max(hi.x, point.x), max(hi.y, point.y), max(hi.z, point.z)))
    return lo, hi


def _studio():
    scene = bpy.context.scene
    world = bpy.data.worlds.get('preview_world') or bpy.data.worlds.new('preview_world')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputWorld')
    background = nodes.new('ShaderNodeBackground')
    # A soft gradient: bright above, dim below, a little warm on one side.
    coords = nodes.new('ShaderNodeTexCoord')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coords.outputs['Generated'], split.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.05, 0.05, 0.055, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.75, 0.8, 0.9, 1.0)
    links.new(split.outputs['Z'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = 0.9
    links.new(background.outputs['Background'], output.inputs['Surface'])

    for name, rotation, energy, colour in (('preview_key', (math.radians(50), 0, math.radians(35)), 3.2, (1.0, 0.96, 0.9)),
                                           ('preview_rim', (math.radians(65), 0, math.radians(200)), 1.6, (0.8, 0.88, 1.0))):
        light = bpy.data.objects.get(name)
        if light is None:
            data = bpy.data.lights.new(name, 'SUN')
            light = bpy.data.objects.new(name, data)
            scene.collection.objects.link(light)
        light.data.energy = energy
        light.data.color = colour
        light.data.angle = math.radians(6)
        light.rotation_euler = rotation


def render(path, objects=None, views=((35, 18),), size=(1280, 720), samples=48, zoom=1.0,
           focus=None, ground=False):
    """Renders `objects` (every mesh by default) from each view, an (azimuth, elevation) pair in
    degrees: azimuth 0 looks at the asset's front (+Y side) and turns anticlockwise seen from
    above. Several views are saved as `NAME_0.png`, `NAME_1.png`, and so on."""
    scene = bpy.context.scene
    objects = [o for o in (objects or bpy.data.objects) if o.type == 'MESH']
    _studio()
    scene.render.engine = 'CYCLES'
    try:
        preferences = bpy.context.preferences.addons['cycles'].preferences
        preferences.compute_device_type = 'OPTIX'
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type in ('OPTIX', 'CUDA')
        scene.cycles.device = 'GPU'
    except Exception:  # noqa: BLE001
        scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'

    lo, hi = _bounds(objects)
    centre = Vector(focus) if focus is not None else (lo + hi) * 0.5
    radius = max((hi - lo).length * 0.5, 1e-3)
    plane = None
    if ground:
        mesh = bpy.data.meshes.new('preview_ground')
        s = radius * 30
        mesh.from_pydata([(-s, -s, lo.z), (s, -s, lo.z), (s, s, lo.z), (-s, s, lo.z)], [], [(0, 1, 2, 3)])
        plane = bpy.data.objects.new('preview_ground', mesh)
        scene.collection.objects.link(plane)
        mat = bpy.data.materials.new('preview_ground')
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (0.18, 0.18, 0.18, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.8
        mesh.materials.append(mat)

    camera_data = bpy.data.cameras.get('preview_camera') or bpy.data.cameras.new('preview_camera')
    camera = bpy.data.objects.get('preview_camera')
    if camera is None:
        camera = bpy.data.objects.new('preview_camera', camera_data)
        scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.lens = 70
    camera_data.clip_start = 0.01
    camera_data.clip_end = 2000
    fov = 2 * math.atan(36 / (2 * camera_data.lens) * min(1.0, size[1] / size[0]))
    distance = radius / math.sin(fov * 0.5) / zoom

    # Only the asset: hide everything else from the render.
    hidden = []
    keep = set(objects) | {camera, plane}
    for obj in bpy.data.objects:
        if obj not in keep and obj.type == 'MESH' and not obj.hide_render:
            obj.hide_render = True
            hidden.append(obj)

    stem, extension = os.path.splitext(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    written = []
    for index, (azimuth, elevation) in enumerate(views):
        a, e = math.radians(azimuth), math.radians(elevation)
        direction = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        camera.location = centre + direction * distance
        camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = path if len(views) == 1 else f'{stem}_{index}{extension}'
        bpy.ops.render.render(write_still=True)
        written.append(scene.render.filepath)
    for obj in hidden:
        obj.hide_render = False
    if plane is not None:
        bpy.data.objects.remove(plane)
    print('preview:', ', '.join(written), flush=True)
    return written
