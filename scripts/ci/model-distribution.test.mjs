import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { inferenceBuild } from '../inference-build.mjs';
import { verifyDistribution } from '../verify-model-distribution.mjs';

const commit = 'a'.repeat(40), hash = text => createHash('sha256').update(text).digest('hex');
test('build manifest contains the actual application Worker hash and rejects its absence', () => {
  const dir = mkdtempSync(join(tmpdir(), 'voxelshogi-app-manifest-'));
  try {
    mkdirSync(join(dir, 'assets')); writeFileSync(join(dir, 'build-info.json'), JSON.stringify({ commit }));
    assert.throws(() => inferenceBuild(dir), /Worker/);
    writeFileSync(join(dir, 'assets/inference.worker-abc.js'), 'abc');
    mkdirSync(join(dir, 'models/m6'), { recursive: true });
    const catalog = '{"schema":1,"releases":[]}';
    writeFileSync(join(dir, 'models/m6/catalog.json'), catalog);
    assert.throws(() => inferenceBuild(dir), /policy Worker/);
    writeFileSync(join(dir, 'assets/policy.worker-abc.js'), 'policy');
    assert.deepEqual(inferenceBuild(dir).files, [{ path: 'assets/inference.worker-abc.js', bytes: 3, sha256: hash('abc') }, { path: 'assets/policy.worker-abc.js', bytes: 6, sha256: hash('policy') }]);
    assert.deepEqual(inferenceBuild(dir).catalog, { path: 'models/m6/catalog.json', bytes: Buffer.byteLength(catalog), sha256: hash(catalog) });
    writeFileSync(join(dir, 'models/m6/fp32.onnx'), 'opaque fixture');
    assert.throws(() => inferenceBuild(dir), /only catalog/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

function distribution(change = {}) {
  const bodies = new Map(), descriptor = (path, body = 'abc') => { bodies.set('https://example.test/' + path, body); return { path, bytes: Buffer.byteLength(body), sha256: hash(body) }; };
  const prefix = 'models/m3/', worker = descriptor('assets/inference.worker-abc.js'), policyWorker = descriptor('assets/policy.worker-abc.js');
  const file = descriptor(prefix + 'models/hash/data.bin');
  const relative = { ...file, path: 'data.bin' };
  const model = { id: 'test-untrained', license: 'Apache-2.0', trained: false, sourceDirty: false, sourceCommit: commit,
    checkpoint: relative, fixtures: [{ input: relative }], variants: ['fp32', 'fp16', 'int8'].map(id => ({ id, model: relative, references: { input: { policy: relative, value: relative } } })) };
  const modelFile = descriptor(prefix + 'models/hash/manifest.json', JSON.stringify(model)); modelFile.path = 'models/hash/manifest.json';
  const part = descriptor(prefix + 'runtime/part.bin'); part.path = 'runtime/part.bin';
  const runtimeFile = descriptor(prefix + 'runtime/code.mjs'); runtimeFile.path = 'runtime/code.mjs';
  const notice = descriptor(prefix + 'models/hash/LICENSE.txt'); notice.path = 'models/hash/LICENSE.txt';
  const card = descriptor(prefix + 'models/hash/MODEL_CARD.md'); card.path = 'models/hash/MODEL_CARD.md';
  bodies.set('https://example.test/build-info.json', JSON.stringify({ commit }));
  const catalog = descriptor('models/m6/catalog.json', '{"schema":1,"releases":[]}');
  bodies.set('https://example.test/inference-build.json', JSON.stringify({ schema: 1, commit, files: [worker, policyWorker], catalog }));
  const index = { schema: 1, publication: true, model: modelFile, modelNotices: [notice, card], runtime: { version: '1.31.1', bundle: runtimeFile, bootstrap: runtimeFile, notices: [notice], wasm: { bytes: 3, sha256: hash('abc'), parts: [part] } }, ...change };
  bodies.set('https://example.test/models/m3/index.json', JSON.stringify(index));
  const fetcher = async url => new Response(bodies.get(url) ?? 'missing', { status: bodies.has(url) ? 200 : 404, headers: {
    'content-type': url.endsWith('.js') || url.endsWith('.mjs') ? 'text/javascript' : 'application/octet-stream',
    'cache-control': url.endsWith('/index.json') || url.endsWith('/catalog.json') ? 'no-store' : 'public, max-age=31536000, immutable',
  } });
  return { bodies, fetcher };
}

test('published audit verifies application, model, references, notices and whole runtime bytes', async () => {
  const d = distribution(), r = await verifyDistribution('https://example.test', commit, d.fetcher);
  assert.equal(r.expectedCommit, commit); assert.equal(r.sameOrigin, true); assert.ok(r.records.length >= 10);
  assert.ok(r.records.some(r => r.url.endsWith('/data.bin') && r.sha256 === hash('abc')));
  assert.ok(r.records.some(r => r.url.endsWith('/models/m6/catalog.json') && r.cache === 'no-store'));
  d.bodies.set('https://example.test/models/m3/models/hash/data.bin', 'abd');
  await assert.rejects(verifyDistribution('https://example.test', commit, d.fetcher), /hash mismatch/);
  const pending = distribution({ publication: false });
  await assert.rejects(verifyDistribution('https://example.test', commit, pending.fetcher), /not approved/);
});

test('published model catalog bytes must match the tested catalog even with the same app commit', async () => {
  const d = distribution();
  d.bodies.set('https://example.test/models/m6/catalog.json', '{"schema":2,"releases":[]}');
  await assert.rejects(verifyDistribution('https://example.test', commit, d.fetcher), /hash mismatch/);
});

test('published application must include the actual policy Worker artifact', async () => {
  const d = distribution(), url = 'https://example.test/inference-build.json';
  const application = JSON.parse(d.bodies.get(url));
  application.files = application.files.filter(file => !file.path.includes('policy.worker'));
  d.bodies.set(url, JSON.stringify(application));
  await assert.rejects(verifyDistribution('https://example.test', commit, d.fetcher), /policy Worker/);
});

test('public manifests must match the tested artifact even when their commit still matches', async () => {
  const d = distribution();
  const expected = {
    build: JSON.parse(d.bodies.get('https://example.test/build-info.json')),
    application: JSON.parse(d.bodies.get('https://example.test/inference-build.json')),
    deployment: JSON.parse(d.bodies.get('https://example.test/models/m3/index.json')),
  };
  await verifyDistribution('https://example.test', commit, d.fetcher, expected);
  d.bodies.set('https://example.test/assets/inference.worker-abc.js', 'abd');
  d.bodies.set('https://example.test/inference-build.json', JSON.stringify({ ...expected.application,
    files: expected.application.files.map((file, index) => index === 0 ? { ...file, sha256: hash('abd') } : file) }));
  await assert.rejects(verifyDistribution('https://example.test', commit, d.fetcher, expected), /tested application artifact/);
  const changed = distribution();
  changed.bodies.set('https://example.test/models/m3/index.json', JSON.stringify({ ...expected.deployment, extra: 'different artifact' }));
  await assert.rejects(verifyDistribution('https://example.test', commit, changed.fetcher, expected), /tested model artifact/);
});
