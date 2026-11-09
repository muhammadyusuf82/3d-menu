import { useState } from 'react';
import type { Order, OrderStatus } from '../../../shared/types.ts';
import { api } from '../lib/api.ts';
import { formatMoney, loc } from '../lib/menu.ts';
import { useApp } from '../store.tsx';
import { Dialog } from './common.tsx';

const NEXT: Partial<Record<OrderStatus, { to: OrderStatus; label: string }>> = {
  new: { to: 'preparing', label: 'accept' },
  preparing: { to: 'ready', label: 'markReady' },
  ready: { to: 'served', label: 'markServed' },
};
const BACK: Partial<Record<OrderStatus, { to: OrderStatus; label: string }>> = {
  preparing: { to: 'new', label: 'backToNew' },
  ready: { to: 'preparing', label: 'backToPreparing' },
};

function ReasonDialog({ onSubmit, onClose }: { onSubmit: (reason: string) => void; onClose: () => void }) {
  const { t } = useApp();
  const [reason, setReason] = useState('');
  return (
    <Dialog onClose={onClose} className="receipt small" label={t('cancelOrder')}>
      <h2>{t('cancelOrder')}</h2>
      <p>{t('cancelReasonHelp')}</p>
      <label className="field">
        <span>{t('cancelReason')}</span>
        <input type="text" autoFocus maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="receipt-actions">
        <button className="btn" onClick={() => (document.querySelector('dialog.small') as HTMLDialogElement | null)?.close()}>{t('back')}</button>
        <button className="btn btn-danger" disabled={!reason.trim()} onClick={() => onSubmit(reason.trim())}>{t('cancelOrder')}</button>
      </div>
    </Dialog>
  );
}

export function OrderCard({ order }: { order: Order }) {
  const { t, lang, toast, errorText, refresh } = useApp();
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);

  const change = async (status: OrderStatus, reason?: string) => {
    setBusy(true);
    try {
      await api.setStatus(order.id, status, reason);
      toast(t('orderUpdated', { number: order.number, status: t(status) }), 'ok');
      setAsking(false);
    } catch (e) { toast(errorText(e), 'error'); }
    finally { setBusy(false); void refresh(); }
  };

  const next = NEXT[order.status];
  const back = BACK[order.status];
  const open = order.status === 'new' || order.status === 'preparing' || order.status === 'ready';
  const time = new Date(order.createdAt).toLocaleTimeString(lang === 'uz' ? 'uz-UZ' : 'en-US', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className={`order-row st-${order.status}`}>
      <div className="order-no">{order.number}</div>
      <div className="order-meta">
        <b>{t('tableName', { n: order.table })}</b> · {order.items.reduce((s, i) => s + i.qty, 0)} · {formatMoney(order.total, lang)}
        {order.discount > 0 && <span className="co-save"> (−{formatMoney(order.discount, lang)})</span>}
        <br />{order.staffName ?? t('client')} · {time}
        <br />{order.items.map((i) => `${loc(i.name, lang)} ×${i.qty}`).join(', ')}
        {order.note && <><br /><i>📝 {order.note}</i></>}
        {order.cancelReason && <><br /><i className="co-warn">⛔ {order.cancelReason}</i></>}
      </div>
      <span className={`status ${order.status}`}>{t(order.status)}</span>
      <div className="order-actions">
        {next && <button className="btn btn-primary" disabled={busy} onClick={() => void change(next.to)}>{t(next.label)}</button>}
        {back && <button className="btn" disabled={busy} onClick={() => void change(back.to)}>↩ {t(back.label)}</button>}
        {open && <button className="btn btn-ghost-danger" disabled={busy} onClick={() => setAsking(true)}>{t('cancelOrder')}</button>}
      </div>
      {asking && <ReasonDialog onClose={() => setAsking(false)} onSubmit={(r) => void change('cancelled', r)} />}
    </div>
  );
}

export function OrdersList({ orders, empty }: { orders: Order[]; empty?: string }) {
  const { t } = useApp();
  if (orders.length === 0) return <div className="empty">{empty ?? t('noOrders')}</div>;
  return <div>{orders.map((o) => <OrderCard key={o.id} order={o} />)}</div>;
}
