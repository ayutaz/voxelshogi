import { expect, it } from 'vitest';
import { ARENA_LINKS, MODEL_LINKS, screenForQuery } from '../src/navigation';
it('keeps normal watching and the model lab as the public screens', () => {
  expect(screenForQuery('')).toBe('arena');
  expect(screenForQuery('?models=1')).toBe('models');
  expect(screenForQuery('?models=0')).toBe('models');
});
it('opens normal watching for legacy comparison-room URLs', () => {
  for (const query of ['?experiment=1', '?experiment=0', '?experiment']) expect(screenForQuery(query)).toBe('arena');
});
it('keeps the model lab when an old comparison parameter is also present', () => {
  expect(screenForQuery('?experiment=1&models=1')).toBe('models');
});
it('links watching to the model lab without offering the retired comparison room', () => {
  expect(ARENA_LINKS).toEqual([{ href: '/?models=1', label: 'モデル推論ラボ' }]);
});
it('links the model lab back to AI watching without a comparison-room entry', () => {
  expect(MODEL_LINKS).toEqual([{ href: '/', label: 'AI対局の観戦へ' }]);
});
