import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

assert.equal(process.platform, 'linux');
const base = 'https://voxelshogi.yousan-apps.workers.dev/models/m3/';
const response = await fetch(base + 'index.json', { credentials: 'omit' });
assert.equal(response.status, 200);
const text = await response.text(); assert.ok(text.length < 1024 * 1024);
const index = JSON.parse(text); assert.equal(index.runtime.version, '1.31.1');
const root = resolve('apps/web/public/models/m3');
const refs = [index.runtime.bundle, index.runtime.bootstrap, ...index.runtime.wasm.parts, ...index.runtime.notices];
for (const file of refs) {
  assert.match(file.path, /^runtime\/[0-9a-f]{64}\/[A-Za-z0-9_.-]+$/);
  assert.ok(Number.isSafeInteger(file.bytes) && file.bytes > 0 && file.bytes <= 25 * 1024 * 1024);
  const result = await fetch(new URL(file.path, base), { credentials: 'omit' }); assert.equal(result.status, 200);
  const bytes = Buffer.from(await result.arrayBuffer()); assert.equal(bytes.length, file.bytes);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), file.sha256);
  const path = resolve(root, file.path); mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, bytes);
}
mkdirSync(root, { recursive: true }); writeFileSync(resolve(root, 'index.json'), text);
console.log(`Verified ${refs.length} pinned public runtime assets; no M3 or S weights copied`);
