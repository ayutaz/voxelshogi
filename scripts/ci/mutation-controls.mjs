import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, mkdirSync, cpSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const mutations = [
  { name: 'video-first-content-frame', file: 'scripts/demo-video.mjs', before: 'else if (green >= 3) return frame;', after: 'else if (green >= 3) return frame + 1;', test: 'demo-video' },
  { name: 'video-cross-layer-hook', file: 'scripts/demo-video.mjs', before: 'move[2] !== move[5]', after: 'move[2] === move[5]', test: 'demo-video' },
  { name: 'video-duration-proof', file: 'scripts/demo-video.mjs', before: 'Math.abs(Number(probe.format.duration) - seconds) <= 1 / 30', after: 'true', test: 'demo-video' },
  { name: 'video-frame-count', file: 'scripts/demo-video.mjs', before: 'assert.equal(Number(stream.nb_frames), seconds * 30);', after: '', test: 'demo-video' },
  { name: 'research-channel-progress-not-terminal', file: 'scripts/research-browser-channel.mjs', before: "message.status === 'progress'", after: 'false', test: 'research-browser-channel' },
  { name: 'research-channel-timeout-stage', file: 'scripts/research-browser-channel.mjs', before: "progress.at(-1)?.stage ?? 'worker-start'", after: "'worker-start'", test: 'research-browser-channel' },
  { name: 'research-channel-worker-release', file: 'scripts/research-browser-channel.mjs', before: 'cancel(timer);worker.terminate();', after: 'cancel(timer);', test: 'research-browser-channel' },
  { name: 'research-channel-progress-bound', file: 'scripts/research-browser-channel.mjs', before: 'progress.length >= 128', after: 'false', test: 'research-browser-channel' },
  { name: 'research-channel-case-identity', file: 'scripts/research-browser-channel.mjs', before: 'message?.name !== data.name', after: 'false', test: 'research-browser-channel' },
  { name: 'research-channel-fixed-deadline', file: 'scripts/research-browser-channel.mjs', before: "fail('TimeoutError', 'research case timed out'), 180000", after: "fail('TimeoutError', 'research case timed out'), 180001", test: 'research-browser-channel' },
  { name: 'research-channel-progress-preserves-timer', file: 'scripts/research-browser-channel.mjs', before: 'progress.push(update);', after: 'progress.push(update);cancel(timer);', test: 'research-browser-channel' },
  { name: 'research-browser-session-progress', file: 'scripts/research-browser-worker.mjs', before: "stage = 'session';", after: "stage = 'model-download';", test: 'research-browser-probe' },
  { name: 'research-browser-warmup-progress', file: 'scripts/research-browser-worker.mjs', before: "stage = i < data.plan.warmup_steps ? 'warmup' : 'measurement';", after: "stage = 'measurement';", test: 'research-browser-probe' },
  { name: 'research-browser-progress-envelope', file: 'scripts/research-browser-worker.mjs', before: "status: 'progress', name: data.name", after: "status: 'success', name: data.name", test: 'research-browser-probe' },
  { name: 'research-browser-request-encoding', file: 'scripts/research-browser-contract.mjs', before: 'encodeURIComponent(descriptor.path)', after: 'descriptor.path', test: 'research-browser-probe' },
  { name: 'research-browser-runtime-origin', file: 'scripts/research-browser-contract.mjs', before: 'value?.assetBase === assetBase', after: 'true', test: 'research-browser-probe' },
  { name: 'research-browser-runtime-known-path', file: 'scripts/research-browser-contract.mjs', before: 'entry?.path === path', after: 'true', test: 'research-browser-probe' },
  { name: 'research-browser-worker-owner-origin', file: 'scripts/research-browser-worker.mjs', before: "event.origin !== ''", after: 'false', test: 'research-browser-probe' },
  { name: 'research-browser-worker-private-scope', file: 'scripts/research-browser-worker.mjs', before: '!(self instanceof DedicatedWorkerGlobalScope)', after: 'false', test: 'research-browser-probe' },
  { name: 'research-browser-vector-tolerance', file: 'scripts/research-browser-contract.mjs', before: 'delta > atol + rtol * Math.abs(expected[i])', after: 'delta < atol + rtol * Math.abs(expected[i])', test: 'research-browser-probe' },
  { name: 'research-browser-body-hash', file: 'scripts/research-browser-contract.mjs', before: 'digest === descriptor.sha256', after: 'true', test: 'research-browser-probe' },
  { name: 'research-browser-no-provider-fallback', file: 'scripts/research-browser-contract.mjs', before: 'entries.length === 1', after: 'entries.length >= 1', test: 'research-browser-probe' },
  { name: 'research-browser-full-architecture-matrix', file: 'scripts/research-browser-contract.mjs', before: 'value.models.length === 4', after: 'value.models.length === 3', test: 'research-browser-probe' },
  { name: 'research-browser-linux-only', file: 'scripts/research-browser-contract.mjs', before: "platform === 'linux'", after: 'true', test: 'research-browser-probe' },
  { name: 'security-scope-must-succeed', file: 'scripts/ci/security-scope.mjs', before: "scope?.result !== 'success'", after: 'false', test: 'security-scope' },
  { name: 'security-scope-typed-outputs', file: 'scripts/ci/security-scope.mjs', before: "outputKeys.every(key => ['true', 'false'].includes(scope.outputs?.[key]))", after: 'true', test: 'security-scope' },
  { name: 'security-any-affected-language', file: 'scripts/ci/security-scope.mjs', before: "impactKeys.some(key => scope.outputs[key] === 'true')", after: 'false', test: 'security-scope' },
  { name: 'security-pr-requires-real-results', file: 'scripts/ci/security-scope.mjs', before: "if (eventName !== 'push') return true;", after: "if (!['pull_request', 'push'].includes(eventName)) return true;", test: 'security-scope' },
  { name: 'security-periodic-always-analyzes', file: 'scripts/ci/security-scope.mjs', before: "if (eventName !== 'push') return true;", after: "if (eventName !== 'push') return false;", test: 'security-scope' },
  { name: 'security-required-check-on-scope-failure', file: '.github/workflows/security.yml', before: "    needs: scope\n    if: always()", after: "    needs: scope\n    if: success()", test: 'security-scope' },
  { name: 'security-init-requires-proof', file: '.github/workflows/security.yml', before: "      - if: steps.proof.outputs.analyze == 'true'\n        uses: github/codeql-action/init@", after: "      - uses: github/codeql-action/init@", test: 'security-scope' },
  { name: 'security-analysis-requires-proof', file: '.github/workflows/security.yml', before: "      - if: steps.proof.outputs.analyze == 'true'\n        uses: github/codeql-action/analyze@", after: "      - uses: github/codeql-action/analyze@", test: 'security-scope' },
  { name: 'scope-unknown-full', file: 'scripts/ci/ci-scope.mjs', before: 'else return full(); // New/unclassified input must not silently lose coverage.', after: 'else continue;', test: 'ci-scope' },
  { name: 'scope-rename-both-sides', file: 'scripts/ci/ci-scope.mjs', before: "['diff','--name-only','--no-renames','-z',base,'HEAD']", after: "['diff','--name-only','--find-renames','-z',base,'HEAD']", test: 'ci-scope' },
  { name: 'scope-core-cross-language', file: 'scripts/ci/ci-scope.mjs', before: "['rust','web','python','models']", after: "['rust']", test: 'ci-scope' },
  { name: 'required-training-matrix', file: 'scripts/ci/gate.mjs', before: ", 'python-model-mutations', 'python-training-mutations', 'quality'].flatMap", after: ", 'python-model-mutations', 'quality'].flatMap", test: 'gate' },
  { name: 'main-deep-verification', file: 'scripts/ci/ci-scope.mjs', before: "eventName !== 'pull_request'", after: 'false', test: 'ci-scope' },
  { name: 'required-main-quality', file: 'scripts/ci/gate.mjs', before: ", 'quality'].flatMap", after: '].flatMap', test: 'gate' },
  { name: 'main-cannot-use-fast-scope', file: 'scripts/ci/gate.mjs', before: " && (event === 'pull_request' || scope.outputs.deep === 'true')", after: '', test: 'gate' },
  { name: 'required-deep-output', file: 'scripts/ci/gate.mjs', before: ", 'deep']", after: ']', test: 'gate' },
  { name: 'pr-deferred-mutations', file: 'scripts/ci/gate.mjs', before: " || scope.outputs.deep === 'false'", after: '', test: 'gate' },
  { name: 'typed-scope-proof', file: 'scripts/ci/gate.mjs', before: "scopeKeys.every((name) => ['true', 'false'].includes(scope.outputs?.[name]))", after: 'true', test: 'gate' },
  { name: 'unaffected-failure-is-still-failure', file: 'scripts/ci/gate.mjs', before: "validScope && result === 'skipped'", after: 'validScope', test: 'gate' },
  { name: 'benchmark-wait-measured-input', file: 'scripts/trained-benchmark.mjs', before: 'const measured = await Promise.race([completion.then(() => false), waitForMeasured().then(() => true)]);', after: 'const measured = true;', test: 'trained-benchmark' },
  {"name": "portable-evidence-compute", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.equal(validation.information.computePrecision, 'float32', 'FP16 weight-only requires FP32 compute');", "after": "", "test": "trained-browser-evidence"},
  { name: 'benchmark-root-side', file: 'scripts/trained-benchmark.mjs', before: 'if (game.sideToMove() !== fixture.side)', after: 'if (false)', test: 'trained-benchmark' },
  { name: 'benchmark-root-free', file: 'scripts/trained-benchmark.mjs', before: 'finally { game.free(); }', after: 'finally {}', test: 'trained-benchmark' },
  { name: 'benchmark-root-history', file: 'scripts/trained-benchmark.mjs', before: "ruleset: 'voxelshogi-standard-v1', recordJson }", after: "ruleset: 'voxelshogi-standard-v1', recordJson: '{}' }", test: 'trained-benchmark' },
  { name: 'benchmark-initial-not-switch', file: 'scripts/trained-benchmark.mjs', before: 'formats[(i + 1) % formats.length]', after: 'formats[i % formats.length]', test: 'trained-benchmark' },
  { name: 'benchmark-files-once', file: 'scripts/trained-benchmark.mjs', before: '!sentFiles ? { files:', after: 'true ? { files:', test: 'trained-benchmark' },
  { name: 'benchmark-reply-id', file: 'scripts/trained-benchmark.mjs', before: 'data.requestId !== active.id || ', after: '', test: 'trained-benchmark' },
  { name: 'benchmark-ignore-progress', file: 'scripts/trained-benchmark.mjs', before: " || data.kind === 'progress'", after: '', test: 'trained-benchmark' },
  { name: 'benchmark-worker-close', file: 'scripts/trained-benchmark.mjs', before: 'worker?.terminate();', after: '', test: 'trained-benchmark' },
  { name: 'benchmark-warmup-exclusion', file: 'scripts/trained-benchmark.mjs', before: 'if(i>=warmup)samples.push(result)', after: 'if(true)samples.push(result)', test: 'trained-benchmark' },
  { name: 'benchmark-measured-input-only', file: 'scripts/trained-benchmark.mjs', before: 'count>1 && i>=warmup', after: 'count>1', test: 'trained-benchmark' },
  { name: 'trained-evidence-contract', file: 'scripts/trained-browser-evidence.mjs', before: "assert.equal(model.numericContract, 'voxelshogi-trained-numeric-v1', 'trained numeric contract differs');", after: '', test: 'trained-browser-evidence' },
  { name: 'trained-evidence-absolute-bound', file: 'scripts/trained-browser-evidence.mjs', before: "assert.equal(stats.atol, atol, 'numeric absolute bound differs');", after: '', test: 'trained-browser-evidence' },
  { name: 'trained-evidence-relative-bound', file: 'scripts/trained-browser-evidence.mjs', before: "assert.equal(stats.rtol, rtol, 'numeric relative bound differs');", after: '', test: 'trained-browser-evidence' },
  {"name": "trained-no-unsupported-switch", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.ok(report.rows.filter(row => row.backend === group.backend && row.precision === step.precision).every(row => row.status === 'done'), 'unsupported format cannot be a successful switch');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-linux-only", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.equal(platform, 'linux', 'trained browser measurements require external Linux');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-public-proof", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.ok(allowCandidate || report.candidate === false, 'candidate is not final public proof');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-only-provider", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.deepEqual(Object.keys(validation.profile.providers), [provider], 'unexpected policy provider');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-all-references", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.deepEqual(validation.fixtures.map(f => f.name), TRAINED_FIXTURES, 'all same-format references required');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-model-identity", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.deepEqual(row.selection, { modelId: model.id, packageHash: model.packageHash, precision: row.precision, backend: row.backend }, 'mixed model identity');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-ten-warmups", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.equal(row.warmupCount, 10, 'ten warmups required');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-thirty-measurements", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.equal(row.samples.length, 30, 'thirty measured repetitions required');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-actual-switch", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.notEqual(step.precision, previous, 'initial load or repeated model is not a switch');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-memory-gap", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.ok(Number.isFinite(value.maximumSamplingGapMs) && value.maximumSamplingGapMs >= 0 && value.maximumSamplingGapMs <= 5000, 'resource sampling gap exceeds bound');", "after": "", "test": "trained-browser-evidence"},
  {"name": "trained-unsupported-classification", "file": "scripts/trained-browser-evidence.mjs", "before": "assert.match(row.error.message, /shader-f16|outputs exceed .* tolerance|not supported|unsupported|WebGPU.*not available/i, 'unclassified error is not unsupported');", "after": "", "test": "trained-browser-evidence"},
  { name: 'policy-worker-build', file: 'scripts/inference-build.mjs', before: "assert.ok(policyWorker, 'policy Worker is missing from build');", after: '', test: 'model-distribution' },
  { name: 'policy-worker-served', file: 'scripts/verify-model-distribution.mjs', before: "assert.ok(policyWorker, 'policy Worker missing from tested application');", after: '', test: 'model-distribution' },
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
    if (mutation.test === 'research-browser-probe') for (const file of ['scripts/research-browser-contract.mjs', 'scripts/research-browser-worker.mjs']) {
      if (file !== mutation.file) cpSync(join(root, file), join(copy, file));
    }
    if (mutation.test === 'model-distribution') for (const file of ['scripts/inference-build.mjs', 'scripts/verify-model-distribution.mjs']) {
      if (file !== mutation.file) cpSync(join(root, file), join(copy, file));
    }
    if (mutation.test === 'security-scope') for (const file of ['scripts/ci/ci-scope.mjs', 'scripts/ci/security-scope.mjs', '.github/workflows/security.yml']) {
      if (file !== mutation.file) {
        mkdirSync(dirname(join(copy, file)), { recursive: true });
        cpSync(join(root, file), join(copy, file));
      }
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
