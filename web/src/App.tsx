import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AppProvider, useApp } from './store.tsx';
import { ClientView } from './components/ClientView.tsx';
import { WaiterView } from './components/Waiter.tsx';
import { AdminView } from './components/Admin.tsx';
import { miniManager } from './three/viewer.ts';

type RoleTab = 'client' | 'waiter' | 'admin';
const ROLES: [RoleTab, string, string][] = [['client', '👤', 'client'], ['waiter', '🧑‍🍳', 'waiter'], ['admin', '🔑', 'admin']];

function Shell() {
  const { t, lang, setLang, online, loadError, toasts, snap } = useApp();
  const [role, setRole] = useState<RoleTab>('client');
  const [visited, setVisited] = useState<Set<RoleTab>>(new Set(['client']));
  const tabsRef = useRef<HTMLDivElement>(null);

  const select = (r: RoleTab) => {
    setRole(r);
    setVisited((v) => (v.has(r) ? v : new Set(v).add(r)));
    window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };
  useEffect(() => { miniManager.paused = role !== 'client'; }, [role]);

  const onKey = (e: KeyboardEvent) => {
    const i = ROLES.findIndex(([r]) => r === role);
    let n = i;
    if (e.key === 'ArrowRight') n = (i + 1) % 3; else if (e.key === 'ArrowLeft') n = (i + 2) % 3; else if (e.key === 'Home') n = 0; else if (e.key === 'End') n = 2; else return;
    e.preventDefault();
    select(ROLES[n][0]);
    (tabsRef.current?.querySelectorAll('button')[n] as HTMLElement | undefined)?.focus();
  };

  return (
    <>
      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <div className="logo" aria-hidden="true">🍽️</div>
            <div><div className="brand-name">Sizzle</div><div className="brand-sub">{t('platform')}</div></div>
          </div>
          <div className="header-tools">
            <div className="switcher" role="tablist" aria-label={t('selectRole')} ref={tabsRef} onKeyDown={onKey}>
              {ROLES.map(([r, icon, key]) => (
                <button key={r} className="role-btn" role="tab" aria-selected={role === r} tabIndex={role === r ? 0 : -1} onClick={() => select(r)}>
                  <span aria-hidden="true">{icon}</span> {t(key)}
                </button>
              ))}
            </div>
            <div className="lang-switch" role="group" aria-label="Language / Til">
              <button className="lang-btn" aria-pressed={lang === 'en'} lang="en" aria-label="English" onClick={() => setLang('en')}>EN</button>
              <button className="lang-btn" aria-pressed={lang === 'uz'} lang="uz" aria-label="O‘zbek tili" onClick={() => setLang('uz')}>UZ</button>
            </div>
          </div>
        </div>
        {!online && <div className="offline-banner" role="alert">{snap ? t('offlineBanner') : loadError ? t('serverDown') : t('connecting')}</div>}
      </header>
      <main>
        <div hidden={role !== 'client'}>{visited.has('client') && <ClientView />}</div>
        <div hidden={role !== 'waiter'}>{visited.has('waiter') && <WaiterView />}</div>
        <div hidden={role !== 'admin'}>{visited.has('admin') && <AdminView />}</div>
      </main>
      <div className="toast-wrap" role="status" aria-live="polite">
        {toasts.map((x) => <div key={x.id} className={'toast ' + x.kind}>{x.text}</div>)}
      </div>
    </>
  );
}

export default function App() {
  return <AppProvider><Shell /></AppProvider>;
}
