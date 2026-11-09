"""
Shared helpers for building HD food models in Blender (run headless: blender -b --factory-startup --python <script> -- args).

Units are metres (a burger bun is ~0.105 m wide). Every ingredient is its own object, named with the meal's
ingredient id, with its origin at the bottom centre and its location at its assembled height; the web viewer
uses those node names and heights for highlight, focus and the exploded view.

Materials are authored procedurally (nodes or numpy-painted images), then baked to image textures so they
survive glTF export (procedural shader nodes do not export).
"""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets')


def args():
    """Parses `--key value` pairs after the `--` separator."""
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = {}
    for i in range(0, len(argv) - 1, 2):
        out[argv[i].lstrip('-')] = argv[i + 1]
    return out


# ------------------------------------------------------------------ scene

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.render.engine = 'CYCLES'
    use_gpu()
    return scene


def use_gpu():
    scene = bpy.context.scene
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for kind in ('OPTIX', 'CUDA'):
            try:
                prefs.compute_device_type = kind
                break
            except TypeError:
                continue
        (getattr(prefs, 'refresh_devices', None) or prefs.get_devices)()
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        scene.cycles.device = 'GPU'
    except Exception as e:  # CPU fallback still works, just slower
        print('GPU setup failed, using CPU:', e)
        scene.cycles.device = 'CPU'


def studio(target_height=0.06, distance=0.32):
    """Warm food-photography lighting: big soft key, fill, rim, dark backdrop, catcher floor."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new('studio')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.035, 0.022, 0.016, 1)
    bg.inputs['Strength'].default_value = 1.0

    def area(name, loc, energy, size, color):
        light = bpy.data.lights.new(name, 'AREA')
        light.energy, light.size, light.color = energy, size, color
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = loc
        direction = Vector((0, 0, target_height)) - Vector(loc)
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        return obj

    # energies are for a ~10 cm subject lit from ~0.5 m
    area('key', (-0.25, -0.30, 0.38), 5.0, 0.35, (1.0, 0.93, 0.84))
    area('fill', (0.35, -0.18, 0.16), 1.0, 0.40, (0.85, 0.9, 1.0))
    area('rim', (0.05, 0.38, 0.30), 3.5, 0.20, (1.0, 0.82, 0.62))

    floor = bpy.data.meshes.new('floor')
    floor_obj = bpy.data.objects.new('floor', floor)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=2.0)
    bm.to_mesh(floor)
    bm.free()
    scene.collection.objects.link(floor_obj)
    floor_obj.is_shadow_catcher = True
    floor_obj['preview_only'] = True

    cam_data = bpy.data.cameras.new('cam')
    cam_data.lens = 70
    cam = bpy.data.objects.new('cam', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    aim(distance=distance, target_height=target_height)
    scene.render.film_transparent = False
    # closest to the web viewer's neutral PBR look (AgX desaturates food noticeably)
    try:
        scene.view_settings.view_transform = 'Khronos PBR Neutral'
    except TypeError:
        scene.view_settings.view_transform = 'Standard'


def aim(distance=0.32, target_height=0.06, azimuth=-35.0, elevation=24.0):
    cam = bpy.context.scene.camera
    az, el = math.radians(azimuth), math.radians(elevation)
    target = Vector((0, 0, target_height))
    cam.location = target + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * distance
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()


def render(path, samples=96, res=(1100, 800)):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)


# ------------------------------------------------------------------ mesh helpers

def new_object(name, bm):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def activate(obj):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def smooth(obj, angle=60):
    activate(obj)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))
    except Exception:
        bpy.ops.object.shade_smooth()


def apply_modifiers(obj):
    activate(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def uv_unwrap(obj, margin=0.02):
    activate(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def planar_uv(obj, faces_filter=None, size=None):
    """Top-down UV projection (x,y -> u,v) for discs, slices and caps."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    uv = me.uv_layers.active.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    span = size or max(max(xs) - min(xs), max(ys) - min(ys)) or 1
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    for poly in me.polygons:
        if faces_filter and not faces_filter(poly):
            continue
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv[li].uv = ((co.x - cx) / span + 0.5, (co.y - cy) / span + 0.5)


def disc_mesh(name, radius, height, cuts=40, radius_fn=None, bevel=0.35, smooth_level=1):
    """A cylinder whose caps have grid topology (a cube mapped onto a disc), so baked textures and normals have no
    radial streaks. radius_fn(theta) -> scale factor shapes irregular or crinkle-cut edges."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    for v in bm.verts:
        x, y, z = v.co
        xd = x * math.sqrt(max(0.0, 1 - y * y / 2))
        yd = y * math.sqrt(max(0.0, 1 - x * x / 2))
        theta = math.atan2(yd, xd)
        r = radius * (radius_fn(theta) if radius_fn else 1.0)
        v.co = Vector((xd * r, yd * r, z * height / 2))
    obj = new_object(name, bm)
    if bevel:
        b = obj.modifiers.new('bevel', 'BEVEL')
        b.width, b.segments, b.limit_method = height * bevel, 4, 'ANGLE'
    if smooth_level:
        s = obj.modifiers.new('smooth', 'SUBSURF')
        s.levels = smooth_level
    apply_modifiers(obj)
    return obj


def set_origin_bottom(obj, z0=None):
    """Moves the origin to the bottom centre of the mesh (or to height z0) and places the object there."""
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    off = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, min(zs) if z0 is None else z0))
    for v in me.vertices:
        v.co -= off
    obj.location += off


# ------------------------------------------------------------------ materials

def node_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    return mat, nt, bsdf


def link(nt, a, b):
    nt.links.new(a, b)


def image_from_array(name, arr, non_color=False):
    """arr: float32 HxWx3 or HxWx4 in 0..1, row 0 = top of the image."""
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    img = bpy.data.images.new(name, w, h, alpha=False)
    # must happen BEFORE writing pixels: changing the colour space of a generated image regenerates it (blank)
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(np.flipud(arr).astype(np.float32).ravel())
    img.pack()
    return img


def image_to_array(img):
    w, h = img.size
    arr = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(arr)
    return arr.reshape(h, w, 4)


def array_to_image(img, arr):
    img.pixels.foreach_set(arr.astype(np.float32).ravel())
    img.update()
    img.pack()


def tex_node(nt, img, x=-600, y=0):
    node = nt.nodes.new('ShaderNodeTexImage')
    node.image = img
    node.location = (x, y)
    return node


# ------------------------------------------------------------------ baking

def bake(obj, res=1024, normal=True, roughness=True, samples=4):
    """Bakes the object's (procedural) materials into one set of textures and swaps in a glTF-friendly material."""
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.render.bake.margin = 6
    activate(obj)
    passes = [('color', 'DIFFUSE', False)]
    if roughness:
        passes.append(('rough', 'ROUGHNESS', True))
    if normal:
        passes.append(('normal', 'NORMAL', True))
    baked = {}
    for key, kind, non_color in passes:
        img = bpy.data.images.new(f'{obj.name}_{key}', res, res, alpha=False)
        if non_color:
            img.colorspace_settings.name = 'Non-Color'
        for slot in obj.material_slots:
            nt = slot.material.node_tree
            n = nt.nodes.new('ShaderNodeTexImage')
            n.image = img
            n.name = 'BAKE_TARGET'
            nt.nodes.active = n
        kw = {'type': kind, 'margin': 6, 'use_clear': True}
        if kind == 'DIFFUSE':
            kw['pass_filter'] = {'COLOR'}
        if kind == 'NORMAL':
            kw['normal_space'] = 'TANGENT'
        bpy.ops.object.bake(**kw)
        for slot in obj.material_slots:
            nt = slot.material.node_tree
            nt.nodes.remove(nt.nodes['BAKE_TARGET'])
        img.pack()
        baked[key] = img

    # glTF-friendly replacement material
    mat, nt, bsdf = node_material(f'{obj.name}_baked')
    first = obj.material_slots[0].material
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Specular IOR Level'].default_value = first.get('spec', 0.5) if first else 0.5
    c = tex_node(nt, baked['color'], -700, 300)
    link(nt, c.outputs['Color'], bsdf.inputs['Base Color'])
    if 'rough' in baked:
        r = tex_node(nt, baked['rough'], -700, 0)
        link(nt, r.outputs['Color'], bsdf.inputs['Roughness'])
    if 'normal' in baked:
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.location = (-300, -300)
        n = tex_node(nt, baked['normal'], -700, -300)
        link(nt, n.outputs['Color'], nm.inputs['Color'])
        link(nt, nm.outputs['Normal'], bsdf.inputs['Normal'])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return mat


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def decimate_to(obj, target):
    """Collapse-decimates a part to roughly `target` triangles (UVs and baked textures are preserved)."""
    current = triangles(obj)
    if current <= target:
        return current
    m = obj.modifiers.new('budget', 'DECIMATE')
    m.decimate_type = 'COLLAPSE'
    m.ratio = target / current
    m.use_collapse_triangulate = True
    apply_modifiers(obj)
    return triangles(obj)


# ------------------------------------------------------------------ export

def export_glb(objects, path):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    allowed = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=path, export_format='GLB', use_selection=True, export_apply=True, export_yup=True,
              export_image_format='JPEG', export_jpeg_quality=88, export_image_quality=88,
              export_materials='EXPORT', export_cameras=False, export_lights=False, export_extras=True)
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in allowed})
    print('exported', path, round(os.path.getsize(path) / 1024), 'KB')
