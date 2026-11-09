import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { AddressInfo } from 'node:net';
import { WebSocket } from 'ws';
import { createApp } from '../server/app.ts';

let ctx: ReturnType<typeof createApp>;
let base = '';
let dir = '';

async function call(method: string, url: string, body?: unknown, token?: string) {
  const res = await fetch(base + url, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json: any = await res.json().catch(() => ({}));
  return { status: res.status, json };
}
const login = async (pin: string) => (await call('POST', '/api/login', { pin })).json;

beforeAll(async () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sizzle-test-'));
  ctx = createApp({ dbPath: path.join(dir, 't.db'), dataDir: dir, clientOrderLimit: 1000 });
  await new Promise<void>((r) => ctx.server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${(ctx.server.address() as AddressInfo).port}`;
});
afterAll(async () => {
  await ctx.close();
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('snapshot & seed', () => {
  it('serves the seeded menu publicly without orders', async () => {
    const { status, json } = await call('GET', '/api/snapshot');
    expect(status).toBe(200);
    expect(json.meals.length).toBeGreaterThanOrEqual(30);
    expect(json.categories.map((c: any) => c.id)).toEqual(expect.arrayContaining(['sushi', 'steak', 'kids', 'dessert', 'traditional', 'drinks-hot', 'drinks-cold', 'drinks-coffee']));
    expect(json.events.length).toBe(3);
    expect(json.tables.length).toBe(12);
    expect(json.orders).toEqual([]);
  });
});

describe('auth', () => {
  it('rejects a wrong PIN and accepts the right ones', async () => {
    expect((await call('POST', '/api/login', { pin: '9999' })).status).toBe(401);
    expect((await call('POST', '/api/login', { pin: 'abcd' })).status).toBe(400);
    const w = await login('1234');
    expect(w.staff.role).toBe('waiter');
    const a = await login('0000');
    expect(a.staff.role).toBe('admin');
  });
});

describe('order flow & permissions', () => {
  it('client order is priced on the server and hidden from the public snapshot', async () => {
    const r = await call('POST', '/api/orders', { table: 3, items: [{ mealId: 'classic-hotdog', qty: 2 }, { mealId: 'tiramisu', qty: 1 }] });
    expect(r.status).toBe(201);
    const o = r.json.order;
    expect(o.status).toBe('new');
    expect(o.source).toBe('client');
    // BOGO on hot dogs: 2 hot dogs => 1 free. Tiramisu is covered by Happy Friday only on Fridays.
    expect(o.items[0].discount).toBe(65000);
    expect((await call('GET', '/api/snapshot')).json.orders).toEqual([]);
    const w = await login('1234');
    const snap = (await call('GET', '/api/snapshot', undefined, w.token)).json;
    expect(snap.orders.some((x: any) => x.id === o.id)).toBe(true);
    expect(snap.tables.find((t: any) => t.number === 3).state).toBe('occupied');
  });

  it('rejects client-supplied prices, bad tables, quantities and unknown meals', async () => {
    const t = (items: any, table = 1) => call('POST', '/api/orders', { table, items });
    expect((await t([{ mealId: 'nope', qty: 1 }])).status).toBe(400);
    expect((await t([{ mealId: 'plov', qty: 0 }])).status).toBe(400);
    expect((await t([{ mealId: 'plov', qty: 21 }])).status).toBe(400);
    expect((await t([{ mealId: 'plov', qty: 1 }], 99)).status).toBe(400);
    expect((await t([])).status).toBe(400);
    const ok = await call('POST', '/api/orders', { table: 1, items: [{ mealId: 'plov', qty: 1, price: 1 }], total: 1 });
    expect(ok.json.order.total).toBe(72000);
  });

  it('only staff can change status; transitions are enforced; cancel needs a reason', async () => {
    const o = (await call('POST', '/api/orders', { table: 2, items: [{ mealId: 'plov', qty: 1 }] })).json.order;
    expect((await call('PATCH', `/api/orders/${o.id}/status`, { status: 'preparing' })).status).toBe(401);
    const w = await login('1234');
    const p = (s: string, extra: object = {}) => call('PATCH', `/api/orders/${o.id}/status`, { status: s, ...extra }, w.token);
    expect((await p('served')).status).toBe(409);
    expect((await p('preparing')).json.order.status).toBe('preparing');
    expect((await p('ready')).json.order.status).toBe('ready');
    expect((await p('cancelled')).status).toBe(400);
    expect((await p('served')).json.order.status).toBe('served');
    expect((await p('preparing')).status).toBe(409);
  });

  it('waiter takes an order, appends items, and cancels with a reason', async () => {
    const w = await login('1234');
    const created = await call('POST', '/api/orders', { table: 5, items: [{ mealId: 'classic-hotdog', qty: 1 }], note: 'no onion' }, w.token);
    const o = created.json.order;
    expect(o.source).toBe('waiter');
    expect(o.staffName).toBe('Waiter 1');
    const added = await call('POST', `/api/orders/${o.id}/items`, { items: [{ mealId: 'classic-hotdog', qty: 1 }, { mealId: 'plov', qty: 1 }] }, w.token);
    expect(added.json.order.items.find((i: any) => i.mealId === 'classic-hotdog').qty).toBe(2);
    expect(added.json.order.items.find((i: any) => i.mealId === 'classic-hotdog').discount).toBe(65000);
    const c = await call('PATCH', `/api/orders/${o.id}/status`, { status: 'cancelled', reason: 'Guest left' }, w.token);
    expect(c.json.order.status).toBe('cancelled');
    expect(c.json.order.cancelReason).toBe('Guest left');
    expect((await call('POST', `/api/orders/${o.id}/items`, { items: [{ mealId: 'plov', qty: 1 }] }, w.token)).status).toBe(409);
  });

  it('table bill flag toggles and is cleared by a new order', async () => {
    const w = await login('1234');
    await call('POST', '/api/tables/7/bill', { on: true }, w.token);
    let t = (await call('GET', '/api/snapshot', undefined, w.token)).json.tables.find((x: any) => x.number === 7);
    expect(t.state).toBe('needs_bill');
    await call('POST', '/api/orders', { table: 7, items: [{ mealId: 'plov', qty: 1 }] });
    t = (await call('GET', '/api/snapshot', undefined, w.token)).json.tables.find((x: any) => x.number === 7);
    expect(t.state).toBe('occupied');
  });

  it('order numbers are unique and increasing', async () => {
    const a = (await call('POST', '/api/orders', { table: 9, items: [{ mealId: 'plov', qty: 1 }] })).json.order.number;
    const b = (await call('POST', '/api/orders', { table: 9, items: [{ mealId: 'plov', qty: 1 }] })).json.order.number;
    expect(Number(b.slice(1))).toBe(Number(a.slice(1)) + 1);
  });

  it('sold-out meals cannot be ordered', async () => {
    const a = await login('0000');
    await call('PATCH', '/api/meals/lagman', { available: false }, a.token);
    expect((await call('POST', '/api/orders', { table: 1, items: [{ mealId: 'lagman', qty: 1 }] })).status).toBe(400);
    await call('PATCH', '/api/meals/lagman', { available: true }, a.token);
  });
});

describe('admin-only management', () => {
  it('waiters cannot manage events, meals, staff or settings', async () => {
    const w = await login('1234');
    const ev = { title: ['x', 'x'], type: 'percent', params: { percent: 10 } };
    expect((await call('POST', '/api/events', ev, w.token)).status).toBe(403);
    expect((await call('PATCH', '/api/meals/plov', { price: 1 }, w.token)).status).toBe(403);
    expect((await call('GET', '/api/staff', undefined, w.token)).status).toBe(403);
    expect((await call('PUT', '/api/settings', { tableCount: 5 }, w.token)).status).toBe(403);
    expect((await call('POST', '/api/events', ev)).status).toBe(401);
  });

  it('admin creates, edits and deletes an event; validation errors are 400', async () => {
    const a = await login('0000');
    const bad = await call('POST', '/api/events', { title: ['x', 'x'], type: 'percent', params: { percent: 500 } }, a.token);
    expect(bad.status).toBe(400);
    const created = await call('POST', '/api/events', {
      title: ['Buy 2 Get 1', 'Ikkitasiga bittasi'], type: 'buy_x_get_y', params: { buy: 2, get: 1 }, categoryIds: ['sushi'], schedule: {}, active: true,
    }, a.token);
    expect(created.status).toBe(201);
    const id = created.json.event.id;
    const o = (await call('POST', '/api/orders', { table: 4, items: [{ mealId: 'california-roll', qty: 3 }] })).json.order;
    expect(o.discount).toBe(98000);
    const upd = await call('PUT', `/api/events/${id}`, { ...created.json.event, active: false }, a.token);
    expect(upd.json.event.active).toBe(false);
    const o2 = (await call('POST', '/api/orders', { table: 4, items: [{ mealId: 'california-roll', qty: 3 }] })).json.order;
    expect(o2.discount).toBe(0);
    expect((await call('DELETE', `/api/events/${id}`, undefined, a.token)).status).toBe(200);
  });

  it('admin meal and category CRUD with integrity checks', async () => {
    const a = await login('0000');
    const cat = await call('POST', '/api/categories', { name: ['Salads', 'Salatlar'], icon: '🥗' }, a.token);
    expect(cat.status).toBe(201);
    const meal = await call('POST', '/api/meals', {
      categoryId: cat.json.category.id, price: 30000, name: ['Greek salad', 'Yunon salati'],
      ingredients: [{ id: 'feta', name: ['Feta', 'Feta'], amount: 40, unit: 'g', color: '#ffffff', shape: 'slab' }],
      model: { kind: 'generic', container: 'bowl' },
    }, a.token);
    expect(meal.status).toBe(201);
    expect((await call('DELETE', `/api/categories/${cat.json.category.id}`, undefined, a.token)).status).toBe(409);
    const dup = await call('POST', '/api/meals', {
      categoryId: cat.json.category.id, price: 1, name: ['x', 'x'],
      ingredients: [{ id: 'a', name: ['a', 'a'], amount: 1, unit: 'g', color: '#000000' }, { id: 'a', name: ['a', 'a'], amount: 1, unit: 'g', color: '#000000' }],
    }, a.token);
    expect(dup.status).toBe(400);
    expect((await call('DELETE', `/api/meals/${meal.json.meal.id}`, undefined, a.token)).status).toBe(200);
    expect((await call('DELETE', `/api/categories/${cat.json.category.id}`, undefined, a.token)).status).toBe(200);
  });

  it('staff: unique PINs, last admin protected, PIN change invalidates sessions', async () => {
    const a = await login('0000');
    expect((await call('POST', '/api/staff', { name: 'Dup', role: 'waiter', pin: '1234' }, a.token)).status).toBe(400);
    const made = await call('POST', '/api/staff', { name: 'Ali', role: 'waiter', pin: '4321' }, a.token);
    expect(made.status).toBe(201);
    const ali = made.json.staff.find((s: any) => s.name === 'Ali');
    const aliSession = await login('4321');
    expect((await call('GET', '/api/me', undefined, aliSession.token)).status).toBe(200);
    await call('PUT', `/api/staff/${ali.id}`, { pin: '5555' }, a.token);
    expect((await call('GET', '/api/me', undefined, aliSession.token)).status).toBe(401);
    expect((await call('PUT', `/api/staff/${a.staff.id}`, { role: 'waiter' }, a.token)).status).toBe(400);
    expect((await call('DELETE', `/api/staff/${a.staff.id}`, undefined, a.token)).status).toBe(400);
    expect((await call('DELETE', `/api/staff/${ali.id}`, undefined, a.token)).status).toBe(200);
  });

  it('settings: table count can grow, and cannot drop tables with open orders', async () => {
    const a = await login('0000');
    expect((await call('PUT', '/api/settings', { tableCount: 15 }, a.token)).status).toBe(200);
    expect((await call('GET', '/api/snapshot')).json.tables.length).toBe(15);
    await call('POST', '/api/orders', { table: 15, items: [{ mealId: 'plov', qty: 1 }] });
    expect((await call('PUT', '/api/settings', { tableCount: 10 }, a.token)).status).toBe(409);
    expect((await call('PUT', '/api/settings', { tableCount: 0 }, a.token)).status).toBe(400);
  });

  it('uploads accept real images only', async () => {
    const a = await login('0000');
    const png = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(40)]).toString('base64');
    const ok = await call('POST', '/api/upload', { dataUrl: 'data:image/png;base64,' + png }, a.token);
    expect(ok.status).toBe(201);
    expect(ok.json.path).toMatch(/^\/uploads\/.+\.png$/);
    const served = await fetch(base + ok.json.path);
    expect(served.status).toBe(200);
    const fake = Buffer.from('<script>alert(1)</script>').toString('base64');
    expect((await call('POST', '/api/upload', { dataUrl: 'data:image/png;base64,' + fake }, a.token)).status).toBe(400);
    expect((await call('POST', '/api/upload', { dataUrl: 'data:text/html;base64,' + fake }, a.token)).status).toBe(400);
    expect((await call('POST', '/api/upload', { dataUrl: 'data:image/png;base64,' + png })).status).toBe(401);
  });
});

describe('realtime', () => {
  it('broadcasts a change message when an order is placed', async () => {
    const ws = new WebSocket(base.replace('http', 'ws') + '/ws');
    const msgs: any[] = [];
    ws.on('message', (d) => msgs.push(JSON.parse(String(d))));
    await new Promise((r) => ws.once('open', r));
    await new Promise((r) => setTimeout(r, 50));
    await call('POST', '/api/orders', { table: 6, items: [{ mealId: 'plov', qty: 1 }] });
    await new Promise((r) => setTimeout(r, 150));
    ws.close();
    expect(msgs.some((m) => m.type === 'changed')).toBe(true);
  });
});

describe('anti-spam', () => {
  it('rate-limits anonymous orders per IP but not staff', async () => {
    const d2 = fs.mkdtempSync(path.join(os.tmpdir(), 'sizzle-rl-'));
    const c2 = createApp({ dbPath: path.join(d2, 'r.db'), dataDir: d2, clientOrderLimit: 2 });
    await new Promise<void>((r) => c2.server.listen(0, '127.0.0.1', r));
    const b2 = `http://127.0.0.1:${(c2.server.address() as AddressInfo).port}`;
    const post = (token?: string) => fetch(b2 + '/api/orders', {
      method: 'POST', headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) },
      body: JSON.stringify({ table: 1, items: [{ mealId: 'plov', qty: 1 }] }),
    });
    expect((await post()).status).toBe(201);
    expect((await post()).status).toBe(201);
    expect((await post()).status).toBe(429);
    const login = await (await fetch(b2 + '/api/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ pin: '1234' }) })).json() as any;
    expect((await post(login.token)).status).toBe(201);
    await c2.close();
    fs.rmSync(d2, { recursive: true, force: true });
  });
});
