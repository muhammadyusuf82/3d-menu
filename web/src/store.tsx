import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Category, Meal, Order, Snapshot } from '../../shared/types.ts';
import { api, ApiError, getToken, setToken, type Session } from './lib/api.ts';
import { connectRealtime } from './lib/realtime.ts';
import { reuse, type Lang } from './lib/menu.ts';
import { makeT, type TFn } from './lib/i18n.ts';
import type { Quality } from './three/viewer.ts';

export interface CartItem { mealId: string; qty: number }
export interface ToastMsg { id: number; text: string; kind: 'info' | 'error' | 'ok' }

interface AppState {
  snap: Snapshot | null;
  online: boolean;
  loadError: boolean;
  now: Date;
  lang: Lang;
  setLang: (l: Lang) => void;
  t: TFn;
  session: Session | null;
  login: (pin: string) => Promise<Session>;
  logout: () => Promise<void>;
  quality: Quality;
  setQuality: (q: Quality) => void;
  cart: CartItem[];
  addToCart: (mealId: string, qty: number) => boolean;
  clearCart: () => void;
  setCartQty: (mealId: string, qty: number) => void;
  toasts: ToastMsg[];
  toast: (text: string, kind?: ToastMsg['kind']) => void;
  errorText: (e: unknown) => string;
  refresh: () => Promise<void>;
  mealsById: Map<string, Meal>;
  catsById: Map<string, Category>;
}

const Ctx = createContext<AppState | null>(null);
export const useApp = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error('AppProvider missing');
  return v;
};

const lsGet = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

function beep(freq = 880) {
  try {
    const AC = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new AC();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = freq; o.type = 'sine';
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    o.connect(g); g.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.4);
    o.onended = () => ctx.close();
  } catch { /* audio blocked until first user gesture */ }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [tick, setTick] = useState(0);
  const [offset, setOffset] = useState(0);
  const [lang, setLangState] = useState<Lang>(() => (lsGet('sizzle_lang') === 'uz' ? 'uz' : 'en'));
  const [session, setSession] = useState<Session | null>(null);
  const [quality, setQualityState] = useState<Quality>(() => (lsGet('sizzle_quality') === 'hd' ? 'hd' : 'standard'));
  const [cart, setCart] = useState<CartItem[]>(() => {
    try {
      const raw = JSON.parse(lsGet('sizzle_cart') || '[]');
      return Array.isArray(raw) ? raw.filter((c) => typeof c?.mealId === 'string' && Number.isInteger(c.qty) && c.qty > 0).map((c) => ({ mealId: c.mealId, qty: Math.min(20, c.qty) })) : [];
    } catch { return []; }
  });
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const t = useMemo(() => makeT(lang), [lang]);
  const tRef = useRef(t);
  tRef.current = t;
  const sessionRef = useRef<Session | null>(null);
  sessionRef.current = session;
  const prevOrders = useRef<Map<string, string> | null>(null);

  const toast = useCallback((text: string, kind: ToastMsg['kind'] = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((l) => [...l.slice(-2), { id, text, kind }]);
    setTimeout(() => setToasts((l) => l.filter((x) => x.id !== id)), 3600);
  }, []);

  const errorText = useCallback((e: unknown) => {
    if (e instanceof ApiError) {
      if (e.status === 0) return tRef.current('errNetwork');
      return tRef.current('srv:' + e.message) ;
    }
    return tRef.current('errGeneric');
  }, []);

  // ---- alerts for staff when orders appear / become ready
  const detectOrderChanges = useCallback((orders: Order[]) => {
    const prev = prevOrders.current;
    const next = new Map(orders.map((o) => [o.id, o.status] as const));
    prevOrders.current = next;
    if (!prev || !sessionRef.current) return;
    const tt = tRef.current;
    for (const o of orders) {
      const before = prev.get(o.id);
      if (before === undefined) {
        if (o.source === 'client') { toast(tt('alertNew', { number: o.number, table: o.table }), 'ok'); beep(660); }
      } else if (before !== 'ready' && o.status === 'ready') {
        toast(tt('alertReady', { number: o.number, table: o.table }), 'ok'); beep(990);
      }
    }
  }, [toast]);

  const refreshing = useRef(false);
  const again = useRef(false);
  const refresh = useCallback(async () => {
    if (refreshing.current) { again.current = true; return; }
    refreshing.current = true;
    try {
      do {
        again.current = false;
        try {
          const s = await api.snapshot();
          setOffset(s.serverNow - Date.now());
          setSnap((prev) => ({
            ...s,
            meals: reuse(prev?.meals, s.meals),
            categories: reuse(prev?.categories, s.categories),
            events: reuse(prev?.events, s.events),
            orders: reuse(prev?.orders, s.orders),
          }));
          detectOrderChanges(s.orders);
          setLoadError(false);
        } catch (e) {
          if (e instanceof ApiError && e.status === 0) setLoadError(true);
        }
      } while (again.current);
    } finally { refreshing.current = false; }
  }, [detectOrderChanges]);

  // restore session
  useEffect(() => {
    if (!getToken()) return;
    api.me().then(setSession).catch((e) => { if (e instanceof ApiError && e.status === 401) setToken(null); });
  }, []);
  // reset order baseline whenever the staff session changes (orders only come with a session)
  useEffect(() => { prevOrders.current = null; void refresh(); }, [session, refresh]);

  // realtime + polling fallback
  useEffect(() => {
    let timer: number | undefined;
    const debounced = () => { clearTimeout(timer); timer = window.setTimeout(() => void refresh(), 60); };
    const stop = connectRealtime({ onChanged: debounced, onStatus: setOnline });
    const poll = window.setInterval(() => { if (!document.hidden) void refresh(); }, 20000);
    const vis = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', vis);
    return () => { stop(); clearInterval(poll); clearTimeout(timer); document.removeEventListener('visibilitychange', vis); };
  }, [refresh]);

  // time-based events (Happy Hour...) need a periodic re-evaluation
  useEffect(() => { const i = window.setInterval(() => setTick((x) => x + 1), 30000); return () => clearInterval(i); }, []);
  const now = useMemo(() => new Date(Date.now() + offset), [tick, offset, snap]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { document.documentElement.lang = lang; document.title = t('title'); }, [lang, t]);

  const setLang = useCallback((l: Lang) => { setLangState(l); lsSet('sizzle_lang', l); }, []);
  const setQuality = useCallback((q: Quality) => { setQualityState(q); lsSet('sizzle_quality', q); }, []);

  const login = useCallback(async (pin: string) => {
    const r = await api.login(pin);
    setToken(r.token);
    const s: Session = { staff: r.staff, defaultPin: r.defaultPin };
    setSession(s);
    return s;
  }, []);
  const logout = useCallback(async () => {
    try { await api.logout(); } catch { /* token may already be invalid */ }
    setToken(null);
    setSession(null);
  }, []);

  // cart (per device)
  useEffect(() => { lsSet('sizzle_cart', JSON.stringify(cart)); }, [cart]);
  const mealsById = useMemo(() => new Map((snap?.meals ?? []).map((m) => [m.id, m])), [snap?.meals]);
  const catsById = useMemo(() => new Map((snap?.categories ?? []).map((c) => [c.id, c])), [snap?.categories]);
  // drop cart lines whose meal no longer exists
  useEffect(() => {
    if (!snap) return;
    setCart((c) => (c.some((x) => !mealsById.has(x.mealId)) ? c.filter((x) => mealsById.has(x.mealId)) : c));
  }, [snap, mealsById]);

  const addToCart = useCallback((mealId: string, qty: number) => {
    const meal = mealsById.get(mealId);
    const tt = tRef.current;
    if (!meal || !meal.available) { toast(tt('notAvailable', { name: meal ? meal.name[0] : '' }), 'error'); return false; }
    const current = cart.find((x) => x.mealId === mealId)?.qty ?? 0;
    if (current + qty > 20) { toast(tt('maxQty'), 'error'); return false; }
    setCart((c) => {
      const found = c.find((x) => x.mealId === mealId);
      return found ? c.map((x) => (x.mealId === mealId ? { ...x, qty: Math.min(20, x.qty + qty) } : x)) : [...c, { mealId, qty }];
    });
    toast(tt('added', { name: lang === 'uz' ? meal.name[1] || meal.name[0] : meal.name[0] }), 'ok');
    return true;
  }, [mealsById, toast, cart, lang]);
  const clearCart = useCallback(() => setCart([]), []);
  const setCartQty = useCallback((mealId: string, qty: number) => {
    setCart((c) => (qty <= 0 ? c.filter((x) => x.mealId !== mealId) : c.map((x) => (x.mealId === mealId ? { ...x, qty: Math.min(20, qty) } : x))));
  }, []);

  const value: AppState = {
    snap, online, loadError, now, lang, setLang, t, session, login, logout, quality, setQuality,
    cart, addToCart, clearCart, setCartQty, toasts, toast, errorText, refresh, mealsById, catsById,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
