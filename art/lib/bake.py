"""Smart materials: textures made for one model, from what its own surface is like.

A hero asset (a weapon, a vehicle) is unwrapped into an atlas, and Cycles bakes what a texture
painter's generators work from: where each texel is on the model, which way it faces, how shut in
it is, and how near a sharp edge. numpy then lays materials down from 3D noise at each texel's own
position, so nothing shows a seam, and wears the paint off the edges and packs grime into the
corners.

    group = bake.Atlas('rifle_upper', objects, size=1024)
    group.assign(recipe_for_slot)        # which recipe paints each material slot
    material = group.bake(out_dir)       # the one material all its objects now share
"""

import math
import os

import bpy
import numpy as np

from . import tex
from .tex import F, fbm3, lerp, saturate, smoothstep

SUPERSAMPLE = 2


# ---------------------------------------------------------------------------------------------
# Baking geometry maps with Cycles
# ---------------------------------------------------------------------------------------------

def _setup_cycles(samples):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    try:
        preferences = bpy.context.preferences.addons['cycles'].preferences
        preferences.compute_device_type = 'OPTIX'
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type in ('OPTIX', 'CUDA')
        scene.cycles.device = 'GPU'
    except Exception as error:  # noqa: BLE001
        print(f'bake: no GPU for Cycles ({error}); using the CPU')
        scene.cycles.device = 'CPU'


def _select(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _image(name, size, float_buffer=True):
    if name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[name])
    image = bpy.data.images.new(name, size, size, alpha=True, float_buffer=float_buffer)
    image.colorspace_settings.name = 'Non-Color'
    return image


def _pixels(image):
    size = image.size[0]
    data = np.empty(size * size * 4, dtype=np.float32)
    image.pixels.foreach_get(data)
    # Blender's rows run bottom to top; ours top to bottom.
    return data.reshape(size, size, 4)[::-1].copy()


def _with_targets(objects, image, make_surface):
    """Gives every material of `objects` a temporary node tree whose surface is what
    `make_surface(nodes, links, slot_index, material)` returns (or the existing one if it returns
    None), with `image` as the bake target. Returns what to call to put things back."""
    saved = []
    seen = set()
    for obj in objects:
        for index, material in enumerate(obj.data.materials):
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            tree = material.node_tree
            nodes, links = tree.nodes, tree.links
            output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
            old_link = output.inputs['Surface'].links[0].from_socket if output.inputs['Surface'].links else None
            added = []
            target = nodes.new('ShaderNodeTexImage')
            target.image = image
            added.append(target)
            before = set(nodes)
            surface = make_surface(nodes, links, material)
            added.extend(n for n in nodes if n not in before)
            if surface is not None:
                links.new(surface, output.inputs['Surface'])
            for node in nodes:
                node.select = False
            target.select = True
            nodes.active = target
            saved.append((material, output, old_link, added))

    def restore():
        for material, output, old_link, added in saved:
            nodes, links = material.node_tree.nodes, material.node_tree.links
            for node in added:
                nodes.remove(node)
            if old_link is not None:
                links.new(old_link, output.inputs['Surface'])

    return restore


def _bake(objects, kind, image, margin, make_surface=lambda nodes, links, material: None, **options):
    restore = _with_targets(objects, image, make_surface)
    _select(objects)
    scene = bpy.context.scene
    scene.render.bake.margin = margin
    scene.render.bake.margin_type = 'EXTEND'
    scene.render.bake.use_clear = True
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.target = 'IMAGE_TEXTURES'
    try:
        bpy.ops.object.bake(type=kind, margin=margin, use_clear=True, **options)
    finally:
        restore()
    return _pixels(image)


def _emission(nodes, links, colour_socket):
    emission = nodes.new('ShaderNodeEmission')
    links.new(colour_socket, emission.inputs['Color'])
    return emission.outputs['Emission']


def geometry_maps(objects, size, edge_radius=0.0025, ao_distance=0.06, slot_ids=None):
    """Bakes the maps recipes work from, for objects that share one UV atlas. Returns a dict of
    arrays with row 0 at the top:

      position  (n, n, 3)  where the texel is, in metres, in the model's space
      normal    (n, n, 3)  which way it faces
      ao        (n, n)     1 open, 0 shut in
      edge      (n, n)     1 on a sharp edge, falling to 0 a few millimetres off it
      slot      (n, n)     which recipe paints it (an integer), -1 where the atlas is empty
      covered   (n, n)     True where a surface is
    """
    _setup_cycles(1)
    margin = 0
    position = _bake(objects, 'POSITION', _image('_bake_position', size), margin)
    covered = position[..., 3] > 0.5
    normal = _bake(objects, 'NORMAL', _image('_bake_normal', size), margin, normal_space='OBJECT')
    normal = normal[..., :3] * 2.0 - 1.0

    # Which slot: each material's own flat colour.
    ids = slot_ids or {}

    def flat_id(nodes, links, material):
        value = nodes.new('ShaderNodeRGB')
        index = ids.get(material.name, 0)
        value.outputs[0].default_value = ((index + 1) / 64.0, 0.0, 0.0, 1.0)
        return _emission(nodes, links, value.outputs[0])

    slot = _bake(objects, 'EMIT', _image('_bake_slot', size), margin, flat_id)
    slot_index = np.rint(slot[..., 0] * 64.0).astype(np.int32) - 1
    slot_index[~covered] = -1

    # How near an edge: a normal rounded over the edge radius differs from the true one there.
    _setup_cycles(24)

    def edge_surface(nodes, links, material):
        bevel = nodes.new('ShaderNodeBevel')
        bevel.samples = 8
        bevel.inputs['Radius'].default_value = edge_radius
        geometry = nodes.new('ShaderNodeNewGeometry')
        dot = nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        links.new(bevel.outputs['Normal'], dot.inputs[0])
        links.new(geometry.outputs['Normal'], dot.inputs[1])
        return _emission(nodes, links, dot.outputs['Value'])

    edge = _bake(objects, 'EMIT', _image('_bake_edge', size), margin, edge_surface)
    edge = saturate((1.0 - edge[..., 0]) * 11.0)

    scene = bpy.context.scene
    _setup_cycles(96)
    world = scene.world or bpy.data.worlds.new('bake_world')
    scene.world = world
    try:
        world.light_settings.distance = ao_distance
    except AttributeError:
        pass
    ao = _bake(objects, 'AO', _image('_bake_ao', size), margin)[..., 0]

    for name in ('_bake_position', '_bake_normal', '_bake_slot', '_bake_edge', '_bake_ao'):
        if name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[name])
    return {
        'position': position[..., :3].astype(F),
        'normal': normal.astype(F),
        'ao': saturate(ao).astype(F),
        'edge': edge.astype(F),
        'slot': slot_index,
        'covered': covered,
    }


def covered_preview(maps):
    return maps['covered'].astype(F)


def dilate(image, covered, passes=12):
    """Spreads the colour of covered texels out into the empty ones around them, so that
    filtering and mip-mapping never pull in the background."""
    image = image.copy()
    filled = covered.copy()
    for _ in range(passes):
        if filled.all():
            break
        total = np.zeros_like(image)
        count = np.zeros(filled.shape, dtype=F)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            shifted = np.roll(np.roll(filled, dy, axis=0), dx, axis=1)
            source = np.roll(np.roll(image, dy, axis=0), dx, axis=1)
            weight = shifted.astype(F)
            total += source * (weight[..., None] if image.ndim == 3 else weight)
            count += weight
        new = (~filled) & (count > 0)
        if image.ndim == 3:
            image[new] = total[new] / count[new][..., None]
        else:
            image[new] = total[new] / count[new]
        filled |= new
    return image


def downsample(image, factor):
    if factor == 1:
        return image
    m, n = image.shape[:2]
    shape = (m // factor, factor, n // factor, factor) + image.shape[2:]
    return image.reshape(shape).mean(axis=(1, 3))


# ---------------------------------------------------------------------------------------------
# The canvas a recipe paints on
# ---------------------------------------------------------------------------------------------

class Surface:
    """What recipes read and write: the baked maps, and the material's maps being built."""

    def __init__(self, maps, seed=0):
        self.maps = maps
        self.position = maps['position']
        self.normal = maps['normal']
        self.ao = maps['ao']
        self.edge = maps['edge']
        self.covered = maps['covered']
        self.seed = seed
        shape = self.ao.shape
        self.colour = np.zeros(shape + (3,), dtype=F)
        self.roughness = np.full(shape, 0.5, dtype=F)
        self.metallic = np.zeros(shape, dtype=F)
        # Fine relief, in metres, which becomes the normal map.
        self.height = np.zeros(shape, dtype=F)
        self.emissive = None
        # Metres of surface a texel covers, for turning height into slopes.
        dx = np.linalg.norm(np.roll(self.position, -1, axis=1) - np.roll(self.position, 1, axis=1), axis=-1) * 0.5
        dy = np.linalg.norm(np.roll(self.position, -1, axis=0) - np.roll(self.position, 1, axis=0), axis=-1) * 0.5
        sane = (dx > 1e-6) & (dx < 0.01) & (dy > 1e-6) & (dy < 0.01) & self.covered
        typical = float(np.median(np.concatenate([dx[sane], dy[sane]]))) if sane.any() else 0.001
        self.texel_metres = typical

    def noise(self, scale, seed=0, octaves=4, gain=0.5):
        """Fractal noise at each texel's place on the model: `scale` features to a metre."""
        return fbm3(self.position * scale, self.seed + seed, octaves=octaves, gain=gain)

    def grain(self, scale, seed=0):
        """Single-octave noise, for fine speckle."""
        return tex.value3(self.position * scale, self.seed + seed)

    def wear(self, amount=0.5, scale=140.0, seed=0, spread=1.0):
        """Where a coating has worn through: along edges, broken up by noise so that it comes
        and goes, and a little on open flats where things rub."""
        breakup = self.noise(scale, seed + 11, octaves=4)
        broad = self.noise(scale * 0.12, seed + 12, octaves=3)
        edge = saturate(self.edge * spread)
        worn = smoothstep(1.0 - amount * 0.9, 1.05 - amount * 0.5, edge * (0.45 + 0.75 * breakup) * (0.6 + 0.6 * broad))
        rubbed = smoothstep(0.80 - amount * 0.12, 0.9, breakup * 0.6 + broad * 0.5) * amount * 0.5
        return saturate(worn + rubbed * self.ao)

    def grime(self, amount=0.5, scale=60.0, seed=0):
        """Where dirt gathers: in corners and recesses, in drifts."""
        occluded = 1.0 - self.ao
        drift = self.noise(scale, seed + 21, octaves=4)
        broad = self.noise(scale * 0.15, seed + 22, octaves=3)
        packed = smoothstep(0.25 - amount * 0.2, 0.8, occluded * (0.6 + 0.8 * drift))
        film = smoothstep(0.62 - amount * 0.2, 0.95, broad * 0.6 + drift * 0.4) * amount * 0.6
        return saturate(packed * (0.4 + amount) + film)

    def dust(self, amount=0.5, scale=50.0, seed=0, up=(0.0, 0.0, 1.0)):
        """Dust settled on faces that look up."""
        facing = saturate(self.normal @ np.asarray(up, dtype=F))
        drift = self.noise(scale, seed + 31, octaves=3)
        return saturate(smoothstep(0.35, 1.0, facing) * (0.35 + 0.9 * drift) * amount)

    def scratches(self, density=1.0, seed=0, length=(0.002, 0.014)):
        """Fine scratches, drawn in the atlas."""
        n = self.ao.shape[0]
        marks = tex.scratches(n, self.seed + seed + 41, 2600 * density, length=length, width=0.0)
        # Scratches gather where things rub: near edges, and in patches.
        where = saturate(0.25 + self.edge * 0.9 + smoothstep(0.5, 0.8, self.noise(30.0, seed + 43)) * 0.6)
        return marks * where * self.covered

    def paint(self, mask, colour=None, roughness=None, metallic=None, height=None):
        """Lays a material down where `mask` says (0..1)."""
        if colour is not None:
            self.colour = lerp(self.colour, np.asarray(colour, dtype=F), mask)
        if roughness is not None:
            self.roughness = lerp(self.roughness, roughness, mask)
        if metallic is not None:
            self.metallic = lerp(self.metallic, metallic, mask)
        if height is not None:
            self.height = self.height + height * mask


# ---------------------------------------------------------------------------------------------
# Recipes: each paints one kind of material onto the texels of its slots
# ---------------------------------------------------------------------------------------------

def _region(surface, mask):
    return mask.astype(F)


def anodized(surface, mask, colour=(0.028, 0.029, 0.032), wear=0.5, grime=0.4):
    """Hard-anodised aluminium, as rifle receivers are: a dark satin skin over bright metal that
    shows on every worn edge."""
    m = _region(surface, mask)
    fine = surface.grain(2600.0, 1)
    broad = surface.noise(18.0, 2, octaves=3)
    skin = np.asarray(colour, dtype=F) * (0.82 + 0.36 * broad[..., None])
    surface.paint(m, skin, 0.50 + (fine - 0.5) * 0.10 + (broad - 0.5) * 0.10, 0.92, (fine - 0.5) * 0.000012)
    worn = surface.wear(wear, 160.0, 3) * m
    bright = tex.rgb(0.62, 0.63, 0.64) * (0.9 + 0.2 * fine[..., None])
    surface.paint(worn, bright, 0.30 + fine * 0.12, 1.0, -0.00001)
    # Handling polishes the flats a little, and leaves grease.
    polish = smoothstep(0.55, 0.85, surface.noise(40.0, 4)) * m * 0.5
    surface.paint(polish, None, surface.roughness * 0.78)
    scratched = surface.scratches(1.0, 5) * m * wear
    surface.paint(scratched * 0.55, tex.rgb(0.40, 0.40, 0.41), 0.32, 1.0)
    dirty = surface.grime(grime, 70.0, 6) * m
    surface.paint(dirty * 0.75, tex.rgb(0.07, 0.06, 0.05), 0.85, 0.0)


def steel(surface, mask, colour=(0.05, 0.052, 0.056), wear=0.5, grime=0.4, rust=0.15):
    """Phosphated or blued steel: barrels, muzzle devices, small parts. Greyer and rougher than
    anodising; wears to bright steel and takes a little rust."""
    m = _region(surface, mask)
    fine = surface.grain(1900.0, 1)
    broad = surface.noise(22.0, 2, octaves=3)
    skin = np.asarray(colour, dtype=F) * (0.78 + 0.44 * broad[..., None])
    surface.paint(m, skin, 0.60 + (fine - 0.5) * 0.14, 0.9, (fine - 0.5) * 0.00002)
    worn = surface.wear(wear, 150.0, 3) * m
    surface.paint(worn, tex.rgb(0.50, 0.50, 0.51), 0.34 + fine * 0.1, 1.0)
    rusty = smoothstep(0.78 - rust * 0.3, 0.9, surface.noise(120.0, 7, octaves=4) * 0.7 + (1 - surface.ao) * 0.5) * m * (rust > 0)
    surface.paint(rusty * 0.8, tex.rgb(0.20, 0.075, 0.025), 0.9, 0.1)
    dirty = surface.grime(grime, 70.0, 6) * m
    surface.paint(dirty * 0.7, tex.rgb(0.06, 0.055, 0.045), 0.88, 0.0)


def bright_steel(surface, mask, wear=0.4):
    """Bare polished steel: a bolt carrier, a trigger."""
    m = _region(surface, mask)
    fine = surface.grain(2200.0, 1)
    broad = surface.noise(30.0, 2, octaves=3)
    surface.paint(m, tex.rgb(0.52, 0.52, 0.53) * (0.85 + 0.3 * broad[..., None]), 0.28 + fine * 0.14, 1.0)
    burnt = smoothstep(0.5, 0.85, surface.noise(60.0, 3)) * m
    surface.paint(burnt * 0.5, tex.rgb(0.16, 0.14, 0.12), 0.55, 0.8)
    dirty = surface.grime(0.5, 80.0, 6) * m
    surface.paint(dirty * 0.7, tex.rgb(0.05, 0.045, 0.04), 0.8, 0.0)


def polymer(surface, mask, colour=(0.022, 0.022, 0.024), wear=0.4, grime=0.4, texture=1.0):
    """Moulded polymer furniture: stocks, grips, handguards, magazines. Matt, lightly textured,
    going shiny where it is handled and pale where it is scuffed."""
    m = _region(surface, mask)
    pebble = surface.grain(1500.0, 1)
    pebble2 = surface.grain(3300.0, 8)
    broad = surface.noise(16.0, 2, octaves=3)
    base = np.asarray(colour, dtype=F)
    skin = base * (0.85 + 0.3 * broad[..., None])
    relief = ((pebble - 0.5) * 0.00006 + (pebble2 - 0.5) * 0.00003) * texture
    surface.paint(m, skin, 0.62 + (pebble - 0.5) * 0.16, 0.0, relief)
    worn = surface.wear(wear, 150.0, 3, spread=1.2) * m
    scuff = lerp(base, tex.rgb(0.30, 0.29, 0.27), 0.35) * 1.6
    surface.paint(worn * 0.8, np.clip(scuff, 0, 1), 0.48, 0.0)
    handled = smoothstep(0.5, 0.8, surface.noise(35.0, 4)) * m * 0.6
    surface.paint(handled, None, surface.roughness * 0.72)
    scratched = surface.scratches(0.8, 5) * m
    surface.paint(scratched * 0.4, np.clip(base * 1.9 + 0.03, 0, 1), 0.7, 0.0)
    dirty = surface.grime(grime, 70.0, 6) * m
    dusty = surface.dust(grime * 0.6, 40.0, 9) * m
    surface.paint(saturate(dirty * 0.7 + dusty * 0.5), tex.rgb(0.13, 0.11, 0.085), 0.9, 0.0)


def rubber(surface, mask, colour=(0.02, 0.02, 0.021)):
    m = _region(surface, mask)
    fine = surface.grain(1800.0, 1)
    broad = surface.noise(20.0, 2, octaves=3)
    surface.paint(m, np.asarray(colour, dtype=F) * (0.8 + 0.4 * broad[..., None]), 0.86 + (fine - 0.5) * 0.1, 0.0,
                  (fine - 0.5) * 0.00005)
    dusty = saturate(surface.dust(0.5, 40.0, 9) + surface.grime(0.5, 60.0, 6)) * m
    surface.paint(dusty * 0.6, tex.rgb(0.14, 0.12, 0.10), 0.95, 0.0)


def brass(surface, mask, tarnish=0.4):
    """Cartridge brass."""
    m = _region(surface, mask)
    fine = surface.grain(2400.0, 1)
    broad = surface.noise(60.0, 2, octaves=3)
    surface.paint(m, tex.rgb(0.78, 0.57, 0.24) * (0.85 + 0.3 * broad[..., None]), 0.24 + fine * 0.12, 1.0)
    dull = smoothstep(0.55 - tarnish * 0.3, 0.9, broad) * m
    surface.paint(dull * 0.6, tex.rgb(0.34, 0.24, 0.11), 0.5, 0.9)


def copper(surface, mask):
    """A bullet's copper jacket."""
    m = _region(surface, mask)
    fine = surface.grain(2400.0, 1)
    surface.paint(m, tex.rgb(0.72, 0.36, 0.22) * (0.9 + 0.2 * fine[..., None]), 0.3 + fine * 0.1, 1.0)


def wood(surface, mask, colour=(0.20, 0.09, 0.04), grain_axis=1, varnish=0.5, wear=0.5, grime=0.4):
    """Oiled or varnished hardwood, the grain running along `grain_axis` (0 X, 1 Y, 2 Z):
    rifle furniture, tool handles."""
    m = _region(surface, mask)
    p = surface.position.astype(np.float64).copy()
    # Growth rings as shells about an axis off to one side of the piece, stretched along the grain.
    stretch = np.ones(3)
    stretch[grain_axis] = 0.03
    warp = fbm3(p * stretch * 40.0, surface.seed + 3, octaves=3) - 0.5
    axes = [a for a in range(3) if a != grain_axis]
    radial = np.sqrt((p[..., axes[0]] + 0.13) ** 2 + (p[..., axes[1]] + 0.07) ** 2)
    rings = 0.5 + 0.5 * np.sin((radial * 520.0 + warp * 9.0) * math.tau / 3.0)
    rings = (rings ** 1.6).astype(F)
    fibre = fbm3(p * stretch * 1400.0 + 7.0, surface.seed + 4, octaves=3)
    base = np.asarray(colour, dtype=F)
    late = base * 0.42
    early = np.clip(base * 1.55 + 0.01, 0, 1)
    skin = lerp(late, early, rings) * (0.82 + 0.36 * fibre[..., None])
    pores = saturate((fibre - 0.62) * 5.0)
    surface.paint(m, skin, lerp(0.62, 0.30, varnish) + pores * 0.2, 0.0, -pores * 0.00004 + (rings - 0.5) * 0.00002)
    worn = surface.wear(wear, 110.0, 5, spread=1.5) * m
    surface.paint(worn * 0.85, np.clip(base * 2.2 + 0.03, 0, 1) * (0.8 + 0.3 * fibre[..., None]), 0.7, 0.0)
    dented = smoothstep(0.78, 0.9, surface.noise(260.0, 6, octaves=3)) * m
    surface.paint(dented * 0.6, late * 0.6, 0.75, 0.0, -0.00012)
    dirty = surface.grime(grime, 70.0, 7) * m
    surface.paint(dirty * 0.75, tex.rgb(0.035, 0.026, 0.018), 0.85, 0.0)


def paint(surface, mask, colour=(0.16, 0.19, 0.10), wear=0.5, grime=0.5, rust=0.5, gloss=0.4,
          primer=(0.32, 0.12, 0.08), dust_colour=(0.20, 0.17, 0.13)):
    """Paint over steel: military equipment, vehicles, drums, boxes. Chips to primer and bare
    metal along edges, rusts where it has chipped, and gathers dust and streaks."""
    m = _region(surface, mask)
    fine = surface.grain(900.0, 1)
    peel = surface.grain(380.0, 12)
    broad = surface.noise(4.0, 2, octaves=4)
    base = np.asarray(colour, dtype=F)
    # Sun and weather fade paint unevenly.
    faded = lerp(base, np.clip(base * 1.25 + 0.03, 0, 1) * tex.rgb(1.0, 0.98, 0.94), smoothstep(0.4, 0.9, broad) * 0.5)
    surface.paint(m, faded, lerp(0.62, 0.28, gloss) + (peel - 0.5) * 0.06, 0.0, (peel - 0.5) * 0.00003)
    chipped = surface.wear(wear, 90.0, 3, spread=1.3) * m
    edge_primer = saturate(chipped * 1.6)
    surface.paint(edge_primer * 0.9, np.asarray(primer, dtype=F), 0.7, 0.0, -0.00004)
    bare = smoothstep(0.45, 0.8, chipped)
    surface.paint(bare, tex.rgb(0.40, 0.39, 0.38) * (0.8 + 0.3 * fine[..., None]), 0.42, 1.0, -0.00006)
    if rust > 0:
        blotch = surface.noise(55.0, 7, octaves=4)
        rusty = saturate(bare * smoothstep(0.35, 0.7, blotch) * rust * 2.0
                         + smoothstep(0.86 - rust * 0.16, 0.95, blotch * 0.75 + (1 - surface.ao) * 0.4) * m * rust)
        tone = lerp(tex.rgb(0.10, 0.035, 0.012), tex.rgb(0.33, 0.13, 0.04), surface.noise(300.0, 8, octaves=3))
        surface.paint(rusty, tone, 0.92, 0.05, 0.00003)
        # Rust weeps downward from where it starts.
        p = surface.position
        streak = fbm3(np.stack([p[..., 0] * 220.0, p[..., 1] * 220.0, p[..., 2] * 9.0], axis=-1), surface.seed + 9, octaves=3)
        weep = smoothstep(0.62, 0.9, streak) * smoothstep(0.5, 0.9, surface.noise(14.0, 10)) * m * rust * (1 - np.abs(surface.normal[..., 2]))
        surface.paint(weep * 0.45, tex.rgb(0.22, 0.10, 0.04), 0.85, 0.0)
    dirty = surface.grime(grime, 45.0, 6) * m
    dusty = surface.dust(grime, 30.0, 9) * m
    surface.paint(saturate(dirty * 0.7 + dusty * 0.75), np.asarray(dust_colour, dtype=F), 0.93, 0.0)


def glass_dark(surface, mask):
    """A lens or a dark window."""
    m = _region(surface, mask)
    smear = surface.noise(40.0, 1)
    surface.paint(m, tex.rgb(0.06, 0.08, 0.10), 0.05 + smear * 0.08, 1.0)


def emissive(surface, mask, colour=(1.0, 0.1, 0.05), strength=1.0):
    """Something lit from within: a sight's dot, an indicator lamp."""
    m = _region(surface, mask)
    surface.paint(m, np.asarray(colour, dtype=F), 0.4, 0.0)
    if surface.emissive is None:
        surface.emissive = np.zeros(surface.colour.shape, dtype=F)
    surface.emissive = lerp(surface.emissive, np.asarray(colour, dtype=F) * strength, m)


def fabric(surface, mask, colour=(0.2, 0.22, 0.14), grime=0.5, weave=900.0):
    """Woven cloth: webbing, pouches, slings, seat covers."""
    m = _region(surface, mask)
    p = surface.position
    # No finer than the texture can hold, or the weave turns to moire.
    weave = min(weave, 1.0 / (surface.texel_metres * SUPERSAMPLE * 3.2))
    warp = 0.5 + 0.5 * np.sin((p[..., 0] + p[..., 1] * 0.5) * weave * math.tau)
    weft = 0.5 + 0.5 * np.sin((p[..., 2] - p[..., 1] * 0.5) * weave * math.tau)
    thread = (warp * weft) ** 0.5
    fuzz = surface.grain(2400.0, 1)
    broad = surface.noise(10.0, 2, octaves=3)
    base = np.asarray(colour, dtype=F)
    surface.paint(m, base * (0.7 + 0.35 * thread[..., None]) * (0.85 + 0.3 * broad[..., None]), 0.93, 0.0,
                  thread * 0.00018 + (fuzz - 0.5) * 0.00004)
    frayed = surface.wear(0.5, 120.0, 3, spread=1.6) * m
    surface.paint(frayed * 0.5, np.clip(base * 1.7 + 0.04, 0, 1), 0.97, 0.0)
    dirty = saturate(surface.grime(grime, 50.0, 6) + surface.dust(grime * 0.7, 35.0, 9)) * m
    surface.paint(dirty * 0.6, tex.rgb(0.12, 0.10, 0.08), 0.96, 0.0)


# ---------------------------------------------------------------------------------------------
# An atlas: objects that share one set of textures
# ---------------------------------------------------------------------------------------------

def unwrap(objects, margin=0.004, angle=66.0):
    """Unwraps objects together into one atlas, every island at the same scale."""
    _select(objects)
    for obj in objects:
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name='UVMap')
        obj.data.uv_layers.active_index = 0
        obj.data.uv_layers[0].active_render = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    # Packed again by their true outlines, which fits a good deal more into the atlas.
    try:
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pack_islands(rotate=True, margin_method='FRACTION', margin=margin * 0.6,
                                shape_method='CONCAVE')
    except (TypeError, RuntimeError) as error:
        print(f'bake: islands left as first packed ({error})')
    bpy.ops.object.mode_set(mode='OBJECT')


class Atlas:
    """Objects that share one unwrapped texture set, painted by recipes."""

    def __init__(self, name, objects, size=1024, seed=1, margin=0.004, edge_radius=0.0022,
                 ao_distance=0.05):
        self.name = name
        self.objects = list(objects)
        self.size = size
        self.seed = seed
        self.margin = margin
        self.edge_radius = edge_radius
        self.ao_distance = ao_distance
        self.recipes = {}

    def recipe(self, material_name, function, **options):
        """Says which recipe paints the faces that have the material of this name."""
        self.recipes[material_name] = (function, options)
        return self

    def bake(self, out_dir, two_sided=False, unwrap=True):
        """Unwraps (unless the objects' own UVs are to be kept), bakes and paints, writes the
        textures, and gives every object the one finished material. Returns that material."""
        from . import bl
        for obj in self.objects:
            if obj.parent is None:
                bl.apply_transform(obj)
        if unwrap:
            globals()['unwrap'](self.objects, self.margin)
        names = []
        for obj in self.objects:
            for material in obj.data.materials:
                if material is not None and material.name not in names:
                    names.append(material.name)
        ids = {name: index for index, name in enumerate(names)}
        big = self.size * SUPERSAMPLE
        maps = geometry_maps(self.objects, big, self.edge_radius, self.ao_distance, ids)
        surface = Surface(maps, self.seed)
        if os.environ.get('BAKE_DEBUG'):
            debug = np.stack([maps['edge'], maps['ao'], covered_preview(maps)], axis=-1)
            tex.write_png(os.path.join(out_dir, f'{self.name}_debug.png'), downsample(debug, SUPERSAMPLE))
        surface.colour[...] = tex.rgb(0.5, 0.0, 0.5)
        for name, index in ids.items():
            mask = maps['slot'] == index
            if not mask.any():
                continue
            if name not in self.recipes:
                print(f'bake: {self.name}: no recipe for material `{name}`: left magenta')
                continue
            function, options = self.recipes[name]
            function(surface, mask, **options)

        covered = maps['covered']
        colour = dilate(surface.colour, covered)
        roughness = dilate(surface.roughness, covered)
        metallic = dilate(surface.metallic, covered)
        height = dilate(surface.height, covered, passes=4)
        ao = dilate(surface.ao, covered)
        # Slopes of the fine relief, in the atlas's own directions: a tangent-space normal map.
        scale = 1.0 / max(surface.texel_metres, 1e-6)
        dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * scale
        dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * scale
        inside = covered & np.roll(covered, 1, axis=1) & np.roll(covered, -1, axis=1) \
            & np.roll(covered, 1, axis=0) & np.roll(covered, -1, axis=0)
        dx = np.where(inside, dx, 0.0)
        dy = np.where(inside, dy, 0.0)
        normal = np.stack([-dx, dy, np.ones_like(dx)], axis=-1)
        normal /= np.linalg.norm(normal, axis=-1, keepdims=True)

        f = SUPERSAMPLE
        normal = downsample(normal, f)
        normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
        made = tex.TextureSet(self.name, downsample(colour, f), normal, downsample(roughness, f),
                              downsample(metallic, f), downsample(saturate(ao * 0.75 + 0.25), f))
        made.write(out_dir)
        material = bl.material(f'{self.name}', self.name, tex_dir=out_dir, two_sided=two_sided)
        material['unique_uv'] = True
        if surface.emissive is not None:
            emissive_map = downsample(dilate(surface.emissive, covered), f)
            path = os.path.join(out_dir, f'{self.name}_emissive.png')
            tex.write_png(path, saturate(emissive_map), is_colour=True)
            nodes, links = material.node_tree.nodes, material.node_tree.links
            bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
            image = nodes.new('ShaderNodeTexImage')
            image.image = bl.load_image(path, True)
            links.new(image.outputs['Color'], bsdf.inputs['Emission Color'])
            bsdf.inputs['Emission Strength'].default_value = 1.0
        for obj in self.objects:
            obj.data.materials.clear()
            obj.data.materials.append(material)
            for polygon in obj.data.polygons:
                polygon.material_index = 0
        coverage = float(covered.mean())
        print(f'bake: {self.name}: {len(self.objects)} objects, {coverage * 100:.0f}% of the atlas used, '
              f'{surface.texel_metres * 1000 * f:.2f} mm a texel', flush=True)
        return material
