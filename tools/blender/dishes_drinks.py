"""Hot drinks, cold drinks and coffee."""
import math

import numpy as np

import containers as C
import kit as K
import produce as P
import sauces as S
from lib import bake, disc_mesh, uv_unwrap


# ------------------------------------------------------------------ painted tops

def crema_texture(res=1024, seed=1, art=None):
    """Espresso crema seen from above (planar UV, r = 1 at the cup wall); art: None | 'heart' | 'rosetta'."""
    x, y, r, t = K.grid(res)
    mottle = K.fbm(res, 5, seed, 4)
    # tiger-striping: soft darker flecks drawn out in rings (the crema swirls as it settles)
    swirl = K.vnoise(res, 18, seed + 2)
    flecks = K.smoothstep(0.55, 0.75, np.sin(r * 38 + swirl * 9) * 0.5 + 0.5) * K.smoothstep(0.45, 0.7, K.vnoise(res, 30, seed + 3))
    col = K.lerp_color((0.76, 0.52, 0.27), (0.60, 0.36, 0.16), np.clip(mottle * 0.9, 0, 1))
    col = col * (1 - 0.25 * flecks[..., None])
    ring = K.smoothstep(0.72, 0.99, r)
    col = col * (1 - ring[..., None] * 0.55) + np.array([0.33, 0.17, 0.06]) * ring[..., None] * 0.55
    rough = np.full((res, res), 0.32, np.float32)
    if art:
        milk = np.zeros((res, res), np.float32)
        if art == 'heart':
            hx, hy = x / 0.52, (y + 0.05) / 0.52
            f = (hx * hx + hy * hy - 1) ** 3 - hx * hx * hy ** 3
            milk = (f < 0).astype(np.float32)
            # the pour line cuts through the bottom of the heart
            milk = np.maximum(milk * (1 - ((np.abs(x) < 0.02) & (y < -0.25)) * 1.0), 0)
        else:   # rosetta: stacked leaves narrowing to the top, with a stem line
            for k in range(7):
                cy = -0.45 + k * 0.13
                w = 0.62 - k * 0.07
                band = ((y - cy) / 0.07) ** 2 + (x / w) ** 2 < 1
                inner = ((y - cy - 0.025) / 0.06) ** 2 + (x / (w * 0.92)) ** 2 < 1
                milk = np.maximum(milk, (band & ~inner).astype(np.float32))
            milk = np.maximum(milk, ((np.abs(x) < 0.012) & (y > -0.6) & (y < 0.5)).astype(np.float32))
            hx, hy = x / 0.16, (y - 0.48) / 0.16
            milk = np.maximum(milk, (((hx * hx + hy * hy - 1) ** 3 - hx * hx * hy ** 3) < 0).astype(np.float32))
        # soft edges and a little crema bleeding into the milk
        k = 3
        for _ in range(2):
            milk = (milk + np.roll(milk, k, 0) + np.roll(milk, -k, 0) + np.roll(milk, k, 1) + np.roll(milk, -k, 1)) / 5
        milk *= 1 - 0.12 * mottle
        col = col * (1 - milk[..., None]) + np.array([0.96, 0.93, 0.86]) * milk[..., None]
        rough = (0.32 - 0.04 * milk).astype(np.float32)
    micro = K.vnoise(res, 260, seed + 7)
    return np.clip(col, 0, 1).astype(np.float32), rough, K.height_to_normal((mottle * 0.2 + micro * 0.05).astype(np.float32), 0.3)


def _gradient_layer(vessel, z0, z1, name, bottom, top, rough=0.12):
    """A liquid layer whose colour blends from `bottom` to `top` with height (layered latte, iced drinks)."""
    s = K.Shader(name + '_mat', spec=0.5)
    zf = s.maprange(s.position('Z'), z0, z1, 0, 1)
    n = s.noise(80, 3, 0.5)
    fac = s.math('ADD', zf, s.math('MULTIPLY', s.math('SUBTRACT', n, 0.5), 0.15), clamp=True)
    col = s.ramp(fac, [(0.0, bottom), (1.0, top)])
    mat = s.out(col, rough=rough)
    obj = S.fill(vessel, z1, name, mat, z0=z0, meniscus=0)
    uv_unwrap(obj)
    bake(obj, res=512, normal=False, roughness=False)
    obj.data.materials[0].node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = rough
    return obj


def _ice(d, vessel, level, count=6, size=0.023, seed=3):
    """Ice cubes floating against the liquid surface (simulated with upward gravity under a lid)."""
    rng = np.random.default_rng(seed)
    cubes = []
    for i in range(count):
        c = P.ice_cube(f'ice_{i}', size * (0.9 + 0.2 * rng.random()), seed=seed + i)
        r = vessel.r_at(level) * 0.45
        a = i / count * math.tau + rng.random() * 0.5
        c.rotation_euler = tuple(rng.random(3) * 0.8)
        c.location = (r * math.cos(a) * (0.6 + 0.4 * (i % 2)), r * math.sin(a) * (0.6 + 0.4 * (i % 2)),
                      level - size * (1.2 + 1.3 * (i // 3)))
        K.apply_transform(c)
        cubes.append(c)
    lid = S.pool('lid', vessel.r_at(level) * 1.5, 0.002)
    lid.location.z = level + size * 0.28
    K.apply_transform(lid)
    K.settle(cubes, [vessel.obj, lid], frames=70, gravity=(0, 0, 9.81), friction=0.3)
    K.remove(lid)
    ice = K.join(cubes, 'ice')
    K.assign(ice, P.ice_material())
    return ice


def _rim_slice(slice_obj, vessel, angle=0.0):
    """Hooks a notched citrus slice on the glass rim (slice plane radial, notch over the wall)."""
    lo, hi = K.bounds(slice_obj)
    slice_obj.location.z -= (lo[2] + hi[2]) / 2
    K.apply_transform(slice_obj)
    radius = (hi[0] - lo[0]) / 2
    # disc in XY with the notch on +X -> stand it up in XZ with the notch pointing down
    K.transform(slice_obj, rot=(math.pi / 2, math.pi / 2, 0))
    rr = vessel.r_at(vessel.rim) + 0.001
    K.transform(slice_obj, loc=(rr, 0, vessel.rim + radius * 0.55), rot=(0, 0.12, 0))
    K.transform(slice_obj, rot=(0, 0, angle))
    return slice_obj


# ------------------------------------------------------------------ hot drinks

def black_tea(d):
    v = d.base(C.tea_glass())
    level = v.floor + (v.rim - v.floor) * 0.84
    tea = S.fill(v, level, 'black-tea', S.liquid_mat('tea', (0.30, 0.055, 0.008), rough=0.02))
    d.part(tea, 'black-tea')
    a = P.citrus_slice('lemon_a', radius=0.021, seed=1)
    K.transform(a, loc=(0.006, -0.004, level - 0.0018), rot=(0.06, -0.04, 0.4))
    b = P.citrus_slice('lemon_b', radius=0.021, seed=2)
    K.place(b, [v.obj], 0.056, -0.036, rot=(0, 0, 1.0))
    d.part(K.join([a, b], 'lemon'), 'lemon')


def green_tea(d):
    v = d.base(C.piala())
    level = v.floor + (v.rim - v.floor) * 0.78
    mat = K.solid('green-tea', (0.56, 0.46, 0.10), rough=0.02, alpha=0.62)
    d.part(S.fill(v, level, 'green-tea', mat), 'green-tea')
    m1 = P.sprig('mint_a', 'mint', size=0.75, seed=2)
    K.transform(m1, loc=(-0.012, -0.004, level - 0.001), rot=(0, 0, 0.5))
    m2 = P.sprig('mint_b', 'mint', size=0.8, seed=5)
    K.place(m2, [v.obj], 0.052, 0.035, rot=(0, 0, 2.4))
    d.part(K.join([m1, m2], 'mint'), 'mint')


def hot_chocolate(d):
    v = d.base(C.mug())
    level = v.rim - 0.008
    d.part(S.fill(v, level, 'hot-choc', S.liquid_mat('cocoa', (0.10, 0.028, 0.010), rough=0.22)), 'hot-choc')
    cream = S.piped_swirl('whipped', radius=0.03, height=0.032, turns=2.4, tube=0.009, z0=level - 0.004)
    d.part(cream, 'whipped')
    rng = np.random.default_rng(4)
    mallows = []
    for i in range(8):
        m = disc_mesh(f'mm_{i}', 0.0062 * (0.9 + 0.2 * rng.random()), 0.011, cuts=6, bevel=0.45, smooth_level=1)
        K.displace(m, 0.0006, 0.004)
        a = i / 8 * math.tau + rng.random() * 0.4
        rr = 0.02 + 0.012 * (i % 2)
        K.place(m, [cream, d.parts[0]], rr * math.cos(a), rr * math.sin(a),
                rot=tuple(rng.random(3) * 1.2), sink=0.002)
        mallows.append(m)
    mm = K.join(mallows, 'marshmallow')
    s = K.Shader('marshmallow_mat', spec=0.35)
    n = s.noise(220, 3, 0.6)
    toast = s.math('POWER', s.maprange(s.up(), 0.6, 1.0, 0, 1), 3)
    col = s.mix((0.97, 0.94, 0.90), (0.78, 0.55, 0.32), s.math('MULTIPLY', toast, 0.35))
    s.out(col, rough=0.72, height=n, strength=0.2, distance=0.0003)
    K.assign(mm, s.mat)
    uv_unwrap(mm)
    bake(mm, res=512)
    d.part(mm, 'marshmallow')


# ------------------------------------------------------------------ cold drinks

def _cold_glass(d, liquid_id, color, rough, ice_seed, straw_color):
    v = d.base(C.tumbler())
    d.base(C.straw('straw', base=(-0.012, 0.006, v.floor + 0.004), top=(-0.03, 0.022, v.rim + 0.07), color=straw_color))
    level = v.rim - 0.022
    d.part(S.fill(v, level, liquid_id, S.liquid_mat(liquid_id, color, rough=rough)), liquid_id)
    d.part(_ice(d, v, level, seed=ice_seed), 'ice')
    return v, level


def lemonade(d):
    v, level = _cold_glass(d, 'lemonade', (0.90, 0.80, 0.26), 0.05, 3, (0.95, 0.80, 0.10))
    rim = _rim_slice(P.citrus_slice('lemon_rim', radius=0.024, notch=True, seed=3), v, angle=-0.6)
    floating = P.citrus_slice('lemon_float', radius=0.022, seed=4)
    K.place(floating, [d.parts[0], d.parts[1]], 0.012, -0.012, rot=(0.25, 0.1, 0.3), sink=0.002)
    d.part(K.join([rim, floating], 'lemon'), 'lemon')
    mint = P.sprig('mint', 'mint', size=0.85, seed=7)
    K.place(mint, [d.parts[0], d.parts[1]], -0.004, 0.012, rot=(0.15, -0.35, 2.2), sink=0.003)
    d.part(mint, 'mint')


def peach_iced_tea(d):
    v, level = _cold_glass(d, 'peach-tea', (0.42, 0.085, 0.008), 0.02, 11, (0.95, 0.55, 0.35))
    skin, flesh = P.peach_materials()
    a = P.wedge('peach_a', radius=0.03, angle=0.8, skin=skin, flesh=flesh, seed=1)
    K.place(a, [d.parts[0], d.parts[1]], 0.014, -0.006, rot=(0.35, 0.1, 0.4), sink=0.005)
    b = P.wedge('peach_b', radius=0.028, angle=0.75, skin=skin, flesh=flesh, seed=2)
    K.place(b, [d.parts[0], d.parts[1]], -0.012, 0.012, rot=(-0.3, 0.2, 2.6), sink=0.004)
    d.part(K.join([a, b], 'peach-slice'), 'peach-slice')


def strawberry_milkshake(d):
    v = d.base(C.stemmed_glass('shake-glass', bowl_r=0.047, bowl_h=0.092, stem_h=0.05, foot_r=0.038))
    d.base(C.straw('straw', base=(0.01, -0.004, v.floor + 0.01), top=(0.03, -0.016, v.rim + 0.085), color=(0.9, 0.2, 0.35)))
    level = v.rim - 0.004
    shake = S.fill(v, level, 'milkshake', S.cream_mat('milkshake_mat', color=(0.86, 0.40, 0.46), rough=0.4))
    uv_unwrap(shake)
    bake(shake, res=512)
    d.part(shake, 'milkshake')
    cream = S.piped_swirl('whipped', radius=0.036, height=0.04, turns=2.6, tube=0.0105, z0=level - 0.003)
    d.part(cream, 'whipped')
    berry = P.strawberry('strawberry_top', seed=3)
    K.place(berry, [cream], 0.0, 0.0, rot=(0.0, 0.25, 0.0), sink=0.006)
    half = P.strawberry('strawberry_half', half=True, seed=5, calyx=True)
    K.place(half, [cream, shake], 0.026, -0.012, rot=(0.0, -0.9, -0.5), sink=0.004)
    d.part(K.join([berry, half], 'strawberry'), 'strawberry')


# ------------------------------------------------------------------ coffee

def espresso(d):
    v = d.base(C.cup('cup', r_bottom=0.02, r_top=0.031, height=0.046, saucer=0.058))
    top = v.floor + (v.rim - v.floor) * 0.78
    d.part(S.fill(v, top - 0.002, 'espresso', S.liquid_mat('espresso_mat', (0.018, 0.007, 0.003), rough=0.08)), 'espresso')
    col, rough, normal = crema_texture(seed=2)
    crema = S.fill(v, top, 'crema', K.textured('crema_mat', col, rough, normal, spec=0.45), z0=top - 0.002, meniscus=0.0008)
    d.part(crema, 'crema')


def cappuccino(d):
    v = d.base(C.cup())
    h = v.rim - v.floor
    d.part(S.fill(v, v.floor + h * 0.32, 'espresso', S.liquid_mat('espresso_mat', (0.03, 0.011, 0.004), rough=0.1),
                  meniscus=0), 'espresso')
    d.part(_gradient_layer(v, v.floor + h * 0.32, v.floor + h * 0.8, 'milk', (0.36, 0.20, 0.09), (0.86, 0.78, 0.64)), 'milk')
    col, rough, normal = crema_texture(seed=4, art='heart')
    foam = S.fill(v, v.rim - 0.002, 'foam', K.textured('foam_mat', col, rough, normal, spec=0.45),
                  z0=v.floor + h * 0.8, meniscus=0, dome=0.006)
    d.part(foam, 'foam')
    rr = v.r_at(v.rim) * 0.95
    d.part(S.dust('cocoa', [foam], lambda rng: _ring_point(rng, rr * 0.62, rr * 0.95), 380, size=0.0006, seed=3), 'cocoa')


def _ring_point(rng, r0, r1):
    r = math.sqrt(rng.uniform(r0 * r0, r1 * r1))
    a = rng.random() * math.tau
    return r * math.cos(a), r * math.sin(a)


def caramel_latte(d):
    glass = C.tumbler('latte-glass', r_bottom=0.03, r_top=0.036, height=0.13, base=0.01)
    handle = K.sweep('latte-handle', [(0.036 + 0.022 * math.sin(a), 0, 0.065 + 0.04 * math.cos(a))
                                      for a in np.linspace(0.08, math.pi - 0.08, 28)], 0.0042, sides=12)
    K.assign(handle, glass.obj.data.materials[0])
    v = d.base(glass)
    d.base(handle)
    h = v.rim - v.floor
    d.part(_gradient_layer(v, v.floor + 0.0003, v.floor + h * 0.55, 'milk', (0.88, 0.82, 0.70), (0.80, 0.66, 0.46)), 'milk')
    d.part(_gradient_layer(v, v.floor + h * 0.55, v.floor + h * 0.76, 'espresso', (0.42, 0.22, 0.09), (0.10, 0.04, 0.015),
                           rough=0.08), 'espresso')
    foam = S.fill(v, v.rim - 0.003, 'foam', S.cream_mat('foam_mat', color=(0.95, 0.92, 0.85), rough=0.5),
                  z0=v.floor + h * 0.76, meniscus=0, dome=0.009)
    uv_unwrap(foam)
    bake(foam, res=512)
    d.part(foam, 'foam')
    caramel = K.solid('caramel_mat', (0.55, 0.20, 0.03), rough=0.08, spec=0.6)
    path = S.zigzag(-0.026, 0.026, 0.024, 7, steps=240)
    d.part(S.drizzle('caramel', [foam], path, radius=0.0017, mat=caramel, seed=2), 'caramel')


DISHES = {
    'black-tea': black_tea,
    'green-tea': green_tea,
    'hot-chocolate': hot_chocolate,
    'lemonade': lemonade,
    'peach-iced-tea': peach_iced_tea,
    'strawberry-milkshake': strawberry_milkshake,
    'espresso': espresso,
    'cappuccino': cappuccino,
    'caramel-latte': caramel_latte,
}
