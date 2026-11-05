// Linux deep-CI only: exercise the real Worker message envelope, without models.
import assert from 'node:assert/strict';
import { createReadStream, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildResearchWorker } from './research-browser-probe.mjs';

assert.equal(process.platform, 'linux', 'real Worker execution requires external Linux');
const root = fileURLToPath(new URL('../', import.meta.url));
const folder = mkdtempSync(join(tmpdir(), 'voxelshogi-worker-channel-'));
let server, browser;
try {
  const worker = await buildResearchWorker(join(folder, 'bundle'));
  server = createServer((request, response) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (request.url === '/') { response.setHeader('Content-Type', 'text/html');response.end('<!doctype html><title>Private Worker envelope check</title>');return; }
    if (request.url === '/worker.mjs') { response.setHeader('Content-Type', 'text/javascript');createReadStream(worker).pipe(response);return; }
    response.statusCode = 404;response.end();
  });
  await new Promise((resolve, reject) => { server.once('error', reject);server.listen(0, '127.0.0.1', resolve); });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const require = createRequire(new URL('../apps/web/package.json', import.meta.url));
  const { chromium } = await import(pathToFileURL(join(dirname(require.resolve('@playwright/test')), 'index.mjs')).href);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext(), page = await context.newPage(), requests = [];
  context.on('request', request => requests.push(request.url()));
  await page.goto(origin);
  const result = await page.evaluate(() => new Promise((resolve, reject) => {
    const worker = new Worker('/worker.mjs', { type: 'module' });
    const timer = setTimeout(() => { worker.terminate();reject(new Error('Worker channel timeout')); }, 30000);
    worker.onerror = error => { clearTimeout(timer);worker.terminate();reject(new Error(error.message)); };
    worker.onmessage = event => { clearTimeout(timer);worker.terminate();resolve(event.data); };
    worker.postMessage({ name: 'full', backend: 'wasm', plan: {} });
  }));
  assert.equal(result.status, 'failed');
  assert.equal(result.stage, 'input', 'legitimate private channel must reach input validation');
  assert.match(result.error_message, /invalid untrained research origin/);
  assert.ok(requests.every(url => new URL(url).origin === origin));
  assert.ok(requests.every(url => ['/', '/worker.mjs', '/favicon.ico'].includes(new URL(url).pathname)), 'no runtime/model/fixture payload may be loaded');
  await context.close();
  console.log(JSON.stringify({ schema: 'voxelshogi-research-worker-channel-smoke-v1', passed: true, actual_browser: browser.version(), accepted_owner_channel: true, expected_invalid_plan_rejected: true, model_or_runtime_payloads_requested: 0, scope: 'Real dedicated Worker envelope only; not M inference, numerical accuracy, GPU or performance evidence' }));
} finally {
  await browser?.close();
  if (server?.listening) await new Promise(resolve => server.close(resolve));
  rmSync(folder, { recursive: true, force: true });
}
