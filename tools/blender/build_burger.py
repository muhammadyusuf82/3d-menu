"""
Builds HD burgers as separate ingredient parts (one GLB per meal, node names = the meal's ingredient ids).

  blender -b --factory-startup --python tools/blender/build_burger.py -- --meal classic-burger --out web/public/models/hd [--preview <dir>]
  --meal all   builds every burger below.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import burger_parts as P  # noqa: E402
import veg_parts as V  # noqa: E402
from lib import aim, args, decimate_to, export_glb, render, reset, studio  # noqa: E402

# Recipes, bottom -> top, in the same order as the meal's ingredient list (shared/seed.ts).
RECIPES = {
    'classic-burger': lambda bun: [bun[0], V.sauce(), P.patty(), P.cheese(), V.tomato(), V.onion(), V.pickles(),
                                   V.lettuce(), bun[1]],
    'double-burger': lambda bun: [bun[0], V.sauce(), P.patty(), P.cheese(), P.bacon(),
                                  P.patty('patty2', seed=2, tone=0.92), P.cheese('cheese2', rot=1.1), V.tomato(),
                                  V.onion(), V.pickles(), V.lettuce(), bun[1]],
}
# small overlaps so layers sit into each other like a real stacked burger
GAPS = {'sauce': -0.0006, 'patty': -0.0012, 'patty2': -0.0012, 'cheese': 0.0012, 'cheese2': 0.0012,  # rest above the patty's surface lumps
        'bacon': -0.0008, 'tomato': -0.0005, 'onion': -0.0004, 'pickles': -0.0006, 'lettuce': -0.0008,
        'bun-top': -0.0015}
# triangle budget per part so a tablet can spin the whole meal smoothly
BUDGET = {'sauce': 2000, 'patty': 9000, 'patty2': 9000, 'cheese': 8000, 'cheese2': 8000, 'bacon': 4000,
          'tomato': 6000, 'pickles': 5000, 'lettuce': 12000}


def height(obj):
    return obj.get('stack_h', obj.dimensions.z)


def assemble(stack, spacing=0.0):
    z = 0.0
    for i, obj in enumerate(stack):
        drip = obj.dimensions.z - height(obj)          # e.g. melted cheese hangs below its origin
        obj.location = (0, 0, z + (drip if spacing else 0.0) + (0.0 if spacing else GAPS.get(obj.name, 0.0)))
        obj['stack'] = i                               # explicit explode order (glTF extras -> three.js userData)
        z = obj.location.z + height(obj) + spacing
    return z


def build(meal, out_dir, preview):
    reset()
    stack = RECIPES[meal](P.bun_halves())
    tris = {o.name: decimate_to(o, BUDGET.get(o.name, 10 ** 9)) for o in stack}
    print('TRIANGLES', meal, tris, 'total', sum(tris.values()))
    top = assemble(stack)
    if preview:
        studio(target_height=top * 0.5, distance=0.36)
        render(os.path.join(preview, f'{meal}_assembled.png'), samples=64)
        top = assemble(stack, spacing=0.025)
        aim(distance=0.62, target_height=top * 0.5)
        render(os.path.join(preview, f'{meal}_exploded.png'), samples=64)
        assemble(stack)
    if out_dir:
        export_glb(stack, os.path.join(out_dir, f'{meal}.glb'))


opt = args()
meals = list(RECIPES) if opt.get('meal', 'classic-burger') == 'all' else [opt.get('meal', 'classic-burger')]
for m in meals:
    build(m, opt.get('out', 'web/public/models/hd') if opt.get('export', '1') == '1' else None, opt.get('preview'))
