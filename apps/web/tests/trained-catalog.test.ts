import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { parseTrainedCatalog } from '../src/inference/local-model';

it('validates the shipped public catalog through the same approval and identity parser as the Worker', () => {
  const value = JSON.parse(readFileSync(new URL('../public/models/m6/catalog.json', import.meta.url), 'utf8'));
  expect(() => parseTrainedCatalog(value)).not.toThrow();
});
