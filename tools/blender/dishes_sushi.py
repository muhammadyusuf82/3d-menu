"""Salmon nigiri, California roll, Philadelphia roll on a slate board."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import containers as C
import kit as K
import sauces as S
from lib import bake, new_object, planar_uv, set_origin_bottom, smooth, uv_unwrap


# ------------------------------------------------------------------ textures

def rice_texture(res=1024, grains=340, seed=0, grain=0.10):
    """Packed sushi rice: many glossy grains with shaded domes, slightly translucent gaps."""
    rng = np.random.default_rng(seed)
    height = np.zeros((res, res), np.float32)
    tone = np.zeros((res, res), np.float32)
    L, W = grain * res, grain * 0.5 * res
    for _ in range(grains):
        cx, cy = rng.random(2) * res
        a = rng.random() * math.pi
        rad = int(L) + 2
        x0, x1 = int(cx) - rad, int(cx) + rad
        y0, y1 = int(cy) - rad, int(cy) + rad
        yy, xx = np.mgrid[y0:y1, x0:x1]
        u, v = xx - cx, yy - cy
        cu, su = math.cos(a), math.sin(a)
        e = ((u * cu + v * su) / (L / 2)) ** 2 + ((-u * su + v * cu) / (W / 2)) ** 2
        dome = np.clip(1 - e, 0, 1) ** 0.5
        yi, xi = yy % res, xx % res
        h = height[yi, xi]
        upd = dome > h
        height[yi[upd], xi[upd]] = dome[upd]
        tone[yi[upd], xi[upd]] = 0.9 + 0.1 * rng.random()
    col = K.lerp_color((0.62, 0.60, 0.56), (0.98, 0.97, 0.93), np.clip(height * 1.6, 0, 1) * tone)
    rough = (0.55 - 0.3 * height).astype(np.float32)
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal(height, 1.5)


def salmon_texture(res=1024, seed=0):
    x, y, r, t = K.grid(res)
    n = K.fbm(res, 8, seed, 4)
    warp = K.fbm(res, 3, seed + 1, 3)
    phase = (x * 0.8 + y * 0.6) * 9 + warp * 4
    fat = K.smoothstep(0.86, 0.97, np.sin(phase) * 0.5 + 0.5)
    fine = K.smoothstep(0.9, 1.0, np.sin(phase * 3.1 + 1) * 0.5 + 0.5) * 0.5
    col = K.lerp_color((0.98, 0.46, 0.20), (0.93, 0.36, 0.14), n)
    lines = np.clip(fat + fine, 0, 1)
    col = col * (1 - lines[..., None] * 0.8) + np.array([1.0, 0.86, 0.74]) * lines[..., None] * 0.8
    # darker, redder fat-line belly at one side, lighter towards the cut edge
    col = col * (0.88 + 0.16 * K.smoothstep(-1, 1, y))[..., None]
    rough = (0.24 + 0.1 * lines).astype(np.float32)
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal((lines * 0.4 + n * 0.3).astype(np.float32), 0.6)


def tobiko_texture(res=1024, seed=0):
    f1, f2 = K.cells(res, 1100, seed)          # texture tiles every 4 cm -> ~1.2 mm roe
    bead = np.clip(1 - f1 / 0.016, 0, 1)
    spec = np.clip(1 - np.abs(f1 - 0.006) / 0.004, 0, 1)
    col = K.lerp_color((0.62, 0.12, 0.0), (1.0, 0.45, 0.06), bead ** 0.7)
    col = col + spec[..., None] * 0.15
    return np.clip(col, 0, 1).astype(np.float32), (0.12 + 0.3 * (1 - bead)).astype(np.float32), \
        K.height_to_normal(bead.astype(np.float32), 3.0)


def nori_mat():
    res = 512
    n = K.fbm(res, 30, 3, 4)
    fibres = K.vnoise(res, 200, 4, aspect=0.2)
    col = K.lerp_color((0.035, 0.05, 0.035), (0.08, 0.11, 0.07), n * 0.7 + fibres * 0.3)
    return K.textured('nori_mat', col.astype(np.float32), (0.45 + 0.15 * n).astype(np.float32),
                      K.height_to_normal(fibres, 0.5), spec=0.45)


def _rice_mat():
    color, rough, normal = rice_texture()
    return K.textured('rice_mat', color, rough, normal, spec=0.5)


def _grains_on(name, obj, count, rng, min_up=-1.0):
    """Real rice grains on an object's surface (silhouette detail the texture can't give)."""
    tpl = K.ellipsoid_tpl(0.0026, 0.0012, 0.0011, 6, 4)
    me = obj.data
    polys = [p for p in me.polygons if p.normal.z >= min_up]
    weights = np.array([p.area for p in polys])
    pick = rng.choice(len(polys), size=count, p=weights / weights.sum())
    mats, cols = [], []
    for i in pick:
        p = polys[i]
        c = obj.matrix_world @ p.center
        n = (obj.matrix_world.to_3x3() @ p.normal).normalized()
        mats.append(K.frame(c + n * 0.0004, n, rng.random() * math.tau, (1, 1, 1), (rng.uniform(-0.3, 0.3), 0)))
        g = 0.93 + 0.06 * rng.random()
        cols.append((g, g, g * 0.97))
    grains = K.instances(name, tpl, mats, cols)
    K.assign(grains, K.solid(name + '_mat', (1, 1, 1), rough=0.3, spec=0.5, vcol=True))
    return grains


# ------------------------------------------------------------------ nigiri

def _nigiri_template(rng):
    bed = K.blob('bed', 1.0, scale=(0.024, 0.0105, 0.0085), lumps=0, subdiv=3)
    for v in bed.data.vertices:
        if v.co.z < 0:
            v.co.z *= 0.35
    K.displace(bed, 0.0008, 0.004)
    set_origin_bottom(bed)
    bed.location = (0, 0, 0)
    K.apply_transform(bed)
    uv_unwrap(bed)
    K.assign(bed, _rice_mat())
    rice = bed
    inside = lambda x, y: abs(x) < 0.031 and abs(y) < 0.0125 * (1 - 0.25 * (abs(x) / 0.031) ** 4)
    fish = K.drape('salmon_tpl', [rice], 0.035, inside, offset=0.0011, res=60, thickness=0.0055, smooth_iter=6)
    for v in fish.data.vertices:             # tips lift slightly, like a real hand-cut slice
        v.co.z += 0.0025 * (abs(v.co.x) / 0.031) ** 3
    K.subdivide(fish, 1)
    planar_uv(fish)
    color, rough, normal = salmon_texture()
    K.assign(fish, K.textured('salmon_mat', color, rough, normal, spec=0.55))
    smooth(fish, 60)
    return rice, fish


def salmon_nigiri(d):
    slate = d.base(C.slate(size=(0.32, 0.17)))
    soy_v = C.soy_dish()
    K.transform(soy_v.obj, loc=(0.06, 0.14, 0))
    d.base(soy_v)
    rng = np.random.default_rng(2)
    rice_t, fish_t = _nigiri_template(rng)
    spots = [(-0.1 + 0.06 * i, 0.032 * (1 if j else -1) + 0.004 * (i % 2)) for j in (0, 1) for i in range(3)]
    rice_m, fish_m = [], []
    for k, (x, y) in enumerate(spots):
        m = K.frame((x, y, slate.floor), (0, 0, 1), 0.35 + rng.uniform(-0.08, 0.08), (1 + rng.uniform(-0.04, 0.04),) * 3)
        rice_m.append(m)
        fish_m.append(m)
    beds = K.instances('beds', K.template(rice_t), rice_m)
    K.assign(beds, rice_t.data.materials[0])
    grains = _grains_on('grains', beds, 720, rng, min_up=-0.2)
    rice = K.join([beds, grains], 'sushi-rice')
    fish = K.instances('salmon', K.template(fish_t), fish_m)
    K.assign(fish, fish_t.data.materials[0])
    smooth(rice, 60)
    smooth(fish, 60)
    K.remove(rice_t)
    K.remove(fish_t)
    d.part(rice, 'sushi-rice')
    d.part(fish, 'salmon')
    wasabi = K.blob('wasabi', 0.011, scale=(1.2, 1.0, 0.75), lumps=0.3, subdiv=4, seed=3)
    s = K.Shader('wasabi_mat', spec=0.4)
    n = s.noise(500, 4, 0.6)
    s.out(s.ramp(n, [(0.3, (0.18, 0.30, 0.03)), (0.7, (0.34, 0.48, 0.07))]), rough=0.6, height=n, strength=0.6,
          distance=0.0006)
    K.assign(wasabi, s.mat)
    uv_unwrap(wasabi)
    bake(wasabi, res=512)
    K.place(wasabi, [slate.obj], 0.115, 0.035)
    d.part(wasabi, 'wasabi')
    petals = []
    for i in range(9):
        p = _ginger_petal(f'g{i}', rng)
        K.place(p, [slate.obj] + petals, 0.115 + rng.uniform(-0.012, 0.012), -0.03 + rng.uniform(-0.012, 0.012),
                rot=(rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.random() * math.tau))
        petals.append(p)
    ginger = K.join(petals, 'ginger')
    K.assign(ginger, K.solid('ginger_mat', (0.92, 0.50, 0.45), rough=0.25, spec=0.5))
    d.part(ginger, 'ginger')
    soy = S.fill(soy_v, soy_v.floor + 0.004, 'soy', K.solid('soy_mat', (0.03, 0.008, 0.002), rough=0.03, spec=0.6),
                 meniscus=0.0006)
    K.transform(soy, loc=(0.06, 0.14, 0))
    d.part(soy, 'soy')


def _ginger_petal(name, rng):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=1.0, segments=24)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
    a, b = 0.014 * (0.8 + 0.4 * rng.random()), 0.01 * (0.8 + 0.4 * rng.random())
    curl = rng.uniform(40, 90)
    for v in bm.verts:
        x, y = v.co.x * a, v.co.y * b
        v.co = Vector((x, y, curl * (x * x) * 0.5 + 0.0008 * math.sin(y * 600)))
    obj = new_object(name, bm)
    K.solidify(obj, 0.0007, offset=0)
    smooth(obj, 60)
    return obj


# ------------------------------------------------------------------ rolls (uramaki)

def _annulus(name, r_in, r_out, h, seg=48, uv='planar'):
    if r_in <= 0:
        prof = [(0.0, 0.0), (r_out, 0.0), (r_out, h), (0.0, h)]
    else:
        prof = [(r_in, 0.0), (r_out, 0.0), (r_out, h), (r_in, h), (r_in, 0.0)]
    return K.revolve(name, prof, segments=seg, uv=uv)


def _roll_piece(kind, rng):
    """One uramaki piece (as separate template objects per ingredient). kind: 'california' | 'philadelphia'."""
    h = 0.021
    out = {}
    r_coat_out, r_rice_out, r_nori_out = 0.0235, 0.0222, 0.0128
    coat_name = 'tobiko' if kind == 'california' else 'salmon'
    coat = _annulus(coat_name, r_rice_out - 0.0004, r_coat_out, h, seg=64, uv='wrap')
    rice = _annulus('sushi-rice', r_nori_out, r_rice_out, h, seg=64)
    nori = _annulus('nori', r_nori_out - 0.0009, r_nori_out, h, seg=64)
    planar_uv(rice)
    _real_uv(coat, 0.04)
    out[coat_name] = coat
    out['sushi-rice'] = rice
    out['nori'] = nori
    # filling inside the nori ring
    fill_r = r_nori_out - 0.0009
    def stick(name, r, at, color_top, color_side, shape='round'):
        o = _annulus(name, 0.0, r, h * 0.995, seg=24)
        if shape == 'crescent':
            for v in o.data.vertices:
                ang = math.atan2(v.co.y, v.co.x)
                v.co.x *= 1.5
                v.co.y *= 0.7
        o.location = (at[0], at[1], 0.0001)
        K.apply_transform(o)
        s = K.Shader(name + '_mat', spec=0.5)
        top = s.maprange(s.up(), 0.5, 0.9, 0, 1)
        s.out(s.mix(color_side, color_top, top), rough=0.3, height=s.noise(300, 3, 0.5), strength=0.2, distance=0.0002)
        K.assign(o, s.mat)
        return o
    if kind == 'california':
        out['crab'] = K.join([stick('crab_a', 0.0042, (-0.004, 0.003), (0.92, 0.88, 0.82), (0.75, 0.10, 0.04)),
                              stick('crab_b', 0.0038, (0.0035, 0.0045), (0.92, 0.88, 0.82), (0.75, 0.10, 0.04))], 'crab')
        out['avocado'] = stick('avocado', 0.004, (0.0, -0.005), (0.62, 0.70, 0.22), (0.20, 0.32, 0.05), 'crescent')
        out['cucumber'] = stick('cucumber', 0.0028, (0.0062, -0.0015), (0.70, 0.80, 0.50), (0.05, 0.20, 0.03))
    else:
        out['cream-cheese'] = stick('cream-cheese', 0.0062, (-0.002, 0.0015), (0.97, 0.96, 0.92), (0.95, 0.94, 0.90))
        out['cucumber'] = stick('cucumber', 0.003, (0.0055, -0.0035), (0.70, 0.80, 0.50), (0.05, 0.20, 0.03))
    return out


def _real_uv(obj, tile):
    """Cylindrical UVs in real units (texture repeats every `tile` metres), so roe / fish are never stretched."""
    me = obj.data
    uv = me.uv_layers.active
    for p in me.polygons:
        us = []
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            r = math.hypot(co.x, co.y)
            us.append((math.atan2(co.y, co.x) * max(r, 1e-4) / tile, co.z / tile))
        # avoid the seam wrap on faces that straddle the -x axis
        span = max(u for u, _ in us) - min(u for u, _ in us)
        if span > 0.5 * math.pi * 0.023 / tile:
            us = [(u + (2 * math.pi * 0.023 / tile if u < 0 else 0), v) for u, v in us]
        for li, val in zip(p.loop_indices, us):
            uv.data[li].uv = val


def _roll(d, kind):
    slate = d.base(C.slate(size=(0.30, 0.15)))
    rng = np.random.default_rng(5 if kind == 'california' else 9)
    piece = _roll_piece(kind, rng)
    rice_mat = _rice_mat()
    piece['sushi-rice'].data.materials.clear()
    piece['sushi-rice'].data.materials.append(rice_mat)
    piece['nori'].data.materials.append(nori_mat())
    if kind == 'california':
        col, rough, normal = tobiko_texture()
        coat_mat = K.textured('tobiko_mat', col, rough, normal, spec=0.6)
        piece['tobiko'].data.materials.append(coat_mat)
    else:
        col, rough, normal = salmon_texture(seed=3)
        piece['salmon'].data.materials.append(K.textured('salmon_mat', col, rough, normal, spec=0.55))
    for name in ('crab', 'avocado', 'cucumber', 'cream-cheese'):
        if name in piece:
            uv_unwrap(piece[name])
            bake(piece[name], res=256, normal=False)
    spots = [(-0.075 + 0.05 * i, 0.027 * (1 if j else -1)) for j in (0, 1) for i in range(4)]
    mats = []
    for x, y in spots:
        tilt = (rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05))
        mats.append(K.frame((x, y, slate.floor), (0, 0, 1), rng.random() * math.tau, (1, 1, 1), tilt))
    order = ['nori', 'sushi-rice'] + [k for k in ('crab', 'avocado', 'cucumber', 'cream-cheese') if k in piece] + \
            (['tobiko'] if kind == 'california' else ['salmon'])
    built = {}
    for name in order:
        t = piece[name]
        obj = K.instances(name, K.template(t), mats)
        K.assign(obj, t.data.materials[0])
        smooth(obj, 40 if name != 'sushi-rice' else 30)
        K.remove(t)
        built[name] = obj
    # real grains on the cut face of the rice ring
    rice = built['sushi-rice']
    grains = _grains_on('grains', rice, 900, rng, min_up=0.7)
    built['sushi-rice'] = K.join([rice, grains], 'sushi-rice')
    for name in order:
        d.part(built[name], name)
    tops = [built['sushi-rice']]
    seeds_tpl = K.ellipsoid_tpl(0.0016, 0.001, 0.0006, 6, 4)
    def seed_region(r):
        x, y = spots[int(r.integers(0, len(spots)))]
        a, rr = r.random() * math.tau, 0.013 + 0.009 * r.random()
        return x + rr * math.cos(a), y + rr * math.sin(a)
    sesame = K.scatter('sesame', tops + [built['tobiko' if kind == 'california' else 'salmon']], seeds_tpl,
                       160, seed_region, rng, embed=0.2, tilt=0.5,
                       colors=lambda r: (0.95, 0.88, 0.70) if r.random() > 0.25 else (0.25, 0.2, 0.15))
    K.assign(sesame, K.solid('sesame_mat', (1, 1, 1), rough=0.4, vcol=True))
    if kind == 'california':
        # sesame goes under the tobiko in the explode order (tobiko is the outermost coat)
        d.parts.insert(len(d.parts) - 1, sesame)
        sesame.name = 'sesame'
    else:
        d.part(sesame, 'sesame')


def california_roll(d):
    _roll(d, 'california')


def philadelphia_roll(d):
    _roll(d, 'philadelphia')


DISHES = {
    'salmon-nigiri': salmon_nigiri,
    'california-roll': california_roll,
    'philadelphia-roll': philadelphia_roll,
}
