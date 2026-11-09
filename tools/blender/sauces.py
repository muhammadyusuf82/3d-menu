"""Liquids, sauces, creams and dustings."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import kit as K
from lib import bake, disc_mesh, planar_uv, set_origin_bottom, smooth, uv_unwrap


# ================================================================== liquids in vessels

def fill(vessel, level, name, mat, z0=None, inset=0.0005, meniscus=0.0012, dome=0.0):
    """The liquid (or layer) inside a vessel between z0 (default: its floor) and `level`, as a closed solid.
    Planar UVs, so a texture on the top shows as seen from above (latte art, crema). dome > 0 bulges the top (foam)."""
    z0 = vessel.floor + 0.0003 if z0 is None else z0
    pts = [(0.0, z0)]
    zs = sorted({z0, level, *[z for _, z in vessel.inner if z0 < z < level]})
    for z in zs:
        pts.append((max(0.001, vessel.r_at(z) - inset), z))
    r_top = max(0.001, vessel.r_at(level) - inset)
    if meniscus:
        pts.append((r_top, level + meniscus * 0.6))
        pts.append((r_top - meniscus * 1.5, level))
    for k in range(1, 7) if dome else ():
        s = k / 6
        pts.append((r_top * (1 - s), level + dome * math.sin(s * math.pi / 2)))
    if not dome:
        pts.append((0.0, level))
    obj = K.revolve(name, pts, segments=96, uv='planar')
    K.assign(obj, mat)
    smooth(obj, 50)
    return obj


def liquid_mat(name, color, rough=0.05, spec=0.5):
    return K.solid(name, color, rough=rough, spec=spec)


# ================================================================== piped cream, scoops

def piped_swirl(name, radius=0.03, height=0.035, turns=2.6, tube=0.0085, points=8, mat=None, z0=0.0):
    """Star-tip piped whipped cream: a ridged tube on a conical helix ending in a peak."""
    n = 140
    pts, rad = [], []
    for i in range(n):
        s = i / (n - 1)
        r = radius * (1 - s) ** 0.9
        a = s * turns * math.tau
        pts.append((r * math.cos(a), r * math.sin(a), z0 + tube * 0.8 + height * s ** 1.1))
        rad.append(tube * (1 - 0.65 * s ** 2.5) + 0.0006)
    obj = K.sweep(name, pts, rad, sides=40, profile=lambda q: 1.0 + 0.18 * math.cos(q * points))
    if mat is None:
        mat = cream_mat(name + '_mat')
    K.assign(obj, mat)
    smooth(obj, 80)
    set_origin_bottom(obj)
    return obj


def cream_mat(name, color=(0.97, 0.95, 0.90), rough=0.42):
    s = K.Shader(name, spec=0.45)
    n = s.noise(260, 4, 0.6)
    col = s.mix(color, (0.88, 0.84, 0.76), s.math('MULTIPLY', n, 0.35))
    return s.out(col, rough=rough, height=n, strength=0.15, distance=0.0003)


def scoop(name, radius=0.026, color=(0.96, 0.90, 0.72), seed=0, chunks=None):
    """An ice-cream scoop: round top, ragged scooped 'skirt' ring at the base, creamy micro-texture (baked)."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=72, v_segments=40, radius=radius)
    ph = rng.random(4) * math.tau
    for v in bm.verts:
        z = v.co.z / radius
        a = math.atan2(v.co.y, v.co.x)
        if z < -0.25:                      # flattened bottom
            v.co.z = -0.25 * radius - (z + 0.25) * radius * 0.08
        skirt = math.exp(-((z + 0.12) / 0.12) ** 2)
        ragged = 1 + skirt * (0.10 + 0.05 * math.sin(a * 7 + ph[0]) + 0.04 * math.sin(a * 13 + ph[1]))
        v.co.x *= ragged
        v.co.y *= ragged
    obj = K.new_object(name, bm) if hasattr(K, 'new_object') else None
    from lib import new_object
    obj = obj or new_object(name, bm)
    K.displace(obj, radius * 0.05, radius * 0.25, depth=3)
    s = K.Shader(name + '_mat', spec=0.45)
    n = s.noise(90, 6, 0.65)
    pits = s.voronoi(160, out='Distance')
    col = s.mix(color, tuple(c * 0.86 for c in color), s.math('MULTIPLY', n, 0.6))
    if chunks:
        spots = s.math('LESS_THAN', s.voronoi(55, out='Distance'), 0.13)
        col = s.mix(col, chunks, spots)
    height = s.math('ADD', n, s.math('MULTIPLY', pits, 0.6))
    mat = s.out(col, rough=0.38, height=height, strength=0.55, distance=0.0008)
    K.assign(obj, mat)
    smooth(obj, 80)
    uv_unwrap(obj)
    bake(obj, res=1024)
    set_origin_bottom(obj)
    return obj


# ================================================================== sauces on food

def drizzle(name, targets, path_xy, radius=0.0022, lift=0.4, mat=None, wobble=0.15, seed=0, sides=10):
    """A sauce line poured along path_xy [(x, y), ...] that rests on the food below (ray-cast)."""
    rng = np.random.default_rng(seed)
    pts, rad = [], []
    for i, (x, y) in enumerate(path_xy):
        hit = K.ray_down(targets, x, y)
        if not hit:
            continue
        loc = hit[0]
        r = radius * (1 + wobble * math.sin(i * 0.7 + rng.random()))
        pts.append((loc.x, loc.y, loc.z + r * lift))
        rad.append(r)
    if len(pts) < 2:
        raise RuntimeError(f'drizzle {name}: path misses the targets')
    # smooth heights a little so the line doesn't jitter over crumbs
    z = np.array([p[2] for p in pts])
    zs = np.convolve(np.pad(z, 2, mode='edge'), np.ones(5) / 5, mode='valid')
    pts = [(p[0], p[1], max(zz, p[2] - radius * 0.3)) for p, zz in zip(pts, zs)]
    rad[0] *= 0.5
    rad[-1] *= 0.5
    obj = K.sweep(name, pts, rad, sides=sides)
    if mat is not None:
        K.assign(obj, mat)
    smooth(obj, 70)
    set_origin_bottom(obj)
    return obj


def zigzag(x0, x1, y_amp, n_zig, steps=200, y0=0.0, axis='x', jitter=0.0, seed=0):
    rng = np.random.default_rng(seed)
    pts = []
    for i in range(steps):
        s = i / (steps - 1)
        a = x0 + (x1 - x0) * s
        b = y0 + y_amp * math.sin(s * n_zig * math.pi) + jitter * (rng.random() - 0.5)
        pts.append((a, b) if axis == 'x' else (b, a))
    return pts


def spiral(r_max, turns, steps=240, cx=0.0, cy=0.0):
    return [(cx + r_max * (i / steps) * math.cos(i / steps * turns * math.tau),
             cy + r_max * (i / steps) * math.sin(i / steps * turns * math.tau)) for i in range(1, steps)]


def pool(name, radius, height=0.003, mat=None, seed=0, lobes=0.12, center=(0, 0)):
    """An irregular sauce puddle (pepper sauce, wine reduction, molten chocolate)."""
    rng = np.random.default_rng(seed)
    ph = rng.random(4) * math.tau
    edge = lambda t: 1 + lobes * (0.6 * math.sin(3 * t + ph[0]) + 0.3 * math.sin(7 * t + ph[1]) + 0.2 * math.sin(11 * t + ph[2]))
    obj = disc_mesh(name, radius, height, cuts=18, radius_fn=edge, bevel=0.6, smooth_level=1)
    for v in obj.data.vertices:            # meniscus: thicker in the middle, thin edge
        r = math.hypot(v.co.x, v.co.y) / radius
        if v.co.z > 0:
            v.co.z *= 0.5 + 0.5 * max(0.0, 1 - r * r)
    planar_uv(obj)
    if mat is not None:
        K.assign(obj, mat)
    smooth(obj, 80)
    set_origin_bottom(obj)
    obj.location = (center[0], center[1], 0)
    K.apply_transform(obj)
    return obj


def dollop(name, radius=0.018, height=0.016, mat=None, points=0, twist=1.2, seed=0):
    """A spooned dollop (sour cream, yogurt) or, with points > 0, a piped rosette."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
    ph = rng.random(3) * math.tau
    for v in bm.verts:
        z = max(-0.2, v.co.z)
        a = math.atan2(v.co.y, v.co.x)
        k = (1 + 0.08 * math.sin(3 * a + ph[0]) + 0.05 * math.sin(5 * a + ph[1]))
        if points:
            k *= 1 + 0.12 * math.cos(points * (a + twist * (z + 0.2)))
        peak = math.exp(-(math.hypot(v.co.x, v.co.y) / 0.25) ** 2) * 0.25 * (z > 0.5)
        v.co.x *= radius * k
        v.co.y *= radius * k
        v.co.z = (z + 0.2) / 1.2 * height + peak * height
    from lib import new_object
    obj = new_object(name, bm)
    if mat is not None:
        K.assign(obj, mat)
    smooth(obj, 80)
    set_origin_bottom(obj)
    return obj


def dust(name, targets, region, count, color=(0.25, 0.12, 0.06), size=0.0009, seed=0, rough=0.9):
    """Cocoa / powdered sugar / spice dusting: many tiny flakes resting on the surface."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=size, segments=5)
    tpl = K.template(bm)
    obj = K.scatter(name, targets, tpl, count, region, rng, scale=(0.5, 1.6), embed=-0.2, tilt=0.3, align=1.0,
                    colors=lambda r: tuple(c * (0.75 + 0.5 * r.random()) for c in color), min_up=0.05)
    K.solidify(obj, size * 0.4, offset=0)
    K.assign(obj, K.solid(name + '_mat', (1, 1, 1), rough=rough, spec=0.3, vcol=True))
    set_origin_bottom(obj)
    return obj
