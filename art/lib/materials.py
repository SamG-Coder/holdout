"""The tiling materials of HOLDOUT: each a function that synthesises a seamless PBR texture set
with real-world scale (`tile_metres` says how much surface one repeat covers).

Albedos are kept in physically plausible ranges (asphalt about 0.07, concrete 0.4, white paint
0.8) so that surfaces sit correctly beside each other under one exposure.
"""

import math

import numpy as np

from . import tex
from .tex import F, TextureSet, blur, fbm, lerp, saturate, smoothstep


def _finish(name, colour, height_m, roughness, tile, metallic=None, cavity_radius=6.0,
            cavity_strength=1.0, alpha=None, cavity=None):
    normal = tex.normal_from_height(height_m, tile)
    if cavity is None:
        cavity = tex.cavity_from_height(height_m, cavity_radius, cavity_strength)
    return TextureSet(name, colour, normal, roughness, metallic, cavity, alpha, tile_metres=tile)


# ---------------------------------------------------------------------------------------------
# Ground
# ---------------------------------------------------------------------------------------------

def asphalt(n=1024, seed=11):
    """Aged road asphalt: dark binder, paler exposed aggregate, hairline cracks."""
    tile = 2.0
    f1, f2, ids = tex.worley(n, 150, seed)
    stones = saturate(1.0 - f1 * 1.5)
    fine_f1, _, fine_ids = tex.worley(n, 330, seed + 1)
    grit = saturate(1.0 - fine_f1 * 1.6)
    blotch = fbm(n, seed + 2, beta=2.4, lo=1, hi=12)
    wear = fbm(n, seed + 3, beta=1.6, lo=3)
    # Cracks: the edges of a few big cells, broken up so they start and stop.
    c1, c2, _ = tex.worley(n, 5, seed + 4, jitter=0.9)
    crack_line = tex.cracks(1.0 - smoothstep(0.0, 0.011, c2 - c1), seed + 5)
    crack = saturate(crack_line * smoothstep(0.56, 0.72, fbm(n, seed + 6, beta=2.2, lo=1, hi=6)))
    height = stones * 0.0022 + grit * 0.0009 + (wear - 0.5) * 0.0015 - crack * 0.006
    binder = lerp(tex.rgb(0.06, 0.06, 0.06), tex.rgb(0.11, 0.107, 0.10), blotch)
    stone_colour = tex.ramp(ids, [(0.0, tex.rgb(0.10, 0.10, 0.10)), (0.6, tex.rgb(0.17, 0.165, 0.155)),
                                  (0.85, tex.rgb(0.26, 0.25, 0.23)), (1.0, tex.rgb(0.34, 0.30, 0.25))])
    exposed = smoothstep(0.35, 0.8, stones) * (0.45 + 0.55 * wear)
    colour = lerp(binder, stone_colour, exposed)
    colour = lerp(colour, tex.ramp(fine_ids, [(0, tex.rgb(0.06)), (1, tex.rgb(0.2, 0.19, 0.18))]),
                  smoothstep(0.5, 0.9, grit) * 0.35)
    colour = colour * (0.85 + 0.3 * blotch[..., None])
    colour = lerp(colour, tex.rgb(0.02, 0.02, 0.02), crack * 0.9)
    roughness = 0.9 - exposed * 0.18 + crack * 0.1
    return _finish('asphalt', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=1.4)


def concrete(n=1024, seed=21, name='concrete'):
    """Cast concrete: mottled grey, sandy, pitted, with faint stains."""
    tile = 2.0
    blotch = fbm(n, seed, beta=2.6, lo=1, hi=10)
    mid = fbm(n, seed + 1, beta=1.8, lo=6)
    sand = blur(tex.white(n, seed + 2), 0.7)
    sand = tex.normalize01(sand)
    pits = tex.speckle(n, seed + 3, n * n / 2600, 1.3, 0.45)
    big_pits = tex.speckle(n, seed + 4, n * n / 70000, 2.4, 0.5)
    stains = smoothstep(0.55, 0.85, fbm(n, seed + 5, beta=2.8, lo=1, hi=5))
    streak = fbm(n, seed + 6, beta=2.0, lo=2, aniso=(1.0, 0.08))
    c1, c2, _ = tex.worley(n, 3, seed + 7, jitter=1.0)
    hair = tex.cracks(1.0 - smoothstep(0.0, 0.012, c2 - c1), seed + 8)
    hair = hair * smoothstep(0.6, 0.78, fbm(n, seed + 9, beta=2.2, lo=1, hi=5))
    height = (mid - 0.5) * 0.0012 + (sand - 0.5) * 0.0005 - pits * 0.0016 - big_pits * 0.004 - hair * 0.002
    base = tex.ramp(blotch, [(0.0, tex.rgb(0.24, 0.235, 0.22)), (0.5, tex.rgb(0.32, 0.315, 0.30)),
                             (1.0, tex.rgb(0.40, 0.39, 0.365))])
    colour = base * (0.9 + 0.2 * mid[..., None]) * (0.94 + 0.12 * sand[..., None])
    colour = lerp(colour, colour * tex.rgb(0.62, 0.58, 0.52), stains * 0.55)
    colour = lerp(colour, colour * 0.8, smoothstep(0.6, 0.9, streak) * 0.25)
    colour = lerp(colour, colour * 0.45, saturate(pits + big_pits) * 0.8)
    colour = lerp(colour, colour * 0.35, hair * 0.8)
    roughness = 0.82 + (mid - 0.5) * 0.12 + stains * 0.06
    return _finish(name, colour, height, roughness, tile, cavity_radius=4.0)


def sidewalk(n=1024, seed=31):
    """A pavement slab: broom-finished concrete with a tooled joint around its edge. One tile is
    one slab, 1.5 m square."""
    tile = 1.5
    base = concrete(n, seed, name='sidewalk')
    x, y = tex.grid(n)
    edge = np.minimum(np.minimum(x, 1 - x), np.minimum(y, 1 - y)) * tile  # metres from the joint
    joint = 1.0 - smoothstep(0.004, 0.011, edge)
    trowel = 1.0 - smoothstep(0.035, 0.055, edge)
    broom = tex.band(n, seed + 20, 150, 50, aniso=(0.04, 1.0))
    blotch = fbm(n, seed + 21, beta=2.6, lo=1, hi=8)
    grit = blur(tex.white(n, seed + 22), 0.6)
    pits = tex.speckle(n, seed + 23, n * n / 2500, 1.4, 0.45)
    height = ((broom - 0.5) * 0.0011 * (1 - trowel) + (tex.normalize01(grit) - 0.5) * 0.0004
              - pits * 0.0012 - joint * 0.007)
    colour = tex.ramp(blotch, [(0, tex.rgb(0.29, 0.285, 0.27)), (1, tex.rgb(0.42, 0.41, 0.385))])
    colour = colour * (0.93 + 0.14 * broom[..., None])
    colour = lerp(colour, colour * 1.06, trowel * 0.5)
    dirt = smoothstep(0.0, 0.03, 0.03 - edge + (fbm(n, seed + 24, beta=2, lo=4) - 0.5) * 0.03)
    colour = lerp(colour, tex.rgb(0.09, 0.08, 0.065), saturate(joint * 0.9 + dirt * 0.35))
    colour = lerp(colour, colour * 0.5, pits * 0.7)
    stains = smoothstep(0.6, 0.9, fbm(n, seed + 25, beta=2.8, lo=1, hi=4))
    colour = lerp(colour, colour * tex.rgb(0.7, 0.66, 0.6), stains * 0.4)
    roughness = 0.86 - trowel * 0.12 + joint * 0.1
    del base
    return _finish('sidewalk', colour, height, roughness, tile, cavity_radius=4.0)


def dirt(n=1024, seed=41):
    """Bare packed soil with small stones."""
    tile = 2.0
    broad = fbm(n, seed, beta=2.5, lo=1, hi=10)
    clumps = fbm(n, seed + 1, beta=1.9, lo=5)
    f1, _, ids = tex.worley(n, 60, seed + 2)
    stones = smoothstep(0.62, 0.9, 1.0 - f1 * 1.3) * (ids > 0.72)
    fine = tex.normalize01(blur(tex.white(n, seed + 3), 0.8))
    height = (broad - 0.5) * 0.02 + (clumps - 0.5) * 0.012 + stones * 0.006 + (fine - 0.5) * 0.0012
    colour = tex.ramp(clumps, [(0, tex.rgb(0.085, 0.058, 0.036)), (0.5, tex.rgb(0.14, 0.10, 0.065)),
                               (1, tex.rgb(0.21, 0.16, 0.11))])
    colour = colour * (0.82 + 0.36 * broad[..., None]) * (0.9 + 0.2 * fine[..., None])
    colour = lerp(colour, tex.ramp(ids, [(0.7, tex.rgb(0.2, 0.19, 0.17)), (1, tex.rgb(0.42, 0.4, 0.36))]),
                  stones * 0.9)
    roughness = 0.94 - stones * 0.2
    return _finish('dirt', colour, height, roughness, tile, cavity_radius=5.0, cavity_strength=1.3)


def lawn(n=1024, seed=51):
    """A mown lawn seen from above: the ground beneath the blades of grass, and all there is of
    the lawn far away. Dry patches, thatch and bare soil show through."""
    tile = 2.0
    blades_a = tex.band(n, seed, 180, 70, aniso=(0.25, 1.0))
    blades_b = tex.band(n, seed + 1, 180, 70, aniso=(1.0, 0.25))
    blades_c = tex.band(n, seed + 2, 260, 90)
    blades = tex.normalize01(np.maximum(np.maximum(blades_a, blades_b), blades_c))
    patch = fbm(n, seed + 3, beta=2.4, lo=1, hi=8)
    dry = smoothstep(0.55, 0.8, fbm(n, seed + 4, beta=2.2, lo=2, hi=12))
    bare = smoothstep(0.68, 0.85, fbm(n, seed + 5, beta=2.0, lo=3, hi=20)) * 0.6
    height = blades * 0.012 * (1 - bare) + (patch - 0.5) * 0.01
    green = tex.ramp(blades, [(0.0, tex.rgb(0.012, 0.024, 0.006)), (0.5, tex.rgb(0.03, 0.062, 0.013)),
                              (1.0, tex.rgb(0.055, 0.10, 0.024))])
    straw = tex.ramp(blades, [(0.0, tex.rgb(0.05, 0.04, 0.018)), (1.0, tex.rgb(0.19, 0.16, 0.075))])
    soil = tex.ramp(fbm(n, seed + 6, beta=1.8, lo=6), [(0, tex.rgb(0.07, 0.05, 0.03)), (1, tex.rgb(0.16, 0.12, 0.08))])
    # Only a little of either: a patch that shows is a patch seen again every two metres.
    colour = lerp(green, straw, dry * 0.2)
    colour = colour * (0.9 + 0.2 * patch[..., None])
    colour = lerp(colour, soil, bare * 0.3)
    roughness = np.full((n, n), 0.92, dtype=F) - blades * 0.08
    return _finish('lawn', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=1.5)


def gravel(n=1024, seed=61):
    """Crushed stone on a lane, trodden into the dirt it was laid on: small angular stones,
    the fines and the earth showing between them."""
    tile = 1.0
    f1, f2, ids = tex.worley(n, 58, seed)
    g1, _, gids = tex.worley(n, 150, seed + 1)
    big = saturate(1.0 - f1 * 1.25) ** 0.6
    small = saturate(1.0 - g1 * 1.3) ** 0.7
    between = smoothstep(0.0, 0.12, f2 - f1)
    # Where the lane is worn, the stones have sunk and the earth has come up over them.
    worn = smoothstep(0.42, 0.7, fbm(n, seed + 3, beta=2.2, lo=1, hi=7))
    proud = big * between * (1.0 - worn * 0.65)
    height = proud * 0.008 + small * 0.003 * (1 - proud * 0.7)
    stone = tex.ramp(ids, [(0, tex.rgb(0.10, 0.095, 0.09)), (0.4, tex.rgb(0.17, 0.165, 0.155)),
                           (0.75, tex.rgb(0.24, 0.225, 0.2)), (1, tex.rgb(0.33, 0.315, 0.29))])
    fines = tex.ramp(gids, [(0, tex.rgb(0.085, 0.07, 0.055)), (1, tex.rgb(0.2, 0.175, 0.14))])
    colour = lerp(fines, stone, smoothstep(0.3, 0.55, proud))
    colour = colour * (0.78 + 0.44 * fbm(n, seed + 2, beta=1.5, lo=10)[..., None])
    colour = lerp(colour, colour * tex.rgb(0.82, 0.72, 0.6), worn * 0.5)
    roughness = np.full((n, n), 0.9, dtype=F)
    return _finish('gravel', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=1.5)


# ---------------------------------------------------------------------------------------------
# Walls and roofs
# ---------------------------------------------------------------------------------------------

def siding(n=1024, seed=71):
    """Painted lap siding, eight courses to a 1.6 m tile. Near white, so a material's colour
    factor paints the house."""
    tile = 1.6
    courses = 8
    x, y = tex.grid(n)
    v = y * courses
    course = np.floor(v)
    f = v - course           # 0 at a course's top, 1 at its bottom edge
    # Each board leans out towards its bottom edge, then drops back to the next.
    profile = f * 0.010 - smoothstep(0.955, 1.0, f) * 0.010
    grain = fbm(n, seed, beta=1.4, lo=6, aniso=(0.025, 1.0))
    pores = saturate((grain - 0.5) * 2.5)
    wander = fbm(n, seed + 1, beta=2.4, lo=1, hi=10)
    height = profile + (pores - 0.3) * 0.00045 + (wander - 0.5) * 0.0006
    # Butt joints between boards of a course, staggered.
    r = tex.rng(seed + 2)
    joints = np.zeros((n, n), dtype=F)
    for c in range(courses):
        for _ in range(1):
            jx = r.random()
            d = np.minimum(np.abs(x - jx), 1 - np.abs(x - jx)) * tile
            joints = np.maximum(joints, (1.0 - smoothstep(0.0008, 0.0022, d)) * (course == c))
    height = height - joints * 0.003
    per_board = r.random(courses).astype(F)[course.astype(np.int32) % courses]
    chalk = fbm(n, seed + 3, beta=2.2, lo=2)
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.78, 0.78, 0.77)
    colour = colour * (0.95 + 0.05 * per_board[..., None]) * (0.94 + 0.08 * chalk[..., None])
    colour = colour * (0.97 + 0.04 * grain[..., None])
    # Grime gathers under each lap and runs down from it.
    under = smoothstep(0.90, 1.0, f) + (1.0 - smoothstep(0.0, 0.10, f)) * 0.6
    run = fbm(n, seed + 4, beta=1.8, lo=3, aniso=(1.0, 0.05))
    grime = saturate(under * 0.55 + smoothstep(0.62, 0.9, run) * 0.22 * (1 - f * 0.5))
    colour = lerp(colour, colour * tex.rgb(0.52, 0.50, 0.46), grime * 0.55)
    colour = lerp(colour, colour * 0.4, joints * 0.8)
    roughness = 0.62 + chalk * 0.12 + grime * 0.12
    cavity = saturate(1.0 - (smoothstep(0.93, 1.0, f) * 0.5 + (1.0 - smoothstep(0.0, 0.06, f)) * 0.55))
    return _finish('siding', colour, height, roughness, tile, cavity=cavity)


def brick(n=1024, seed=81):
    """Red clay brick in running bond, 5 by 16 bricks to a 1.2 m tile."""
    tile = 1.2
    columns, rows = 5, 16
    height01, ids, mortar = tex.brick_pattern(n, columns, rows, mortar=0.16, bevel=0.07, seed=seed, jitter=0.05)
    face = fbm(n, seed + 1, beta=1.6, lo=8)
    drag = fbm(n, seed + 2, beta=1.4, lo=10, aniso=(0.06, 1.0))
    pits = tex.speckle(n, seed + 3, n * n / 900, 1.3, 0.5)
    sand = tex.normalize01(blur(tex.white(n, seed + 4), 0.8))
    height = (height01 * 0.004 + (face - 0.5) * 0.0012 * height01 + (drag - 0.5) * 0.0006 * height01
              - pits * 0.0012 * height01 + (sand - 0.5) * 0.0008 * mortar)
    clay = tex.ramp(ids, [(0.0, tex.rgb(0.20, 0.065, 0.045)), (0.35, tex.rgb(0.30, 0.10, 0.065)),
                          (0.65, tex.rgb(0.36, 0.135, 0.085)), (0.86, tex.rgb(0.27, 0.105, 0.08)),
                          (0.94, tex.rgb(0.13, 0.07, 0.06)), (1.0, tex.rgb(0.42, 0.20, 0.13))])
    clay = clay * (0.82 + 0.36 * face[..., None]) * (0.92 + 0.16 * drag[..., None])
    clay = lerp(clay, clay * 0.55, pits[..., None] * 0.8)
    grout = tex.ramp(sand, [(0, tex.rgb(0.30, 0.29, 0.27)), (1, tex.rgb(0.50, 0.48, 0.44))])
    colour = lerp(clay, grout, mortar)
    # Lime bloom and soot, in broad drifts.
    bloom = smoothstep(0.6, 0.9, fbm(n, seed + 5, beta=2.6, lo=1, hi=6))
    colour = lerp(colour, tex.rgb(0.55, 0.52, 0.48), bloom * 0.18 * (1 - mortar))
    soot = smoothstep(0.55, 0.9, fbm(n, seed + 6, beta=2.4, lo=1, hi=5))
    colour = lerp(colour, colour * 0.6, soot * 0.3)
    roughness = lerp(0.84 + (face - 0.5) * 0.1, np.full((n, n), 0.95, dtype=F), mortar)
    return _finish('brick', colour, height, roughness, tile, cavity_radius=5.0, cavity_strength=1.3)


def shingles(n=1024, seed=91):
    """Three-tab asphalt roof shingles: 12 courses of 6 tabs to a 1.8 m tile. Mid grey-brown, so
    a material's colour factor can make it charcoal, brown or green."""
    tile = 1.8
    courses, tabs = 12, 6
    x, y = tex.grid(n)
    v = y * courses
    course = np.floor(v)
    f = v - course                      # 0 at the top of the exposed part, 1 at its bottom edge
    u = x * tabs + (course % 2) * 0.5
    tab = np.floor(u)
    fu = u - tab
    r = tex.rng(seed)
    table = r.random((courses, tabs)).astype(F)
    ids = table[course.astype(np.int32) % courses, tab.astype(np.int32) % tabs]
    slot_w = 0.012 / (tile / tabs)
    slot = (1.0 - smoothstep(slot_w * 0.5, slot_w * 0.5 + 0.006, np.minimum(fu, 1 - fu))) * smoothstep(0.02, 0.06, f)
    lift = (ids - 0.5) * 0.0012
    # Each course lies over the one below: thickest at its bottom edge.
    profile = f * 0.0035 + lift - smoothstep(0.965, 1.0, f) * 0.0035
    granule = tex.white(n, seed + 1)
    granule_b = tex.normalize01(blur(tex.white(n, seed + 2), 1.0))
    height = profile - slot * 0.003 + (granule_b - 0.5) * 0.0011
    base = tex.ramp(ids, [(0, tex.rgb(0.11, 0.10, 0.095)), (0.5, tex.rgb(0.16, 0.15, 0.14)),
                          (1, tex.rgb(0.22, 0.205, 0.19))])
    speck = tex.ramp(granule, [(0, tex.rgb(0.45)), (0.5, tex.rgb(1.0)), (0.93, tex.rgb(1.25)), (1, tex.rgb(2.2))])
    colour = base * speck * (0.8 + 0.4 * granule_b[..., None])
    weather = fbm(n, seed + 3, beta=2.4, lo=1, hi=8)
    streak = fbm(n, seed + 4, beta=2.0, lo=2, aniso=(1.0, 0.06))
    colour = colour * (0.82 + 0.3 * weather[..., None])
    colour = lerp(colour, colour * tex.rgb(0.6, 0.62, 0.55), smoothstep(0.6, 0.9, streak) * 0.3)
    shadow = smoothstep(0.95, 1.0, f) * 0.6 + (1.0 - smoothstep(0.0, 0.05, f)) * 0.7
    colour = lerp(colour, colour * 0.25, saturate(slot * 0.9))
    roughness = np.full((n, n), 0.93, dtype=F)
    cavity = saturate(1.0 - shadow * 0.6 - slot * 0.5)
    return _finish('shingles', colour, height, roughness, tile, cavity=cavity)


def plaster(n=1024, seed=101):
    """A painted interior wall: roller stipple on plasterboard. Near white, for tinting."""
    tile = 2.0
    stipple = tex.band(n, seed, 230, 90)
    broad = fbm(n, seed + 1, beta=2.6, lo=1, hi=6)
    scuff = smoothstep(0.7, 0.92, fbm(n, seed + 2, beta=2.2, lo=2, hi=16))
    height = (stipple - 0.5) * 0.00035 + (broad - 0.5) * 0.0008
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.80, 0.795, 0.78)
    colour = colour * (0.95 + 0.07 * broad[..., None]) * (0.985 + 0.03 * stipple[..., None])
    colour = lerp(colour, colour * tex.rgb(0.7, 0.68, 0.64), scuff * 0.35)
    roughness = 0.78 + scuff * 0.1 + (stipple - 0.5) * 0.06
    return _finish('plaster', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=0.5)


def stucco(n=1024, seed=111):
    """Sand-finished exterior render. Near white, for tinting."""
    tile = 1.5
    lumps = tex.band(n, seed, 90, 40)
    fine = tex.band(n, seed + 1, 300, 110)
    broad = fbm(n, seed + 2, beta=2.5, lo=1, hi=8)
    height = (lumps - 0.5) * 0.0028 + (fine - 0.5) * 0.0009 + (broad - 0.5) * 0.002
    streak = fbm(n, seed + 3, beta=2.0, lo=2, aniso=(1.0, 0.05))
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.74, 0.73, 0.70)
    colour = colour * (0.9 + 0.14 * broad[..., None]) * (0.93 + 0.14 * lumps[..., None])
    colour = lerp(colour, colour * tex.rgb(0.6, 0.57, 0.52), smoothstep(0.6, 0.92, streak) * 0.35)
    roughness = np.full((n, n), 0.9, dtype=F)
    return _finish('stucco', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=1.2)


# ---------------------------------------------------------------------------------------------
# Wood
# ---------------------------------------------------------------------------------------------

def fence_wood(n=1024, seed=121):
    """Weathered cedar fence boards, eight upright boards to a 1.2 m tile."""
    tile = 1.2
    h01, ids, gap, along = tex.plank_pattern(n, 8, gap=0.035, seed=seed, vertical=True, bevel=0.05)
    grain, pores = tex.wood_grain(n, seed + 1, rings=56, vertical=True, knots=7)
    fibre = fbm(n, seed + 2, beta=1.2, lo=12, aniso=(1.0, 0.02))
    checks = smoothstep(0.78, 0.95, fbm(n, seed + 3, beta=1.6, lo=6, aniso=(1.0, 0.012)))
    height = h01 * 0.008 + (grain - 0.5) * 0.0011 * h01 + (fibre - 0.5) * 0.0007 - checks * 0.0018 * h01
    silver = tex.ramp(grain, [(0, tex.rgb(0.17, 0.155, 0.135)), (0.5, tex.rgb(0.27, 0.25, 0.22)),
                              (1, tex.rgb(0.36, 0.335, 0.30))])
    warm = tex.ramp(grain, [(0, tex.rgb(0.16, 0.09, 0.05)), (0.5, tex.rgb(0.28, 0.17, 0.095)),
                            (1, tex.rgb(0.38, 0.25, 0.15))])
    weathering = smoothstep(0.3, 0.75, fbm(n, seed + 4, beta=2.3, lo=1, hi=8) * 0.6 + ids * 0.4)
    colour = lerp(warm, silver, weathering)
    colour = colour * (0.82 + 0.3 * ids[..., None]) * (0.9 + 0.2 * fibre[..., None])
    # Damp, green-black at the foot of the boards; the tile's bottom is the ground end.
    damp = smoothstep(0.82, 1.0, along + (fbm(n, seed + 5, beta=2, lo=3) - 0.5) * 0.15)
    colour = lerp(colour, tex.rgb(0.05, 0.055, 0.035), damp * 0.5)
    colour = lerp(colour, colour * 0.3, checks * 0.7)
    colour = lerp(colour, tex.rgb(0.015, 0.012, 0.01), gap)
    roughness = 0.86 + checks * 0.08
    cavity = saturate(tex.cavity_from_height(height, 5.0, 1.2) * (1 - gap * 0.8))
    return _finish('fence_wood', colour, height, roughness, tile, cavity=cavity)


def painted_wood(n=1024, seed=131):
    """Painted timber trim: brush marks over grain, a little peeling. Near white, for tinting."""
    tile = 1.0
    grain, pores = tex.wood_grain(n, seed, rings=30, vertical=False, knots=1)
    brush = tex.band(n, seed + 1, 190, 70, aniso=(0.04, 1.0))
    broad = fbm(n, seed + 2, beta=2.5, lo=1, hi=6)
    peel_mask = smoothstep(0.80, 0.86, fbm(n, seed + 3, beta=2.1, lo=3, hi=40))
    height = (brush - 0.5) * 0.0003 + (grain - 0.5) * 0.00025 - peel_mask * 0.0005
    paint = np.ones((n, n, 3), dtype=F) * tex.rgb(0.80, 0.80, 0.785)
    paint = paint * (0.95 + 0.06 * broad[..., None]) * (0.98 + 0.03 * brush[..., None])
    bare = tex.ramp(grain, [(0, tex.rgb(0.20, 0.17, 0.14)), (1, tex.rgb(0.36, 0.32, 0.27))])
    colour = lerp(paint, bare, peel_mask)
    grime = smoothstep(0.6, 0.9, fbm(n, seed + 4, beta=2.2, lo=2))
    colour = lerp(colour, colour * tex.rgb(0.62, 0.6, 0.55), grime * 0.3)
    roughness = lerp(0.45 + brush * 0.1 + grime * 0.2, np.full((n, n), 0.85, dtype=F), peel_mask)
    return _finish('painted_wood', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=0.6)


def plywood(n=1024, seed=141):
    """Sheathing plywood, as boards up a window: pale rotary-cut veneer with wild grain."""
    tile = 1.2
    wander = fbm(n, seed, beta=3.0, lo=1, hi=5, aniso=(0.12, 1.0))
    x, y = tex.grid(n)
    rings = 0.5 + 0.5 * np.sin((y * 4.0 + (wander - 0.5) * 9.0) * math.tau)
    rings = rings ** 1.5
    fibre = fbm(n, seed + 1, beta=1.2, lo=10, aniso=(0.02, 1.0))
    patches = smoothstep(0.75, 0.8, fbm(n, seed + 2, beta=2.4, lo=2, hi=9))
    height = (rings - 0.5) * 0.0004 + (fibre - 0.5) * 0.0005
    colour = tex.ramp(rings, [(0, tex.rgb(0.42, 0.30, 0.17)), (0.6, tex.rgb(0.55, 0.42, 0.26)),
                              (1, tex.rgb(0.34, 0.22, 0.12))])
    colour = colour * (0.88 + 0.22 * fibre[..., None])
    colour = lerp(colour, colour * tex.rgb(0.8, 0.72, 0.6), patches * 0.4)
    water = smoothstep(0.55, 0.9, fbm(n, seed + 3, beta=2.6, lo=1, hi=5))
    colour = lerp(colour, colour * tex.rgb(0.6, 0.56, 0.5), water * 0.4)
    roughness = 0.72 + (fibre - 0.5) * 0.1 + water * 0.1
    return _finish('plywood', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=0.6)


def floor_wood(n=1024, seed=151):
    """An oak strip floor with a worn satin finish: ten boards across a 1.0 m tile."""
    tile = 1.0
    h01, ids, gap, along = tex.plank_pattern(n, 10, gap=0.02, seed=seed, vertical=False, length_cells=2, bevel=0.03)
    grain, pores = tex.wood_grain(n, seed + 1, rings=70, vertical=False, knots=2)
    fibre = fbm(n, seed + 2, beta=1.3, lo=14, aniso=(0.02, 1.0))
    height = h01 * 0.0012 + (grain - 0.5) * 0.00012 - pores * 0.00015
    colour = tex.ramp(grain, [(0, tex.rgb(0.20, 0.105, 0.045)), (0.5, tex.rgb(0.33, 0.19, 0.085)),
                              (1, tex.rgb(0.43, 0.27, 0.13))])
    colour = colour * (0.78 + 0.4 * ids[..., None]) * (0.92 + 0.16 * fibre[..., None])
    colour = lerp(colour, tex.rgb(0.03, 0.02, 0.012), gap * 0.9)
    wear = smoothstep(0.45, 0.8, fbm(n, seed + 3, beta=2.4, lo=1, hi=7))
    scuffs = tex.scratches(n, seed + 4, 260, length=(0.02, 0.2), width=0.8)
    roughness = 0.32 + wear * 0.28 + scuffs * 0.25 + gap * 0.4
    return _finish('floor_wood', colour, height, roughness, tile, cavity_radius=3.0, cavity_strength=0.8)


# ---------------------------------------------------------------------------------------------
# Metal, glass, plastic
# ---------------------------------------------------------------------------------------------

def painted_metal(n=1024, seed=161):
    """Factory-painted sheet metal with wear: orange peel, fine scratches, chips to bare steel
    with a rim of rust. Near white, for tinting."""
    tile = 1.0
    peel = tex.band(n, seed, 170, 70)
    broad = fbm(n, seed + 1, beta=2.6, lo=1, hi=6)
    scratch = tex.scratches(n, seed + 2, 420, length=(0.01, 0.16), width=0.7)
    chip_field = fbm(n, seed + 3, beta=1.9, lo=3, hi=60)
    chips = smoothstep(0.80, 0.83, chip_field)
    rim = smoothstep(0.74, 0.80, chip_field) * (1 - chips)
    dust = smoothstep(0.45, 0.85, fbm(n, seed + 4, beta=2.3, lo=1, hi=10))
    height = (peel - 0.5) * 0.00012 - chips * 0.00025 - scratch * 0.00008 + (broad - 0.5) * 0.0003
    paint = np.ones((n, n, 3), dtype=F) * tex.rgb(0.78, 0.78, 0.78)
    paint = paint * (0.96 + 0.05 * broad[..., None])
    paint = lerp(paint, paint * tex.rgb(0.72, 0.69, 0.64), dust * 0.32)
    paint = lerp(paint, paint * 1.12, scratch * 0.3)
    steel = np.ones((n, n, 3), dtype=F) * tex.rgb(0.42, 0.40, 0.38)
    rust = tex.ramp(fbm(n, seed + 5, beta=1.6, lo=6), [(0, tex.rgb(0.10, 0.035, 0.012)), (1, tex.rgb(0.30, 0.11, 0.03))])
    colour = lerp(paint, rust, rim * 0.85)
    colour = lerp(colour, lerp(steel, rust, 0.35), chips)
    metallic = chips * 0.75
    roughness = lerp(0.36 + dust * 0.28 + scratch * 0.2 + (peel - 0.5) * 0.06,
                     np.full((n, n), 0.6, dtype=F), saturate(chips + rim))
    return _finish('painted_metal', colour, height, roughness, tile, metallic=metallic,
                   cavity_radius=3.0, cavity_strength=0.5)


def corrugated(n=1024, seed=171):
    """Galvanised corrugated sheet: 13 waves to a 1.0 m tile, with spangle and rust blooms."""
    tile = 1.0
    waves = 13
    x, y = tex.grid(n)
    wave = 0.5 + 0.5 * np.cos(x * waves * math.tau)
    f1, f2, ids = tex.worley(n, 26, seed)
    spangle = ids * 0.6 + (1 - saturate(f1)) * 0.4
    streak = fbm(n, seed + 1, beta=2.0, lo=2, aniso=(1.0, 0.04))
    rust_mask = smoothstep(0.66, 0.8, fbm(n, seed + 2, beta=2.1, lo=2, hi=30) + (1 - wave) * 0.06)
    dents = fbm(n, seed + 3, beta=2.8, lo=1, hi=5)
    height = wave * 0.016 + (dents - 0.5) * 0.004 + rust_mask * 0.0004
    zinc = tex.ramp(spangle, [(0, tex.rgb(0.42, 0.44, 0.45)), (0.5, tex.rgb(0.56, 0.58, 0.59)),
                              (1, tex.rgb(0.70, 0.72, 0.73))])
    zinc = lerp(zinc, zinc * tex.rgb(0.7, 0.68, 0.63), smoothstep(0.55, 0.9, streak)[..., None] * 0.5)
    rust = tex.ramp(fbm(n, seed + 4, beta=1.5, lo=8), [(0, tex.rgb(0.09, 0.03, 0.012)), (0.6, tex.rgb(0.24, 0.085, 0.025)),
                                                       (1, tex.rgb(0.36, 0.15, 0.05))])
    colour = lerp(zinc, rust, rust_mask)
    metallic = 1.0 - rust_mask * 0.85
    roughness = lerp(0.38 + spangle * 0.14 + smoothstep(0.55, 0.9, streak) * 0.2,
                     np.full((n, n), 0.92, dtype=F), rust_mask)
    cavity = saturate(0.55 + 0.45 * wave)
    return _finish('corrugated', colour, height, roughness, tile, metallic=metallic, cavity=cavity)


def rusty_metal(n=1024, seed=181):
    """Steel left to the weather: flaking mill scale and deep orange rust."""
    tile = 1.0
    coarse = fbm(n, seed, beta=2.0, lo=2)
    flake = fbm(n, seed + 1, beta=1.5, lo=8)
    scale = smoothstep(0.52, 0.6, fbm(n, seed + 2, beta=2.0, lo=3, hi=50))
    pits = tex.speckle(n, seed + 3, n * n / 500, 1.5, 0.4)
    height = (coarse - 0.5) * 0.0015 + (flake - 0.5) * 0.0009 + scale * 0.0008 - pits * 0.001
    rust = tex.ramp(flake * 0.6 + coarse * 0.4, [(0, tex.rgb(0.05, 0.02, 0.012)), (0.35, tex.rgb(0.15, 0.05, 0.018)),
                                                 (0.65, tex.rgb(0.28, 0.105, 0.03)), (1, tex.rgb(0.42, 0.19, 0.06))])
    steel = tex.ramp(flake, [(0, tex.rgb(0.07, 0.07, 0.075)), (1, tex.rgb(0.16, 0.16, 0.165))])
    colour = lerp(rust, steel, scale * 0.85)
    metallic = scale * 0.8
    roughness = lerp(np.full((n, n), 0.93, dtype=F), 0.55 + flake * 0.15, scale)
    return _finish('rusty_metal', colour, height, roughness, tile, metallic=metallic,
                   cavity_radius=3.0, cavity_strength=1.2)


def dark_steel(n=1024, seed=191):
    """Blued or parkerised steel, as on tools and gun parts: near black, finely brushed."""
    tile = 0.5
    brushed = fbm(n, seed, beta=0.8, lo=20, aniso=(0.012, 1.0))
    broad = fbm(n, seed + 1, beta=2.5, lo=1, hi=8)
    scratch = tex.scratches(n, seed + 2, 220, length=(0.02, 0.25), width=0.6)
    height = (brushed - 0.5) * 0.00005 - scratch * 0.00004
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.045, 0.047, 0.052)
    colour = colour * (0.8 + 0.4 * broad[..., None]) * (0.9 + 0.2 * brushed[..., None])
    colour = lerp(colour, tex.rgb(0.33, 0.33, 0.34), scratch * 0.6)
    roughness = 0.46 + (brushed - 0.5) * 0.14 + broad * 0.1 - scratch * 0.15
    metallic = np.full((n, n), 1.0, dtype=F)
    return _finish('dark_steel', colour, height, roughness, tile, metallic=metallic,
                   cavity_radius=2.0, cavity_strength=0.3)


def bare_metal(n=1024, seed=201):
    """Bright worn aluminium or steel: brushed, scratched, a little stained."""
    tile = 0.5
    brushed = fbm(n, seed, beta=0.8, lo=20, aniso=(0.012, 1.0))
    broad = fbm(n, seed + 1, beta=2.5, lo=1, hi=8)
    scratch = tex.scratches(n, seed + 2, 300, length=(0.02, 0.3), width=0.6)
    stain = smoothstep(0.6, 0.9, fbm(n, seed + 3, beta=2.3, lo=2, hi=20))
    height = (brushed - 0.5) * 0.00006 - scratch * 0.00005
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.60, 0.61, 0.62)
    colour = colour * (0.9 + 0.2 * broad[..., None]) * (0.93 + 0.14 * brushed[..., None])
    colour = lerp(colour, colour * tex.rgb(0.55, 0.5, 0.45), stain * 0.5)
    roughness = 0.34 + (brushed - 0.5) * 0.16 + stain * 0.25 - scratch * 0.1
    metallic = np.full((n, n), 1.0, dtype=F)
    return _finish('bare_metal', colour, height, roughness, tile, metallic=metallic,
                   cavity_radius=2.0, cavity_strength=0.3)


def glass(n=512, seed=211):
    """Window glass seen from outside by day: a dark mirror with dust and smears."""
    tile = 1.0
    smear = fbm(n, seed, beta=2.6, lo=1, hi=8, aniso=(0.3, 1.0))
    dust = smoothstep(0.5, 0.9, fbm(n, seed + 1, beta=2.2, lo=2))
    rain = smoothstep(0.7, 0.95, fbm(n, seed + 2, beta=1.8, lo=3, aniso=(1.0, 0.03)))
    height = (smear - 0.5) * 0.00002
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.20, 0.24, 0.27)
    colour = lerp(colour, tex.rgb(0.30, 0.29, 0.27), saturate(dust * 0.35 + rain * 0.3))
    roughness = 0.035 + smear * 0.05 + dust * 0.22 + rain * 0.25
    metallic = 1.0 - saturate(dust * 0.4 + rain * 0.35)
    return _finish('glass', colour, height, roughness, tile, metallic=metallic, cavity_radius=2.0,
                   cavity_strength=0.0)


def plastic(n=512, seed=221):
    """Moulded plastic with a fine pebbled grain. Near white, for tinting."""
    tile = 0.4
    grain = tex.band(n, seed, 120, 45)
    broad = fbm(n, seed + 1, beta=2.5, lo=1, hi=6)
    scuff = tex.scratches(n, seed + 2, 120, length=(0.02, 0.2), width=0.7)
    height = (grain - 0.5) * 0.00012
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.74, 0.74, 0.74)
    colour = colour * (0.94 + 0.08 * broad[..., None])
    colour = lerp(colour, colour * 1.1, scuff * 0.3)
    roughness = 0.5 + (grain - 0.5) * 0.12 + broad * 0.12 + scuff * 0.15
    return _finish('plastic', colour, height, roughness, tile, cavity_radius=2.0, cavity_strength=0.3)


def rubber(n=512, seed=231):
    """Black rubber: tyres, mats, grips."""
    tile = 0.3
    grain = tex.band(n, seed, 150, 60)
    broad = fbm(n, seed + 1, beta=2.3, lo=1, hi=8)
    dust = smoothstep(0.5, 0.9, fbm(n, seed + 2, beta=2.0, lo=2))
    height = (grain - 0.5) * 0.00018
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.022, 0.022, 0.023)
    colour = colour * (0.8 + 0.4 * broad[..., None])
    colour = lerp(colour, tex.rgb(0.12, 0.105, 0.085), dust * 0.4)
    roughness = 0.82 + dust * 0.12 + (grain - 0.5) * 0.08
    return _finish('rubber', colour, height, roughness, tile, cavity_radius=2.0, cavity_strength=0.4)


def chainlink(n=1024, seed=241):
    """Chain-link fence mesh as a cut-out: galvanised wire, eight diamonds to a 0.48 m tile."""
    tile = 0.48
    diamonds = 8
    x, y = tex.grid(n)
    a = (x + y) * diamonds
    b = (x - y) * diamonds
    da = np.abs(a - np.round(a))        # distance to the nearest wire of each family, in periods
    db = np.abs(b - np.round(b))
    # One period measured across the wires is tile / diamonds / sqrt(2).
    period = tile / diamonds / math.sqrt(2.0)
    radius = 0.0018 / period
    wire_a = saturate(1.0 - (da / radius) ** 2)
    wire_b = saturate(1.0 - (db / radius) ** 2)
    # Where they cross, the wires twist round each other, taking turns on top.
    over = ((np.floor(a) + np.floor(b)) % 2) < 1
    ha = np.sqrt(wire_a) * np.where(over, 1.0, 0.7)
    hb = np.sqrt(wire_b) * np.where(over, 0.7, 1.0)
    height01 = np.maximum(ha, hb)
    alpha = (np.maximum(wire_a, wire_b) > 0.0).astype(F)
    alpha = saturate(blur(alpha, 0.6) * 1.6)
    tarnish = fbm(n, seed, beta=2.0, lo=2)
    rust = smoothstep(0.7, 0.86, fbm(n, seed + 1, beta=2.0, lo=3, hi=40))
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.50, 0.52, 0.53)
    colour = colour * (0.75 + 0.4 * tarnish[..., None])
    colour = lerp(colour, tex.rgb(0.22, 0.08, 0.03), rust * 0.8)
    metallic = 1.0 - rust * 0.8
    roughness = 0.42 + tarnish * 0.15 + rust * 0.4
    return _finish('chainlink', colour, height01 * 0.0018, roughness, tile, metallic=metallic,
                   alpha=alpha, cavity=np.ones((n, n), dtype=F))


# ---------------------------------------------------------------------------------------------
# Cloth
# ---------------------------------------------------------------------------------------------

def canvas(n=1024, seed=251):
    """Heavy cotton duck: truck tilts, tents, tarpaulins. Near white, for tinting."""
    tile = 0.3
    h = tex.weave(n, 96, seed)
    broad = fbm(n, seed + 1, beta=2.4, lo=1, hi=8)
    stain = smoothstep(0.55, 0.9, fbm(n, seed + 2, beta=2.4, lo=1, hi=6))
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.72, 0.72, 0.70)
    colour = colour * (0.72 + 0.34 * h[..., None]) * (0.9 + 0.16 * broad[..., None])
    colour = lerp(colour, colour * tex.rgb(0.66, 0.62, 0.55), stain * 0.45)
    roughness = np.full((n, n), 0.93, dtype=F)
    return _finish('canvas', colour, h * 0.0005, roughness, tile, cavity_radius=1.5, cavity_strength=1.0)


def burlap(n=1024, seed=261):
    """Coarse jute sacking, as sandbags are made of."""
    tile = 0.25
    h = tex.weave(n, 34, seed)
    fuzz = fbm(n, seed + 1, beta=1.2, lo=20)
    broad = fbm(n, seed + 2, beta=2.4, lo=1, hi=6)
    colour = tex.ramp(h, [(0, tex.rgb(0.09, 0.07, 0.045)), (0.6, tex.rgb(0.30, 0.24, 0.15)),
                          (1, tex.rgb(0.44, 0.37, 0.25))])
    colour = colour * (0.8 + 0.3 * broad[..., None]) * (0.9 + 0.2 * fuzz[..., None])
    dirt_mask = smoothstep(0.5, 0.9, fbm(n, seed + 3, beta=2.3, lo=1, hi=8))
    colour = lerp(colour, colour * tex.rgb(0.6, 0.55, 0.48), dirt_mask * 0.5)
    roughness = np.full((n, n), 0.96, dtype=F)
    return _finish('burlap', colour, h * 0.0014 + (fuzz - 0.5) * 0.0003, roughness, tile,
                   cavity_radius=3.0, cavity_strength=1.5)


def carpet(n=1024, seed=271):
    """Cut-pile household carpet. Near white, for tinting."""
    tile = 1.0
    tufts = tex.band(n, seed, 280, 100)
    lay = fbm(n, seed + 1, beta=2.6, lo=1, hi=10)
    worn = smoothstep(0.55, 0.9, fbm(n, seed + 2, beta=2.4, lo=1, hi=5))
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.62, 0.60, 0.56)
    colour = colour * (0.72 + 0.4 * tufts[..., None]) * (0.86 + 0.24 * lay[..., None])
    colour = lerp(colour, colour * tex.rgb(0.6, 0.57, 0.52), worn * 0.4)
    roughness = np.full((n, n), 0.97, dtype=F)
    return _finish('carpet', colour, (tufts - 0.5) * 0.0025 + (lay - 0.5) * 0.002, roughness, tile,
                   cavity_radius=2.0, cavity_strength=1.4)


def fabric(n=1024, seed=281):
    """Upholstery and clothing cloth: a fine twill. Near white, for tinting."""
    tile = 0.2
    x, y = tex.grid(n)
    threads = 80
    twill = 0.5 + 0.5 * np.sin((x + y * 0.5) * threads * math.tau)
    cross = 0.5 + 0.5 * np.sin((x - y * 2.0) * threads * math.pi)
    h = saturate(twill * 0.7 + cross * 0.3)
    fuzz = fbm(n, seed, beta=1.3, lo=16)
    broad = fbm(n, seed + 1, beta=2.5, lo=1, hi=8)
    colour = np.ones((n, n, 3), dtype=F) * tex.rgb(0.70, 0.70, 0.70)
    colour = colour * (0.78 + 0.26 * h[..., None]) * (0.92 + 0.14 * fuzz[..., None]) * (0.92 + 0.12 * broad[..., None])
    roughness = np.full((n, n), 0.92, dtype=F)
    return _finish('fabric', colour, h * 0.00025, roughness, tile, cavity_radius=1.5, cavity_strength=0.8)


def ceramic_tile(n=1024, seed=291):
    """Glazed wall and floor tiles, six to a 0.9 m tile, with grey grout. Near white."""
    tile = 0.9
    h01, ids, grout = tex.brick_pattern(n, 6, 6, mortar=0.035, bevel=0.03, offset=0.0, seed=seed)
    broad = fbm(n, seed + 1, beta=2.6, lo=1, hi=6)
    grit = tex.normalize01(blur(tex.white(n, seed + 2), 0.8))
    height = h01 * 0.0016 + (grit - 0.5) * 0.0005 * grout
    glaze = np.ones((n, n, 3), dtype=F) * tex.rgb(0.80, 0.80, 0.78)
    glaze = glaze * (0.96 + 0.05 * ids[..., None]) * (0.97 + 0.04 * broad[..., None])
    grout_c = tex.ramp(grit, [(0, tex.rgb(0.16, 0.15, 0.14)), (1, tex.rgb(0.30, 0.29, 0.27))])
    colour = lerp(glaze, grout_c, grout)
    grime = smoothstep(0.5, 0.9, fbm(n, seed + 3, beta=2.3, lo=2))
    roughness = lerp(0.12 + grime * 0.3, np.full((n, n), 0.9, dtype=F), grout)
    return _finish('ceramic_tile', colour, height, roughness, tile, cavity_radius=3.0)


def car_paint(n=1024, seed=301):
    """A car's clear-coated paint after two years standing outdoors: glossy under a film of
    road dust, with water marks and the odd stone chip. Near white, for tinting."""
    tile = 1.5
    peel = tex.band(n, seed, 220, 90)
    broad = fbm(n, seed + 1, beta=2.7, lo=1, hi=5)
    film = smoothstep(0.3, 0.8, fbm(n, seed + 2, beta=2.4, lo=1, hi=12))
    spots = blur(tex.speckle(n, seed + 3, 260, 5.0, 0.6), 1.2)
    runs = tex.normalize01(blur(tex.white(n, seed + 4), 5.0)[:1, :]) * np.ones((n, 1), dtype=F)
    streak = tex.normalize01(runs + tex.normalize01(fbm(n, seed + 5, beta=2.2, lo=2, hi=30)) * 0.8)
    chip_field = fbm(n, seed + 6, beta=1.8, lo=6, hi=90)
    chips = smoothstep(0.93, 0.95, chip_field)
    scratch = tex.scratches(n, seed + 7, 120, length=(0.02, 0.2), width=0.6)
    dust = saturate(film * 0.75 + spots * 0.5 + smoothstep(0.55, 0.9, streak) * 0.25)
    height = (peel - 0.5) * 0.00006 - chips * 0.00018 - scratch * 0.00004
    paint = np.ones((n, n, 3), dtype=F) * tex.rgb(0.80, 0.80, 0.80)
    paint = paint * (0.97 + 0.04 * broad[..., None])
    paint = lerp(paint, paint * tex.rgb(0.80, 0.77, 0.72) + tex.rgb(0.02, 0.018, 0.014), dust * 0.4)
    paint = lerp(paint, paint * 1.1, scratch * 0.25)
    primer = np.ones((n, n, 3), dtype=F) * tex.rgb(0.36, 0.35, 0.34)
    colour = lerp(paint, primer, chips)
    roughness = saturate(0.16 + dust * 0.42 + scratch * 0.2 + (peel - 0.5) * 0.03 + chips * 0.4)
    return _finish('car_paint', colour, height, roughness, tile, metallic=chips * 0.5,
                   cavity_radius=2.0, cavity_strength=0.3)


def burnt_metal(n=1024, seed=311):
    """Sheet steel after a fire: the paint gone to black scale and pale ash, rust coming
    through everywhere the scale has flaked."""
    tile = 1.2
    coarse = tex.normalize01(fbm(n, seed, beta=2.2, lo=1, hi=8))
    mid = tex.normalize01(fbm(n, seed + 1, beta=1.8, lo=4, hi=40))
    fine = tex.normalize01(fbm(n, seed + 2, beta=1.3, lo=14))
    grain = tex.normalize01(blur(tex.white(n, seed + 7), 0.7))
    blister = tex.normalize01(tex.worley(n, 30, seed + 3)[0])
    # Rust takes most of the sheet, broken by the fine noise so that no edge is a clean line.
    rust_field = tex.normalize01(fbm(n, seed + 4, beta=2.0, lo=2, hi=24)) * 0.7 + fine * 0.3
    rust_mask = smoothstep(0.34, 0.6, rust_field)
    ash_field = coarse * 0.55 + mid * 0.3 + fine * 0.15
    ash = smoothstep(0.58, 0.8, ash_field) * (0.55 + 0.45 * grain)
    flake = smoothstep(0.6, 0.66, fine * 0.6 + mid * 0.4) * (1 - ash)
    height = ((coarse - 0.5) * 0.0012 + (fine - 0.5) * 0.0008 + flake * 0.0007
              - smoothstep(0.0, 0.22, blister) * 0.0005 + (grain - 0.5) * 0.0002)
    char = tex.ramp(fine * 0.6 + grain * 0.4, [(0, tex.rgb(0.010, 0.009, 0.009)), (1, tex.rgb(0.06, 0.052, 0.048))])
    rust = tex.ramp(mid * 0.5 + fine * 0.3 + grain * 0.2,
                    [(0, tex.rgb(0.045, 0.02, 0.012)), (0.45, tex.rgb(0.13, 0.055, 0.022)),
                     (0.8, tex.rgb(0.23, 0.10, 0.04)), (1, tex.rgb(0.30, 0.15, 0.065))])
    ash_c = tex.ramp(grain * 0.5 + fine * 0.5, [(0, tex.rgb(0.20, 0.19, 0.18)), (1, tex.rgb(0.50, 0.48, 0.45))])
    colour = lerp(char, rust, rust_mask * 0.92)
    colour = lerp(colour, ash_c, ash * 0.7)
    roughness = saturate(0.84 + (fine - 0.5) * 0.18 + ash * 0.08)
    metallic = saturate(flake * 0.45 * (1 - rust_mask))
    return _finish('burnt_metal', colour, height, roughness, tile, metallic=metallic,
                   cavity_radius=3.0, cavity_strength=1.3)


ALL = [asphalt, concrete, sidewalk, dirt, lawn, gravel, siding, brick, shingles, plaster, stucco,
       fence_wood, painted_wood, plywood, floor_wood, painted_metal, corrugated, rusty_metal,
       dark_steel, bare_metal, glass, plastic, rubber, chainlink, canvas, burlap, carpet, fabric,
       ceramic_tile, car_paint, burnt_metal]


def by_name(name):
    for make in ALL:
        if make.__name__ == name:
            return make
    raise KeyError(f'no material named {name}')
