import type { Category, EventDef, L10n, Meal } from '../../../shared/types.ts';
import { eventCoversMeal, type PriceableMeal } from '../../../shared/pricing.ts';

export type Lang = 'en' | 'uz';
export const loc = (v: L10n, lang: Lang) => (lang === 'uz' ? v[1] || v[0] : v[0]);

export function categoryChain(id: string, cats: Map<string, Category>): string[] {
  const out: string[] = [];
  let cur = cats.get(id);
  while (cur && out.length < 4) { out.push(cur.id); cur = cur.parentId ? cats.get(cur.parentId) : undefined; }
  return out;
}

export function toPriceable(m: Meal, cats: Map<string, Category>): PriceableMeal {
  return { id: m.id, price: m.price, name: m.name, categoryIds: categoryChain(m.categoryId, cats) };
}

export function eventCovers(ev: EventDef, m: Meal, cats: Map<string, Category>): boolean {
  return eventCoversMeal(ev, toPriceable(m, cats));
}

export function formatMoney(n: number, lang: Lang): string {
  const s = Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return lang === 'uz' ? `${s} so‘m` : `${s} UZS`;
}

const pad = (n: number) => String(n).padStart(2, '0');
export const todayKey = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** Structural sharing: keep previous object identities when the JSON is unchanged (limits React/WebGL rebuilds). */
export function reuse<T extends { id: string }>(prev: T[] | undefined, next: T[]): T[] {
  if (!prev) return next;
  const map = new Map(prev.map((p) => [p.id, JSON.stringify(p)] as const));
  const old = new Map(prev.map((p) => [p.id, p] as const));
  return next.map((n) => (map.get(n.id) === JSON.stringify(n) ? old.get(n.id)! : n));
}
