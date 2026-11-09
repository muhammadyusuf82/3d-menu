import { useState } from 'react';
import { formatMoney } from '../lib/menu.ts';
import { useApp } from '../store.tsx';
import { PinGate } from './common.tsx';
import { OrdersList } from './Orders.tsx';
import { EventsManager } from './AdminEvents.tsx';
import { MenuManager } from './AdminMenu.tsx';
import { StaffManager } from './AdminStaff.tsx';

type Tab = 'overview' | 'events' | 'menu' | 'staff';

export function AdminView() {
  const { session } = useApp();
  const [, force] = useState(0);
  if (!session || session.staff.role !== 'admin') {
    return <section className="view wrap"><PinGate role="admin" onDone={() => force((x) => x + 1)} /></section>;
  }
  return <section className="view wrap"><Dashboard /></section>;
}

function Dashboard() {
  const { snap, session, t, lang, logout, toast, now } = useApp();
  const [tab, setTab] = useState<Tab>('overview');
  const orders = snap?.orders ?? [];
  const recent = orders.filter((o) => now.getTime() - o.createdAt < 12 * 3600 * 1000 && o.status !== 'cancelled');
  const stats: [string, string][] = [
    ['orders12', String(recent.length)],
    ['revenue12', formatMoney(recent.reduce((s, o) => s + o.total, 0), lang)],
    ['activeTickets', String(orders.filter((o) => o.status === 'new' || o.status === 'preparing' || o.status === 'ready').length)],
    ['occupied', `${(snap?.tables ?? []).filter((x) => x.state !== 'free').length} / ${snap?.tables.length ?? 0}`],
  ];
  const tabs: [Tab, string][] = [['overview', 'tabOverview'], ['events', 'tabEvents'], ['menu', 'tabMenu'], ['staff', 'tabStaff']];

  return (
    <div className="panel">
      <div className="panel-head">
        <div><h2>{t('dashboard')}</h2><p>{t('dashboardDesc')}</p></div>
        <button className="btn" onClick={() => { void logout(); toast(t('locked')); }}>🔒 {t('lockDashboard')}</button>
      </div>
      {session!.defaultPin && <div className="warn-banner">⚠️ {t('defaultPinWarn')}</div>}
      <div className="tabs tabs-wide" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" className="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{t(label)}</button>
        ))}
      </div>
      {tab === 'overview' && (
        <>
          <div className="stat-row">
            {stats.map(([k, v]) => <div className="stat" key={k}><span>{t(k)}</span><b>{v}</b></div>)}
          </div>
          <section className="block">
            <h3>{t('liveOrders')}</h3>
            <OrdersList orders={orders.slice(0, 40)} />
          </section>
        </>
      )}
      {tab === 'events' && <EventsManager />}
      {tab === 'menu' && <MenuManager />}
      {tab === 'staff' && <StaffManager />}
    </div>
  );
}
