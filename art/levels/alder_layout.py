"""The plan of Alder Ridge, shared by the script that builds its ground (in Blender) and the
script that writes its level (anywhere): streets, lots, houses, and what the ground is made of
at any point.

Engine coordinates: X east, Z south (north is -Z), in metres. Alder Street runs east-west
along z = 0; Juniper Court runs north from it at x = 0 to a turning circle at z = -86; Mill Road crosses
at x = 130. A thing's yaw is in degrees: 0 faces north (-Z), 90 west, -90 east, 180 south.
"""

import math

KERB = 0.12
LOW, HIGH, RAMP = 0, 1, 2

# The ground is cut to this rectangle; beyond it the far terrain takes over.
BOUNDS = (-70.0, -120.0, 200.0, 80.0)
# Where the player can go.
PLAY = (-46.0, -104.0, 184.0, 44.0)

REGIONS = []
HOUSES = []


def rect(x0, z0, x1, z1):
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def disc(cx, cz, radius, sides=32):
    return [(cx + radius * math.cos(math.tau * i / sides), cz + radius * math.sin(math.tau * i / sides))
            for i in range(sides)]


def paint(material, polygon, level=HIGH, clip=None, ramp=None):
    """Lays `material` over a convex polygon. Later regions cover earlier ones. `level` LOW is
    the roadway, HIGH is kerb height, RAMP slopes between them: `ramp` is then (axis, where
    it is low, where it is high). `clip` keeps the region to a rectangle (x0, z0, x1, z1)."""
    REGIONS.append(dict(material=material, polygon=polygon, level=level, clip=clip, ramp=ramp))


def _inside(region, x, z):
    clip = region['clip']
    if clip is not None and not (clip[0] <= x <= clip[2] and clip[1] <= z <= clip[3]):
        return False
    polygon = region['polygon']
    sign = 0
    for (ax, az), (bx, bz) in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (bx - ax) * (z - az) - (bz - az) * (x - ax)
        if abs(cross) < 1e-9:
            continue
        if sign == 0:
            sign = 1 if cross > 0 else -1
        elif (cross > 0) != (sign > 0):
            return False
    return True


def surface(x, z):
    """What the ground is at a point: (material, height)."""
    material, level, ramp = 'lawn', HIGH, None
    for region in REGIONS:
        if _inside(region, x, z):
            material, level, ramp = region['material'], region['level'], region['ramp']
    if level == LOW:
        return material, 0.0
    if level == RAMP and ramp is not None:
        axis, low, high = ramp
        share = ((x if axis == 'x' else z) - low) / (high - low)
        return material, KERB * min(max(share, 0.0), 1.0)
    return material, KERB


def height(x, z):
    return surface(x, z)[1]


def to_world(x, z, yaw, local_x, local_y):
    """Where a point of a model is in the world: `local_y` is toward the model's front."""
    angle = math.radians(yaw)
    local_z = -local_y
    return (x + local_x * math.cos(angle) + local_z * math.sin(angle),
            z - local_x * math.sin(angle) + local_z * math.cos(angle))


def local_rect(x, z, yaw, x0, y0, x1, y1):
    ax, az = to_world(x, z, yaw, x0, y0)
    bx, bz = to_world(x, z, yaw, x1, y1)
    return rect(ax, az, bx, bz)


# What each kind of house needs of the ground, in its own space (x to its right as seen from
# behind... that is, Blender's X; y toward the street): the driveway's two sides and where it
# starts, the door path's two sides and where the steps end.
HOUSE_KINDS = {
    'a': dict(drive=(5.5, 10.5, 4.1), path=(-0.65, 0.65, 5.6), drive_material='concrete',
              bounds=(-6.2, -4.7, 11.8, 6.2)),
    # The cream one is built the other way round, its garage on the left.
    'm': dict(drive=(-10.5, -5.5, 4.1), path=(-0.65, 0.65, 5.6), drive_material='concrete',
              bounds=(-11.8, -4.7, 6.2, 6.2)),
    'b': dict(drive=(-7.3, -2.3, 4.8), path=(-0.75, 0.55, 5.5), drive_material='concrete',
              bounds=(-8.3, -4.95, 9.4, 6.1)),
    'c': dict(drive=(-7.6, -4.6, -3.0), path=(1.65, 2.95, 7.0), drive_material='gravel',
              bounds=(-4.4, -5.3, 5.2, 7.6)),
}


def house_kind(part):
    if part == 'house_a_cream':
        return 'm'
    return 'a' if part.startswith('house_a') or part == 'house_safe' else part[6]


def footprint(entry, margin=0.0):
    """The rectangle of ground a house stands on: (x0, z0, x1, z1)."""
    x0, y0, x1, y1 = HOUSE_KINDS[house_kind(entry['part'])]['bounds']
    corners = local_rect(entry['x'], entry['z'], entry['yaw'], x0 - margin, y0 - margin, x1 + margin, y1 + margin)
    return (corners[0][0], corners[0][1], corners[2][0], corners[2][1])


def built_on(x, z, margin=0.0):
    """Whether a house stands at this point."""
    for entry in HOUSES:
        x0, z0, x1, z1 = footprint(entry, margin)
        if x0 <= x <= x1 and z0 <= z <= z1:
            return True
    return False


def house(part, x, z, yaw, kerb, verge=1.5, walk=1.5, name=None):
    """Stands a house on its lot and lays its driveway and the path to its door. `kerb` is how
    far in front of the house's own origin the kerb of its street runs."""
    kind = HOUSE_KINDS[house_kind(part)]
    lot = kerb - verge - walk
    x0, x1, start = kind['drive']
    paint(kind['drive_material'], local_rect(x, z, yaw, x0, start, x1, lot))
    # The ramp down to the road crosses the verge, or the pavement where there is no verge.
    foot = kerb - (verge if verge > 0 else walk)
    low = to_world(x, z, yaw, 0, kerb)
    high = to_world(x, z, yaw, 0, foot)
    along_x = abs(low[0] - high[0]) > abs(low[1] - high[1])
    ramp = ('x', low[0], high[0]) if along_x else ('z', low[1], high[1])
    paint(kind['drive_material'], local_rect(x, z, yaw, x0, foot, x1, kerb), level=RAMP, ramp=ramp)
    px0, px1, steps = kind['path']
    paint('sidewalk', local_rect(x, z, yaw, px0, steps, px1, lot))
    HOUSES.append(dict(part=part, x=x, z=z, yaw=yaw, name=name or part, kerb=kerb))


def corner(x, z, dx, dz, radius):
    """Rounds the kerb where two streets meet: the corner of the block at (x, z), the block
    lying toward (dx, dz)."""
    square = rect(x, z, x + dx * radius, z + dz * radius)
    paint('asphalt', square, level=LOW)
    clip = (min(p[0] for p in square), min(p[1] for p in square), max(p[0] for p in square), max(p[1] for p in square))
    paint('sidewalk', disc(x + dx * radius, z + dz * radius, radius), clip=clip)


def build():
    # --- Pavements --------------------------------------------------------------------------
    paint('sidewalk', rect(-70, -7.5, 200, -6))
    paint('sidewalk', rect(-70, 6, 200, 7.5))
    paint('sidewalk', rect(-5.5, -82, 5.5, -7.5))
    paint('sidewalk', disc(0, -86, 12.5))
    paint('sidewalk', rect(7.35, -98.5, 8.65, -95.0))
    paint('sidewalk', rect(124, -120, 136, 80))

    # --- The filling station's forecourt, and the yard the Directorate parks in ------------
    paint('concrete', rect(138, -46, 176, -7.5))
    paint('concrete', rect(136, -31, 138, -19))
    paint('gravel', rect(138, 7.5, 178, 42))
    # --- The alley behind Juniper Court ------------------------------------------------------
    paint('gravel', rect(38, -80, 42, -7.5))
    paint('dirt', rect(37.4, -80, 38, -7.5))
    paint('dirt', rect(42, -80, 42.6, -7.5))

    # --- Houses: Alder Street, north side (they face south) --------------------------------
    house('house_a_cream', -21.0, -19.1, 180, kerb=14.6)
    house('house_b_green', 22.0, -19.2, 180, kerb=14.7, name='corner')
    house('house_a_grey', 56.0, -19.1, 180, kerb=14.6)
    house('house_c_white', 74.0, -20.5, 180, kerb=16.0)
    house('house_b_tan', 95.0, -19.2, 180, kerb=14.7)
    house('house_c_blue', 114.0, -20.5, 180, kerb=16.0, name='billet')
    # --- Alder Street, south side (they face north) -----------------------------------------
    house('house_b_white', -49.0, 19.2, 0, kerb=14.7)
    house('house_c_red', -26.0, 20.5, 0, kerb=16.0)
    house('house_a_blue', -6.0, 19.1, 0, kerb=14.6)
    house('house_b_green', 23.0, 19.2, 0, kerb=14.7)
    house('house_a_grey', 42.0, 19.1, 0, kerb=14.6)
    house('house_c_white', 66.0, 20.5, 0, kerb=16.0)
    house('house_a_cream', 86.0, 19.1, 0, kerb=14.6)
    house('house_b_tan', 112.0, 19.2, 0, kerb=14.7)
    # --- Juniper Court, east side (they face west) ------------------------------------------
    house('house_c_red', 17.5, -43.0, 90, kerb=13.5, verge=0)
    house('house_safe', 16.7, -61.0, 90, kerb=12.7, verge=0, name='safehouse')
    # --- Juniper Court, west side (they face east) ------------------------------------------
    house('house_b_white', -16.7, -44.0, -90, kerb=12.7, verge=0)
    house('house_c_blue', -17.5, -60.0, -90, kerb=13.5, verge=0)
    # --- The head of the court (it faces south, down the court) ------------------------------
    house('house_a_blue', 8.0, -110.0, 180, kerb=13.5, verge=0)

    # --- Worn ground --------------------------------------------------------------------------
    for x, z, radius in ((27.5, -66.0, 1.6), (30.0, -58.5, 1.3), (30.5, -47.0, 2.0), (33.0, -30.0, 1.8),
                         (104.0, -6.6, 2.2), (110.0, 6.8, 2.0), (120.5, -10.5, 2.6), (150.0, 20.0, 5.0),
                         (163.0, 30.0, 4.0), (-30.0, -40.0, 1.5), (60.0, 30.0, 1.8)):
        paint('dirt', disc(x, z, radius, 14))

    # --- Roads --------------------------------------------------------------------------------
    paint('asphalt', rect(-70, -4.5, 200, 4.5), level=LOW)
    paint('asphalt', rect(-4, -82, 4, -4.5), level=LOW)
    paint('asphalt', disc(0, -86, 11), level=LOW)
    paint('asphalt', rect(125.5, -120, 134.5, 80), level=LOW)
    corner(4, -4.5, 1, -1, 3.0)
    corner(-4, -4.5, -1, -1, 3.0)
    corner(125.5, -4.5, -1, -1, 4.0)
    corner(125.5, 4.5, -1, 1, 4.0)
    corner(134.5, -4.5, 1, -1, 4.0)
    corner(134.5, 4.5, 1, 1, 4.0)
    # Repairs, older and darker than the road round them.
    for patch in (rect(18, -3.9, 25, -1.4), rect(68, 0.6, 72, 3.6), rect(97, -2.2, 106, 0.4), rect(-31, 0.8, -24, 3.2),
                  rect(-2.6, -44, 0.2, -37), rect(126.5, -52, 129.5, -44), rect(150, -3.5, 156, -1.0)):
        paint('asphalt_patch', patch, level=LOW)

    # --- Ways on and off the road -------------------------------------------------------------
    paint('gravel', rect(38, -6, 42, -4.5), level=RAMP, ramp=('z', -4.5, -6))
    for x0, x1 in ((141, 151), (161, 171)):
        paint('concrete', rect(x0, -6, x1, -4.5), level=RAMP, ramp=('z', -4.5, -6))
    paint('concrete', rect(134.5, -31, 136, -19), level=RAMP, ramp=('x', 134.5, 136))
    paint('gravel', rect(147, 4.5, 159, 6), level=RAMP, ramp=('z', 4.5, 6))

    # --- Paint on the road --------------------------------------------------------------------
    x = -68.0
    while x < 196:
        if not 119 < x + 1.5 < 141:
            paint('mark_yellow', rect(x, -0.07, x + 3, 0.07), level=LOW)
        x += 9.0
    for z0, z1 in ((-118, -9.5), (9.5, 78)):
        paint('mark_yellow', rect(129.8, z0, 129.92, z1), level=LOW)
        paint('mark_yellow', rect(130.08, z0, 130.2, z1), level=LOW)
    paint('mark_white', rect(-3.8, -8.3, -0.15, -7.9), level=LOW)
    paint('mark_white', rect(120.3, 0.15, 120.7, 4.3), level=LOW)
    paint('mark_white', rect(139.3, -4.3, 139.7, -0.15), level=LOW)
    paint('mark_white', rect(125.7, -9.9, 129.75, -9.5), level=LOW)
    paint('mark_white', rect(130.25, 9.5, 134.3, 9.9), level=LOW)
    z = -4.1
    while z < 4.0:
        paint('mark_white', rect(121.6, z, 124.4, z + 0.4), level=LOW)
        z += 1.0


build()
