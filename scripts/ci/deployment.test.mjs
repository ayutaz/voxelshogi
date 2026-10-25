import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { isCurrentCommit, parseDeploymentVersion, productionConfig, stampBuild, waitForDeployment } from './deployment.mjs';

const sha = 'a'.repeat(40);
const config = { CLOUDFLARE_API_TOKEN: 'private-token', CLOUDFLARE_ACCOUNT_ID: 'private-account', WORKERS_SUBDOMAIN: 'yousan-apps' };

test('deployment records exactly one Cloudflare version ID', () => {
  const version = '01234567-89ab-cdef-0123-456789abcdef';
  const log = `Uploaded voxelshogi\nCurrent Version ID: ${version}\n`;
  assert.equal(parseDeploymentVersion(log), version);
  assert.throws(() => parseDeploymentVersion('Upload failed'), /version/);
  assert.throws(() => parseDeploymentVersion(log + log), /version/);
});

test('production requires every configuration value without exposing values', () => {
  assert.equal(productionConfig(config), 'https://voxelshogi.yousan-apps.workers.dev');
  for (const key of Object.keys(config)) {
    assert.throws(() => productionConfig({ ...config, [key]: '' }), (error) => error.message.includes(key) && !error.message.includes('private-'));
  }
  assert.throws(() => productionConfig({ ...config, WORKERS_SUBDOMAIN: 'evil.example/path' }), /subdomain/);
});

test('only the current main commit can be deployed', () => {
  assert.equal(isCurrentCommit(sha, sha), true);
  assert.equal(isCurrentCommit('b'.repeat(40), sha), false);
  assert.throws(() => isCurrentCommit('', sha), /commit/);
  assert.throws(() => isCurrentCommit(sha, 'not-a-sha'), /commit/);
});

test('build information records the tested commit deterministically', () => {
  const dir = mkdtempSync(join(tmpdir(), 'voxelshogi-stamp-'));
  try {
    stampBuild(dir, sha);
    assert.deepEqual(JSON.parse(readFileSync(join(dir, 'build-info.json'), 'utf8')), { commit: sha });
    const first = readFileSync(join(dir, 'build-info.json'), 'utf8');
    stampBuild(dir, sha);
    assert.equal(readFileSync(join(dir, 'build-info.json'), 'utf8'), first);
    assert.throws(() => stampBuild(dir, ''), /commit/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('publication waits for the expected commit and bypasses caches', async () => {
  let requests = 0;
  let waits = 0;
  await waitForDeployment('https://example.test', sha, {
    attempts: 3,
    fetch: async (url, options) => {
      requests++;
      assert.equal(new URL(url).searchParams.get('commit'), sha);
      assert.equal(options.cache, 'no-store');
      return Response.json({ commit: requests === 1 ? 'b'.repeat(40) : sha });
    },
    sleep: async () => { waits++; },
  });
  assert.equal(requests, 2);
  assert.equal(waits, 1);
});

for (const [name, fetch] of [
  ['old commit', async () => Response.json({ commit: 'b'.repeat(40) })],
  ['HTML fallback', async () => new Response('<html>SPA fallback</html>')],
  ['HTTP failure', async () => new Response('', { status: 503 })],
  ['network failure', async () => { throw new Error('connection failed'); }],
]) {
  test(`publication fails within its limit for ${name}`, async () => {
    let attempts = 0;
    await assert.rejects(waitForDeployment('https://example.test', sha, {
      attempts: 2,
      fetch: async (...args) => { attempts++; return fetch(...args); },
      sleep: async () => {},
    }), /not published/);
    assert.equal(attempts, 2);
  });
}
