import type { EventDef, Meal, Category, Order, OrderStatus, Role, Snapshot, StaffRow } from '../../../shared/types.ts';

const TOKEN_KEY = 'sizzle_token';

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: { ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...(token ? { authorization: 'Bearer ' + token } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, (data as any).error || res.statusText);
  return data as T;
}

export interface Session { staff: { id: string; name: string; role: Role }; defaultPin: boolean }
export interface OrderInput { table: number; items: { mealId: string; qty: number }[]; note?: string }

export const api = {
  snapshot: () => req<Snapshot>('GET', '/api/snapshot'),
  login: (pin: string) => req<Session & { token: string }>('POST', '/api/login', { pin }),
  me: () => req<Session>('GET', '/api/me'),
  logout: () => req<{ ok: true }>('POST', '/api/logout'),
  createOrder: (o: OrderInput) => req<{ order: Order }>('POST', '/api/orders', o),
  addItems: (id: string, items: OrderInput['items'], note?: string) => req<{ order: Order }>('POST', `/api/orders/${id}/items`, { items, note }),
  setStatus: (id: string, status: OrderStatus, reason?: string) => req<{ order: Order }>('PATCH', `/api/orders/${id}/status`, { status, reason }),
  setBill: (table: number, on: boolean) => req<{ ok: true }>('POST', `/api/tables/${table}/bill`, { on }),

  saveEvent: (e: Partial<EventDef>) => e.id ? req<{ event: EventDef }>('PUT', `/api/events/${e.id}`, e) : req<{ event: EventDef }>('POST', '/api/events', e),
  deleteEvent: (id: string) => req<{ ok: true }>('DELETE', `/api/events/${id}`),
  saveMeal: (m: Partial<Meal>) => m.id ? req<{ meal: Meal }>('PUT', `/api/meals/${m.id}`, m) : req<{ meal: Meal }>('POST', '/api/meals', m),
  patchMeal: (id: string, p: { price?: number; available?: boolean }) => req<{ meal: Meal }>('PATCH', `/api/meals/${id}`, p),
  deleteMeal: (id: string) => req<{ ok: true }>('DELETE', `/api/meals/${id}`),
  saveCategory: (c: Partial<Category>) => c.id ? req<{ category: Category }>('PUT', `/api/categories/${c.id}`, c) : req<{ category: Category }>('POST', '/api/categories', c),
  deleteCategory: (id: string) => req<{ ok: true }>('DELETE', `/api/categories/${id}`),

  staff: () => req<{ staff: StaffRow[] }>('GET', '/api/staff'),
  addStaff: (s: { name: string; role: Role; pin: string }) => req<{ staff: StaffRow[] }>('POST', '/api/staff', s),
  updateStaff: (id: string, s: { name?: string; role?: Role; pin?: string }) => req<{ staff: StaffRow[] }>('PUT', `/api/staff/${id}`, s),
  deleteStaff: (id: string) => req<{ staff: StaffRow[] }>('DELETE', `/api/staff/${id}`),
  setTableCount: (tableCount: number) => req<{ ok: true }>('PUT', '/api/settings', { tableCount }),
  upload: (dataUrl: string) => req<{ path: string }>('POST', '/api/upload', { dataUrl }),
};

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error('read'));
    r.readAsDataURL(file);
  });
}
