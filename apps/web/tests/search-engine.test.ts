import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { loadWasm } from './loadWasm';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import { SearchEngine } from '../src/ai/search-engine';
import type { SearchRequest } from '../src/ai/search-protocol';

const fixtures = JSON.parse(readFileSync(new URL('../../../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8')) as { name: string; record: unknown; config: SearchRequest['limits']; expected: Record<string, unknown> }[];
beforeAll(loadWasm);
function request(f = fixtures[0]!): SearchRequest {
  const g = Game.fromRecordJson(JSON.stringify(f.record));
  try {
    return { schema: 1, kind: 'search', requestId: 1, revision: 3, ruleset: 'voxelshogi-standard-v1',
      hash: g.hash(), side: g.sideToMove() as 'b' | 'w', recordJson: g.recordJson(), cursor: g.ply(),
      difficulty: 'normal', seed: 42, limits: f.config };
  } finally { g.free(); }
}

describe('Worker search engine using real WASM', () => {
  for (const f of fixtures) it(f.name, async () => {
    const engine = new SearchEngine(async () => {});
    const r = await engine.run(request(f));
    expect(r.kind).toBe('result');
    if (r.kind === 'result') expect(r.result).toMatchObject(f.expected);
  });

  it('initializes once, restores the cursor rather than the redo future, and records timing', async () => {
    const init = vi.fn(async () => {});
    let ms = 0;
    const engine = new SearchEngine(init, () => ++ms);
    const r = request();
    const g = Game.fromRecordJson(r.recordJson);
    try { g.play('999888'); r.recordJson = g.recordJson(); } finally { g.free(); }
    for (let i = 0; i < 2; ++i) {
      const reply = await engine.run(r);
      expect(reply.kind).toBe('result');
      if (reply.kind === 'result') {
        expect(reply.result).toMatchObject({ nodes: '29', bestMove: '999888' });
        expect(reply.metrics.totalMs).toBeGreaterThan(0);
        expect(reply.metrics.replayMs).toBeGreaterThan(0);
      }
    }
    expect(init).toHaveBeenCalledTimes(1);
  });

  it('Easy is seeded, legal, and never resumes abandoned games', async () => {
    const engine = new SearchEngine(async () => {});
    const r = { ...request(), difficulty: 'easy' as const };
    const first = await engine.run(r), second = await engine.run(r);
    expect(first.kind).toBe('result');
    if (first.kind === 'result' && second.kind === 'result') {
      expect(first.result).toEqual(second.result);
      expect(first.result.stopReason).toBe('random');
      const g = Game.fromRecordJson(r.recordJson);
      try { expect(g.legalMoves()).toContain(first.result.bestMove); } finally { g.free(); }
    }
    const stopped = { ...JSON.parse(r.recordJson), termination: 'Abandoned' };
    const reply = await engine.run({ ...r, recordJson: JSON.stringify(stopped) });
    expect(reply.kind).toBe('result');
    if (reply.kind === 'result') expect(reply.result).toMatchObject({ bestMove: null, score: null, stopReason: 'terminal' });
    expect(await engine.run({ ...r, limits: { maxDepth: 0, maxGamePly: 41 } })).toMatchObject({ kind: 'result', result: { bestMove: null, score: 0, stopReason: 'terminal' } });
  });

  it('rejects malformed requests and mismatched roots before accepting any move', async () => {
    const engine = new SearchEngine(async () => {});
    for (const bad of [null, {}, { ...request(), schema: 2 }, { ...request(), requestId: 0 },
      { ...request(), revision: 1.5 }, { ...request(), cursor: 1 },
      { ...request(), hash: '0000000000000000' }, { ...request(), side: 'w' },
      { ...request(), ruleset: 'other' }, { ...request(), seed: -1 },
      { ...request(), recordJson: 'x'.repeat(4 * 1024 * 1024 + 1) },
      { ...request(), limits: { maxDepth: 65 } }, { ...request(), difficulty: 'unknown' },
    ]) {
      const reply = await engine.run(bad);
      expect(reply.kind).toBe('error');
      if (reply.kind === 'error') expect(reply.code).toBe('input');
    }
  });

  it('reports initialization failures and rejects duplicate requests while initialization is pending', async () => {
    const broken = new SearchEngine(async () => { throw new Error('missing wasm'); });
    expect(await broken.run(request())).toMatchObject({ kind: 'error', code: 'initialization', message: 'missing wasm' });
    let ready!: () => void;
    const slow = new SearchEngine(() => new Promise<void>((resolve) => { ready = resolve; }));
    const first = slow.run(request());
    expect(await slow.run(request())).toMatchObject({ kind: 'error', code: 'busy' });
    ready();
    expect((await first).kind).toBe('result');
  });

  it('frees the owned WASM game on root validation and execution failure', async () => {
    const r = request();
    const free = vi.spyOn(Game.prototype, 'free');
    const engine = new SearchEngine(async () => {});
    try {
      expect(await engine.run({ ...r, hash: '0000000000000000' })).toMatchObject({ kind: 'error', code: 'input' });
      expect(free).toHaveBeenCalledTimes(1);
      free.mockClear();
      const search = vi.spyOn(Game.prototype, 'bestMove').mockImplementation(() => { throw new Error('search trap'); });
      try {
        expect(await engine.run(r)).toMatchObject({ kind: 'error', code: 'execution', message: 'search trap' });
        expect(free).toHaveBeenCalledTimes(1);
      } finally { search.mockRestore(); }
    } finally { free.mockRestore(); }
  });
});
