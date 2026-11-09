import { useMemo, useState } from 'react';
import type { Order } from '../../../shared/types.ts';
import { priceCart } from '../../../shared/pricing.ts';
import { api } from '../lib/api.ts';
import { formatMoney, loc, toPriceable } from '../lib/menu.ts';
import { useApp } from '../store.tsx';
import { Dialog } from './common.tsx';

export function TablePicker({ value, onChange }: { value: number | null; onChange: (n: number) => void }) {
  const { snap, t } = useApp();
  return (
    <div className="table-grid" role="group" aria-label={t('tableNumber')}>
      {(snap?.tables ?? []).map((tb) => {
        const label = t(tb.state === 'free' ? 'free' : tb.state === 'needs_bill' ? 'needsBill' : 'busy');
        return (
          <button key={tb.number} type="button" className={`table-btn ${tb.state}`} aria-pressed={value === tb.number}
            aria-label={`${t('tableName', { n: tb.number })} · ${label}`} onClick={() => onChange(tb.number)}>
            {tb.number}<small>{label}</small>
          </button>
        );
      })}
    </div>
  );
}

export function Checkout({ onClose, onPlaced }: { onClose: () => void; onPlaced: (o: Order) => void }) {
  const { snap, t, lang, now, catsById, cart, setCartQty, clearCart, toast, errorText, refresh } = useApp();
  const [table, setTable] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const lines = useMemo(() => {
    const rows = cart.flatMap((c) => { const m = snap?.meals.find((x) => x.id === c.mealId); return m ? [{ m, qty: c.qty }] : []; });
    const priced = priceCart(rows.map((r) => ({ meal: toPriceable(r.m, catsById), qty: r.qty })), snap?.events ?? [], now);
    return { rows, priced };
  }, [cart, snap, catsById, now]);

  const confirm = async () => {
    if (!table) { toast(t('pickTable'), 'error'); return; }
    if (lines.rows.some((r) => !r.m.available)) { toast(t('cartUnavailable'), 'error'); return; }
    setBusy(true);
    try {
      const { order } = await api.createOrder({ table, items: cart.map((c) => ({ mealId: c.mealId, qty: c.qty })), note: note.trim() || undefined });
      clearCart();
      onPlaced(order);
    } catch (e) {
      toast(errorText(e), 'error');
      void refresh();
    } finally { setBusy(false); }
  };

  return (
    <Dialog onClose={onClose} className="receipt" label={t('confirmTitle')}>
      <h2>{t('confirmTitle')}</h2>
      <p>{t('checkoutDesc')}</p>
      <ul className="slip-list co-lines">
        {lines.rows.map((r, i) => {
          const pl = lines.priced.lines[i];
          return (
            <li key={r.m.id}>
              <span className="co-name">
                {loc(r.m.name, lang)}
                {pl.discount > 0 && <small className="co-save"> −{formatMoney(pl.discount, lang)}</small>}
                {!r.m.available && <small className="co-warn"> · {t('soldOut')}</small>}
              </span>
              <span className="stepper">
                <button aria-label={t('decrease')} onClick={() => setCartQty(r.m.id, r.qty - 1)}>−</button>
                <b>{r.qty}</b>
                <button aria-label={t('increase')} disabled={r.qty >= 20} onClick={() => setCartQty(r.m.id, r.qty + 1)}>+</button>
              </span>
              <span className="co-price">{formatMoney(pl.lineTotal, lang)}</span>
            </li>
          );
        })}
      </ul>
      <div className="facts">
        <div className="fact"><span>{t('items')}</span><b>{cart.reduce((s, c) => s + c.qty, 0)}</b></div>
        <div className="fact"><span>{t('total')}</span><b>{formatMoney(lines.priced.total, lang)}</b></div>
      </div>
      {lines.priced.discount > 0 && <p className="co-saved">🎉 {t('youSave', { amount: formatMoney(lines.priced.discount, lang) })}</p>}
      <span className="checkout-table-label">{t('tableNumber')}</span>
      <TablePicker value={table} onChange={setTable} />
      <label className="field">
        <span>{t('noteOptional')}</span>
        <input type="text" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('notePlaceholder')} />
      </label>
      <div className="receipt-actions">
        <button className="btn" onClick={() => (document.querySelector('dialog.receipt') as HTMLDialogElement | null)?.close()}>{t('cancel')}</button>
        <button className="btn btn-primary" disabled={busy} onClick={() => void confirm()}>{busy ? t('sending') : t('confirmOrder')}</button>
      </div>
    </Dialog>
  );
}

export function ResultModal({ order, onClose }: { order: Order; onClose: () => void }) {
  const { t, lang } = useApp();
  const rows: [string, string][] = [
    [t('table'), t('tableName', { n: order.table })],
    [t('items'), String(order.items.reduce((s, i) => s + i.qty, 0))],
    ...(order.discount > 0 ? [[t('discount'), '−' + formatMoney(order.discount, lang)] as [string, string]] : []),
    [t('total'), formatMoney(order.total, lang)],
    [t('takenBy'), order.staffName ?? t('client')],
    [t('meals'), order.items.map((i) => `${loc(i.name, lang)} ×${i.qty}`).join(', ')],
  ];
  return (
    <Dialog onClose={onClose} className="receipt" label={t('confirmed')}>
      <div className="check" aria-hidden="true">✓</div>
      <h2>{t('confirmed')}</h2>
      <p>{t('showNumber')}</p>
      <div className="order-number">{order.number}</div>
      <div className="meta">{rows.map(([a, b]) => <div key={a}><span>{a}</span><b>{b}</b></div>)}</div>
      <button className="btn btn-primary btn-block" onClick={() => (document.querySelector('dialog.receipt') as HTMLDialogElement | null)?.close()}>{t('thanks')}</button>
    </Dialog>
  );
}
