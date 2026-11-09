import { createRequire } from 'node:module';
import type { DatabaseSync as DatabaseSyncType } from 'node:sqlite';
import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import type { Category, EventDef, Meal, Order, OrderItem, OrderStatus, Role, StaffRow } from '../shared/types.ts';
import { DEFAULT_STAFF, DEFAULT_TABLE_COUNT, SEED_CATEGORIES, SEED_EVENTS, SEED_MEALS, SEED_V2_MEAL_IDS } from '../shared/seed.ts';

// Loaded via require so bundlers (vitest/vite) don't try to resolve the `node:sqlite` builtin.
const { DatabaseSync } = createRequire(import.meta.url)('node:sqlite') as typeof import('node:sqlite');

export function hashPin(pin: string): string {
  const salt = randomBytes(16);
  const hash = scryptSync(pin, salt, 32);
  return salt.toString('hex') + ':' + hash.toString('hex');
}

export function verifyPin(pin: string, stored: string): boolean {
  const [saltHex, hashHex] = stored.split(':');
  if (!saltHex || !hashHex) return false;
  const expected = Buffer.from(hashHex, 'hex');
  const actual = scryptSync(pin, Buffer.from(saltHex, 'hex'), expected.length);
  return timingSafeEqual(expected, actual);
}

export interface StaffRecord { id: string; name: string; role: Role; pinHash: string; defaultPin: boolean }

type Row = Record<string, any>;

export class Store {
  readonly db: DatabaseSyncType;

  constructor(path: string) {
    this.db = new DatabaseSync(path);
    this.db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
    this.migrate();
    this.seedIfEmpty();
  }

  close() { this.db.close(); }

  private migrate() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS categories (id TEXT PRIMARY KEY, sort INTEGER NOT NULL, doc TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS meals (id TEXT PRIMARY KEY, sort INTEGER NOT NULL, doc TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, sort INTEGER NOT NULL, doc TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS tables (number INTEGER PRIMARY KEY, bill_requested INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY, number TEXT NOT NULL, table_no INTEGER NOT NULL, source TEXT NOT NULL,
        staff_id TEXT, staff_name TEXT, status TEXT NOT NULL, items TEXT NOT NULL,
        subtotal INTEGER NOT NULL, discount INTEGER NOT NULL, total INTEGER NOT NULL,
        note TEXT NOT NULL DEFAULT '', cancel_reason TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS orders_status ON orders(status);
      CREATE INDEX IF NOT EXISTS orders_table ON orders(table_no);
      CREATE TABLE IF NOT EXISTS staff (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, pin_hash TEXT NOT NULL, default_pin INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, staff_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    `);
  }

  private seedIfEmpty() {
    const seeded = this.db.prepare("SELECT value FROM meta WHERE key = 'seeded'").get();
    if (!seeded) this.seedAll();
    this.migrateSeed();
  }

  /** Adds meals introduced after the first release to databases created before them (never re-adds deleted ones twice). */
  private migrateSeed() {
    const row = this.db.prepare("SELECT value FROM meta WHERE key = 'seedVersion'").get() as Row | undefined;
    if (Number(row?.value ?? 1) >= 2) return;
    this.tx(() => {
      for (const id of SEED_V2_MEAL_IDS) {
        const m = SEED_MEALS.find((x) => x.id === id);
        if (m && !this.meal(id) && this.category(m.categoryId)) this.putMeal(m);
      }
      this.db.prepare("INSERT INTO meta (key, value) VALUES ('seedVersion', '2') ON CONFLICT(key) DO UPDATE SET value = excluded.value").run();
    });
  }

  private seedAll() {
    this.tx(() => {
      SEED_CATEGORIES.forEach((c, i) => this.putCategory(c, i));
      SEED_MEALS.forEach((m, i) => this.putMeal(m, i));
      SEED_EVENTS.forEach((e, i) => this.putEvent(e, i));
      this.setTableCount(DEFAULT_TABLE_COUNT);
      for (const s of DEFAULT_STAFF) {
        this.db.prepare('INSERT INTO staff (id, name, role, pin_hash, default_pin) VALUES (?,?,?,?,1)')
          .run(s.id, s.name, s.role, hashPin(s.pin));
      }
      this.db.prepare("INSERT INTO meta (key, value) VALUES ('nextNo', '1041')").run();
      this.db.prepare("INSERT INTO meta (key, value) VALUES ('seeded', '1')").run();
    });
  }

  tx<T>(fn: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const r = fn();
      this.db.exec('COMMIT');
      return r;
    } catch (e) {
      this.db.exec('ROLLBACK');
      throw e;
    }
  }

  // ---- catalog (JSON documents)
  private nextSort(table: 'categories' | 'meals' | 'events'): number {
    const r = this.db.prepare(`SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM ${table}`).get() as Row;
    return Number(r.n);
  }
  private putDoc(table: 'categories' | 'meals' | 'events', id: string, doc: unknown, sort?: number) {
    const s = sort ?? (this.db.prepare(`SELECT sort FROM ${table} WHERE id = ?`).get(id) as Row | undefined)?.sort ?? this.nextSort(table);
    this.db.prepare(`INSERT INTO ${table} (id, sort, doc) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET sort = excluded.sort, doc = excluded.doc`)
      .run(id, Number(s), JSON.stringify(doc));
  }
  private allDocs<T>(table: 'categories' | 'meals' | 'events'): T[] {
    return (this.db.prepare(`SELECT doc FROM ${table} ORDER BY sort, id`).all() as Row[]).map((r) => JSON.parse(r.doc) as T);
  }
  private oneDoc<T>(table: 'categories' | 'meals' | 'events', id: string): T | null {
    const r = this.db.prepare(`SELECT doc FROM ${table} WHERE id = ?`).get(id) as Row | undefined;
    return r ? (JSON.parse(r.doc) as T) : null;
  }

  categories(): Category[] { return this.allDocs<Category>('categories').sort((a, b) => a.sort - b.sort); }
  category(id: string) { return this.oneDoc<Category>('categories', id); }
  putCategory(c: Category, sort?: number) { this.putDoc('categories', c.id, c, sort); }
  deleteCategory(id: string) { this.db.prepare('DELETE FROM categories WHERE id = ?').run(id); }

  meals(): Meal[] { return this.allDocs<Meal>('meals'); }
  meal(id: string) { return this.oneDoc<Meal>('meals', id); }
  putMeal(m: Meal, sort?: number) { this.putDoc('meals', m.id, m, sort); }
  deleteMeal(id: string) { this.db.prepare('DELETE FROM meals WHERE id = ?').run(id); }

  events(): EventDef[] { return this.allDocs<EventDef>('events'); }
  event(id: string) { return this.oneDoc<EventDef>('events', id); }
  putEvent(e: EventDef, sort?: number) { this.putDoc('events', e.id, e, sort); }
  deleteEvent(id: string) { this.db.prepare('DELETE FROM events WHERE id = ?').run(id); }

  // ---- tables
  tableNumbers(): number[] {
    return (this.db.prepare('SELECT number FROM tables ORDER BY number').all() as Row[]).map((r) => Number(r.number));
  }
  tableCount(): number { return this.tableNumbers().length; }
  billFlags(): Map<number, boolean> {
    return new Map((this.db.prepare('SELECT number, bill_requested FROM tables').all() as Row[]).map((r) => [Number(r.number), Number(r.bill_requested) === 1]));
  }
  setBill(n: number, on: boolean) { this.db.prepare('UPDATE tables SET bill_requested = ? WHERE number = ?').run(on ? 1 : 0, n); }
  setTableCount(count: number) {
    const cur = this.tableNumbers();
    for (let n = 1; n <= count; n++) if (!cur.includes(n)) this.db.prepare('INSERT INTO tables (number, bill_requested) VALUES (?, 0)').run(n);
    for (const n of cur) if (n > count) this.db.prepare('DELETE FROM tables WHERE number = ?').run(n);
  }

  // ---- orders
  private rowToOrder(r: Row): Order {
    return {
      id: r.id, number: r.number, table: Number(r.table_no), source: r.source, staffId: r.staff_id ?? null,
      staffName: r.staff_name ?? null, status: r.status as OrderStatus, items: JSON.parse(r.items) as OrderItem[],
      subtotal: Number(r.subtotal), discount: Number(r.discount), total: Number(r.total), note: r.note ?? '',
      cancelReason: r.cancel_reason ?? null, createdAt: Number(r.created_at), updatedAt: Number(r.updated_at),
    };
  }
  orders(limit = 300): Order[] {
    return (this.db.prepare('SELECT * FROM orders ORDER BY created_at DESC, rowid DESC LIMIT ?').all(limit) as Row[]).map((r) => this.rowToOrder(r));
  }
  order(id: string): Order | null {
    const r = this.db.prepare('SELECT * FROM orders WHERE id = ?').get(id) as Row | undefined;
    return r ? this.rowToOrder(r) : null;
  }
  openOrderCounts(): Map<number, number> {
    const rows = this.db.prepare("SELECT table_no, COUNT(*) AS n FROM orders WHERE status IN ('new','preparing','ready') GROUP BY table_no").all() as Row[];
    return new Map(rows.map((r) => [Number(r.table_no), Number(r.n)]));
  }
  allocateNumber(): string {
    const r = this.db.prepare("SELECT value FROM meta WHERE key = 'nextNo'").get() as Row;
    const n = Number(r.value);
    this.db.prepare("UPDATE meta SET value = ? WHERE key = 'nextNo'").run(String(n + 1));
    return '#' + n;
  }
  insertOrder(o: Order) {
    this.db.prepare(`INSERT INTO orders (id, number, table_no, source, staff_id, staff_name, status, items, subtotal, discount, total, note, cancel_reason, created_at, updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
      .run(o.id, o.number, o.table, o.source, o.staffId, o.staffName, o.status, JSON.stringify(o.items), o.subtotal, o.discount, o.total, o.note, o.cancelReason, o.createdAt, o.updatedAt);
  }
  updateOrder(o: Order) {
    this.db.prepare(`UPDATE orders SET status = ?, items = ?, subtotal = ?, discount = ?, total = ?, note = ?, cancel_reason = ?, updated_at = ? WHERE id = ?`)
      .run(o.status, JSON.stringify(o.items), o.subtotal, o.discount, o.total, o.note, o.cancelReason, o.updatedAt, o.id);
  }

  // ---- staff & sessions
  private rowToStaff(r: Row): StaffRecord {
    return { id: r.id, name: r.name, role: r.role as Role, pinHash: r.pin_hash, defaultPin: Number(r.default_pin) === 1 };
  }
  staff(): StaffRecord[] { return (this.db.prepare('SELECT * FROM staff ORDER BY role, name').all() as Row[]).map((r) => this.rowToStaff(r)); }
  staffById(id: string): StaffRecord | null {
    const r = this.db.prepare('SELECT * FROM staff WHERE id = ?').get(id) as Row | undefined;
    return r ? this.rowToStaff(r) : null;
  }
  staffRows(): StaffRow[] { return this.staff().map((s) => ({ id: s.id, name: s.name, role: s.role, defaultPin: s.defaultPin })); }
  findStaffByPin(pin: string): StaffRecord | null {
    return this.staff().find((s) => verifyPin(pin, s.pinHash)) ?? null;
  }
  insertStaff(s: { id: string; name: string; role: Role; pin: string }) {
    this.db.prepare('INSERT INTO staff (id, name, role, pin_hash, default_pin) VALUES (?,?,?,?,0)').run(s.id, s.name, s.role, hashPin(s.pin));
  }
  updateStaff(id: string, patch: { name?: string; role?: Role; pin?: string }) {
    const cur = this.staffById(id);
    if (!cur) return;
    this.db.prepare('UPDATE staff SET name = ?, role = ?, pin_hash = ?, default_pin = ? WHERE id = ?').run(
      patch.name ?? cur.name, patch.role ?? cur.role, patch.pin ? hashPin(patch.pin) : cur.pinHash, patch.pin ? 0 : cur.defaultPin ? 1 : 0, id,
    );
  }
  deleteStaff(id: string) {
    this.db.prepare('DELETE FROM sessions WHERE staff_id = ?').run(id);
    this.db.prepare('DELETE FROM staff WHERE id = ?').run(id);
  }

  createSession(staffId: string, ttlMs: number): string {
    const token = randomBytes(24).toString('hex');
    this.db.prepare('DELETE FROM sessions WHERE expires_at < ?').run(Date.now());
    this.db.prepare('INSERT INTO sessions (token, staff_id, expires_at) VALUES (?,?,?)').run(token, staffId, Date.now() + ttlMs);
    return token;
  }
  sessionStaff(token: string): StaffRecord | null {
    const r = this.db.prepare('SELECT staff_id, expires_at FROM sessions WHERE token = ?').get(token) as Row | undefined;
    if (!r || Number(r.expires_at) < Date.now()) return null;
    return this.staffById(r.staff_id);
  }
  deleteSession(token: string) { this.db.prepare('DELETE FROM sessions WHERE token = ?').run(token); }
  deleteSessionsFor(staffId: string) { this.db.prepare('DELETE FROM sessions WHERE staff_id = ?').run(staffId); }
}
