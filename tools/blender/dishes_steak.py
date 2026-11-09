"""Ribeye, filet mignon and striploin with fries."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import burger_parts as BP
import containers as C
import cooked as F
import kit as K
import produce as P
import sauces as S
import veg_parts as V
from lib import bake, disc_mesh, image_from_array, new_object, planar_uv, set_origin_bottom, smooth, uv_unwrap, link


def _steak_crust(name, grill=True, fat_side=None):
    """Seared crust with crosshatch grill marks on top and bottom, darker caramelised edges, optional fat cap."""
    s = K.Shader(name, spec=0.45)
    n = s.noise(40, 8, 0.65)
    fine = s.noise(260, 3, 0.55)
    col = s.ramp(n, [(0.25, (0.022, 0.008, 0.003)), (0.55, (0.10, 0.032, 0.010)), (0.82, (0.22, 0.075, 0.02))])
    flat = s.maprange(s.math('ABSOLUTE', s.up()), 0.75, 0.95, 0, 1)
    if grill:
        a = s.wave(26, distortion=1.2, detail=1, bands='DIAGONAL')
        mapping = s.nt.nodes.new('ShaderNodeMapping')
        mapping.inputs['Rotation'].default_value = (0, 0, math.radians(90))
        link(s.nt, s.coord, mapping.inputs['Vector'])
        b = s.wave(26, vec=mapping.outputs['Vector'], distortion=1.2, detail=1, bands='DIAGONAL')
        marks = s.math('MAXIMUM', s.maprange(a, 0.1, 0.0, 0, 1), s.maprange(b, 0.1, 0.0, 0, 1))
        marks = s.math('MULTIPLY', marks, flat)
        col = s.mix(col, (0.018, 0.008, 0.004), s.math('MULTIPLY', marks, 0.9))
    else:
        marks = None
    if fat_side is not None:
        # a rim of rendered fat along one side (+Y), golden and glossy
        fat = s.maprange(s.position('Y'), fat_side - 0.012, fat_side, 0, 1)
        fat = s.math('MULTIPLY', fat, s.math('SUBTRACT', 1, flat))
        col = s.mix(col, (0.62, 0.36, 0.12), s.math('MULTIPLY', fat, 0.85))
    rough = s.maprange(n, 0.3, 0.7, 0.32, 0.6)
    height = s.math('ADD', n, s.math('MULTIPLY', fine, 0.4))
    return s.out(col, rough=rough, height=height, strength=0.6, distance=0.0012)


def _slab(name, length, width, height, seed=0, outline=None):
    """A steak-shaped slab: irregular rounded outline, domed, with seared lumpy surface."""
    rng = np.random.default_rng(seed)
    ph = rng.random(4) * math.tau
    fn = outline or (lambda t: 1 + 0.06 * math.sin(2 * t + ph[0]) + 0.04 * math.sin(3 * t + ph[1]) + 0.02 * math.sin(7 * t + ph[2]))
    obj = disc_mesh(name, 0.5, height, cuts=18, radius_fn=fn, bevel=0.75, smooth_level=1)
    for v in obj.data.vertices:
        v.co.x *= length
        v.co.y *= width
        r = math.hypot(v.co.x / (length / 2), v.co.y / (width / 2))
        if v.co.z > 0:
            v.co.z += height * 0.12 * (1 - min(1, r) ** 2)
    obj.location = tuple(rng.random(3) * 3)
    K.apply_transform(obj)
    K.displace(obj, height * 0.06, 0.012, depth=2)
    lo, hi = K.bounds(obj)
    obj.location = tuple(-(lo + hi) / 2)
    K.apply_transform(obj)
    return obj


def _mash(name='mashed', radius=0.042, height=0.034, seed=0):
    prof = [(radius * s, height * (1 - s ** 2.4) ** 0.7) for s in np.linspace(0, 1, 24)]
    obj = K.revolve(name, [(0.0, 0.0), (radius, 0.0)] + prof[::-1][1:], segments=96, uv='planar')
    K.subdivide(obj, 1)
    for v in obj.data.vertices:       # piped / spooned swirl ridges
        r = math.hypot(v.co.x, v.co.y) / radius
        a = math.atan2(v.co.y, v.co.x)
        if v.co.z > 0.002:
            v.co.z += 0.0024 * math.sin(a * 1 + r * 22) * (1 - r) * 1.3
            k = 1 + 0.03 * math.sin(a * 6 + r * 10)
            v.co.x *= k
            v.co.y *= k
    s = K.Shader(name + '_mat', spec=0.4)
    n = s.noise(70, 5, 0.6)
    top = s.maprange(s.up(), 0.6, 1.0, 0, 1)
    col = s.mix((0.90, 0.80, 0.52), (0.80, 0.62, 0.30), s.math('MULTIPLY', s.math('MULTIPLY', top, n), 0.35))
    s.out(col, rough=0.5, height=n, strength=0.4, distance=0.0008)
    K.assign(obj, s.mat)
    smooth(obj, 70)
    uv_unwrap(obj)
    bake(obj, res=1024)
    set_origin_bottom(obj)
    return obj


def _asparagus(count, rng):
    spears = []
    for i in range(count):
        L = 0.13 + 0.015 * rng.random()
        pts = [(L * s, 0.0, 0.0045 + 0.002 * math.sin(s * math.pi)) for s in np.linspace(0, 1, 30)]
        rad = [0.0052 * (1 - 0.25 * s) * (1 if s < 0.86 else 1.15 - (s - 0.86) * 5.5) for s in np.linspace(0, 1, 30)]
        sp = K.sweep(f'asp_{i}', pts, [max(r, 0.0008) for r in rad], sides=12)
        K.transform(sp, loc=(-L / 2, (i - (count - 1) / 2) * 0.0115, 0), rot=(0, 0, rng.uniform(-0.04, 0.04)))
        spears.append(sp)
    obj = K.join(spears, 'asparagus')
    s = K.Shader('asparagus_mat', spec=0.5)
    x = s.maprange(s.position('X'), -0.07, 0.075, 0, 1)
    tip = s.maprange(x, 0.82, 0.95, 0, 1)
    scales = s.voronoi(400, out='Distance')
    col = s.ramp(x, [(0.0, (0.26, 0.32, 0.08)), (0.5, (0.07, 0.20, 0.025)), (1.0, (0.05, 0.12, 0.02))])
    col = s.mix(col, (0.22, 0.12, 0.18), s.math('MULTIPLY', tip, s.maprange(scales, 0.2, 0.0, 0, 0.6)))
    grill = s.wave(9, distortion=0.3, detail=0, bands='X')
    col = s.mix(col, (0.02, 0.02, 0.008), s.math('MULTIPLY', s.maprange(grill, 0.035, 0.0, 0, 1), s.maprange(s.up(), 0.75, 0.95, 0, 0.8)))
    s.out(col, rough=0.35, height=s.math('ADD', scales, 0), strength=0.25, distance=0.0004)
    K.assign(obj, s.mat)
    smooth(obj, 60)
    uv_unwrap(obj)
    bake(obj, res=1024)
    set_origin_bottom(obj)
    return obj


def _herb_butter(name='garlic-butter', radius=0.015, height=0.007):
    obj = disc_mesh(name, radius, height, cuts=8, bevel=0.5)
    for v in obj.data.vertices:          # melting: base spreads, top softens
        r = math.hypot(v.co.x, v.co.y)
        if v.co.z < 0:
            v.co.x *= 1.18
            v.co.y *= 1.18
    planar_uv(obj)
    res = 512
    x, y, r, t = K.grid(res)
    col = np.ones((res, res, 3), np.float32) * np.array([0.98, 0.88, 0.52])
    herbs = K.vnoise(res, 70, 3) > 0.8
    col[herbs] = np.array([0.20, 0.38, 0.10])
    garlic = K.vnoise(res, 50, 5) > 0.86
    col[garlic] = np.array([0.98, 0.96, 0.85])
    K.assign(obj, K.textured(name + '_mat', col, None, base_rough=0.25, spec=0.5))
    smooth(obj, 60)
    set_origin_bottom(obj)
    return obj


def _peppercorn_sauce(name, radius, center, seed, targets_floor):
    p = S.pool(name, radius, height=0.004, mat=K.solid(name + '_mat', (0.16, 0.06, 0.02), rough=0.08, spec=0.55),
               seed=seed, center=center)
    K.transform(p, loc=(0, 0, targets_floor))
    corns = F.crumbles(name + '_corns', [p], K.disc_region(radius * 0.8, center[0], center[1]), 26, (0.03, 0.025, 0.02),
                       size=0.0032, rough=0.4, seed=seed, squash=(1, 1, 0.9))
    return K.join([p, corns], name)


# ------------------------------------------------------------------ dishes

def ribeye(d):
    plate = d.base(C.plate(radius=0.15, well=0.115))
    rng = np.random.default_rng(3)
    mash = _mash()
    K.place(mash, [plate.obj], -0.065, 0.035)
    d.part(mash, 'mashed')
    asp = _asparagus(4, rng)
    K.place(asp, [plate.obj], -0.02, -0.055, rot=(0, 0, 0.25))
    d.part(asp, 'asparagus')
    steak = _slab('ribeye', 0.15, 0.105, 0.026, seed=3)
    K.assign(steak, _steak_crust('ribeye_mat', fat_side=0.052 * 0.9))
    smooth(steak, 50)
    uv_unwrap(steak)
    bake(steak, res=2048)
    K.place(steak, [plate.obj, asp], 0.03, 0.01, rot=(0.0, 0.03, -0.35))
    d.part(steak, 'ribeye')
    butter = _herb_butter()
    K.place(butter, [steak], 0.035, 0.012, sink=0.001)
    d.part(butter, 'garlic-butter')
    sauce = _peppercorn_sauce('pepper-sauce', 0.032, (0.085, -0.06), 4, plate.floor)
    d.part(sauce, 'pepper-sauce')
    ros = P.sprig('rosemary', 'rosemary', size=0.9, seed=2)
    K.place(ros, [steak, butter], 0.025, -0.012, rot=(0, 0, 0.8), sink=0.001)
    ros2 = P.sprig('rosemary2', 'rosemary', size=0.75, seed=5)
    K.place(ros2, [plate.obj, mash], -0.03, 0.08, rot=(0, 0, 2.4))
    d.part(K.join([ros, ros2], 'rosemary'), 'rosemary')


def filet_mignon(d):
    plate = d.base(C.plate(radius=0.15, well=0.115, color=(0.08, 0.075, 0.075)))
    rng = np.random.default_rng(5)
    mash = _mash(radius=0.04, height=0.03, seed=2)
    K.place(mash, [plate.obj], -0.06, -0.035)
    d.part(mash, 'mashed')
    filet = disc_mesh('filet', 0.036, 0.046, cuts=14, radius_fn=lambda t: 1 + 0.03 * math.sin(3 * t) + 0.02 * math.sin(5 * t),
                      bevel=0.32, smooth_level=1)
    K.displace(filet, 0.0012, 0.01)
    K.assign(filet, _steak_crust('filet_mat'))
    smooth(filet, 50)
    uv_unwrap(filet)
    bake(filet, res=1024)
    set_origin_bottom(filet)
    sauce = S.pool('wine-sauce', 0.06, height=0.0035, mat=K.solid('wine_mat', (0.10, 0.006, 0.012), rough=0.04, spec=0.6),
                   seed=6, center=(0.035, 0.012))
    K.transform(sauce, loc=(0, 0, plate.floor))
    K.place(filet, [plate.obj, sauce], 0.035, 0.012, sink=0.001)
    d.part(sauce, 'wine-sauce')
    d.parts.insert(len(d.parts) - 1, d.parts.pop())   # sauce below the steak in explode order
    d.part(filet, 'filet')
    # bacon wrapped around the side
    lo, hi = K.bounds(filet)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    nu, nv = 96, 8
    verts, faces, uvs = [], [], []
    for i in range(nu + 1):
        a = i / nu * (math.tau + 0.4)
        rr = 0.0372 + 0.0006 * math.sin(a * 14)
        for j in range(nv + 1):
            z = lo[2] + 0.009 + (j / nv) * 0.029 + 0.0014 * math.sin(a * 5 + j * 0.3)
            r2 = rr + 0.0012 * (1 if i / nu > 1.0 else 0)
            verts.append((cx + r2 * math.cos(a), cy + r2 * math.sin(a), z))
    for i in range(nu):
        for j in range(nv):
            q = (i * (nv + 1) + j, (i + 1) * (nv + 1) + j, (i + 1) * (nv + 1) + j + 1, i * (nv + 1) + j + 1)
            faces.append(q)
            uvs += [(i / nu, j / nv), ((i + 1) / nu, j / nv), ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv)]
    bacon = K.mesh_from_arrays('bacon-wrap', verts, faces, uvs)
    K.solidify(bacon, 0.0025, offset=1)
    color, rough = BP._bacon_texture(seed=4)
    K.assign(bacon, K.textured('bacon_wrap_mat', color, rough, spec=0.5))
    smooth(bacon, 60)
    d.part(bacon, 'bacon-wrap')
    thyme = []
    for i in range(3):
        t = P.sprig(f'thyme_{i}', 'thyme', size=0.9, seed=i + 1)
        K.place(t, [filet, plate.obj, mash], [0.03, 0.045, -0.04][i], [0.01, 0.0, -0.03][i], rot=(0, 0, i * 1.9 + 0.3), sink=0.001)
        thyme.append(t)
    d.part(K.join(thyme, 'thyme'), 'thyme')


def _grilled_tomato(name, seed=0):
    halves = []
    for i, (x, y) in enumerate([(0.0, 0.0), (0.036, 0.018)]):
        prof = [(0.0, 0.0)] + [(0.024 * math.sin(a), 0.022 * (1 - math.cos(a)) * 0.9) for a in np.linspace(0.05, math.pi / 2, 16)] + \
               [(0.0, 0.0198)]
        h = K.revolve(f'{name}_{i}', prof, segments=64, uv='planar')
        for v in h.data.vertices:
            a = math.atan2(v.co.y, v.co.x)
            k = 1 + 0.05 * math.sin(a * 5 + seed)
            v.co.x *= k
            v.co.y *= k
        # flip so the cut face is on top
        K.transform(h, rot=(math.pi, 0, 0))
        set_origin_bottom(h)
        h.location = (x, y, 0)
        K.apply_transform(h)
        halves.append(h)
    obj = K.join(halves, name)
    planar_uv(obj)
    tc, tr = V._tomato_texture(seed + 3)
    char = K.smoothstep(0.75, 0.95, K.fbm(1024, 14, seed, 4))
    tc = tc * (1 - char[..., None] * 0.85)
    K.assign(obj, K.textured(name + '_mat', np.clip(tc, 0, 1).astype(np.float32), tr, spec=0.5))
    smooth(obj, 60)
    set_origin_bottom(obj)
    return obj


def striploin_fries(d):
    plate = d.base(C.plate(radius=0.155, well=0.12))
    rng = np.random.default_rng(7)
    fries = F.fries_pile('fries', [plate.obj], 30, lambda r: (r.uniform(-0.085, -0.035), r.uniform(-0.05, 0.04)),
                         plate.floor + 0.03, rng, catcher_z=plate.floor)
    d.part(fries, 'fries')
    # whole steak, then cut into slices showing a pink medium-rare centre
    L, W, H = 0.13, 0.07, 0.028
    base = _slab('strip_whole', L, W, H, seed=7,
                 outline=lambda t: (1 / max(abs(math.cos(t)) ** 4 + abs(math.sin(t)) ** 4, 1e-6) ** 0.25) * 0.82)
    crust = _steak_crust('strip_crust', fat_side=W / 2 * 0.95)
    inner = K.Shader('strip_inner', spec=0.5)
    yy = inner.math('ABSOLUTE', inner.position('Y'))
    zz = inner.math('ABSOLUTE', inner.position('Z'))
    edge = inner.math('MAXIMUM', inner.maprange(yy, W * 0.25, W * 0.5, 0, 1), inner.maprange(zz, H * 0.15, H * 0.5, 0, 1))
    grain = inner.noise(180, 4, 0.6)
    col = inner.ramp(edge, [(0.0, (0.46, 0.065, 0.05)), (0.55, (0.40, 0.085, 0.055)), (0.82, (0.27, 0.11, 0.065)),
                            (0.95, (0.14, 0.05, 0.02))])
    col = inner.mix(col, (0.9, 0.7, 0.6), inner.math('MULTIPLY', inner.maprange(grain, 0.6, 0.75, 0, 1), 0.25))
    inner.out(col, rough=0.3, height=grain, strength=0.3, distance=0.0004)
    cuts = 5
    slices = []
    for i in range(cuts):
        x0 = -L / 2 + L * i / cuts
        x1 = x0 + L / cuts
        piece = K.duplicate(base, f'sl_{i}')
        K.assign(piece, crust)                     # slots first: clearing slots later resets face indices
        piece.data.materials.append(inner.mat)
        bm = bmesh.new()
        bm.from_mesh(piece.data)
        for plane_x, keep_pos in ((x0, True), (x1, False)):
            res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(plane_x, 0, 0),
                                         plane_no=(1, 0, 0), clear_inner=keep_pos, clear_outer=not keep_pos)
        filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
        tri = bmesh.ops.triangulate(bm, faces=filled['faces'])
        for f in tri['faces']:
            f.material_index = 1
        bm.to_mesh(piece.data)
        bm.free()
        slices.append(piece)
    K.remove(base)
    steak = K.join(slices, 'striploin')
    smooth(steak, 40)
    uv_unwrap(steak)
    bake(steak, res=2048)       # baked upright: the doneness gradient is keyed to the slice's Y / Z
    # now lean every slice over like fallen dominoes so the pink cut faces look up
    import bpy
    K.activate(steak) if hasattr(K, 'activate') else None
    from lib import activate
    activate(steak)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    pieces = sorted(bpy.context.selected_objects, key=lambda o: K.bounds(o)[0][0])
    leaned = []
    for i, piece in enumerate(pieces):
        lo, hi = K.bounds(piece)
        piece.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])
        K.apply_transform(piece)
        K.transform(piece, rot=(0, 1.05, 0))
        lo, hi = K.bounds(piece)
        K.transform(piece, loc=(-i * 0.019 - (lo[0] + hi[0]) / 2, 0, -lo[2] + i * 0.0012))
        leaned.append(piece)
    steak = K.join(leaned, 'striploin')
    K.place(steak, [plate.obj], 0.04, 0.012, rot=(0, 0, 0.45))
    d.part(steak, 'striploin')
    tom = _grilled_tomato('grilled-tomato', seed=2)
    K.place(tom, [plate.obj], 0.02, -0.08, rot=(0, 0, 0.3))
    d.part(tom, 'grilled-tomato')
    v = C.ramekin('sauce-pot', radius=0.026, height=0.028)
    sauce = S.fill(v, v.rim - 0.004, 'pepper-sauce', K.solid('pepper_mat', (0.16, 0.06, 0.02), rough=0.08, spec=0.55), dome=0.0015)
    corns = F.crumbles('corns', [sauce], K.disc_region(0.016), 18, (0.03, 0.025, 0.02), size=0.0032, rough=0.4, seed=3)
    sauce = K.join([sauce, corns], 'pepper-sauce')
    for o in (v.obj, sauce):
        K.transform(o, loc=(-0.03, 0.085, plate.floor))
    d.base(v)
    d.part(sauce, 'pepper-sauce')


DISHES = {
    'ribeye': ribeye,
    'filet-mignon': filet_mignon,
    'striploin-fries': striploin_fries,
}
