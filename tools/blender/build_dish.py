"""
Builds HD dishes (everything except the two burgers, see build_burger.py) as one GLB per meal:
  - one static node 'base' (plate, glass, board... never moves in the viewer, glTF extras static=1)
  - one node per ingredient, named with the meal's ingredient id, in physical bottom -> top order (extras stack=i);
    the web viewer lifts them apart in that order.

  blender -b --factory-startup --python tools/blender/build_dish.py -- --meal <id|family|all> --out web/public/models/hd
        [--preview <dir>] [--export 0|1]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kit as K  # noqa: E402
from lib import aim, args, decimate_to, export_glb, render, reset, studio, triangles  # noqa: E402

FAMILIES = ['dishes_fastfood', 'dishes_sushi', 'dishes_traditional', 'dishes_kids', 'dishes_steak',
            'dishes_dessert', 'dishes_drinks']


class Dish:
    def __init__(self, meal):
        self.meal = meal
        self.static = []
        self.parts = []
        self.budget = {}

    def base(self, *items):
        for it in items:
            self.static.append(getattr(it, 'obj', it))
        return items[0] if len(items) == 1 else items

    def part(self, obj, ingredient, budget=None):
        obj.name = ingredient
        obj.data.name = ingredient
        if budget:
            self.budget[ingredient] = budget
        self.parts.append(obj)
        return obj


def registry():
    reg = {}
    for mod in FAMILIES:
        try:
            m = __import__(mod)
        except ModuleNotFoundError as e:
            if e.name == mod:
                continue
            raise
        for meal, fn in m.DISHES.items():
            reg[meal] = (mod, fn)
    return reg


def _lift(dish, gap):
    """Same rule as the web viewer ('stack' mode): parts rise in order, each above the previous one."""
    saved = [p.location.z for p in dish.parts]
    cursor = (K.bounds(dish.static)[1][2] if dish.static else 0.0) + gap
    for p in dish.parts:
        lo, hi = K.bounds(p)
        p.location.z += cursor - lo[2]
        cursor += max(hi[2] - lo[2], 0.002) + gap
    return saved


def preview(dish, folder):
    import math
    objs = dish.static + dish.parts
    lo, hi = K.bounds(objs)
    size = float(max(hi - lo))
    studio(target_height=(lo[2] + hi[2]) / 2, distance=0.4)
    _scale_studio(size / 0.12)

    def shoot(path, objs_now, elev, fit=0.8):
        lo, hi = K.bounds(objs_now)
        c = (lo + hi) / 2
        radius = float(((hi - lo) ** 2).sum() ** 0.5 / 2)
        dist = radius / math.sin(math.radians(22) / 2) * fit
        aim(distance=dist, target_height=float(c[2]), elevation=elev)
        render(path, samples=48, res=(900, 700))

    shoot(os.path.join(folder, f'{dish.meal}_a.png'), objs, 30)
    saved = _lift(dish, gap=size * 0.09)
    import bpy
    bpy.context.view_layer.update()
    shoot(os.path.join(folder, f'{dish.meal}_b.png'), dish.static + dish.parts, 14, fit=1.0)
    for p, z in zip(dish.parts, saved):
        p.location.z = z


def _scale_studio(s):
    import bpy
    for o in bpy.data.objects:
        if o.type == 'LIGHT':
            o.location = o.location * s
            o.data.size *= s
            o.data.energy *= s * s
        if o.name == 'floor':
            o.scale = (s, s, s)


def build(meal, fn, out_dir, preview_dir):
    t0 = time.time()
    reset()
    dish = Dish(meal)
    fn(dish)
    tris = {}
    for p in dish.parts:
        # decimation only where a recipe asks for it: collapsing many small UV islands smears textures black
        tris[p.name] = decimate_to(p, dish.budget[p.name]) if p.name in dish.budget else triangles(p)
    base = None
    if dish.static:
        base = K.join(dish.static, 'base') if len(dish.static) > 1 else dish.static[0]
        base.name = 'base'
        base['static'] = 1
        dish.static = [base]
        tris['base'] = triangles(base)
    for i, p in enumerate(dish.parts):
        p['stack'] = i
    print('TRIANGLES', meal, tris, 'total', sum(tris.values()))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        preview(dish, preview_dir)
    if out_dir:
        export_glb(dish.static + dish.parts, os.path.join(out_dir, f'{meal}.glb'))
    print(f'BUILT {meal} in {time.time() - t0:.0f}s')


if __name__ == '__main__':
    opt = args()
    reg = registry()
    want = opt.get('meal', 'all')
    if want == 'all':
        meals = list(reg)
    elif want in reg:
        meals = [want]
    else:
        meals = [m for m, (mod, _) in reg.items() if mod == want or mod == 'dishes_' + want]
    if not meals:
        raise SystemExit(f'unknown meal/family {want}; known: {sorted(reg)}')
    failed = []
    for m in meals:
        try:
            build(m, reg[m][1], opt.get('out', 'web/public/models/hd') if opt.get('export', '1') == '1' else None,
                  opt.get('preview'))
        except Exception:
            import traceback
            traceback.print_exc()
            failed.append(m)
    if failed:
        print('FAILED', failed)
        sys.exit(1)
