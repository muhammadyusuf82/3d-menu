"""Fruit, vegetables and herbs used across many dishes. Builders return objects at the origin (bottom at z = 0)."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import kit as K
from lib import activate, bake, disc_mesh, new_object, planar_uv, set_origin_bottom, smooth, uv_unwrap

# ================================================================== citrus slices

def citrus_texture(res=1024, rind=(0.96, 0.80, 0.12), pulp=(0.98, 0.86, 0.30), pith=(0.97, 0.95, 0.82),
                   segments=10, seed=1):
    x, y, r, t = K.grid(res)
    col = np.zeros((res, res, 3), np.float32)
    rough = np.full((res, res), 0.25, np.float32)
    seg = (t + math.pi) / math.tau * segments
    frac = seg - np.floor(seg)
    edge = np.minimum(frac, 1 - frac) * (math.tau / segments) * np.maximum(r, 1e-3)   # distance to membrane
    vesicles = K.vnoise(res, 90, seed) * 0.5 + K.vnoise(res, 220, seed + 1) * 0.5
    streak = 0.5 + 0.5 * np.sin(r * 160 + vesicles * 6) * np.sin(t * 50)
    p = np.asarray(pulp, np.float32) * (0.82 + 0.25 * vesicles[..., None]) * (0.92 + 0.12 * streak[..., None])
    col[:] = p
    membrane = (edge < 0.012) & (r < 0.84)
    col[membrane] = np.asarray(pith) * 0.98
    rough[membrane] = 0.45
    core = r < 0.07
    col[core] = np.asarray(pith)
    pith_ring = (r >= 0.83) & (r < 0.92)
    col[pith_ring] = np.asarray(pith) * (0.95 + 0.05 * vesicles[pith_ring][..., None])
    rough[pith_ring] = 0.6
    rind_ring = r >= 0.92
    pores = K.vnoise(res, 300, seed + 3)
    col[rind_ring] = np.asarray(rind) * (0.85 + 0.2 * pores[rind_ring][..., None])
    rough[rind_ring] = 0.42
    height = np.where(r < 0.84, vesicles * 0.6 - membrane * 0.8, 0.2) + np.where(rind_ring, pores * 0.3, 0)
    return np.clip(col, 0, 1), rough, K.height_to_normal(height.astype(np.float32), 0.5)


def citrus_slice(name='lemon', radius=0.026, thickness=0.0042, kind='lemon', notch=False, seed=1):
    colors = {'lemon': ((0.95, 0.80, 0.10), (0.98, 0.88, 0.34), (0.97, 0.95, 0.82)),
              'lime': ((0.30, 0.55, 0.12), (0.72, 0.86, 0.36), (0.90, 0.95, 0.80)),
              'orange': ((0.96, 0.52, 0.06), (0.98, 0.62, 0.18), (0.98, 0.92, 0.78))}[kind]
    obj = disc_mesh(name, radius, thickness, cuts=24, bevel=0.35, radius_fn=lambda a: 1 + 0.012 * math.sin(a * 5 + seed))
    if notch:   # a cut from the edge to the centre so it can hang on a glass rim
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for f in bm.faces:
            c = f.calc_center_median()
            if c.x > 0 and abs(c.y) < 0.0012:
                f.select = True
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.select], context='FACES')
        bm.to_mesh(obj.data)
        bm.free()
    planar_uv(obj)
    color, rough, normal = citrus_texture(rind=colors[0], pulp=colors[1], pith=colors[2], seed=seed)
    K.assign(obj, K.textured(f'{name}_mat', color, rough, normal, spec=0.5))
    smooth(obj, 50)
    set_origin_bottom(obj)
    return obj


# ================================================================== wedges (peach, tomato, apple...)

def wedge(name, radius=0.03, angle=0.75, squash=(1, 1, 0.95), skin=None, flesh=None, seed=0, res=1024):
    """A wedge cut from a round fruit: outer skin and two flat flesh faces, baked into one texture set.
    The wedge lies on one cut face (bottom at z = 0)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=40, radius=radius)
    bmesh.ops.scale(bm, vec=squash, verts=bm.verts)
    for a, keep in ((angle / 2, 'inner'), (-angle / 2, 'outer')):
        n = Vector((-math.sin(a), math.cos(a), 0))
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0), plane_no=n, clear_outer=(keep == 'inner'),
                               clear_inner=(keep == 'outer'))
    filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    tri = bmesh.ops.triangulate(bm, faces=filled['faces'])
    for f in tri['faces']:
        f.material_index = 1
    obj = new_object(name, bm)
    K.assign(obj, skin)
    obj.data.materials.append(flesh)
    smooth(obj, 40)
    uv_unwrap(obj)
    bake(obj, res=res)
    # lay it on a cut face
    obj.rotation_euler = (math.pi / 2, -angle / 2, 0)
    K.apply_transform(obj)
    set_origin_bottom(obj)
    return obj


def peach_materials():
    s = K.Shader('peach_skin', spec=0.35)
    blush = s.noise(28, 4, 0.5)
    fine = s.noise(400, 2, 0.5)
    col = s.ramp(blush, [(0.35, (0.55, 0.06, 0.02)), (0.55, (0.80, 0.22, 0.04)), (0.75, (0.92, 0.55, 0.08))])
    skin = s.out(col, rough=0.62, height=fine, strength=0.15, distance=0.0003)
    f = K.Shader('peach_flesh', spec=0.5)
    radial = f.maprange(f.length(), 0.004, 0.03, 0, 1)
    fib = f.noise(180, 3, 0.6)
    col = f.ramp(radial, [(0.0, (0.55, 0.12, 0.03)), (0.22, (0.86, 0.42, 0.06)), (0.8, (0.95, 0.62, 0.12)),
                          (0.97, (0.86, 0.40, 0.06))])
    col = f.mix(col, (1.0, 0.85, 0.5), f.math('MULTIPLY', fib, 0.18), 'MULTIPLY')
    flesh = f.out(col, rough=0.22, height=fib, strength=0.12, distance=0.0002)
    return skin, flesh


# ================================================================== berries

def strawberry(name='strawberry', height=0.034, radius=0.0145, half=False, seed=0, calyx=True):
    rng = np.random.default_rng(seed)
    lobes = rng.random(3) * math.tau
    prof = []
    for i in range(40):
        s = i / 39                      # 0 tip .. 1 shoulder
        z = height * s
        r = radius * (math.sin(s * math.pi * 0.62) ** 0.9) * (1 - 0.35 * max(0, s - 0.85) / 0.15)
        prof.append((max(r, 0.0), z))
    prof[0] = (0.0, 0.0)
    prof.append((radius * 0.35, height * 1.0))
    prof.append((0.0, height * 0.98))
    obj = K.revolve(name, prof, segments=48, uv='wrap')
    for v in obj.data.vertices:
        a = math.atan2(v.co.y, v.co.x)
        k = 1 + 0.05 * math.sin(3 * a + lobes[0]) + 0.03 * math.sin(5 * a + lobes[1])
        v.co.x *= k
        v.co.y *= k
    tilt = (rng.random() - 0.5) * 0.15
    s = K.Shader(f'{name}_mat', spec=0.6)
    zpos = s.position('Z')
    zf = s.maprange(zpos, 0, height, 0, 1)
    dimple = s.voronoi(900 * 0.034 / height, out='Distance')
    col = s.ramp(zf, [(0.0, (0.42, 0.02, 0.02)), (0.65, (0.62, 0.03, 0.03)), (0.86, (0.72, 0.18, 0.08)),
                      (0.97, (0.85, 0.75, 0.45))])
    col = s.mix(col, (0.55, 0.45, 0.4), s.maprange(dimple, 0.05, 0.0, 0, 0.6), 'MULTIPLY')
    mat = s.out(col, rough=s.maprange(dimple, 0, 0.3, 0.38, 0.18), height=dimple, strength=0.45, distance=0.0006)
    K.assign(obj, mat)
    smooth(obj, 80)
    uv_unwrap(obj)
    bake(obj, res=512)
    # seeds (achenes) on a spiral, sitting in their dimples
    tpl = K.ellipsoid_tpl(0.0007, 0.00045, 0.0004, 6, 4)
    mats = []
    golden = math.pi * (3 - math.sqrt(5))
    n = 70
    for i in range(n):
        zz = 0.08 + 0.82 * (i + 0.5) / n
        rr = np.interp(zz * height, [p[1] for p in prof[:-2]], [p[0] for p in prof[:-2]])
        a = i * golden
        loc = Vector((rr * math.cos(a), rr * math.sin(a), zz * height))
        nrm = Vector((math.cos(a), math.sin(a), 0.25)).normalized()
        mats.append(K.frame(loc - nrm * 0.0001, nrm, rng.random(), (1, 1, 1)))
    seeds = K.instances(f'{name}_seeds', tpl, mats)
    K.assign(seeds, K.solid(f'{name}_seed', (0.85, 0.66, 0.20), rough=0.4))
    parts = [obj, seeds]
    if calyx:
        parts.append(_calyx(f'{name}_calyx', radius * 0.95, height, rng))
    berry = K.join(parts, name)
    if half:
        _halve(berry, height)
    berry.rotation_euler = (math.pi, tilt, 0) if not half else (0, 0, 0)
    K.apply_transform(berry)
    set_origin_bottom(berry)
    return berry


def _calyx(name, radius, top, rng):
    leaves = []
    count = 8
    for i in range(count):
        a = i / count * math.tau + rng.random() * 0.3
        length = radius * (1.0 + rng.random() * 0.35)
        pts = []
        for s in np.linspace(0, 1, 8):
            rr = 0.002 + length * s
            pts.append((rr * math.cos(a), rr * math.sin(a), top + 0.0012 - 0.004 * s * s))
        w = [0.0018 * math.sin(max(0.08, s) * math.pi) ** 0.6 + 0.0002 for s in np.linspace(0, 1, 8)]
        leaf = K.sweep(f'{name}_{i}', pts, w, sides=6, profile=lambda q: 1.0 if abs(math.sin(q)) > 0.5 else 0.25)
        leaves.append(leaf)
    stem = K.sweep(f'{name}_stem', [(0, 0, top), (0.0005, 0, top + 0.004), (0.0015, 0.0005, top + 0.008)], 0.0011, sides=8)
    leaves.append(stem)
    c = K.join(leaves, name)
    K.assign(c, K.solid(f'{name}_green', (0.10, 0.28, 0.05), rough=0.55))
    return c


def _halve(obj, height):
    """Cuts a berry lengthwise and gives the cut face the pale-centre strawberry interior."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, 1, 0),
                           clear_outer=True)
    filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    tri = bmesh.ops.triangulate(bm, faces=filled['faces'])
    idx = len(obj.data.materials)
    for f in tri['faces']:
        f.material_index = idx
    bm.to_mesh(obj.data)
    bm.free()
    res = 512
    x, y, r, t = K.grid(res)
    # cut face uses planar x/z projection: x across, y = height
    core = np.exp(-((x / 0.32) ** 2)) * np.clip((y + 1) / 2, 0, 1) ** 0.5
    rays = 0.5 + 0.5 * np.sin(np.arctan2(y + 1.2, x) * 40) * 0.3
    col = K.lerp_color((0.80, 0.08, 0.08), (0.98, 0.80, 0.78), np.clip(core * 1.2 + rays * 0.1, 0, 1))
    mat = K.textured(f'{obj.name}_cut', col.astype(np.float32), None, base_rough=0.2, spec=0.6)
    obj.data.materials.append(mat)
    me = obj.data
    uv = me.uv_layers.active
    lo, hi = K.bounds(obj)
    for p in me.polygons:
        if p.material_index == idx:
            for li in p.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                uv.data[li].uv = ((co.x - lo[0]) / (hi[0] - lo[0]), (co.z - lo[2]) / (hi[2] - lo[2]))
    obj.rotation_euler = (math.pi / 2, 0, 0)   # cut face up
    K.apply_transform(obj)


def raspberry(name='raspberry', radius=0.0095, height=0.019, seed=0):
    rng = np.random.default_rng(seed)
    tpl = K.ellipsoid_tpl(1, 1, 1, 8, 5)
    mats, cols = [], []
    rows = 9
    for i in range(rows):
        s = (i + 0.5) / rows
        z = height * s
        rr = radius * math.sin(0.25 + s * (math.pi - 0.9)) ** 0.8
        n = max(5, int(rr / radius * 11))
        for k in range(n):
            a = k / n * math.tau + i * 0.4
            nrm = Vector((math.cos(a), math.sin(a), 0.35 - s * 0.7)).normalized()
            d = 0.0032 * (0.85 + 0.3 * rng.random())
            mats.append(K.frame((rr * math.cos(a), rr * math.sin(a), z), nrm, 0, (d, d, d * 0.9)))
            c = 0.85 + 0.25 * rng.random()
            cols.append((0.55 * c, 0.02 * c, 0.10 * c))
    obj = K.instances(name, tpl, mats, cols)
    mat = K.solid(f'{name}_mat', (1, 1, 1), rough=0.28, spec=0.6, vcol=True)
    K.assign(obj, mat)
    obj.rotation_euler = (math.pi, 0, rng.random() * math.tau)  # open end down, like they're served
    K.apply_transform(obj)
    set_origin_bottom(obj)
    return obj


def cherry(name='cherry', radius=0.012, color=(0.62, 0.0, 0.03), seed=0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=24, radius=radius)
    for v in bm.verts:
        r_xy = math.hypot(v.co.x, v.co.y) / radius
        if v.co.z > 0:
            v.co.z -= radius * 0.22 * math.exp(-(r_xy / 0.35) ** 2)   # dimple at the stem
        v.co.z *= 0.93
    obj = new_object(name, bm)
    K.assign(obj, K.solid(f'{name}_mat', color, rough=0.12, spec=0.7, coat=0.6))
    smooth(obj, 80)
    top = max(v.co.z for v in obj.data.vertices)
    pts = [(0.0, 0.0, top - 0.002)] + [(0.004 * s * s, 0.0, top - 0.002 + 0.03 * s) for s in np.linspace(0.05, 1, 16)]
    stem = K.sweep(f'{name}_stem', pts, [0.0009] * len(pts), sides=6)
    K.assign(stem, K.solid(f'{name}_stem_mat', (0.32, 0.25, 0.08), rough=0.6))
    obj = K.join([obj, stem], name)
    set_origin_bottom(obj)
    return obj


# ================================================================== leaves and herbs

def leaf_texture(res=256, base=(0.16, 0.42, 0.10), vein=(0.42, 0.62, 0.24), seed=0, veins=7):
    """u along the leaf (0 stem .. 1 tip), v across (0 .. 1, midrib at 0.5)."""
    u = np.linspace(0, 1, res, dtype=np.float32)[None, :] * np.ones((res, 1), np.float32)
    v = np.linspace(1, 0, res, dtype=np.float32)[:, None] * np.ones((1, res), np.float32)
    n = K.fbm(res, 8, seed, 3)
    col = np.asarray(base, np.float32) * (0.85 + 0.3 * n[..., None])
    mid = np.abs(v - 0.5)
    rib = np.clip(1 - mid / 0.025, 0, 1)
    side = np.abs(((u * veins + mid * 2.2) % 1.0) - 0.5)
    lat = np.clip(1 - side / 0.06, 0, 1) * (mid < 0.48)
    vmask = np.maximum(rib, lat * 0.7)
    col = col * (1 - vmask[..., None] * 0.6) + np.asarray(vein, np.float32) * vmask[..., None] * 0.6
    height = -vmask + 0.3 * n
    rough = (0.5 + 0.2 * n).astype(np.float32)
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal(height.astype(np.float32), 1.2)


def leaf_mesh(name, length, width, serration=0.0, teeth=12, fold=0.25, curl=0.15, shape='ovate', nu=16, nv=8,
              lobes=0, thick=True):
    """A single leaf on +X from the origin, as a thin double-sided sheet with UVs (u along, v across)."""
    verts, faces, uvs = [], [], []
    for i in range(nu + 1):
        s = i / nu
        if shape == 'ovate':
            half = width / 2 * math.sin(math.pi * s ** 0.75) ** 0.9
        elif shape == 'lance':
            half = width / 2 * math.sin(math.pi * s) ** 1.3
        else:   # 'round' (cilantro / parsley lobes)
            half = width / 2 * math.sin(math.pi * s ** 0.6) ** 0.6
        if serration:
            half *= 1 - serration * (0.5 + 0.5 * math.sin(s * teeth * math.tau))
        if lobes:
            half *= 0.75 + 0.25 * abs(math.cos(s * lobes * math.pi))
        for j in range(nv + 1):
            w = j / nv - 0.5
            y = w * 2 * half
            z = abs(w) * width * fold + curl * length * s * s
            verts.append((s * length, y, z))
            uvs.append((s, j / nv))
    loop_uvs = []
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            q = (a, a + nv + 1, a + nv + 2, a + 1)
            faces.append(q)
            loop_uvs += [uvs[k] for k in q]
    obj = K.mesh_from_arrays(name, verts, faces, loop_uvs)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=1e-7)
    bpy.ops.object.mode_set(mode='OBJECT')
    if thick:
        K.solidify(obj, 0.00025, offset=0)
    return obj


def sprig(name, kind='mint', size=1.0, seed=0, leaf_mat=None):
    """Herb sprig lying roughly flat (stem along +X). kind: mint, basil, parsley, cilantro, rosemary, thyme."""
    rng = np.random.default_rng(seed)
    parts = []
    spec = {
        'mint': dict(pairs=3, length=0.026, width=0.017, serr=0.08, shape='ovate', stem=0.05, color=(0.14, 0.40, 0.09)),
        'basil': dict(pairs=2, length=0.04, width=0.024, serr=0.0, shape='ovate', stem=0.05, color=(0.10, 0.36, 0.06)),
        'parsley': dict(pairs=3, length=0.016, width=0.014, serr=0.12, shape='round', stem=0.055, color=(0.10, 0.34, 0.06)),
        'cilantro': dict(pairs=3, length=0.013, width=0.014, serr=0.1, shape='round', stem=0.05, color=(0.17, 0.44, 0.10)),
        'rosemary': dict(pairs=22, length=0.018, width=0.0022, serr=0.0, shape='lance', stem=0.1, color=(0.12, 0.26, 0.12)),
        'thyme': dict(pairs=12, length=0.0045, width=0.0022, serr=0.0, shape='lance', stem=0.06, color=(0.18, 0.30, 0.12)),
    }[kind]
    L = spec['stem'] * size
    stem_pts = [(L * s, 0.002 * math.sin(s * 3 + seed), 0.002 + 0.004 * math.sin(s * math.pi)) for s in np.linspace(0, 1, 16)]
    stem = K.sweep(f'{name}_stem', stem_pts, [0.0011 * size * (1 - 0.5 * s) for s in np.linspace(0, 1, 16)], sides=6)
    stem_color = (0.30, 0.42, 0.14) if kind not in ('rosemary', 'thyme') else (0.30, 0.24, 0.14)
    K.assign(stem, K.solid(f'{name}_stem_mat', stem_color, rough=0.55))
    parts.append(stem)
    if leaf_mat is None:
        color, rough, normal = leaf_texture(base=spec['color'], seed=seed,
                                            vein=tuple(min(1, c * 1.9 + 0.05) for c in spec['color']))
        leaf_mat = K.textured(f'{name}_leaf', color, rough, normal, spec=0.45)
    pairs = spec['pairs']
    for i in range(pairs):
        s = 0.25 + 0.75 * (i / max(1, pairs - 1)) if pairs > 1 else 0.8
        scale = (1.0 - 0.45 * s) if kind in ('mint', 'basil') else (0.8 + 0.3 * rng.random())
        for side in (-1, 1):
            needles = kind in ('rosemary', 'thyme')
            lf = leaf_mesh(f'{name}_l{i}{side}', spec['length'] * size * scale, spec['width'] * size * scale,
                           serration=spec['serr'], shape=spec['shape'], fold=0.18, curl=0.1 + 0.1 * rng.random(),
                           lobes=3 if kind in ('parsley', 'cilantro') else 0,
                           nu=5 if needles else 12, nv=2 if needles else 6, thick=not needles)
            ang = side * (0.9 + 0.3 * rng.random()) if kind not in ('rosemary', 'thyme') else side * (0.5 + 0.3 * rng.random())
            px = L * s
            lf.rotation_euler = (side * 0.25, -0.15 - 0.2 * rng.random(), ang + (rng.random() - 0.5) * 0.3)
            lf.location = (px, 0, 0.003 + 0.004 * math.sin(s * math.pi))
            K.apply_transform(lf)
            K.assign(lf, leaf_mat)
            parts.append(lf)
    if kind in ('mint', 'basil', 'parsley', 'cilantro'):     # crown of small leaves at the tip
        for k in range(3):
            lf = leaf_mesh(f'{name}_tip{k}', spec['length'] * size * 0.5, spec['width'] * size * 0.45,
                           serration=spec['serr'], shape=spec['shape'], fold=0.3, curl=0.3)
            lf.rotation_euler = (0, -0.4, (k - 1) * 0.7)
            lf.location = (L, 0, 0.004)
            K.apply_transform(lf)
            K.assign(lf, leaf_mat)
            parts.append(lf)
    obj = K.join(parts, name)
    smooth(obj, 70)
    set_origin_bottom(obj)
    return obj


def herb_flakes(name, targets, region, count, color=(0.12, 0.36, 0.07), size=0.004, seed=0):
    """Chopped herbs (parsley, dill, cilantro, green onion bits) scattered on food."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=size / 2)
    for v in bm.verts:
        v.co.z = (abs(v.co.x) + abs(v.co.y)) * 0.25
    tpl = K.template(bm)
    tv = tpl[0]
    # give the flake a thickness: duplicate offset (cheap two-sided)
    obj = K.scatter(name, targets, (tv, tpl[1], tpl[2]), count, region, rng, scale=(0.6, 1.4), embed=0.0,
                    tilt=0.8, colors=lambda r: tuple(c * (0.8 + 0.4 * r.random()) for c in color))
    K.solidify(obj, 0.0003, offset=0)
    K.assign(obj, K.solid(f'{name}_mat', (1, 1, 1), rough=0.5, vcol=True))
    set_origin_bottom(obj)
    return obj


# ================================================================== ice

def ice_cube(name='ice', size=0.024, seed=0):
    rng = np.random.default_rng(seed)
    obj = K.rounded_box(name, (size, size * (0.9 + 0.2 * rng.random()), size * (0.85 + 0.2 * rng.random())), bevel=0.18,
                        segments=3)
    K.subdivide(obj, 2)
    K.displace(obj, size * 0.05, size * 0.4, depth=2)
    obj.location = (rng.random() * 3, rng.random() * 3, 0)   # different noise for each cube
    K.apply_transform(obj)
    set_origin_bottom(obj)
    lo, hi = K.bounds(obj)
    obj.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0)
    K.apply_transform(obj)
    return obj


def ice_material(name='ice'):
    res = 512
    f1, f2 = K.cells(res, 18, 3)
    crack = np.clip(1 - (f2 - f1) / 0.012, 0, 1)
    bub = (K.vnoise(res, 120, 5) > 0.86).astype(np.float32)
    cloud = K.fbm(res, 6, 9, 3)
    col = K.lerp_color((0.70, 0.82, 0.88), (0.97, 0.99, 1.0), np.clip(crack * 0.8 + bub * 0.6 + cloud * 0.35, 0, 1))
    rough = (0.04 + 0.2 * crack).astype(np.float32)
    return K.textured(name, col.astype(np.float32), rough, K.height_to_normal(cloud * 0.4 + crack * 0.3, 0.6), spec=0.6)
