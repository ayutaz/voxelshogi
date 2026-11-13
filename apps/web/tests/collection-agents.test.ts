import { expect, it } from 'vitest';
import { collectionAgents } from '../src/collection/agents';
import { isGameSubmission } from '../src/collection/contract';
import { DEFAULT_AI_OPTIONS } from '../src/ai/arena-controller';
import type { ModelSeat } from '../src/ai/arena-model';

it('records independent human, Easy and Normal seats without a local path', () => {
  expect(collectionAgents(DEFAULT_AI_OPTIONS)).toEqual({
    b: { kind: 'normal', seed: 42, maxDepth: 6, maxNodes: 50000, maxTimeMs: 1000 },
    w: { kind: 'normal', seed: 42, maxDepth: 6, maxNodes: 50000, maxTimeMs: 1000 },
  });
  expect(collectionAgents({ ...DEFAULT_AI_OPTIONS, mode: 'h-r', wDifficulty: 'easy' })).toEqual({ b: { kind: 'human' }, w: { kind: 'easy', seed: 42 } });
  expect(collectionAgents({ ...DEFAULT_AI_OPTIONS, mode: 'r-h', bDifficulty: 'easy' })).toEqual({ b: { kind: 'easy', seed: 42 }, w: { kind: 'human' } });
});

it('records the actual selected model identity and precision but excludes local handles/files', () => {
  const model: ModelSeat = { sourceId: 'local-1', repo: 'voxelshogi/model-s', revision: 'f'.repeat(40), sourceCommit: 'c'.repeat(40), license: 'Apache-2.0', files: [], fixtures: ['case'],
    selection: { modelId: 'model-s', packageHash: 'd'.repeat(64), precision: 'int8', backend: 'wasm' } };
  const selected = collectionAgents({ ...DEFAULT_AI_OPTIONS, bDifficulty: 'model', bModel: model });
  expect(selected.b).toEqual({ kind: 'model', modelId: model.selection.modelId, precision: 'int8', backend: 'wasm',
    packageHash: model.selection.packageHash, repo: model.repo, revision: model.revision, sourceCommit: model.sourceCommit, license: model.license });
  expect(JSON.stringify(selected)).not.toContain('local-1');
  expect(isGameSubmission({ schema: 1, requestId: '00000000-0000-4000-8000-000000000001', consent: 'game-research-v1', ending: 'aborted',
    applicationCommit: 'a'.repeat(40), mode: 'r-r', conditionsScope: 'selected-at-submission', selectedAgents: selected,
    record: { ruleset_id: 'voxelshogi-standard-v1', initial: '8k/9/K8 b - 1', moves: [], result: null, termination: 'Abandoned' } })).toBe(true);
});
