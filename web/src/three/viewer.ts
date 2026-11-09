import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import type { Meal } from '../../../shared/types.ts';
import { buildMeal, disposeModel, type MealModel } from './models.ts';
import { buildPhotoMeal, hasPhotoModel } from './photoreal.ts';

/** 'hd' shows the photoreal scanned model when the meal has one, otherwise the standard model. */
export type Quality = 'standard' | 'hd';

const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function modelBounds(root: MealModel, amount: number): T.Box3 {
  const box = new T.Box3();
  for (const p of root.userData.parts) {
    const old = p.obj.position.y;
    p.obj.position.y = T.MathUtils.lerp(p.obj.userData.assembledY, p.obj.userData.explodedY, amount);
    root.updateMatrixWorld(true);
    box.expandByObject(p.obj);
    p.obj.position.y = old;
  }
  if (root.userData.static) box.expandByObject(root.userData.static);
  root.updateMatrixWorld(true);
  return box;
}

function fitPose(camera: T.PerspectiveCamera, bounds: T.Box3, extra = 1.15) {
  const sphere = bounds.getBoundingSphere(new T.Sphere());
  const v = (camera.fov * Math.PI) / 180;
  const h = 2 * Math.atan(Math.tan(v / 2) * camera.aspect);
  const distance = Math.max(sphere.radius / Math.sin(v / 2), sphere.radius / Math.sin(h / 2)) * extra;
  const position = sphere.center.clone().addScaledVector(new T.Vector3(0.5, 0.35, 1).normalize(), distance);
  return { center: sphere.center, position };
}

function addLights(scene: T.Scene, hd: boolean) {
  scene.add(new T.HemisphereLight('#fff3e2', '#2a160c', hd ? 0.7 : 2));
  const key = new T.DirectionalLight('#fff6ec', hd ? 2.4 : 3);
  key.position.set(4, 7, 5);
  scene.add(key);
  const rim = new T.DirectionalLight('#ffc98a', hd ? 1.3 : 1.8);
  rim.position.set(-4, 3, -4);
  scene.add(rim);
  return key;
}

// ================================================================= big interactive viewer
export interface ModelState {
  /** The photoreal model is on screen. */
  photo: boolean;
  /** This meal has a photoreal model. */
  available: boolean;
  loading: boolean;
  failed: boolean;
  /** The model on screen has more than one part to pull apart. */
  explodable: boolean;
}

export interface BigViewerEvents {
  onUserInteract: () => void;
  /** HD mode was too slow on this device and has been switched off. */
  onSlow: () => void;
  onModelState: (s: ModelState) => void;
}

export class BigViewer {
  private renderer: T.WebGLRenderer;
  private scene = new T.Scene();
  private camera = new T.PerspectiveCamera(35, 1, 0.1, 100);
  private controls: OrbitControls;
  private key!: T.DirectionalLight;
  private lights: T.Light[] = [];
  private ground: T.Mesh | null = null;
  private envTex: T.Texture | null = null;
  private pmrem: T.PMREMGenerator | null = null;
  private root: MealModel | null = null;
  private meal: Meal | null = null;
  private amount = 0;
  private target = 0;
  private animation: { time: number; from: T.Vector3; to: T.Vector3; fromTarget: T.Vector3; toTarget: T.Vector3 } | null = null;
  private observer: ResizeObserver;
  private raf = 0;
  private last = performance.now();
  private destroyed = false;
  private quality: Quality = 'standard';
  private photo = false;
  private loadToken = 0;
  private frames = 0;
  private frameTime = 0;

  constructor(private canvas: HTMLCanvasElement, private ev: BigViewerEvents) {
    this.renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
    this.renderer.outputColorSpace = T.SRGBColorSpace;
    this.renderer.toneMapping = T.ACESFilmicToneMapping;
    this.camera.position.set(3, 2.5, 5);
    this.controls = new OrbitControls(this.camera, canvas);
    Object.assign(this.controls, { enableDamping: true, dampingFactor: 0.075, enablePan: false, minDistance: 1, maxDistance: 30, minPolarAngle: 0.1, maxPolarAngle: Math.PI * 0.9, autoRotateSpeed: 0.8 });
    this.controls.addEventListener('start', () => { this.controls.autoRotate = false; this.animation = null; this.ev.onUserInteract(); });
    this.observer = new ResizeObserver(() => { this.resize(); if (this.root) this.fit(true); });
    this.observer.observe(canvas.parentElement!);
    this.applyLighting(false);
    this.resize();
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }

  get hasModel() { return !!this.root; }

  /** Studio lighting for the procedural models; environment lighting + soft shadows for the photoreal scans. */
  private applyLighting(hd: boolean) {
    // rebuild lights / environment for the mode
    for (const l of this.lights) this.scene.remove(l);
    this.lights = [];
    const before = new Set(this.scene.children);
    this.key = addLights(this.scene, hd);
    for (const c of this.scene.children) if (!before.has(c)) this.lights.push(c as T.Light);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, hd ? 2 : 1.75));
    this.renderer.toneMappingExposure = hd ? 1.05 : 1.1;
    this.renderer.shadowMap.enabled = hd;
    this.renderer.shadowMap.type = T.PCFSoftShadowMap;
    this.renderer.shadowMap.needsUpdate = true;
    this.key.castShadow = hd;
    if (hd) {
      this.key.shadow.mapSize.set(2048, 2048);
      Object.assign(this.key.shadow.camera, { left: -3.5, right: 3.5, top: 3.5, bottom: -3.5, near: 0.5, far: 20 });
      this.key.shadow.bias = -0.0004;
      this.key.shadow.normalBias = 0.02;
      this.key.shadow.radius = 4;
      this.key.shadow.camera.updateProjectionMatrix();
      if (!this.envTex) {
        this.pmrem = new T.PMREMGenerator(this.renderer);
        this.envTex = this.pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      }
      this.scene.environment = this.envTex;
      if (!this.ground) {
        this.ground = new T.Mesh(new T.PlaneGeometry(14, 14), new T.ShadowMaterial({ opacity: 0.38 }));
        this.ground.rotation.x = -Math.PI / 2;
        this.ground.receiveShadow = true;
      }
      this.ground.position.y = -0.005;
      this.scene.add(this.ground);
    } else {
      this.scene.environment = null;
      if (this.ground) this.scene.remove(this.ground);
    }
    this.frames = 0;
    this.frameTime = 0;
  }

  setMeal(meal: Meal, quality: Quality, spin: boolean) {
    this.meal = meal;
    this.quality = quality;
    this.controls.autoRotate = spin;
    this.showStandard(false);
    if (quality === 'hd') void this.loadPhoto();
  }

  setQuality(q: Quality) {
    if (q === this.quality || !this.meal) return;
    this.quality = q;
    if (q === 'hd') void this.loadPhoto();
    else if (this.photo) this.showStandard(true);
    else { this.loadToken++; this.emit(); } // cancels a photoreal load still in flight
  }

  /** The procedural model appears instantly; it also stays on screen while a photoreal model loads. */
  private showStandard(keepPose: boolean) {
    this.loadToken++;
    this.applyLighting(false);
    this.install(buildMeal(this.meal!), keepPose);
    this.photo = false;
    this.emit();
  }

  private async loadPhoto() {
    const meal = this.meal!;
    if (!hasPhotoModel(meal.id)) { this.emit(); return; }
    const token = ++this.loadToken;
    this.emit({ loading: true });
    try {
      const model = await buildPhotoMeal(meal.id);
      if (token !== this.loadToken || this.destroyed) { disposeModel(model); return; }
      this.applyLighting(true);
      this.install(model, true);
      this.photo = true;
      this.emit();
    } catch (e) {
      console.warn('photoreal model failed to load', e);
      if (token === this.loadToken && !this.destroyed) this.emit({ failed: true });
    }
  }

  private install(model: MealModel, keepPose: boolean) {
    const rotation = keepPose ? this.root?.rotation.y ?? 0 : 0;
    if (this.root) { this.scene.remove(this.root); disposeModel(this.root); }
    this.root = model;
    this.scene.add(model);
    model.rotation.y = rotation;
    this.amount = this.target = 0;
    if (!keepPose) {
      this.camera.position.set(3, 2.5, 5);
      this.controls.target.set(0, 0.7, 0);
    }
    this.resize();
    this.fit(true);
  }

  private emit(extra: { loading?: boolean; failed?: boolean } = {}) {
    if (this.destroyed || !this.meal) return;
    this.ev.onModelState({
      photo: this.photo,
      available: hasPhotoModel(this.meal.id),
      loading: !!extra.loading,
      failed: !!extra.failed,
      explodable: (this.root?.userData.parts.length ?? 0) > 1,
    });
  }

  private resize() {
    const r = this.canvas.parentElement!.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this.renderer.setSize(Math.round(r.width), Math.round(r.height), false);
    this.camera.aspect = r.width / r.height;
    this.camera.updateProjectionMatrix();
  }

  private fit(instant = false) {
    if (!this.root) return;
    const b = modelBounds(this.root, this.target);
    if (!b.isEmpty()) this.fitBox(b, instant);
  }

  private fitBox(b: T.Box3, instant: boolean, extra = 1.15) {
    const pose = fitPose(this.camera, b, extra);
    if (instant) {
      this.camera.position.copy(pose.position);
      this.controls.target.copy(pose.center);
      this.camera.lookAt(pose.center);
      this.animation = null;
    } else {
      this.animation = { time: 0, from: this.camera.position.clone(), to: pose.position, fromTarget: this.controls.target.clone(), toTarget: pose.center.clone() };
    }
  }

  explode(on: boolean) {
    if (on && (this.root?.userData.parts.length ?? 0) < 2) return;
    this.target = on ? 1 : 0;
    this.fit(reduceMotion());
    if (reduceMotion()) this.amount = this.target;
  }
  spin(on: boolean) { this.controls.autoRotate = on; }
  reset() {
    if (!this.root) return;
    this.target = 0;
    this.root.rotation.y = 0;
    this.fit(reduceMotion());
  }
  highlight(id: string, on: boolean) {
    if (!this.root) return;
    for (const p of this.root.userData.parts) {
      p.obj.traverse((o) => {
        const m = (o as T.Mesh).material as T.MeshStandardMaterial | undefined;
        if ((o as T.Mesh).isMesh && m?.emissive) m.emissive.setHex(on && p.id === id ? 0x5e2808 : 0);
      });
    }
  }
  focus(id: string) {
    if (!this.root) return;
    const p = this.root.userData.parts.find((x) => x.id === id);
    if (!p) return;
    this.controls.autoRotate = false;
    this.ev.onUserInteract();
    this.root.updateMatrixWorld(true);
    this.fitBox(new T.Box3().setFromObject(p.obj), false, 1.65);
  }

  private loop(now: number) {
    if (this.destroyed) return;
    this.raf = requestAnimationFrame(this.loop);
    const raw = (now - this.last) / 1000;
    const dt = Math.min(0.05, raw);
    this.last = now;
    if (document.hidden || !this.root) return;
    this.amount += (this.target - this.amount) * Math.min(1, dt * 6);
    for (const p of this.root.userData.parts) p.obj.position.y = T.MathUtils.lerp(p.obj.userData.assembledY, p.obj.userData.explodedY, this.amount);
    if (this.animation) {
      const a = this.animation;
      a.time = Math.min(1, a.time + dt * 2.5);
      const k = 1 - (1 - a.time) ** 3;
      this.camera.position.lerpVectors(a.from, a.to, k);
      this.controls.target.lerpVectors(a.fromTarget, a.toTarget, k);
      if (a.time === 1) this.animation = null;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);

    // HD safety net: if the device cannot sustain ~24 fps with the photoreal model, drop back to Standard.
    if (this.photo) {
      if (this.frames >= 20) this.frameTime += raw; // skip warm-up frames
      this.frames++;
      if (this.frames === 140) {
        const fps = 120 / this.frameTime;
        if (fps < 24) this.ev.onSlow();
      }
    }
  }

  destroy() {
    this.destroyed = true;
    cancelAnimationFrame(this.raf);
    this.observer.disconnect();
    this.controls.dispose();
    if (this.root) { this.scene.remove(this.root); disposeModel(this.root); }
    this.envTex?.dispose();
    this.pmrem?.dispose();
    this.ground?.geometry.dispose();
    (this.ground?.material as T.Material | undefined)?.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}

// ================================================================= shared thumbnails (single WebGL context)
const MINI_W = 400;
const MINI_H = 300;

interface Mini {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  scene: T.Scene;
  camera: T.PerspectiveCamera;
  root: MealModel;
  visible: boolean;
}

class MiniManager {
  private renderer: T.WebGLRenderer | null = null;
  private failed = false;
  private minis = new Map<HTMLCanvasElement, Mini>();
  private io: IntersectionObserver | null = null;
  private pending = new Map<HTMLCanvasElement, Meal>();
  private raf = 0;
  private last = 0;
  paused = false;

  private ensureRenderer(): T.WebGLRenderer | null {
    if (this.renderer || this.failed) return this.renderer;
    try {
      const canvas = document.createElement('canvas');
      this.renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
      this.renderer.setPixelRatio(1);
      this.renderer.setSize(MINI_W, MINI_H, false);
      this.renderer.outputColorSpace = T.SRGBColorSpace;
      this.renderer.toneMapping = T.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.1;
      this.renderer.domElement.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.renderer = null; this.failed = true; });
    } catch { this.failed = true; this.renderer = null; }
    return this.renderer;
  }

  /** Registers a thumbnail canvas; the model is built lazily when it scrolls into view. Returns an unregister function. */
  register(canvas: HTMLCanvasElement, meal: Meal, onReady: () => void): () => void {
    canvas.width = MINI_W;
    canvas.height = MINI_H;
    this.pending.set(canvas, meal);
    if (!this.io) {
      this.io = new IntersectionObserver((entries) => {
        for (const e of entries) {
          const c = e.target as HTMLCanvasElement;
          let mini = this.minis.get(c);
          if (e.isIntersecting && !mini && this.pending.has(c)) {
            try {
              if (!this.ensureRenderer()) continue;
              mini = this.create(c, this.pending.get(c)!);
              this.minis.set(c, mini);
              onReadyMap.get(c)?.();
            } catch { /* leave the emoji fallback */ }
          }
          if (mini) mini.visible = e.isIntersecting;
        }
      }, { rootMargin: '80px' });
    }
    onReadyMap.set(canvas, onReady);
    this.io.observe(canvas);
    if (!this.raf) this.raf = requestAnimationFrame((t) => this.loop(t));
    return () => {
      this.io?.unobserve(canvas);
      this.pending.delete(canvas);
      onReadyMap.delete(canvas);
      const m = this.minis.get(canvas);
      if (m) { disposeModel(m.root); this.minis.delete(canvas); }
    };
  }

  private create(canvas: HTMLCanvasElement, meal: Meal): Mini {
    const scene = new T.Scene();
    addLights(scene, false);
    const camera = new T.PerspectiveCamera(35, MINI_W / MINI_H, 0.1, 100);
    const root = buildMeal(meal);
    scene.add(root);
    const pose = fitPose(camera, modelBounds(root, 0));
    camera.position.copy(pose.position);
    camera.lookAt(pose.center);
    return { canvas, ctx: canvas.getContext('2d')!, scene, camera, root, visible: true };
  }

  private loop(now: number) {
    this.raf = requestAnimationFrame((t) => this.loop(t));
    if (document.hidden || this.paused || !this.renderer || now - this.last < 33) return;
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    for (const m of this.minis.values()) {
      if (!m.visible || !m.canvas.isConnected) continue;
      if (!reduceMotion()) m.root.rotation.y += dt * 0.32;
      this.renderer.render(m.scene, m.camera);
      m.ctx.clearRect(0, 0, MINI_W, MINI_H);
      m.ctx.drawImage(this.renderer.domElement, 0, 0);
    }
  }
}
const onReadyMap = new Map<HTMLCanvasElement, () => void>();
export const miniManager = new MiniManager();
