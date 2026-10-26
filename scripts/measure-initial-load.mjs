// Generic before/after acquisition: can run against the pre-M2 public UI too.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { chromium } from '../apps/web/node_modules/@playwright/test/index.mjs';

const baseUrl = process.argv[2];
assert.ok(baseUrl, 'usage: node scripts/measure-initial-load.mjs BASE_URL OUTPUT.json');
const output = resolve(process.argv[3] ?? 'runs/m2/initial-load.json');
mkdirSync(dirname(output), { recursive: true });
const browser = await chromium.launch({ channel: 'chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const buildInfo = await (await page.request.get(new URL('/build-info.json', baseUrl).href)).json();
  assert.match(buildInfo.commit, /^[0-9a-f]{40}$/);
  await page.goto(baseUrl);
  await page.getByTestId('status').waitFor();
  const initialView = await page.locator('.views').getAttribute('class');
  const initialNetwork = await page.evaluate(() => performance.getEntriesByType('resource').map((r) => r.toJSON()));
  await page.getByRole('button', { name: '2D', exact: true }).click();
  const after2dNetwork = await page.evaluate(() => performance.getEntriesByType('resource').map((r) => r.toJSON()));
  const scripts = initialNetwork.filter((r) => /\.js(?:\?|$)/.test(r.name));
  assert.ok(scripts.length > 0 && scripts.every((r) => r.decodedBodySize > 0));
  const assets = [];
  for (const entry of initialNetwork.filter((r) => /\.(?:js|wasm)(?:\?|$)/.test(r.name))) {
    const response = await page.request.get(entry.name); assert.ok(response.ok());
    const body = await response.body();
    assert.equal(body.length, entry.decodedBodySize, 'ResourceTiming must agree with the actual asset');
    assets.push({ path: new URL(entry.name).pathname, bytes: body.length, sha256: createHash('sha256').update(body).digest('hex') });
  }
  const report = { schema: 'voxelshogi-initial-load-v1', checkedAtUtc: new Date().toISOString(), baseUrl,
    publishedCommit: buildInfo.commit, browser: browser.version(), userAgent: await page.evaluate(() => navigator.userAgent),
    initialView, selectedView: '2d', initialNetwork, after2dNetwork, assets,
    initialJsDecodedBytes: scripts.reduce((n, r) => n + r.decodedBodySize, 0),
    initialJsTransferredBytes: scripts.reduce((n, r) => n + r.transferSize, 0) };
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ output, publishedCommit: report.publishedCommit, initialView, initialJsDecodedBytes: report.initialJsDecodedBytes }, null, 2));
} finally { await browser.close(); }
