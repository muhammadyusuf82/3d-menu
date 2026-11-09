"""Ingredient builders for burgers. Each returns an object whose origin is its bottom centre (z = 0)."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from lib import (ASSETS, activate, apply_modifiers, array_to_image, bake, disc_mesh, image_from_array, image_to_array,
                 link, new_object, node_material, planar_uv, set_origin_bottom, smooth, tex_node, uv_unwrap)

BUN_SCAN = f'{ASSETS}/polyhaven/hamburger_buns/hamburger_buns.gltf'


# ------------------------------------------------------------------ bun (real Poly Haven scan, cut in half)

def _crumb_material():
    mat, nt, bsdf = node_material('crumb')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    pores = nt.nodes.new('ShaderNodeTexVoronoi')
    pores.inputs['Scale'].default_value = 300
    link(nt, coord.outputs['Object'], pores.inputs['Vector'])
    fine = nt.nodes.new('ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 900
    fine.inputs['Detail'].default_value = 8
    link(nt, coord.outputs['Object'], fine.inputs['Vector'])
    toast = nt.nodes.new('ShaderNodeTexNoise')
    toast.inputs['Scale'].default_value = 40
    toast.inputs['Detail'].default_value = 6
    link(nt, coord.outputs['Object'], toast.inputs['Vector'])
    # toasted cut face: golden brown with lighter crumb where less toasted
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.42, 0.19, 0.05, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.80, 0.55, 0.26, 1)
    link(nt, toast.outputs['Fac'], ramp.inputs['Fac'])
    pore_ramp = nt.nodes.new('ShaderNodeValToRGB')
    pore_ramp.color_ramp.elements[0].position = 0.02
    pore_ramp.color_ramp.elements[0].color = (0.35, 0.2, 0.08, 1)
    pore_ramp.color_ramp.elements[1].position = 0.28
    pore_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    link(nt, pores.outputs['Distance'], pore_ramp.inputs['Fac'])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    link(nt, ramp.outputs['Color'], mix.inputs['A'])
    link(nt, pore_ramp.outputs['Color'], mix.inputs['B'])
    link(nt, mix.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.82
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.0
    bump.inputs['Distance'].default_value = 0.0016
    add = nt.nodes.new('ShaderNodeMath')
    add.operation = 'ADD'
    link(nt, pores.outputs['Distance'], add.inputs[0])
    link(nt, fine.outputs['Fac'], add.inputs[1])
    link(nt, add.outputs['Value'], bump.inputs['Height'])
    link(nt, bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _brioche_grade(mat):
    """The scan is a pale bread roll: grade its photo texture to a golden, egg-washed brioche crust."""
    for node in mat.node_tree.nodes:
        if node.type != 'TEX_IMAGE' or not node.image:
            continue
        img = node.image
        a = image_to_array(img)
        if img.colorspace_settings.name == 'sRGB' and 'arm' not in img.name.lower():
            rgb = a[..., :3]
            lum = rgb.mean(axis=2, keepdims=True)
            # deeper where the crust is already darker, keep highlights warm
            golden = np.array([1.0, 0.80, 0.56], np.float32)
            a[..., :3] = np.clip((rgb * 0.5 + lum * 0.5) ** 1.12 * golden, 0, 1)
        elif 'arm' in img.name.lower():
            a[..., 1] *= 0.58  # glossier (egg wash): roughness lives in the green channel
        array_to_image(img, a)


def sesame(obj, count=70, seed=3):
    """Scatters sesame seeds on the dome of a bun-top by ray-casting straight down onto it."""
    rng = np.random.default_rng(seed)
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    radius = (max(xs) - min(xs)) / 2 * 0.78
    top = max(v.co.z for v in me.vertices) + 0.01
    bm = bmesh.new()
    placed = 0
    tries = 0
    while placed < count and tries < count * 6:
        tries += 1
        rr = radius * math.sqrt(rng.random())
        th = rng.random() * math.tau
        origin = Vector((rr * math.cos(th), rr * math.sin(th), top))
        hit, loc, nrm, _ = obj.ray_cast(origin, Vector((0, 0, -1)))
        if not hit or nrm.z < 0.35:
            continue
        seed_bm = bmesh.new()
        bmesh.ops.create_uvsphere(seed_bm, u_segments=10, v_segments=6, radius=1)
        bmesh.ops.scale(seed_bm, vec=(0.0021, 0.0011, 0.0006), verts=seed_bm.verts)
        rot = nrm.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(rng.random() * math.tau, 4, 'Z')
        bmesh.ops.transform(seed_bm, matrix=Matrix.Translation(loc + nrm * 0.0003) @ rot, verts=seed_bm.verts)
        tmp = bpy.data.meshes.new('tmp')
        seed_bm.to_mesh(tmp)
        seed_bm.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        placed += 1
    seeds = new_object('sesame', bm)
    seeds.matrix_world = obj.matrix_world.copy()  # seeds were placed in the bun's local coordinates
    mat, _, bsdf = node_material('sesame')
    bsdf.inputs['Base Color'].default_value = (0.92, 0.80, 0.56, 1)
    bsdf.inputs['Roughness'].default_value = 0.45
    seeds.data.materials.append(mat)
    smooth(seeds, 80)
    activate(obj)
    seeds.select_set(True)
    name = obj.name
    bpy.ops.object.join()
    obj.name = name
    return obj


def bun_halves(cut=0.40, which='hamburger_buns_02'):
    """Imports the scanned bun, cuts it horizontally and caps both cut faces with a toasted crumb surface."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=BUN_SCAN)
    imported = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in imported if o.type == 'MESH' and o.name.startswith(which))
    for o in imported:
        if o is not src:
            bpy.data.objects.remove(o, do_unlink=True)
    activate(src)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    set_origin_bottom(src)
    src.location = (0, 0, 0)
    _brioche_grade(src.data.materials[0])
    height = max(v.co.z for v in src.data.vertices)
    zc = height * cut
    crumb = _crumb_material()

    halves = {}
    for name, keep_top in (('bun-bottom', False), ('bun-top', True)):
        obj = src.copy()
        obj.data = src.data.copy()
        obj.name = name
        bpy.context.scene.collection.objects.link(obj)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, zc), plane_no=(0, 0, 1),
                               clear_inner=keep_top, clear_outer=not keep_top)
        # the scan is open underneath (it was scanned sitting on a table), so close every hole, not just the cut
        filled = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
        tri = bmesh.ops.triangulate(bm, faces=filled['faces'], quad_method='BEAUTY', ngon_method='BEAUTY')
        cap_faces = tri['faces']
        crumb_index = len(obj.data.materials)
        for f in cap_faces:
            f.material_index = crumb_index
            f.normal_update()
            on_cut = abs(f.calc_center_median().z - zc) < height * 0.05
            # the cut face of the top half points down, the bottom half's up; the old scan hole is the underside
            want_up = (not keep_top) if on_cut else False
            if (f.normal.z > 0) != want_up:
                f.normal_flip()
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.materials.append(crumb)
        # bake only the crumb cap into its own texture: separate it, bake, join back (scan textures stay untouched)
        activate(obj)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for p in obj.data.polygons:
            p.select = p.material_index == crumb_index
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        cap = next(o for o in bpy.context.selected_objects if o is not obj)
        cap.data.materials.clear()
        cap.data.materials.append(crumb)
        for p in cap.data.polygons:
            p.material_index = 0
        planar_uv(cap)
        bake(cap, res=1024, roughness=False)
        activate(obj)
        cap.select_set(True)
        bpy.ops.object.join()
        obj.name = name
        obj.data.validate(clean_customdata=False)  # holes_fill can leave degenerate faces glTF export warns about
        smooth(obj, 35)
        set_origin_bottom(obj)
        if keep_top:
            sesame(obj)
        halves[name] = obj
    bpy.data.objects.remove(src, do_unlink=True)
    return halves['bun-bottom'], halves['bun-top']


# ------------------------------------------------------------------ patty

def _patty_material(name='patty', tone=1.0):
    mat, nt, bsdf = node_material(name)
    mat['spec'] = 0.3  # baked material keeps a softer specular sheen
    coord = nt.nodes.new('ShaderNodeTexCoord')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    big = nt.nodes.new('ShaderNodeTexNoise')
    big.inputs['Scale'].default_value = 55
    big.inputs['Detail'].default_value = 14
    big.inputs['Roughness'].default_value = 0.68
    link(nt, coord.outputs['Object'], big.inputs['Vector'])
    bits = nt.nodes.new('ShaderNodeTexVoronoi')
    bits.inputs['Scale'].default_value = 260
    link(nt, coord.outputs['Object'], bits.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.28, (0.016 * tone, 0.007 * tone, 0.004 * tone, 1)
    els[1].position, els[1].color = 0.56, (0.11 * tone, 0.042 * tone, 0.016 * tone, 1)
    e = els.new(0.80)
    e.color = (0.25 * tone, 0.11 * tone, 0.045 * tone, 1)
    link(nt, big.outputs['Fac'], ramp.inputs['Fac'])
    # seared top/bottom are darker than the sides
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    link(nt, geo.outputs['Normal'], sep.inputs['Vector'])
    absz = nt.nodes.new('ShaderNodeMath')
    absz.operation = 'ABSOLUTE'
    link(nt, sep.outputs['Z'], absz.inputs[0])
    sear = nt.nodes.new('ShaderNodeMix')
    sear.data_type = 'RGBA'
    sear.blend_type = 'MULTIPLY'
    sear.inputs['B'].default_value = (0.62, 0.46, 0.34, 1)
    link(nt, absz.outputs['Value'], sear.inputs['Factor'])
    link(nt, ramp.outputs['Color'], sear.inputs['A'])
    crisp = nt.nodes.new('ShaderNodeMix')
    crisp.data_type = 'RGBA'
    crisp.blend_type = 'MULTIPLY'
    crisp_ramp = nt.nodes.new('ShaderNodeMath')
    crisp_ramp.operation = 'LESS_THAN'
    crisp_ramp.inputs[1].default_value = 0.12
    link(nt, bits.outputs['Distance'], crisp_ramp.inputs[0])
    link(nt, crisp_ramp.outputs['Value'], crisp.inputs['Factor'])
    crisp.inputs['B'].default_value = (0.4, 0.27, 0.2, 1)
    link(nt, sear.outputs['Result'], crisp.inputs['A'])
    link(nt, crisp.outputs['Result'], bsdf.inputs['Base Color'])
    # juicy: glossy fat patches on a mostly rough surface
    gloss = nt.nodes.new('ShaderNodeTexNoise')
    gloss.inputs['Scale'].default_value = 90
    link(nt, coord.outputs['Object'], gloss.inputs['Vector'])
    rr = nt.nodes.new('ShaderNodeMapRange')
    rr.inputs['From Min'].default_value = 0.45
    rr.inputs['From Max'].default_value = 0.65
    rr.inputs['To Min'].default_value = 0.72
    rr.inputs['To Max'].default_value = 0.4
    link(nt, gloss.outputs['Fac'], rr.inputs['Value'])
    link(nt, rr.outputs['Result'], bsdf.inputs['Roughness'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.7
    bump.inputs['Distance'].default_value = 0.001
    soft = nt.nodes.new('ShaderNodeMath')
    soft.operation = 'MULTIPLY'
    soft.inputs[1].default_value = 0.3
    link(nt, bits.outputs['Distance'], soft.inputs[0])
    hsum = nt.nodes.new('ShaderNodeMath')
    hsum.operation = 'ADD'
    link(nt, big.outputs['Fac'], hsum.inputs[0])
    link(nt, soft.outputs['Value'], hsum.inputs[1])
    link(nt, hsum.outputs['Value'], bump.inputs['Height'])
    link(nt, bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def patty(name='patty', radius=0.056, height=0.017, seed=1, tone=1.0):
    rng = np.random.default_rng(seed)
    phases = rng.random(4) * math.tau
    # slightly irregular hand-formed edge
    edge = lambda t: 1 + 0.018 * math.sin(3 * t + phases[0]) + 0.012 * math.sin(7 * t + phases[1]) + 0.006 * math.sin(13 * t + phases[2])
    obj = disc_mesh(name, radius, height, cuts=30, radius_fn=edge, bevel=0.42, smooth_level=1)
    tex = bpy.data.textures.new(f'{name}_lumps', 'CLOUDS')
    tex.noise_scale = 0.010
    tex.noise_depth = 3
    disp = obj.modifiers.new('lumps', 'DISPLACE')
    disp.texture, disp.strength, disp.mid_level, disp.texture_coords = tex, 0.003, 0.5, 'OBJECT'
    apply_modifiers(obj)
    smooth(obj, 80)
    uv_unwrap(obj)
    obj.data.materials.append(_patty_material(name, tone))
    bake(obj, res=1024)
    set_origin_bottom(obj)
    return obj


# ------------------------------------------------------------------ cheese (melting cheddar slice)

def cheese(name='cheese', size=0.104, thickness=0.0026, patty_r=0.056, patty_h=0.017, rot=0.35):
    """A square slice with softened corners that melts over the patty edge and hugs its side.
    The origin sits under the flat middle, so it rests on the patty top; drips hang below."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=56, y_segments=56, size=size / 2)
    obj = new_object(name, bm)
    hug = patty_r * 0.93
    for v in obj.data.vertices:
        x, y = v.co.x, v.co.y
        sq = max(abs(x), abs(y))
        sup = (x ** 4 + y ** 4) ** 0.25 or 1
        x, y = x * sq / sup, y * sq / sup          # square -> squircle (soft corners)
        r = math.hypot(x, y)
        a = math.atan2(y, x)
        if r > hug:
            d = r - hug
            t = min(1.0, d / 0.012)
            new_r = hug + d * (1 - 0.72 * t)         # pulled in to wrap around the patty side
            # ...but never inside the patty's widest (irregular, displaced) edge, or the patty pokes through
            new_r = max(new_r, min(r, patty_r * 1.07 + 0.003))
            drop = d * (0.35 + 1.25 * t) * (1 + 0.18 * math.sin(a * 7 + 0.6))
            x, y = math.cos(a) * new_r, math.sin(a) * new_r
            v.co.z = -min(drop, patty_h * 0.85)
        v.co.x, v.co.y = x, y
    sol = obj.modifiers.new('solid', 'SOLIDIFY')
    sol.thickness, sol.offset = thickness, 1
    bev = obj.modifiers.new('bevel', 'BEVEL')
    bev.width, bev.segments = thickness * 0.45, 3
    sub = obj.modifiers.new('sub', 'SUBSURF')
    sub.levels = 1
    apply_modifiers(obj)
    obj.rotation_euler.z = rot
    activate(obj)
    bpy.ops.object.transform_apply(rotation=True)
    smooth(obj, 70)
    planar_uv(obj)  # top-down: no UV seams on the visible face (smart UV seams showed as dark cracks)
    mat, nt, bsdf = node_material(name)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 70
    n.inputs['Detail'].default_value = 6
    link(nt, coord.outputs['Object'], n.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.35, (0.72, 0.17, 0.0, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.7, (0.86, 0.27, 0.005, 1)
    link(nt, n.outputs['Fac'], ramp.inputs['Fac'])
    link(nt, ramp.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.24
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.2
    bump.inputs['Distance'].default_value = 0.0004
    link(nt, n.outputs['Fac'], bump.inputs['Height'])
    link(nt, bump.outputs['Normal'], bsdf.inputs['Normal'])
    obj.data.materials.append(mat)
    bake(obj, res=1024, roughness=False)
    obj.data.materials[0].node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.24
    set_origin_bottom(obj, z0=0.0)
    obj['stack_h'] = thickness
    return obj


# ------------------------------------------------------------------ bacon (crispy smoked strips)

def _bacon_texture(res=512, seed=9):
    """Irregular lean/fat marbling across the strip with crisp, browned edges (no candy-cane stripes)."""
    rng = np.random.default_rng(seed)
    v = np.linspace(0, 1, res, dtype=np.float32)[:, None] * np.ones((1, res), np.float32)   # across the strip
    u = np.linspace(0, 1, res, dtype=np.float32)[None, :] * np.ones((res, 1), np.float32)   # along the strip

    def smooth_noise(scale_u, scale_v):
        g = rng.random((scale_v + 2, scale_u + 2)).astype(np.float32)
        iu, iv = u * scale_u, v * scale_v
        u0, v0 = iu.astype(int), iv.astype(int)
        fu, fv = iu - u0, iv - v0
        fu, fv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)
        return (g[v0, u0] * (1 - fu) * (1 - fv) + g[v0, u0 + 1] * fu * (1 - fv)
                + g[v0 + 1, u0] * (1 - fu) * fv + g[v0 + 1, u0 + 1] * fu * fv)

    # fat runs along the strip in uneven ribbons
    ribbons = smooth_noise(3, 7) * 0.7 + smooth_noise(9, 16) * 0.3
    fat = np.clip((ribbons - 0.52) * 6, 0, 1)[..., None]
    lean = np.array([0.30, 0.055, 0.03])
    fat_col = np.array([0.80, 0.52, 0.30])
    col = lean * (1 - fat) + fat_col * fat
    browning = 0.7 + 0.35 * smooth_noise(14, 4)[..., None]
    char = np.clip((smooth_noise(24, 6) - 0.72) * 4, 0, 1)[..., None]   # crispy dark spots
    edge = np.clip(np.minimum(v, 1 - v) / 0.1, 0, 1)[..., None]
    col = col * browning * (1 - 0.55 * char) * (0.5 + 0.5 * edge)
    rough = (0.55 - 0.25 * fat[..., 0]).astype(np.float32)
    return np.clip(col, 0, 1).astype(np.float32), rough


def bacon(name='bacon', strips=2, length=0.125, width=0.03, seed=9):
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new('UVMap')
    nu, nv = 60, 6
    for s in range(strips):
        ph = rng.random(3) * math.tau
        off = 0.0
        z0 = s * 0.0022
        cross = (s - (strips - 1) / 2) * 1.1          # strips cross at ~60 degrees
        verts = []
        for i in range(nu + 1):
            t = i / nu
            x = (t - 0.5) * length
            row = []
            for j in range(nv + 1):
                w = j / nv
                y = off + (w - 0.5) * width * (1 + 0.12 * math.sin(t * 9 + ph[2]))
                # crispy ripples along the length plus a slight curl across
                z = z0 + 0.0045 * math.sin(t * 13 + ph[0]) + 0.0016 * math.sin(t * 29 + ph[1]) + 0.004 * (w - 0.5) ** 2 + 0.0012 * math.sin(t * 40 + w * 5)
                y += 0.002 * math.sin(t * 6 + ph[2])
                row.append(bm.verts.new((x * math.cos(cross) - y * math.sin(cross), x * math.sin(cross) + y * math.cos(cross), z)))
            verts.append(row)
        for i in range(nu):
            for j in range(nv):
                f = bm.faces.new((verts[i][j], verts[i + 1][j], verts[i + 1][j + 1], verts[i][j + 1]))
                for loop, (a, b) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                    loop[uv_layer].uv = (a / nu, b / nv)
    obj = new_object(name, bm)
    sol = obj.modifiers.new('solid', 'SOLIDIFY')
    sol.thickness = 0.0018
    apply_modifiers(obj)
    obj.rotation_euler.z = 0.5
    activate(obj)
    bpy.ops.object.transform_apply(rotation=True)
    color, rough = _bacon_texture(seed=seed)
    mat, nt, bsdf = node_material(name)
    c = nt.nodes.new('ShaderNodeTexImage')
    c.image = image_from_array(f'{name}_color', color)
    link(nt, c.outputs['Color'], bsdf.inputs['Base Color'])
    r = nt.nodes.new('ShaderNodeTexImage')
    r.image = image_from_array(f'{name}_rough', np.repeat(rough[..., None], 3, axis=2), non_color=True)
    link(nt, r.outputs['Color'], bsdf.inputs['Roughness'])
    obj.data.materials.append(mat)
    smooth(obj, 60)
    set_origin_bottom(obj)
    return obj
