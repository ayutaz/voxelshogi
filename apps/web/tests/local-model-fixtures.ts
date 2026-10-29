import { createHash } from 'node:crypto';
import { modelFixture } from './inference-fixtures';

export const digest = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
export const ref = (path: string, text: string) => ({ path, bytes: new TextEncoder().encode(text).length, sha256: digest(text) });
export function trainedFixture() {
  return { ...modelFixture(), id: 'voxelshogi-transformer-s-m6-314159-v1', trained: true,
    sourceCommit: 'c'.repeat(40), sourceDirty: false, checkpoint: { path: 'model.safetensors', bytes: 3, sha256: digest('abc') },
    training: { binding: { source_commit: 'c'.repeat(40) }, receipt: { verified: true, progress: { epoch: 1, next_batch: 0, best_val_loss: 0.5 } },
      evaluated_weights_sha256: digest('abc'), evaluation_report_sha256: 'd'.repeat(64), test_report_sha256: 'e'.repeat(64),
      evaluation_game_count: 60, teacher_splits: { train: 30000, val: 3000, test: 3894 } },
  };
}
export function releaseFixture(text = JSON.stringify(trainedFixture())) {
  return { approved: true, id: 'voxelshogi-transformer-s-m6-314159-v1', license: 'Apache-2.0', sourceCommit: 'c'.repeat(40),
    repo: 'voxelshogi/voxelshogi-transformer-s', revision: 'f'.repeat(40), manifest: ref('manifest.json', text),
    notices: [ref('README.md', 'Fixture card'), ref('LICENSE', 'Fixture license')] };
}
