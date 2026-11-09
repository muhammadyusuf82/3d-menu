import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Store } from '../server/db.ts';
import { cleanMeal } from '../server/validate.ts';
import { SEED_V2_MEAL_IDS } from '../shared/seed.ts';

describe('seed migration', () => {
  it('adds the new desserts to a database created before them, exactly once', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sizzle-mig-'));
    const file = path.join(dir, 'm.db');
    let s = new Store(file);
    const total = s.meals().length;
    // simulate a database from the first release
    for (const id of SEED_V2_MEAL_IDS) s.deleteMeal(id);
    s.db.prepare("DELETE FROM meta WHERE key = 'seedVersion'").run();
    expect(s.meals().length).toBe(total - SEED_V2_MEAL_IDS.length);
    s.close();

    s = new Store(file);
    expect(s.meals().length).toBe(total);
    for (const id of SEED_V2_MEAL_IDS) expect(s.meal(id)).not.toBeNull();
    // once migrated, a meal the admin deletes stays deleted
    s.deleteMeal('croissant');
    s.close();
    s = new Store(file);
    expect(s.meal('croissant')).toBeNull();
    s.close();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it('keeps the platter layout ("spread") through validation', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sizzle-mig-'));
    const s = new Store(path.join(dir, 'v.db'));
    const platter = s.meal('fruit-platter')!;
    expect(platter.model.arrange).toBe('spread');
    expect(cleanMeal(platter, s, platter.id).model.arrange).toBe('spread');
    expect(cleanMeal({ ...platter, model: { kind: 'generic', container: 'board' } }, s, platter.id).model.arrange).toBeUndefined();
    s.close();
    fs.rmSync(dir, { recursive: true, force: true });
  });
});
