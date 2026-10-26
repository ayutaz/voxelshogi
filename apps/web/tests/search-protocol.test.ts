import { describe, expect, it } from 'vitest';
import { parseAiResult, parseRequest, validateConfig, type SearchRequest } from '../src/ai/search-protocol';

const request: SearchRequest = { schema: 1, kind: 'search', requestId: 1, revision: 0, ruleset: 'voxelshogi-standard-v1',
  cursor: 0, hash: '043b66e12f6b84fd', side: 'b', difficulty: 'normal', seed: 0, recordJson: '{}', limits: { maxDepth: 64 } };
const result = { schema: 1, bestMove: '577567', score: 0, completedDepth: 1, nodes: '8', lastIterationNodes: '8', ttHits: '0', stopReason: 'depth' };

describe('search protocol boundaries', () => {
  it('accepts safe boundaries and fractional finite time; rejects bad option types and unknown fields', () => {
    expect(() => validateConfig({ maxDepth: 64, maxNodes: Number.MAX_SAFE_INTEGER, maxTimeMs: 0.125, maxGamePly: 0xffff_ffff,
      options: { iterativeDeepening: false, moveOrdering: true, transpositionTable: false, tableCapacity: 1_000_000 } })).not.toThrow();
    expect(() => validateConfig({ maxDepth: 0, maxNodes: null, maxTimeMs: null, maxGamePly: null })).not.toThrow();
    for (const config of [null, [], {}, { maxDepth: 65 }, { maxDepth: 1.5 }, { maxDepth: -1 },
      ...[NaN, Infinity, -1, 2 ** 53].map((maxTimeMs) => ({ maxDepth: 1, maxTimeMs })),
      ...[-1, 0.5, 2 ** 53].map((maxNodes) => ({ maxDepth: 1, maxNodes })),
      ...[null, [], { tableCapacity: 1_000_001 }, { tableCapacity: 0.5 }, { moveOrdering: 1 }, { transpositionTable: null }, { typo: 1 }].map((options) => ({ maxDepth: 1, options })),
      { maxDepth: 1, typo: true }, { maxDepth: 1, maxGamePly: 2 ** 32 },
    ]) expect(() => validateConfig(config)).toThrow();
  });

  it('limits record bytes rather than just UTF-16 characters and validates identity types', () => {
    expect(parseRequest(request)).toEqual(request);
    for (const changed of [{ recordJson: 'あ'.repeat(1_500_000) }, { recordJson: 3 }, { cursor: 20_001 },
      { cursor: -1 }, { requestId: 2 ** 53 }, { revision: -1 }, { hash: '123' }, { side: 'x' },
      { seed: 2 ** 32 }, { seed: 0.1 }, { extra: true }]) expect(() => parseRequest({ ...request, ...changed })).toThrow();
  });

  it('keeps full u64 counters as decimal strings and validates result consistency', () => {
    const wide = { ...result, nodes: '18446744073709551615', lastIterationNodes: '18446744073709551615' };
    expect(parseAiResult(wide, request)).toEqual(wide);
    for (const changed of [{ schema: 2 }, { bestMove: 'bad' }, { bestMove: null }, { score: 1.5 },
      { score: 1_000_001 }, { completedDepth: 65 }, { completedDepth: 1, score: null },
      { nodes: 8 }, { nodes: '08' }, { nodes: '-1' }, { nodes: '18446744073709551616' },
      { lastIterationNodes: '9' }, { ttHits: '9' }, { stopReason: 'random' }, { stopReason: 'unknown' },
      { stopReason: 'terminal', bestMove: '577567' },
    ]) expect(() => parseAiResult({ ...result, ...changed }, request)).toThrow();
    expect(() => parseAiResult(result, { ...request, limits: { maxDepth: 2, maxNodes: 7 } })).toThrow();
    expect(parseAiResult({ ...result, bestMove: 'P*565' }, request).bestMove).toBe('P*565');
  });
});
