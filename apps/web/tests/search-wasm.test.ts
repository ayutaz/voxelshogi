import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it } from 'vitest';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { loadWasm } from './loadWasm';

interface Fixture {
  name: string;
  record: Record<string, unknown>;
  config: Record<string, unknown>;
  expected: Record<string, unknown>;
  mateWinner?: string;
}
const fixtures = JSON.parse(readFileSync(new URL('../../../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8')) as Fixture[];
beforeAll(loadWasm);

describe('real WASM search (shared native, hand-counted fixtures)', () => {
  for (const f of fixtures) {
    it(f.name, () => {
      const g = Game.fromRecordJson(JSON.stringify(f.record));
      try {
        const before = { record: g.recordJson(), hash: g.hash(), ply: g.ply() };
        const r = JSON.parse(g.bestMove(JSON.stringify(f.config))) as Record<string, unknown>;
        expect(r).toMatchObject(f.expected);
        expect({ record: g.recordJson(), hash: g.hash(), ply: g.ply() }).toEqual(before);
        if (r.bestMove !== null) {
          expect(g.legalMoves()).toContain(r.bestMove);
          g.play(r.bestMove as string);
        }
        if (f.mateWinner) expect(JSON.parse(g.result()!)).toEqual({ Win: { winner: f.mateWinner, reason: 'Checkmate' } });
      } finally { g.free(); }
    });
  }

  it('keeps a redo future and uses absolute ply for the game cap', () => {
    const g = Game.fromRecordJson(JSON.stringify(fixtures[0]!.record));
    try {
      g.play('999888');
      g.undo();
      const before = g.recordJson();
      expect(JSON.parse(g.bestMove('{"maxDepth":1}'))).toMatchObject({ nodes: '8', score: 0 });
      expect(g.recordJson()).toBe(before);
      expect(g.ply()).toBe(0);
      expect(g.moveCount()).toBe(1);
      expect(JSON.parse(g.bestMove('{"maxDepth":1,"maxGamePly":41}'))).toMatchObject({ bestMove: null, stopReason: 'terminal' });
      expect(JSON.parse(g.bestMove('{"maxDepth":0,"maxGamePly":42}')).bestMove).toBe('999888');
    } finally { g.free(); }
  });

  it('distinguishes no completed iteration, depth zero and browser deadlines', () => {
    const g = Game.fromRecordJson(JSON.stringify(fixtures[0]!.record));
    try {
      expect(JSON.parse(g.bestMove('{"maxDepth":4,"maxNodes":0}'))).toMatchObject({ nodes: '0', score: null, completedDepth: 0, stopReason: 'nodes' });
      expect(JSON.parse(g.bestMove('{"maxDepth":0}'))).toMatchObject({ nodes: '1', score: 0, completedDepth: 0, stopReason: 'depth' });
      expect(JSON.parse(g.bestMove('{"maxDepth":4,"maxTimeMs":0}'))).toMatchObject({ nodes: '0', score: null, stopReason: 'time' });
      // This invokes the actual JS performance clock, with no timing threshold assertion.
      const r = JSON.parse(g.bestMove('{"maxDepth":64,"maxTimeMs":5}')) as { stopReason: string; bestMove: string };
      expect(r.stopReason).toBe('time');
      expect(g.legalMoves()).toContain(r.bestMove);
    } finally { g.free(); }
  });

  it('preserves externally stopped records and refuses invalid search configurations', () => {
    for (const [termination, result, score] of [
      ['MaxPlies', { Draw: { reason: 'MaxPlies' } }, 0], ['Abandoned', null, null],
    ] as const) {
      const record = { ...fixtures[0]!.record, termination, result };
      const g = Game.fromRecordJson(JSON.stringify(record));
      try {
        expect(g.isFinished()).toBe(true);
        expect(JSON.parse(g.recordJson())).toEqual(record);
        expect(JSON.parse(g.bestMove('{"maxDepth":1}'))).toMatchObject({ bestMove: null, score, stopReason: 'terminal' });
        for (const bad of [{}, { maxDepth: 65 }, { maxDepth: 1, maxNodes: 2 ** 53 }, { maxDepth: 1, maxTimeMs: -1 }, { maxDepth: 1, options: { tableCapacity: 1_000_001 } }, { maxDepth: 1, typo: true }]) {
          expect(() => g.bestMove(JSON.stringify(bad))).toThrow();
        }
        expect(() => g.play('999888')).toThrow();
      } finally { g.free(); }
    }
  });

  it('imports the exact validated resignation reason on a mating final position', () => {
    for (const [side, move, winner] of [['b', '232222', 'Black'], ['w', '878888', 'White']] as const) {
      const f = fixtures.find((fixture) => fixture.name === `mate-in-one-${side}`)!;
      const g = Game.fromRecordJson(JSON.stringify(f.record));
      let record: Record<string, unknown>;
      try {
        g.play(move);
        expect(JSON.parse(g.result()!)).toEqual({ Win: { winner, reason: 'Checkmate' } });
        record = { ...JSON.parse(g.recordJson()), termination: 'Resignation', result: { Win: { winner, reason: 'Resignation' } } };
      } finally { g.free(); }
      const imported = Game.fromRecordJson(JSON.stringify(record));
      try {
        expect(JSON.parse(imported.result()!)).toEqual(record.result);
        expect(JSON.parse(imported.recordJson())).toEqual(record);
        expect(JSON.parse(imported.bestMove('{"maxDepth":0}'))).toMatchObject({ bestMove: null, score: -1_000_000, stopReason: 'terminal' });
      } finally { imported.free(); }
    }
  });
});
