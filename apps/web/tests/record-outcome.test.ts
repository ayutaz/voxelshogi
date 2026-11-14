import { expect, it } from 'vitest';
import { recordOutcome } from '../src/game/record-outcome';
it('reads the terminal result from the full record, independently of the displayed cursor', () => {
  expect(recordOutcome(JSON.stringify({ result: { Win: { winner: 'White', reason: 'Resignation' } }, termination: 'Resignation' }))).toEqual({ kind: 'win', winner: 'w', reason: 'Resignation' });
  expect(recordOutcome(JSON.stringify({ result: { Draw: { reason: 'MaxPlies' } }, termination: 'MaxPlies' }))).toEqual({ kind: 'draw', reason: 'MaxPlies' });
  expect(recordOutcome(JSON.stringify({ result: null, termination: null }))).toBeNull();
});
