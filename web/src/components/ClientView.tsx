import { useMemo, useState } from 'react';
import type { Category, EventDef, Meal, Order } from '../../../shared/types.ts';
import { isEventActive, mealPromo, priceCart } from '../../../shared/pricing.ts';
import { useApp } from '../store.tsx';
import { categoryChain, eventCovers, formatMoney, loc, toPriceable } from '../lib/menu.ts';
import { eventLabel, scheduleText } from '../lib/eventText.ts';
import { MealThumb } from './common.tsx';
import { hasPhotoModel } from '../three/photoreal.ts';
import { MealModal } from './MealModal.tsx';
import { Checkout, ResultModal } from './Checkout.tsx';

export function ClientView() {
  const { snap, t, lang, now, catsById, cart, clearCart, addToCart } = useApp();
  const [cat, setCat] = useState<string>('all');
  const [sub, setSub] = useState<string | null>(null);
  const [eventId, setEventId] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [openMeal, setOpenMeal] = useState<string | null>(null);
  const [checkout, setCheckout] = useState(false);
  const [result, setResult] = useState<Order | null>(null);

  const meals = snap?.meals ?? [];
  const events = snap?.events ?? [];
  const topCats = useMemo(() => (snap?.categories ?? []).filter((c) => !c.parentId).sort((a, b) => a.sort - b.sort), [snap?.categories]);
  const children = useMemo(() => (snap?.categories ?? []).filter((c) => c.parentId === cat).sort((a, b) => a.sort - b.sort), [snap?.categories, cat]);
  const activeEvents = useMemo(() => events.filter((e) => isEventActive(e, now)), [events, now]);

  const promoOf = (m: Meal) => mealPromo(toPriceable(m, catsById), events, now);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const ev = eventId ? activeEvents.find((e) => e.id === eventId) : undefined;
    return meals.filter((m) => {
      if (needle && !(m.name[0] + ' ' + m.name[1] + ' ' + m.tag[0] + ' ' + m.tag[1]).toLowerCase().includes(needle)) return false;
      if (eventId) return !!ev && eventCovers(ev, m, catsById);
      if (cat === 'promo') return promoOf(m) !== null;
      if (cat !== 'all') {
        const chain = categoryChain(m.categoryId, catsById);
        if (!chain.includes(cat)) return false;
        if (sub && !chain.includes(sub)) return false;
      }
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meals, cat, sub, eventId, q, activeEvents, catsById, events, now]);

  const priced = useMemo(() => {
    const inputs = cart.flatMap((c) => { const m = snap?.meals.find((x) => x.id === c.mealId); return m ? [{ meal: toPriceable(m, catsById), qty: c.qty }] : []; });
    return { ...priceCart(inputs, events, now), count: cart.reduce((s, c) => s + c.qty, 0) };
  }, [cart, snap?.meals, catsById, events, now]);

  const available = visible.filter((m) => m.available).length;
  const selectCat = (id: string) => { setCat(id); setSub(null); setEventId(null); };

  return (
    <section className="view wrap" aria-label={t('client')}>
      <div className="hero">
        <div>
          <h1>{t('heroA')}<em>{t('heroEm')}</em>{t('heroB')}</h1>
          <p>{t('heroDesc')}</p>
          <div className="hero-badges">
            <span className="chip-badge">🧊 {t('realTime')}</span>
            <span className="chip-badge">🥗 {t('transparency')}</span>
            <span className="chip-badge">✨ {t('hdMode')}</span>
          </div>
        </div>
        <div className="hero-card">
          <h3>{t('how')}</h3>
          <ul>
            <li><span className="num-badge">1</span><span>{t('step1')}</span></li>
            <li><span className="num-badge">2</span><span>{t('step2')}</span></li>
            <li><span className="num-badge">3</span><span>{t('step3')}</span></li>
          </ul>
        </div>
      </div>

      {activeEvents.length > 0 && (
        <div className="event-strip" aria-label={t('promotions')}>
          {activeEvents.map((ev) => (
            <EventCard key={ev.id} ev={ev} active={eventId === ev.id} onClick={() => { setEventId(eventId === ev.id ? null : ev.id); setCat('all'); setSub(null); }} />
          ))}
        </div>
      )}

      <div className="toolbar">
        <div className="chips" role="group" aria-label={t('categories')}>
          <button className="chip" aria-pressed={cat === 'all' && !eventId} onClick={() => selectCat('all')}>{t('All')}</button>
          <button className="chip chip-promo" aria-pressed={cat === 'promo' && !eventId} onClick={() => selectCat('promo')}>🔥 {t('promoMeals')}</button>
          {topCats.map((c) => (
            <button key={c.id} className="chip" aria-pressed={cat === c.id && !eventId} onClick={() => selectCat(c.id)}>{c.icon} {loc(c.name, lang)}</button>
          ))}
        </div>
        <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search')} aria-label={t('search')} />
      </div>

      {children.length > 0 && !eventId && (
        <div className="chips subchips" role="group" aria-label={t('subCategories')}>
          <button className="chip chip-sm" aria-pressed={sub === null} onClick={() => setSub(null)}>{t('All')}</button>
          {children.map((c: Category) => (
            <button key={c.id} className="chip chip-sm" aria-pressed={sub === c.id} onClick={() => setSub(c.id)}>{c.icon} {loc(c.name, lang)}</button>
          ))}
        </div>
      )}
      {eventId && (
        <div className="filter-note">
          {t('showingEvent', { name: loc(events.find((e) => e.id === eventId)?.title ?? ['', ''], lang) })}
          <button className="btn btn-sm" onClick={() => setEventId(null)}>{t('clearFilter')}</button>
        </div>
      )}
      <div className="muted menu-count" aria-live="polite">{t('dishCount', { n: visible.length, a: available })}</div>

      {!snap ? (
        <p className="empty">{t('loading')}</p>
      ) : visible.length === 0 ? (
        <p className="empty">{t('noMeals')}</p>
      ) : (
        <div className="menu-grid">
          {visible.map((m) => {
            const promo = promoOf(m);
            const name = loc(m.name, lang);
            return (
              <article className="card" key={m.id}>
                <button className="card-media" onClick={() => setOpenMeal(m.id)} aria-label={t('viewLabel', { name })}>
                  <MealThumb meal={m} icon={catsById.get(m.categoryId)?.icon ?? '🍽️'} />
                  <span className="card-badge">{loc(catsById.get(m.categoryId)?.name ?? ['', ''], lang)}</span>
                  <span className={'card-badge3d' + (m.available ? '' : ' sold')} title={hasPhotoModel(m.id) ? t('hdHint') : undefined}>
                    {m.available ? (hasPhotoModel(m.id) ? '3D · HD' : '3D') : t('soldOut')}
                  </span>
                  {promo && <span className="card-promo">{eventLabel(promo.event, t, lang)}</span>}
                </button>
                <div className="card-body">
                  <h3>{name}</h3>
                  <p className="card-tag">{loc(m.tag, lang)}</p>
                  <div className="card-foot">
                    <span className="price-box">
                      {promo?.discountedPrice != null ? (
                        <><span className="price price-new">{formatMoney(promo.discountedPrice, lang)}</span><s className="price-old">{formatMoney(m.price, lang)}</s></>
                      ) : (
                        <span className="price">{formatMoney(m.price, lang)}</span>
                      )}
                    </span>
                    <div className="card-actions">
                      <button className="btn" onClick={() => setOpenMeal(m.id)}>{t('view3d')}</button>
                      <button className="btn btn-primary btn-icon" disabled={!m.available} aria-label={t('addLabel', { name })} onClick={() => addToCart(m.id, 1)}>+</button>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
      <p className="demo-note">{t('lanNote')}</p>

      {priced.count > 0 && (
        <div className="cart-bar">
          <div className="cart-inner">
            <div className="cart-count">{priced.count}</div>
            <div className="cart-text">
              <b>{t('cartTitle', { n: priced.count })}</b>
              <span>{priced.discount > 0 ? t('youSave', { amount: formatMoney(priced.discount, lang) }) : t('cartSub', { n: priced.count })}</span>
            </div>
            <div className="cart-actions">
              <button className="btn cart-clear" onClick={() => { clearCart(); }}>{t('clear')}</button>
              <button className="btn btn-primary" onClick={() => setCheckout(true)}>{t('placeOrder')} · {formatMoney(priced.total, lang)}</button>
            </div>
          </div>
        </div>
      )}

      {openMeal && snap?.meals.find((m) => m.id === openMeal) && (
        <MealModal mealId={openMeal} onClose={() => setOpenMeal(null)} />
      )}
      {checkout && priced.count > 0 && (
        <Checkout onClose={() => setCheckout(false)} onPlaced={(o) => { setCheckout(false); setResult(o); }} />
      )}
      {result && <ResultModal order={result} onClose={() => setResult(null)} />}
    </section>
  );
}

function EventCard({ ev, active, onClick }: { ev: EventDef; active: boolean; onClick: () => void }) {
  const { t, lang } = useApp();
  return (
    <button className={'event-card' + (active ? ' on' : '')} onClick={onClick} aria-pressed={active}
      style={ev.banner ? { backgroundImage: `linear-gradient(90deg,#1a0f08e6 35%,#1a0f0899),url(${ev.banner})` } : undefined}>
      <span className="event-badge">{eventLabel(ev, t, lang)}</span>
      <b>{loc(ev.title, lang)}</b>
      <small>{scheduleText(ev, t, lang)}</small>
    </button>
  );
}
