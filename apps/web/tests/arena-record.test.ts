import { expect, it } from 'vitest';
import { ArenaJournal, arenaConditions } from '../src/ai/arena-record';
import { DEFAULT_AI_OPTIONS } from '../src/ai/arena-controller';
import type { ModelCompleted } from '../src/ai/arena-model';
import { policyResult } from './policy-worker-fixtures';
const record = (moves: string[] = [], initial = 'position') => JSON.stringify({ ruleset_id: 'voxelshogi-standard-v1', initial, moves, result: null, termination: null });
const root = (moves: string[] = []) => ({ recordJson: record(moves), revision: moves.length + 1, cursor: moves.length, side: moves.length % 2 ? 'w' as const : 'b' as const, hash: '1'.repeat(16), ruleset: 'voxelshogi-standard-v1' });
it('exports selected seats without their File handles and keeps human seats explicit', () => {
  const model = { ...reply().model, files: [], fixtures: ['initial-b'] };
  const selected = arenaConditions({ ...DEFAULT_AI_OPTIONS, mode: 'h-r', wDifficulty: 'model', wModel: model });
  expect(selected.b).toEqual({ controller: 'human' });
  expect(selected.w).toMatchObject({ controller: 'ai', difficulty: 'model', model: { selection: { precision: 'fp32' } } });
  expect(JSON.stringify(selected)).not.toMatch(/files|fixtures|maxNodes/);
});
function reply(): ModelCompleted {
  const fixture = policyResult();
  return { ...root(), kind: 'model-result', requestId: 1, model: { sourceId: 'local-1', repo: 'voxelshogi/model', revision: 'f'.repeat(40), sourceCommit: 'c'.repeat(40), license: 'Apache-2.0', selection: fixture.result.selection },
    validation: fixture.validation, result: { bestMove: '111211', value: .25, rawAction: 0, rawLegal: false }, inferenceMs: 3, roundTripMs: 4 };
}
it('records exact accepted AI conditions without files or fabricated search metrics', () => {
  const journal = new ArenaJournal(), completed = reply();
  journal.accept(root(), { seed: 43, limits: DEFAULT_AI_OPTIONS.limits }, completed);
  const saved = journal.snapshot(record(['111211']), 1);
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ root: { cursor: 0, hash: '1'.repeat(16) }, reply: { model: { revision: 'f'.repeat(40), selection: { precision: 'fp32' } }, result: { value: .25 } } });
  expect(JSON.stringify(saved)).not.toMatch(/recordJson|files|arrayBuffer|maxNodes|seed/);
  completed.model.revision = 'e'.repeat(40);
  expect(saved[0]!.reply.kind === 'model-result' && saved[0]!.reply.model.revision).toBe('f'.repeat(40));
  const again = journal.snapshot(record(['111211']), 1)[0]!.reply;
  expect(again.kind === 'model-result' && again.model.revision).toBe('f'.repeat(40));
});
it('discards observations from abandoned branches and leaves imported/human moves unattributed', () => {
  const journal = new ArenaJournal();
  journal.accept(root(), { seed: 43, limits: DEFAULT_AI_OPTIONS.limits }, reply());
  expect(journal.snapshot(record(['111211']), 0)).toEqual([]);
  expect(journal.snapshot(record(['111211']), 1)).toHaveLength(1);
  journal.reconcile(record(['111311']));
  expect(journal.snapshot(record(['111211']), 1)).toEqual([]);
  journal.accept(root(), { seed: 43, limits: DEFAULT_AI_OPTIONS.limits }, reply());
  journal.reconcile(record([], 'different initial'));
  expect(journal.snapshot(record(['111211']), 1)).toEqual([]);
  journal.accept(root(), { seed: 43, limits: DEFAULT_AI_OPTIONS.limits }, reply());
  journal.clear(); expect(journal.snapshot(record(['111211']), 1)).toEqual([]);
});
it('retains actual baseline seed, limits, completed depth and node counts', () => {
  const journal = new ArenaJournal();
  const result = { ...root(), schema: 1 as const, kind: 'result' as const, requestId: 1, difficulty: 'normal' as const,
    result: { schema: 1 as const, bestMove: '111211', score: 100, completedDepth: 2, nodes: '51', lastIterationNodes: '30', ttHits: '2', stopReason: 'nodes' as const },
    metrics: { initMs: 0, replayMs: 1, searchMs: 5, totalMs: 6 }, roundTripMs: 7 };
  journal.accept(root(), { seed: 123, limits: { maxDepth: 3, maxNodes: 51 } }, result);
  expect(journal.snapshot(record(['111211']), 1)[0]).toMatchObject({ search: { seed: 123, limits: { maxDepth: 3, maxNodes: 51 } }, reply: { result: { completedDepth: 2, nodes: '51' } } });
});
