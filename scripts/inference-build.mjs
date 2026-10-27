import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function inferenceBuild(directory) {
  const root = resolve(directory), build = JSON.parse(readFileSync(resolve(root, 'build-info.json'), 'utf8'));
  assert.match(build.commit, /^[0-9a-f]{40}$/, 'tested build commit required');
  const files = readdirSync(resolve(root, 'assets'), { withFileTypes: true }).filter(f => f.isFile() && /\.(?:js|mjs|wasm|css)$/.test(f.name)).map(f => {
    const path = `assets/${f.name}`, bytes = readFileSync(resolve(root, path));
    assert.ok(bytes.length > 0 && bytes.length <= 25 * 1024 * 1024, 'application asset exceeds static limit');
    return { path, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  }).sort((a, b) => a.path.localeCompare(b.path));
  assert.ok(files.some(f => /^assets\/inference\.worker-.*\.js$/.test(f.path)), 'inference Worker is missing from build');
  const manifest = { schema: 1, commit: build.commit, files };
  writeFileSync(resolve(root, 'inference-build.json'), JSON.stringify(manifest, null, 2) + '\n');
  return manifest;
}
if (import.meta.url === pathToFileURL(process.argv[1]).href) inferenceBuild(process.argv[2]);
