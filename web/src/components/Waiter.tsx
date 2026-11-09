import { useMemo, useState } from 'react';
import type { Order } from '../../../shared/types.ts';
import { mealPromo, priceCart } from '../../../shared/pricing.ts';
import { api } from '../lib/api.ts';
import { categoryChain, formatMoney, loc, toPriceable } from '../lib/menu.ts';
import { eventLabel } from '../lib/eventText.ts';
import { useApp } from '../store.tsx';
import { PinGate } from './common.tsx';
import { OrdersList } from './Orders.tsx';
import { ResultModal } from './Checkout.tsx';

export function WaiterView() {
  const { session } = useApp();
  const [, force] = useState(0);
  if (!session) return <section className="view wrap"><PinGate role="waiter" onDone={() => force((x) => x + 1)} /></section>;
  return <section className="view wrap"><WaiterConsole /></section>;
}

function WaiterConsole() {
  const { snap, session, t, logout, toast, errorText, refresh } = useApp();
  const [table, setTable] = useState<number | null>(null);
  const [tab, setTab] = useState<'orders' | 'order'>('orders');
  const [showDone, setShowDone] = useState(false);

  const orders = snap?.orders ?? [];
  const active = orders.filter((o) => o.status === 'new' || o.status === 'preparing' || o.status === 'ready');
  const shown = useMemo(() => {
    const base = showDone ? orders.slice(0, 60) : [...active].reverse();
    return table ? base.filter((o) => o.table === table) : base;
  }, [orders, active, showDone, table]);

  const selected = snap?.tables.find((x) => x.number === table);
  const setBill = async (on: boolean) => {
    if (!table) return;
    try { await api.setBill(table, on); await refresh(); } catch (e) { toast(errorText(e), 'error'); }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div><h2>{t('waiterConsole')}</h2><p>{t('signedIn', { name: session!.staff.name })}</p></div>
        <button className="btn" onClick={() => { void logout(); toast(t('locked')); }}>🔒 {t('lockConsole')}</button>
      </div>
      <div className="waiter-grid2">
        <section className="block">
          <h3><span className="step">1</span>{t('selectTable')}</h3>
          <div className="table-grid">
            {(snap?.tables ?? []).map((tb) => {
              const label = t(tb.state === 'free' ? 'free' : tb.state === 'needs_bill' ? 'needsBill' : 'busy');
              return (
                <button key={tb.number} className={`table-btn ${tb.state}`} aria-pressed={table === tb.number}
                  aria-label={`${t('tableName', { n: tb.number })} · ${label}`}
                  onClick={() => { setTable(table === tb.number ? null : tb.number); if (table !== tb.number) setTab('order'); else setTab('orders'); }}>
                  {tb.number}<small>{label}{tb.openOrders > 0 ? ` · ${tb.openOrders}` : ''}</small>
                </button>
              );
            })}
          </div>
          <div className="legend">
            <span><i className="lg free" />{t('free')}</span><span><i className="lg occupied" />{t('busy')}</span><span><i className="lg needs_bill" />{t('needsBill')}</span>
          </div>
          <p className="table-hint">{table ? t('tableSelected', { n: table }) : t('noTable')}</p>
          {selected && (
            <div className="table-actions">
              {selected.state === 'needs_bill'
                ? <button className="btn" onClick={() => void setBill(false)}>✅ {t('billPaid')}</button>
                : selected.openOrders > 0 && <button className="btn" onClick={() => void setBill(true)}>🧾 {t('requestBill')}</button>}
            </div>
          )}
        </section>

        <section className="block">
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'order'} className="tab" onClick={() => setTab('order')}>➕ {t('takeOrder')}</button>
            <button role="tab" aria-selected={tab === 'orders'} className="tab" onClick={() => setTab('orders')}>📋 {t('orders')} <span className="count">{active.length}</span></button>
          </div>
          {tab === 'order' ? (
            table ? <OrderBuilder key={table} table={table} /> : <div className="empty">{t('pickTableFirst')}</div>
          ) : (
            <>
              <div className="list-tools">
                <span className="muted">{table ? t('ordersForTable', { n: table }) : t('allTables')}</span>
                <label className="check-inline"><input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} /> {t('showFinished')}</label>
              </div>
              <OrdersList orders={shown} empty={t('noActiveOrders')} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function OrderBuilder({ table }: { table: number }) {
  const { snap, t, lang, now, catsById, toast, errorText, refresh } = useApp();
  const [lines, setLines] = useState<Record<string, number>>({});
  const [note, setNote] = useState('');
  const [cat, setCat] = useState('all');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [result, setResult] = useState<Order | null>(null);

  const meals = snap?.meals ?? [];
  const events = snap?.events ?? [];
  const appendable = (snap?.orders ?? []).filter((o) => o.table === table && (o.status === 'new' || o.status === 'preparing'));
  // default to adding onto the table's open order, if there is one
  const effTarget = target === 'new' ? 'new' : appendable.find((o) => o.id === target)?.id ?? appendable[0]?.id ?? 'new';
  const appendTo = effTarget !== 'new' ? appendable.find((o) => o.id === effTarget) : undefined;
  const topCats = (snap?.categories ?? []).filter((c) => !c.parentId).sort((a, b) => a.sort - b.sort);

  const list = meals.filter((m) => {
    if (cat !== 'all' && !categoryChain(m.categoryId, catsById).includes(cat)) return false;
    const n = q.trim().toLowerCase();
    return !n || (m.name[0] + ' ' + m.name[1]).toLowerCase().includes(n);
  });

  const entries = Object.entries(lines).filter(([, qty]) => qty > 0);
  const priced = useMemo(() => {
    const rows = entries.flatMap(([id, qty]) => { const m = meals.find((x) => x.id === id); return m ? [{ m, qty }] : []; });
    return { rows, p: priceCart(rows.map((r) => ({ meal: toPriceable(r.m, catsById), qty: r.qty })), events, now) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, meals, catsById, events, now]);

  const bump = (id: string, d: number) => setLines((l) => {
    const next = Math.max(0, Math.min(20, (l[id] ?? 0) + d));
    const copy = { ...l };
    if (next === 0) delete copy[id]; else copy[id] = next;
    return copy;
  });

  const send = async () => {
    if (entries.length === 0) { toast(t('addFirst'), 'error'); return; }
    const items = entries.map(([mealId, qty]) => ({ mealId, qty }));
    setBusy(true);
    try {
      if (effTarget !== 'new' && appendTo) {
        await api.addItems(appendTo.id, items, note.trim() || undefined);
        toast(t('itemsAdded', { number: appendTo.number }), 'ok');
      } else {
        const { order } = await api.createOrder({ table, items, note: note.trim() || undefined });
        setResult(order);
      }
      setLines({});
      setNote('');
    } catch (e) { toast(errorText(e), 'error'); }
    finally { setBusy(false); void refresh(); }
  };

  return (
    <div className="builder">
      <div className="builder-menu">
        <div className="chips" role="group" aria-label={t('categories')}>
          <button className="chip chip-sm" aria-pressed={cat === 'all'} onClick={() => setCat('all')}>{t('All')}</button>
          {topCats.map((c) => <button key={c.id} className="chip chip-sm" aria-pressed={cat === c.id} onClick={() => setCat(c.id)}>{c.icon} {loc(c.name, lang)}</button>)}
        </div>
        <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search')} aria-label={t('search')} />
        <div className="waiter-menu">
          {list.map((m) => {
            const qty = lines[m.id] ?? 0;
            const promo = mealPromo(toPriceable(m, catsById), events, now);
            const name = loc(m.name, lang);
            return (
              <div className="wm-row" key={m.id}>
                <div className="wm-thumb" aria-hidden="true">{catsById.get(m.categoryId)?.icon ?? '🍽️'}</div>
                <div className="wm-info">
                  <b>{name}</b>
                  <span>
                    {!m.available ? t('soldOut') : promo?.discountedPrice != null
                      ? <><b className="price-new">{formatMoney(promo.discountedPrice, lang)}</b> <s className="price-old">{formatMoney(m.price, lang)}</s></>
                      : formatMoney(m.price, lang)}
                    {promo && m.available && <em className="mini-promo">{eventLabel(promo.event, t, lang)}</em>}
                  </span>
                </div>
                <div className="stepper">
                  <button aria-label={`${t('decrease')} — ${name}`} disabled={!qty} onClick={() => bump(m.id, -1)}>−</button>
                  <b>{qty}</b>
                  <button aria-label={`${t('increase')} — ${name}`} disabled={!m.available || qty >= 20} onClick={() => bump(m.id, 1)}>+</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="builder-slip">
        <h4>{t('orderSlip')} · {t('tableName', { n: table })}</h4>
        {appendable.length > 0 && (
          <label className="field">
            <span>{t('sendTo')}</span>
            <select value={effTarget} onChange={(e) => setTarget(e.target.value)}>
              <option value="new">{t('newOrder')}</option>
              {appendable.map((o) => <option key={o.id} value={o.id}>{t('addToOrder', { number: o.number })} ({t(o.status)})</option>)}
            </select>
          </label>
        )}
        <ul className="slip-list">
          {priced.rows.length === 0 && <li className="empty">{t('emptySlip')}</li>}
          {priced.rows.map((r, i) => (
            <li key={r.m.id}>
              <span>{r.qty} × {loc(r.m.name, lang)}{priced.p.lines[i].discount > 0 && <small className="co-save"> −{formatMoney(priced.p.lines[i].discount, lang)}</small>}</span>
              <span>{formatMoney(priced.p.lines[i].lineTotal, lang)}</span>
            </li>
          ))}
        </ul>
        <label className="field">
          <span>{t('noteOptional')}</span>
          <input type="text" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('notePlaceholder')} />
        </label>
        {priced.p.discount > 0 && <div className="slip-sub"><span>{t('discount')}</span><b className="co-save">−{formatMoney(priced.p.discount, lang)}</b></div>}
        <div className="slip-total"><span className="muted">{t('total')}</span><b>{formatMoney(priced.p.total, lang)}</b></div>
        <button className="btn btn-primary btn-block" disabled={busy || entries.length === 0} onClick={() => void send()}>
          {busy ? t('sending') : effTarget !== 'new' ? t('addToKitchen') : t('sendKitchen')}
        </button>
      </div>
      {result && <ResultModal order={result} onClose={() => setResult(null)} />}
    </div>
  );
}
