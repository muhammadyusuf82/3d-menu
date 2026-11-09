"""Hot dogs, shawarma wraps, loaded fries and chicken strips."""
import math

import bmesh
import numpy as np

import containers as C
import cooked as F
import kit as K
import produce as P
import sauces as S
import veg_parts as V
from lib import bake, disc_mesh, planar_uv, set_origin_bottom, smooth, uv_unwrap

KETCHUP = (0.40, 0.018, 0.008)
MUSTARD = (0.80, 0.50, 0.015)


def _sauce(name, color, rough=0.18):
    return K.solid(name, color, rough=rough, spec=0.55)


def _nestle(obj, targets, radius):
    """Lowers a horizontal cylinder (along X) into a groove until it touches the targets on both sides."""
    lo, hi = K.bounds(obj)
    cy = (lo[1] + hi[1]) / 2
    need = -1e9
    for x in np.linspace(lo[0] + 0.02, hi[0] - 0.02, 7):
        for dy in (-0.75, -0.5, 0.5, 0.75):
            hit = K.ray_down(targets, x, cy + dy * radius)
            if hit:
                bottom = hit[0].z + radius * math.sqrt(1 - dy * dy) - radius
                need = max(need, bottom)
    obj.location.z += need - lo[2]
    K.apply_transform(obj)
    return obj


def _onion_dice(name, targets, region, count, seed):
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.0045)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.0006, segments=1, affect='EDGES')
    tpl = K.template(bm)
    obj = K.scatter(name, targets, tpl, count, region, rng, scale=(0.7, 1.2), embed=0.3, tilt=1.4,
                    colors=lambda r: (0.92, 0.90, 0.84) if r.random() > 0.3 else (0.85, 0.86, 0.72))
    K.assign(obj, K.solid(name + '_mat', (1, 1, 1), rough=0.25, spec=0.5, vcol=True))
    set_origin_bottom(obj)
    return obj


def _along(x_half, y_half, cx=0.0, cy=0.0):
    return lambda rng: (cx + rng.uniform(-x_half, x_half), cy + rng.uniform(-y_half, y_half))


def _hotdog_base(d, sausage_style, seed):
    boat = d.base(C.paper_boat(size=(0.205, 0.095), height=0.034))
    bun = F.hotdog_bun()
    K.transform(bun, loc=(0, 0, boat.floor))
    d.part(bun, 'bun')
    s = F.sausage('sausage', length=0.185, radius=0.0135, style=sausage_style, seed=seed)
    lo, hi = K.bounds(s)
    K.transform(s, loc=(0, 0, K.bounds(bun)[1][2] + 0.02 - lo[2]))
    _nestle(s, [bun], 0.0135)
    return boat, bun, s


def classic_hotdog(d):
    boat, bun, s = _hotdog_base(d, 'grilled', 1)
    d.part(s, 'sausage')
    d.part(S.drizzle('ketchup', [s], S.zigzag(-0.078, 0.078, 0.0085, 9, steps=260), radius=0.0026,
                     mat=_sauce('ketchup_mat', KETCHUP)), 'ketchup')
    d.part(S.drizzle('mustard', [s, d.parts[-1]], S.zigzag(-0.074, 0.074, 0.008, 11, steps=260, y0=0.0006, seed=2),
                     radius=0.0021, mat=_sauce('mustard_mat', MUSTARD, rough=0.25)), 'mustard')
    tops = [s, d.parts[-1], d.parts[-2]]
    d.part(_onion_dice('white-onion', tops, _along(0.07, 0.009), 46, 3), 'white-onion')
    d.part(F.crumbles('relish', tops + [d.parts[-1]], _along(0.065, 0.008), 40, (0.20, 0.40, 0.06), size=0.0045,
                      rough=0.2, seed=5), 'relish')


def _jalapeno_rings(name, targets, count, seed):
    rng = np.random.default_rng(seed)
    res = 512
    x, y, r, t = K.grid(res)
    n = K.fbm(res, 12, seed, 3)
    col = K.lerp_color((0.62, 0.78, 0.38), (0.48, 0.66, 0.25), n)
    col[r > 0.86] = np.array([0.10, 0.30, 0.05])
    seeds = (K.vnoise(res, 40, seed + 1) > 0.78) & (r < 0.66) & (r > 0.5)
    col[seeds] = np.array([0.93, 0.90, 0.72])
    mat = K.textured(name + '_mat', np.clip(col, 0, 1).astype(np.float32), None, base_rough=0.3, spec=0.5)
    rings = []
    for i in range(count):
        ro = 0.011 * (0.9 + 0.2 * rng.random())
        prof = [(ro * 0.55, 0.0), (ro, 0.0), (ro, 0.003), (ro * 0.55, 0.003), (ro * 0.55, 0.0)]
        ring = K.revolve(f'{name}_{i}', prof, segments=40, uv='planar')
        K.assign(ring, mat)
        a = i / count * math.tau
        K.place(ring, targets, (i - (count - 1) / 2) * 0.034 + rng.uniform(-0.004, 0.004), rng.uniform(-0.005, 0.005),
                rot=(rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), a), sink=0.0012)
        rings.append(ring)
    obj = K.join(rings, name)
    smooth(obj, 40)
    return obj


def chili_hotdog(d):
    boat, bun, s = _hotdog_base(d, 'smoked', 2)
    d.part(s, 'beef-sausage')
    rng = np.random.default_rng(7)
    ph = rng.random(3) * math.tau
    inside = lambda x, y: abs(x) < 0.07 * (1 + 0.05 * math.sin(y * 300 + ph[0])) and \
        abs(y) < 0.019 * (1 + 0.25 * math.sin(x * 90 + ph[1]) + 0.15 * math.sin(x * 210 + ph[2]))
    chili = K.drape('chili', [s, bun], 0.09, inside, offset=0.003, res=150, thickness=0.004, smooth_iter=4)
    K.displace(chili, 0.003, 0.004, depth=2)
    mince = K.Shader('chili_mat', spec=0.5)
    n = mince.noise(120, 5, 0.65)
    bits = mince.voronoi(260, out='Distance')
    col = mince.ramp(n, [(0.3, (0.10, 0.018, 0.006)), (0.7, (0.30, 0.06, 0.015))])
    col = mince.mix(col, (0.45, 0.10, 0.03), mince.maprange(bits, 0.18, 0.05, 0, 0.6))
    mince.out(col, rough=mince.maprange(n, 0.3, 0.7, 0.15, 0.45), height=mince.math('SUBTRACT', n, bits), strength=0.8,
              distance=0.0012)
    K.assign(chili, mince.mat)
    smooth(chili, 60)
    uv_unwrap(chili)
    bake(chili, res=1024)
    beans = F.crumbles('beans', [chili], _along(0.06, 0.012), 22, (0.30, 0.05, 0.02), size=0.008, rough=0.25, seed=9,
                       squash=(1.3, 0.8, 0.7))
    d.part(K.join([chili, beans], 'chili'), 'chili')
    d.part(S.drizzle('cheese-sauce', [d.parts[-1]], S.zigzag(-0.07, 0.07, 0.011, 7, steps=240), radius=0.0036,
                     mat=_sauce('cheese_sauce_mat', (0.86, 0.36, 0.02), rough=0.2), wobble=0.3), 'cheese-sauce')
    tops = [d.parts[-1], d.parts[-2]]
    d.part(_jalapeno_rings('jalapeno', tops, 4, 3), 'jalapeno')
    d.part(F.crumbles('crispy', tops + [d.parts[-1]], _along(0.065, 0.011), 60, (0.62, 0.32, 0.07), size=0.007,
                      rough=0.5, seed=11, squash=(1.8, 0.4, 0.35)), 'crispy')
    cream = S.dollop('cream', 0.011, 0.012, K.solid('cream_mat', (0.92, 0.91, 0.86), rough=0.3), points=0, seed=2)
    K.place(cream, [d.parts[-1], d.parts[-2], d.parts[-3]], 0.022, 0.0, sink=0.003)
    d.part(cream, 'cream')


# ------------------------------------------------------------------ shawarma

def _shawarma(d, meat_id, sauce_id, onion_id, seed):
    board = d.base(C.wooden_board(length=0.36))
    rng = np.random.default_rng(seed)
    halves = []
    layout = [(-0.042, -0.055, 0.08), (0.045, -0.03, -0.18)]          # x, y, rotation (open ends towards -y)
    for k, (hx, hy, rz) in enumerate(layout):
        w = F.wrap_half(f'pita_{k}', seed=seed + k)
        K.transform(w, loc=(0, 0, board.floor))
        K.transform(w, rot=(0, 0, rz))
        K.transform(w, loc=(hx, hy, 0))
        halves.append((w, hx, hy, rz))
    d.part(K.join([h[0] for h in halves], 'pita'), 'pita')

    r_out, r_in = 0.034, 0.024
    groups = {meat_id: [], 'fries': [], 'pickles': [], 'tomato': [], onion_id: [], sauce_id: [], 'parsley': []}
    meat_mat = F.meat_mat('meat_mat', (0.62, 0.28, 0.07), (0.30, 0.10, 0.025)) if meat_id == 'chicken' else \
        F.meat_mat('meat_mat', (0.30, 0.09, 0.03), (0.12, 0.035, 0.012), char=0.3)
    fry_color, fry_rough, fry_normal = F.fries_texture(seed=seed)
    fry_mat = K.textured('fry_mat', fry_color, fry_rough, fry_normal, spec=0.45)
    pc, pr = V._pickle_texture(seed)
    pickle_mat = K.textured('pickle_mat', pc, pr, spec=0.5)
    tc, tr = V._tomato_texture(seed)
    tomato_mat = K.textured('tomato_mat', tc, tr, spec=0.5)
    onion_mat = K.solid('onion_mat', (0.85, 0.80, 0.86) if onion_id == 'onion' else (0.55, 0.12, 0.25), rough=0.25)
    sauce_mat = K.solid('wrap_sauce_mat', (0.93, 0.91, 0.84) if sauce_id == 'garlic' else (0.80, 0.68, 0.45), rough=0.3)
    herb = K.solid('parsley_mat', (0.06, 0.22, 0.03), rough=0.5)

    for (w, hx, hy, rz) in halves:
        cos, sin = math.cos(rz), math.sin(rz)

        def to_world(lx, ly, lz):
            return (hx + lx * cos - ly * sin, hy + lx * sin + ly * cos, board.floor + lz)

        def y_open(lz):
            return 0.012 + 0.45 * (lz - r_out)

        slots = []
        for _ in range(26):
            rr = r_in * 0.82 * math.sqrt(rng.random())
            a = rng.random() * math.tau
            slots.append((rr * math.cos(a), r_out + rr * math.sin(a)))
        kinds = [meat_id] * 9 + ['fries'] * 4 + ['pickles'] * 3 + ['tomato'] * 3 + [onion_id] * 3 + [sauce_id] * 3 + ['parsley']
        for (lx, lz), kind in zip(slots, kinds):
            ly = y_open(lz) - rng.uniform(0.002, 0.007)          # poke out of the cut a little
            if kind == meat_id:
                p = K.blob('m', 0.0075, scale=(1.0, 1.6, 0.75), lumps=0.35, subdiv=2, seed=int(rng.integers(0, 99)))
                K.transform(p, rot=tuple(rng.uniform(-0.6, 0.6, 3)))
            elif kind == 'fries':
                p = F.fry('f', rng.uniform(0.04, 0.06), 0.0075, rng)
                K.transform(p, rot=(math.pi / 2 + rng.uniform(-0.3, 0.3), 0, rng.uniform(-0.4, 0.4)))
                K.transform(p, loc=(0, 0.02, 0))
            elif kind == 'pickles':
                p = disc_mesh('p', 0.0085, 0.0028, cuts=4, radius_fn=lambda t: 1 + 0.04 * math.sin(t * 14), bevel=0.3)
                planar_uv(p)
                K.transform(p, rot=(math.pi / 2 + rng.uniform(-0.4, 0.4), rng.uniform(-0.5, 0.5), 0))
            elif kind == 'tomato':
                p = K.rounded_box('t', (0.011, 0.009, 0.008), bevel=0.25, segments=2)
                planar_uv(p)
                K.transform(p, rot=tuple(rng.uniform(-0.8, 0.8, 3)))
            elif kind == onion_id:
                arc = [(0.009 * math.cos(a), 0.009 * math.sin(a), 0) for a in np.linspace(0, 2.2, 14)]
                p = K.sweep('o', arc, 0.0012, sides=6)
                for v in p.data.vertices:
                    v.co.z *= 0.4
                K.transform(p, rot=(math.pi / 2 + rng.uniform(-0.5, 0.5), rng.uniform(0, 3), 0))
            elif kind == sauce_id:
                p = K.blob('s', 0.006, scale=(1.4, 1.0, 0.8), lumps=0.2, subdiv=2)
            else:
                p = K.blob('h', 0.004, scale=(1.4, 1.0, 0.25), lumps=0.3, subdiv=1)
            loc = to_world(lx, ly, lz)
            K.transform(p, rot=(0, 0, rz))
            K.transform(p, loc=loc)
            groups[kind].append(p)
    mats = {meat_id: meat_mat, 'fries': fry_mat, 'pickles': pickle_mat, 'tomato': tomato_mat, onion_id: onion_mat,
            sauce_id: sauce_mat, 'parsley': herb}
    order = [meat_id, 'fries', 'pickles', 'tomato', onion_id, sauce_id, 'parsley']
    for kind in order:
        obj = K.join(groups[kind], kind)
        K.assign(obj, mats[kind])
        smooth(obj, 60)
        if kind == meat_id:
            uv_unwrap(obj)
            bake(obj, res=1024)
        d.part(obj, kind)


def chicken_shawarma(d):
    _shawarma(d, 'chicken', 'garlic', 'onion', 4)


def beef_shawarma(d):
    _shawarma(d, 'beef', 'tahini', 'sumac', 8)


# ------------------------------------------------------------------ fries plates

def loaded_fries(d):
    boat = d.base(C.paper_boat(size=(0.18, 0.12), height=0.042))
    rng = np.random.default_rng(5)
    fries = F.fries_pile('fries', [boat.obj], 48, lambda r: (r.uniform(-0.055, 0.055), r.uniform(-0.03, 0.03)),
                         boat.floor + 0.03, rng, catcher_z=boat.floor)
    d.part(fries, 'fries')
    ph = rng.random(3) * math.tau
    inside = lambda x, y: math.hypot(x / 0.07, y / 0.045) < 0.85 + 0.15 * math.sin(math.atan2(y, x) * 5 + ph[0]) and \
        math.sin(x * 160 + ph[1]) * math.sin(y * 170 + ph[2]) > -0.55
    cheese = K.drape('cheddar-melt', [fries], 0.09, inside, offset=0.0012, res=140, thickness=0.0022, smooth_iter=6)
    K.assign(cheese, _sauce('cheddar_melt_mat', (0.86, 0.34, 0.02), rough=0.22))
    smooth(cheese, 60)
    d.part(cheese, 'cheddar-melt')
    tops = [fries, cheese]
    d.part(F.crumbles('bacon', tops, K.disc_region(0.055, ry=0.035), 34, (0.42, 0.07, 0.035), size=0.008, rough=0.4,
                      seed=7, squash=(1.3, 0.9, 0.5)), 'bacon')
    d.part(S.drizzle('ranch', tops + [d.parts[-1]], S.zigzag(-0.06, 0.06, 0.028, 6, steps=220, axis='x'), radius=0.0022,
                     mat=_sauce('ranch_mat', (0.88, 0.86, 0.76), rough=0.3)), 'ranch')
    rings = F.ring_tpl()
    onions = K.scatter('green-onion', tops + [d.parts[-1], d.parts[-2]], rings, 45, K.disc_region(0.055, ry=0.035),
                       np.random.default_rng(9), scale=(0.8, 1.3), embed=0.1, tilt=0.6,
                       colors=lambda r: (0.20, 0.50, 0.08) if r.random() > 0.3 else (0.55, 0.75, 0.35))
    K.assign(onions, K.solid('green_onion_mat', (1, 1, 1), rough=0.35, vcol=True))
    d.part(onions, 'green-onion')


def _ramekin_with(d, x, y, z, sauce_id, color, rough):
    v = C.ramekin(f'ramekin_{sauce_id}', radius=0.027, height=0.028)
    sauce = S.fill(v, v.rim - 0.004, sauce_id, _sauce(f'{sauce_id}_mat', color, rough), dome=0.0025)
    for o in (v.obj, sauce):
        K.transform(o, loc=(x, y, z))
    d.base(v)
    return sauce


def chicken_strips(d):
    plate = d.base(C.plate(radius=0.15, well=0.115))
    rng = np.random.default_rng(3)
    fries = F.fries_pile('fries', [plate.obj], 34, lambda r: (r.uniform(-0.075, -0.02), r.uniform(-0.045, 0.035)),
                         plate.floor + 0.03, rng, catcher_z=plate.floor)
    d.part(fries, 'fries')
    mat = F.breaded_mat('breading_mat')
    strips = []
    for i in range(5):
        st = F.breaded_piece(f'strip_{i}', size=(0.088 + 0.012 * rng.random(), 0.032, 0.022), seed=i + 3, mat=mat, res=512)
        # laid side by side, leaning on the fries at the back
        K.place(st, [plate.obj, fries], 0.035 + 0.004 * (i % 2), -0.072 + i * 0.025,
                rot=(0.0, 0.12 + 0.05 * (i % 3), 0.15 * (i - 2) + rng.uniform(-0.1, 0.1)))
        strips.append(st)
    d.part(K.join(strips, 'strips'), 'strips')
    bbq = _ramekin_with(d, 0.05, 0.072, plate.floor, 'bbq-sauce', (0.10, 0.018, 0.006), 0.12)
    ranch = _ramekin_with(d, -0.012, 0.082, plate.floor, 'ranch', (0.88, 0.86, 0.77), 0.3)
    d.part(bbq, 'bbq-sauce')
    d.part(ranch, 'ranch')


DISHES = {
    'classic-hotdog': classic_hotdog,
    'chili-hotdog': chili_hotdog,
    'chicken-shawarma': chicken_shawarma,
    'beef-shawarma': beef_shawarma,
    'loaded-fries': loaded_fries,
    'chicken-strips': chicken_strips,
}
