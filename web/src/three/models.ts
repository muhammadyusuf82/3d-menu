import * as T from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import type { Container, Ingredient, Meal } from '../../../shared/types.ts';

export interface Part { id: string; obj: T.Object3D }
export interface MealModel extends T.Group {
  userData: { parts: Part[]; static: T.Object3D | null };
}

// ---------------------------------------------------------------- build context
let RND: () => number = Math.random;

function rng(seed: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface MatOpts { opacity?: number }
function material(color: string | number, roughness = 0.75, o: MatOpts = {}): T.Material {
  const m = new T.MeshStandardMaterial({ color, roughness, metalness: 0.02, side: T.DoubleSide });
  if (o.opacity !== undefined) { m.transparent = true; m.opacity = o.opacity; m.depthWrite = o.opacity > 0.6; }
  return m;
}

function mesh(geometry: T.BufferGeometry, mat: T.Material): T.Mesh {
  const m = new T.Mesh(geometry, mat);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}
const cylinder = (r: number, h: number, color: string, o?: MatOpts) => mesh(new T.CylinderGeometry(r, r, h, 48), material(color, 0.75, o));
const sphere = (x: number, y: number, z: number, color: string, o?: MatOpts) => {
  const m = mesh(new T.SphereGeometry(1, 36, 22), material(color, 0.75, o));
  m.scale.set(x, y, z);
  return m;
};
const box = (x: number, y: number, z: number, color: string) => mesh(new T.BoxGeometry(x, y, z), material(color));
const group = (...objects: T.Object3D[]) => { const g = new T.Group(); g.add(...objects); return g; };

// ---------------------------------------------------------------- legacy builders (burger / hot dog / wrap)
function bunTop() {
  const shape: [number, number][] = [[0, 0], [0.93, 0], [0.94, 0.12]];
  const n = 24;
  for (let i = 1; i <= n; i++) { const a = (i / n) * Math.PI / 2; shape.push([0.94 * Math.cos(a), 0.12 + 0.45 * Math.sin(a)]); }
  const g = group(mesh(new T.LatheGeometry(shape.map((p) => new T.Vector2(...p)), 56), material('#e6b26b', 0.75)));
  for (let i = 0; i < 32; i++) {
    const r = Math.sqrt((i + 0.5) / 32) * 0.83, a = i * 2.399963;
    const z = r * Math.sin(a), x = r * Math.cos(a), y = 0.12 + 0.45 * Math.sqrt(1 - (r * r) / (0.94 * 0.94));
    const seed = sphere(0.025, 0.012, 0.046, '#f6e3c2');
    seed.position.set(x, y + 0.007, z);
    seed.rotation.y = a;
    g.add(seed);
  }
  return g;
}
function lettuce() {
  const geometry = new T.CylinderGeometry(1, 1, 0.035, 96, 1);
  const pos = geometry.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), a = Math.atan2(z, x), r = Math.hypot(x, z);
    if (r > 0.5) { const wave = 1 + 0.055 * Math.sin(a * 11); pos.setXYZ(i, x * wave, pos.getY(i) + 0.07 * Math.sin(a * 11 + 0.8), z * wave); }
  }
  geometry.computeVertexNormals();
  return group(mesh(geometry, material('#5fbf4e')));
}
function cheese(color: string) {
  const geo = new T.BoxGeometry(1.53, 0.045, 1.53, 12, 1, 12), pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) { const r = Math.hypot(pos.getX(i), pos.getZ(i)); pos.setY(i, pos.getY(i) - Math.max(0, r - 0.5) ** 1.8 * 0.35); }
  geo.computeVertexNormals();
  const m = mesh(geo, material(color, 0.4));
  m.rotation.y = 0.35;
  return group(m);
}
function onion(color: string, count = 3) {
  const g = new T.Group();
  for (let i = 0; i < count; i++) { const m = mesh(new T.TorusGeometry(0.67 - i * 0.13, 0.032, 10, 48), material(color, 0.55)); m.rotation.x = Math.PI / 2; m.position.y = i * 0.045; g.add(m); }
  return g;
}
function pickles() {
  const g = new T.Group();
  [[-0.45, 0.1], [0.4, -0.2], [0.05, 0.4]].forEach(([x, z]) => { const p = cylinder(0.19, 0.09, '#7ba05b'); p.position.set(x, 0, z); g.add(p); });
  return g;
}
function sauceRing(color: string) {
  const g = new T.Group();
  for (let i = 0; i < 5; i++) { const a = (i * Math.PI * 2) / 5, p = sphere(0.26, 0.045, 0.2, color); p.position.set(0.52 * Math.cos(a), 0, 0.52 * Math.sin(a)); g.add(p); }
  return g;
}
function bacon() {
  const g = new T.Group();
  for (let j = 0; j < 2; j++) {
    const geo = new T.PlaneGeometry(1.65, 0.25, 32, 3);
    geo.rotateX(-Math.PI / 2);
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) p.setY(i, 0.065 * Math.sin(p.getX(i) * 7));
    geo.computeVertexNormals();
    const m = mesh(geo, material(j ? '#c15a34' : '#b5462b'));
    m.position.set(0, j * 0.065, j * 0.27 - 0.14);
    m.rotation.y = j * 0.2;
    g.add(m);
  }
  return g;
}
function patty(color: string) {
  const geo = new T.CylinderGeometry(0.86, 0.86, 0.23, 60, 4), p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) { const x = p.getX(i), z = p.getZ(i), n = 1 + 0.012 * Math.sin(x * 34) * Math.cos(z * 28); p.setX(i, x * n); p.setZ(i, z * n); }
  geo.computeVertexNormals();
  return group(mesh(geo, material(color, 0.95)));
}
function hotdogBun() {
  const g = new T.Group();
  for (const side of [-1, 1]) {
    const m = mesh(new T.CapsuleGeometry(0.28, 1.5, 8, 28), material('#e8b36c', 0.75));
    m.rotation.z = Math.PI / 2; m.scale.y = 0.87; m.position.set(0, 0.22, side * 0.25); g.add(m);
  }
  return g;
}
function sausage(color: string) {
  const m = mesh(new T.CapsuleGeometry(0.25, 1.63, 8, 32), material(color, 0.5));
  m.rotation.z = Math.PI / 2;
  return group(m);
}
function drizzle(color: string, r = 0.052, offset = 0, width = 1.56) {
  const half = width / 2;
  const points = Array.from({ length: 40 }, (_, i) => { const t = i / 39; return new T.Vector3(-half + t * width, 0.025, Math.sin(t * Math.PI * 6 + offset) * 0.14); });
  return group(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(points), 72, r, 10, false), material(color, 0.25)));
}
function diced(color: string, count = 14, size = 0.09) {
  const g = new T.Group(), geo = new T.IcosahedronGeometry(size, 1), mat = material(color, 0.65);
  for (let i = 0; i < count; i++) {
    const p = mesh(geo, mat);
    p.position.set((RND() - 0.5) * 1.65, RND() * 0.05, (RND() - 0.5) * 0.45);
    p.rotation.set(RND() * 3, RND() * 3, RND() * 3);
    p.scale.set(1.2, 0.65, 1);
    g.add(p);
  }
  return g;
}
function fries() {
  const g = new T.Group();
  for (let i = 0; i < 8; i++) { const f = box(0.12, 0.12, 0.68, '#f2c230'); f.position.set((RND() - 0.5) * 1.6, RND() * 0.04, (RND() - 0.5) * 0.35); f.rotation.y = (RND() - 0.5) * 2; g.add(f); }
  return g;
}
function pita() {
  const g = new T.Group(), geo = new T.CylinderGeometry(0.56, 0.56, 2.25, 48, 1, true, 0, Math.PI);
  geo.rotateZ(Math.PI / 2);
  const m = mesh(geo, material('#e3c08a', 0.8));
  m.rotation.x = Math.PI / 2; m.position.y = 0.46; g.add(m);
  return g;
}

// ---------------------------------------------------------------- containers (static, do not explode)
interface ContainerInfo {
  group: T.Object3D | null;
  floorY: number; // where stacked ingredients start
  topY: number; // rim height
  inner: number; // usable inner radius for scatter / discs
  liquidR: number;
  fill: number; // full liquid height
}

function lathe(points: [number, number][], color: string, o?: MatOpts) {
  const m = mesh(new T.LatheGeometry(points.map((p) => new T.Vector2(p[0], p[1])), 64), material(color, 0.35, o));
  return m;
}
function handle(x: number, y: number, r = 0.22) {
  const m = mesh(new T.TorusGeometry(r, 0.055, 12, 28), material('#f4f1ea', 0.35));
  m.position.set(x, y, 0);
  return m;
}

function makeContainer(kind: Container): ContainerInfo {
  const white = '#f4f1ea';
  switch (kind) {
    case 'plate': {
      const g = lathe([[0, 0], [0.7, 0], [1.05, 0.03], [1.3, 0.1], [1.38, 0.13], [1.33, 0.13], [1.0, 0.08], [0, 0.08]], white);
      return { group: g, floorY: 0.08, topY: 0.13, inner: 1.0, liquidR: 0.9, fill: 0.5 };
    }
    case 'bowl': {
      const g = lathe([[0, 0], [0.35, 0], [0.7, 0.12], [1.0, 0.45], [1.15, 0.85], [1.1, 0.85], [0.95, 0.5], [0.65, 0.17], [0, 0.12]], white);
      return { group: g, floorY: 0.12, topY: 0.85, inner: 0.85, liquidR: 0.78, fill: 0.5 };
    }
    case 'glass': {
      const g = lathe([[0, 0], [0.45, 0], [0.5, 0.06], [0.63, 1.7], [0.59, 1.7], [0.46, 0.12], [0, 0.1]], '#cfe9ff', { opacity: 0.25 });
      return { group: g, floorY: 0.1, topY: 1.7, inner: 0.46, liquidR: 0.49, fill: 1.25 };
    }
    case 'mug': {
      const g = group(lathe([[0, 0], [0.5, 0], [0.55, 0.05], [0.56, 1.0], [0.51, 1.0], [0.5, 0.1], [0, 0.1]], white), handle(0.68, 0.52));
      return { group: g, floorY: 0.1, topY: 1.0, inner: 0.48, liquidR: 0.5, fill: 0.7 };
    }
    case 'cup': {
      const saucer = lathe([[0, 0], [0.8, 0], [1.0, 0.05], [1.08, 0.1], [1.03, 0.1], [0.8, 0.05], [0, 0.05]], white);
      const cup = group(lathe([[0, 0], [0.28, 0], [0.34, 0.05], [0.63, 0.82], [0.58, 0.82], [0.3, 0.13], [0, 0.11]], white), handle(0.72, 0.45, 0.2));
      cup.position.y = 0.06;
      return { group: group(saucer, cup), floorY: 0.17, topY: 0.88, inner: 0.5, liquidR: 0.53, fill: 0.55 };
    }
    case 'board': {
      const geo = new RoundedBoxGeometry(2.7, 0.12, 1.8, 4, 0.04);
      const b = mesh(geo, material('#b07a45', 0.7));
      b.position.y = 0.06;
      return { group: group(b), floorY: 0.12, topY: 0.12, inner: 1.0, liquidR: 0.9, fill: 0.5 };
    }
    default:
      return { group: null, floorY: 0, topY: 0, inner: 1.0, liquidR: 0.9, fill: 0.5 };
  }
}

// ---------------------------------------------------------------- generic ingredient parts (base sits at local y = 0)
const ROLL: Record<string, { r: number; len: number }> = {
  strips: { r: 0.13, len: 0.75 }, skewers: { r: 0.09, len: 1.45 }, asparagus: { r: 0.06, len: 1.2 },
  croissant: { r: 0.26, len: 1.25 },
};

function lift(m: T.Object3D, h: number) { m.position.y = h / 2; return m; }

function halfDome(rx: number, h: number, color: string, o?: MatOpts) {
  const geo = new T.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2);
  const m = mesh(geo, material(color, 0.7, o));
  m.scale.set(rx, h, rx);
  return m;
}

function genericPart(ing: Ingredient, c: ContainerInfo, liquidH: number): { obj: T.Object3D; h: number } {
  const size = ing.size ?? 1;
  const col = ing.color;
  const fit = Math.min(c.inner, 0.95);
  const g = new T.Group();
  const pcs = ing.unit === 'pcs' || ing.unit === 'slices' ? Math.max(1, Math.min(8, Math.round(ing.amount))) : 0;
  const special = ing.id === 'fries' || ing.id === 'kids-fries' ? 'pile' : null;
  const shape = special ?? ing.shape ?? 'scatter';

  switch (shape) {
    case 'pile': {
      const n = Math.min(32, Math.max(8, Math.round(ing.amount / 7)));
      for (let i = 0; i < n; i++) {
        const f = box(0.1, 0.1, 0.62, col);
        const rr = Math.sqrt(RND()) * Math.min(fit * 0.7, 0.75), a = RND() * Math.PI * 2;
        f.position.set(rr * Math.cos(a), 0.05 + RND() * 0.2, rr * Math.sin(a));
        f.rotation.set((RND() - 0.5) * 0.5, RND() * Math.PI, (RND() - 0.5) * 0.5);
        g.add(f);
      }
      return { obj: g, h: 0.28 };
    }
    case 'disc': {
      const r = Math.min(fit, 0.5 + 0.2 * Math.min(size, 2));
      if (pcs > 1) {
        const t = 0.1;
        for (let i = 0; i < pcs; i++) { const d = cylinder(r, t, col); d.position.y = i * t * 0.95 + t / 2; g.add(d); }
        return { obj: g, h: pcs * t * 0.95 + 0.06 };
      }
      const t = 0.06 + 0.07 * size;
      g.add(lift(cylinder(r, t, col), t));
      return { obj: g, h: t + 0.01 };
    }
    case 'slab': {
      const w = Math.min(1.8, 1.3 + 0.25 * size), d = Math.min(1.2, 0.8 + 0.1 * size), h = 0.04 + 0.12 * size;
      const m = mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(0.04, h / 2.5)), material(col, 0.6));
      m.position.y = h / 2;
      m.rotation.y = (RND() - 0.5) * 0.12;
      g.add(m);
      return { obj: g, h: h + 0.01 };
    }
    case 'mound': {
      const rx = Math.min(fit, 0.45 + 0.25 * size), h = 0.3 + 0.25 * size;
      g.add(halfDome(rx, h, col));
      return { obj: g, h: h * 0.8 };
    }
    case 'sphere': {
      const r = Math.max(0.1, 0.5 * size);
      const n = pcs || 1;
      const ring = n > 1 ? r * 1.7 : 0;
      for (let i = 0; i < n; i++) {
        const s = mesh(new T.SphereGeometry(r, 32, 24), material(col, 0.55));
        const a = (i / n) * Math.PI * 2;
        s.position.set(ring * Math.cos(a), r, ring * Math.sin(a));
        g.add(s);
      }
      return { obj: g, h: n > 1 ? r * 2 : r * 1.6 };
    }
    case 'scatter': {
      const count = pcs ? Math.min(16, pcs * 2) : Math.min(26, 8 + Math.round(ing.amount / 12));
      const pr = 0.075 * size;
      const geo = new T.IcosahedronGeometry(pr, 1), mat = material(col, 0.65);
      const spread = Math.min(fit * 0.75, 0.8);
      for (let i = 0; i < count; i++) {
        const p = mesh(geo, mat);
        const rr = Math.sqrt(RND()) * spread, a = RND() * Math.PI * 2;
        p.position.set(rr * Math.cos(a), pr * 0.6 + RND() * 0.04, rr * Math.sin(a));
        p.rotation.set(RND() * 3, RND() * 3, RND() * 3);
        p.scale.set(1 + RND() * 0.4, 0.7, 1 + RND() * 0.3);
        g.add(p);
      }
      return { obj: g, h: pr * 1.6 + 0.04 };
    }
    case 'rings': {
      const count = pcs ? Math.min(5, pcs) : 3;
      const R = Math.min(fit, 0.5 * size + 0.1);
      for (let i = 0; i < count; i++) {
        const t = mesh(new T.TorusGeometry(Math.max(0.1, R - i * 0.05), 0.03, 10, 48), material(col, 0.55));
        t.rotation.x = Math.PI / 2;
        t.position.y = 0.03 + i * 0.05;
        g.add(t);
      }
      return { obj: g, h: count * 0.05 + 0.05 };
    }
    case 'drizzle':
      return { obj: group(drizzle(col, 0.05, 0, Math.min(1.56, fit * 1.6))), h: 0.07 };
    case 'roll': {
      const spec = ROLL[ing.id] ?? { r: 0.12, len: 1.0 };
      const n = pcs || 3;
      const gap = spec.r * 2 + 0.07;
      for (let i = 0; i < n; i++) {
        const m = mesh(new T.CylinderGeometry(spec.r, spec.r, spec.len, 20), material(col, 0.6));
        m.rotation.z = Math.PI / 2;
        m.position.set(0, spec.r, (i - (n - 1) / 2) * gap);
        g.add(m);
      }
      return { obj: g, h: spec.r * 2 + 0.02 };
    }
    case 'tall': {
      for (let i = 0; i < 3; i++) { const m = cylinder(0.12, 0.8, col); m.position.set((i - 1) * 0.3, 0.4, 0); g.add(m); }
      return { obj: g, h: 0.82 };
    }
    case 'liquid': {
      const h = Math.max(0.1, liquidH);
      g.add(lift(mesh(new T.CylinderGeometry(c.liquidR, c.liquidR, h, 48), material(col, 0.15, { opacity: 0.94 })), h));
      return { obj: g, h };
    }
    case 'foam': {
      const h = Math.max(0.06, liquidH);
      g.add(halfDome(c.liquidR, h * 1.6, col));
      return { obj: g, h };
    }
    case 'ice': {
      const n = pcs || 5;
      for (let i = 0; i < n; i++) {
        const cube = mesh(new RoundedBoxGeometry(0.26, 0.26, 0.26, 2, 0.04), material(col, 0.1, { opacity: 0.6 }));
        const rr = Math.sqrt(RND()) * c.liquidR * 0.6, a = RND() * Math.PI * 2;
        cube.position.set(rr * Math.cos(a), 0.13 + RND() * 0.12, rr * Math.sin(a));
        cube.rotation.set(RND() * 2, RND() * 2, RND() * 2);
        g.add(cube);
      }
      return { obj: g, h: 0.34 };
    }
    case 'leaf': {
      const n = pcs || 3;
      for (let i = 0; i < n; i++) {
        const leaf = sphere(0.22, 0.025, 0.1, col);
        const a = (i / n) * Math.PI * 2 + RND();
        leaf.position.set(Math.cos(a) * 0.18, 0.03 + i * 0.012, Math.sin(a) * 0.18);
        leaf.rotation.set((RND() - 0.5) * 0.4, a, (RND() - 0.5) * 0.3);
        g.add(leaf);
      }
      return { obj: g, h: 0.09 };
    }
  }
  return { obj: g, h: 0.1 };
}

// ---------------------------------------------------------------- meal assembly
export function buildMeal(meal: Meal): MealModel {
  const root = new T.Group() as MealModel;
  const parts: Part[] = [];
  let y = 0;
  let startCursor = -0.15;
  let staticObj: T.Object3D | null = null;

  function add(id: string, obj: T.Object3D, height: number) {
    obj.position.y = y;
    obj.userData.id = id;
    obj.userData.assembledY = y;
    root.add(obj);
    parts.push({ id, obj });
    y += height;
  }

  const kind = meal.model.kind;
  if (kind === 'burger') {
    for (const ing of meal.ingredients) {
      RND = rng(meal.id + ing.id);
      let obj: T.Object3D, h = 0.09;
      switch (ing.id) {
        case 'bun-bottom': obj = group(cylinder(0.92, 0.3, ing.color)); h = 0.22; break;
        case 'sauce': obj = sauceRing(ing.color); h = 0.04; break;
        case 'patty': case 'patty2': obj = patty(ing.color); h = 0.23; break;
        case 'cheese': case 'cheese2': obj = cheese(ing.color); h = 0.05; break;
        case 'bacon': obj = bacon(); h = 0.09; break;
        case 'tomato': { const a = cylinder(0.72, 0.055, ing.color), b = cylinder(0.69, 0.055, ing.color); b.position.y = 0.07; obj = group(a, b); h = 0.12; break; }
        case 'onion': obj = onion(ing.color); h = 0.05; break;
        case 'pickles': obj = pickles(); h = 0.05; break;
        case 'lettuce': obj = lettuce(); h = 0.06; break;
        case 'bun-top': obj = bunTop(); h = 0.57; break;
        default: obj = diced(ing.color, 8, 0.08); h = 0.08;
      }
      add(ing.id, obj, h);
    }
  } else if (kind === 'hotdog') {
    for (const ing of meal.ingredients) {
      RND = rng(meal.id + ing.id);
      let obj: T.Object3D, h = 0.08;
      if (ing.id === 'bun') { obj = hotdogBun(); h = 0.3; }
      else if (ing.id === 'sausage' || ing.id === 'beef-sausage') { obj = sausage(ing.color); h = 0.24; }
      else if (['mustard', 'ketchup', 'cheese-sauce'].includes(ing.id)) { obj = drizzle(ing.color, ing.id === 'cheese-sauce' ? 0.085 : 0.052, ing.id === 'ketchup' ? 2 : 0); h = 0.035; }
      else if (ing.id === 'jalapeno') {
        obj = new T.Group();
        for (let i = 0; i < 4; i++) { const r = mesh(new T.TorusGeometry(0.09, 0.027, 8, 20), material(ing.color)); r.rotation.x = Math.PI / 2; r.position.x = -0.6 + i * 0.4; obj.add(r); }
        h = 0.07;
      } else obj = diced(ing.color, ing.id === 'chili' ? 22 : 14, ing.id === 'chili' ? 0.11 : 0.07);
      add(ing.id, obj, h);
    }
  } else if (kind === 'wrap') {
    for (const ing of meal.ingredients) {
      RND = rng(meal.id + ing.id);
      let obj: T.Object3D, h = 0.065;
      if (ing.id === 'pita') { obj = pita(); h = 0.25; }
      else if (ing.id === 'chicken' || ing.id === 'beef') { obj = diced(ing.color, 14, 0.18); h = 0.14; }
      else if (ing.id === 'fries') { obj = fries(); h = 0.075; }
      else if (ing.id === 'garlic' || ing.id === 'tahini') { obj = drizzle(ing.color, 0.075); h = 0.05; }
      else obj = diced(ing.color, ing.id === 'parsley' ? 14 : 9, ing.id === 'parsley' ? 0.045 : 0.1);
      add(ing.id, obj, h);
    }
  } else {
    const c = makeContainer(meal.model.container);
    if (c.group) { root.add(c.group); staticObj = c.group; }
    y = c.floorY;
    startCursor = meal.model.container === 'plate' || meal.model.container === 'board' ? c.floorY + 0.25 : c.topY + 0.3;
    // liquid heights are proportional to their volume within the vessel
    const liquidShapes = new Set(['liquid', 'foam']);
    const totalMl = meal.ingredients.filter((i) => i.shape && liquidShapes.has(i.shape)).reduce((s, i) => s + Math.max(1, i.amount), 0);
    const spread = meal.model.arrange === 'spread';
    const spots = spreadSpots(meal.ingredients.length, c.inner);
    meal.ingredients.forEach((ing, i) => {
      RND = rng(meal.id + ing.id);
      const lh = totalMl > 0 && ing.shape && liquidShapes.has(ing.shape) ? (c.fill * Math.max(1, ing.amount)) / totalMl : 0;
      const { obj, h } = genericPart(ing, c, lh);
      if (spread) {
        obj.position.set(spots[i][0], 0, spots[i][1]);
        add(ing.id, obj, 0); // side by side on the vessel floor instead of stacked
      } else add(ing.id, obj, h);
    });
    if (spread) {
      root.updateMatrixWorld(true);
      return finishModel(root, parts, staticObj, 'lift');
    }
  }

  root.updateMatrixWorld(true);
  return finishModel(root, parts, staticObj, 'stack', startCursor);
}

/** Positions for laying N items side by side: an ellipse on the vessel floor, with one in the middle when crowded. */
export function spreadSpots(n: number, inner: number): [number, number][] {
  const rx = Math.min(0.95, inner * 0.95), rz = rx * 0.5;
  const ring = n > 5 ? n - 1 : n;
  const out: [number, number][] = [];
  for (let i = 0; i < ring; i++) {
    const a = (i / ring) * Math.PI * 2 + Math.PI;
    out.push([Math.cos(a) * rx, Math.sin(a) * rz]);
  }
  if (ring < n) out.push([0, 0]);
  return out;
}

/**
 * Computes the exploded position of every part and stores the part list on the root.
 * 'stack': parts are stacked above each other in order (layered dishes).
 * 'lift': parts that already sit apart are lifted together (platters).
 */
export function finishModel(root: MealModel, parts: Part[], staticObj: T.Object3D | null, mode: 'stack' | 'lift', startCursor = 0, gap = 0.16): MealModel {
  if (mode === 'lift') {
    for (const p of parts) p.obj.userData.explodedY = p.obj.userData.assembledY + 0.55;
  } else {
    let cursor = startCursor;
    for (const p of parts) {
      const bounds = new T.Box3().setFromObject(p.obj);
      const height = Math.max(0.05, bounds.max.y - bounds.min.y);
      p.obj.userData.explodedY = p.obj.position.y + cursor - bounds.min.y;
      cursor += height + gap;
    }
  }
  root.userData.parts = parts;
  root.userData.static = staticObj;
  return root;
}

export function disposeModel(root: T.Object3D | null) {
  if (!root) return;
  const geometries = new Set<T.BufferGeometry>(), materials = new Set<T.Material>();
  root.traverse((o) => {
    if ((o as T.Mesh).isMesh) {
      const m = o as T.Mesh;
      geometries.add(m.geometry);
      (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => materials.add(x));
    }
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => {
    // scanned (photoreal) models carry large textures; free them together with the material
    for (const v of Object.values(m)) if (v && (v as T.Texture).isTexture) (v as T.Texture).dispose();
    m.dispose();
  });
}
