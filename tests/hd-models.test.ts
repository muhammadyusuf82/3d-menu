import { readFileSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { SEED_MEALS } from '../shared/seed.ts';
import { PHOTO_MODELS } from '../web/src/three/photoreal.ts';

const PUBLIC = join(__dirname, '..', 'web', 'public');

interface GltfNode { name?: string; extras?: Record<string, unknown>; children?: number[] }

/** Reads the JSON chunk of a binary glTF (.glb). */
function glbJson(path: string) {
  const buf = readFileSync(path);
  expect(buf.toString('ascii', 0, 4)).toBe('glTF');
  const len = buf.readUInt32LE(12);
  expect(buf.toString('ascii', 16, 20)).toBe('JSON');
  return JSON.parse(buf.toString('utf8', 20, 20 + len)) as { scenes: { nodes: number[] }[]; nodes: GltfNode[] };
}

describe('HD models', () => {
  it('every seeded meal has an HD model', () => {
    const missing = SEED_MEALS.filter((m) => !(m.id in PHOTO_MODELS)).map((m) => m.id);
    expect(missing).toEqual([]);
  });

  for (const meal of SEED_MEALS) {
    const spec = PHOTO_MODELS[meal.id];
    if (spec?.kind !== 'layered') continue;
    it(`${meal.id}: GLB parts match the recipe`, () => {
      const file = join(PUBLIC, spec.url);
      expect(existsSync(file), file).toBe(true);
      expect(statSync(file).size).toBeLessThan(8 * 1024 * 1024); // keeps tablets on the LAN responsive
      const gltf = glbJson(file);
      const top = gltf.scenes[0].nodes.map((i) => gltf.nodes[i]);
      const parts = top.filter((n) => !n.extras?.static);
      const ids = new Set(meal.ingredients.map((i) => i.id));
      // every exploding node is a real ingredient of this meal (so highlight / focus from the recipe list works)
      expect(parts.map((n) => n.name).filter((n) => !ids.has(n!))).toEqual([]);
      // ...and every ingredient has its part
      expect([...ids].filter((id) => !parts.some((n) => n.name === id))).toEqual([]);
      // explicit explode order, no duplicates
      const stacks = parts.map((n) => n.extras?.stack);
      expect(stacks.every((s) => typeof s === 'number')).toBe(true);
      expect(new Set(stacks).size).toBe(stacks.length);
      // at most one static base
      expect(top.filter((n) => n.extras?.static).length).toBeLessThanOrEqual(1);
    });
  }
});
