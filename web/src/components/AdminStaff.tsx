import { useEffect, useState } from 'react';
import type { Role, StaffRow } from '../../../shared/types.ts';
import { api } from '../lib/api.ts';
import { useApp } from '../store.tsx';

export function StaffManager() {
  const { snap, t, toast, errorText, refresh, session } = useApp();
  const [staff, setStaff] = useState<StaffRow[]>([]);
  const [name, setName] = useState('');
  const [role, setRole] = useState<Role>('waiter');
  const [pin, setPin] = useState('');
  const [tables, setTables] = useState(String(snap?.tables.length ?? 12));

  const load = () => api.staff().then((r) => setStaff(r.staff)).catch((e) => toast(errorText(e), 'error'));
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (snap) setTables(String(snap.tables.length)); }, [snap?.tables.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<{ staff: StaffRow[] }>, ok: string) => {
    try { const r = await fn(); setStaff(r.staff); toast(ok, 'ok'); return true; } catch (e) { toast(errorText(e), 'error'); return false; }
  };

  return (
    <>
      <section className="block">
        <h3>{t('staff')}</h3>
        <div className="staff-list">
          {staff.map((s) => <StaffLine key={s.id} s={s} self={s.id === session?.staff.id} act={act} />)}
        </div>
        <form className="staff-add" onSubmit={async (e) => {
          e.preventDefault();
          if (await act(() => api.addStaff({ name: name.trim(), role, pin }), t('saved'))) { setName(''); setPin(''); }
        }}>
          <h4>{t('addStaff')}</h4>
          <div className="grid4">
            <label className="field"><span>{t('name')}</span><input required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field"><span>{t('role')}</span>
              <select value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="waiter">{t('waiter')}</option><option value="admin">{t('admin')}</option></select>
            </label>
            <label className="field"><span>{t('pin')}</span><input required inputMode="numeric" pattern="[0-9]{4}" maxLength={4} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} /></label>
            <button className="btn btn-primary self-end" disabled={!name.trim() || pin.length !== 4}>{t('add')}</button>
          </div>
        </form>
      </section>

      <section className="block">
        <h3>{t('restaurantSettings')}</h3>
        <form className="staff-add" onSubmit={async (e) => {
          e.preventDefault();
          try { await api.setTableCount(Number(tables)); toast(t('saved'), 'ok'); await refresh(); } catch (err) { toast(errorText(err), 'error'); }
        }}>
          <div className="grid4">
            <label className="field"><span>{t('tableCount')}</span><input type="number" min={1} max={60} value={tables} onChange={(e) => setTables(e.target.value)} /></label>
            <button className="btn btn-primary self-end">{t('save')}</button>
          </div>
        </form>
      </section>
    </>
  );
}

function StaffLine({ s, self, act }: { s: StaffRow; self: boolean; act: (fn: () => Promise<{ staff: StaffRow[] }>, ok: string) => Promise<boolean> }) {
  const { t } = useApp();
  const [name, setName] = useState(s.name);
  const [role, setRole] = useState<Role>(s.role);
  const [pin, setPin] = useState('');
  const dirty = name.trim() !== s.name || role !== s.role || pin.length > 0;
  return (
    <div className="staff-row">
      <div className="avatar" aria-hidden="true">{s.name.slice(0, 2).toUpperCase()}</div>
      <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} aria-label={t('name')} />
      <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label={t('role')}>
        <option value="waiter">{t('waiter')}</option><option value="admin">{t('admin')}</option>
      </select>
      <input className="num" inputMode="numeric" maxLength={4} placeholder={t('newPin')} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} aria-label={t('newPin')} />
      {s.defaultPin && <span className="status new">{t('defaultPin')}</span>}
      <button className="btn btn-sm btn-primary" disabled={!dirty || (pin.length > 0 && pin.length !== 4)}
        onClick={async () => { if (await act(() => api.updateStaff(s.id, { name: name.trim(), role, ...(pin ? { pin } : {}) }), t('saved'))) setPin(''); }}>{t('save')}</button>
      <button className="btn btn-sm btn-ghost-danger" disabled={self}
        onClick={() => { if (window.confirm(t('confirmDeleteStaff', { name: s.name }))) void act(() => api.deleteStaff(s.id), t('deleted')); }}>{t('delete')}</button>
    </div>
  );
}
