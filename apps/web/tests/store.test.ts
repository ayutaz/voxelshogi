import { beforeAll, describe, expect, it, vi } from 'vitest';
import { loadWasm } from './loadWasm';
import { GameStore } from '../src/game/store';

beforeAll(() => loadWasm());

describe('GameStore', () => {
  it('exposes a snapshot of the initial position', () => {
    const s = new GameStore();
    const snap = s.snapshot();
    expect(snap.side).toBe('b');
    expect(snap.ply).toBe(0);
    expect(snap.legal.length).toBe(424);
    expect(snap.board.length).toBe(729);
    expect(snap.result).toBeNull();
    expect(snap.inCheck).toEqual({ b: false, w: false });
    expect(snap.lastMove).toBeNull();
    expect(snap.kingSquare).toEqual({ b: 4 * 81 + 8 * 9 + 4, w: 4 * 81 + 0 * 9 + 4 });
  });

  it('caches the snapshot until something changes and notifies subscribers', () => {
    const s = new GameStore();
    const listener = vi.fn();
    const unsubscribe = s.subscribe(listener);
    const a = s.snapshot();
    expect(s.snapshot()).toBe(a);
    expect(s.play('577567')).toEqual({ ok: true });
    expect(listener).toHaveBeenCalledTimes(1);
    const b = s.snapshot();
    expect(b).not.toBe(a);
    expect(b.side).toBe('w');
    expect(b.lastMove).toBe('577567');
    unsubscribe();
    s.undo();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(s.snapshot().ply).toBe(0);
  });

  it('reports illegal moves as errors without notifying', () => {
    const s = new GameStore();
    const listener = vi.fn();
    s.subscribe(listener);
    const r = s.play('555554');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.length).toBeGreaterThan(0);
    expect(listener).not.toHaveBeenCalled();
  });

  it('parses results, exports and imports records, and starts new games', () => {
    const s = new GameStore();
    s.play('577567');
    const json = s.exportRecord();
    s.resign();
    expect(s.snapshot().result).toEqual({ kind: 'win', winner: 'b', reason: 'Resignation' });
    expect(s.snapshot().legal).toEqual([]);
    expect(s.importRecord(json)).toEqual({ ok: true });
    expect(s.snapshot().moves).toEqual(['577567']);
    expect(s.importRecord('{"broken"').ok).toBe(false);
    expect(s.snapshot().moves).toEqual(['577567']); // failed import keeps the game
    s.newGame();
    expect(s.snapshot().moves).toEqual([]);
  });

  it('rejects oversized imports before parsing', () => {
    const s = new GameStore();
    const r = s.importRecord('x'.repeat(5 * 1024 * 1024));
    expect(r.ok).toBe(false);
  });

  it('marks abandoned and move-limit records as finished, preserving their metadata', () => {
    const s = new GameStore();
    s.play('577567');
    for (const termination of ['Abandoned', 'MaxPlies']) {
      const record = { ...JSON.parse(s.exportRecord()), termination,
        result: termination === 'MaxPlies' ? { Draw: { reason: 'MaxPlies' } } : null };
      expect(s.importRecord(JSON.stringify(record))).toEqual({ ok: true });
      expect(s.snapshot().finished).toBe(true);
      expect(s.snapshot().legal).toEqual([]);
      expect(s.snapshot().result).toEqual(termination === 'MaxPlies' ? { kind: 'draw', reason: 'MaxPlies' } : null);
      expect(JSON.parse(s.exportRecord())).toEqual(record);
      s.undo();
      expect(s.snapshot().finished).toBe(false);
      expect(s.snapshot().legal.length).toBe(424);
      s.redo();
    }
  });

  it('invalidates AI roots even when undo, import or new game return to the same board', () => {
    const s = new GameStore();
    const root = s.searchState();
    expect(root).toMatchObject({ revision: 0, hash: '043b66e12f6b84fd', cursor: 0, side: 'b', ruleset: 'voxelshogi-standard-v1' });
    expect(JSON.parse(root.recordJson).moves).toEqual([]);
    for (const reset of [() => { s.play('577567'); s.undo(); }, () => s.importRecord(root.recordJson), () => s.newGame(), () => s.goto(0)]) {
      reset();
      expect(s.snapshot().hash).toBe(root.hash);
      expect(s.snapshot().revision).toBeGreaterThan(root.revision);
      expect(s.applyAiMove(root, '577567').ok).toBe(false);
      expect(s.snapshot().ply).toBe(0);
    }
    const current = s.searchState();
    expect(s.applyAiMove({ ...current, side: 'w' }, '577567').ok).toBe(false);
    expect(s.applyAiMove({ ...current, hash: '0000000000000000' }, '577567').ok).toBe(false);
    expect(s.applyAiMove({ ...current, ruleset: 'other' }, '577567').ok).toBe(false);
    expect(s.applyAiMove({ ...current, cursor: 1 }, '577567').ok).toBe(false);
    expect(s.applyAiMove(current, '555554').ok).toBe(false);
    expect(s.snapshot().revision).toBe(current.revision);
    expect(s.applyAiMove(current, '577567')).toEqual({ ok: true });
    expect(s.applyAiMove(current, '577567').ok).toBe(false);
    expect(s.snapshot().ply).toBe(1);
    expect(s.snapshot().revision).toBe(current.revision + 1);
  });
});
