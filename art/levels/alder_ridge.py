"""Alder Ridge, Oregon, in the second year of the occupation: the level of DEAD AIR.

    python art/levels/alder_ridge.py

A safehouse on Juniper Court; back yards and an alley down to Alder Street; the Directorate's
checkpoint where Alder meets Mill Road; and the filling station on the far corner, where the
truck that has silenced the town stands under its mast. The plan itself (streets, lots, what
the ground is) is in alder_layout.py, which the ground's own script reads too.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alder_layout as plan  # noqa: E402
from common import Level  # noqa: E402

level = Level('alder_ridge')
rng = random.Random(1907)
G = plan.height
K = plan.KERB

# What each prop is made of, for the sound and the dust of a bullet striking it.
SURFACES = [
    (('fence_wood', 'fence_gate', 'fence_picket', 'pallet', 'crate_wood', 'woodpile', 'picnic', 'workbench', 'shelving',
      'map_table', 'utility_pole', 'boxes'), 'wood'),
    (('jersey', 'rubble', 'station_store', 'hydrant'), 'concrete'),
    (('sandbag', 'hesco'), 'dirt'),
    (('banner', 'washing_line', 'bedroll', 'lawn_chair', 'trash_bin', 'cone', 'tyre'), 'cloth'),
]
GHOSTS = ('wire_span', 'graffiti', 'banner', 'washing_line', 'flag_pole')
# Where things already stand: (x, z, radius), so that trees and grass keep off them.
blocked = []
# Where the broad-leaved trees stand in the town: their leaves lie under them.
canopies = []


def surface_of(name):
    for names, kind in SURFACES:
        if name.startswith(names):
            return kind
    return 'metal'


# Boxes that stand in for a thing's own shape where people and bullets are concerned: its own
# is many small triangles, which cost a great deal to walk a person against. Each is
# (x, y, z, size x, size y, size z) in the thing's own space: y up, z toward its back.
PANEL = [(0, 0.925, 0, 2.5, 1.85, 0.1)]
CAB = [(0, 1.9, -0.6, 2.4, 1.7, 1.84), (0, 1.5, -2.46, 1.5, 0.94, 1.88), (0, 0.62, 0.1, 2.3, 1.0, 7.3)]
PROXIES = {
    'jersey': [(0, 0.405, 0, 3.0, 0.81, 0.5)],
    'sandbag_wall': [(-0.08, 0.53, 0, 2.34, 1.06, 0.62)],
    'sandbag_low': [(-0.08, 0.305, 0, 2.32, 0.61, 0.62)],
    'sandbag_corner': [(-0.08, 0.53, 0, 2.34, 1.06, 0.62), (1.05, 0.53, 1.05, 0.62, 1.06, 2.4)],
    'hesco': [(0, 0.7, 0, 1.14, 1.4, 1.14)],
    'fence_wood': PANEL,
    'fence_wood_broken': PANEL,
    'fence_picket': [(0, 0.52, 0, 2.5, 1.05, 0.08)],
    'dumpster': [(0, 0.75, 0, 1.98, 1.5, 1.84)],
    'generator': [(0, 0.74, -0.12, 2.0, 1.48, 1.25)],
    'woodpile': [(0, 0.44, 0, 1.78, 0.88, 0.48)],
    'sedan': [(0, 0.56, 0, 1.8, 0.74, 4.7), (0, 1.18, 0.55, 1.5, 0.5, 2.3)],
    'pickup': [(0, 0.80, 0, 1.92, 0.9, 5.5), (0, 1.52, -0.28, 1.72, 0.6, 1.85)],
    'van': [(0, 1.14, 0.78, 1.94, 1.64, 3.45), (0, 0.72, -1.72, 1.9, 0.8, 1.55)],
    'patrol': [(0, 0.9, 0, 1.86, 0.7, 4.3), (0, 1.6, 0.62, 1.8, 0.7, 2.95)],
    'truck_cargo': CAB + [(0, 2.07, 2.14, 2.5, 2.06, 3.44)],
    'truck_jammer': CAB + [(0, 2.05, 2.15, 2.46, 1.97, 3.42)],
}
# These stop people and nothing else: a bullet goes through wire.
EDGES = {
    'wire_coil': [(0, 0.45, 0, 3.0, 0.9, 0.8)],
    'fence_chain': [(0, 1.2, 0, 3.06, 2.4, 0.1)],
}


def proxy(name, x, y, z, yaw, surface, wide=1.0):
    """Stands a thing's boxes where it stands. Returns whether it had any."""
    for table, solid in ((PROXIES, True), (EDGES, False)):
        key = next((k for k in sorted(table, key=len, reverse=True) if name.startswith(k)), None)
        if key is None:
            continue
        angle = math.radians(yaw)
        for lx, ly, lz, sx, sy, sz in table[key]:
            lx, sx = lx * wide, sx * wide
            level.blocker(x + lx * math.cos(angle) + lz * math.sin(angle), y + ly,
                          z - lx * math.sin(angle) + lz * math.cos(angle), sx, sy, sz, yaw,
                          surface=surface if solid else None)
        return True
    return False


def prop(name, x, z, yaw=0.0, lift=0.0, **options):
    """Stands a prop on the ground."""
    options.setdefault('surface', surface_of(name))
    if name.startswith(GHOSTS):
        options.setdefault('collide', 'none')
    y = G(x, z) + lift
    if 'collide' not in options and 'pitch' not in options and proxy(name, x, y, z, yaw, options['surface'],
                                                                      options.get('sx', 1.0)):
        options['collide'] = 'none'
    level.place(f'p:{name}', x, y, z, yaw, **options)


def vehicle(name, x, z, yaw, **options):
    options.setdefault('surface', 'metal')
    if proxy(name, x, G(x, z), z, yaw, 'metal'):
        options['collide'] = 'none'
    level.place(f'v:{name}', x, G(x, z), z, yaw, **options)
    blocked.append((x, z, 3.2 if 'truck' in name else 2.6))


def fence(kind, x0, z0, x1, z1, gaps=(), broken=(), panel=2.5):
    """A run of fence panels from one point to another, along X or along Z. `gaps` are the
    stretches (from, to), in metres along the run, left open; `broken` the panels, by number,
    that have been kicked in."""
    length = math.hypot(x1 - x0, z1 - z0)
    count = max(1, round(length / panel))
    step = length / count
    yaw = 0.0 if abs(x1 - x0) > abs(z1 - z0) else 90.0
    for i in range(count):
        middle = (i + 0.5) * step
        if any(a < middle < b for a, b in gaps):
            continue
        share = middle / length
        part = 'fence_wood_broken' if i in broken else kind
        prop(part, x0 + (x1 - x0) * share, z0 + (z1 - z0) * share, yaw, sx=round(step / panel, 4))


def tree(species, x, z, scale=1.0, tint=None, variant=None):
    words = [f'tree {species} {x:.2f} {G(x, z):.2f} {z:.2f}', f'yaw={rng.uniform(0, 360):.0f}', f'scale={scale:.2f}',
             f'variant={rng.randrange(4) if variant is None else variant}']
    if tint is not None:
        words.append('tint=' + ','.join(f'{c:.2f}' for c in tint))
    level.add(' '.join(words))
    blocked.append((x, z, 1.2))
    bx0, bz0, bx1, bz1 = plan.PLAY
    if species in ('oak', 'birch') and bx0 < x < bx1 and bz0 < z < bz1:
        canopies.append((x, z))


# Autumn: what the leaves have turned to, as multiples of their summer green.
GOLD = (2.3, 1.3, 0.45)
AMBER = (2.5, 0.95, 0.3)
RUSSET = (2.1, 0.62, 0.3)
FADING = (1.5, 1.2, 0.6)
GREEN = None


def autumn():
    return rng.choice((GOLD, GOLD, AMBER, AMBER, RUSSET, FADING, GREEN))


def light(x, y, z, reach, colour, name=None):
    r, g, b = colour
    level.add(f'light {x:.2f} {y:.2f} {z:.2f} {reach:.1f} {r:.2f} {g:.2f} {b:.2f}' + (f' name={name}' if name else ''))


WHITE = (1.0, 0.95, 0.85)
WARM = (1.0, 0.62, 0.3)


def floodlight(x, z, yaw, reach=20.0, power=1.0):
    """A work light on its tripod, and the light it throws: `yaw` is the way its lamps look."""
    prop('floodlight', x, z, yaw)
    angle = math.radians(yaw)
    ahead = (-math.sin(angle), -math.cos(angle))
    light(x + ahead[0] * 1.2, G(x, z) + 3.6, z + ahead[1] * 1.2, reach, tuple(c * power for c in WHITE))


# =============================================================================================
# Kits, people, pools
# =============================================================================================
level.add('camera 16.2 1.9 -69.0 -1.5708 -0.05')
level.kit('g', '../kits/alder_ground.glb')
level.kit('h', '../kits/houses.glb')
level.kit('p', '../kits/props.glb')
level.kit('v', '../kits/vehicles.glb')
level.kit('l', '../kits/litter.glb')
level.standard(soldiers=24, rebels=2)

# =============================================================================================
# The ground and the houses
# =============================================================================================
for part, kind, collide in (('lawn', 'grass', 'coarse'), ('sidewalk', 'concrete', 'auto'), ('concrete', 'concrete', 'auto'),
                            ('gravel', 'dirt', 'auto'), ('dirt', 'dirt', 'auto'), ('asphalt', 'asphalt', 'coarse'),
                            ('asphalt_patch', 'asphalt', 'none'), ('mark_yellow', 'asphalt', 'none'),
                            ('mark_white', 'asphalt', 'none')):
    level.place(f'g:ground_{part}', 0, 0, 0, 0, collide=collide, surface=kind)
level.place('g:ground_far', 0, 0, 0, 0, collide='coarse', surface='grass')

for entry in plan.HOUSES:
    level.place(f"h:{entry['part']}", entry['x'], K, entry['z'], entry['yaw'], surface='wood')
# The streets behind: roofs over the fences, nobody home.
for part, x, z, yaw in (('house_b_tan', 62, -60, 0), ('house_a_grey', 86, -62, 0), ('house_c_red', 112, -61, 0),
                        ('house_a_blue', 70, 62, 180), ('house_b_white', 30, 61, 180), ('house_c_blue', 100, 63, 180),
                        ('house_a_cream', -4, 62, 180), ('house_b_green', -62, -24, 90), ('house_c_white', -62, -56, 90),
                        ('house_a_grey', 60, -98, 180), ('house_b_green', 160, 62, 0), ('house_c_red', 196, -30, 90),
                        ('house_a_cream', 168, -66, 0)):
    level.place(f'h:{part}', x, K, z, yaw, surface='wood')
    blocked.append((x, z, 11.0))

# =============================================================================================
# The safehouse: a garage on Juniper Court
# =============================================================================================
# Its inside runs x 13.45..19.75, z -71.95..-66.05, on a slab 0.24 above the road.
FLOOR = K + 0.12
level.place('p:workbench', 16.6, FLOOR, -71.5, 180, surface='wood')
level.place('p:shelving', 14.6, FLOOR, -66.35, 0, surface='wood')
level.place('p:map_table', 15.4, FLOOR, -69.9, 75, surface='wood')
level.place('p:bedroll', 18.9, FLOOR, -67.3, 0, surface='cloth')
level.place('p:bedroll', 17.6, FLOOR, -67.2, 8, surface='cloth')
level.place('p:boxes', 14.3, FLOOR, -71.2, 20, surface='wood')
level.place('p:crate_military', 18.6, FLOOR, -71.4, 4, surface='metal')
level.place('p:crate_long', 18.5, FLOOR + 0.5, -71.4, -6, surface='metal')
level.place('p:ammo_box', 14.05, FLOOR + 0.82, -71.15, 30, surface='metal', tag='pickup', collide='none')
level.place('p:drum_blue', 13.9, FLOOR, -68.4, 0, surface='metal')
level.place('p:tyre_stack', 13.95, FLOOR, -67.4, 0, surface='cloth')
level.place('p:graffiti_here', 17.4, FLOOR + 0.25, -66.08, 0, collide='none', surface='wood')
light(15.5, FLOOR + 1.5, -69.8, 5.0, tuple(c * 0.2 for c in WARM), name='lantern')
light(18.3, FLOOR + 2.0, -68.0, 4.0, tuple(c * 0.08 for c in WARM))

# =============================================================================================
# The back yards: the way out, fenced from the alley and from each other
# =============================================================================================
ALLEY_W = 37.4
# The safehouse's yard.
fence('fence_wood', 20.0, -78.0, ALLEY_W, -78.0)
fence('fence_wood', 20.0, -78.0, 20.0, -72.4)
fence('fence_wood', 21.0, -54.0, 21.0, -56.2, panel=2.2)
# Along the alley, from the head of the yards down to the corner lot.
fence('fence_wood', ALLEY_W, -78.0, ALLEY_W, -33.5, broken=(9,))
# Between the safehouse and the cottage: two panels are down.
fence('fence_wood', 21.0, -54.0, ALLEY_W, -54.0, gaps=((8.2, 10.6),), broken=(2, 5))
prop('fence_wood_broken', 30.3, -54.9, 12, pitch=-74, collide='none')
# The cottage's yard: shut off from the court on both sides of the house.
fence('fence_wood', 22.6, -54.0, 22.6, -48.3)
fence('fence_wood', 22.6, -38.5, 22.6, -33.5)
# Between the cottage and the corner house: a gap by the alley.
fence('fence_wood', 10.0, -33.5, ALLEY_W, -33.5, gaps=((21.6, 24.4),), broken=(7,))
prop('fence_wood_broken', 32.8, -32.5, -8, pitch=78, collide='none')
# The corner house's yard, and its gate onto the alley.
fence('fence_wood', 10.0, -33.5, 10.0, -24.0)
fence('fence_wood', 10.0, -24.0, 12.6, -24.0, panel=2.6)
fence('fence_wood', 30.4, -21.0, ALLEY_W, -21.0)
fence('fence_wood', ALLEY_W, -33.5, ALLEY_W, -21.0, gaps=((3.7, 5.6),))
prop('fence_gate', ALLEY_W, -29.75, 90, sx=2.27, collide='none')

# What two years have left in them.
level.place('h:shed_green', 34.0, K, -74.6, 90, surface='wood')
prop('woodpile', 26.0, -77.4, 0)
prop('woodpile', 28.0, -77.4, 0)
prop('washing_line', 27.5, -62.5, 90)
prop('lawn_chair', 23.2, -64.5, -60)
prop('lawn_chair_fallen', 24.6, -66.0, 20)
prop('barbecue', 22.6, -62.3, 0)
prop('trash_bin', 21.0, -73.4, 0)
prop('trash_bin', 21.0, -74.3, 10)
prop('tyre_stack', 35.9, -70.0, 0)
prop('drum_rust', 36.4, -56.0, 0)
prop('swing_set', 30.0, -44.0, 90)
prop('picnic_table', 27.0, -50.2, 14)
level.place('h:shed_red', 34.6, K, -37.0, -90, surface='wood')
prop('lawn_chair_fallen', 25.0, -41.0, 130)
prop('trash_bin_tipped', 23.6, -36.2, 40)
prop('pallet', 35.6, -47.5, 12)
prop('washing_line', 22.0, -28.8, 0)
prop('barbecue', 27.6, -26.0, 0)
prop('woodpile', 14.0, -32.8, 0)
prop('crate_wood', 35.8, -24.2, 8)
prop('trash_bin', 31.4, -22.0, 0)
prop('picnic_table', 17.5, -28.5, 80)

# =============================================================================================
# The alley
# =============================================================================================
ALLEY_E = 42.6
fence('fence_wood', ALLEY_E, -78.0, ALLEY_E, -40.0)
fence('fence_wood', ALLEY_E, -40.0, ALLEY_E, -12.5, broken=(4,))
fence('fence_chain', 38.0, -80.2, 42.0, -80.2, panel=3.0)
prop('dumpster', 41.2, -49.0, 90)
prop('trash_bin', 41.6, -52.0, 0)
prop('trash_bin_tipped', 38.6, -60.0, 200)
prop('pallet', 41.5, -64.0, 0)
prop('pallet', 41.45, -64.05, 30, lift=0.12)
prop('crate_wood', 41.4, -66.2, 20)
prop('tyre_stack', 38.3, -72.0, 0)
prop('drum_rust', 41.7, -34.0, 0)
prop('drum_rust', 41.6, -35.0, 0)
prop('rubble_2', 39.0, -78.6, 0, collide='none')
prop('graffiti_air', 42.52, -26.0, 90, lift=-0.1)
prop('graffiti_here', 37.48, -44.0, -90, lift=-0.15)
for z in (-70.0, -40.0, -10.5):
    prop('utility_pole', 43.3, z, 90)
for z in (-55.0, -25.25):
    prop('wire_span', 43.3, z, 0, sz=0.98 if z > -40 else 1.0)
prop('ammo_box', 40.3, -49.9, 80, tag='pickup', collide='none')

# =============================================================================================
# Alder Street
# =============================================================================================
# The west end is shut.
for z in (-3.1, 0.0, 3.1):
    prop('jersey', -42.0, z, 90)
prop('wire_coil', -40.4, -2.4, 90)
prop('wire_coil', -40.4, 1.6, 90)
prop('tank_trap', -39.0, 3.6, 30)
prop('tank_trap', -38.6, -3.9, 70)
prop('notice_order', -37.5, -5.3, -90)
vehicle('van_green', -47.5, 0.6, 62)
vehicle('sedan_burnt', -52.0, -2.4, -20)

# Left at the kerb, in the drives, and where they stopped.
vehicle('sedan_white', -24.0, 3.5, -90)
vehicle('sedan_silver', 2.0, 10.2, 180)
vehicle('pickup_red', 26.8, -9.9, 0)
vehicle('sedan_blue', 14.0, -3.4, 90)
vehicle('sedan_burnt', 31.0, 1.3, 68)
vehicle('van_white', 49.5, -3.35, 90)
vehicle('pickup_tan', 57.5, 3.3, -84)
vehicle('sedan_maroon', 66.0, -0.9, 122)
vehicle('pickup_burnt', 71.6, 1.7, 28)
vehicle('sedan_silver', 80.5, 3.45, -90)
vehicle('van_green', 88.5, -3.3, 96)
vehicle('sedan_blue', 99.6, -9.4, 0)
vehicle('sedan_white', 50.0, 9.6, 180)
# On Juniper Court.
vehicle('sedan_maroon', 9.0, -69.0, 90)
vehicle('van_white', -3.05, -30.0, 4)
vehicle('pickup_tan', -9.0, -48.8, -90)
rubble = ((62.5, 0.9, 1), (69.0, -2.6, 2), (33.5, -1.0, 2))
for x, z, kind in rubble:
    prop(f'rubble_{kind}', x, z, rng.uniform(0, 360), collide='none')

# Lamps that no longer light, poles, wires.
for x in (-30, 14, 60, 92):
    prop('street_light', x, -5.2, 180)
for x in (-12, 36, 76, 112):
    prop('street_light', x, 5.2, 0)
for z in (-28, -62):
    prop('street_light', 4.7, z, -90)
poles = [-50, -20, 10, 40, 70, 100]
for x in poles:
    prop('utility_pole', x, 5.6, 0)
for a, b in zip(poles, poles[1:]):
    prop('wire_span', (a + b) / 2, 5.6, 90)
# Signs: whose streets these were, and whose they are now.
prop('stop_sign', -4.9, -8.4, 0)
prop('sign_juniper', 5.0, -8.6, 0)
prop('sign_mill', 124.6, 7.0, 0)
prop('stop_sign', 124.7, -8.2, -90)
prop('notice_curfew', 8.6, -5.3, -90)
prop('notice_order', 46.0, -5.3, -90)
prop('notice_checkpoint', 88.0, 5.3, 90)
prop('notice_checkpoint', 91.5, -5.3, 90)
prop('hydrant', 34.0, 5.1, 0)
prop('hydrant', -3.3, -9.2, 90)
prop('hydrant', 121.0, -5.2, 180)
# What was put out and never collected.
for x, z, yaw, part in ((-27.5, 6.6, 0, 'trash_bin'), (0.5, 6.5, 0, 'trash_bin_tipped'), (20.0, 6.7, 180, 'trash_bin'),
                        (53.5, -6.7, 0, 'trash_bin'), (54.4, -6.6, 30, 'trash_bin_tipped'), (78.0, -6.8, 0, 'trash_bin'),
                        (96.0, 6.6, 90, 'trash_bin_tipped'), (4.8, -36.0, 90, 'trash_bin'), (-4.8, -52.0, 0, 'trash_bin')):
    prop(part, x, z, yaw)
# Letter boxes at the foot of each drive.
for entry in plan.HOUSES:
    kind = plan.HOUSE_KINDS[plan.house_kind(entry['part'])]
    side = kind['drive'][1] + 0.7
    x, z = plan.to_world(entry['x'], entry['z'], entry['yaw'], side, entry['kerb'] - 0.7)
    if plan.surface(x, z)[0] in ('lawn', 'sidewalk'):
        prop('mailbox', x, z, entry['yaw'] + 90)
# Picket fences along two front gardens.
fence('fence_picket', 62.0, 8.0, 71.5, 8.0, gaps=((6.0, 7.6),))
fence('fence_picket', 68.6, -8.0, 78.6, -8.0, gaps=((1.2, 2.8),))
fence('fence_picket', -31.0, 8.0, -21.0, 8.0, gaps=((6.4, 8.0),))
# The Directorate's colours on the house they have taken.
prop('banner', 112.6, -12.75, 180, lift=2.6, collide='none')

# =============================================================================================
# The back fences: where the town ends, as far as anyone on foot is concerned
# =============================================================================================
fence('fence_wood', ALLEY_E, -40.0, 123.6, -40.0, broken=(11, 23))
fence('fence_wood', 123.6, -40.0, 123.6, -26.0)
fence('fence_wood', -60.0, 41.0, 123.6, 41.0, broken=(15, 40))
fence('fence_wood', 123.6, 41.0, 123.6, 25.0)
fence('fence_wood', -38.5, -84.0, -38.5, -8.0)
fence('fence_wood', -38.5, -84.0, -13.0, -84.0)
fence('fence_wood', -38.5, 8.0, -38.5, 12.5, panel=2.25)
fence('fence_wood', -60.0, 8.0, -60.0, 41.0)
# Between the lots along Alder, behind the houses' fronts.
for x, z0, z1 in ((64.0, -40.0, -24.0), (84.0, -40.0, -24.5), (105.5, -40.0, -24.5), (-36.0, 41.0, 25.0), (-14.0, 41.0, 24.5),
                  (10.0, 41.0, 24.0), (34.0, 41.0, 24.5), (57.0, 41.0, 24.5), (73.0, 41.0, 25.0), (99.0, 41.0, 24.5)):
    fence('fence_wood', x, z0, x, z1)

# =============================================================================================
# The checkpoint, where Alder Street meets Mill Road
# =============================================================================================
# What a driver meets first.
for x, z in ((93.0, -3.6), (93.6, -1.2), (94.2, 1.2)):
    prop('cone', x, z, 0)
prop('tank_trap', 96.0, 3.9, 20)
prop('tank_trap', 96.6, -4.0, 65)
# The chicane.
prop('jersey', 100.0, -2.7, 90)
prop('jersey', 100.1, 0.4, 84)
prop('jersey', 106.0, 2.7, 90)
prop('jersey', 105.9, -0.4, 96)
prop('wire_coil', 100.9, 3.1, 90)
prop('wire_coil', 105.1, -3.2, 90)
# The north post: sandbags on the verge, the booth, the boom.
prop('sandbag_corner', 103.2, -7.4, 90)
prop('sandbag_wall', 106.5, -6.2, 90)
prop('sandbag_low', 109.6, -5.5, 6)
prop('guard_booth', 113.6, -6.9, 180)
prop('boom_gate', 111.6, -4.95, -90)
prop('boom_gate_up', 111.6, 4.95, 90)
prop('crate_military', 115.6, -6.2, 8)
prop('crate_military', 115.7, -6.25, -5, lift=0.5)
prop('ammo_box', 115.5, -6.2, 40, lift=1.0, tag='pickup', collide='none')
prop('drum_red', 117.0, -8.6, 0)
prop('drum_red', 117.7, -8.3, 0)
prop('generator', 118.6, -10.6, 90)
# A fire in a drum, where the guard stands the night.
prop('drum_fire', 110.6, -8.9, 0)
level.marker('fire', 'checkpoint', 110.6, K + 0.86, -8.9, heat=1.0)
light(110.6, K + 1.5, -8.9, 7.0, (1.6, 0.85, 0.32))
prop('pallet', 112.0, -10.4, 30)
prop('crate_wood', 109.2, -10.2, 15)
# The south post.
prop('sandbag_wall', 108.4, 5.6, 90)
prop('sandbag_corner', 111.0, 7.4, 90)
for x in (114.4, 115.6, 116.8):
    prop('hesco', x, 6.7, 0)
prop('hesco', 116.8, 7.9, 0)
prop('crate_long', 118.4, 9.4, 12)
prop('flag_pole', 119.6, 8.6, 30)
# The tower on the corner, and the car that waits behind the barrier.
prop('watchtower', 120.6, -10.6, 0)
vehicle('patrol', 117.0, 1.6, 64)
vehicle('truck_cargo', 131.6, 15.5, 0)
floodlight(102.0, -8.6, 100, reach=22, power=1.25)
floodlight(109.6, 8.9, 70, reach=22, power=1.25)
floodlight(118.9, -7.2, -60, reach=20, power=1.0)
light(113.6, K + 2.1, -6.9, 5.0, tuple(c * 0.6 for c in WHITE))
light(120.6, K + 6.0, -10.6, 9.0, tuple(c * 0.5 for c in WHITE))
prop('notice_curfew', 122.6, 6.3, 90)

# Mill Road is shut north and south, and Alder east of the station.
for x in (127.0, 130.0, 133.0):
    prop('jersey', x, -58.0, 0)
    prop('jersey', x, 50.0, 0)
prop('wire_coil', 128.4, -56.6, 0)
prop('wire_coil', 131.6, -56.6, 0)
prop('wire_coil', 130.0, 48.6, 0)
prop('tank_trap', 126.6, 47.6, 10)
prop('tank_trap', 133.4, -55.4, 50)
prop('notice_order', 135.3, -52.0, 180)
for z in (-3.1, 0.0, 3.1):
    prop('jersey', 181.0, z, 90)
prop('wire_coil', 179.5, -2.0, 90)
prop('wire_coil', 179.5, 2.0, 90)
vehicle('truck_cargo', 187.5, 0.6, 76)

# =============================================================================================
# Cascade Fuel: the station, and the jammer
# =============================================================================================
level.place('p:station_canopy', 154.0, K, -22.0, 0, surface='metal')
for x in (149.0, 159.0):
    for z in (-23.4, -20.6):
        level.place('p:station_pump', x, K + 0.16, z, 90, surface='metal')
level.place('p:station_store', 156.0, K, -39.5, 180, surface='concrete')
prop('station_sign', 140.6, -10.2, 90)
# The truck with the mast, its panel toward the street.
proxy('truck_jammer', 147.0, K, -29.2, 90, 'metal')
level.place('v:truck_jammer', 147.0, K, -29.2, 90, surface='metal', tag='jammer_intact', collide='none')
level.place('v:truck_jammer_wreck', 147.0, K, -29.2, 90, surface='metal', tag='jammer_wreck', collide='none')
blocked.append((147.0, -29.2, 5.0))
prop('generator', 152.8, -31.6, 0)
prop('drum_red', 154.6, -31.4, 0)
prop('drum_red', 155.3, -31.8, 0)
prop('drum_red', 154.9, -30.7, 0)
prop('drum_blue', 141.2, -33.0, 0)
prop('crate_military', 143.6, -33.6, 80)
prop('crate_long', 145.6, -33.9, 5)
prop('crate_wood', 141.4, -26.2, 12)
prop('pallet', 141.3, -28.6, 0)
# Cover on the forecourt.
prop('hesco', 141.0, -9.4, 0)
prop('hesco', 142.2, -9.4, 0)
prop('hesco', 151.8, -9.4, 0)
prop('hesco', 153.0, -9.4, 0)
prop('hesco', 159.4, -9.4, 0)
prop('sandbag_wall', 146.0, -15.2, 0)
prop('sandbag_low', 162.6, -15.6, 0)
prop('sandbag_wall', 138.9, -24.8, 90)
prop('jersey', 165.5, -27.0, 70)
prop('dumpster', 165.8, -40.2, 0)
prop('tyre_stack', 147.4, -41.6, 0)
prop('tyre_stack', 148.2, -42.2, 0)
prop('trash_bin_tipped', 163.4, -34.2, 100)
prop('notice_order', 163.9, -35.3, 180)
prop('banner', 159.0, -19.75, 180, lift=0.3, sx=0.55, sy=0.75, collide='none')
prop('ammo_box', 150.4, -34.9, 15, tag='pickup', collide='none')
floodlight(140.2, -20.6, -72, reach=22, power=1.1)
floodlight(153.6, -34.0, 28, reach=18, power=0.9)
for x in (150.0, 154.0, 158.0):
    light(x, K + 4.7, -22.0, 9.0, tuple(c * 0.45 for c in WHITE))
light(155.3, K + 2.6, -38.0, 7.0, tuple(c * 0.8 for c in WARM))
fence('fence_chain', 138.0, -46.4, 176.0, -46.4, panel=3.0)
fence('fence_chain', 176.4, -46.4, 176.4, -7.5, panel=3.0)

# The yard across the road, where their lorries park.
for x in (138.6, 139.8, 141.0, 142.2, 143.4, 144.6, 145.8, 160.2, 161.4, 162.6, 163.8, 165.0, 166.2, 167.4):
    prop('hesco', x, 9.2, 0)
vehicle('truck_cargo', 166.0, 22.0, 180)
vehicle('patrol', 151.0, 30.0, -100)
prop('generator', 172.0, 14.0, 0)
prop('drum_fire', 156.0, 19.0, 0)
level.marker('fire', 'yard', 156.0, K + 0.86, 19.0, heat=1.0)
light(156.0, K + 1.5, 19.0, 7.0, (1.6, 0.85, 0.32))
prop('crate_military', 158.0, 14.5, 20)
prop('crate_military', 159.5, 14.3, -4)
prop('crate_long', 158.6, 14.4, 6, lift=0.5)
prop('drum_blue', 173.6, 18.0, 0)
prop('drum_red', 174.2, 18.8, 0)
prop('pallet', 170.0, 35.0, 0)
prop('tyre_stack', 141.0, 36.0, 0)
floodlight(146.6, 12.4, -160, reach=20, power=0.9)
fence('fence_chain', 138.0, 42.4, 178.0, 42.4, panel=3.0)
fence('fence_chain', 178.4, 42.4, 178.4, 7.5, panel=3.0)

# =============================================================================================
# Trees
# =============================================================================================
# Along the streets.
for x, z, species, scale in ((-22, -5.3, 'birch', 0.95), (30, -5.3, 'oak', 0.8), (68, -5.25, 'birch', 1.0),
                             (-34, 5.3, 'oak', 0.85), (8, 5.25, 'birch', 0.9), (62, 5.3, 'oak', 0.8), (95, 5.25, 'birch', 1.05)):
    tree(species, x, z, scale, autumn())
# In the gardens.
for x, z, species, scale in ((31.5, -68.0, 'oak', 1.0), (25.5, -46.5, 'birch', 0.9), (34.5, -57.5, 'bush', 1.0),
                             (15.0, -27.0, 'oak', 0.9), (24.0, -75.5, 'bush', 1.1), (8.5, -52.5, 'birch', 0.85),
                             (-28.0, -28.0, 'oak', 1.1), (-30.0, -62.0, 'birch', 1.0), (-10.0, -72.0, 'oak', 0.9),
                             (52.0, -32.0, 'oak', 1.15), (76.0, -33.0, 'birch', 1.0), (93.0, -34.0, 'oak', 1.0),
                             (116.0, -34.0, 'birch', 0.9), (60.0, -12.0, 'bush', 0.9), (81.5, -11.0, 'birch', 0.8),
                             (-45.0, 33.0, 'oak', 1.1), (-20.0, 34.0, 'birch', 1.0), (3.0, 33.0, 'oak', 1.0),
                             (26.0, 34.0, 'oak', 1.2), (48.0, 33.0, 'birch', 0.95), (66.0, 35.0, 'oak', 1.0),
                             (92.0, 33.0, 'birch', 1.0), (113.0, 34.0, 'oak', 1.1), (11.0, 10.5, 'bush', 0.9),
                             (56.5, 11.0, 'birch', 0.8), (101.0, 10.5, 'bush', 1.0), (-14.5, -93.0, 'oak', 1.1),
                             (21.0, -90.0, 'birch', 1.0), (30.0, -86.0, 'oak', 1.0)):
    tree(species, x, z, scale, autumn() if species != 'bush' else rng.choice((FADING, GREEN)))


def clear(x, z, room):
    if plan.surface(x, z)[0] != 'lawn' or plan.built_on(x, z, room):
        return False
    return all(math.hypot(x - bx, z - bz) > radius + room for bx, bz, radius in blocked)


# Beyond the fences: the woods the town was cut out of.
def woods(count, x0, z0, x1, z1, firs=0.5, low=0.85, high=1.35):
    placed = 0
    tries = 0
    while placed < count and tries < count * 30:
        tries += 1
        x, z = rng.uniform(x0, x1), rng.uniform(z0, z1)
        px0, pz0, px1, pz1 = plan.PLAY
        inside = px0 - 2 < x < px1 + 2 and pz0 - 2 < z < pz1 + 2
        bx0, bz0, bx1, bz1 = plan.BOUNDS
        if bx0 < x < bx1 and bz0 < z < bz1:
            if not clear(x, z, 2.5):
                continue
            if inside and -42 < z < 42.5 and -40 < x < 180:
                continue
        if rng.random() < firs:
            tree('fir', x, z, rng.uniform(low, high) * 1.1)
        else:
            tree(rng.choice(('oak', 'oak', 'birch')), x, z, rng.uniform(low, high), autumn())
        placed += 1


woods(26, 44, -58, 122, -43, firs=0.35)
woods(26, -58, 43.5, 122, 58, firs=0.35)
woods(14, -66, -84, -40.5, 8, firs=0.4)
woods(12, 137.5, -64, 198, -48.5, firs=0.5)
woods(10, 180, 9, 198, 60, firs=0.5)
woods(12, -36, -116, 60, -88, firs=0.5)
woods(10, 44, -84, 122, -66, firs=0.5)
# The ridge.
woods(70, -260, -300, 400, -125, firs=0.85, low=1.1, high=1.8)
woods(40, 205, -120, 420, 120, firs=0.85, low=1.1, high=1.8)
woods(40, -280, 85, 400, 260, firs=0.8, low=1.1, high=1.8)
woods(26, -300, -120, -75, 80, firs=0.8, low=1.1, high=1.8)

# =============================================================================================
# Grass: two summers unmown
# =============================================================================================
def lawns(x0, z0, x1, z1):
    """Grows every lawn in a rectangle: one patch, two metres square, wherever a whole patch
    fits on grass. What grows is the same over a few patches at a time, so that it lies in
    drifts."""
    drifts = {}
    count = 0
    for i in range(int(x0 // 2), int(x1 // 2)):
        for j in range(int(z0 // 2), int(z1 // 2)):
            x, z = i * 2 + 1.0, j * 2 + 1.0
            if any(plan.surface(x + dx, z + dz)[0] != 'lawn' for dx, dz in ((0, 0), (-1, -1), (1, -1), (-1, 1), (1, 1),
                                                                             (0, -1), (0, 1), (-1, 0), (1, 0))):
                continue
            if plan.built_on(x, z, 1.2):
                continue
            key = (i // 4, j // 4)
            if key not in drifts:
                drifts[key] = rng.choices(('meadow', 'verge', 'tall', 'dry'), weights=(50, 26, 12, 12))[0]
            breed = drifts[key] if rng.random() < 0.8 else rng.choice(('meadow', 'verge'))
            level.add(f'grass {breed} {x:.1f} {K:.2f} {z:.1f} turn={rng.randrange(4)} variant={rng.randrange(4)}')
            count += 1
    return count


grown = lawns(-40, -84, 124, 42)
grown += lawns(124, -60, 180, 46)
print('grass patches:', grown)

# =============================================================================================
# What lies on the ground: a year's leaves, and the occupier's leaflets
# =============================================================================================
def litter(part, x, z, yaw=None):
    """Lays a two-metre sheet of litter flat on the ground, where the ground under all of it
    is at one height. Returns whether it could."""
    heights = [G(x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
    if max(heights) - min(heights) > 1e-3:
        return False
    if plan.built_on(x, z, 0.6):
        return False
    level.place(f'l:{part}', x, heights[0], z, rng.uniform(0, 360) if yaw is None else yaw, collide='none')
    return True


strewn = 0
# Under the trees that have dropped them, thick near the trunk and thinning outward.
for x, z in canopies:
    for part, count, reach in (('leaves_a', 3, 3.2), ('leaves_b', 4, 6.0), ('leaves_c', 3, 8.5)):
        for _ in range(count):
            angle, away = rng.uniform(0, math.tau), rng.uniform(0.8, reach)
            strewn += litter(part, x + math.cos(angle) * away, z + math.sin(angle) * away)
# Blown into the gutters: drifts along the kerbs of each street.
x = -38.0
while x < 122.0:
    for z in (-3.45, 3.45):
        if rng.random() < 0.62:
            strewn += litter('leaves_a' if rng.random() < 0.6 else 'leaves_b', x + rng.uniform(-1, 1), z, rng.choice((0, 180)))
    x += rng.uniform(2.6, 4.4)
z = -78.0
while z < -10.0:
    for x in (-2.95, 2.95):
        if rng.random() < 0.6:
            strewn += litter('leaves_a' if rng.random() < 0.5 else 'leaves_b', x, z + rng.uniform(-1, 1), rng.choice((90, 270)))
    z += rng.uniform(2.6, 4.6)
# And anywhere at all.
for _ in range(240):
    x, z = rng.uniform(-38, 176), rng.uniform(-82, 42)
    strewn += litter(rng.choice(('leaves_b', 'leaves_c', 'leaves_c')), x, z)
# Leaflets, where the lorries threw them out.
for x, z in ((88.5, -1.5), (95.5, 2.4), (103.0, -3.0), (112.5, 1.8), (121.0, -1.0), (60.5, 2.0), (40.5, -9.5), (8.0, -1.8),
             (127.5, -14.0), (143.5, -12.5), (118.5, -8.2)):
    strewn += litter('leaflets', x, z)
print('litter:', strewn)

# =============================================================================================
# The edges of the world
# =============================================================================================
x0, z0, x1, z1 = plan.PLAY
level.blocker((x0 + x1) / 2, 6, z0 - 1, x1 - x0 + 4, 14, 2)
level.blocker((x0 + x1) / 2, 6, z1 + 1, x1 - x0 + 4, 14, 2)
level.blocker(x0 - 1, 6, (z0 + z1) / 2, 2, 14, z1 - z0 + 4)
level.blocker(x1 + 1, 6, (z0 + z1) / 2, 2, 14, z1 - z0 + 4)
# The ends of the streets, just behind their barricades.
level.blocker(-43.2, 6, 0, 1, 14, 16)
level.blocker(182.2, 6, 0, 1, 14, 16)
level.blocker(130, 6, -59.2, 16, 14, 1)
level.blocker(130, 6, 51.2, 16, 14, 1)

# =============================================================================================
# The mission
# =============================================================================================
level.marker('player', 'start', 16.2, FLOOR + 0.02, -69.0, -90)
# What the title is shown over: the checkpoint, from down the street.
level.marker('view', 'title', 90.5, 2.3, 2.6, -88, pitch=1.5, fov=48, sweep=0.1)
level.marker('goal', 'garage_door', 21.6, K, -70.9)
level.marker('goal', 'yards', 34.8, K, -29.6)
level.marker('goal', 'checkpoint', 108.0, 0, 0)
level.marker('goal', 'jammer', 149.85, K + 0.75, -27.75)
level.marker('use', 'jammer', 149.85, K + 0.75, -27.75, radius=2.6, hold=3.0, prompt='Hold_E_to_plant_the_charge')
level.marker('goal', 'jammer_b', 155.0, K + 0.6, -31.3)
level.marker('goal', 'rally', 113.6, K, 8.4)

# The cell: waiting in the yard.
level.marker('spawn', 'cell', 23.4, K, -72.6, 60, kind='rebel_a', follow=1)
level.marker('spawn', 'cell', 25.6, K, -69.2, 100, kind='rebel_b', follow=1)
# The patrol that walks the alley.
for n, z in enumerate((-66.0, -44.0, -16.0, -44.0)):
    level.marker('route', 'alley', 40.0, K, z, 0, n=n)
level.marker('spawn', 'patrol', 40.0, K, -76.0, 180, patrol='alley')
level.marker('spawn', 'patrol', 39.2, K, -76.9, 180, patrol='alley')
level.marker('spawn', 'patrol', 40.8, K, -78.6, 180, patrol='alley')
# The checkpoint's garrison.
for x, z in ((104.6, -7.1), (107.5, -6.4), (113.4, -9.6), (109.4, 5.8), (112.4, 7.8), (118.2, 4.6), (120.0, -3.6)):
    level.marker('spawn', 'checkpoint', x, G(x, z), z, 90)
# The sentry in the tower: he sees over everything, and does not come down.
level.marker('spawn', 'checkpoint', 120.5, K + 4.5, -10.4, 90, hold=1)
# Those who guard the truck.
for x, z in ((151.5, -18.5), (157.0, -25.6), (142.4, -31.4), (160.5, -33.5), (143.0, -17.0)):
    level.marker('spawn', 'station', x, G(x, z), z, 100)
# And those who come when it is too late.
for x, z in ((168.5, 27.0), (170.5, 30.0), (166.5, 31.5), (177.0, -2.2), (178.0, 1.6), (176.0, 0.2)):
    level.marker('spawn', 'reinforcements', x, G(x, z), z, 90)

# Ammunition, where the boxes with the `pickup` tag stand, in the same order.
level.marker('pickup', 'garage', 14.05, FLOOR + 0.82, -71.15, rounds=90)
level.marker('pickup', 'alley', 40.3, K, -49.9, rounds=60)
level.marker('pickup', 'booth', 115.5, K + 1.0, -6.2, rounds=90)
level.marker('pickup', 'store', 150.4, K, -34.9, rounds=90)

# Something is burning beyond the ridge, as something always is.
level.marker('plume', 'north', -150.0, 40.0, -330.0, heat=1.0)
level.marker('plume', 'east', 420.0, 30.0, 60.0, heat=0.8)
level.setting('mission', 'dead_air')
# Dusk in October, deepening as the mission goes on, and stopping short of night.
level.setting('time', 17.5)
level.setting('time_stop', 17.68)
level.setting('day_seconds', 72000)
level.setting('day', 291)
level.setting('latitude', 44.5)
level.setting('weather', 'broken')
level.setting('exposure', 2.0)
level.setting('nav', '6 -82 184 44')
level.write()
