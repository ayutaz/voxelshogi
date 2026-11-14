import { expect, it } from 'vitest';
import { cueFor } from '../src/audio/cues';
import type { PresentationEvent } from '../src/game/presentation';

const move: PresentationEvent = { id: '1:1', kind: 'move', mover: 'b', capture: false, promotion: false, check: false, result: null };
it('uses one cue per accepted move with explicit semantic priority', () => {
  expect(cueFor(move, null)).toBe('move');
  expect(cueFor({ ...move, capture: true }, null)).toBe('capture');
  expect(cueFor({ ...move, capture: true }, 'w')).toBe('capture-against');
  expect(cueFor({ ...move, capture: true }, 'b')).toBe('capture');
  expect(cueFor({ ...move, promotion: true }, null)).toBe('promotion');
  expect(cueFor({ ...move, promotion: true, capture: true }, null)).toBe('capture');
  expect(cueFor({ ...move, promotion: true, capture: true, check: true }, null)).toBe('check');
  const result = { kind: 'win', winner: 'b', reason: 'Checkmate' } as const;
  expect(cueFor({ ...move, check: true, result }, null)).toBe('end');
  expect(cueFor({ ...move, check: true, result }, 'b')).toBe('win');
  expect(cueFor({ ...move, check: true, result }, 'w')).toBe('defeat');
  expect(cueFor({ ...move, result: { kind: 'draw', reason: 'Repetition' } }, 'b')).toBe('end');
});
it('history forward plays only a move/capture; replacements are silent', () => {
  expect(cueFor({ ...move, kind: 'forward', check: true, promotion: true, result: { kind: 'draw', reason: 'Repetition' } }, null)).toBe('move');
  expect(cueFor({ ...move, kind: 'forward', capture: true, check: true }, 'w')).toBe('capture');
  expect(cueFor({ id: '1:2', kind: 'clear' }, null)).toBeNull();
});
