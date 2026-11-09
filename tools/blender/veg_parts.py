"""Tomato, onion, pickles, lettuce and sauce: geometry plus numpy-painted textures (no baking needed)."""
import math

import bmesh
import bpy
import numpy as np

from lib import activate, disc_mesh, image_from_array, link, new_object, node_material, planar_uv, set_origin_bottom, \
    smooth, tex_node

RES = 1024


def _grid(res=RES):
    """Normalised texture coordinates: x, y in [-1, 1], radius r, angle t (row 0 = top)."""
    lin = np.linspace(-1, 1, res, dtype=np.float32)
    x, y = np.meshgrid(lin, -lin)
    return x, y, np.hypot(x, y), np.arctan2(y, x)


def _noise(res, scale, seed):
    """Cheap smooth value noise (bilinear upsampled random grid)."""
    rng = np.random.default_rng(seed)
    g = rng.random((scale + 1, scale + 1)).astype(np.float32)
    idx = np.linspace(0, scale, res, dtype=np.float32)
    i0 = np.floor(idx).astype(int).clip(0, scale - 1)
    f = (idx - i0)[None, :]
    rows = g[i0][:, i0] * (1 - f) + g[i0][:, i0 + 1] * f
    fr = (idx - i0)[:, None]
    return rows * (1 - fr) + g[i0 + 1][:, i0] * (1 - f) * fr + g[i0 + 1][:, i0 + 1] * f * fr


def _textured(name, color, rough, base_rough=0.4, spec=0.5):
    mat, nt, bsdf = node_material(name)
    c = tex_node(nt, image_from_array(f'{name}_color', color), -600, 200)
    link(nt, c.outputs['Color'], bsdf.inputs['Base Color'])
    if rough is not None:
        r = tex_node(nt, image_from_array(f'{name}_rough', np.repeat(rough[..., None], 3, axis=2), non_color=True), -600, -150)
        link(nt, r.outputs['Color'], bsdf.inputs['Roughness'])
    else:
        bsdf.inputs['Roughness'].default_value = base_rough
    bsdf.inputs['Specular IOR Level'].default_value = spec
    return mat


def _ellipses(img, mask_fn, centers, a, b, angles, color):
    """Stamps filled ellipses (seeds) into img where they fall inside mask_fn."""
    res = img.shape[0]
    for (cx, cy), ang in zip(centers, angles):
        px, py = int((cx + 1) / 2 * res), int((1 - (cy + 1) / 2) * res)
        rad = int(max(a, b) * res / 2) + 2
        y0, y1, x0, x1 = max(0, py - rad), min(res, py + rad), max(0, px - rad), min(res, px + rad)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        u = (xx / res * 2 - 1) - cx
        v = (1 - yy / res * 2) - cy
        cu, su = math.cos(ang), math.sin(ang)
        inside = ((u * cu + v * su) / a) ** 2 + ((-u * su + v * cu) / b) ** 2 <= 1
        if mask_fn is not None:
            inside &= mask_fn(cx, cy)
        img[y0:y1, x0:x1][inside] = color


# ------------------------------------------------------------------ tomato

def _tomato_texture(seed=4):
    x, y, r, t = _grid()
    n = _noise(RES, 24, seed)
    n2 = _noise(RES, 9, seed + 1)
    rng = np.random.default_rng(seed)
    col = np.zeros((RES, RES, 3), np.float32)
    rough = np.full((RES, RES), 0.32, np.float32)
    # pericarp: deep red with subtle mottling and a lighter band just inside the skin
    col[:] = np.array([0.74, 0.07, 0.03]) * (0.85 + 0.3 * n[..., None])
    band = np.clip(1 - np.abs(r - 0.86) / 0.06, 0, 1)[..., None]
    col = col * (1 - 0.25 * band) + np.array([0.90, 0.22, 0.10]) * 0.25 * band
    lobes = int(rng.integers(3, 5))
    offs = rng.random() * math.tau
    warp_t = t + (n2 - 0.5) * 0.5                       # wobbly, organic locule walls
    warp_r = r + (n - 0.5) * 0.08
    ang = (warp_t - offs) % (math.tau / lobes) - math.pi / lobes
    lobe_w = (math.pi / lobes) * 0.78 * np.clip((warp_r - 0.18) / 0.3, 0, 1) ** 0.6
    gel = (warp_r > 0.2) & (warp_r < 0.72 + 0.04 * np.sin(t * 3)) & (np.abs(ang) < lobe_w)
    gel_col = np.array([0.93, 0.42, 0.16]) * (0.85 + 0.25 * n2[..., None])
    col[gel] = col[gel] * 0.25 + gel_col[gel] * 0.75
    rough[gel] = 0.16
    core = warp_r < 0.19
    col[core] = (np.array([0.88, 0.28, 0.12]) * (0.9 + 0.15 * n[..., None]))[core]
    for k in range(lobes):
        a0 = offs + (k + 0.5) * math.tau / lobes
        cs, angs = [], []
        for _ in range(int(rng.integers(9, 14))):
            rr = 0.33 + 0.28 * rng.random()
            aa = a0 + (rng.random() - 0.5) * 0.75 * (math.pi / lobes) * 2 * min(1, rr / 0.55)
            cs.append((rr * math.cos(aa), rr * math.sin(aa)))
            angs.append(aa + (rng.random() - 0.5) * 0.8)
        _ellipses(col, None, cs, 0.024, 0.014, angs, np.array([0.95, 0.82, 0.42]))
    skin = r > 0.955
    col[skin] = np.array([0.50, 0.03, 0.015])
    rough[skin] = 0.2
    return np.clip(col, 0, 1).astype(np.float32), rough


def tomato(name='tomato', radius=0.034, thickness=0.0055, slices=2, seed=4):
    color, rough = _tomato_texture(seed)
    mat = _textured(name, color, rough)
    bm_all = bmesh.new()
    offsets = [(-0.012, 0.004, 0.0, 0.2), (0.013, -0.006, thickness * 0.55, 1.4), (0.0, 0.016, thickness * 0.3, 2.6)]
    parts = []
    for i in range(slices):
        piece = disc_mesh(f'{name}_{i}', radius * (1 - 0.04 * i), thickness, cuts=14, bevel=0.3)
        planar_uv(piece)
        dx, dy, dz, rot = offsets[i]
        piece.rotation_euler.z = rot
        piece.location = (dx, dy, dz + thickness / 2)
        parts.append(piece)
    for p in parts[1:]:
        p.select_set(True)
    activate(parts[0])
    for p in parts[1:]:
        p.select_set(True)
    bpy.ops.object.join()
    obj = parts[0]
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    smooth(obj, 50)
    set_origin_bottom(obj)
    bm_all.free()
    return obj


# ------------------------------------------------------------------ red onion rings

def _onion_texture():
    lin = np.linspace(0, 1, 256, dtype=np.float32)
    v = np.repeat(lin[:, None], 64, axis=1)          # rows = across the ring (0 inner .. 1 outer)
    col = np.zeros((256, 64, 3), np.float32)
    white = np.array([0.93, 0.86, 0.90])
    purple = np.array([0.45, 0.07, 0.30])
    pink = np.array([0.80, 0.55, 0.70])
    f = np.clip((v - 0.70) / 0.22, 0, 1)[..., None]
    col[:] = white * (1 - f) + purple * f
    inner = (v < 0.10)[..., None]
    col[:] = np.where(inner, pink, col)
    return np.flipud(col).copy()


def onion(name='onion', rings=((0.030, 0.026), (0.024, 0.021), (0.036, 0.032)), thickness=0.0028, seed=5):
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new('UVMap')
    seg, across = 72, 2
    for ri, (ro, rin) in enumerate(rings):
        cx, cy = (rng.random() - 0.5) * 0.02, (rng.random() - 0.5) * 0.02
        z0 = ri * thickness * 0.6
        grid = []
        for layer, z in enumerate((z0, z0 + thickness)):
            rows = []
            for a in range(seg):
                th = a / seg * math.tau
                wob = 1 + 0.04 * math.sin(th * 2 + ri)
                row = []
                for j in range(across + 1):
                    rr = (rin + (ro - rin) * j / across) * wob
                    row.append(bm.verts.new((cx + rr * math.cos(th), cy + rr * math.sin(th), z)))
                rows.append(row)
            grid.append(rows)

        def quad(vs, uvs, flip):
            f = bm.faces.new(vs[::-1] if flip else vs)
            for loop, uv in zip(f.loops, uvs[::-1] if flip else uvs):
                loop[uv_layer].uv = uv

        for layer in (0, 1):
            rows = grid[layer]
            for a in range(seg):
                b = (a + 1) % seg
                for j in range(across):
                    vs = [rows[a][j], rows[b][j], rows[b][j + 1], rows[a][j + 1]]
                    uvs = [(a / seg * 6, j / across), ((a + 1) / seg * 6, j / across), ((a + 1) / seg * 6, (j + 1) / across), (a / seg * 6, (j + 1) / across)]
                    quad(vs, uvs, flip=(layer == 0))
        for a in range(seg):
            b = (a + 1) % seg
            for j, vcoord in ((0, 0.02), (across, 0.98)):
                vs = [grid[0][a][j], grid[0][b][j], grid[1][b][j], grid[1][a][j]]
                uvs = [(a / seg * 6, vcoord)] * 2 + [((a + 1) / seg * 6, vcoord)] * 2
                quad(vs, uvs, flip=(j == across))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    obj = new_object(name, bm)
    mat = _textured(name, _onion_texture(), None, base_rough=0.18)
    obj.data.materials.append(mat)
    smooth(obj, 50)
    set_origin_bottom(obj)
    return obj


# ------------------------------------------------------------------ pickles (crinkle cut)

def _pickle_texture(seed=6):
    x, y, r, t = _grid()
    n = _noise(RES, 18, seed)
    col = np.zeros((RES, RES, 3), np.float32)
    col[:] = np.array([0.56, 0.60, 0.24]) * (0.9 + 0.2 * n[..., None])
    seedbed = r < 0.5
    col[seedbed] = (np.array([0.68, 0.70, 0.36]) * (0.92 + 0.12 * n[..., None]))[seedbed]
    skin = r > 0.86
    stripe = (np.sin(t * 22) > 0.2)
    col[skin] = np.array([0.15, 0.27, 0.06])
    col[skin & stripe] = np.array([0.24, 0.36, 0.10])
    rng = np.random.default_rng(seed)
    cs, angs = [], []
    for k in range(3):
        base = k * math.tau / 3 + 0.4
        for _ in range(5):
            rr = 0.22 + 0.16 * rng.random()
            aa = base + (rng.random() - 0.5) * 0.7
            cs.append((rr * math.cos(aa), rr * math.sin(aa)))
            angs.append(aa)
    _ellipses(col, None, cs, 0.07, 0.035, angs, np.array([0.86, 0.84, 0.62]))
    rough = np.full((RES, RES), 0.34, np.float32)
    return col, rough


def pickles(name='pickles', count=3, radius=0.0165, thickness=0.0032, seed=6):
    color, rough = _pickle_texture(seed)
    mat = _textured(name, color, rough)
    pieces = []
    for i in range(count):
        crinkle = lambda t: 1 + 0.035 * math.sin(t * 16)
        p = disc_mesh(f'{name}_{i}', radius, thickness, cuts=10, radius_fn=crinkle, bevel=0.3)
        planar_uv(p)
        a = i * math.tau / count + 0.5
        p.location = (math.cos(a) * 0.026, math.sin(a) * 0.026, thickness / 2 + i * 0.0004)
        p.rotation_euler = (0.012 * (i - 1), 0.015, a)
        pieces.append(p)
    activate(pieces[0])
    for p in pieces[1:]:
        p.select_set(True)
    bpy.ops.object.join()
    obj = pieces[0]
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    smooth(obj, 50)
    set_origin_bottom(obj)
    return obj


# ------------------------------------------------------------------ lettuce (butter lettuce leaf)

def _lettuce_texture(seed=7):
    x, y, r, t = _grid()
    n = _noise(RES, 30, seed)
    centre = np.array([0.60, 0.74, 0.30])
    edge = np.array([0.20, 0.42, 0.07])
    f = np.clip(r, 0, 1)[..., None] ** 1.3
    col = centre * (1 - f) + edge * f
    col = col * (0.88 + 0.22 * n[..., None])
    rng = np.random.default_rng(seed)
    veins = np.zeros_like(r)
    for k in range(9):
        a = k * math.tau / 9 + rng.random() * 0.3
        d = np.abs(np.sin(t - a)) * r
        same_side = np.cos(t - a) > 0
        w = 0.012 * (1.15 - r)
        veins = np.maximum(veins, np.where(same_side, np.clip(1 - d / np.maximum(w, 1e-4), 0, 1), 0))
    vein_col = np.array([0.80, 0.88, 0.58])
    col = col * (1 - veins[..., None] * 0.8) + vein_col * veins[..., None] * 0.8
    rough = (0.55 + 0.15 * n).astype(np.float32)
    return col.astype(np.float32), rough


def lettuce(name='lettuce', radius=0.062, seed=7):
    rng = np.random.default_rng(seed)
    ph = rng.random(4) * math.tau
    edge = lambda t: 1 + 0.06 * math.sin(5 * t + ph[0]) + 0.04 * math.sin(11 * t + ph[1])
    obj = disc_mesh(name, radius, 0.0008, cuts=56, radius_fn=edge, bevel=0, smooth_level=0)
    for v in obj.data.vertices:
        x, y = v.co.x, v.co.y
        r = math.hypot(x, y) / radius
        t = math.atan2(y, x)
        k = (max(0.0, r - 0.4) / 0.6) ** 2.0
        ruffle = k * (0.0065 * math.sin(t * 13 + 3 * math.sin(t * 3 + ph[2]))
                      + 0.0022 * math.sin(t * 37 + r * 40 + ph[3])          # crinkles
                      + 0.0012 * math.sin(r * 90 + t * 5))
        dome = -0.004 * r * r                       # edges curl down over the burger
        v.co.z += ruffle + dome
    planar_uv(obj)
    solid = obj.modifiers.new('solid', 'SOLIDIFY')
    solid.thickness = 0.0007
    sub = obj.modifiers.new('sub', 'SUBSURF')
    sub.levels = 1
    activate(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    color, rough = _lettuce_texture(seed)
    obj.data.materials.append(_textured(name, color, rough))
    smooth(obj, 80)
    set_origin_bottom(obj)
    obj['stack_h'] = 0.004
    return obj


# ------------------------------------------------------------------ sauce

def sauce(name='sauce', radius=0.044, color=(0.80, 0.36, 0.14), seed=8):
    rng = np.random.default_rng(seed)
    ph = rng.random(3) * math.tau
    edge = lambda t: 1 + 0.08 * math.sin(4 * t + ph[0]) + 0.05 * math.sin(9 * t + ph[1])
    obj = disc_mesh(name, radius, 0.0022, cuts=14, radius_fn=edge, bevel=0.5, smooth_level=1)
    mat, nt, bsdf = node_material(name)
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = 0.12
    obj.data.materials.append(mat)
    smooth(obj, 80)
    set_origin_bottom(obj)
    obj['stack_h'] = 0.0008
    return obj
