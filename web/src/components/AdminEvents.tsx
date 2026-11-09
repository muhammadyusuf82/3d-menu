import { useRef, useState } from 'react';
import type { EventDef, EventType } from '../../../shared/types.ts';
import { isEventActive } from '../../../shared/pricing.ts';
import { api, fileToDataUrl } from '../lib/api.ts';
import { loc } from '../lib/menu.ts';
import { eventLabel, scheduleText, weekdayNames } from '../lib/eventText.ts';
import { useApp } from '../store.tsx';
import { Dialog } from './common.tsx';

export function EventsManager() {
  const { snap, t, lang, now, toast, errorText, refresh, catsById } = useApp();
  const [editing, setEditing] = useState<Partial<EventDef> | null>(null);
  const events = snap?.events ?? [];

  const toggle = async (ev: EventDef) => {
    try { await api.saveEvent({ ...ev, active: !ev.active }); await refresh(); } catch (e) { toast(errorText(e), 'error'); }
  };
  const remove = async (ev: EventDef) => {
    if (!window.confirm(t('confirmDeleteEvent', { name: loc(ev.title, lang) }))) return;
    try { await api.deleteEvent(ev.id); toast(t('deleted'), 'ok'); await refresh(); } catch (e) { toast(errorText(e), 'error'); }
  };
  const targets = (ev: EventDef) => {
    const names = [
      ...ev.categoryIds.map((id) => catsById.get(id)).filter(Boolean).map((c) => loc(c!.name, lang)),
      ...ev.mealIds.map((id) => snap?.meals.find((m) => m.id === id)).filter(Boolean).map((m) => loc(m!.name, lang)),
    ];
    return names.length ? names.join(', ') : t('allMeals');
  };

  return (
    <section className="block">
      <div className="block-head">
        <h3>{t('tabEvents')}</h3>
        <button className="btn btn-primary" onClick={() => setEditing({})}>＋ {t('newEvent')}</button>
      </div>
      <p className="muted small">{t('eventsHelp')}</p>
      {events.length === 0 && <div className="empty">{t('noEvents')}</div>}
      <div className="event-list">
        {events.map((ev) => {
          const live = isEventActive(ev, now);
          return (
            <div className="event-row" key={ev.id}>
              {ev.banner && <img className="event-thumb" src={ev.banner} alt="" />}
              <div className="event-info">
                <b>{loc(ev.title, lang)}</b> <span className="event-badge sm">{eventLabel(ev, t, lang)}</span>
                <span className={'status ' + (live ? 'ready' : ev.active ? 'preparing' : 'served')}>{live ? t('liveNow') : ev.active ? t('scheduled') : t('off')}</span>
                <div className="muted small">{targets(ev)}</div>
                <div className="muted small">🕒 {scheduleText(ev, t, lang)}</div>
              </div>
              <div className="order-actions">
                <button className="toggle" role="switch" aria-checked={ev.active} aria-label={t('active')} onClick={() => void toggle(ev)} />
                <button className="btn" onClick={() => setEditing(ev)}>{t('edit')}</button>
                <button className="btn btn-ghost-danger" onClick={() => void remove(ev)}>{t('delete')}</button>
              </div>
            </div>
          );
        })}
      </div>
      {editing && <EventForm initial={editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

interface FormState {
  titleEn: string; titleUz: string; type: EventType; percent: string; amount: string; buy: string; get: string;
  categoryIds: string[]; mealIds: string[]; weekdays: number[]; from: string; to: string; start: string; end: string;
  banner: string | null; active: boolean;
}

function fromEvent(e: Partial<EventDef>): FormState {
  return {
    titleEn: e.title?.[0] ?? '', titleUz: e.title?.[1] ?? '', type: e.type ?? 'percent',
    percent: String(e.params?.percent ?? 10), amount: String(e.params?.amount ?? 10000), buy: String(e.params?.buy ?? 2), get: String(e.params?.get ?? 1),
    categoryIds: e.categoryIds ?? [], mealIds: e.mealIds ?? [], weekdays: e.schedule?.weekdays ?? [],
    from: e.schedule?.from ?? '', to: e.schedule?.to ?? '', start: e.schedule?.start ?? '', end: e.schedule?.end ?? '',
    banner: e.banner ?? null, active: e.active ?? true,
  };
}

function EventForm({ initial, onClose }: { initial: Partial<EventDef>; onClose: () => void }) {
  const { snap, t, lang, toast, errorText, refresh } = useApp();
  const [f, setF] = useState<FormState>(() => fromEvent(initial));
  const [busy, setBusy] = useState(false);
  const [mealQ, setMealQ] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));
  const toggleIn = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const cats = [...(snap?.categories ?? [])].sort((a, b) => a.sort - b.sort);
  const meals = (snap?.meals ?? []).filter((m) => !mealQ.trim() || (m.name[0] + m.name[1]).toLowerCase().includes(mealQ.trim().toLowerCase()));
  const days = weekdayNames(lang);

  const preset = (p: 'happy' | 'friday' | 'b2g1') => {
    if (p === 'happy') setF((s) => ({ ...s, titleEn: 'Happy Hour', titleUz: 'Happy Hour', type: 'percent', percent: '20', categoryIds: ['drinks'], mealIds: [], weekdays: [], start: '15:00', end: '17:00' }));
    if (p === 'friday') setF((s) => ({ ...s, titleEn: 'Happy Friday', titleUz: 'Happy Friday', type: 'percent', percent: '15', weekdays: [5], start: '', end: '' }));
    if (p === 'b2g1') setF((s) => ({ ...s, titleEn: 'Buy 2 Get 1 Free', titleUz: '2 ta oling — 1 tasi bepul', type: 'buy_x_get_y', buy: '2', get: '1' }));
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { toast(t('imageTypeError'), 'error'); return; }
    if (file.size > 3 * 1024 * 1024) { toast(t('imageSizeError'), 'error'); return; }
    try {
      const { path } = await api.upload(await fileToDataUrl(file));
      set('banner', path);
    } catch (e) { toast(errorText(e), 'error'); }
  };

  const save = async () => {
    const params = f.type === 'percent' ? { percent: Number(f.percent) } : f.type === 'fixed_off' ? { amount: Number(f.amount) } : { buy: Number(f.buy), get: Number(f.get) };
    setBusy(true);
    try {
      await api.saveEvent({
        id: initial.id, title: [f.titleEn.trim(), f.titleUz.trim()], type: f.type, params,
        categoryIds: f.categoryIds, mealIds: f.mealIds, banner: f.banner, active: f.active,
        schedule: { ...(f.from ? { from: f.from } : {}), ...(f.to ? { to: f.to } : {}), ...(f.weekdays.length ? { weekdays: f.weekdays } : {}), ...(f.start ? { start: f.start } : {}), ...(f.end ? { end: f.end } : {}) },
      });
      toast(t('saved'), 'ok');
      await refresh();
      onClose();
    } catch (e) { toast(errorText(e), 'error'); }
    finally { setBusy(false); }
  };

  return (
    <Dialog onClose={onClose} className="form-dialog" label={t('newEvent')}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <h2>{initial.id ? t('editEvent') : t('newEvent')}</h2>
        {!initial.id && (
          <div className="presets">
            <span className="muted small">{t('presets')}:</span>
            <button type="button" className="chip chip-sm" onClick={() => preset('happy')}>Happy Hour</button>
            <button type="button" className="chip chip-sm" onClick={() => preset('friday')}>Happy Friday</button>
            <button type="button" className="chip chip-sm" onClick={() => preset('b2g1')}>Buy 2 Get 1</button>
          </div>
        )}
        <div className="grid2">
          <label className="field"><span>{t('titleEn')}</span><input required maxLength={80} value={f.titleEn} onChange={(e) => set('titleEn', e.target.value)} /></label>
          <label className="field"><span>{t('titleUz')}</span><input maxLength={80} value={f.titleUz} onChange={(e) => set('titleUz', e.target.value)} /></label>
        </div>
        <div className="grid2">
          <label className="field"><span>{t('eventType')}</span>
            <select value={f.type} onChange={(e) => set('type', e.target.value as EventType)}>
              <option value="percent">{t('typePercent')}</option>
              <option value="fixed_off">{t('typeFixed')}</option>
              <option value="buy_x_get_y">{t('typeBogo')}</option>
            </select>
          </label>
          {f.type === 'percent' && <label className="field"><span>{t('percentOff')}</span><input type="number" min={1} max={100} value={f.percent} onChange={(e) => set('percent', e.target.value)} /></label>}
          {f.type === 'fixed_off' && <label className="field"><span>{t('amountOff')}</span><input type="number" min={1} step={500} value={f.amount} onChange={(e) => set('amount', e.target.value)} /></label>}
          {f.type === 'buy_x_get_y' && (
            <div className="grid2">
              <label className="field"><span>{t('buyQty')}</span><input type="number" min={1} max={20} value={f.buy} onChange={(e) => set('buy', e.target.value)} /></label>
              <label className="field"><span>{t('freeQty')}</span><input type="number" min={1} max={20} value={f.get} onChange={(e) => set('get', e.target.value)} /></label>
            </div>
          )}
        </div>

        <fieldset className="fs">
          <legend>{t('appliesTo')}</legend>
          <p className="muted small">{t('appliesHelp')}</p>
          <div className="chips">
            {cats.map((c) => (
              <button type="button" key={c.id} className="chip chip-sm" aria-pressed={f.categoryIds.includes(c.id)} onClick={() => set('categoryIds', toggleIn(f.categoryIds, c.id))}>
                {c.parentId ? '↳ ' : ''}{c.icon} {loc(c.name, lang)}
              </button>
            ))}
          </div>
          <input className="search" type="search" placeholder={t('searchMeals')} value={mealQ} onChange={(e) => setMealQ(e.target.value)} />
          <div className="pick-list">
            {meals.map((m) => (
              <label key={m.id} className="check-inline">
                <input type="checkbox" checked={f.mealIds.includes(m.id)} onChange={() => set('mealIds', toggleIn(f.mealIds, m.id))} /> {loc(m.name, lang)}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="fs">
          <legend>{t('schedule')}</legend>
          <p className="muted small">{t('scheduleHelp')}</p>
          <div className="chips">
            {days.map((d, i) => (
              <button type="button" key={i} className="chip chip-sm" aria-pressed={f.weekdays.includes(i)} onClick={() => set('weekdays', toggleIn(f.weekdays, i))}>{d}</button>
            ))}
          </div>
          <div className="grid4">
            <label className="field"><span>{t('startTime')}</span><input type="time" value={f.start} onChange={(e) => set('start', e.target.value)} /></label>
            <label className="field"><span>{t('endTime')}</span><input type="time" value={f.end} onChange={(e) => set('end', e.target.value)} /></label>
            <label className="field"><span>{t('fromDate')}</span><input type="date" value={f.from} onChange={(e) => set('from', e.target.value)} /></label>
            <label className="field"><span>{t('toDate')}</span><input type="date" value={f.to} onChange={(e) => set('to', e.target.value)} /></label>
          </div>
        </fieldset>

        <div className="field">
          <span>{t('banner')}</span>
          <div className="upload-row">
            {f.banner && <img className="event-thumb" src={f.banner} alt="" />}
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ''; }} />
            {f.banner && <button type="button" className="btn btn-sm" onClick={() => set('banner', null)}>{t('removeImage')}</button>}
          </div>
        </div>
        <label className="check-inline"><input type="checkbox" checked={f.active} onChange={(e) => set('active', e.target.checked)} /> {t('active')}</label>

        <div className="receipt-actions">
          <button type="button" className="btn" onClick={() => (document.querySelector('dialog.form-dialog') as HTMLDialogElement | null)?.close()}>{t('cancel')}</button>
          <button className="btn btn-primary" disabled={busy || !f.titleEn.trim()}>{busy ? t('sending') : t('save')}</button>
        </div>
      </form>
    </Dialog>
  );
}
