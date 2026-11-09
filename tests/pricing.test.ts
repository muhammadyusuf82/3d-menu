import { describe, expect, it } from 'vitest';
import { isScheduleActive, mealPromo, priceCart, validateEventParams, validateSchedule, type PriceableMeal } from '../shared/pricing.ts';
import type { EventDef } from '../shared/types.ts';

const meal = (id: string, price: number, cats = ['c1']): PriceableMeal => ({ id, price, categoryIds: cats, name: [id, id] });
const ev = (over: Partial<EventDef>): EventDef => ({
  id: 'e', title: ['e', 'e'], type: 'percent', params: { percent: 10 }, mealIds: [], categoryIds: [], schedule: {}, banner: null, active: true, ...over,
});
const monday3pm = new Date(2026, 10, 2, 15, 30); // Mon 2 Nov 2026
const friday = new Date(2026, 10, 6, 12, 0);

describe('schedule', () => {
  it('handles time windows and midnight crossing', () => {
    expect(isScheduleActive({ start: '15:00', end: '17:00' }, monday3pm)).toBe(true);
    expect(isScheduleActive({ start: '16:00', end: '17:00' }, monday3pm)).toBe(false);
    expect(isScheduleActive({ start: '22:00', end: '02:00' }, new Date(2026, 10, 2, 23, 0))).toBe(true);
    expect(isScheduleActive({ start: '22:00', end: '02:00' }, new Date(2026, 10, 2, 1, 0))).toBe(true);
    expect(isScheduleActive({ start: '22:00', end: '02:00' }, new Date(2026, 10, 2, 12, 0))).toBe(false);
  });
  it('handles weekdays and date ranges', () => {
    expect(isScheduleActive({ weekdays: [5] }, friday)).toBe(true);
    expect(isScheduleActive({ weekdays: [5] }, monday3pm)).toBe(false);
    expect(isScheduleActive({ from: '2026-11-03' }, monday3pm)).toBe(false);
    expect(isScheduleActive({ to: '2026-11-02' }, monday3pm)).toBe(true);
  });
  it('validates schedules', () => {
    expect(validateSchedule({ start: '10:00' })).toBeTruthy();
    expect(validateSchedule({ start: '25:00', end: '10:00' })).toBeTruthy();
    expect(validateSchedule({ from: '2026-12-01', to: '2026-11-01' })).toBeTruthy();
    expect(validateSchedule({ weekdays: [7] })).toBeTruthy();
    expect(validateSchedule({ start: '10:00', end: '12:00', weekdays: [1] })).toBeNull();
  });
});

describe('priceCart', () => {
  it('returns full price with no events', () => {
    const r = priceCart([{ meal: meal('a', 10000), qty: 3 }], [], monday3pm);
    expect(r).toMatchObject({ subtotal: 30000, discount: 0, total: 30000 });
  });
  it('applies percent discount only to covered category', () => {
    const r = priceCart(
      [{ meal: meal('a', 10000, ['drinks']), qty: 2 }, { meal: meal('b', 10000, ['food']), qty: 1 }],
      [ev({ categoryIds: ['drinks'], params: { percent: 20 } })], monday3pm);
    expect(r.discount).toBe(4000);
    expect(r.total).toBe(26000);
    expect(r.lines[0].eventId).toBe('e');
    expect(r.lines[1].eventId).toBeNull();
  });
  it('covers sub-categories through ancestor ids', () => {
    const r = priceCart([{ meal: meal('a', 10000, ['hot', 'drinks']), qty: 1 }], [ev({ categoryIds: ['drinks'] })], monday3pm);
    expect(r.discount).toBe(1000);
  });
  it('ignores inactive and out-of-schedule events', () => {
    expect(priceCart([{ meal: meal('a', 10000), qty: 1 }], [ev({ active: false })], monday3pm).discount).toBe(0);
    expect(priceCart([{ meal: meal('a', 10000), qty: 1 }], [ev({ schedule: { weekdays: [5] } })], monday3pm).discount).toBe(0);
    expect(priceCart([{ meal: meal('a', 10000), qty: 1 }], [ev({ schedule: { weekdays: [5] } })], friday).discount).toBe(1000);
  });
  it('buy 1 get 1: second unit free', () => {
    const e = ev({ type: 'buy_x_get_y', params: { buy: 1, get: 1 }, mealIds: ['a'] });
    expect(priceCart([{ meal: meal('a', 6000), qty: 1 }], [e], monday3pm).discount).toBe(0);
    expect(priceCart([{ meal: meal('a', 6000), qty: 2 }], [e], monday3pm).total).toBe(6000);
    expect(priceCart([{ meal: meal('a', 6000), qty: 3 }], [e], monday3pm).total).toBe(12000);
    expect(priceCart([{ meal: meal('a', 6000), qty: 4 }], [e], monday3pm).total).toBe(12000);
  });
  it('buy 2 get 1 free across different meals frees the cheapest', () => {
    const e = ev({ type: 'buy_x_get_y', params: { buy: 2, get: 1 }, categoryIds: ['c1'] });
    const r = priceCart([{ meal: meal('a', 9000), qty: 1 }, { meal: meal('b', 5000), qty: 1 }, { meal: meal('c', 7000), qty: 1 }], [e], monday3pm);
    expect(r.discount).toBe(5000);
    expect(r.lines.find((l) => l.mealId === 'b')!.discount).toBe(5000);
    expect(r.total).toBe(16000);
  });
  it('does not stack: best single discount wins per unit', () => {
    const r = priceCart([{ meal: meal('a', 10000), qty: 1 }], [ev({ id: 'p10', params: { percent: 10 } }), ev({ id: 'p30', params: { percent: 30 } })], monday3pm);
    expect(r.discount).toBe(3000);
    expect(r.lines[0].eventId).toBe('p30');
  });
  it('BOGO beats a smaller percent on the free unit', () => {
    const r = priceCart([{ meal: meal('a', 10000), qty: 2 }],
      [ev({ id: 'p', params: { percent: 10 } }), ev({ id: 'b', type: 'buy_x_get_y', params: { buy: 1, get: 1 } })], monday3pm);
    expect(r.discount).toBe(10000 + 1000);
  });
  it('fixed_off never exceeds the price', () => {
    const r = priceCart([{ meal: meal('a', 4000), qty: 1 }], [ev({ type: 'fixed_off', params: { amount: 9000 } })], monday3pm);
    expect(r.total).toBe(0);
  });
  it('rounds percent to integer som', () => {
    const r = priceCart([{ meal: meal('a', 9995), qty: 1 }], [ev({ params: { percent: 15 } })], monday3pm);
    expect(Number.isInteger(r.discount)).toBe(true);
    expect(r.total).toBe(9995 - Math.round(9995 * 0.15));
  });
});

describe('mealPromo & validation', () => {
  it('reports discounted price for percent, null for BOGO', () => {
    expect(mealPromo(meal('a', 10000), [ev({ params: { percent: 25 } })], monday3pm)?.discountedPrice).toBe(7500);
    const b = mealPromo(meal('a', 10000), [ev({ type: 'buy_x_get_y', params: { buy: 1, get: 1 } })], monday3pm);
    expect(b).not.toBeNull();
    expect(b!.discountedPrice).toBeNull();
    expect(mealPromo(meal('a', 10000), [ev({ active: false })], monday3pm)).toBeNull();
  });
  it('validates event params', () => {
    expect(validateEventParams('percent', { percent: 0 })).toBeTruthy();
    expect(validateEventParams('percent', { percent: 101 })).toBeTruthy();
    expect(validateEventParams('percent', { percent: 50 })).toBeNull();
    expect(validateEventParams('buy_x_get_y', { buy: 2, get: 0 })).toBeTruthy();
    expect(validateEventParams('buy_x_get_y', { buy: 2, get: 1 })).toBeNull();
    expect(validateEventParams('fixed_off', { amount: -5 })).toBeTruthy();
  });
});
