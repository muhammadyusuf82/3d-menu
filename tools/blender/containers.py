"""
Serving ware for HD dishes. Every builder returns a Vessel: the static object (never explodes in the viewer) plus
its inner profile, so liquids, sauces and piles can be fitted exactly inside it.
"""
import math
import os

import bmesh
import bpy
import numpy as np

import kit as K
from lib import ASSETS, activate, set_origin_bottom, smooth

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_SCAN = os.path.join(HERE, '..', '..', 'web', 'public', 'models', 'polyhaven', 'wooden_cutting_board',
                          'wooden_cutting_board.gltf')


class Vessel:
    def __init__(self, obj, inner=None, floor=0.0, rim=0.0, radius=0.0):
        self.obj = obj
        self.inner = inner or []   # [(r, z)] inner wall from the floor up to the rim
        self.floor = floor         # z of the inner bottom (where food rests)
        self.rim = rim
        self.radius = radius       # usable radius at the floor (plates) / opening (bowls)

    def r_at(self, z):
        p = np.asarray(self.inner)
        return float(np.interp(z, p[:, 1], p[:, 0]))


def _ceramic(name, color=(0.93, 0.92, 0.885), rough=0.07):
    return K.solid(name, color, rough=rough, spec=0.55)


# ------------------------------------------------------------------ painted patterns

def paxta_texture(res=2048, rim_from=0.74, motifs=14, medallion=True, seed=2):
    """Uzbek 'paxta' (cotton boll) pattern in cobalt on white glaze, for top-down planar UVs (r = 1 at the rim)."""
    x, y, r, t = K.grid(res)
    white = np.array([0.95, 0.94, 0.91], np.float32)
    cobalt = np.array([0.09, 0.22, 0.58], np.float32)
    deep = np.array([0.04, 0.11, 0.38], np.float32)
    gold = np.array([0.80, 0.62, 0.28], np.float32)
    col = np.ones((res, res, 3), np.float32) * white
    glaze = K.fbm(res, 6, seed, 3)
    col *= (0.985 + 0.03 * glaze)[..., None]
    paint = np.zeros((res, res), np.float32)          # 0 = white, 1 = cobalt
    dark = np.zeros((res, res), np.float32)

    def boll(cx, cy, a, rot):
        u, v = x - cx, y - cy
        rr = np.hypot(u, v)
        th = np.arctan2(v, u) - rot
        disc = rr < a
        petals = rr < a * 0.70 * (0.62 + 0.38 * np.abs(np.cos(2 * th)) ** 0.7)
        ring = (rr > a * 0.86) & disc
        centre = rr < a * 0.16
        np.maximum(paint, (disc & ~petals).astype(np.float32), out=paint)
        np.maximum(dark, (ring | centre).astype(np.float32), out=dark)

    def leaf(cx, cy, length, width, ang):
        u, v = x - cx, y - cy
        cu, su = math.cos(ang), math.sin(ang)
        a = (u * cu + v * su) / length
        b = (-u * su + v * cu) / width
        shape = (a * a + (b / np.maximum(1e-3, 1 - a * a)) ** 2 < 1) & (np.abs(a) < 1)
        np.maximum(paint, shape.astype(np.float32), out=paint)

    band = (r > rim_from) & (r < 0.985)
    rmid = (rim_from + 0.985) / 2
    a = (0.985 - rim_from) * 0.36
    for k in range(motifs):
        ang = k / motifs * math.tau
        boll(rmid * math.cos(ang), rmid * math.sin(ang), a, ang)
        la = ang + math.pi / motifs
        for side in (-1, 1):
            leaf(rmid * math.cos(la) + side * 0.0, rmid * math.sin(la), a * 0.9, a * 0.33, la + math.pi / 2 + side * 0.5)
    for rr_line, w in ((rim_from - 0.012, 0.006), (0.985, 0.01), (rim_from - 0.03, 0.003)):
        np.maximum(dark, (np.abs(r - rr_line) < w).astype(np.float32), out=dark)
    if medallion:
        boll(0, 0, 0.17, 0.4)
        for k in range(8):
            ang = k / 8 * math.tau + 0.2
            leaf(0.27 * math.cos(ang), 0.27 * math.sin(ang), 0.06, 0.022, ang)
        np.maximum(dark, (np.abs(r - 0.36) < 0.004).astype(np.float32), out=dark)
    del band
    # hand-painted: slightly uneven pigment density
    density = 0.82 + 0.25 * K.fbm(res, 40, seed + 5, 3)
    col = col * (1 - paint[..., None] * density[..., None]) + cobalt * (paint * density)[..., None]
    col = col * (1 - dark[..., None]) + deep * dark[..., None]
    gilt = r > 0.992
    col[gilt] = gold
    return np.clip(col, 0, 1).astype(np.float32)


def profile_arc(prof):
    """Arc-length fraction of each profile point (matches revolve(uv='wrap') v coordinates) and total length."""
    p = np.asarray(prof, np.float64)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    return arc / arc[-1], float(arc[-1])


def paxta_wrap_texture(v_rim, total_arc, band_r, v_foot=0.06, motifs=8, w=2048, h=1024, seed=3):
    """Paxta pattern for wrap UVs (u around, v along the profile: outside 0..v_rim, inside v_rim..1)."""
    U = (np.arange(w, dtype=np.float32) + 0.5)[None, :] / w * np.ones((h, 1), np.float32)
    V = (1 - (np.arange(h, dtype=np.float32) + 0.5) / h)[:, None] * np.ones((1, w), np.float32)
    circ = math.tau * band_r
    white = np.array([0.95, 0.94, 0.91], np.float32)
    cobalt = np.array([0.09, 0.22, 0.58], np.float32)
    deep = np.array([0.04, 0.11, 0.38], np.float32)
    gold = np.array([0.80, 0.62, 0.28], np.float32)
    col = np.ones((h, w, 3), np.float32) * white * (0.985 + 0.03 * K.fbm(w, 6, seed, 3)[:h])[..., None]
    paint = np.zeros((h, w), np.float32)
    dark = np.zeros((h, w), np.float32)
    v0, v1 = v_foot + (v_rim - v_foot) * 0.18, v_rim - (v_rim - v_foot) * 0.12
    vc = (v0 + v1) / 2
    a = (v1 - v0) * total_arc * 0.36

    def local(uc, vcen):
        du = (U - uc + 0.5) % 1.0 - 0.5
        return du * circ, (V - vcen) * total_arc

    for k in range(motifs):
        uc = (k + 0.5) / motifs
        x, y = local(uc, vc)
        rr = np.hypot(x, y)
        th = np.arctan2(y, x)
        disc = rr < a
        petals = rr < a * 0.70 * (0.62 + 0.38 * np.abs(np.cos(2 * th)) ** 0.7)
        np.maximum(paint, (disc & ~petals).astype(np.float32), out=paint)
        np.maximum(dark, (((rr > a * 0.86) & disc) | (rr < a * 0.16)).astype(np.float32), out=dark)
        x, y = local(uc + 0.5 / motifs, vc)
        for side in (-1, 1):
            ang = math.pi / 2 + side * 0.55
            cu, su = math.cos(ang), math.sin(ang)
            px, py = x - side * a * 0.35, y
            la = (px * cu + py * su) / (a * 0.95)
            lb = (-px * su + py * cu) / (a * 0.34)
            shape = (la * la + (lb / np.maximum(1e-3, 1 - la * la)) ** 2 < 1) & (np.abs(la) < 1)
            np.maximum(paint, shape.astype(np.float32), out=paint)
    for vline, wid in ((v0 - 0.012, 0.004), (v1 + 0.012, 0.004), (v_rim + 0.035, 0.003)):
        np.maximum(dark, (np.abs(V - vline) < wid).astype(np.float32), out=dark)
    density = 0.82 + 0.25 * K.fbm(w, 40, seed + 5, 3)[:h]     # hand-painted: uneven pigment
    col = col * (1 - (paint * density)[..., None]) + cobalt * (paint * density)[..., None]
    col = col * (1 - dark[..., None]) + deep * dark[..., None]
    col[np.abs(V - v_rim) < 0.007] = gold
    return np.clip(col, 0, 1).astype(np.float32)


def _patterned_ceramic(name, pattern):
    mat = K.textured(name, pattern, None, base_rough=0.07, spec=0.55)
    return mat


# ------------------------------------------------------------------ plates and bowls

def plate(name='plate', radius=0.135, well=0.095, rim_h=0.021, pattern=None, color=(0.93, 0.92, 0.885)):
    """Restaurant dinner plate (or an Uzbek lyagan when pattern='paxta')."""
    floor = 0.0095
    prof = K.lathe_profile([(0.0, 0.0035), (well * 0.68, 0.0026), (well * 0.74, 0.0), (well * 0.80, 0.0),
                            (well * 0.88, 0.0035), (well, 0.0065), (radius * 0.97, rim_h - 0.0035), (radius, rim_h),
                            (radius - 0.004, rim_h + 0.0012), (radius * 0.9, rim_h - 0.003),
                            (well * 1.02, floor + 0.0006), (well * 0.9, floor), (0.0, floor)], steps=3)
    obj = K.revolve(name, prof, segments=96, uv='planar')
    if pattern == 'paxta':
        mat = _patterned_ceramic(f'{name}_paxta', paxta_texture())
    else:
        mat = _ceramic(f'{name}_glaze', color)
    K.assign(obj, mat)
    smooth(obj, 50)
    return Vessel(obj, inner=[(well, floor), (radius * 0.95, rim_h)], floor=floor, rim=rim_h, radius=well)


def bowl(name='bowl', radius=0.085, depth=0.07, foot=0.035, pattern=None, color=(0.93, 0.92, 0.885), wall=0.005):
    """Deep bowl (a kosa when pattern='paxta'). Inner wall is a smooth curve from the floor to the rim."""
    pts_out, pts_in = [], []
    for i in range(13):
        s = i / 12
        rr = foot + (radius - foot) * math.sin(s * math.pi / 2) ** 0.85
        pts_out.append((rr, depth * s ** 1.15))
    floor = 0.009
    for i in range(13):
        s = 1 - i / 12
        rr = (foot + (radius - foot) * math.sin(s * math.pi / 2) ** 0.85) - wall
        z = max(floor, depth * s ** 1.15 + wall * 0.2)
        pts_in.append((max(0.0, rr), z))
    prof = [(0.0, 0.002), (foot * 0.82, 0.002), (foot * 0.88, 0.0), (foot, 0.0)] + pts_out[1:] + \
           [(radius - wall * 0.5, depth + 0.0015)] + pts_in + [(0.0, floor)]
    smooth_prof = K.lathe_profile(prof, steps=2)
    obj = K.revolve(name, smooth_prof, segments=96, uv='wrap')
    if pattern == 'paxta':
        arc, total = profile_arc(smooth_prof)
        rim_i = int(np.argmax([p[1] for p in smooth_prof]))
        foot_i = int(np.argmin([abs(p[0] - foot) + abs(p[1]) for p in smooth_prof]))
        mat = _patterned_ceramic(f'{name}_paxta', paxta_wrap_texture(float(arc[rim_i]), total, radius * 0.85,
                                                                     v_foot=float(arc[foot_i]),
                                                                     motifs=6 if radius < 0.06 else 9))
    else:
        mat = _ceramic(f'{name}_glaze', color)
    K.assign(obj, mat)
    smooth(obj, 50)
    inner = sorted(pts_in, key=lambda p: p[1])
    return Vessel(obj, inner=[(foot - wall, floor)] + inner, floor=floor, rim=depth, radius=radius - wall)


def piala(name='piala', pattern='paxta'):
    """Uzbek tea bowl (piala), ~9 cm across."""
    return bowl(name, radius=0.046, depth=0.048, foot=0.022, pattern=pattern, wall=0.0035)


def ramekin(name='ramekin', radius=0.032, height=0.03, color=(0.95, 0.94, 0.91), wall=0.004):
    prof = K.lathe_profile([(0.0, 0.0), (radius - 0.003, 0.0), (radius, 0.003), (radius, height - 0.001),
                            (radius - wall / 2, height), (radius - wall, height - 0.001), (radius - wall, 0.008),
                            (radius - wall - 0.002, 0.006), (0.0, 0.006)], steps=3)
    obj = K.revolve(name, prof, segments=72, uv='wrap')
    K.assign(obj, _ceramic(f'{name}_glaze', color))
    smooth(obj, 50)
    return Vessel(obj, inner=[(radius - wall - 0.002, 0.006), (radius - wall, 0.008), (radius - wall, height - 0.001)],
                  floor=0.006, rim=height, radius=radius - wall)


def soy_dish(name='soy-dish', radius=0.04):
    prof = K.lathe_profile([(0.0, 0.0), (radius * 0.6, 0.0), (radius, 0.012), (radius - 0.003, 0.0135),
                            (radius * 0.62, 0.0045), (0.0, 0.0045)], steps=3)
    obj = K.revolve(name, prof, segments=72, uv='planar')
    K.assign(obj, _ceramic(f'{name}_glaze', (0.06, 0.05, 0.05), rough=0.06))
    smooth(obj, 50)
    return Vessel(obj, inner=[(radius * 0.62, 0.0045), (radius - 0.003, 0.0135)], floor=0.0045, rim=0.0135,
                  radius=radius * 0.6)


# ------------------------------------------------------------------ boards and trays

def slate(name='slate', size=(0.30, 0.15), thickness=0.008):
    """Dark slate serving board with chipped natural edges."""
    w, d = size
    obj = K.rounded_box(name, (w, d, thickness), bevel=0.25, segments=2)
    K.subdivide(obj, 2)
    K.displace(obj, 0.0012, 0.01, depth=3)
    res = 1024
    n = K.fbm(res, 10, 3, 5)
    grain = K.vnoise(res, 90, 4, aspect=0.15)
    col = np.ones((res, res, 3), np.float32) * np.array([0.16, 0.17, 0.18])
    col *= (0.75 + 0.45 * n * (0.8 + 0.4 * grain))[..., None]
    rough = (0.62 + 0.25 * n).astype(np.float32)
    normal = K.height_to_normal(grain * 0.6 + n, 0.6)
    lo, hi = K.bounds(obj)
    me = obj.data
    uv = me.uv_layers.new(name='UVMap') if not me.uv_layers else me.uv_layers.active
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((co.x - lo[0]) / (hi[0] - lo[0]), (co.y - lo[1]) / (hi[0] - lo[0]))
    K.assign(obj, K.textured(f'{name}_mat', col, rough, normal, spec=0.35))
    smooth(obj, 40)
    set_origin_bottom(obj)
    obj.location = (0, 0, 0)
    top = float(K.bounds(obj)[1][2])
    return Vessel(obj, floor=top, rim=top, radius=min(w, d) / 2)


def wooden_board(name='board', length=0.34):
    """The Poly Haven 'wooden cutting board' scan (CC0), scaled to `length`, textures reduced to 1k for the web."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(BOARD_SCAN))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    for o in new:
        if o.type != 'MESH':
            o.select_set(False)
    for o in meshes:
        activate(o)
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    obj = K.join(meshes, name)
    lo, hi = K.bounds(obj)
    s = length / max(hi[0] - lo[0], hi[1] - lo[1])
    obj.scale = (s, s, s)
    K.apply_transform(obj)
    lo, hi = K.bounds(obj)
    if hi[1] - lo[1] > hi[0] - lo[0]:          # long side along x
        obj.rotation_euler.z = math.pi / 2
        K.apply_transform(obj)
    set_origin_bottom(obj)
    obj.location = (0, 0, 0)
    for mat in obj.data.materials:
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and node.image.size[0] > 1024:
                node.image.scale(1024, 1024)
                node.image.pack()
    lo, hi = K.bounds(obj)
    # the board has a handle at one end: food goes on the flat middle
    top = float(np.median([v.co.z for v in obj.data.vertices if v.co.z > hi[2] - 0.01]))
    return Vessel(obj, floor=top, rim=top, radius=(hi[1] - lo[1]) / 2)


def _rounded_rect(w, d, r, n=10):
    """Outline of a rounded rectangle (counter-clockwise), corners with n segments."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90), (-w / 2 + r, -d / 2 + r, 180),
                       (w / 2 - r, -d / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def paper_boat(name='paper-boat', size=(0.17, 0.10), height=0.038, checker=(0.78, 0.08, 0.06)):
    """Kraft-paper food tray with flared, softly pleated walls, lined with red/white checked paper."""
    w, d = size
    flare = 0.016
    rings = 10
    base = _rounded_rect(w - 2 * flare, d - 2 * flare, 0.012)
    n = len(base)
    verts, faces = [(0.0, 0.0, 0.0)], []
    for k in range(rings + 1):
        s = k / rings
        ring = _rounded_rect(w - 2 * flare + 2 * flare * s, d - 2 * flare + 2 * flare * s, 0.012 + flare * s)
        for i, (x, y) in enumerate(ring):
            pleat = 0.0012 * math.sin(i * 1.7) * s          # creased paper at the corners
            verts.append((x * (1 + pleat * 8), y * (1 + pleat * 8), height * s ** 0.9))
    for i in range(n):
        faces.append((0, 1 + i, 1 + (i + 1) % n))
    for k in range(rings):
        for i in range(n):
            a = 1 + k * n + i
            b = 1 + k * n + (i + 1) % n
            faces.append((a, a + n, b + n, b)[::-1])
    obj = K.mesh_from_arrays(name, verts, faces)
    K.solidify(obj, 0.0009, offset=-1)
    K.subdivide(obj, 1)
    res = 1024
    x, y, r, t = K.grid(res)
    kraft = np.array([0.71, 0.53, 0.33], np.float32) * (0.9 + 0.15 * K.fbm(res, 30, 2, 4))[..., None]
    sq = 10
    chk = ((((x + 1) * sq).astype(int) + ((y + 1) * sq * d / w).astype(int)) % 2 == 0)
    cloth = np.where(chk[..., None], np.array(checker, np.float32), np.array([0.95, 0.93, 0.9], np.float32))
    cloth = cloth * (0.94 + 0.06 * np.sin(x * 500) * np.sin(y * 500))[..., None]
    inner = (np.abs(x) < 0.8) & (np.abs(y) < 0.74)
    col = np.where(inner[..., None], cloth, kraft)
    crinkle = K.fbm(res, 24, 7, 4)
    me = obj.data
    lo, hi = K.bounds(obj)
    uv = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((co.x - lo[0]) / (hi[0] - lo[0]), (co.y - lo[1]) / (hi[1] - lo[1]))
    K.assign(obj, K.textured(f'{name}_mat', col.astype(np.float32), (0.7 + 0.15 * crinkle).astype(np.float32),
                             K.height_to_normal(crinkle, 0.4), spec=0.3))
    smooth(obj, 40)
    set_origin_bottom(obj)
    obj.location = (0, 0, 0)
    return Vessel(obj, floor=0.0009, rim=height, radius=min(w, d) / 2 - flare)


# ------------------------------------------------------------------ drinkware

def _glass_profile(r_bottom, r_top, height, wall=0.0022, base=0.010, belly=0.0):
    outer = []
    for i in range(9):
        s = i / 8
        rr = r_bottom + (r_top - r_bottom) * s + belly * math.sin(s * math.pi)
        outer.append((rr, height * s))
    inner = []
    for i in range(9):
        s = 1 - i / 8
        rr = r_bottom + (r_top - r_bottom) * s + belly * math.sin(s * math.pi) - wall
        inner.append((rr, max(base, height * s)))
    prof = [(0.0, 0.0), (r_bottom - 0.003, 0.0)] + outer[1:] + [(r_top - wall / 2, height + 0.0008)] + inner + [(0.0, base)]
    inner_up = sorted(inner, key=lambda p: p[1])
    return K.lathe_profile(prof, steps=2), [(inner_up[0][0] - 0.0015, base)] + inner_up


def tumbler(name='glass', r_bottom=0.031, r_top=0.039, height=0.14, base=0.012):
    prof, inner = _glass_profile(r_bottom, r_top, height, base=base)
    obj = K.revolve(name, prof, segments=96, uv='wrap')
    K.assign(obj, K.glass(f'{name}_glass'))
    smooth(obj, 60)
    return Vessel(obj, inner=inner, floor=base, rim=height, radius=r_top)


def tea_glass(name='tea-glass'):
    """Clear glass tea cup on a saucer (returns the cup vessel; saucer joined into it)."""
    cup_prof, inner = _glass_profile(0.026, 0.040, 0.072, wall=0.002, base=0.007, belly=0.002)
    cup = K.revolve(name + '_cup', cup_prof, segments=96, uv='wrap')
    K.assign(cup, K.glass(f'{name}_glass'))
    handle = K.sweep(name + '_handle', [(0.038 + 0.016 * math.sin(a), 0, 0.036 + 0.019 * math.cos(a))
                                        for a in np.linspace(0.25, math.pi - 0.25, 24)], 0.0035, sides=10)
    K.assign(handle, K.glass(f'{name}_glass2'))
    saucer = _saucer(name + '_saucer', 0.075)
    cup.location.z = saucer[1]
    K.apply_transform(cup)
    handle.location = (0.0, 0, saucer[1])
    K.apply_transform(handle)
    obj = K.join([saucer[0], cup, handle], name)
    smooth(obj, 60)
    inner = [(r, z + saucer[1]) for r, z in inner]
    return Vessel(obj, inner=inner, floor=inner[0][1], rim=0.072 + saucer[1], radius=0.04)


def _saucer(name, radius, color=(0.94, 0.93, 0.90)):
    prof = K.lathe_profile([(0.0, 0.002), (radius * 0.45, 0.0015), (radius * 0.5, 0.0), (radius * 0.56, 0.0),
                            (radius * 0.6, 0.003), (radius, 0.012), (radius - 0.003, 0.0135), (radius * 0.58, 0.0065),
                            (radius * 0.42, 0.006), (0.0, 0.006)], steps=3)
    obj = K.revolve(name, prof, segments=96, uv='planar')
    K.assign(obj, _ceramic(f'{name}_glaze', color))
    smooth(obj, 50)
    return obj, 0.006


def cup(name='cup', r_bottom=0.028, r_top=0.046, height=0.062, saucer=0.075, color=(0.95, 0.94, 0.91)):
    """Porcelain coffee cup on a saucer (cappuccino ~ 180 ml; pass smaller values for espresso)."""
    wall = 0.003
    outer = [(r_bottom + (r_top - r_bottom) * math.sin(s * math.pi / 2) ** 1.4, height * s) for s in np.linspace(0, 1, 10)]
    inner = [(max(0.0, r - wall), max(0.007, z)) for r, z in outer[::-1]]
    prof = [(0.0, 0.0), (r_bottom * 0.75, 0.0), (r_bottom * 0.8, 0.0015)] + outer[1:] + \
           [(r_top - wall / 2, height + 0.001)] + inner + [(0.0, 0.007)]
    body = K.revolve(name + '_body', K.lathe_profile(prof, steps=2), segments=96, uv='wrap')
    K.assign(body, _ceramic(f'{name}_glaze', color))
    hx = r_top * 0.9
    handle = K.sweep(name + '_handle', [(hx + 0.013 * math.sin(a) + 0.002, 0, height * 0.55 + height * 0.3 * math.cos(a))
                                        for a in np.linspace(0.1, math.pi - 0.1, 24)], 0.0032, sides=10)
    K.assign(handle, body.data.materials[0])
    parts = [body, handle]
    lift = 0.0
    if saucer:
        s_obj, lift = _saucer(name + '_saucer', saucer, color)
        body.location.z = handle.location.z = lift
        K.apply_transform(body)
        K.apply_transform(handle)
        parts.append(s_obj)
    obj = K.join(parts, name)
    smooth(obj, 50)
    inner_up = sorted([(r, z + lift) for r, z in inner], key=lambda p: p[1])
    return Vessel(obj, inner=inner_up, floor=0.007 + lift, rim=height + lift, radius=r_top - wall)


def mug(name='mug', radius=0.042, height=0.095, color=(0.55, 0.16, 0.10)):
    """Glazed stoneware mug (hot chocolate)."""
    wall = 0.0045
    prof = K.lathe_profile([(0.0, 0.0), (radius - 0.004, 0.0), (radius, 0.004), (radius + 0.001, height * 0.5),
                            (radius, height), (radius - wall / 2, height + 0.0012), (radius - wall, height),
                            (radius - wall, 0.013), (radius - wall - 0.003, 0.010), (0.0, 0.010)], steps=3)
    body = K.revolve(name + '_body', prof, segments=96, uv='wrap')
    arc, _ = profile_arc(prof)
    v_rim = float(arc[int(np.argmax([p[1] for p in prof]))])
    res = 1024
    n = K.fbm(res, 20, 3, 4)
    speck = (K.vnoise(res, 420, 5) > 0.88).astype(np.float32) * 0.6
    rgb = np.ones((res, res, 3), np.float32) * np.array([0.62, 0.20, 0.11])
    rgb *= (0.85 + 0.25 * n)[..., None]
    rgb = rgb * (1 - 0.5 * speck[..., None])
    # unglazed foot ring and lighter glaze break at the rim (wrap UV: v = 0 at the foot, 1 at the axis inside)
    v = np.linspace(1, 0, res, dtype=np.float32)[:, None] * np.ones((1, res), np.float32)
    foot = v < 0.035
    rgb[foot] = np.array([0.72, 0.60, 0.48])
    brk = np.clip(1 - np.abs(v - v_rim) / 0.025, 0, 1)[..., None]     # glaze thins and pales over the rim
    rgb = rgb * (1 - brk * 0.45) + np.array([0.86, 0.64, 0.44]) * brk * 0.45
    K.assign(body, K.textured(f'{name}_glaze', rgb, (0.12 + 0.1 * n).astype(np.float32), spec=0.5))
    handle = K.sweep(name + '_handle', [(radius - 0.002 + 0.024 * math.sin(a), 0, height * 0.5 + height * 0.3 * math.cos(a))
                                        for a in np.linspace(0.05, math.pi - 0.05, 28)], 0.0055, sides=12,
                     profile=lambda a: 1.0 + 0.35 * math.cos(2 * a))
    K.assign(handle, body.data.materials[0])
    obj = K.join([body, handle], name)
    smooth(obj, 50)
    return Vessel(obj, inner=[(radius - wall - 0.003, 0.010), (radius - wall, 0.013), (radius - wall, height)],
                  floor=0.010, rim=height, radius=radius - wall)


def stemmed_glass(name='sundae-glass', bowl_r=0.048, bowl_h=0.075, stem_h=0.06, foot_r=0.04):
    """Tulip sundae / milkshake glass on a short stem."""
    wall = 0.0025
    pts_out = [(bowl_r * math.sin(min(1, s * 1.15) * math.pi / 2) ** 0.7 * (1 - 0.08 * s), stem_h + bowl_h * s)
               for s in np.linspace(0.05, 1, 12)]
    pts_in = [(max(0.0, r - wall), z + wall * 0.6) for r, z in pts_out[::-1]]
    prof = [(0.0, 0.0), (foot_r, 0.0), (foot_r - 0.002, 0.003), (0.007, 0.006), (0.0055, stem_h * 0.5),
            (0.008, stem_h - 0.004), pts_out[0]] + pts_out[1:] + [(pts_out[-1][0] - wall / 2, stem_h + bowl_h + 0.0008)] + \
           pts_in + [(0.0, stem_h + 0.008)]
    obj = K.revolve(name, K.lathe_profile(prof, steps=2), segments=96, uv='wrap')
    K.assign(obj, K.glass(f'{name}_glass'))
    smooth(obj, 60)
    inner = sorted(pts_in, key=lambda p: p[1])
    return Vessel(obj, inner=[(0.004, stem_h + 0.008)] + inner, floor=stem_h + 0.008, rim=stem_h + bowl_h,
                  radius=bowl_r - wall)


def straw(name='straw', base=(0.015, 0.01, 0.02), top=(0.035, 0.03, 0.2), radius=0.0035,
          color=(0.92, 0.25, 0.25)):
    """Paper straw with a printed spiral stripe."""
    p0, p1 = np.array(base), np.array(top)
    pts = [p0 + (p1 - p0) * s for s in np.linspace(0, 1, 40)]
    obj = K.sweep(name, pts, radius, sides=12, caps=False)
    K.solidify(obj, 0.0004)
    res = 256
    u = np.linspace(0, 1, res, dtype=np.float32)[None, :] * np.ones((res, 1), np.float32)
    v = np.linspace(0, 1, res, dtype=np.float32)[:, None] * np.ones((1, res), np.float32)
    stripe = ((u + v * 8) % 1.0) < 0.5
    rgb = np.where(stripe[..., None], np.array(color, np.float32), np.array([0.96, 0.95, 0.92], np.float32))
    mat = K.textured(f'{name}_paper', rgb.astype(np.float32), None, base_rough=0.6, spec=0.3)
    K.assign(obj, mat)
    return obj


def skewer(name, start, end, radius=0.0018):
    """Flat steel shashlik skewer with a looped handle."""
    pts = [np.array(start) + (np.array(end) - np.array(start)) * s for s in np.linspace(0, 1, 30)]
    obj = K.sweep(name, pts, radius, sides=8, profile=lambda a: 1.0 + 0.9 * abs(math.cos(a)))
    loop_c = np.array(end) + (np.array(end) - np.array(start)) / np.linalg.norm(np.array(end) - np.array(start)) * 0.012
    ring = K.sweep(name + '_ring', [loop_c + np.array([0.011 * math.cos(a), 0.0, 0.011 * math.sin(a)])
                                    for a in np.linspace(0, math.tau, 40)], radius * 0.9, sides=8)
    obj = K.join([obj, ring], name)
    K.assign(obj, K.solid(f'{name}_steel', (0.78, 0.78, 0.8), rough=0.28, metal=1.0))
    return obj
