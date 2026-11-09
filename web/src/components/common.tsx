import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import type { Meal } from '../../../shared/types.ts';
import { miniManager } from '../three/viewer.ts';
import { useApp } from '../store.tsx';
import type { Role } from '../../../shared/types.ts';

export function Dialog({ onClose, className = '', label, children }: { onClose: () => void; className?: string; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const d = ref.current!;
    if (!d.open) d.showModal();
    document.body.classList.add('modal-open');
    const onCloseEvt = () => closeRef.current();
    d.addEventListener('close', onCloseEvt);
    return () => {
      d.removeEventListener('close', onCloseEvt);
      requestAnimationFrame(() => document.body.classList.toggle('modal-open', !!document.querySelector('dialog[open]')));
    };
  }, []);
  return (
    <dialog
      ref={ref} className={className} aria-label={label}
      onClick={(e) => {
        const d = ref.current!;
        if (e.target !== d) return;
        const r = d.getBoundingClientRect();
        if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close();
      }}
    >
      {children}
    </dialog>
  );
}

export function categoryIcon(meal: Meal, cats: Map<string, { icon: string; parentId: string | null }>): string {
  return cats.get(meal.categoryId)?.icon ?? '🍽️';
}

export function MealThumb({ meal, icon }: { meal: Meal; icon: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(false);
    return miniManager.register(ref.current!, meal, () => setReady(true));
  }, [meal]);
  return (
    <>
      {meal.photo && <img className="card-photo" src={meal.photo} alt="" loading="lazy" />}
      {!meal.photo && !ready && <span className="food-fallback" aria-hidden="true">{icon}</span>}
      <canvas ref={ref} className={'mini-canvas' + (meal.photo ? ' under-photo' : '')} aria-hidden="true" />
    </>
  );
}

export function PinGate({ role, onDone }: { role: Role; onDone: () => void }) {
  const { t, login, logout, errorText } = useApp();
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const timer = useRef<number>();

  const submit = async (value: string) => {
    if (busy) return;
    if (value.length !== 4) { setError(t('allDigits')); return; }
    setBusy(true);
    try {
      const s = await login(value);
      if (role === 'admin' && s.staff.role !== 'admin') {
        await logout();
        setError(t('adminOnly'));
        setPin('');
        return;
      }
      setError('');
      onDone();
    } catch (e) {
      setError(errorText(e));
      setPin('');
    } finally { setBusy(false); }
  };

  const change = (next: string) => {
    clearTimeout(timer.current);
    setError('');
    setPin(next);
    if (next.length === 4) timer.current = window.setTimeout(() => void submit(next), 150);
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'clear', '0', 'del'];
  return (
    <div className="gate">
      <form className="gate-card" onSubmit={(e: FormEvent) => { e.preventDefault(); void submit(pin); }}>
        <h2>{t(role === 'admin' ? 'managerAccess' : 'waiterAccess')}</h2>
        <p>{t(role === 'admin' ? 'enterAdminPin' : 'staffPin')}</p>
        <input
          className="pin-input" type="password" inputMode="numeric" maxLength={4} autoComplete="off" value={pin}
          aria-label={t('staffPin')} aria-describedby={`pin-err-${role}`} autoFocus
          onChange={(e) => change(e.target.value.replace(/\D/g, '').slice(0, 4))}
        />
        <div className="keypad">
          {keys.map((k) => (
            <button
              key={k} type="button" className="key" disabled={busy}
              aria-label={k === 'clear' ? t('clearPin') : k === 'del' ? t('deleteDigit') : undefined}
              onClick={() => change(k === 'clear' ? '' : k === 'del' ? pin.slice(0, -1) : pin.length < 4 ? pin + k : pin)}
            >
              {k === 'clear' ? 'C' : k === 'del' ? '⌫' : k}
            </button>
          ))}
        </div>
        <p className="gate-error" id={`pin-err-${role}`} role="status">{error}</p>
        <div className="gate-hint">{t('demoAccess')}</div>
      </form>
    </div>
  );
}
