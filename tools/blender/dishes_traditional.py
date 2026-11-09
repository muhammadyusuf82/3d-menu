"""Samarkand plov, manti, lagman and lamb shashlik."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import containers as C
import cooked as F
import kit as K
import produce as P
import sauces as S
import veg_parts as V
from dishes_sushi import rice_texture
from lib import bake, new_object, planar_uv, set_origin_bottom, smooth, uv_unwrap


def _mound(name, radius, height, seed=0, lumps=0.08):
    rng = np.random.default_rng(seed)
    prof = [(radius * s, height * (1 - s ** 2.2) ** 0.8) for s in np.linspace(0, 1, 24)]
    prof[-1] = (radius, 0.0)
    obj = K.revolve(name, [(0.0, 0.0)] + [(radius, 0.0)] + prof[::-1][1:], segments=96, uv='planar')
    K.subdivide(obj, 1)
    obj.location = tuple(rng.random(3) * 3)
    K.apply_transform(obj)
    K.displace(obj, height * lumps, radius * 0.25, depth=2)
    lo, hi = K.bounds(obj)
    obj.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])
    K.apply_transform(obj)
    return obj


def _surface_grains(name, base, count, rng, tpl, colors, min_up=0.15, lift=0.0006):
    me = base.data
    polys = [p for p in me.polygons if p.normal.z > min_up]
    w = np.array([p.area for p in polys])
    pick = rng.choice(len(polys), size=count, p=w / w.sum())
    mats, cols = [], []
    for i in pick:
        p = polys[i]
        # random point inside the face
        vs = [me.vertices[k].co for k in p.vertices]
        a, b = rng.random(2)
        if a + b > 1:
            a, b = 1 - a, 1 - b
        c = vs[0] + (vs[1] - vs[0]) * a + (vs[2] - vs[0]) * b
        mats.append(K.frame(c + p.normal * lift, p.normal, rng.random() * math.tau, (1, 1, 1),
                            (rng.uniform(-0.35, 0.35), rng.uniform(-0.2, 0.2))))
        cols.append(colors(rng))
    obj = K.instances(name, tpl, mats, cols)
    K.assign(obj, K.solid(name + '_mat', (1, 1, 1), rough=0.28, spec=0.5, vcol=True))
    return obj


# ------------------------------------------------------------------ plov

def plov(d):
    lyagan = d.base(C.plate('lyagan', radius=0.165, well=0.12, rim_h=0.024, pattern='paxta'))
    rng = np.random.default_rng(1)
    mound = _mound('rice_body', 0.1, 0.048, seed=1)
    K.transform(mound, loc=(0, 0, lyagan.floor - 0.001))
    col, rough, normal = rice_texture(seed=3, grain=0.06, grains=900)
    col = np.clip(col * np.array([1.0, 0.82, 0.52]), 0, 1).astype(np.float32)        # amber, oil-soaked devzira
    K.assign(mound, K.textured('plov_rice_mat', col, rough * 0.7, normal, spec=0.55))
    tpl = K.ellipsoid_tpl(0.0034, 0.0012, 0.0011, 5, 3)
    grains = _surface_grains('rice_grains', mound, 1900, rng, tpl,
                             lambda r: tuple(c * (0.85 + 0.25 * r.random()) for c in (0.80, 0.52, 0.18)))
    d.part(K.join([mound, grains], 'rice'), 'rice')
    rice = d.parts[-1]
    stick = K.rounded_box('stick', (0.055, 0.0042, 0.0038), bevel=0.3, segments=1)
    stick_tpl = K.template(stick)
    K.remove(stick)
    carrot = K.scatter('carrot', [rice], stick_tpl, 70, K.disc_region(0.075), rng, scale=(0.6, 1.1), embed=0.4, tilt=0.3,
                       align=1.0, colors=lambda r: (0.90, 0.45, 0.04) if r.random() > 0.35 else (0.95, 0.30, 0.02))
    K.assign(carrot, K.solid('carrot_mat', (1, 1, 1), rough=0.22, spec=0.55, vcol=True))
    d.part(carrot, 'carrot')
    lamb_mat = F.meat_mat('lamb_mat', (0.36, 0.13, 0.04), (0.14, 0.045, 0.015), gloss=0.2, char=0.3)
    lamb = []
    for i in range(9):
        p = K.blob(f'lamb_{i}', 0.017, scale=(1.35, 1.0, 0.7), lumps=0.5, lump_size=0.5, subdiv=3, seed=i)
        a = i / 9 * math.tau
        rr = 0.034 if i % 2 else 0.05
        K.place(p, [rice, carrot], rr * math.cos(a), rr * math.sin(a), rot=(0.15, 0.1, a), sink=0.004)
        lamb.append(p)
    lamb = K.join(lamb, 'lamb')
    K.assign(lamb, lamb_mat)
    uv_unwrap(lamb)
    bake(lamb, res=1024)
    d.part(lamb, 'lamb')
    tops = [rice, carrot, lamb]
    pea = K.ellipsoid_tpl(0.0045, 0.0042, 0.0042, 10, 7)
    d.part(_scatter_vc('chickpeas', tops, pea, 26, K.disc_region(0.08), rng, (0.78, 0.55, 0.25), 0.35), 'chickpeas')
    berry = K.ellipsoid_tpl(0.0028, 0.0019, 0.0019, 8, 5)
    d.part(_scatter_vc('barberry', tops + [d.parts[-1]], berry, 36, K.disc_region(0.085), rng, (0.35, 0.01, 0.015), 0.15),
           'barberry')
    garlic = _garlic_head()
    K.place(garlic, [rice, carrot], 0.0, 0.0, rot=(0.15, 0.0, 0.3), sink=0.008)
    d.part(garlic, 'garlic-head')


def _scatter_vc(name, targets, tpl, count, region, rng, color, rough):
    obj = K.scatter(name, targets, tpl, count, region, rng, scale=(0.85, 1.15), embed=0.35, tilt=1.0,
                    colors=lambda r: tuple(c * (0.8 + 0.35 * r.random()) for c in color))
    K.assign(obj, K.solid(name + '_mat', (1, 1, 1), rough=rough, spec=0.5, vcol=True))
    return obj


def _garlic_head():
    obj = K.revolve('garlic-head', [(0.0, 0.0)] + [(0.024 * math.sin(s * math.pi) ** 0.8 * (1 - 0.3 * s), 0.036 * s)
                                                     for s in np.linspace(0.02, 1, 24)] + [(0.0, 0.037)], segments=72,
                    uv='wrap')
    for v in obj.data.vertices:
        a = math.atan2(v.co.y, v.co.x)
        k = 1 + 0.1 * abs(math.sin(a * 5))         # cloves bulging
        v.co.x *= k
        v.co.y *= k
    s = K.Shader('garlic_mat', spec=0.45)
    n = s.noise(80, 5, 0.6)
    streak = s.wave(60, distortion=2, bands='Z')
    col = s.ramp(n, [(0.3, (0.55, 0.32, 0.12)), (0.7, (0.86, 0.66, 0.40))])
    col = s.mix(col, (0.45, 0.22, 0.08), s.math('MULTIPLY', streak, 0.25))
    s.out(col, rough=0.35, height=s.math('ADD', n, s.math('MULTIPLY', streak, 0.3)), strength=0.4, distance=0.0006)
    K.assign(obj, s.mat)
    smooth(obj, 60)
    uv_unwrap(obj)
    bake(obj, res=512)
    set_origin_bottom(obj)
    return obj


# ------------------------------------------------------------------ manti

def _manti_template():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=11, use_grid_fill=True)
    R, H = 0.028, 0.037
    for v in bm.verts:
        p = v.co.normalized()
        x, y, z = p
        a = math.atan2(y, x)
        sq = 1 + 0.16 * math.cos(4 * a)                      # square-ish pouch
        seam = max(0.0, math.cos(4 * (a - math.pi / 4))) ** 6  # 4 pinched seams meeting at the top
        if z < 0:
            z *= 0.35
        zz = (z * 0.5 + 0.5)
        lift = seam * max(0.0, zz - 0.45) * 0.55
        pinch = 1 - 0.55 * max(0.0, zz - 0.55) ** 1.2 - 0.25 * seam * max(0.0, zz - 0.5)
        v.co = Vector((x * R * sq * pinch, y * R * sq * pinch, zz * H * (1 + lift)))
    obj = new_object('manti_tpl', bm)
    s = K.Shader('dough_mat', spec=0.45)
    n = s.noise(60, 4, 0.6)
    thin = s.maprange(s.position('Z'), 0.0, 0.034, 0, 1)
    col = s.ramp(n, [(0.3, (0.78, 0.62, 0.40)), (0.7, (0.90, 0.79, 0.58))])
    col = s.mix(col, (0.55, 0.38, 0.25), s.math('MULTIPLY', s.math('SUBTRACT', 1, thin), 0.15))
    pleat = s.wave(220, distortion=3, bands='Z')
    s.out(col, rough=s.maprange(n, 0.3, 0.7, 0.28, 0.45), height=s.math('ADD', pleat, n), strength=0.25, distance=0.0005)
    K.assign(obj, s.mat)
    smooth(obj, 70)
    uv_unwrap(obj)
    bake(obj, res=1024)
    set_origin_bottom(obj)
    obj.location = (0, 0, 0)
    return obj


def manti(d):
    plate = d.base(C.plate('lyagan', radius=0.145, well=0.1, pattern='paxta'))
    rng = np.random.default_rng(4)
    tpl_obj = _manti_template()
    mats, spots = [], []
    for i in range(6):
        a = i / 6 * math.tau + 0.3
        x, y = 0.05 * math.cos(a) - 0.012, 0.05 * math.sin(a)
        spots.append((x, y))
        mats.append(K.frame((x, y, plate.floor - 0.0005), (0, 0, 1), rng.random(), (1 + rng.uniform(-0.05, 0.05),) * 3,
                            (rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05))))
    m = K.instances('manti', K.template(tpl_obj), mats)
    K.assign(m, tpl_obj.data.materials[0])
    smooth(m, 70)
    K.remove(tpl_obj)
    d.part(m, 'manti')
    yogurt = S.dollop('yogurt', 0.022, 0.016, S.cream_mat('yogurt_mat', color=(0.96, 0.95, 0.92), rough=0.3), seed=3)
    K.place(yogurt, [plate.obj], 0.075, -0.045, sink=0.001)
    uv_unwrap(yogurt)
    bake(yogurt, res=512)
    d.part(yogurt, 'yogurt')
    rings = F.ring_tpl(r=0.011, tube=0.0016, flat=0.55)
    onion = K.scatter('sumac-onion', [plate.obj, yogurt], rings, 9, K.disc_region(0.022, 0.075, 0.04), rng,
                      scale=(0.7, 1.1), embed=0.2, tilt=0.5,
                      colors=lambda r: (0.55, 0.12, 0.25) if r.random() > 0.4 else (0.75, 0.40, 0.50))
    K.assign(onion, K.solid('sumac_onion_mat', (1, 1, 1), rough=0.3, vcol=True))
    d.part(onion, 'sumac-onion')
    tops = [m]
    inside = lambda x, y: min(math.hypot(x - sx, y - sy) for sx, sy in spots) < 0.016
    butter = K.drape('butter-melt', tops, 0.09, inside, offset=0.0006, res=160, thickness=0.0008, smooth_iter=3,
                     center=(-0.012, 0.0))
    K.assign(butter, K.solid('butter_mat', (0.95, 0.72, 0.25), rough=0.03, spec=0.6, alpha=0.35))
    d.part(butter, 'butter-melt')
    d.part(P.herb_flakes('dill', tops + [butter], K.disc_region(0.07, -0.012, 0.0), 120, color=(0.06, 0.20, 0.03),
                         size=0.003, seed=6), 'dill')


# ------------------------------------------------------------------ lagman

def lagman(d):
    kosa = d.base(C.bowl('kosa', radius=0.1, depth=0.072, foot=0.04, pattern='paxta'))
    rng = np.random.default_rng(6)
    level = kosa.floor + (kosa.rim - kosa.floor) * 0.62
    d.part(S.fill(kosa, level, 'broth', K.solid('broth_mat', (0.36, 0.10, 0.02), rough=0.04, spec=0.55)), 'broth')
    noodles = []
    for k in range(30):
        r0 = kosa.r_at(level) * 0.75 * math.sqrt(rng.random())
        a0 = rng.random() * math.tau
        pts = []
        x, y = r0 * math.cos(a0), r0 * math.sin(a0)
        heading = rng.random() * math.tau
        for i in range(56):
            heading += rng.normal(0, 0.35)
            x += math.cos(heading) * 0.004
            y += math.sin(heading) * 0.004
            rr = math.hypot(x, y)
            lim = kosa.r_at(level) * 0.82
            if rr > lim:
                heading += math.pi * 0.8
                x, y = x / rr * lim, y / rr * lim
            dome = 0.024 * (1 - (math.hypot(x, y) / lim) ** 2)
            z = level - 0.006 + dome * (0.4 + 0.6 * rng.random()) + 0.003 * math.sin(i * 0.4 + k)
            pts.append((x, y, z))
        n = K.sweep(f'n{k}', pts, 0.0028, sides=6)
        noodles.append(n)
    rng_c = np.random.default_rng(11)
    for n in noodles:     # per-noodle tone instead of a baked texture (thin UV islands bake badly)
        attr = n.data.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
        tone = 0.88 + 0.18 * rng_c.random()
        for c in attr.data:
            c.color = (0.90 * tone, 0.70 * tone, 0.36 * tone, 1)
    nood = K.join(noodles, 'noodles')
    K.assign(nood, K.solid('noodle_mat', (1, 1, 1), rough=0.28, spec=0.5, vcol=True))
    smooth(nood, 60)
    d.part(nood, 'noodles')
    tops = [nood, d.parts[0]]
    beef_mat = F.meat_mat('beef_mat', (0.26, 0.08, 0.025), (0.10, 0.03, 0.01), gloss=0.15, char=0.2)
    strips = []
    for i in range(10):
        p = K.blob(f'b{i}', 0.008, scale=(2.2, 0.8, 0.55), lumps=0.3, subdiv=3, seed=i)
        a = rng.random() * math.tau
        rr = 0.035 * math.sqrt(rng.random())
        K.place(p, tops, rr * math.cos(a), rr * math.sin(a), rot=(0.1, 0.1, rng.random() * math.tau), sink=0.002)
        strips.append(p)
    beef = K.join(strips, 'beef')
    K.assign(beef, beef_mat)
    uv_unwrap(beef)
    bake(beef, res=512)
    d.part(beef, 'beef')
    pep = []
    for i in range(18):
        arc = [(0.012 * math.cos(a), 0.012 * math.sin(a), 0) for a in np.linspace(0, 1.4, 10)]
        p = K.sweep(f'p{i}', arc, 0.0022, sides=6)
        for v in p.data.vertices:
            v.co.z *= 0.45
        a = rng.random() * math.tau
        rr = 0.05 * math.sqrt(rng.random())
        K.place(p, tops + [beef], rr * math.cos(a), rr * math.sin(a), rot=(0, 0, rng.random() * math.tau), sink=0.0015)
        color = (0.55, 0.03, 0.01) if i % 3 else (0.10, 0.30, 0.03)
        attr = p.data.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
        for c in attr.data:
            c.color = (*color, 1)
        pep.append(p)
    peppers = K.join(pep, 'peppers')
    K.assign(peppers, K.solid('pepper_mat', (1, 1, 1), rough=0.15, spec=0.6, vcol=True))
    d.part(peppers, 'peppers')
    c1 = P.sprig('cil_a', 'cilantro', size=0.9, seed=3)
    K.place(c1, tops + [beef, peppers], 0.01, -0.01, rot=(0, 0, 0.6), sink=0.002)
    flakes = P.herb_flakes('cil_b', tops + [beef, peppers], K.disc_region(0.05), 40, color=(0.08, 0.26, 0.04), size=0.005,
                           seed=8)
    d.part(K.join([c1, flakes], 'cilantro'), 'cilantro')


# ------------------------------------------------------------------ shashlik

def shashlik(d):
    board = d.base(C.wooden_board(length=0.42))
    rng = np.random.default_rng(8)
    # lavash: a big thin flatbread lying in soft folds
    lav = K.drape('lavash', [board.obj], 0.16, lambda x, y: abs(x) < 0.15 and abs(y) < 0.1 * (1 + 0.06 * math.sin(x * 40)),
                  offset=0.0015, res=110, thickness=0.0018, smooth_iter=2)
    for v in lav.data.vertices:          # soft folds
        v.co.z += 0.0025 * (math.sin(v.co.x * 40 + 1) * math.cos(v.co.y * 25) + 1)
    col, rough, normal = F.flatbread_texture(seed=5, toast=0.6)
    K.assign(lav, K.textured('lavash_mat', col, rough, normal, spec=0.3))
    smooth(lav, 50)
    d.part(lav, 'lavash')
    meat_mat = F.meat_mat('shashlik_mat', (0.46, 0.17, 0.05), (0.045, 0.014, 0.005), gloss=0.25, char=0.85)
    skewers, meats = [], []
    for k in range(3):
        y = -0.05 + k * 0.05
        rz = (k - 1) * 0.06
        z = board.floor + 0.022
        cs, sn = math.cos(rz), math.sin(rz)
        start = np.array([-0.13 * cs, y - 0.13 * sn, z])
        end = np.array([0.15 * cs, y + 0.15 * sn, z + 0.004])
        skewers.append(C.skewer(f'skewer_{k}', start, end))
        for i in range(5):
            s = -0.095 + i * 0.043 + rng.uniform(-0.003, 0.003)
            chunk = K.rounded_box(f'meat_{k}_{i}', (0.033, 0.03, 0.027), bevel=0.16, segments=2)
            K.subdivide(chunk, 2)
            chunk.location = tuple(rng.random(3) * 4)
            K.apply_transform(chunk)
            K.displace(chunk, 0.0035, 0.006, depth=3)
            lo, hi = K.bounds(chunk)
            chunk.location = tuple(-(lo + hi) / 2)
            K.apply_transform(chunk)
            K.transform(chunk, loc=(s * cs, y + s * sn, z), rot=(rng.uniform(-0.3, 0.3), rng.uniform(-0.2, 0.2), rz + rng.uniform(-0.3, 0.3)))
            meats.append(chunk)
    meat = K.join(meats, 'meat')
    K.assign(meat, meat_mat)
    uv_unwrap(meat)
    bake(meat, res=1024)
    steel = K.join(skewers, 'steel')
    sk = K.join([meat, steel], 'skewers')
    d.part(sk, 'skewers')
    rings = F.ring_tpl(r=0.013, tube=0.0018, flat=0.55)
    onion = K.scatter('sumac-onion', [lav, board.obj], rings, 10, K.disc_region(0.03, 0.1, 0.075), rng,
                      scale=(0.7, 1.1), embed=0.2, tilt=0.5,
                      colors=lambda r: (0.55, 0.12, 0.25) if r.random() > 0.4 else (0.75, 0.40, 0.50))
    K.assign(onion, K.solid('sumac_onion_mat', (1, 1, 1), rough=0.3, vcol=True))
    d.part(onion, 'sumac-onion')
    tomato = V.tomato('tomato', radius=0.03, slices=2)
    K.place(tomato, [lav, board.obj], -0.1, 0.075, rot=(0, 0, 0.4))
    d.part(tomato, 'tomato')
    p1 = P.sprig('par_a', 'parsley', size=1.1, seed=4)
    K.place(p1, [lav, board.obj, tomato], -0.05, 0.085, rot=(0, 0, 2.6))
    p2 = P.sprig('par_b', 'parsley', size=1.0, seed=7)
    K.place(p2, [lav, board.obj, onion], 0.07, 0.09, rot=(0, 0, -0.4))
    d.part(K.join([p1, p2], 'parsley'), 'parsley')


DISHES = {
    'plov': plov,
    'manti': manti,
    'lagman': lagman,
    'shashlik': shashlik,
}
