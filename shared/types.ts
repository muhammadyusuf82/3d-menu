export type L10n = [en: string, uz: string];

export type Shape =
  | 'disc' | 'slab' | 'mound' | 'scatter' | 'rings' | 'drizzle' | 'sphere' | 'roll' | 'tall'
  | 'liquid' | 'foam' | 'ice' | 'leaf';

export interface Ingredient {
  id: string;
  name: L10n;
  amount: number;
  unit: 'g' | 'ml' | 'pcs' | 'slices';
  color: string;
  /** Generic 3D shape (used by the generic builder). Legacy burger/hotdog/wrap builders key off `id`. */
  shape?: Shape;
  /** Scale multiplier for the generic 3D builder (default 1). */
  size?: number;
}

export type ModelKind =
  | 'burger' | 'hotdog' | 'wrap' | 'generic';

export type Container = 'none' | 'plate' | 'bowl' | 'glass' | 'mug' | 'cup' | 'board';

export interface ModelSpec {
  kind: ModelKind;
  container: Container;
  /** Generic builder: stack ingredients (default) or lay them side by side (e.g. a fruit platter). */
  arrange?: 'stack' | 'spread';
}

export interface Category {
  id: string;
  parentId: string | null;
  name: L10n;
  icon: string;
  sort: number;
}

export interface Meal {
  id: string;
  categoryId: string;
  price: number; // integer so'm
  prepMin: number;
  kcal: number;
  name: L10n;
  tag: L10n;
  desc: L10n;
  ingredients: Ingredient[];
  model: ModelSpec;
  photo: string | null;
  available: boolean;
}

export type EventType = 'percent' | 'fixed_off' | 'buy_x_get_y';

export interface EventSchedule {
  from?: string; // YYYY-MM-DD inclusive
  to?: string; // YYYY-MM-DD inclusive
  weekdays?: number[]; // 0 = Sunday ... 6 = Saturday
  start?: string; // HH:MM
  end?: string; // HH:MM (if < start the window crosses midnight)
}

export interface EventDef {
  id: string;
  title: L10n;
  type: EventType;
  /** percent: {percent}; fixed_off: {amount}; buy_x_get_y: {buy, get} */
  params: { percent?: number; amount?: number; buy?: number; get?: number };
  mealIds: string[];
  categoryIds: string[];
  schedule: EventSchedule;
  banner: string | null;
  active: boolean;
}

export type OrderStatus = 'new' | 'preparing' | 'ready' | 'served' | 'cancelled';
export const ORDER_STATUSES: OrderStatus[] = ['new', 'preparing', 'ready', 'served', 'cancelled'];

export interface OrderItem {
  mealId: string;
  name: L10n;
  qty: number;
  unitPrice: number;
  discount: number; // total discount for the line
  eventId: string | null;
}

export interface Order {
  id: string;
  number: string;
  table: number;
  source: 'client' | 'waiter';
  staffId: string | null;
  staffName: string | null;
  status: OrderStatus;
  items: OrderItem[];
  subtotal: number;
  discount: number;
  total: number;
  note: string;
  cancelReason: string | null;
  createdAt: number;
  updatedAt: number;
}

export type TableState = 'free' | 'occupied' | 'needs_bill';

export interface TableInfo {
  number: number;
  state: TableState;
  billRequested: boolean;
  openOrders: number;
}

export type Role = 'waiter' | 'admin';

export interface StaffInfo {
  id: string;
  name: string;
  role: Role;
}

export interface StaffRow extends StaffInfo {
  defaultPin: boolean;
}

export interface Snapshot {
  serverNow: number;
  categories: Category[];
  meals: Meal[];
  events: EventDef[];
  tables: TableInfo[];
  /** Only populated for authenticated staff. */
  orders: Order[];
}
