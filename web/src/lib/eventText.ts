import type { EventDef } from '../../../shared/types.ts';
import { formatMoney, type Lang } from './menu.ts';
import type { TFn } from './i18n.ts';

export function eventLabel(ev: EventDef, t: TFn, lang: Lang): string {
  if (ev.type === 'percent') return `-${ev.params.percent}%`;
  if (ev.type === 'fixed_off') return `-${formatMoney(ev.params.amount ?? 0, lang)}`;
  return t('buyGet', { b: ev.params.buy ?? 1, g: ev.params.get ?? 1 });
}

export function weekdayNames(lang: Lang): string[] {
  const f = new Intl.DateTimeFormat(lang === 'uz' ? 'uz-UZ' : 'en-US', { weekday: 'short' });
  return Array.from({ length: 7 }, (_, d) => f.format(new Date(2024, 0, 7 + d))); // 2024-01-07 is a Sunday
}

export function scheduleText(ev: EventDef, t: TFn, lang: Lang): string {
  const s = ev.schedule;
  const parts: string[] = [];
  if (s.from || s.to) parts.push(`${s.from ?? '…'} → ${s.to ?? '…'}`);
  if (s.weekdays && s.weekdays.length) {
    const names = weekdayNames(lang);
    parts.push([...s.weekdays].sort((a, b) => a - b).map((d) => names[d]).join(', '));
  }
  if (s.start && s.end) parts.push(`${s.start}–${s.end}`);
  return parts.length ? parts.join(' · ') : t('always');
}
