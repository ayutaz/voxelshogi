import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
export const MAX_ASSET_BYTES = 25 * 1024 * 1024;
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
function safePath(directory, name) {
  assert.ok(typeof name === 'string' && /^[a-zA-Z0-9_./-]+$/.test(name) && !isAbsolute(name) && !name.split('/').some((p) => !p || p === '.' || p === '..'), 'invalid package path');
  const path = realpathSync(resolve(directory, name));
  assert.ok(!relative(realpathSync(directory), path).startsWith('..'), 'package symlink escapes source');
  return path;
}

export function prepareInference(modelDirectory, outputDirectory, runtimeDirectory = resolve(root, 'apps/web/node_modules/onnxruntime-web'), options = {}) {
  const publication = options.publication ?? true;
  const partBytes = options.partBytes ?? 16 * 1024 * 1024;
  assert.ok(Number.isSafeInteger(partBytes) && partBytes > 0 && partBytes <= MAX_ASSET_BYTES, 'invalid part size');
  const source = resolve(modelDirectory), output = resolve(outputDirectory);
  const manifestBytes = readFileSync(resolve(source, 'manifest.json'));
  const manifest = JSON.parse(manifestBytes);
  if (publication) {
    assert.equal(manifest.license, 'Apache-2.0', 'model license must be approved before publication');
    assert.equal(manifest.sourceDirty, false, 'publication requires clean source');
    assert.ok(typeof manifest.sourceCommit === 'string' && /^[0-9a-f]{40}$/.test(manifest.sourceCommit), 'publication requires a source commit');
    assert.equal(manifest.trained, false, 'M3 approval does not cover trained models');
  }
  const runtimePackage = JSON.parse(readFileSync(resolve(runtimeDirectory, 'package.json'), 'utf8'));
  assert.equal(runtimePackage.version, '1.31.1', 'runtime files and pinned API must match');
  const modelPrefix = `models/${sha(manifestBytes)}/`;
  const write = (name, bytes) => {
    assert.ok(bytes.length > 0 && bytes.length <= MAX_ASSET_BYTES, `asset too large: ${name}`);
    const path = resolve(output, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, bytes);
    return { path: name, bytes: bytes.length, sha256: sha(bytes) };
  };
  const files = [manifest.checkpoint, ...manifest.fixtures.map((f) => f.input)];
  for (const variant of manifest.variants) {
    files.push(variant.model);
    for (const reference of Object.values(variant.references)) files.push(reference.policy, reference.value);
  }
  for (const file of files) {
    const bytes = readFileSync(safePath(source, file.path));
    assert.equal(bytes.length, file.bytes, 'model file length mismatch');
    assert.equal(sha(bytes), file.sha256, 'model file hash mismatch');
    write(modelPrefix + file.path, bytes);
  }
  const bundleName = 'ort.webgpu.bundle.min.mjs', bootstrapName = 'ort-wasm-simd-threaded.asyncify.mjs', wasmName = 'ort-wasm-simd-threaded.asyncify.wasm';
  const bundle = readFileSync(resolve(runtimeDirectory, 'dist', bundleName));
  assert.ok(bundle.toString('utf8').includes(bootstrapName), 'runtime bundle/bootstrap flavor mismatch');
  const bootstrap = readFileSync(resolve(runtimeDirectory, 'dist', bootstrapName));
  const wasm = readFileSync(resolve(runtimeDirectory, 'dist', wasmName));
  const runtimePrefix = `runtime/${sha(Buffer.concat([bundle, bootstrap, wasm]))}/`;
  const parts = [];
  for (let start = 0, i = 0; start < wasm.length; start += partBytes, i++) {
    parts.push(write(`${runtimePrefix}${wasmName}.part-${String(i).padStart(3, '0')}.bin`, wasm.subarray(start, start + partBytes)));
  }
  const noticesDirectory = existsSync(resolve(runtimeDirectory, 'LICENSE')) ? runtimeDirectory : resolve(root, 'third_party/onnxruntime-1.31.1');
  const notices = ['LICENSE', 'ThirdPartyNotices.txt'].map((name) => write(runtimePrefix + name, readFileSync(resolve(noticesDirectory, name))));
  const modelNotices = [];
  if (manifest.license === 'Apache-2.0') {
    const license = readFileSync(resolve(root, 'LICENSE'));
    const card = Buffer.from(`# Untrained VoxelShogi model\n\nModel ID: ${manifest.id}\n\nUntrained, fixed-seed technical validation only. This is not a playing-strength or win-probability estimate.\n\n- Parameters: ${manifest.parameters}\n- Seed: ${manifest.seed}\n- License: Apache-2.0 (see the accompanying LICENSE file)\n- Source commit: ${manifest.sourceCommit}\n- Source dirty: ${manifest.sourceDirty}\n- Input: float32 [1,729,43], standard single-king rules\n- Outputs: float32 Policy [1,1067985] and Value [1,1]\n\n| Variant | Precision | Bytes | SHA-256 |\n|---|---|---:|---|\n${manifest.variants.map(v => `| ${v.id} | ${v.precision} | ${v.model.bytes} | ${v.model.sha256} |`).join('\n')}\n\nINT8 stores quantized weights and computes in float32 with graph optimization basic. FP16 WebGPU did not meet the numerical criteria on the tested Apple M1; the FP16 WASM path is verified. Other devices must pass runtime comparison before an output is accepted.\n\nFull conversion settings, same-format reference files and FP32 differences are in manifest.json. The original checkpoint and fixed inputs belong to the same package.\n\n[Validation records](https://github.com/ayutaz/voxelshogi/blob/main/docs/M3_VALIDATION.md)\n`);
    modelNotices.push(write(`${modelPrefix}LICENSE-${sha(license)}.txt`, license), write(`${modelPrefix}MODEL_CARD-${sha(card)}.md`, card));
  }
  const index = { schema: 1, publication, modelNotices,
    model: write(modelPrefix + 'manifest.json', manifestBytes),
    runtime: { version: runtimePackage.version, license: runtimePackage.license, bundle: write(runtimePrefix + bundleName, bundle),
      bootstrap: write(runtimePrefix + bootstrapName, bootstrap), wasm: { path: wasmName, bytes: wasm.length, sha256: sha(wasm), parts }, notices },
  };
  write('index.json', Buffer.from(JSON.stringify(index, null, 2) + '\n'));
  return index;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [, , model, output, flag] = process.argv;
  assert.ok(model && output && (!flag || flag === '--local'), 'usage: node scripts/prepare-inference.mjs MODEL_DIRECTORY OUTPUT_DIRECTORY [--local]');
  console.log(JSON.stringify(prepareInference(model, output, undefined, { publication: flag !== '--local' }), null, 2));
}
