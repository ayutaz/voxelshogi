import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { prepareInference } from '../prepare-inference.mjs';

const sha = (value) => createHash('sha256').update(value).digest('hex');
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'voxelshogi-inference-package-'));
  const model = join(root, 'model'), runtime = join(root, 'runtime'), output = join(root, 'output');
  mkdirSync(model); mkdirSync(join(runtime, 'dist'), { recursive: true });
  const bytes = Buffer.from('abc');
  writeFileSync(join(model, 'data.bin'), bytes);
  const file = { path: 'data.bin', bytes: 3, sha256: sha(bytes) };
  const manifest = { schema: 1, id: 'voxelshogi-transformer-s-untrained-314159-v1', seed: 314159, parameters: 5021064, license: 'Apache-2.0', trained: false, sourceDirty: false, sourceCommit: 'a'.repeat(40),
    checkpoint: file, fixtures: [{ name: 'test', input: file }],
    variants: [{ id: 'fp32', precision: 'fp32', model: file, references: { test: { policy: file, value: file } } }] };
  writeFileSync(join(model, 'manifest.json'), JSON.stringify(manifest));
  writeFileSync(join(runtime, 'package.json'), JSON.stringify({ version: '1.31.1', license: 'MIT' }));
  writeFileSync(join(runtime, 'README.md'), 'ORT notices in LICENSE/ThirdPartyNotices.txt');
  writeFileSync(join(runtime, 'LICENSE'), 'MIT test notice');
  writeFileSync(join(runtime, 'ThirdPartyNotices.txt'), 'third party test notice');
  writeFileSync(join(runtime, 'dist/ort.webgpu.bundle.min.mjs'), "export const env = {}; export const wasmModule = 'ort-wasm-simd-threaded.asyncify.mjs';");
  writeFileSync(join(runtime, 'dist/ort-wasm-simd-threaded.asyncify.mjs'), 'export default function(){}');
  writeFileSync(join(runtime, 'dist/ort-wasm-simd-threaded.asyncify.wasm'), 'abcdefghij');
  return { root, model, runtime, output, manifest };
}

test('publishes verified originals under immutable hashes and rejoins exact WASM bytes', () => {
  const f = fixture();
  try {
    const index = prepareInference(f.model, f.output, f.runtime, { partBytes: 4 });
    assert.equal(index.publication, true);
    assert.equal(index.runtime.version, '1.31.1');
    assert.equal(index.runtime.wasm.parts.length, 3);
    const chunks = index.runtime.wasm.parts.map((p) => {
      const bytes = readFileSync(join(f.output, p.path));
      assert.ok(bytes.length <= 4);
      assert.equal(sha(bytes), p.sha256);
      return bytes;
    });
    const original = Buffer.concat(chunks);
    assert.equal(original.toString(), 'abcdefghij');
    assert.equal(sha(original), index.runtime.wasm.sha256);
    assert.equal(readFileSync(join(f.output, index.model.path), 'utf8'), JSON.stringify(f.manifest));
    assert.equal(sha(readFileSync(join(f.output, index.runtime.bundle.path))), index.runtime.bundle.sha256);
    assert.equal(index.runtime.notices.length, 2);
    assert.equal(index.modelNotices.length, 2);
    const noticeText = index.modelNotices.map(item => {
      const bytes = readFileSync(join(f.output, item.path));
      assert.equal(sha(bytes), item.sha256);
      return bytes.toString('utf8');
    });
    assert.ok(noticeText.some(text => /Apache License/.test(text)));
    assert.ok(noticeText.some(text => text.includes(f.manifest.id) && /Untrained/.test(text)));
    assert.deepEqual(prepareInference(f.model, join(f.root, 'again'), f.runtime, { partBytes: 4 }), index);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

for (const failure of ['license', 'dirty', 'hash', 'path', 'commit', 'trained']) {
  test(`rejects an invalid release: ${failure}`, () => {
    const f = fixture();
    try {
      if (failure === 'license') f.manifest.license = null;
      if (failure === 'dirty') f.manifest.sourceDirty = true;
      if (failure === 'hash') writeFileSync(join(f.model, 'data.bin'), 'abd');
      if (failure === 'path') f.manifest.checkpoint = { ...f.manifest.checkpoint, path: '../secret' };
      if (failure === 'commit') f.manifest.sourceCommit = null;
      if (failure === 'trained') f.manifest.trained = true;
      writeFileSync(join(f.model, 'manifest.json'), JSON.stringify(f.manifest));
      assert.throws(() => prepareInference(f.model, f.output, f.runtime));
    } finally { rmSync(f.root, { recursive: true, force: true }); }
  });
}

test('local-only packages remain explicitly marked and cannot be mistaken for publication', () => {
  const f = fixture();
  try {
    f.manifest.license = null; f.manifest.sourceDirty = true;
    writeFileSync(join(f.model, 'manifest.json'), JSON.stringify(f.manifest));
    const index = prepareInference(f.model, f.output, f.runtime, { publication: false, partBytes: 4 });
    assert.equal(index.publication, false);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});
