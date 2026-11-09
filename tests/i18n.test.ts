import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { DICTS } from '../web/src/lib/i18n.ts';

const walk = (d: string): string[] =>
  fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));

// keys that are built dynamically in the components
const DYNAMIC = [
  'accept', 'markReady', 'markServed', 'backToNew', 'backToPreparing', 'new', 'preparing', 'ready', 'served', 'cancelled',
  'free', 'busy', 'needsBill', 'client', 'waiter', 'admin', 'tabOverview', 'tabEvents', 'tabMenu', 'tabStaff',
  'orders12', 'revenue12', 'activeTickets', 'occupied',
  ...['plate', 'board', 'bowl', 'glass', 'mug', 'cup', 'none'].map((x) => 'container_' + x),
  ...['disc', 'slab', 'mound', 'scatter', 'rings', 'drizzle', 'sphere', 'roll', 'tall', 'liquid', 'foam', 'ice', 'leaf'].map((x) => 'shape_' + x),
];

describe('i18n', () => {
  const used = new Set<string>(DYNAMIC);
  for (const f of walk('web/src').filter((x) => /\.tsx?$/.test(x) && !x.endsWith('i18n.ts'))) {
    const s = fs.readFileSync(f, 'utf8');
    for (const m of s.matchAll(/\bt\(\s*'([^']+)'/g)) if (!m[1].endsWith('_')) used.add(m[1]); // 'prefix_' + x is covered by DYNAMIC
  }
  it('every used key exists in English and Uzbek', () => {
    expect([...used].filter((k) => !(k in DICTS.en))).toEqual([]);
    expect([...used].filter((k) => !(k in DICTS.uz))).toEqual([]);
  });
  it('English and Uzbek have identical key sets', () => {
    const en = Object.keys(DICTS.en).sort(), uz = Object.keys(DICTS.uz).sort();
    expect(en.filter((k) => !uz.includes(k))).toEqual([]);
    expect(uz.filter((k) => !en.includes(k))).toEqual([]);
  });
  it('placeholders match between languages', () => {
    const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(',');
    const bad = Object.keys(DICTS.en).filter((k) => ph(DICTS.en[k]) !== ph(DICTS.uz[k] ?? ''));
    expect(bad).toEqual([]);
  });
});
