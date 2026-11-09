"""Tiramisu, cheesecake, ice-cream sundae, chocolate lava cake."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import containers as C
import cooked as F
import kit as K
import produce as P
import sauces as S
from lib import bake, disc_mesh, new_object, set_origin_bottom, smooth, uv_unwrap

CHOC = (0.035, 0.012, 0.005)


def _layer(name, size, z0, h, mat, seed, wobble=0.0012, res=1024):
    """A rectangular dessert layer with softly irregular cut sides (sliced with a knife, not machined)."""
    obj = K.rounded_box(name, (size, size, h), bevel=0.08, segments=2)
    K.subdivide(obj, 2)
    obj.location = (seed * 1.7, seed * 0.9, 0)
    K.apply_transform(obj)
    K.displace(obj, wobble, 0.01, depth=2)
    lo, hi = K.bounds(obj)
    obj.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, z0 - lo[2])
    K.apply_transform(obj)
    K.assign(obj, mat)
    smooth(obj, 50)
    uv_unwrap(obj)
    bake(obj, res=res)
    return obj


def _sponge_mat(name, soak=1.0):
    s = K.Shader(name, spec=0.35)
    pores = s.voronoi(420, out='Distance')
    n = s.noise(40, 5, 0.6)
    col = s.ramp(n, [(0.3, (0.42 - 0.2 * soak, 0.20 - 0.1 * soak, 0.06 - 0.03 * soak)), (0.7, (0.62 - 0.2 * soak, 0.36 - 0.12 * soak, 0.12 - 0.05 * soak))])
    col = s.mix(col, (0.5, 0.4, 0.3), s.maprange(pores, 0.12, 0.0, 0, 0.6), 'MULTIPLY')
    return s.out(col, rough=0.75, height=pores, strength=0.6, distance=0.0008)


def tiramisu(d):
    plate = d.base(C.plate(radius=0.11, well=0.075))
    size = 0.078
    z = plate.floor
    layers = [('sponge', 0.016, _sponge_mat('sponge_mat', 1.0)),
              ('mascarpone', 0.015, S.cream_mat('masc_mat', color=(0.95, 0.90, 0.74), rough=0.55)),
              ('sponge-2', 0.014, _sponge_mat('sponge2_mat', 0.9)),
              ('mascarpone-2', 0.014, S.cream_mat('masc2_mat', color=(0.95, 0.90, 0.74), rough=0.55))]
    for i, (name, h, mat) in enumerate(layers):
        obj = _layer(name, size * (1 - 0.01 * i), z, h, mat, i)
        d.part(obj, name)
        z += h - 0.0006
    s = K.Shader('cocoa_mat', spec=0.2)
    n = s.noise(600, 3, 0.6)
    s.out(s.ramp(n, [(0.3, (0.07, 0.025, 0.01)), (0.7, (0.16, 0.06, 0.025))]), rough=0.95, height=n, strength=0.3, distance=0.0003)
    cocoa = _layer('cocoa', size * 0.97, z, 0.0018, s.mat, 7, wobble=0.0003, res=512)
    d.part(cocoa, 'cocoa')
    rng = np.random.default_rng(3)
    curls = []
    for i in range(9):
        pts = [(0.004 * math.cos(a), 0.004 * math.sin(a), a * 0.0012) for a in np.linspace(0, 2.6 * math.pi, 28)]
        c = K.sweep(f'curl_{i}', pts, 0.0014, sides=6, profile=lambda q: 1.0 if abs(math.cos(q)) > 0.6 else 0.3)
        K.transform(c, rot=(math.pi / 2, 0, 0))
        K.place(c, [cocoa] + curls, rng.uniform(-0.025, 0.025), rng.uniform(-0.025, 0.025),
                rot=(0, rng.uniform(-0.3, 0.3), rng.random() * math.tau), sink=0.001)
        curls.append(c)
    shav = K.join(curls, 'choc-shavings')
    K.assign(shav, K.solid('shaving_mat', CHOC, rough=0.35, spec=0.5))
    d.part(shav, 'choc-shavings')


def _wedge_cake(name, radius, z0, h, angle, mat_outer, mat_cut):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=96, radius1=radius, radius2=radius, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > h * 0.5], cuts=4)
    for a, keep in ((angle / 2, 'inner'), (-angle / 2, 'outer')):
        n = Vector((-math.sin(a), math.cos(a), 0))
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=n,
                               clear_outer=(keep == 'inner'), clear_inner=(keep == 'outer'))
    filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    tri = bmesh.ops.triangulate(bm, faces=filled['faces'])
    for f in tri['faces']:
        f.material_index = 1
    obj = new_object(name, bm)
    K.assign(obj, mat_outer)
    obj.data.materials.append(mat_cut)
    smooth(obj, 35)
    uv_unwrap(obj)
    bake(obj, res=1024)
    obj.location.z = z0
    K.apply_transform(obj)
    return obj


def cheesecake(d):
    plate = d.base(C.plate(radius=0.11, well=0.075))
    R, ang = 0.105, 0.85
    crumb = K.Shader('biscuit_mat', spec=0.3)
    n = crumb.noise(300, 5, 0.6)
    crumb.out(crumb.ramp(n, [(0.3, (0.40, 0.20, 0.06)), (0.7, (0.68, 0.42, 0.16))]), rough=0.8, height=n, strength=0.8,
              distance=0.001)
    crumb2 = K.Shader('biscuit_cut', spec=0.3)
    n2 = crumb2.noise(300, 5, 0.6)
    crumb2.out(crumb2.ramp(n2, [(0.3, (0.40, 0.20, 0.06)), (0.7, (0.68, 0.42, 0.16))]), rough=0.8, height=n2, strength=0.8,
               distance=0.001)
    body_out = K.Shader('cc_outer', spec=0.4)
    t = body_out.noise(30, 5, 0.6)
    top = body_out.maprange(body_out.up(), 0.5, 0.95, 0, 1)
    col = body_out.mix((0.92, 0.76, 0.46), (0.62, 0.36, 0.12), body_out.math('MULTIPLY', top, body_out.maprange(t, 0.3, 0.7, 0.5, 1)))
    body_out.out(col, rough=0.5, height=t, strength=0.2, distance=0.0005)
    body_cut = K.Shader('cc_cut', spec=0.4)
    t2 = body_cut.noise(200, 3, 0.5)
    body_cut.out(body_cut.ramp(t2, [(0.3, (0.92, 0.84, 0.62)), (0.7, (0.97, 0.91, 0.74))]), rough=0.45, height=t2,
                 strength=0.15, distance=0.0003)
    rot = (0, 0, -0.6)
    base = _wedge_cake('biscuit', R, plate.floor, 0.009, ang, crumb.mat, crumb2.mat)
    body = _wedge_cake('cheesecake', R, plate.floor + 0.0088, 0.042, ang, body_out.mat, body_cut.mat)
    for o in (base, body):
        lo, hi = K.bounds(body)
        K.transform(o, loc=(-(lo[0] + hi[0]) / 2 + 0.01, -(lo[1] + hi[1]) / 2, 0))
        K.transform(o, rot=rot)
    d.part(base, 'biscuit')
    d.part(body, 'cheesecake')
    bl, bh = K.bounds(body)
    top_z = bh[2]
    rng = np.random.default_rng(4)
    ph = rng.random(3) * math.tau

    def inside(x, y):
        hit = K.ray_down([body], x, y)
        if hit and hit[0].z > top_z - 0.003:
            return math.sin(x * 120 + ph[0]) * math.sin(y * 110 + ph[1]) > -0.85
        # drips: narrow tongues just past the round back edge
        return hit is not None and math.sin(math.atan2(y, x) * 11 + ph[2]) > 0.7
    sauce = K.drape('berry-sauce', [body], 0.12, inside, offset=0.0009, res=170, thickness=0.0022, smooth_iter=4)
    K.assign(sauce, K.solid('berry_mat', (0.36, 0.008, 0.02), rough=0.06, spec=0.6))
    smooth(sauce, 60)
    d.part(sauce, 'berry-sauce')
    berries = []
    cx, cy = (bl[0] + bh[0]) / 2, (bl[1] + bh[1]) / 2
    for i, (dx, dy, half) in enumerate([(-0.012, 0.004, True), (0.012, -0.006, True)]):
        b = P.strawberry(f'cs{i}', half=half, seed=i + 7)
        K.place(b, [sauce, body], cx + dx, cy + dy, rot=(0, 0, rng.random() * math.tau), sink=0.002)
        berries.append(b)
    whole = P.strawberry('cs_w', seed=12)
    K.place(whole, [plate.obj], cx + 0.05, cy - 0.045, rot=(0, 1.3, 0.4))
    berries.append(whole)
    d.part(K.join(berries, 'strawberry'), 'strawberry')


def sundae(d):
    g = d.base(C.stemmed_glass('sundae-glass', bowl_r=0.05, bowl_h=0.07, stem_h=0.055, foot_r=0.042))
    choc = S.scoop('choc-scoop', 0.031, color=(0.17, 0.065, 0.025), seed=1)
    van = S.scoop('vanilla-scoop', 0.03, color=(0.95, 0.86, 0.62), seed=2, chunks=(0.2, 0.15, 0.1))
    K.place(choc, [g.obj], -0.004, 0.003, sink=-0.0)
    lo, hi = K.bounds(choc)
    # the first scoop sits down in the glass; nestle until it meets the wall
    z = g.floor + 0.01
    for zz in np.linspace(g.rim, g.floor, 80):
        if g.r_at(zz + 0.012) < 0.029:
            z = zz
            break
    choc.location.z += z - lo[2]
    K.apply_transform(choc)
    d.part(choc, 'choc-scoop')
    K.place(van, [choc, g.obj], 0.004, -0.002, sink=0.012)
    d.part(van, 'vanilla-scoop')
    cream = S.piped_swirl('whipped', radius=0.024, height=0.03, turns=2.3, tube=0.0085)
    K.place(cream, [van], 0.004, -0.002, sink=0.008)
    d.part(cream, 'whipped')
    path = S.spiral(0.03, 3.2, steps=260, cx=0.002, cy=0.0)
    syrup = S.drizzle('choc-syrup', [cream, van, choc], path, radius=0.0019, mat=K.solid('choc_syrup_mat', CHOC, rough=0.06, spec=0.6))
    d.part(syrup, 'choc-syrup')
    cherry = P.cherry('cherry', radius=0.011, color=(0.55, 0.0, 0.02))
    K.place(cherry, [cream], 0.004, -0.002, sink=0.007)
    d.part(cherry, 'cherry')


def lava_cake(d):
    plate = d.base(C.plate(radius=0.12, well=0.085))
    rng = np.random.default_rng(6)
    prof = [(0.0, 0.0), (0.038, 0.0), (0.040, 0.004)] + [(0.040 - 0.006 * s, 0.004 + 0.04 * s) for s in np.linspace(0.1, 1, 8)] + \
           [(0.031, 0.046), (0.018, 0.048), (0.0, 0.0485)]
    cake = K.revolve('lava_body', K.lathe_profile(prof, steps=2), segments=80, uv='wrap')
    K.displace(cake, 0.0012, 0.006, depth=3)
    s = K.Shader('lava_mat', spec=0.35)
    n = s.noise(45, 6, 0.65)
    crack = s.voronoi(120, out='Distance', feature='DISTANCE_TO_EDGE')
    col = s.ramp(n, [(0.3, (0.025, 0.008, 0.003)), (0.7, (0.07, 0.025, 0.01))])
    col = s.mix(col, (0.012, 0.004, 0.002), s.maprange(crack, 0.03, 0.0, 0, 0.8))
    s.out(col, rough=0.7, height=s.math('ADD', n, s.math('MULTIPLY', crack, 2.0)), strength=0.7, distance=0.001)
    K.assign(cake, s.mat)
    smooth(cake, 60)
    uv_unwrap(cake)
    bake(cake, res=1024)
    K.transform(cake, loc=(-0.012, 0.0, plate.floor))
    # molten centre spilling out of a cut in the front onto the plate
    ooze = S.pool('ooze', 0.045, height=0.004, mat=None, seed=3, lobes=0.18, center=(0.02, -0.022))
    K.transform(ooze, loc=(0, 0, plate.floor))
    spill = K.blob('spill', 0.018, scale=(1.2, 0.8, 1.0), lumps=0.15, subdiv=3, seed=2)
    K.transform(spill, loc=(0.012, -0.024, plate.floor + 0.016))
    ooze_mat = K.solid('molten_mat', (0.05, 0.016, 0.006), rough=0.05, spec=0.6)
    for o in (ooze, spill):
        K.assign(o, ooze_mat)
        smooth(o, 70)
    lava = K.join([cake, ooze, spill], 'lava')
    d.part(lava, 'lava')
    scoop = S.scoop('lava-scoop', 0.024, color=(0.95, 0.87, 0.64), seed=5, chunks=(0.2, 0.15, 0.1))
    K.place(scoop, [plate.obj], 0.05, 0.035)
    d.part(scoop, 'lava-scoop')
    rasp = []
    for i, (x, y) in enumerate([(0.06, -0.01), (0.05, -0.045), (0.07, -0.03), (-0.045, 0.05)]):
        r = P.raspberry(f'r{i}', seed=i)
        K.place(r, [plate.obj, d.parts[0]], x, y, rot=(rng.uniform(0, 1.2), 0, rng.random() * math.tau))
        rasp.append(r)
    d.part(K.join(rasp, 'raspberry'), 'raspberry')
    d.part(S.dust('cocoa', [plate.obj, d.parts[0]], K.disc_region(0.08, -0.01, 0.01), 900, color=(0.10, 0.035, 0.014),
                  size=0.0007, seed=4), 'cocoa')


DISHES = {
    'tiramisu': tiramisu,
    'cheesecake': cheesecake,
    'sundae': sundae,
    'lava-cake': lava_cake,
}
