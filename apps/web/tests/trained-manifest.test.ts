import { expect, it } from 'vitest';
import { parseModel, parseTrainedModel } from '../src/inference/manifest';
import { trainedFixture, releaseFixture } from './local-model-fixtures';

it('requires a separate identity for trained models and keeps M3 scoped to untrained', () => {
  const model = trainedFixture();
  expect(() => parseModel(model)).toThrow();
  const parsed = parseTrainedModel(model, releaseFixture());
  expect(parsed.trained).toBe(true);
  expect(parsed.variants[0]!.model.path).toBe('fp32.onnx');
});

for (const field of ['source', 'dirty', 'license', 'id', 'seed', 'trained', 'checkpoint', 'hash', 'cohort', 'teachers', 'split', 'selection', 'epoch', 'cursor', 'loss']) {
  it(`rejects trained provenance that differs from the reviewed release: ${field}`, () => {
    const model = trainedFixture();
    if (field === 'source') model.sourceCommit = 'a'.repeat(40);
    if (field === 'dirty') model.sourceDirty = true;
    if (field === 'license') model.license = 'unknown';
    if (field === 'id') model.id = 'another-model';
    if (field === 'seed') model.seed = 123;
    if (field === 'trained') model.trained = false;
    if (field === 'checkpoint') model.training.evaluated_weights_sha256 = 'b'.repeat(64);
    if (field === 'hash') model.training.test_report_sha256 = 'bad';
    if (field === 'cohort') model.training.evaluation_game_count = 59;
    if (field === 'teachers') model.training.teacher_splits.train--;
    if (field === 'split') { model.training.teacher_splits.val = 0; model.training.teacher_splits.train += 3000; }
    if (field === 'selection') model.training.receipt.verified = false;
    if (field === 'epoch') model.training.receipt.progress.epoch = 0;
    if (field === 'cursor') model.training.receipt.progress.next_batch = 1;
    if (field === 'loss') model.training.receipt.progress.best_val_loss = NaN;
    expect(() => parseTrainedModel(model, releaseFixture())).toThrow();
  });
}
