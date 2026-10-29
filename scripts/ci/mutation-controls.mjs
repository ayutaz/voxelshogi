import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, cpSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const mutations = [
  { name: 'catalog-artifact-hash', file: 'scripts/inference-build.mjs', before: "createHash('sha256').update(catalogBytes).digest('hex')", after: "'0'.repeat(64)", test: 'model-distribution' },
  { name: 'catalog-metadata-only', file: 'scripts/inference-build.mjs', before: "assert.deepEqual(readdirSync(resolve(root, 'models/m6')).sort(), ['catalog.json'], 'M6 public assets may contain only catalog metadata');", after: '', test: 'model-distribution' },
  { name: 'catalog-served-bytes', file: 'scripts/verify-model-distribution.mjs', before: "const catalog = await read(new URL(path(application.catalog.path), origin + '/').href, application.catalog, true, null, true);", after: 'const catalog = { schema: 1, releases: [] };', test: 'model-distribution' },
  { name: 'required-real-model-ci', file: 'scripts/ci/gate.mjs', before: ", 'models'", after: '', test: 'gate' },
  { name: 'resident-set-unit', file: 'scripts/browser-memory.mjs', before: 'rssBytes: kib * 1024', after: 'rssBytes: kib * 1000', test: 'browser-memory' },
  { name: 'model-publication-license', file: 'scripts/prepare-inference.mjs', before: "assert.equal(manifest.license, 'Apache-2.0', 'model license must be approved before publication');", after: '', test: 'inference-package' },
  { name: 'model-clean-source', file: 'scripts/prepare-inference.mjs', before: "assert.equal(manifest.sourceDirty, false, 'publication requires clean source');", after: '', test: 'inference-package' },
  { name: 'model-distribution-hash', file: 'scripts/prepare-inference.mjs', before: "assert.equal(sha(bytes), file.sha256, 'model file hash mismatch');", after: '', test: 'inference-package' },
  { name: 'publication-approval', file: 'scripts/model-publication.mjs', before: "assert.equal(policy.publication, true, 'model publication approval is pending');", after: '', test: 'model-publication' },
  { name: 'publication-source-commit', file: 'scripts/prepare-inference.mjs', before: "assert.ok(typeof manifest.sourceCommit === 'string' && /^[0-9a-f]{40}$/.test(manifest.sourceCommit), 'publication requires a source commit');", after: '', test: 'inference-package' },
  { name: 'publication-untrained-scope', file: 'scripts/prepare-inference.mjs', before: "assert.equal(manifest.trained, false, 'M3 approval does not cover trained models');", after: '', test: 'inference-package' },
  { name: 'twenty-actual-model-switches', file: 'scripts/measure-browser-models.mjs', before: '[(i + 1) % 3]', after: '[i % 3]', test: 'model-switches' },
  { name: 'actual-gpu-model-switches', file: 'scripts/measure-browser-models.mjs', before: "['int8', 'fp32'][i % 2]", after: "['fp32', 'int8'][i % 2]", test: 'model-switches' },
  { name: 'application-worker-hash', file: 'scripts/inference-build.mjs', before: "createHash('sha256').update(bytes).digest('hex')", after: "'0'.repeat(64)", test: 'model-distribution' },
  { name: 'public-served-file-hash', file: 'scripts/verify-model-distribution.mjs', before: "assert.equal(sha256, file.sha256, `hash mismatch: ${url}`);", after: '', test: 'model-distribution' },
  { name: 'tested-application-artifact', file: 'scripts/verify-model-distribution.mjs', before: "if (expectedArtifact) assert.deepEqual(application, expectedArtifact.application, 'served files differ from tested application artifact');", after: '', test: 'model-distribution' },
  { name: 'tested-model-artifact', file: 'scripts/verify-model-distribution.mjs', before: "if (expectedArtifact) assert.deepEqual(index, expectedArtifact.deployment, 'served files differ from tested model artifact');", after: '', test: 'model-distribution' },
];
const work = mkdtempSync(join(tmpdir(), 'voxelshogi-control-mutations-'));
try {
  for (const mutation of mutations) {
    const copy = join(work, mutation.name), source = join(copy, mutation.file), test = `scripts/ci/${mutation.test}.test.mjs`;
    mkdirSync(dirname(source), { recursive: true }); mkdirSync(dirname(join(copy, test)), { recursive: true });
    const original = readFileSync(join(root, mutation.file), 'utf8');
    assert.equal(original.split(mutation.before).length - 1, 1, `stale mutation ${mutation.name}`);
    cpSync(join(root, test), join(copy, test)); writeFileSync(source, original);
    cpSync(join(root, 'LICENSE'), join(copy, 'LICENSE'));
    cpSync(join(root, 'scripts/browser-memory.mjs'), join(copy, 'scripts/browser-memory.mjs'));
    if (mutation.test === 'model-distribution') for (const file of ['scripts/inference-build.mjs', 'scripts/verify-model-distribution.mjs']) {
      if (file !== mutation.file) cpSync(join(root, file), join(copy, file));
    }
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
