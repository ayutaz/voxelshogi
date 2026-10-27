import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import os from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { browserMemory } from './browser-memory.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../apps/web/package.json', import.meta.url));
export const modelSwitchVariants = count => Array.from({ length: count }, (_, i) => ['fp32', 'fp16', 'int8'][(i + 1) % 3]);
const summary = values => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? { count: sorted.length, median: (sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.ceil((sorted.length - 1) / 2)]) / 2, p95: sorted[Math.ceil(sorted.length * .95) - 1], max: sorted.at(-1) } : null;
};

async function observe(page) {
  await page.addInitScript(() => {
    const probe = window.modelMeasurement = { gaps: [], inputs: [], draws: 0, last: null };
    const running = () => document.querySelector('[data-testid="inference-phase"]')?.dataset.phase === 'running';
    const tick = at => { if (running() && probe.last !== null) probe.gaps.push(at - probe.last); probe.last = running() ? at : null; requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    for (const kind of ['pointerdown', 'pointermove', 'pointerup']) window.addEventListener(kind, e => {
      if (e.target instanceof HTMLCanvasElement) probe.inputs.push({ kind, at: performance.now(), running: running(), trusted: e.isTrusted });
    }, true);
    const draw = WebGL2RenderingContext.prototype.drawElementsInstanced;
    WebGL2RenderingContext.prototype.drawElementsInstanced = function (...args) { const result = draw.apply(this, args); if (running()) probe.draws++; return result; };
  });
}

async function execute(page, iterations) {
  await page.getByRole('button', { name: iterations === 40 ? '30回を計測' : '推論を実行', exact: true }).click();
  await page.waitForFunction(() => ['done', 'error'].includes(document.querySelector('[data-testid="inference-phase"]')?.dataset.phase), null, { timeout: 120_000 });
  const alert = page.getByRole('alert'), error = await alert.count() ? await alert.textContent() : null;
  if (error) throw new Error(error);
  return JSON.parse(await page.getByTestId('inference-json').textContent());
}

async function main() {
  const args = process.argv.slice(2), smoke = args.includes('--smoke'), switchesOnly = args.includes('--switches-only');
  assert.ok(!(smoke && switchesOnly) && args.filter(a => !a.startsWith('--')).length <= 1 && args.every(a => ['--smoke', '--switches-only'].includes(a) || !a.startsWith('--')), 'usage: node scripts/measure-browser-models.mjs [--smoke|--switches-only] [OUTPUT.json]');
  const output = resolve(root, args.find(a => !a.startsWith('--')) ?? 'runs/m3/browser-measurement.json');
  const base = process.env.M3_BASE_URL ?? 'http://localhost:4173';
  const { chromium, expect } = await import(pathToFileURL(resolve(dirname(require.resolve('@playwright/test')), 'index.mjs')).href);
  const browser = await chromium.launch({ channel: 'chrome', args: ['--enable-precise-memory-info'] });
  const browserCdp = await browser.newBrowserCDPSession();
  const report = { schema: 1, smoke, mode: switchesOnly ? 'switches-only' : smoke ? 'smoke' : 'full', complete: false, startedAt: new Date().toISOString(), base,
    measurementSource: { commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), dirty: Boolean(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim()) },
    machine: { platform: os.platform(), release: os.release(), architecture: os.arch(), cpu: os.cpus()[0].model, memoryBytes: os.totalmem(), chrome: browser.version() },
    method: { batch: 1, batch8: { status: 'not-applicable', reason: 'this exact ONNX export has fixed batch=1' }, warmup: 10, measured: 30,
      cold: 'new browser context and Worker; OS and driver shader caches are uncontrolled', reuse: 'same Worker/runtime; each request creates/releases its session and tensors',
      memory: 'sample dedicated browser RSS and main JS heap once per second during repeat; observed maxima, not guaranteed peaks', maximumSamplingGapMs: 5000,
      idleSleep: os.platform() === 'darwin' ? 'caffeinate -i only while this measurement process is alive' : 'not applicable', gpuCompletion: 'await CPU output readback before stopping the inference timer',
      display: 'real demo 3D on/off; a trusted camera drag during the repeated inference triggers real demand frames' }, rows: [], switches: [], errors: [] };
  const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
  const awake = os.platform() === 'darwin' ? spawn('/usr/bin/caffeinate', ['-i', '-w', String(process.pid)], { stdio: 'ignore' }) : null;
  awake?.unref();
  awake?.on('error', error => { report.errors.push(`idle-sleep assertion failed: ${String(error)}`); });
  let requiredFailure = false;
  try {
    const context = await browser.newContext(), page = await context.newPage(); await page.goto(base + '/?models=1');
    await expect(page.getByRole('button', { name: '推論を実行', exact: true })).toBeVisible({ timeout: 30_000 });
    report.build = await (await context.request.get(base + '/build-info.json')).json();
    report.deployment = await (await context.request.get(base + '/models/m3/index.json')).json();
    report.model = await (await context.request.get(new URL(report.deployment.model.path, base + '/models/m3/').href)).json();
    report.browser = await page.evaluate(() => ({ userAgent: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency, deviceMemoryGiB: navigator.deviceMemory, webgpu: Boolean(navigator.gpu) }));
    assert.deepEqual(report.model.variants.map(v => v.id), ['fp32', 'fp16', 'int8']);
    await context.close();
    for (const show3D of switchesOnly ? [] : smoke ? [true] : [false, true]) for (const backend of smoke ? ['webgpu'] : ['wasm', 'webgpu']) for (const variant of smoke ? ['fp32'] : ['fp32', 'fp16', 'int8']) for (const fixture of smoke ? report.model.fixtures.slice(0, 1) : report.model.fixtures) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } }), page = await context.newPage();
      await observe(page);
      const row = { show3D, backend, variant, fixture: fixture.name, status: 'running', memory: [], samplingErrors: [] };
      report.rows.push(row); save();
      let timer, sampleBusy = false;
      try {
        await page.goto(base + '/?models=1');
        await page.getByLabel('3D表示').setChecked(show3D);
        if (show3D) await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
        await page.getByLabel('実行先').selectOption(backend); await page.getByLabel('精度形式').selectOption(variant); await page.getByLabel('検証局面').selectOption(fixture.name);
        row.memory.push({ stage: 'before', ...await browserMemory(browserCdp, page) });
        row.first = await execute(page, 1);
        assert.equal(row.first.request.packageHash, report.deployment.model.sha256, 'package changed during measurement');
        await page.evaluate(() => Object.assign(window.modelMeasurement, { gaps: [], inputs: [], draws: 0, last: null }));
        const samples = async () => { if (sampleBusy) return; sampleBusy = true; try { row.memory.push({ stage: 'repeat', ...await browserMemory(browserCdp, page) }); } catch (e) { row.samplingErrors.push(String(e)); } finally { sampleBusy = false; } };
        timer = setInterval(() => void samples(), 1000);
        const repetition = execute(page, 40);
        void repetition.catch(() => {}); // observed below, including failures during input
        if (show3D) {
          await page.waitForFunction(() => document.querySelector('[data-testid="inference-phase"]')?.dataset.phase === 'running', null, { timeout: 120_000 });
          const box = await page.getByTestId('board3d').boundingBox();
          await page.mouse.move(box.x + box.width * .4, box.y + box.height * .4); await page.mouse.down();
          await page.mouse.move(box.x + box.width * .6, box.y + box.height * .6, { steps: 6 }); await page.mouse.up();
        }
        row.repeat = await repetition;
        clearInterval(timer); timer = null;
        while (sampleBusy) await new Promise(resolve => setTimeout(resolve, 20));
        row.memory.push({ stage: 'after-session-release', ...await browserMemory(browserCdp, page) });
        const probe = await page.evaluate(() => window.modelMeasurement);
        row.display = { frameGapsMs: summary(probe.gaps), drawsDuringInference: probe.draws, inputs: probe.inputs };
        const memoryTicks = row.memory.filter(m => m.stage === 'repeat').map(m => Date.parse(m.at));
        row.samplingGapMs = memoryTicks.length > 1 ? Math.max(...memoryTicks.slice(1).map((at, i) => at - memoryTicks[i])) : null;
        assert.ok(row.samplingGapMs === null || row.samplingGapMs <= report.method.maximumSamplingGapMs, 'measurement interrupted: memory sampling gap exceeded five seconds');
        if (show3D) { assert.ok(probe.draws > 0, 'no real draw during model inference'); assert.ok(probe.inputs.some(e => e.kind === 'pointerdown' && e.running && e.trusted), 'no real input during model inference'); }
        assert.equal(row.samplingErrors.length, 0, 'memory sampling failed');
        assert.equal(row.repeat.metrics.samples.length, 30); assert.equal(row.repeat.comparison.policy.exceeded, 0);
        assert.equal(row.repeat.comparison.policy.elements, 1_067_985);
        assert.equal(row.repeat.information.backend, backend);
        assert.equal(row.repeat.request.packageHash, report.deployment.model.sha256, 'package changed during measurement');
        row.status = 'passed';
      } catch (e) {
        row.error = String(e);
        row.status = backend === 'webgpu' && variant === 'fp16' && /outputs exceed fp16 tolerance/.test(row.error) ? 'numeric-rejected' : 'failed';
        if (row.status === 'failed') requiredFailure = true;
      } finally {
        if (timer) clearInterval(timer);
        while (sampleBusy) await new Promise(resolve => setTimeout(resolve, 20));
        await context.close(); row.afterWorkerClose = await browserMemory(browserCdp);
        save(); console.log(JSON.stringify({ stage: 'measurement', show3D, backend, variant, fixture: fixture.name, status: row.status, medianMs: row.repeat?.metrics.medianMs, error: row.error }));
      }
    }
    const context2 = await browser.newContext({ viewport: { width: 1440, height: 1100 } }), page2 = await context2.newPage();
    const live = new Set(), lifecycle = { created: 0, closed: 0 };
    page2.on('worker', worker => { lifecycle.created++; live.add(worker); worker.on('close', () => { lifecycle.closed++; live.delete(worker); }); });
    await observe(page2); await page2.goto(base + '/?models=1'); await expect(page2.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
    const baseline = await execute(page2, 1);
    assert.equal(baseline.request.variant, 'fp32');
    assert.equal(baseline.request.packageHash, report.deployment.model.sha256);
    report.switchBaseline = { result: baseline, workers: { ...lifecycle, live: live.size } };
    const variants = modelSwitchVariants(smoke ? 2 : 20);
    for (let i = 0; i < variants.length; i++) {
      const variant = variants[i];
      await page2.getByLabel('精度形式').selectOption(variant);
      const result = await execute(page2, 1);
      assert.equal(result.request.variant, variant);
      assert.notEqual(result.request.variant, report.switches.at(-1)?.variant ?? baseline.request.variant, 'each switch must change the model');
      assert.equal(result.request.packageHash, report.deployment.model.sha256);
      assert.ok(live.size <= 1, 'obsolete model Worker remains alive');
      report.switches.push({ iteration: i + 1, variant, workers: { ...lifecycle, live: live.size }, result, memory: await browserMemory(browserCdp, page2) }); save();
    }
    await context2.close(); assert.equal(live.size, 0); assert.equal(lifecycle.created, lifecycle.closed);
    report.switchLifecycle = { ...lifecycle, live: live.size, afterClose: await browserMemory(browserCdp) };
    assert.equal(report.rows.length, switchesOnly ? 0 : smoke ? 1 : 48); assert.equal(report.switches.length, smoke ? 2 : 20);
    report.switchesComplete = !smoke && report.switches.length === 20 && live.size === 0;
    report.complete = !smoke && !switchesOnly && !requiredFailure; report.finishedAt = new Date().toISOString(); save();
    if (requiredFailure) process.exitCode = 1;
  } catch (e) { report.errors.push(String(e)); save(); throw e; }
  finally { await browserCdp.detach(); await browser.close(); awake?.kill(); }
}
if (import.meta.url === pathToFileURL(process.argv[1]).href) await main();
