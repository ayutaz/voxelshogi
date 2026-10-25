import { describe, expect, it } from 'vitest';
import { createRng, pickRandomMove } from '../src/ai/random';

describe('random AI', () => {
  it('is deterministic for a seed and differs across seeds', () => {
    const a = createRng(123);
    const b = createRng(123);
    const c = createRng(124);
    const sa = Array.from({ length: 5 }, () => a());
    expect(sa).toEqual(Array.from({ length: 5 }, () => b()));
    expect(sa).not.toEqual(Array.from({ length: 5 }, () => c()));
    expect(sa.every((v) => v >= 0 && v < 1)).toBe(true);
  });

  it('only ever returns one of the legal moves, covering all of them', () => {
    const legal = ['577567', '477467', 'P*555'];
    const rng = createRng(1);
    const seen = new Set<string>();
    for (let i = 0; i < 300; i++) {
      const m = pickRandomMove(legal, rng);
      expect(legal).toContain(m);
      seen.add(m!);
    }
    expect(seen.size).toBe(3);
  });

  it('returns null when there is no legal move', () => {
    expect(pickRandomMove([], createRng(0))).toBeNull();
  });
});
