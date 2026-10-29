import { expect, it } from 'vitest';
import { addModel, removeModel, chooseModel, modelSeat, type ModelLibrary, type LoadedModel } from '../src/ai/model-library';
import { releaseFixture, trainedFixture } from './local-model-fixtures';
import { parseTrainedCatalog } from '../src/inference/local-model';
import { parseTrainedModel } from '../src/inference/manifest';

function packet(sourceId = 'local-1'): LoadedModel {
  const release = parseTrainedCatalog({ schema: 1, releases: [releaseFixture()] })[0]!;
  const model = parseTrainedModel(trainedFixture(), release);
  model.variants = (['fp32', 'fp16', 'int8'] as const).map(precision => ({ ...model.variants[0]!, id: precision, precision }));
  return { sourceId, release, model, files: [] };
}
const empty = (): ModelLibrary => ({ entries: [], choices: {} });
it('keeps the two seats and exact format/backend independent', () => {
  const state = addModel(empty(), packet());
  const both = chooseModel(chooseModel(state, 'b', { sourceId: 'local-1', precision: 'int8', backend: 'wasm' }), 'w', { sourceId: 'local-1', precision: 'fp16', backend: 'webgpu' });
  expect(modelSeat(both, 'b')!.selection).toEqual({ modelId: 'voxelshogi-transformer-s-m6-314159-v1', packageHash: packet().release.manifest.sha256, precision: 'int8', backend: 'wasm' });
  expect(modelSeat(both, 'w')!.selection.precision).toBe('fp16');
  expect(modelSeat(both, 'w')!.selection.backend).toBe('webgpu');
  expect(modelSeat(both, 'b')!.revision).toBe('f'.repeat(40));
  expect(modelSeat(empty(), 'b')).toBeUndefined();
});
it('replaces a reselected release with a fresh source and preserves both choices', () => {
  let state = addModel(empty(), packet());
  state = chooseModel(state, 'b', { sourceId: 'local-1', precision: 'int8', backend: 'wasm' });
  state = addModel(state, packet('local-2'));
  expect(state.entries.map(entry => entry.sourceId)).toEqual(['local-2']);
  expect(modelSeat(state, 'b')).toMatchObject({ sourceId: 'local-2', selection: { precision: 'int8' } });
  expect(() => addModel(state, packet('local-2'))).toThrow(/source/i);
});
it('clears removed choices without choosing a different model', () => {
  const state = chooseModel(addModel(empty(), packet()), 'w', { sourceId: 'local-1', precision: 'fp32', backend: 'wasm' });
  const removed = removeModel(state, 'local-1');
  expect(removed).toEqual(empty());
  expect(state.entries).toHaveLength(1);
  expect(() => chooseModel(removed, 'w', { sourceId: 'local-1', precision: 'fp32', backend: 'wasm' })).toThrow(/model/i);
  const only = packet(); only.model.variants = only.model.variants.slice(0, 1);
  expect(() => chooseModel(addModel(empty(), only), 'b', { sourceId: 'local-1', precision: 'int8', backend: 'wasm' })).toThrow(/precision/i);
});
it('bounds retained file handles to four releases', () => {
  let state = empty();
  for (let i = 0; i < 4; i++) { const next = packet(`local-${i}`); next.release.id += i; state = addModel(state, next); }
  const extra = packet('local-5'); extra.release.id += 'extra';
  expect(() => addModel(state, extra)).toThrow(/4/);
});

it('derives the independently expected FP16 storage mode from the selected package', () => {
  const entry = packet(); entry.model.variants[1]!.conversion = { method: 'fp16-weight-only', compute: 'float32', activations: 'float32', convertedTensors: 1, convertedElements: 6 };
  const state = chooseModel(addModel(empty(), entry), 'b', { sourceId: 'local-1', precision: 'fp16', backend: 'webgpu' });
  expect(modelSeat(state, 'b')!.fp16WeightOnly).toBe(true);
  const other = chooseModel(state, 'b', { sourceId: 'local-1', precision: 'fp32', backend: 'wasm' });
  expect(modelSeat(other, 'b')!.fp16WeightOnly).toBeUndefined();
});
