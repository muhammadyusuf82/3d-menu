import express, { type NextFunction, type Request, type Response } from 'express';
import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import { WebSocket, WebSocketServer } from 'ws';
import { Store, type StaffRecord } from './db.ts';
import { HttpError, bad, cleanCategory, cleanEvent, cleanMeal, cleanName, cleanPin, cleanRole, int, newId } from './validate.ts';
import { priceCart, type PriceableMeal } from '../shared/pricing.ts';
import type { Category, Order, OrderItem, OrderStatus, Snapshot, TableInfo } from '../shared/types.ts';

export interface AppOptions {
  dbPath: string;
  dataDir: string;
  staticDir?: string;
  /** Max anonymous (client) orders per IP per minute. Default 10. */
  clientOrderLimit?: number;
}

const SESSION_TTL = 12 * 60 * 60 * 1000;
const MAX_QTY = 20;
const MAX_LINES = 30;

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  new: ['preparing', 'cancelled'],
  preparing: ['ready', 'new', 'cancelled'],
  ready: ['served', 'preparing', 'cancelled'],
  served: [],
  cancelled: [],
};

function detectImage(buf: Buffer): 'png' | 'jpg' | 'webp' | null {
  if (buf.length > 12 && buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return 'png';
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return 'jpg';
  if (buf.length > 12 && buf.subarray(0, 4).toString('latin1') === 'RIFF' && buf.subarray(8, 12).toString('latin1') === 'WEBP') return 'webp';
  return null;
}

export function createApp(opts: AppOptions) {
  fs.mkdirSync(path.join(opts.dataDir, 'uploads'), { recursive: true });
  const store = new Store(opts.dbPath);
  const app = express();
  const server = http.createServer(app);
  const wss = new WebSocketServer({ server, path: '/ws' });

  const broadcast = () => {
    const msg = JSON.stringify({ type: 'changed', at: Date.now() });
    for (const c of wss.clients) if (c.readyState === WebSocket.OPEN) c.send(msg);
  };
  wss.on('connection', (ws) => {
    ws.send(JSON.stringify({ type: 'hello', at: Date.now() }));
    (ws as any).isAlive = true;
    ws.on('pong', () => { (ws as any).isAlive = true; });
    ws.on('error', () => {});
  });
  const heartbeat = setInterval(() => {
    for (const c of wss.clients) {
      if ((c as any).isAlive === false) { c.terminate(); continue; }
      (c as any).isAlive = false;
      c.ping();
    }
  }, 20000);

  app.disable('x-powered-by');
  app.use((_req, res, next) => { res.setHeader('X-Content-Type-Options', 'nosniff'); next(); });
  app.use(express.json({ limit: '6mb' }));

  // ---- auth
  const staffOf = (res: Response): StaffRecord | null => res.locals.staff ?? null;
  app.use((req, res, next) => {
    const h = req.header('authorization');
    if (h?.startsWith('Bearer ')) res.locals.staff = store.sessionStaff(h.slice(7).trim());
    next();
  });
  const requireStaff = (_req: Request, res: Response, next: NextFunction) =>
    staffOf(res) ? next() : next(new HttpError(401, 'Sign in required'));
  const requireAdmin = (_req: Request, res: Response, next: NextFunction) => {
    const s = staffOf(res);
    if (!s) return next(new HttpError(401, 'Sign in required'));
    if (s.role !== 'admin') return next(new HttpError(403, 'Admin only'));
    next();
  };

  const fails = new Map<string, { n: number; until: number }>();
  const orderRate = new Map<string, number[]>();

  // ---- helpers
  const categoryChain = (id: string, cats: Map<string, Category>): string[] => {
    const out: string[] = [];
    let cur = cats.get(id);
    while (cur && out.length < 4) { out.push(cur.id); cur = cur.parentId ? cats.get(cur.parentId) : undefined; }
    return out;
  };

  function tablesInfo(): TableInfo[] {
    const counts = store.openOrderCounts();
    const flags = store.billFlags();
    return store.tableNumbers().map((n) => {
      const open = counts.get(n) ?? 0;
      const bill = flags.get(n) ?? false;
      return { number: n, openOrders: open, billRequested: bill, state: bill ? 'needs_bill' : open > 0 ? 'occupied' : 'free' };
    });
  }

  function snapshot(staff: StaffRecord | null): Snapshot {
    return {
      serverNow: Date.now(),
      categories: store.categories(),
      meals: store.meals(),
      events: store.events(),
      tables: tablesInfo(),
      orders: staff ? store.orders() : [],
    };
  }

  function buildItems(rawItems: unknown, existing: OrderItem[] = []): { items: OrderItem[]; subtotal: number; discount: number; total: number } {
    if (!Array.isArray(rawItems) || rawItems.length === 0) bad('Add at least one meal');
    const cats = new Map(store.categories().map((c) => [c.id, c]));
    const mealsById = new Map(store.meals().map((m) => [m.id, m]));
    const qtyBy = new Map<string, number>();
    for (const it of existing) qtyBy.set(it.mealId, (qtyBy.get(it.mealId) ?? 0) + it.qty);
    const unitBy = new Map(existing.map((i) => [i.mealId, i.unitPrice]));
    const added = new Set<string>();
    for (const raw of rawItems as any[]) {
      const id = String(raw?.mealId ?? '');
      const qty = int(raw?.qty, 'Quantity', 1, MAX_QTY);
      const meal = mealsById.get(id);
      if (!meal) bad('Unknown meal');
      if (!meal!.available) bad(`${meal!.name[0]} is sold out`);
      qtyBy.set(id, (qtyBy.get(id) ?? 0) + qty);
      added.add(id);
    }
    if (qtyBy.size > MAX_LINES) bad('Too many different meals in one order');
    for (const q of qtyBy.values()) if (q > MAX_QTY) bad(`Maximum ${MAX_QTY} portions per meal`);
    const inputs = [...qtyBy].map(([id, qty]) => {
      const m = mealsById.get(id);
      const price = unitBy.get(id) ?? m?.price ?? 0;
      const meal: PriceableMeal = { id, categoryIds: m ? categoryChain(m.categoryId, cats) : [], price, name: m?.name ?? ['?', '?'] };
      return { meal, qty };
    });
    const priced = priceCart(inputs, store.events(), new Date());
    const items: OrderItem[] = priced.lines.map((l, i) => ({
      mealId: l.mealId, name: inputs[i].meal.name, qty: l.qty, unitPrice: l.unitPrice, discount: l.discount, eventId: l.eventId,
    }));
    return { items, subtotal: priced.subtotal, discount: priced.discount, total: priced.total };
  }

  const noteOf = (v: unknown) => {
    if (v === undefined || v === null) return '';
    if (typeof v !== 'string') bad('Note must be text');
    if ((v as string).length > 200) bad('Note is too long (max 200)');
    return (v as string).trim();
  };

  // ---- public routes
  app.get('/api/snapshot', (_req, res) => { res.json(snapshot(staffOf(res))); });

  app.post('/api/login', (req, res) => {
    const ip = req.ip ?? 'x';
    const f = fails.get(ip);
    if (f && f.until > Date.now()) throw new HttpError(429, `Too many attempts. Try again in ${Math.ceil((f.until - Date.now()) / 1000)}s`);
    const pin = cleanPin(req.body?.pin);
    const staff = store.findStaffByPin(pin);
    if (!staff) {
      const n = (f?.n ?? 0) + 1;
      fails.set(ip, { n, until: n >= 5 ? Date.now() + 30000 : 0 });
      if (n >= 5) fails.set(ip, { n: 0, until: Date.now() + 30000 });
      throw new HttpError(401, 'Incorrect PIN');
    }
    fails.delete(ip);
    const token = store.createSession(staff.id, SESSION_TTL);
    res.json({ token, staff: { id: staff.id, name: staff.name, role: staff.role }, defaultPin: staff.defaultPin });
  });

  app.get('/api/me', requireStaff, (_req, res) => {
    const s = staffOf(res)!;
    res.json({ staff: { id: s.id, name: s.name, role: s.role }, defaultPin: s.defaultPin });
  });

  app.post('/api/logout', requireStaff, (req, res) => {
    store.deleteSession(req.header('authorization')!.slice(7).trim());
    res.json({ ok: true });
  });

  // ---- orders
  app.post('/api/orders', (req, res) => {
    const staff = staffOf(res);
    if (!staff) {
      const ip = req.ip ?? 'x';
      const now = Date.now();
      const recent = (orderRate.get(ip) ?? []).filter((t) => now - t < 60000);
      if (recent.length >= (opts.clientOrderLimit ?? 10)) throw new HttpError(429, 'Too many orders. Please wait a moment.');
      recent.push(now);
      orderRate.set(ip, recent);
    }
    const table = int(req.body?.table, 'Table', 1, 1000);
    if (!store.tableNumbers().includes(table)) bad('Unknown table');
    const note = noteOf(req.body?.note);
    const order = store.tx(() => {
      const priced = buildItems(req.body?.items);
      const now = Date.now();
      const o: Order = {
        id: newId('o'), number: store.allocateNumber(), table, source: staff ? 'waiter' : 'client',
        staffId: staff?.id ?? null, staffName: staff?.name ?? null, status: 'new', items: priced.items,
        subtotal: priced.subtotal, discount: priced.discount, total: priced.total, note, cancelReason: null,
        createdAt: now, updatedAt: now,
      };
      store.insertOrder(o);
      store.setBill(table, false);
      return o;
    });
    broadcast();
    res.status(201).json({ order });
  });

  app.post('/api/orders/:id/items', requireStaff, (req, res) => {
    const order = store.tx(() => {
      const o = store.order(req.params.id);
      if (!o) throw new HttpError(404, 'Order not found');
      if (o.status !== 'new' && o.status !== 'preparing') throw new HttpError(409, 'Items can only be added to new or preparing orders');
      const priced = buildItems(req.body?.items, o.items);
      const next: Order = { ...o, items: priced.items, subtotal: priced.subtotal, discount: priced.discount, total: priced.total, updatedAt: Date.now() };
      if (req.body?.note !== undefined) next.note = [o.note, noteOf(req.body.note)].filter(Boolean).join(' · ').slice(0, 200);
      store.updateOrder(next);
      return next;
    });
    broadcast();
    res.json({ order });
  });

  app.patch('/api/orders/:id/status', requireStaff, (req, res) => {
    const to = req.body?.status as OrderStatus;
    const order = store.tx(() => {
      const o = store.order(req.params.id);
      if (!o) throw new HttpError(404, 'Order not found');
      if (!TRANSITIONS[o.status].includes(to)) throw new HttpError(409, `Cannot change order from ${o.status} to ${String(to)}`);
      let reason: string | null = o.cancelReason;
      if (to === 'cancelled') {
        const r = typeof req.body?.reason === 'string' ? req.body.reason.trim() : '';
        if (!r) throw new HttpError(400, 'A cancel reason is required');
        if (r.length > 200) throw new HttpError(400, 'Reason is too long');
        reason = r;
      }
      const next: Order = { ...o, status: to, cancelReason: reason, updatedAt: Date.now() };
      store.updateOrder(next);
      return next;
    });
    broadcast();
    res.json({ order });
  });

  app.post('/api/tables/:n/bill', requireStaff, (req, res) => {
    const n = Number(req.params.n);
    if (!store.tableNumbers().includes(n)) throw new HttpError(404, 'Unknown table');
    store.setBill(n, req.body?.on === true);
    broadcast();
    res.json({ ok: true });
  });

  // ---- admin: events
  app.post('/api/events', requireAdmin, (req, res) => {
    const ev = cleanEvent(req.body, store);
    store.putEvent(ev);
    broadcast();
    res.status(201).json({ event: ev });
  });
  app.put('/api/events/:id', requireAdmin, (req, res) => {
    if (!store.event(req.params.id)) throw new HttpError(404, 'Event not found');
    const ev = cleanEvent(req.body, store, req.params.id);
    store.putEvent(ev);
    broadcast();
    res.json({ event: ev });
  });
  app.delete('/api/events/:id', requireAdmin, (req, res) => {
    if (!store.event(req.params.id)) throw new HttpError(404, 'Event not found');
    store.deleteEvent(req.params.id);
    broadcast();
    res.json({ ok: true });
  });

  // ---- admin: meals
  app.post('/api/meals', requireAdmin, (req, res) => {
    const m = cleanMeal(req.body, store);
    store.putMeal(m);
    broadcast();
    res.status(201).json({ meal: m });
  });
  app.put('/api/meals/:id', requireAdmin, (req, res) => {
    if (!store.meal(req.params.id)) throw new HttpError(404, 'Meal not found');
    const m = cleanMeal(req.body, store, req.params.id);
    store.putMeal(m);
    broadcast();
    res.json({ meal: m });
  });
  app.patch('/api/meals/:id', requireAdmin, (req, res) => {
    const cur = store.meal(req.params.id);
    if (!cur) throw new HttpError(404, 'Meal not found');
    const next = { ...cur };
    if (req.body?.price !== undefined) next.price = int(req.body.price, 'Price', 0, 100_000_000);
    if (req.body?.available !== undefined) next.available = req.body.available === true;
    store.putMeal(next);
    broadcast();
    res.json({ meal: next });
  });
  app.delete('/api/meals/:id', requireAdmin, (req, res) => {
    if (!store.meal(req.params.id)) throw new HttpError(404, 'Meal not found');
    store.deleteMeal(req.params.id);
    broadcast();
    res.json({ ok: true });
  });

  // ---- admin: categories
  app.post('/api/categories', requireAdmin, (req, res) => {
    const c = cleanCategory(req.body, store);
    store.putCategory(c);
    broadcast();
    res.status(201).json({ category: c });
  });
  app.put('/api/categories/:id', requireAdmin, (req, res) => {
    if (!store.category(req.params.id)) throw new HttpError(404, 'Category not found');
    const c = cleanCategory(req.body, store, req.params.id);
    store.putCategory(c);
    broadcast();
    res.json({ category: c });
  });
  app.delete('/api/categories/:id', requireAdmin, (req, res) => {
    const id = req.params.id;
    if (!store.category(id)) throw new HttpError(404, 'Category not found');
    if (store.categories().some((c) => c.parentId === id)) throw new HttpError(409, 'Delete or move its sub-categories first');
    if (store.meals().some((m) => m.categoryId === id)) throw new HttpError(409, 'Move or delete the meals in this category first');
    store.deleteCategory(id);
    broadcast();
    res.json({ ok: true });
  });

  // ---- admin: staff & settings
  app.get('/api/staff', requireAdmin, (_req, res) => { res.json({ staff: store.staffRows() }); });
  app.post('/api/staff', requireAdmin, (req, res) => {
    const name = cleanName(req.body?.name);
    const role = cleanRole(req.body?.role);
    const pin = cleanPin(req.body?.pin);
    if (store.findStaffByPin(pin)) bad('This PIN is already used by another staff member');
    const id = newId('staff');
    store.insertStaff({ id, name, role, pin });
    res.status(201).json({ staff: store.staffRows() });
  });
  app.put('/api/staff/:id', requireAdmin, (req, res) => {
    const cur = store.staffById(req.params.id);
    if (!cur) throw new HttpError(404, 'Staff member not found');
    const patch: { name?: string; role?: 'waiter' | 'admin'; pin?: string } = {};
    if (req.body?.name !== undefined) patch.name = cleanName(req.body.name);
    if (req.body?.role !== undefined) patch.role = cleanRole(req.body.role);
    if (req.body?.pin) {
      patch.pin = cleanPin(req.body.pin);
      const other = store.findStaffByPin(patch.pin);
      if (other && other.id !== cur.id) bad('This PIN is already used by another staff member');
    }
    if (cur.role === 'admin' && patch.role === 'waiter' && store.staff().filter((s) => s.role === 'admin').length <= 1) bad('There must be at least one admin');
    store.updateStaff(cur.id, patch);
    if (patch.pin || (patch.role && patch.role !== cur.role)) store.deleteSessionsFor(cur.id);
    res.json({ staff: store.staffRows() });
  });
  app.delete('/api/staff/:id', requireAdmin, (req, res) => {
    const cur = store.staffById(req.params.id);
    if (!cur) throw new HttpError(404, 'Staff member not found');
    if (cur.id === staffOf(res)!.id) bad('You cannot delete yourself');
    if (cur.role === 'admin' && store.staff().filter((s) => s.role === 'admin').length <= 1) bad('There must be at least one admin');
    store.deleteStaff(cur.id);
    res.json({ staff: store.staffRows() });
  });
  app.put('/api/settings', requireAdmin, (req, res) => {
    const count = int(req.body?.tableCount, 'Table count', 1, 60);
    const busy = tablesInfo().filter((t) => t.number > count && t.openOrders > 0);
    if (busy.length) throw new HttpError(409, `Tables ${busy.map((t) => t.number).join(', ')} still have open orders`);
    store.setTableCount(count);
    broadcast();
    res.json({ ok: true });
  });

  // ---- uploads (JSON data URL, validated by magic bytes)
  app.post('/api/upload', requireAdmin, (req, res) => {
    const m = /^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/.exec(String(req.body?.dataUrl ?? ''));
    if (!m) bad('Upload a PNG, JPEG or WebP image');
    const buf = Buffer.from(m![2], 'base64');
    if (buf.length > 4 * 1024 * 1024) throw new HttpError(413, 'Image is too large (max 4 MB)');
    const ext = detectImage(buf);
    if (!ext) bad('File is not a valid PNG, JPEG or WebP image');
    const name = `${randomUUID()}.${ext}`;
    fs.writeFileSync(path.join(opts.dataDir, 'uploads', name), buf);
    res.status(201).json({ path: `/uploads/${name}` });
  });
  app.use('/uploads', express.static(path.join(opts.dataDir, 'uploads'), { maxAge: '7d', index: false, dotfiles: 'deny' }));

  app.use('/api', (_req, _res, next) => next(new HttpError(404, 'Not found')));

  // ---- static web app
  if (opts.staticDir) {
    const dir = path.resolve(opts.staticDir);
    app.use(express.static(dir, { index: false, maxAge: '1h' }));
    // checked per request so a build finishing after the server started is picked up
    app.get('*', (_req, res) => {
      const index = path.join(dir, 'index.html');
      if (fs.existsSync(index)) res.sendFile(index);
      else res.status(503).type('text').send('The web app is not built yet. Run "npm run build" in the project folder, then reload this page.');
    });
  }

  // ---- errors
  app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof HttpError) return void res.status(err.status).json({ error: err.message });
    if (err?.type === 'entity.too.large') return void res.status(413).json({ error: 'Request too large' });
    if (err instanceof SyntaxError) return void res.status(400).json({ error: 'Invalid JSON' });
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  });

  return {
    app, server, store,
    close: () => new Promise<void>((resolve) => {
      clearInterval(heartbeat);
      for (const c of wss.clients) c.terminate();
      wss.close();
      server.close(() => { store.close(); resolve(); });
    }),
  };
}
