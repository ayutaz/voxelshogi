import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, posix, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export async function verifyDistribution(base, expectedCommit, fetcher = fetch, expectedArtifact = null) {
  assert.match(expectedCommit, /^[0-9a-f]{40}$/, 'expected published commit required');
  const origin = new URL(base).origin, modelBase = new URL('/models/m3/', origin).href, records = [];
  const path = name => {
    assert.ok(typeof name === 'string' && /^[a-zA-Z0-9_./-]+$/.test(name) && !name.startsWith('/') && !name.split('/').some(p => !p || p === '.' || p === '..'), 'unsafe distribution path');
    return name;
  };
  const read = async (url, file = null, capture = false, onChunk = null) => {
    if (file) { path(file.path); assert.ok(Number.isSafeInteger(file.bytes) && file.bytes > 0 && file.bytes <= 25 * 1024 * 1024, 'invalid file size'); assert.match(file.sha256, /^[0-9a-f]{64}$/); }
    const response = await fetcher(url, { cache: 'no-store', redirect: 'error' });
    assert.equal(response.status, 200, `download failed: ${url}`);
    const limit = file?.bytes ?? 1024 * 1024, hash = createHash('sha256'), chunks = [];
    let bytes = 0;
    for await (const chunk of response.body) {
      bytes += chunk.byteLength; assert.ok(bytes <= limit, 'distribution body exceeds expected size');
      hash.update(chunk); if (capture) chunks.push(chunk); if (onChunk) onChunk(chunk);
    }
    const sha256 = hash.digest('hex'), headers = response.headers;
    if (file) { assert.equal(bytes, file.bytes, `length mismatch: ${url}`); assert.equal(sha256, file.sha256, `hash mismatch: ${url}`); }
    const mime = headers.get('content-type') ?? '', cache = headers.get('cache-control') ?? '';
    assert.ok(!mime.includes('text/html'), 'HTML fallback is not an artifact');
    if (url.endsWith('.mjs') || url.endsWith('.js')) assert.match(mime, /(?:javascript|ecmascript)/i, 'JavaScript MIME required');
    if (file) assert.match(cache, /immutable/, 'content-addressed files must be immutable');
    records.push({ url, bytes, sha256, mime, cache, contentEncoding: headers.get('content-encoding'), cors: headers.get('access-control-allow-origin') });
    return capture ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : null;
  };
  const build = await read(new URL('/build-info.json', origin).href, null, true);
  assert.equal(build.commit, expectedCommit, 'wrong public build');
  if (expectedArtifact) assert.deepEqual(build, expectedArtifact.build, 'served build differs from tested artifact');
  const application = await read(new URL('/inference-build.json', origin).href, null, true);
  assert.equal(application.schema, 1); assert.equal(application.commit, expectedCommit);
  if (expectedArtifact) assert.deepEqual(application, expectedArtifact.application, 'served files differ from tested application artifact');
  assert.ok(application.files.some(f => /^assets\/inference\.worker-.*\.js$/.test(f.path)), 'application Worker manifest missing');
  for (const file of application.files) await read(new URL(path(file.path), origin + '/').href, file);
  const indexUrl = modelBase + 'index.json', index = await read(indexUrl, null, true);
  if (expectedArtifact) assert.deepEqual(index, expectedArtifact.deployment, 'served files differ from tested model artifact');
  assert.match(records.at(-1).cache, /no-store/, 'model index must bypass cache');
  assert.equal(index.schema, 1); assert.equal(index.publication, true, 'model publication is not approved');
  const model = await read(new URL(path(index.model.path), modelBase).href, index.model, true);
  assert.equal(model.license, 'Apache-2.0'); assert.equal(model.trained, false); assert.equal(model.sourceDirty, false);
  assert.match(model.sourceCommit, /^[0-9a-f]{40}$/); assert.deepEqual(model.variants.map(v => v.id), ['fp32', 'fp16', 'int8']);
  assert.ok(index.modelNotices.length >= 2, 'model license/card missing');
  assert.equal(index.runtime.version, '1.31.1');
  const wasm = createHash('sha256'); let wasmBytes = 0;
  for (const part of index.runtime.wasm.parts) await read(new URL(path(part.path), modelBase).href, part, false, chunk => { wasm.update(chunk); wasmBytes += chunk.byteLength; });
  assert.equal(wasmBytes, index.runtime.wasm.bytes); assert.equal(wasm.digest('hex'), index.runtime.wasm.sha256, 'reassembled runtime mismatch');
  for (const file of [index.runtime.bundle, index.runtime.bootstrap, ...index.runtime.notices, ...index.modelNotices]) await read(new URL(path(file.path), modelBase).href, file);
  const prefix = posix.dirname(index.model.path) + '/', files = [model.checkpoint, ...model.fixtures.map(f => f.input)];
  for (const variant of model.variants) { files.push(variant.model); for (const ref of Object.values(variant.references)) files.push(ref.policy, ref.value); }
  const seen = new Map();
  for (const file of files) {
    const key = path(file.path), previous = seen.get(key);
    if (previous) { assert.deepEqual(file, previous, 'inconsistent duplicate descriptor'); continue; }
    seen.set(key, file); await read(new URL(prefix + key, modelBase).href, file);
  }
  return { schema: 1, verifiedAt: new Date().toISOString(), expectedCommit, modelId: model.id, modelManifestSha256: index.model.sha256, sameOrigin: true, records };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [, , base, output, artifactDirectory = 'apps/web/dist'] = process.argv;
  assert.ok(base && output, 'usage: E2E_COMMIT=SHA node scripts/verify-model-distribution.mjs BASE_URL OUTPUT.json [TESTED_DIST_DIRECTORY]');
  const local = file => JSON.parse(readFileSync(resolve(artifactDirectory, file), 'utf8'));
  const expected = { build: local('build-info.json'), application: local('inference-build.json'), deployment: local('models/m3/index.json') };
  const report = await verifyDistribution(base, process.env.E2E_COMMIT, fetch, expected);
  mkdirSync(dirname(resolve(output)), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ commit: report.expectedCommit, modelId: report.modelId, verifiedFiles: report.records.length }));
}
