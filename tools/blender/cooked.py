"""Cooked food pieces shared by fast food, kids and steak dishes: fries, breaded pieces, sausages, buns, wraps,
meat chunks and small toppings."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import kit as K
from lib import bake, new_object, set_origin_bottom, smooth, uv_unwrap


# ================================================================== fries

def fries_texture(res=1024, seed=0):
    """Rows = 32 bands (one picked per fry for variety), columns = along the fry (browner at the cut ends)."""
    u = np.linspace(0, 1, res, dtype=np.float32)[None, :] * np.ones((res, 1), np.float32)
    n = K.fbm(res, 24, seed, 4)
    streak = K.vnoise(res, 6, seed + 1, aspect=12)              # long streaks along the fry
    band_tone = K.vnoise(res, 1, seed + 2, aspect=32)          # per-fry overall browning
    ends = np.clip(1 - np.minimum(u, 1 - u) / 0.1, 0, 1) ** 2
    brown = np.clip(0.25 * n + 0.3 * streak + 0.45 * band_tone + 0.55 * ends - 0.25, 0, 1)
    col = K.lerp_color((0.98, 0.80, 0.38), (0.78, 0.47, 0.14), brown)
    spots = (K.vnoise(res, 70, seed + 3) > 0.84) * 0.35
    col = col * (1 - spots[..., None] * 0.5)
    rough = (0.55 - 0.2 * n).astype(np.float32)                 # oily sheen in places
    height = n * 0.5 + streak * 0.5 + K.vnoise(res, 200, seed + 4) * 0.3
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal(height.astype(np.float32), 1.2)


def fry(name, length, thick=0.0095, rng=None):
    rng = rng or np.random.default_rng()
    t = thick * (0.85 + 0.3 * rng.random())
    obj = K.rounded_box(name, (t, t * (0.85 + 0.2 * rng.random()), length), bevel=0.22, segments=2)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > length * 0.5],
                              cuts=8)
    bend = (rng.random() - 0.5) * 0.25
    for v in bm.verts:
        s = v.co.z / length
        v.co.x += bend * length * (s * s - 0.25)         # gentle curve
    uv = bm.loops.layers.uv.new('UVMap')
    band = rng.integers(0, 32)
    for f in bm.faces:
        for lp in f.loops:
            co = lp.vert.co
            ang = math.atan2(co.y, co.x) / math.tau + 0.5
            lp[uv].uv = (co.z / length + 0.5, (band + ang * 0.9) / 32)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def fries_pile(name, container_objs, count, region, z_from, rng, length=(0.05, 0.085), thick=0.0095, frames=150,
               extra_passive=(), catcher_z=0.0):
    """Drops individual fries into a container with rigid bodies, then joins them (natural, messy pile)."""
    pieces = []
    for i in range(count):
        f = fry(f'{name}_{i}', rng.uniform(*length), thick, rng)
        x, y = region(rng)
        f.rotation_euler = (rng.uniform(0.6, 2.5), rng.uniform(-0.4, 0.4), rng.random() * math.tau)
        f.location = (x, y, z_from + i * (thick * 1.25))   # never spawn overlapping (Bullet would blast them apart)
        K.apply_transform(f)
        pieces.append(f)
    floor = min(K.bounds(o)[0][2] for o in container_objs)
    # thin crockery lets Bullet tunnel pieces through: a temporary thick slab under the food surface catches them
    xs = [region(np.random.default_rng(k)) for k in range(50)]
    span = max(max(abs(p[0]), abs(p[1])) for p in xs) * 2 + 0.06
    catcher = K.rounded_box('catcher', (span, span, 0.03), bevel=0.0, segments=1)
    K.transform(catcher, loc=(0, 0, catcher_z - 0.015))
    K.settle(pieces, list(container_objs) + list(extra_passive) + [catcher], frames=frames, friction=0.9, damping=0.6)
    K.remove(catcher)
    # Bullet occasionally tunnels a piece through thin crockery or flicks it off the edge: drop those
    xs = [region(np.random.default_rng(k)) for k in range(200)]
    rx = max(abs(p[0]) for p in xs) + 0.03
    ry = max(abs(p[1]) for p in xs) + 0.03
    kept = []
    for f in pieces:
        lo, hi = K.bounds(f)
        c = (lo + hi) / 2
        if lo[2] < floor - 0.002 or abs(c[0]) > rx or abs(c[1]) > ry:
            K.remove(f)
        else:
            kept.append(f)
    print(f'fries_pile {name}: kept {len(kept)}/{len(pieces)}')
    obj = K.join(kept, name)
    color, rough, normal = fries_texture(seed=int(rng.integers(0, 99)))
    K.assign(obj, K.textured(name + '_mat', color, rough, normal, spec=0.45))
    smooth(obj, 40)
    return obj


# ================================================================== breaded / fried

def breaded_mat(name, light=(0.60, 0.26, 0.04), dark=(0.26, 0.08, 0.015), scale=1.0):
    s = K.Shader(name, spec=0.45)
    n = s.noise(60 * scale, 6, 0.6)
    crumbs = s.voronoi(320 * scale, out='Distance')
    fine = s.noise(700 * scale, 3, 0.6)
    col = s.ramp(n, [(0.3, dark), (0.55, light), (0.75, tuple(min(1, c * 1.15) for c in light))])
    col = s.mix(col, dark, s.math('MULTIPLY', s.maprange(crumbs, 0.25, 0.0, 0, 1), 0.35))
    rough = s.maprange(n, 0.3, 0.7, 0.42, 0.66)
    height = s.math('ADD', s.math('MULTIPLY', crumbs, -1.0), s.math('MULTIPLY', fine, 0.4))
    return s.out(col, rough=rough, height=height, strength=0.8, distance=0.0012)


def breaded_piece(name, size=(0.09, 0.028, 0.017), seed=0, crag=0.18, mat=None, res=1024):
    """A hand-breaded strip / nugget: lumpy body with craggy crust (geometry) and crumb detail (baked normal)."""
    rng = np.random.default_rng(seed)
    obj = K.blob(name, 1.0, scale=(size[0] / 2, size[1] / 2, size[2] / 2), lumps=0, subdiv=4)
    for v in obj.data.vertices:                       # flatten the underside a little, taper one end
        if v.co.z < 0:
            v.co.z *= 0.75
        v.co.y *= 1 - 0.18 * max(0.0, v.co.x / (size[0] / 2))
    obj.location = (rng.random() * 5, rng.random() * 5, 0)
    K.apply_transform(obj)
    K.displace(obj, min(size) * crag, min(size) * 0.25, depth=3)
    K.displace(obj, min(size) * crag * 0.35, min(size) * 0.08, depth=2)
    lo, hi = K.bounds(obj)
    obj.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])
    K.apply_transform(obj)
    K.assign(obj, mat or breaded_mat(name + '_mat'))
    smooth(obj, 60)
    uv_unwrap(obj)
    bake(obj, res=res)
    set_origin_bottom(obj)
    return obj


# ================================================================== sausages

def sausage(name, length=0.17, radius=0.0135, style='grilled', seed=0):
    """Capsule with a slight bend; 'grilled' has diagonal char marks, 'smoked' is darker and wrinkled."""
    pts = [(length * (s - 0.5), 0.004 * math.sin(s * math.pi + seed), 0.0) for s in np.linspace(0, 1, 40)]
    rad = [radius * (math.sin(min(1, s * 9) * math.pi / 2) * math.sin(min(1, (1 - s) * 9) * math.pi / 2)) ** 0.35 + 1e-4
           for s in np.linspace(0, 1, 40)]
    obj = K.sweep(name, pts, rad, sides=28)
    s = K.Shader(name + '_mat', spec=0.5)
    n = s.noise(40, 5, 0.6)
    wrinkle = s.noise(300, 2, 0.5)
    base_light, base_dark = ((0.50, 0.16, 0.05), (0.22, 0.05, 0.015)) if style == 'grilled' else ((0.36, 0.09, 0.03), (0.15, 0.035, 0.01))
    col = s.ramp(n, [(0.3, base_dark), (0.7, base_light)])
    marks = s.wave(9 / length * 0.17, distortion=1.5, detail=1, bands='DIAGONAL')
    char = s.maprange(marks, 0.08, 0.0, 0, 1)
    col = s.mix(col, (0.05, 0.015, 0.005), s.math('MULTIPLY', char, 0.85))
    rough = s.maprange(char, 0, 1, 0.24, 0.6)
    s.out(col, rough=rough, height=s.math('ADD', wrinkle, s.math('MULTIPLY', char, 0.6)), strength=0.35, distance=0.0006)
    K.assign(obj, s.mat)
    smooth(obj, 80)
    uv_unwrap(obj)
    bake(obj, res=1024)
    set_origin_bottom(obj)
    return obj


# ================================================================== bread

def _crumb(name, toast=0.0):
    s = K.Shader(name, spec=0.3)
    pores = s.voronoi(260, out='Distance')
    n = s.noise(30, 5, 0.6)
    col = s.ramp(n, [(0.3, (0.80 - 0.3 * toast, 0.62 - 0.35 * toast, 0.36 - 0.25 * toast)),
                     (0.7, (0.93 - 0.2 * toast, 0.80 - 0.3 * toast, 0.55 - 0.3 * toast))])
    col = s.mix(col, (0.55, 0.42, 0.28), s.maprange(pores, 0.12, 0.0, 0, 0.5), 'MULTIPLY')
    return s.out(col, rough=0.85, height=pores, strength=0.7, distance=0.0012)


def _crust(name, top=(0.50, 0.20, 0.04), side=(0.86, 0.60, 0.30)):
    s = K.Shader(name, spec=0.45)
    n = s.noise(25, 5, 0.6)
    up = s.maprange(s.up(), 0.1, 0.9, 0, 1)
    col = s.mix(side, top, s.math('ADD', s.math('MULTIPLY', up, 0.85), s.math('MULTIPLY', n, 0.3)))
    fine = s.noise(500, 3, 0.5)
    return s.out(col, rough=s.maprange(up, 0, 1, 0.6, 0.38), height=fine, strength=0.15, distance=0.0004)


def hotdog_bun(name='bun', length=0.165, width=0.06, height=0.046, open_angle=0.32, seed=0):
    """Split-top milk bun: two half-loaves hinged at the bottom, crumb faces showing, golden top crust."""
    halves = []
    for side in (1, -1):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
        for v in bm.verts:
            x, y, z = v.co
            # squashed capsule: flat-ish ends, flat bottom, domed top
            v.co.x = math.copysign(abs(x) ** 0.55, x) * length / 2
            v.co.y = y * width / 2
            v.co.z = (z * 0.5 + 0.5) ** 0.85 * height if z > -0.6 else (z * 0.5 + 0.5) * height * 0.9
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0), plane_no=(0, side, 0), clear_inner=True)
        filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
        tri = bmesh.ops.triangulate(bm, faces=filled['faces'])
        for f in tri['faces']:
            f.material_index = 1
        obj = new_object(f'{name}_{side}', bm)
        K.assign(obj, _crust(f'{name}_crust'))
        obj.data.materials.append(_crumb(f'{name}_crumb'))
        K.subdivide(obj, 1)
        K.displace(obj, 0.0012, 0.01)
        # hinge open around the bottom edge
        obj.rotation_euler.x = -side * open_angle
        K.apply_transform(obj)
        obj.location.y = side * 0.004
        K.apply_transform(obj)
        halves.append(obj)
    bun = K.join(halves, name)
    smooth(bun, 45)
    uv_unwrap(bun)
    bake(bun, res=1024)
    set_origin_bottom(bun)
    return bun


def flatbread_texture(res=1024, seed=0, toast=1.0):
    n = K.fbm(res, 12, seed, 4)
    spots = K.smoothstep(0.66, 0.82, K.fbm(res, 22, seed + 1, 3)) * toast
    bubbles = K.smoothstep(0.80, 0.92, K.vnoise(res, 45, seed + 2)) * toast
    col = K.lerp_color((0.95, 0.88, 0.70), (0.89, 0.77, 0.56), n)
    col = col * (1 - spots[..., None] * 0.35) + np.array([0.72, 0.48, 0.22]) * spots[..., None] * 0.35
    col = col * (1 - bubbles[..., None] * 0.55) + np.array([0.50, 0.28, 0.10]) * bubbles[..., None] * 0.55
    rough = np.full((res, res), 0.75, np.float32)
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal((n * 0.4 + bubbles * 0.6).astype(np.float32), 0.8)


def wrap_half(name, length=0.125, r_out=0.034, r_in=0.025, turns=1.35, cut_slant=0.45, seed=0):
    """Half of a rolled flatbread wrap: a spiral sheet around the Y axis, cut on a slant at y = 0 (open end).
    Returns (wrap, inner_radius)."""
    nu, nv = 90, 30
    verts, faces, uvs = [], [], []
    for i in range(nu + 1):
        s = i / nu
        th = s * turns * math.tau
        r = r_in + (r_out - r_in) * s
        for j in range(nv + 1):
            y = length * j / nv
            verts.append((r * math.cos(th), y, r * math.sin(th) + r_out))
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            q = (a, a + 1, a + nv + 2, a + nv + 1)
            faces.append(q)
            uvs += [(ii / nu * turns * 0.7, jj / nv * 0.7) for ii, jj in ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))]
    obj = K.mesh_from_arrays(name, verts, faces, uvs)
    K.solidify(obj, 0.0022, offset=0)
    # slanted cut at the open end, then flatten the bottom a little where it rests on the board
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0.012, r_out),
                           plane_no=(0, -1, cut_slant), clear_outer=True)
    for v in bm.verts:
        if v.co.z < 0.004:
            v.co.z = 0.004 - (0.004 - v.co.z) * 0.3
    bm.to_mesh(obj.data)
    bm.free()
    K.subdivide(obj, 1)
    color, rough, normal = flatbread_texture(seed=seed)
    K.assign(obj, K.textured(name + '_mat', color, rough, normal, spec=0.3))
    obj['r_out'], obj['r_in'] = r_out, r_in
    smooth(obj, 50)
    return obj


# ================================================================== meat chunks & toppings

def meat_mat(name, light, dark, gloss=0.3, char=0.5):
    s = K.Shader(name, spec=0.45)
    n = s.noise(45, 6, 0.65)
    fibre = s.noise(220, 3, 0.5)
    col = s.ramp(n, [(0.25, dark), (0.7, light)])
    seared = s.maprange(s.up(), 0.2, 1.0, 0, char)
    col = s.mix(col, tuple(c * 0.45 for c in dark), seared)
    return s.out(col, rough=s.maprange(n, 0.3, 0.7, gloss, gloss + 0.3), height=s.math('ADD', n, s.math('MULTIPLY', fibre, 0.5)),
                 strength=0.5, distance=0.0008)


def chunks(name, count, size, region_fn, rng, mat, squash=(1.3, 1.0, 0.7), z=0.0, lumps=0.35):
    """Irregular meat chunks (chicken, lamb, beef strips) laid out by region_fn(i, rng) -> (x, y, z, rot_z)."""
    pieces = []
    for i in range(count):
        s = size * (0.75 + 0.5 * rng.random())
        p = K.blob(f'{name}_{i}', s / 2, scale=squash, lumps=lumps, lump_size=0.8, subdiv=3, seed=i + int(rng.integers(0, 50)))
        x, y, zz, rz = region_fn(i, rng)
        K.transform(p, loc=(x, y, z + zz), rot=(rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rz))
        pieces.append(p)
    obj = K.join(pieces, name)
    K.assign(obj, mat)
    smooth(obj, 60)
    uv_unwrap(obj)
    bake(obj, res=1024)
    return obj


def crumbles(name, targets, region, count, color, size=0.006, rough=0.35, seed=0, squash=(1, 0.8, 0.6)):
    """Small irregular bits (bacon bits, chili mince, crispy onion) scattered on food, vertex-coloured."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size / 2)
    for v in bm.verts:
        v.co.x *= squash[0] * (0.8 + 0.4 * rng.random())
        v.co.y *= squash[1] * (0.8 + 0.4 * rng.random())
        v.co.z *= squash[2] * (0.8 + 0.4 * rng.random())
    tpl = K.template(bm)
    obj = K.scatter(name, targets, tpl, count, region, rng, scale=(0.7, 1.3), embed=0.35, tilt=1.2,
                    colors=lambda r: tuple(c * (0.7 + 0.5 * r.random()) for c in color))
    K.assign(obj, K.solid(name + '_mat', (1, 1, 1), rough=rough, vcol=True))
    smooth(obj, 80)
    set_origin_bottom(obj)
    return obj


def ring_tpl(r=0.0028, tube=0.0007, flat=0.6):
    pts = [(r * math.cos(a), r * math.sin(a), 0.0) for a in np.linspace(0, math.tau, 17)]
    obj = K.sweep('ring_tpl', pts, tube, sides=6, caps=False)
    for v in obj.data.vertices:
        v.co.z *= flat
    tpl = K.template(obj)
    K.remove(obj)
    return tpl
