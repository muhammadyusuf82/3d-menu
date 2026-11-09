"""Kids menu: mini burger, nuggets, mac & cheese, mini pancakes."""
import math

import bmesh
import numpy as np

import burger_parts as BP
import containers as C
import cooked as F
import kit as K
import produce as P
import sauces as S
from lib import bake, disc_mesh, set_origin_bottom, smooth, uv_unwrap

KIDS_PLATE = (0.28, 0.55, 0.82)       # sky-blue glaze (reads pastel under the web viewer's lighting)
KETCHUP = (0.40, 0.018, 0.008)


def kids_burger(d):
    plate = d.base(C.plate(radius=0.13, well=0.095, color=KIDS_PLATE))
    rng = np.random.default_rng(2)
    fries = F.fries_pile('kids-fries', [plate.obj], 26, lambda r: (r.uniform(-0.07, -0.02), r.uniform(-0.04, 0.04)),
                         plate.floor + 0.03, rng, length=(0.04, 0.065), catcher_z=plate.floor)
    d.part(fries, 'kids-fries')
    bottom, top = BP.bun_halves()
    patty = BP.patty('kids-patty', radius=0.04, height=0.013)
    cheese = BP.cheese('kids-cheese', size=0.075, patty_r=0.04, patty_h=0.013)
    for o in (bottom, top):
        K.transform(o, scale=0.74)
        set_origin_bottom(o)
    # same rule as build_burger.assemble: origins sit at each layer's bottom (cheese: under its flat middle)
    z = plate.floor
    for obj, gap in ((bottom, 0.0), (patty, -0.001), (cheese, 0.001), (top, -0.0012)):
        obj.location = (0.045, 0.0, z + gap)
        z = obj.location.z + obj.get('stack_h', obj.dimensions.z)
    d.part(bottom, 'kids-bun-bottom')
    d.part(patty, 'kids-patty', budget=8000)
    d.part(cheese, 'kids-cheese', budget=7000)
    d.part(top, 'kids-bun-top')


def kids_nuggets(d):
    plate = d.base(C.plate(radius=0.13, well=0.095, color=(0.95, 0.66, 0.18)))
    rng = np.random.default_rng(4)
    fries = F.fries_pile('kids-fries', [plate.obj], 24, lambda r: (r.uniform(-0.07, -0.025), r.uniform(-0.045, 0.03)),
                         plate.floor + 0.03, rng, length=(0.04, 0.065), catcher_z=plate.floor)
    d.part(fries, 'kids-fries')
    mat = F.breaded_mat('nugget_mat', scale=1.3)
    nuggets = []
    spots = [(0.02, -0.045), (0.055, -0.03), (0.035, -0.005), (0.07, 0.0), (0.015, 0.025), (0.05, 0.03)]
    for i, (x, y) in enumerate(spots):
        n = F.breaded_piece(f'nug_{i}', size=(0.042, 0.032, 0.02), seed=20 + i, crag=0.22, mat=mat, res=512)
        K.place(n, [plate.obj, fries], x, y, rot=(rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.random() * math.tau))
        nuggets.append(n)
    d.part(K.join(nuggets, 'nuggets'), 'nuggets')
    v = C.ramekin('ramekin', radius=0.026, height=0.027)
    ketchup = S.fill(v, v.rim - 0.004, 'ketchup', K.solid('ketchup_mat', KETCHUP, rough=0.15, spec=0.55), dome=0.002)
    for o in (v.obj, ketchup):
        K.transform(o, loc=(-0.02, 0.07, plate.floor))
    d.base(v)
    d.part(ketchup, 'ketchup')


def _elbow_tpl():
    pts = [(0.0075 * math.cos(a), 0.0075 * math.sin(a), 0.0) for a in np.linspace(-1.1, 1.1, 14)]
    obj = K.sweep('elbow', pts, 0.0034, sides=10, profile=lambda q: 1 + 0.06 * math.cos(q * 10))  # ridged pasta
    tpl = K.template(obj)
    K.remove(obj)
    return tpl


def mac_cheese(d):
    bowl = d.base(C.bowl('bowl', radius=0.075, depth=0.05, foot=0.035, color=(0.93, 0.92, 0.885)))
    rng = np.random.default_rng(6)
    level = bowl.rim - 0.008
    sauce = S.fill(bowl, level - 0.004, 'mac-sauce', K.solid('mac_sauce_mat', (0.82, 0.32, 0.025), rough=0.22, spec=0.5),
                   meniscus=0, dome=0.012)
    K.displace(sauce, 0.003, 0.01)
    d.part(sauce, 'mac-sauce')
    mac = K.scatter('macaroni', [sauce], _elbow_tpl(), 95, K.disc_region(bowl.r_at(level) * 0.85), rng, scale=(0.9, 1.1),
                    embed=0.55, tilt=2.5, align=0.3,
                    colors=lambda r: (0.88, 0.48, 0.07) if r.random() > 0.35 else (0.92, 0.58, 0.14))
    K.assign(mac, K.solid('macaroni_mat', (1, 1, 1), rough=0.3, spec=0.5, vcol=True))
    d.part(mac, 'macaroni')
    d.parts[0], d.parts[1] = d.parts[1], d.parts[0]          # pasta below its sauce in the explode order
    d.part(F.crumbles('breadcrumbs', [sauce, mac], K.disc_region(bowl.r_at(level) * 0.8), 220, (0.55, 0.28, 0.06),
                      size=0.003, rough=0.75, seed=3), 'breadcrumbs')


def mini_pancakes(d):
    plate = d.base(C.plate(radius=0.13, well=0.095, color=(0.92, 0.55, 0.62)))
    rng = np.random.default_rng(8)
    pan = disc_mesh('pancake', 0.048, 0.011, cuts=9, radius_fn=lambda t: 1 + 0.025 * math.sin(3 * t) + 0.012 * math.sin(7 * t),
                    bevel=0.5, smooth_level=1)
    for v in pan.data.vertices:
        r = math.hypot(v.co.x, v.co.y) / 0.048
        v.co.z += 0.0025 * (1 - r * r) * (1 if v.co.z > 0 else 0.3)       # fluffy dome
    s = K.Shader('pancake_mat', spec=0.4)
    n = s.noise(35, 6, 0.6)
    lace = s.voronoi(90, out='Distance')
    top = s.maprange(s.math('ABSOLUTE', s.up()), 0.6, 0.95, 0, 1)
    brown = s.ramp(s.math('ADD', n, s.math('MULTIPLY', lace, 0.6)), [(0.3, (0.32, 0.12, 0.025)), (0.65, (0.62, 0.30, 0.07)),
                                                                      (0.9, (0.80, 0.50, 0.16))])
    col = s.mix((0.88, 0.70, 0.42), brown, top)
    s.out(col, rough=0.6, height=s.math('ADD', n, lace), strength=0.3, distance=0.0006)
    K.assign(pan, s.mat)
    smooth(pan, 50)
    uv_unwrap(pan)
    bake(pan, res=1024)
    set_origin_bottom(pan)
    pan.location = (0, 0, 0)
    K.apply_transform(pan)
    tpl = K.template(pan)
    lo, hi = K.bounds(pan)
    h = hi[2] - lo[2]
    mats = []
    for i in range(4):
        mats.append(K.frame((rng.uniform(-0.003, 0.003), rng.uniform(-0.003, 0.003), plate.floor + i * (h - 0.0012)),
                            (0, 0, 1), rng.random() * math.tau, (1 - 0.02 * i,) * 3, (rng.uniform(-0.03, 0.03), 0)))
    stack = K.instances('pancakes', tpl, mats)
    K.assign(stack, pan.data.materials[0])
    smooth(stack, 50)
    K.remove(pan)
    d.part(stack, 'pancakes')
    butter = K.rounded_box('butter-pat', (0.02, 0.02, 0.011), bevel=0.25, segments=3)
    K.subdivide(butter, 1)
    for v in butter.data.vertices:        # softening at the base
        if v.co.z < 0:
            v.co.x *= 1.15
            v.co.y *= 1.15
    K.assign(butter, K.solid('butter_mat', (0.95, 0.80, 0.35), rough=0.3, spec=0.5))
    K.place(butter, [stack], 0.004, -0.002, rot=(0, 0, 0.5), sink=0.002)
    d.part(butter, 'butter-pat')
    ph = rng.random(3) * math.tau
    inside = lambda x, y: math.hypot(x, y) < 0.044 * (1 + 0.2 * max(0.0, math.sin(math.atan2(y, x) * 5 + ph[0])) ** 3
                                                     + 0.35 * max(0.0, math.sin(math.atan2(y, x) * 3 + ph[1])) ** 8)
    syrup = K.drape('syrup', [stack, butter], 0.07, inside, offset=0.0009, res=140, thickness=0.0016, smooth_iter=5,
                    floor=plate.floor)
    K.assign(syrup, K.solid('syrup_mat', (0.30, 0.07, 0.008), rough=0.04, spec=0.6, alpha=0.88))
    smooth(syrup, 70)
    d.part(syrup, 'syrup')
    berries = []
    for i, (x, y, half) in enumerate([(0.06, -0.035, True), (0.065, 0.02, False), (-0.055, 0.045, True),
                                      (-0.06, -0.03, False), (0.0, 0.0, True)]):
        b = P.strawberry(f'sb{i}', half=half, seed=i + 2)
        targets = [plate.obj] if i < 4 else [stack, syrup, butter]
        K.place(b, targets, x if i < 4 else 0.022, y if i < 4 else 0.018, rot=(0, 0.3 if not half else 0, rng.random() * math.tau),
                sink=0.0 if i < 4 else 0.003)
        berries.append(b)
    d.part(K.join(berries, 'strawberry'), 'strawberry')


DISHES = {
    'kids-burger': kids_burger,
    'kids-nuggets': kids_nuggets,
    'mac-cheese': mac_cheese,
    'mini-pancakes': mini_pancakes,
}
