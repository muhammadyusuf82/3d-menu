import { randomBytes } from 'node:crypto';
import type { Category, EventDef, Ingredient, L10n, Meal, ModelSpec } from '../shared/types.ts';
import { validateEventParams, validateSchedule } from '../shared/pricing.ts';
import type { Store } from './db.ts';

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
const bad = (msg: string): never => { throw new HttpError(400, msg); };

export const newId = (prefix: string) => `${prefix}-${randomBytes(5).toString('hex')}`;

function str(v: unknown, field: string, max: number, required = false): string {
  if (v === undefined || v === null || v === '') { if (required) bad(`${field} is required`); return ''; }
  if (typeof v !== 'string') bad(`${field} must be text`);
  const s = (v as string).trim();
  if (required && !s) bad(`${field} is required`);
  if (s.length > max) bad(`${field} is too long`);
  return s;
}

function l10n(v: unknown, field: string, max: number, required = false): L10n {
  const a = Array.isArray(v) ? v : [];
  const en = str(a[0], `${field} (EN)`, max, required);
  const uz = str(a[1], `${field} (UZ)`, max, false) || en;
  return [en, uz];
}

function int(v: unknown, field: string, min: number, max: number): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) bad(`${field} must be a number`);
  const n = Math.round(v as number);
  if (n < min || n > max) bad(`${field} must be between ${min} and ${max}`);
  return n;
}

const UPLOAD_RE = /^\/uploads\/[a-f0-9-]{8,64}\.(png|jpg|webp)$/;
function uploadPath(v: unknown, field: string): string | null {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v !== 'string' || !UPLOAD_RE.test(v)) bad(`${field} must be an uploaded file`);
  return v as string;
}

const SHAPES = ['disc', 'slab', 'mound', 'scatter', 'rings', 'drizzle', 'sphere', 'roll', 'tall', 'liquid', 'foam', 'ice', 'leaf'];
const UNITS = ['g', 'ml', 'pcs', 'slices'];
const KINDS = ['burger', 'hotdog', 'wrap', 'generic'];
const CONTAINERS = ['none', 'plate', 'bowl', 'glass', 'mug', 'cup', 'board'];
const HEX = /^#[0-9a-fA-F]{6}$/;

export function cleanMeal(body: any, store: Store, existingId?: string): Meal {
  if (!body || typeof body !== 'object') bad('Invalid meal');
  const categoryId = str(body.categoryId, 'Category', 64, true);
  if (!store.category(categoryId)) bad('Unknown category');
  const ingredientsIn = Array.isArray(body.ingredients) ? body.ingredients : bad('Ingredients are required');
  if (ingredientsIn.length > 30) bad('Too many ingredients (max 30)');
  const seen = new Set<string>();
  const ingredients: Ingredient[] = ingredientsIn.map((raw: any, i: number) => {
    const id = str(raw?.id, `Ingredient ${i + 1} id`, 40, true);
    if (!/^[a-z0-9-]+$/.test(id)) bad(`Ingredient id "${id}" may only contain a-z, 0-9 and -`);
    if (seen.has(id)) bad(`Duplicate ingredient id "${id}"`);
    seen.add(id);
    const unit = raw.unit;
    if (!UNITS.includes(unit)) bad(`Ingredient ${i + 1}: invalid unit`);
    const color = raw.color;
    if (typeof color !== 'string' || !HEX.test(color)) bad(`Ingredient ${i + 1}: invalid color`);
    const out: Ingredient = {
      id, name: l10n(raw.name, `Ingredient ${i + 1} name`, 80, true),
      amount: int(raw.amount, `Ingredient ${i + 1} amount`, 0, 5000), unit, color,
    };
    if (raw.shape !== undefined && raw.shape !== null && raw.shape !== '') {
      if (!SHAPES.includes(raw.shape)) bad(`Ingredient ${i + 1}: invalid shape`);
      out.shape = raw.shape;
    }
    if (raw.size !== undefined && raw.size !== null) {
      if (typeof raw.size !== 'number' || raw.size < 0.1 || raw.size > 3) bad(`Ingredient ${i + 1}: size must be 0.1-3`);
      out.size = raw.size;
    }
    return out;
  });
  const m = body.model ?? {};
  const kind = KINDS.includes(m.kind) ? m.kind : 'generic';
  const container = CONTAINERS.includes(m.container) ? m.container : 'plate';
  const model: ModelSpec = { kind, container, ...(m.arrange === 'spread' ? { arrange: 'spread' as const } : {}) };
  if (ingredients.length === 0) bad('Add at least one ingredient');
  return {
    id: existingId ?? newId('meal'),
    categoryId,
    price: int(body.price, 'Price', 0, 100_000_000),
    prepMin: int(body.prepMin ?? 10, 'Prep time', 0, 600),
    kcal: int(body.kcal ?? 0, 'Calories', 0, 10000),
    name: l10n(body.name, 'Name', 80, true),
    tag: l10n(body.tag, 'Short description', 120),
    desc: l10n(body.desc, 'Description', 600),
    ingredients, model,
    photo: uploadPath(body.photo, 'Photo'),
    available: body.available !== false,
  };
}

export function cleanCategory(body: any, store: Store, existingId?: string): Category {
  if (!body || typeof body !== 'object') bad('Invalid category');
  const parentId = body.parentId ? String(body.parentId) : null;
  if (parentId) {
    const p = store.category(parentId);
    if (!p) bad('Unknown parent category');
    if (p!.parentId) bad('Only two category levels are supported');
    if (existingId && parentId === existingId) bad('A category cannot be its own parent');
  }
  if (existingId && parentId && store.categories().some((c) => c.parentId === existingId)) bad('A category with sub-categories cannot become a sub-category');
  return {
    id: existingId ?? newId('cat'), parentId,
    name: l10n(body.name, 'Name', 60, true),
    icon: str(body.icon, 'Icon', 8) || '🍽️',
    sort: int(body.sort ?? 100, 'Sort', 0, 100000),
  };
}

export function cleanEvent(body: any, store: Store, existingId?: string): EventDef {
  if (!body || typeof body !== 'object') bad('Invalid event');
  const type = body.type;
  if (!['percent', 'fixed_off', 'buy_x_get_y'].includes(type)) bad('Unknown event type');
  const p = body.params ?? {};
  const params: EventDef['params'] = type === 'percent' ? { percent: Number(p.percent) }
    : type === 'fixed_off' ? { amount: Number(p.amount) } : { buy: Number(p.buy), get: Number(p.get) };
  const perr = validateEventParams(type, params);
  if (perr) bad(perr);
  const s = body.schedule ?? {};
  const schedule: EventDef['schedule'] = {};
  if (s.from) schedule.from = String(s.from);
  if (s.to) schedule.to = String(s.to);
  if (Array.isArray(s.weekdays) && s.weekdays.length) schedule.weekdays = s.weekdays.map(Number);
  if (s.start) schedule.start = String(s.start);
  if (s.end) schedule.end = String(s.end);
  const serr = validateSchedule(schedule);
  if (serr) bad(serr);
  const mealIds = (Array.isArray(body.mealIds) ? body.mealIds : []).map(String).filter((id: string) => store.meal(id));
  const categoryIds = (Array.isArray(body.categoryIds) ? body.categoryIds : []).map(String).filter((id: string) => store.category(id));
  return {
    id: existingId ?? newId('ev'), title: l10n(body.title, 'Title', 80, true), type, params,
    mealIds, categoryIds, schedule, banner: uploadPath(body.banner, 'Banner'), active: body.active !== false,
  };
}

export function cleanPin(v: unknown): string {
  if (typeof v !== 'string' || !/^\d{4}$/.test(v)) bad('PIN must be exactly 4 digits');
  return v as string;
}
export function cleanName(v: unknown): string { return str(v, 'Name', 40, true); }
export function cleanRole(v: unknown): 'waiter' | 'admin' {
  if (v !== 'waiter' && v !== 'admin') bad('Role must be waiter or admin');
  return v as 'waiter' | 'admin';
}
export { bad, int, str };
