// Run only on an admitted external Linux host. Never serves outside loopback.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import os from 'node:os';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { browserMemory } from './browser-memory.mjs';
import { researchBrowserCases, requireLinux, validateBrowserInputs, validateProvider } from './research-browser-contract.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
async function digest(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
export async function measureResearch(inputDirectory, outputFile) {
  requireLinux(process.platform);
  assert.equal(process.versions.node, readFileSync(resolve(root, '.node-version'), 'utf8').trim(), 'use pinned Node version');
  const input = realpathSync(inputDirectory), output = resolve(outputFile);
  assert.ok(!existsSync(output), 'use a fresh result file; do not overwrite a prior attempt');
  assert.equal(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(), '', 'clean admitted browser source required');
  const source = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
  const planBytes = readFileSync(resolve(input, 'browser-inputs.json')), plan = JSON.parse(planBytes);
  validateBrowserInputs(plan);
  const files = new Map();
  for (const model of plan.models) for (const descriptor of [model.model, ...model.fixtures.flatMap(f => [f.features, f.policy, f.value])]) {
    const file = realpathSync(resolve(input, descriptor.path));
    assert.ok(!relative(input, file).startsWith('..'), 'research payload escapes staging');
    assert.equal(await digest(file), descriptor.sha256, 'research payload hash changed');
    assert.equal(readFileSync(file).byteLength, descriptor.bytes, 'research payload size changed');
    files.set('/payload/' + descriptor.path, { file, type: 'application/octet-stream' });
  }
  const runtimeDirectory = resolve(root, 'apps/web/node_modules/onnxruntime-web');
  assert.equal(JSON.parse(readFileSync(resolve(runtimeDirectory, 'package.json'))).version, '1.31.1');
  const runtime = { version: '1.31.1' };
  function runtimeFile(name, sourceFile) {
    const bytes = readFileSync(sourceFile), path = 'runtime/' + name;
    files.set('/payload/' + path, { file: sourceFile, type: name.endsWith('.mjs') ? 'text/javascript' : 'application/octet-stream' });
    return { path, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  }
  runtime.bundle = runtimeFile('ort.webgpu.bundle.min.mjs', resolve(runtimeDirectory, 'dist/ort.webgpu.bundle.min.mjs'));
  runtime.bootstrap = runtimeFile('ort-wasm-simd-threaded.asyncify.mjs', resolve(runtimeDirectory, 'dist/ort-wasm-simd-threaded.asyncify.mjs'));
  const wasm = runtimeFile('ort-wasm-simd-threaded.asyncify.wasm', resolve(runtimeDirectory, 'dist/ort-wasm-simd-threaded.asyncify.wasm'));
  runtime.wasm = { ...wasm, parts: [wasm] };
  const notices = existsSync(resolve(runtimeDirectory, 'LICENSE')) ? runtimeDirectory : resolve(root, 'third_party/onnxruntime-1.31.1');
  runtime.notices = ['LICENSE', 'ThirdPartyNotices.txt'].map(n => runtimeFile(n, resolve(notices, n)));
  const require = createRequire(resolve(root, 'apps/web/package.json'));
  const { build } = await import(pathToFileURL(require.resolve('vite')).href);
  const bundles = resolve(dirname(output), 'worker-' + source.slice(0, 12));
  assert.ok(!existsSync(bundles), 'use a fresh worker build directory');
  await build({ configFile: false, root, logLevel: 'warn', build: { outDir: bundles, emptyOutDir: false, minify: false, lib: { entry: resolve(root, 'scripts/research-browser-worker.mjs'), formats: ['es'], fileName: () => 'worker.mjs' } } });
  files.set('/worker.mjs', { file: resolve(bundles, 'worker.mjs'), type: 'text/javascript' });
  const server = createServer((request, response) => {
    const item = files.get(new URL(request.url, 'http://127.0.0.1').pathname);
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (request.url === '/') { response.setHeader('Content-Type', 'text/html');response.end('<!doctype html><meta charset="utf-8"><title>Private research probe</title>');return; }
    if (!item) { response.statusCode = 404;response.end();return; }
    response.setHeader('Content-Type', item.type);createReadStream(item.file).pipe(response);
  });
  const report = { schema: 'voxelshogi-research-browser-results-v1', complete: false, matrix_complete: false,
    application_commit: source, model_source_commit: plan.model_source_commit, origin: plan.origin,
    input_sha256: createHash('sha256').update(planBytes).digest('hex'), runtime, rows: [],
    method: { warmup_steps: 8, measured_steps: 32, fixtures: [0, 3], numeric: plan.numeric, scope: 'untrained operator ONNX only; actual browser and provider profile; no arena rendering, physical mobile or learned strength evidence', memory: 'browser process RSS before/after cases; not peak memory', gpu_timing: 'includes CPU output readback and GPU queue completion', cold: 'fresh context and Worker; OS/driver caches uncontrolled' },
    machine: { platform: process.platform, release: os.release(), cpu: os.cpus()[0].model, memory_bytes: os.totalmem() } };
  const save = () => { mkdirSync(dirname(output), { recursive: true });writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
  let browser;
  try {
    await new Promise((resolve, reject) => { server.once('error', reject);server.listen(0, '127.0.0.1', resolve); });
    const base = `http://127.0.0.1:${server.address().port}`;
    const { chromium } = await import(pathToFileURL(resolve(dirname(require.resolve('@playwright/test')), 'index.mjs')).href);
    const launchOptions = { channel: process.env.PW_CHANNEL || undefined, headless: true, args: ['--no-sandbox', '--enable-gpu', '--use-angle=vulkan', '--enable-features=Vulkan', '--disable-vulkan-surface', '--enable-unsafe-webgpu', '--enable-precise-memory-info'] };
    report.launch_options = launchOptions;
    browser = await chromium.launch(launchOptions);
    report.browser = browser.version();
    const cdp = await browser.newBrowserCDPSession();
    for (const testCase of researchBrowserCases()) {
      const context = await browser.newContext(), page = await context.newPage();
      const row = { ...testCase, status: 'running' };report.rows.push(row);save();
      try {
        await page.goto(base);
        row.before = await browserMemory(cdp, page);
        const result = await page.evaluate(data => new Promise((resolve, reject) => {
          const worker = new Worker('/worker.mjs', { type: 'module' });
          const timer = setTimeout(() => { worker.terminate();reject(new Error('research case timed out')); }, 180000);
          worker.onmessage = ({ data }) => { clearTimeout(timer);worker.terminate();resolve(data); };
          worker.onerror = error => { clearTimeout(timer);worker.terminate();reject(new Error(error.message)); };
          worker.postMessage(data);
        }), { ...testCase, plan, runtime: { assetBase: base + '/payload/', index: { runtime } } });
        Object.assign(row, result);
        if (row.status === 'success') {
          validateProvider(row);
          assert.equal(row.session_released, true);
          assert.deepEqual(row.fixtures.map(f => f.id), [0, 3]);
          for (const fixture of row.fixtures) {
            assert.equal(fixture.samples_ms.length, 32);assert.equal(fixture.warmup_steps, 8);
            assert.ok(fixture.samples_ms.every(n => Number.isFinite(n) && n >= 0));
            assert.equal(fixture.comparisons.policy.elements, 1067985);assert.equal(fixture.comparisons.value.elements, 1);
            assert.equal(fixture.comparisons.policy.exceeded, 0);assert.equal(fixture.comparisons.value.exceeded, 0);
          }
        }
      } catch (error) { row.status = 'failed';row.error_message = String(error.message).slice(0, 1024); }
      finally { await context.close();row.after_worker_close = await browserMemory(cdp);save(); }
    }
    report.matrix_complete = report.rows.length === 8 && report.rows.every(r => ['success', 'failed'].includes(r.status));
    report.complete = report.matrix_complete && report.rows.every(r => r.status === 'success');
    report.wasm_supported = report.rows.filter(r => r.backend === 'wasm' && r.status === 'success').map(r => r.name);
    report.webgpu_supported = report.rows.filter(r => r.backend === 'webgpu' && r.status === 'success').map(r => r.name);
    await cdp.detach();return report;
  } catch (error) { report.error = String(error.message).slice(0, 1024);throw error; }
  finally { await browser?.close();await new Promise(resolve => server.close(resolve));save(); }
}
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  assert.equal(process.argv.length, 4, 'usage: node scripts/research-browser-probe.mjs INPUT_DIRECTORY FRESH_RESULT.json');
  const result = await measureResearch(process.argv[2], process.argv[3]);
  console.log(JSON.stringify({ matrix_complete: result.matrix_complete, complete: result.complete, wasm_supported: result.wasm_supported, webgpu_supported: result.webgpu_supported }));
  if (!result.matrix_complete || result.wasm_supported.length !== 4) process.exitCode = 1;
}
