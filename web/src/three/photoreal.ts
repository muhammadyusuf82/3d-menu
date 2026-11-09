import * as T from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { finishModel, type MealModel, type Part } from './models.ts';

/**
 * HD models, two kinds:
 *  - 'scan': Poly Haven CC0 scans (web/public/models/polyhaven/<asset>/). Either one solid scan (cannot be pulled
 *    apart) or several scanned items on a base, each a separate part.
 *  - 'layered': one GLB built in Blender (tools/blender/) whose top-level nodes are the ingredients, named with the
 *    meal's ingredient ids and placed at their assembled heights; they explode upwards in stacking order.
 */
interface PhotoItem {
  asset: string;
  /** Ingredient id this item represents (enables highlight / focus from the recipe list). */
  ingredient: string;
  /** Position on the base, in the base's normalised units (base width = `size`). */
  at?: [number, number];
  rotY?: number;
}
export interface ScanSpec {
  kind?: 'scan';
  /** Largest dimension of the base (or the single item) after scaling, in scene units. */
  size: number;
  base?: string;
  items: PhotoItem[];
}
export interface LayeredSpec {
  kind: 'layered';
  url: string;
  /** Largest dimension of the assembled meal after scaling, in scene units. */
  size: number;
  /** i18n key of the credit line shown under the viewer. */
  credit: string;
}
export type PhotoSpec = ScanSpec | LayeredSpec;

const layered = (id: string, size: number, credit = 'hdCreditModelled'): LayeredSpec =>
  ({ kind: 'layered', url: `/models/hd/${id}.glb`, size, credit });

/** Blender-built dishes (tools/blender/build_dish.py): a static base (plate, glass, board) plus one node per ingredient. */
const BLENDER_DISHES: Record<string, LayeredSpec> = {
  'classic-hotdog': layered('classic-hotdog', 2.7),
  'chili-hotdog': layered('chili-hotdog', 2.7),
  'chicken-shawarma': layered('chicken-shawarma', 3.0, 'hdCreditBoard'),
  'beef-shawarma': layered('beef-shawarma', 3.0, 'hdCreditBoard'),
  'loaded-fries': layered('loaded-fries', 2.6),
  'chicken-strips': layered('chicken-strips', 2.9),
  'salmon-nigiri': layered('salmon-nigiri', 3.0),
  'california-roll': layered('california-roll', 3.0),
  'philadelphia-roll': layered('philadelphia-roll', 3.0),
  plov: layered('plov', 3.0),
  manti: layered('manti', 2.9),
  lagman: layered('lagman', 2.7),
  shashlik: layered('shashlik', 3.1, 'hdCreditBoard'),
  'kids-burger': layered('kids-burger', 2.8, 'hdCreditBlender'),
  'kids-nuggets': layered('kids-nuggets', 2.8),
  'mac-cheese': layered('mac-cheese', 2.5),
  'mini-pancakes': layered('mini-pancakes', 2.8),
  ribeye: layered('ribeye', 3.0),
  'filet-mignon': layered('filet-mignon', 3.0),
  'striploin-fries': layered('striploin-fries', 3.0),
  tiramisu: layered('tiramisu', 2.5),
  cheesecake: layered('cheesecake', 2.5),
  sundae: layered('sundae', 2.4),
  'lava-cake': layered('lava-cake', 2.6),
  'black-tea': layered('black-tea', 2.4),
  'green-tea': layered('green-tea', 2.3),
  'hot-chocolate': layered('hot-chocolate', 2.3),
  lemonade: layered('lemonade', 2.5),
  'peach-iced-tea': layered('peach-iced-tea', 2.5),
  'strawberry-milkshake': layered('strawberry-milkshake', 2.5),
  espresso: layered('espresso', 2.2),
  cappuccino: layered('cappuccino', 2.3),
  'caramel-latte': layered('caramel-latte', 2.4),
};

export const PHOTO_MODELS: Record<string, PhotoSpec> = {
  ...BLENDER_DISHES,
  'classic-burger': { kind: 'layered', url: '/models/hd/classic-burger.glb', size: 2.4, credit: 'hdCreditBlender' },
  'double-burger': { kind: 'layered', url: '/models/hd/double-burger.glb', size: 2.6, credit: 'hdCreditBlender' },
  'strawberry-chocolate-cake': { size: 2.4, items: [{ asset: 'strawberry_chocolate_cake', ingredient: 'choc-sponge' }] },
  'carrot-cake': { size: 2.3, items: [{ asset: 'carrot_cake', ingredient: 'carrot-sponge' }] },
  croissant: { size: 2.4, items: [{ asset: 'croissant', ingredient: 'croissant' }] },
  'fruit-platter': {
    size: 2.9,
    base: 'wooden_cutting_board',
    items: [
      { asset: 'food_pomegranate_01', ingredient: 'pomegranate', at: [-0.92, 0.05] },
      { asset: 'food_apple_01', ingredient: 'apple', at: [-0.3, -0.3], rotY: 0.6 },
      { asset: 'food_avocado_01', ingredient: 'avocado-whole', at: [0.32, -0.32], rotY: 1.2 },
      { asset: 'food_kiwi_01', ingredient: 'kiwi', at: [0.92, -0.18] },
      { asset: 'food_pears_asian_01', ingredient: 'pears', at: [-0.22, 0.38] },
      { asset: 'food_lime_01', ingredient: 'lime', at: [0.42, 0.36], rotY: 2 },
      { asset: 'food_lychee_01', ingredient: 'lychee', at: [0.98, 0.32] },
    ],
  },
};

export const hasPhotoModel = (mealId: string) => mealId in PHOTO_MODELS;
export const photoCredit = (mealId: string) => {
  const spec = PHOTO_MODELS[mealId];
  return spec?.kind === 'layered' ? spec.credit : 'hdCredit';
};

const url = (asset: string) => `/models/polyhaven/${asset}/${asset}.gltf`;
const loader = new GLTFLoader();

async function loadScene(asset: string): Promise<T.Object3D> {
  return loadUrl(url(asset));
}

async function loadUrl(href: string): Promise<T.Object3D> {
  const gltf = await loader.loadAsync(href);
  gltf.scene.traverse((o) => {
    const m = o as T.Mesh;
    if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; }
  });
  return gltf.scene;
}

/** Puts an object's footprint centre at x/z = 0 and its bottom at y = 0 (in its parent's space). */
function ground(obj: T.Object3D) {
  obj.updateMatrixWorld(true);
  const b = new T.Box3().setFromObject(obj);
  obj.position.x -= (b.min.x + b.max.x) / 2;
  obj.position.z -= (b.min.z + b.max.z) / 2;
  obj.position.y -= b.min.y;
}

/** Loads the photoreal model for a meal. Resolves to a model with the same part structure as the procedural ones. */
export async function buildPhotoMeal(mealId: string): Promise<MealModel> {
  const spec = PHOTO_MODELS[mealId];
  if (!spec) throw new Error('no photoreal model for ' + mealId);
  if (spec.kind === 'layered') return buildLayered(spec);
  const [baseScene, ...itemScenes] = await Promise.all([
    spec.base ? loadScene(spec.base) : Promise.resolve(null),
    ...spec.items.map((i) => loadScene(i.asset)),
  ]);

  const root = new T.Group() as MealModel;
  const parts: Part[] = [];
  // One uniform scale for everything keeps the real-world proportions between the scanned items.
  const reference = baseScene ?? itemScenes[0];
  const refSize = new T.Box3().setFromObject(reference).getSize(new T.Vector3());
  const scale = spec.size / Math.max(refSize.x, refSize.y, refSize.z);

  let floor = 0;
  let staticObj: T.Object3D | null = null;
  if (baseScene) {
    const base = new T.Group();
    base.add(baseScene);
    ground(baseScene); // measured before scaling, while the holder is still the identity
    base.scale.setScalar(scale);
    root.add(base);
    base.updateMatrixWorld(true);
    floor = new T.Box3().setFromObject(base).max.y;
    staticObj = base;
  }

  spec.items.forEach((item, i) => {
    const holder = new T.Group();
    const inner = itemScenes[i];
    if (item.rotY) inner.rotation.y = item.rotY;
    holder.add(inner);
    ground(inner);
    holder.scale.setScalar(scale);
    holder.position.set(item.at?.[0] ?? 0, floor, item.at?.[1] ?? 0);
    holder.userData.id = item.ingredient;
    holder.userData.assembledY = floor;
    root.add(holder);
    parts.push({ id: item.ingredient, obj: holder });
  });
  root.updateMatrixWorld(true);
  return finishModel(root, parts, staticObj, 'lift');
}

/** A Blender-built meal: each top-level node is one ingredient at its assembled height; a node flagged
 *  `static` in its glTF extras (plate, glass, board) stays put while the ingredients lift off it. */
async function buildLayered(spec: LayeredSpec): Promise<MealModel> {
  const scene = await loadUrl(spec.url);
  scene.updateMatrixWorld(true);
  const box = new T.Box3().setFromObject(scene);
  const size = box.getSize(new T.Vector3());
  const center = box.getCenter(new T.Vector3());
  const scale = spec.size / Math.max(size.x, size.y, size.z);
  const root = new T.Group() as MealModel;
  const parts: Part[] = [];
  let staticObj: T.Group | null = null;
  for (const child of [...scene.children]) {
    // Re-parent each node under a holder in scene units, so the viewer can move it along y directly.
    const holder = new T.Group();
    holder.scale.setScalar(scale);
    holder.position.set((child.position.x - center.x) * scale, (child.position.y - box.min.y) * scale, (child.position.z - center.z) * scale);
    child.position.set(0, 0, 0);
    holder.add(child);
    root.add(holder);
    if (child.userData.static) {
      staticObj ??= new T.Group();
      staticObj.add(holder);
      continue;
    }
    holder.userData.id = child.name;
    holder.userData.assembledY = holder.position.y;
    parts.push({ id: child.name, obj: holder });
  }
  if (staticObj) root.add(staticObj);
  // explicit stacking order from the Blender build (glTF extras), falling back to height
  const order = (p: Part) => (p.obj.children[0]?.userData.stack as number | undefined) ?? p.obj.position.y;
  parts.sort((a, b) => order(a) - order(b));
  root.updateMatrixWorld(true);
  // ingredients lift off the top of the plate / glass / board
  const start = staticObj ? new T.Box3().setFromObject(staticObj).max.y + 0.24 : 0;
  return finishModel(root, parts, staticObj, 'stack', start, 0.24);
}
