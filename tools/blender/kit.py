"""
Generic modelling kit for HD dishes: instanced pieces, sweeps, revolves, ray-cast placement, rigid-body settling,
draped melts, painted textures and compact node-material builders. All units are metres; transforms are applied
(objects sit at identity unless stated) so local and world coordinates match.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from lib import activate, apply_modifiers, image_from_array, link, new_object, node_material, set_origin_bottom, \
    smooth, tex_node

# ================================================================== numpy textures

def vnoise(res, scale, seed, aspect=1.0):
    """Smooth value noise in [0,1], `scale` cells across (x), `scale*aspect` down (y); smoothstep interpolation."""
    rng = np.random.default_rng(seed)
    sy = max(1, int(round(scale * aspect)))
    g = rng.random((sy + 2, scale + 2)).astype(np.float32)
    xs = np.linspace(0, scale, res, dtype=np.float32)
    ys = np.linspace(0, sy, res, dtype=np.float32)
    x0 = np.floor(xs).astype(int).clip(0, scale)
    y0 = np.floor(ys).astype(int).clip(0, sy)
    fx = xs - x0
    fy = ys - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    fx = fx[None, :]
    fy = fy[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(res, scale, seed, octaves=4, gain=0.5, aspect=1.0):
    out = np.zeros((res, res), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        out += vnoise(res, scale * 2 ** o, seed + o * 17, aspect) * amp
        total += amp
        amp *= gain
    return out / total


def cells(res, count, seed, jitter=1.0):
    """Worley-style F1/F2 distances (in texture units, tileable) for ~count jittered points: one point per grid cell,
    searched in the 3x3 neighbouring cells (fast enough for thousands of cells)."""
    n = max(1, int(round(math.sqrt(count))))
    rng = np.random.default_rng(seed)
    pts = (np.arange(n)[:, None, None] + np.stack(np.meshgrid(np.arange(n), np.arange(n), indexing='ij'), -1)[..., ::-1][..., :] * 0)
    jit = rng.random((n, n, 2)).astype(np.float32) * jitter + (1 - jitter) * 0.5
    lin = (np.arange(res, dtype=np.float32) + 0.5) / res * n
    x, y = np.meshgrid(lin, lin)
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    f1 = np.full((res, res), 9.0, np.float32)
    f2 = np.full((res, res), 9.0, np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            j = jit[cy % n, cx % n]
            d = np.hypot(x - (cx + j[..., 0]), y - (cy + j[..., 1])) / n
            f2 = np.where(d < f1, f1, np.minimum(f2, d))
            f1 = np.minimum(f1, d)
    del pts
    return f1, f2


def height_to_normal(h, strength=1.0):
    """Tangent-space (OpenGL, +Y up) normal map from a height field whose row 0 is the top of the image (v = 1)."""
    # slope per pixel (not per UV unit, which would explode with resolution); strength 1 ~ gentle bumps
    dx = np.gradient(h, axis=1) * 8.0
    dy = -np.gradient(h, axis=0) * 8.0
    n = np.stack([-dx * strength, -dy * strength, np.ones_like(h)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return (n * 0.5 + 0.5).astype(np.float32)


def grid(res):
    """Normalised coords x, y in [-1, 1] (row 0 = top = +y), radius r and angle t."""
    lin = np.linspace(-1, 1, res, dtype=np.float32)
    x, y = np.meshgrid(lin, -lin)
    return x, y, np.hypot(x, y), np.arctan2(y, x)


def lerp_color(a, b, f):
    f = np.asarray(f, np.float32)[..., None]
    return np.asarray(a, np.float32) * (1 - f) + np.asarray(b, np.float32) * f


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ================================================================== materials

def solid(name, color, rough=0.5, spec=0.5, metal=0.0, alpha=1.0, transmission=0.0, ior=1.45, coat=0.0, vcol=False):
    mat, nt, bsdf = node_material(name)
    bsdf.inputs['Base Color'].default_value = (*color[:3], 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Specular IOR Level'].default_value = spec
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['IOR'].default_value = ior
    if transmission:
        bsdf.inputs['Transmission Weight'].default_value = transmission
    if coat:
        bsdf.inputs['Coat Weight'].default_value = coat
    if alpha < 1:
        bsdf.inputs['Alpha'].default_value = alpha
        for attr, value in (('blend_method', 'BLEND'), ('surface_render_method', 'BLENDED')):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, value)
                except (TypeError, AttributeError):
                    pass
    if vcol:
        attr = nt.nodes.new('ShaderNodeVertexColor')
        attr.layer_name = 'Col'
        link(nt, attr.outputs['Color'], bsdf.inputs['Base Color'])
    mat['spec'] = spec
    return mat


def glass(name='glass', tint=(0.97, 0.99, 1.0), rough=0.02):
    """Clear glass: exports as KHR_materials_transmission (three.js MeshPhysicalMaterial.transmission)."""
    return solid(name, tint, rough=rough, spec=0.5, transmission=1.0, ior=1.5)


def textured(name, color, rough=None, normal=None, base_rough=0.5, spec=0.5, normal_strength=1.0):
    """Material from numpy arrays (HxWx3 colour, HxW roughness, HxWx3 normal map)."""
    mat, nt, bsdf = node_material(name)
    c = tex_node(nt, image_from_array(f'{name}_color', color), -700, 300)
    link(nt, c.outputs['Color'], bsdf.inputs['Base Color'])
    if rough is not None:
        r = tex_node(nt, image_from_array(f'{name}_rough', np.repeat(rough[..., None], 3, axis=2), non_color=True), -700, 0)
        link(nt, r.outputs['Color'], bsdf.inputs['Roughness'])
    else:
        bsdf.inputs['Roughness'].default_value = base_rough
    if normal is not None:
        n = tex_node(nt, image_from_array(f'{name}_normal', normal, non_color=True), -700, -300)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normal_strength
        link(nt, n.outputs['Color'], nm.inputs['Color'])
        link(nt, nm.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Specular IOR Level'].default_value = spec
    mat['spec'] = spec
    return mat


class Shader:
    """Tiny builder for procedural node materials that are baked afterwards (see lib.bake)."""

    def __init__(self, name, spec=0.5):
        self.mat, self.nt, self.bsdf = node_material(name)
        self.mat['spec'] = spec
        self.coord = self.nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
        self.geo = self.nt.nodes.new('ShaderNodeNewGeometry')

    def node(self, kind, **inputs):
        n = self.nt.nodes.new(kind)
        for k, v in inputs.items():
            if hasattr(v, 'is_linked') or hasattr(v, 'links'):
                link(self.nt, v, n.inputs[k])
            else:
                n.inputs[k].default_value = v
        return n

    def noise(self, scale, detail=6.0, rough=0.55, vec=None, distortion=0.0):
        n = self.node('ShaderNodeTexNoise', Scale=scale, Detail=detail, Roughness=rough, Distortion=distortion)
        link(self.nt, vec or self.coord, n.inputs['Vector'])
        return n.outputs['Fac']

    def voronoi(self, scale, vec=None, out='Distance', feature='F1', rand=1.0):
        n = self.nt.nodes.new('ShaderNodeTexVoronoi')
        n.feature = feature
        n.inputs['Scale'].default_value = scale
        n.inputs['Randomness'].default_value = rand
        link(self.nt, vec or self.coord, n.inputs['Vector'])
        return n.outputs[out]

    def wave(self, scale, vec=None, distortion=4.0, detail=3.0, bands='X'):
        n = self.nt.nodes.new('ShaderNodeTexWave')
        n.bands_direction = bands
        n.inputs['Scale'].default_value = scale
        n.inputs['Distortion'].default_value = distortion
        n.inputs['Detail'].default_value = detail
        link(self.nt, vec or self.coord, n.inputs['Vector'])
        return n.outputs['Fac']

    def ramp(self, fac, stops):
        """stops: [(pos, (r, g, b)), ...] -> colour socket."""
        n = self.nt.nodes.new('ShaderNodeValToRGB')
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = (*col[:3], 1)
        link(self.nt, fac, n.inputs['Fac'])
        return n.outputs['Color']

    def math(self, op, a, b=0.0, clamp=False):
        n = self.nt.nodes.new('ShaderNodeMath')
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if hasattr(v, 'links') or hasattr(v, 'is_linked'):
                link(self.nt, v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs['Value']

    def maprange(self, v, a, b, c, d, clamp=True):
        n = self.nt.nodes.new('ShaderNodeMapRange')
        n.clamp = clamp
        link(self.nt, v, n.inputs['Value'])
        for k, val in zip(('From Min', 'From Max', 'To Min', 'To Max'), (a, b, c, d)):
            n.inputs[k].default_value = val
        return n.outputs['Result']

    def mix(self, a, b, fac, blend='MIX'):
        n = self.nt.nodes.new('ShaderNodeMix')
        n.data_type = 'RGBA'
        n.blend_type = blend
        for key, v in (('A', a), ('B', b), ('Factor', fac)):
            if hasattr(v, 'links') or hasattr(v, 'is_linked'):
                link(self.nt, v, n.inputs[key])
            else:
                n.inputs[key].default_value = (*v[:3], 1) if key != 'Factor' else v
        return n.outputs['Result']

    def up(self):
        """Normal z component (1 = facing up), for seared tops, browned crusts, dust that settles on top."""
        sep = self.nt.nodes.new('ShaderNodeSeparateXYZ')
        link(self.nt, self.geo.outputs['Normal'], sep.inputs['Vector'])
        return sep.outputs['Z']

    def length(self, vec=None):
        """Distance from the object origin (radial gradients: fruit flesh, doneness of steak...)."""
        n = self.nt.nodes.new('ShaderNodeVectorMath')
        n.operation = 'LENGTH'
        link(self.nt, vec or self.coord, n.inputs[0])
        return n.outputs['Value']

    def position(self, axis='Z'):
        sep = self.nt.nodes.new('ShaderNodeSeparateXYZ')
        link(self.nt, self.coord, sep.inputs['Vector'])
        return sep.outputs[axis]

    def out(self, color, rough=0.5, height=None, strength=0.5, distance=0.001):
        for key, v in (('Base Color', color), ('Roughness', rough)):
            if hasattr(v, 'links') or hasattr(v, 'is_linked'):
                link(self.nt, v, self.bsdf.inputs[key])
            elif key == 'Roughness':
                self.bsdf.inputs[key].default_value = v
            else:
                self.bsdf.inputs[key].default_value = (*v[:3], 1)
        if height is not None:
            b = self.node('ShaderNodeBump', Strength=strength, Distance=distance)
            link(self.nt, height, b.inputs['Height'])
            link(self.nt, b.outputs['Normal'], self.bsdf.inputs['Normal'])
        return self.mat


# ================================================================== meshes from arrays / instancing

def mesh_from_arrays(name, verts, faces, loop_uvs=None, vcols=None, smooth_shade=True):
    """verts Nx3, faces list of index tuples, loop_uvs (sum(len(f)))x2 aligned with faces, vcols Nx3 per vertex."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in np.asarray(verts, np.float64)], [], [tuple(int(i) for i in f) for f in faces])
    if loop_uvs is not None:
        uv = me.uv_layers.new(name='UVMap')
        uv.data.foreach_set('uv', np.asarray(loop_uvs, np.float32).ravel())
    if vcols is not None:
        attr = me.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
        rgba = np.concatenate([np.asarray(vcols, np.float32), np.ones((len(vcols), 1), np.float32)], axis=1)
        attr.data.foreach_set('color', rgba.ravel())
    me.update()
    if smooth_shade:
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def template(bm_or_obj):
    """(verts, faces, loop_uvs) of a bmesh or mesh object, used as an instancing template."""
    if isinstance(bm_or_obj, bmesh.types.BMesh):
        me = bpy.data.meshes.new('tpl')
        bm_or_obj.to_mesh(me)
        bm_or_obj.free()
        temp = True
    else:
        me = bm_or_obj.data
        temp = False
    verts = np.array([v.co[:] for v in me.vertices], np.float32)
    faces = [tuple(p.vertices) for p in me.polygons]
    uvs = None
    if me.uv_layers:
        uvs = np.array([d.uv[:] for d in me.uv_layers.active.data], np.float32)
    if temp:
        bpy.data.meshes.remove(me)
    return verts, faces, uvs


def instances(name, tpl, matrices, colors=None, uv_offsets=None):
    """Joins many copies of a template into one mesh. matrices: list of 4x4 (mathutils or numpy).
    colors: per-instance RGB -> vertex colour attribute 'Col'. uv_offsets: per-instance (du, dv) to vary texture."""
    tv, tf, tuv = tpl
    k = len(tv)
    homo = np.concatenate([tv, np.ones((k, 1), np.float32)], axis=1)
    verts, faces, uvs, cols = [], [], [], []
    for i, m in enumerate(matrices):
        m = np.array(m, np.float32)
        verts.append((homo @ m.T)[:, :3])
        faces.extend(tuple(j + i * k for j in f) for f in tf)
        if tuv is not None:
            uvs.append(tuv + (np.array(uv_offsets[i], np.float32) if uv_offsets is not None else 0))
        if colors is not None:
            cols.append(np.repeat(np.asarray(colors[i], np.float32)[None, :3], k, axis=0))
    return mesh_from_arrays(name, np.concatenate(verts), faces,
                            np.concatenate(uvs) if uvs else None,
                            np.concatenate(cols) if cols else None)


def frame(loc, normal=(0, 0, 1), spin=0.0, scale=(1, 1, 1), tilt=(0.0, 0.0)):
    """4x4: scale, then tilt (x, y), spin about the normal, align +Z with `normal`, translate to `loc`."""
    n = Vector(normal).normalized()
    align = n.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    m = (Matrix.Translation(Vector(loc)) @ align @ Matrix.Rotation(spin, 4, 'Z')
         @ Matrix.Rotation(tilt[0], 4, 'X') @ Matrix.Rotation(tilt[1], 4, 'Y') @ Matrix.Diagonal((*scale, 1)))
    return m


def ellipsoid_tpl(rx, ry, rz, u=8, v=5):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=1.0, calc_uvs=True)
    bmesh.ops.scale(bm, vec=(rx, ry, rz), verts=bm.verts)
    return template(bm)


# ================================================================== sweeps and revolves

def _frames(points):
    """Parallel-transport frames along a polyline: tangents, normals, binormals (numpy)."""
    p = np.asarray(points, np.float64)
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    ref = np.array([0, 0, 1.0]) if abs(t[0][2]) < 0.9 else np.array([1.0, 0, 0])
    n = np.cross(t[0], ref)
    n /= np.linalg.norm(n)
    ns, bs = [], []
    for i in range(len(p)):
        if i:
            n = n - t[i] * np.dot(n, t[i])
            n /= np.linalg.norm(n) + 1e-12
        b = np.cross(t[i], n)
        ns.append(n.copy())
        bs.append(b)
    return t, np.array(ns), np.array(bs)


def sweep(name, points, radius, sides=10, profile=None, caps=True, twist=0.0):
    """Tube along a polyline. radius: float or per-point list. profile(angle)->radius factor (e.g. star-piped cream).
    UVs: u around, v along (in metres * 20, so textures tile by length)."""
    p = np.asarray(points, np.float64)
    rad = np.full(len(p), radius) if np.isscalar(radius) else np.asarray(radius, np.float64)
    _, ns, bs = _frames(p)
    verts, faces, uvs = [], [], []
    seg_len = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    ring = sides + 1  # duplicated seam column for clean UVs
    for i in range(len(p)):
        for j in range(ring):
            a = j / sides * math.tau + twist * i
            f = profile(a) if profile else 1.0
            verts.append(p[i] + (ns[i] * math.cos(a) + bs[i] * math.sin(a)) * rad[i] * f)
    for i in range(len(p) - 1):
        for j in range(sides):
            a, b = i * ring + j, i * ring + j + 1
            c, d = (i + 1) * ring + j + 1, (i + 1) * ring + j
            faces.append((a, b, c, d))
            uvs += [(j / sides, seg_len[i] * 20), ((j + 1) / sides, seg_len[i] * 20),
                    ((j + 1) / sides, seg_len[i + 1] * 20), (j / sides, seg_len[i + 1] * 20)]
    if caps:
        for end, idx in ((0, 0), (1, len(p) - 1)):
            c = len(verts)
            verts.append(p[idx])
            for j in range(sides):
                a, b = idx * ring + j, idx * ring + j + 1
                faces.append((c, b, a) if end == 0 else (c, a, b))
                uvs += [(0.5, 0.5)] * 3
    obj = mesh_from_arrays(name, verts, faces, uvs)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=1e-7)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def revolve(name, profile, segments=96, uv='planar'):
    """Surface of revolution around Z from a list of (r, z) points (use r = 0 at the axis for closed ends).
    uv: 'planar' (top-down, for plates and patterns) or 'wrap' (u around, v along the profile)."""
    prof = np.asarray(profile, np.float64)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))])
    arc /= arc[-1] or 1
    verts, faces, uvs = [], [], []
    cols = segments + 1
    for i in range(cols):
        a = i / segments * math.tau
        for r, z in prof:
            verts.append((r * math.cos(a), r * math.sin(a), z))
    n = len(prof)
    rmax = max(prof[:, 0].max(), 1e-6)
    for i in range(segments):
        for j in range(n - 1):
            a, b = i * n + j, (i + 1) * n + j
            quad = (a, b, b + 1, a + 1)
            faces.append(quad)
            for q, (ci, pj) in zip(quad, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                if uv == 'planar':
                    x, y, _ = verts[q]
                    uvs.append((x / rmax * 0.5 + 0.5, y / rmax * 0.5 + 0.5))
                else:
                    uvs.append((ci / segments, arc[pj]))
    obj = mesh_from_arrays(name, verts, faces, uvs)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=1e-7)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def lathe_profile(points, steps=6):
    """Rounds a coarse (r, z) outline with Chaikin corner cutting so revolved rims look turned, not faceted."""
    p = np.asarray(points, np.float64)
    for _ in range(steps):
        q = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            q += [a * 0.75 + b * 0.25, a * 0.25 + b * 0.75]
        q.append(p[-1])
        p = np.array(q)
    return [tuple(x) for x in p]


# ================================================================== simple solids

def blob(name, radius, scale=(1, 1, 1), lumps=0.25, lump_size=0.6, subdiv=3, seed=0):
    """Organic lump: icosphere, squashed, with cloud-noise displacement (relative to radius)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    obj = new_object(name, bm)
    if lumps:
        tex = bpy.data.textures.new(f'{name}_n', 'CLOUDS')
        tex.noise_scale = radius * lump_size
        tex.noise_depth = 2
        d = obj.modifiers.new('d', 'DISPLACE')
        d.texture, d.strength, d.mid_level, d.texture_coords = tex, radius * lumps, 0.5, 'OBJECT'
        # different seed -> different noise by offsetting the texture space via an empty-less trick: move then restore
        obj.location = (seed * 1.37, seed * 0.71, seed * 0.29)
        apply_modifiers(obj)
        obj.location = (0, 0, 0)
    return obj


def rounded_box(name, size, bevel=0.2, segments=3, subdiv=0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    obj = new_object(name, bm)
    if bevel:
        b = obj.modifiers.new('b', 'BEVEL')
        b.width, b.segments = min(size) * bevel, segments
    if subdiv:
        s = obj.modifiers.new('s', 'SUBSURF')
        s.levels = subdiv
    apply_modifiers(obj)
    return obj


def displace(obj, strength, size, kind='CLOUDS', depth=2, coords='OBJECT', mid=0.5):
    tex = bpy.data.textures.new(f'{obj.name}_disp', kind)
    if hasattr(tex, 'noise_scale'):
        tex.noise_scale = size
    if hasattr(tex, 'noise_depth'):
        tex.noise_depth = depth
    d = obj.modifiers.new('disp', 'DISPLACE')
    d.texture, d.strength, d.mid_level, d.texture_coords = tex, strength, mid, coords
    apply_modifiers(obj)
    return obj


def subdivide(obj, levels=1):
    s = obj.modifiers.new('sub', 'SUBSURF')
    s.levels = levels
    apply_modifiers(obj)
    return obj


def solidify(obj, thickness, offset=-1.0):
    s = obj.modifiers.new('sol', 'SOLIDIFY')
    s.thickness, s.offset = thickness, offset
    apply_modifiers(obj)
    return obj


def apply_transform(obj):
    activate(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def join(objs, name):
    objs = [o for o in objs if o is not None]
    for o in objs:
        apply_transform(o)
    # If any piece carries vertex colours, give the others white ones: the glTF exporter writes COLOR_0 for the whole
    # mesh and three.js multiplies it into every material, so a missing (black) colour would blacken textured parts.
    if any(o.type == 'MESH' and 'Col' in o.data.color_attributes for o in objs):
        for o in objs:
            if o.type == 'MESH' and 'Col' not in o.data.color_attributes:
                a = o.data.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
                a.data.foreach_set('color', [1.0] * 4 * len(o.data.vertices))
    activate(objs[0])
    for o in objs[1:]:
        o.select_set(True)
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name
    return obj


def duplicate(obj, name=None):
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = name or obj.name + '_dup'
    bpy.context.scene.collection.objects.link(new)
    return new


def transform(obj, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    """Sets a transform and applies it to the mesh (objects stay at identity)."""
    if scale is not None:
        obj.scale = scale if hasattr(scale, '__len__') else (scale,) * 3
    obj.rotation_euler = rot
    obj.location = loc
    return apply_transform(obj)


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def bounds(objs):
    lo = np.array([1e9] * 3)
    hi = -lo
    for o in objs if isinstance(objs, (list, tuple)) else [objs]:
        if o.type != 'MESH' or not o.data.vertices:
            continue
        v = np.array([(o.matrix_world @ x.co)[:] for x in o.data.vertices])
        lo, hi = np.minimum(lo, v.min(0)), np.maximum(hi, v.max(0))
    return lo, hi


def remove(obj):
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)


# ================================================================== placement on surfaces

def ray_down(targets, x, y, top=2.0):
    """Highest hit of a vertical ray at (x, y) on any target: (location, normal) or None."""
    best = None
    for t in targets:
        inv = t.matrix_world.inverted()
        o = inv @ Vector((x, y, top))
        d = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
        hit, loc, nrm, _ = t.ray_cast(o, d)
        if hit:
            loc = t.matrix_world @ loc
            nrm = (inv.transposed().to_3x3() @ nrm).normalized()
            if best is None or loc.z > best[0].z:
                best = (loc, nrm)
    return best


def scatter(name, targets, tpl, count, region, rng, scale=(0.8, 1.2), embed=0.3, min_up=0.25, align=0.8,
            colors=None, tilt=0.4, spacing=0.0, max_tries=20):
    """Drops `count` template pieces onto the highest surface of `targets` inside region(rng) -> (x, y).
    embed: fraction of the piece height sunk into the surface; align: 0 = upright, 1 = follow surface normal.
    colors: callable(rng) -> rgb per piece (vertex colours)."""
    tv = tpl[0]
    piece_h = float(tv[:, 2].max() - tv[:, 2].min())
    mats, cols, placed = [], [], []
    tries = 0
    while len(mats) < count and tries < count * max_tries:
        tries += 1
        x, y = region(rng)
        if spacing and any((x - px) ** 2 + (y - py) ** 2 < spacing ** 2 for px, py in placed):
            continue
        hit = ray_down(targets, x, y)
        if not hit or hit[1].z < min_up:
            continue
        loc, nrm = hit
        n = Vector((0, 0, 1)).lerp(nrm, align).normalized()
        s = rng.uniform(*scale)
        m = frame(loc + n * (piece_h * s * (0.5 - embed)), n, rng.random() * math.tau, (s, s, s),
                  ((rng.random() - 0.5) * tilt, (rng.random() - 0.5) * tilt))
        mats.append(m)
        placed.append((x, y))
        if colors:
            cols.append(colors(rng))
    if not mats:
        raise RuntimeError(f'scatter {name}: nothing placed')
    return instances(name, tpl, mats, cols if colors else None)


def disc_region(radius, cx=0.0, cy=0.0, ry=None):
    ry = ry or radius
    def f(rng):
        r = math.sqrt(rng.random())
        a = rng.random() * math.tau
        return cx + radius * r * math.cos(a), cy + ry * r * math.sin(a)
    return f


def rect_region(x0, x1, y0, y1):
    return lambda rng: (rng.uniform(x0, x1), rng.uniform(y0, y1))


def drape(name, targets, extent, inside, offset=0.0006, res=120, thickness=0.0015, floor=None, smooth_iter=8,
          center=(0.0, 0.0)):
    """A sheet dropped from above onto `targets` (melted cheese, syrup, sauce coats).
    extent: half size of the sampling square; inside(x, y) -> bool keeps the sheet's footprint.
    Points that miss everything fall to `floor` (or are dropped)."""
    cx, cy = center
    xs = np.linspace(-extent, extent, res) + cx
    ys = np.linspace(-extent, extent, res) + cy
    idx = -np.ones((res, res), int)
    verts = []
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            if not inside(x - cx, y - cy):
                continue
            hit = ray_down(targets, x, y)
            if hit:
                z = hit[0].z + offset
            elif floor is not None:
                z = floor + offset
            else:
                continue
            idx[i, j] = len(verts)
            verts.append((x, y, z))
    faces, uvs = [], []
    for i in range(res - 1):
        for j in range(res - 1):
            q = (idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j])
            if min(q) >= 0:
                faces.append(q)
                uvs += [((xs[jj] - cx) / extent * 0.5 + 0.5, (ys[ii] - cy) / extent * 0.5 + 0.5)
                        for ii, jj in ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))]
    obj = mesh_from_arrays(name, verts, faces, uvs)
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.delete_loose()
    bpy.ops.object.mode_set(mode='OBJECT')
    if smooth_iter:
        sm = obj.modifiers.new('sm', 'SMOOTH')
        sm.iterations, sm.factor = smooth_iter, 0.5
        sm.use_x = sm.use_y = False   # smooth heights only: keep the footprint
    if thickness:
        sol = obj.modifiers.new('sol', 'SOLIDIFY')
        sol.thickness, sol.offset = thickness, 1.0
    apply_modifiers(obj)
    return obj


def settle(dynamic, passive, frames=90, shape='CONVEX_HULL', friction=0.75, bounce=0.05, damping=0.4, world_scale=10.0,
           gravity=(0.0, 0.0, -9.81)):
    """Drops `dynamic` objects onto `passive` ones with Bullet rigid bodies and keeps the final poses.
    Bullet is unstable at centimetre scale, so everything is simulated `world_scale` times larger."""
    scene = bpy.context.scene
    all_objs = dynamic + passive
    for o in dynamic:
        activate(o)
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    for o in all_objs:
        o.location *= world_scale
        o.scale *= world_scale
        activate(o)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    old_gravity = tuple(scene.gravity)
    scene.gravity = gravity           # upward gravity + a lid makes ice cubes float at the surface
    rbw = scene.rigidbody_world
    rbw.substeps_per_frame = 20
    rbw.solver_iterations = 30
    rbw.point_cache.frame_start = 1
    rbw.point_cache.frame_end = frames
    for o in passive:
        activate(o)
        bpy.ops.rigidbody.object_add(type='PASSIVE')
        o.rigid_body.collision_shape = 'MESH'
        o.rigid_body.friction = friction
        o.rigid_body.use_margin = True
        o.rigid_body.collision_margin = 0.001
    for o in dynamic:
        activate(o)
        bpy.ops.rigidbody.object_add(type='ACTIVE')
        rb = o.rigid_body
        rb.collision_shape = shape
        rb.friction, rb.restitution = friction, bounce
        rb.linear_damping = rb.angular_damping = damping
        rb.use_margin = True
        rb.collision_margin = 0.002
        rb.mass = max(0.001, o.dimensions.x * o.dimensions.y * o.dimensions.z * 1000)
    for f in range(1, frames + 1):
        scene.frame_set(f)
    for o in dynamic:
        activate(o)
        bpy.ops.object.visual_transform_apply()
    for o in all_objs:
        activate(o)
        bpy.ops.rigidbody.object_remove()
    bpy.ops.rigidbody.world_remove()
    scene.gravity = old_gravity
    for o in all_objs:
        mw = o.matrix_world.copy()
        o.matrix_world = Matrix.Scale(1 / world_scale, 4) @ mw
        apply_transform(o)
    return dynamic


def place(obj, targets, x, y, rot=(0.0, 0.0, 0.0), sink=0.0):
    """Rotates `obj`, then lowers it at (x, y) until its underside rests on the highest point of `targets` below it."""
    obj.rotation_euler = rot
    apply_transform(obj)
    lo, hi = bounds(obj)
    obj.location = (x - (lo[0] + hi[0]) / 2, y - (lo[1] + hi[1]) / 2, -lo[2])
    apply_transform(obj)
    verts = sorted((v.co.copy() for v in obj.data.vertices), key=lambda c: c.z)
    low = verts[:max(8, len(verts) // 12)][::max(1, len(verts) // 12 // 60)]
    lift = None
    for c in low:
        hit = ray_down(targets, c.x, c.y)
        if hit:
            need = hit[0].z - c.z
            lift = need if lift is None else max(lift, need)
    obj.location.z = (lift or 0.0) - sink
    apply_transform(obj)
    return obj


# ================================================================== finishing

def finish(obj, name=None, smooth_angle=60, origin=True):
    if name:
        obj.name = name
        obj.data.name = name
    smooth(obj, smooth_angle)
    if origin:
        set_origin_bottom(obj)
    return obj
