import type { EventDef, EventSchedule, L10n } from './types.ts';

export interface PriceableMeal {
  id: string;
  /** The meal's category plus all ancestor categories (so a parent-category event covers sub-categories). */
  categoryIds: string[];
  price: number;
  name: L10n;
}

export interface CartInput {
  meal: PriceableMeal;
  qty: number;
}

export interface PricedLine {
  mealId: string;
  qty: number;
  unitPrice: number;
  discount: number;
  eventId: string | null;
  lineTotal: number;
}

export interface PricedCart {
  lines: PricedLine[];
  subtotal: number;
  discount: number;
  total: number;
}

const pad = (n: number) => String(n).padStart(2, '0');
const dateKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const minutesOf = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + (m || 0);
};

export function isScheduleActive(s: EventSchedule, now: Date): boolean {
  const day = dateKey(now);
  if (s.from && day < s.from) return false;
  if (s.to && day > s.to) return false;
  if (s.weekdays && s.weekdays.length > 0 && !s.weekdays.includes(now.getDay())) return false;
  if (s.start && s.end) {
    const cur = now.getHours() * 60 + now.getMinutes();
    const a = minutesOf(s.start);
    const b = minutesOf(s.end);
    if (a === b) return true;
    if (a < b) return cur >= a && cur < b;
    return cur >= a || cur < b; // crosses midnight
  }
  return true;
}

export function isEventActive(ev: EventDef, now: Date): boolean {
  return ev.active && isScheduleActive(ev.schedule, now);
}

export function eventCoversMeal(ev: EventDef, meal: PriceableMeal): boolean {
  if (ev.mealIds.length === 0 && ev.categoryIds.length === 0) return true;
  if (ev.mealIds.includes(meal.id)) return true;
  return meal.categoryIds.some((c) => ev.categoryIds.includes(c));
}

/** Per-unit discount for percent / fixed_off events (integer so'm, never above the price). */
export function unitDiscount(ev: EventDef, price: number): number {
  if (ev.type === 'percent') {
    const pct = Math.min(100, Math.max(0, ev.params.percent ?? 0));
    return Math.min(price, Math.round((price * pct) / 100));
  }
  if (ev.type === 'fixed_off') {
    return Math.min(price, Math.max(0, Math.round(ev.params.amount ?? 0)));
  }
  return 0;
}

/**
 * Prices a cart. Rules:
 *  - percent / fixed_off apply per unit, buy_x_get_y applies per group of (buy + get) eligible units
 *    (the cheapest `get` units of each group are free).
 *  - Discounts never stack: each unit receives the single best discount available to it.
 */
export function priceCart(inputs: CartInput[], events: EventDef[], now: Date): PricedCart {
  const active = events.filter((e) => isEventActive(e, now));

  interface Unit { line: number; price: number; best: number; eventId: string | null }
  const units: Unit[] = [];
  inputs.forEach((inp, line) => {
    for (let i = 0; i < inp.qty; i++) units.push({ line, price: inp.meal.price, best: 0, eventId: null });
  });

  // percent / fixed per unit
  for (const u of units) {
    const meal = inputs[u.line].meal;
    for (const ev of active) {
      if (ev.type === 'buy_x_get_y' || !eventCoversMeal(ev, meal)) continue;
      const d = unitDiscount(ev, u.price);
      if (d > u.best) { u.best = d; u.eventId = ev.id; }
    }
  }

  // buy X get Y: free units are chosen from the cheapest eligible units
  for (const ev of active) {
    if (ev.type !== 'buy_x_get_y') continue;
    const buy = Math.max(1, Math.floor(ev.params.buy ?? 1));
    const get = Math.max(1, Math.floor(ev.params.get ?? 1));
    const eligible = units.filter((u) => eventCoversMeal(ev, inputs[u.line].meal));
    const freeCount = Math.floor(eligible.length / (buy + get)) * get;
    if (freeCount === 0) continue;
    const cheapest = [...eligible].sort((a, b) => a.price - b.price).slice(0, freeCount);
    for (const u of cheapest) {
      if (u.price > u.best) { u.best = u.price; u.eventId = ev.id; }
    }
  }

  const lines: PricedLine[] = inputs.map((inp) => ({
    mealId: inp.meal.id, qty: inp.qty, unitPrice: inp.meal.price, discount: 0, eventId: null, lineTotal: 0,
  }));
  const lineBest = new Map<number, { amount: number; eventId: string | null }>();
  for (const u of units) {
    const l = lines[u.line];
    l.discount += u.best;
    if (u.best > 0) {
      const cur = lineBest.get(u.line);
      if (!cur || u.best > cur.amount) lineBest.set(u.line, { amount: u.best, eventId: u.eventId });
    }
  }
  lines.forEach((l, i) => {
    l.eventId = lineBest.get(i)?.eventId ?? null;
    l.lineTotal = l.unitPrice * l.qty - l.discount;
  });
  const subtotal = lines.reduce((s, l) => s + l.unitPrice * l.qty, 0);
  const discount = lines.reduce((s, l) => s + l.discount, 0);
  return { lines, subtotal, discount, total: subtotal - discount };
}

export interface MealPromo {
  event: EventDef;
  /** Discounted unit price for percent / fixed events; null for buy-x-get-y. */
  discountedPrice: number | null;
}

/** Best active promo for a single meal (used for badges and the virtual "Promo" category). */
export function mealPromo(meal: PriceableMeal, events: EventDef[], now: Date): MealPromo | null {
  let best: MealPromo | null = null;
  let bestScore = 0;
  for (const ev of events) {
    if (!isEventActive(ev, now) || !eventCoversMeal(ev, meal)) continue;
    let score: number;
    let discountedPrice: number | null = null;
    if (ev.type === 'buy_x_get_y') {
      const buy = Math.max(1, Math.floor(ev.params.buy ?? 1));
      const get = Math.max(1, Math.floor(ev.params.get ?? 1));
      score = (meal.price * get) / (buy + get); // average saving per unit
    } else {
      score = unitDiscount(ev, meal.price);
      discountedPrice = meal.price - score;
    }
    if (best === null || score > bestScore) { best = { event: ev, discountedPrice }; bestScore = score; }
  }
  return best;
}

export function validateSchedule(s: EventSchedule): string | null {
  const hhmm = /^([01]\d|2[0-3]):[0-5]\d$/;
  const ymd = /^\d{4}-\d{2}-\d{2}$/;
  if (s.from && !ymd.test(s.from)) return 'Invalid start date';
  if (s.to && !ymd.test(s.to)) return 'Invalid end date';
  if (s.from && s.to && s.from > s.to) return 'End date is before start date';
  if (Boolean(s.start) !== Boolean(s.end)) return 'Set both start and end time';
  if (s.start && !hhmm.test(s.start)) return 'Invalid start time';
  if (s.end && !hhmm.test(s.end)) return 'Invalid end time';
  if (s.weekdays && s.weekdays.some((d) => !Number.isInteger(d) || d < 0 || d > 6)) return 'Invalid weekday';
  return null;
}

export function validateEventParams(type: EventDef['type'], p: EventDef['params']): string | null {
  if (type === 'percent') {
    if (!(typeof p.percent === 'number') || p.percent <= 0 || p.percent > 100) return 'Percent must be between 1 and 100';
  } else if (type === 'fixed_off') {
    if (!(typeof p.amount === 'number') || p.amount <= 0) return 'Amount must be greater than 0';
  } else if (type === 'buy_x_get_y') {
    if (!Number.isInteger(p.buy) || (p.buy as number) < 1 || (p.buy as number) > 20) return 'Buy quantity must be 1-20';
    if (!Number.isInteger(p.get) || (p.get as number) < 1 || (p.get as number) > 20) return 'Free quantity must be 1-20';
  } else return 'Unknown event type';
  return null;
}
