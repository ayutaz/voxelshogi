import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, cpSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const mutations = [
  { name: 'required-real-model-ci', file: 'scripts/ci/gate.mjs', before: ", 'models'", after: '', test: 'gate' },
  { name: 'resident-set-unit', file: 'scripts/browser-memory.mjs', before: 'rssBytes: kib * 1024', after: 'rssBytes: kib * 1000', test: 'browser-memory' },
  { name: 'model-publication-license', file: 'scripts/prepare-inference.mjs', before: "assert.equal(manifest.license, 'Apache-2.0', 'model license must be approved before publication');", after: '', test: 'inference-package' },
  { name: 'model-clean-source', file: 'scripts/prepare-inference.mjs', before: "assert.equal(manifest.sourceDirty, false, 'publication requires clean source');", after: '', test: 'inference-package' },
  { name: 'model-distribution-hash', file: 'scripts/prepare-inference.mjs', before: "assert.equal(sha(bytes), file.sha256, 'model file hash mismatch');", after: '', test: 'inference-package' },
];
const work = mkdtempSync(join(tmpdir(), 'voxelshogi-control-mutations-'));
try {
  for (const mutation of mutations) {
    const copy = join(work, mutation.name), source = join(copy, mutation.file), test = `scripts/ci/${mutation.test}.test.mjs`;
    mkdirSync(dirname(source), { recursive: true }); mkdirSync(dirname(join(copy, test)), { recursive: true });
    const original = readFileSync(join(root, mutation.file), 'utf8');
    assert.equal(original.split(mutation.before).length - 1, 1, `stale mutation ${mutation.name}`);
    cpSync(join(root, test), join(copy, test)); writeFileSync(source, original);
    const run = () => spawnSync(process.execPath, ['--test', '--test-reporter=tap', test], { cwd: copy, encoding: 'utf8', timeout: 30_000 });
    const baseline = run(); assert.equal(baseline.status, 0, `control baseline failed: ${mutation.name}`);
    assert.match(baseline.stdout, /# tests [1-9][0-9]*/);
    writeFileSync(source, original.replace(mutation.before, mutation.after));
    const result = run();
    assert.equal(result.status, 1, `mutation must fail: ${mutation.name}`);
    assert.match(result.stdout, /ERR_ASSERTION/, 'module/import/timeouts do not count as detected regressions');
    assert.match(result.stdout, /# fail [1-9][0-9]*/);
    console.log(`${mutation.name}: caught by executed assertion`);
  }
} finally { rmSync(work, { recursive: true, force: true }); }
