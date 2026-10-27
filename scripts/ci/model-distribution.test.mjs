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
    assert.deepEqual(inferenceBuild(dir).files, [{ path: 'assets/inference.worker-abc.js', bytes: 3, sha256: hash('abc') }]);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

function distribution(change = {}) {
  const bodies = new Map(), descriptor = (path, body = 'abc') => { bodies.set('https://example.test/' + path, body); return { path, bytes: Buffer.byteLength(body), sha256: hash(body) }; };
  const prefix = 'models/m3/', worker = descriptor('assets/inference.worker-abc.js');
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
  bodies.set('https://example.test/inference-build.json', JSON.stringify({ schema: 1, commit, files: [worker] }));
  const index = { schema: 1, publication: true, model: modelFile, modelNotices: [notice, card], runtime: { version: '1.31.1', bundle: runtimeFile, bootstrap: runtimeFile, notices: [notice], wasm: { bytes: 3, sha256: hash('abc'), parts: [part] } }, ...change };
  bodies.set('https://example.test/models/m3/index.json', JSON.stringify(index));
  const fetcher = async url => new Response(bodies.get(url) ?? 'missing', { status: bodies.has(url) ? 200 : 404, headers: {
    'content-type': url.endsWith('.js') || url.endsWith('.mjs') ? 'text/javascript' : 'application/octet-stream',
    'cache-control': url.endsWith('/index.json') ? 'no-store' : 'public, max-age=31536000, immutable',
  } });
  return { bodies, fetcher };
}

test('published audit verifies application, model, references, notices and whole runtime bytes', async () => {
  const d = distribution(), r = await verifyDistribution('https://example.test', commit, d.fetcher);
  assert.equal(r.expectedCommit, commit); assert.equal(r.sameOrigin, true); assert.ok(r.records.length >= 10);
  assert.ok(r.records.some(r => r.url.endsWith('/data.bin') && r.sha256 === hash('abc')));
  d.bodies.set('https://example.test/models/m3/models/hash/data.bin', 'abd');
  await assert.rejects(verifyDistribution('https://example.test', commit, d.fetcher), /hash mismatch/);
  const pending = distribution({ publication: false });
  await assert.rejects(verifyDistribution('https://example.test', commit, pending.fetcher), /not approved/);
});
