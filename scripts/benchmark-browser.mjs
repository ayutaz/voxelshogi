// Real Mac/Chrome measurement, deliberately not a CI wall-clock performance gate.
// Build first, then: node scripts/benchmark-browser.mjs runs/m2/browser.json
// M2_BENCH_BASE_URL selects a published build; otherwise starts a local preview.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { cpus, platform, release, totalmem } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const sourceCommit = git('rev-parse', 'HEAD');
const dirty = git('status', '--porcelain').length > 0;
assert.ok(!dirty || process.env.M2_BENCH_ALLOW_DIRTY === '1', 'Commit runtime changes before a final measurement (or explicitly allow a labelled development measurement)');
const expectedCommit = process.env.M2_BENCH_COMMIT ?? sourceCommit;
const runtimePaths = git('ls-files', '--cached', '--others', '--exclude-standard').split('\n').filter((path) => /^(Cargo\.(toml|lock)|rust-toolchain\.toml|crates\/|apps\/web\/(src\/|package\.json|pnpm-lock\.yaml|vite\.config\.ts))/.test(path));
const sourceFiles = runtimePaths.sort().map((path) => ({ path, sha256: sha256(readFileSync(resolve(root, path))) }));
const output = resolve(root, process.argv[2] ?? 'runs/m2/browser.json');
mkdirSync(dirname(output), { recursive: true });

const { chromium } = await import('../apps/web/node_modules/@playwright/test/index.mjs');
const { Game, initSync } = await import('../apps/web/src/wasm/pkg/voxelshogi_wasm.js');
initSync({ module: readFileSync(new URL('../apps/web/src/wasm/pkg/voxelshogi_wasm_bg.wasm', import.meta.url)) });
const fixtures = JSON.parse(readFileSync(new URL('../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8'));
const startGame = new Game();
const initial = startGame.recordJson();
startGame.play('577567'); startGame.play('533543');
const afterTwo = startGame.recordJson(); startGame.free();
const inputs = [
  ...[1, 2, 3].map((n) => ({ name: `initial-${n}`, recordJson: initial })),
  { name: 'after-two-plies', recordJson: afterTwo },
  { name: 'capture-promotion', recordJson: JSON.stringify(fixtures.find((f) => f.name === 'mate-in-one-b').record) },
  { name: 'pieces-in-hand', recordJson: JSON.stringify(fixtures.find((f) => f.name === 'material-b').record) },
  { name: 'history-with-redo', recordJson: JSON.stringify(fixtures.find((f) => f.name === 'repetition-b').record), cursor: 8 },
].map((r, i) => {
  const g = Game.fromRecordJson(r.recordJson);
  try {
    const cursor = r.cursor ?? g.ply(); g.goto(cursor);
    return { ...r, schema: 1, kind: 'search', requestId: i + 1, revision: i, ruleset: 'voxelshogi-standard-v1',
      cursor, hash: g.hash(), side: g.sideToMove(), difficulty: 'normal', seed: 42,
      limits: { maxDepth: 6, maxNodes: 50_000, maxTimeMs: 1000 } };
  } finally { g.free(); }
});

let server, browser;
try {
  const baseUrl = process.env.M2_BENCH_BASE_URL ?? 'http://localhost:4184';
  if (!process.env.M2_BENCH_BASE_URL) {
    server = spawn(process.execPath, [resolve(root, 'apps/web/node_modules/vite/bin/vite.js'), 'preview', '--port', '4184', '--strictPort'], { cwd: resolve(root, 'apps/web'), stdio: ['ignore', 'pipe', 'pipe'] });
    await new Promise((resolveReady, reject) => {
      server.stdout.on('data', (data) => { if (String(data).includes('4184')) resolveReady(); });
      server.once('error', reject);
      server.once('exit', (code) => reject(new Error(`preview exited: ${code}`)));
    });
  }
  browser = await chromium.launch({ channel: 'chrome' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const buildInfo = await (await page.request.get(`${baseUrl}/build-info.json`)).json();
  assert.equal(buildInfo.commit, expectedCommit, 'Measure the intended build');
  await page.goto(baseUrl);
  await page.getByTestId('status').waitFor();
  const resources = () => page.evaluate(() => performance.getEntriesByType('resource').map((entry) => entry.toJSON()));
  const initialNetwork = await resources();
  const initialScripts = initialNetwork.filter((entry) => /\.js(?:\?|$)/.test(entry.name));
  assert.ok(initialScripts.length > 0, 'must measure actual script requests');
  assert.ok(!initialScripts.some((entry) => /Board3D-/.test(entry.name)), '2D initial load must defer 3D');
  const entryUrl = initialScripts.find((entry) => /\/index-/.test(entry.name)).name;
  const entry = await (await page.request.get(entryUrl)).text();
  const workerFile = entry.match(/search\.worker-[a-zA-Z0-9_-]+\.js/)?.[0];
  assert.ok(workerFile, 'production entry must reference a Worker chunk');
  const workerUrl = new URL(workerFile, entryUrl).href;
  await page.getByRole('button', { name: '3D+2D', exact: true }).click();
  await page.getByTestId('board3d').locator('canvas').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="board3d"]')?.getAttribute('data-ready') === 'true');
  const after3dNetwork = await resources();
  assert.ok(after3dNetwork.some((entry) => /Board3D-/.test(entry.name)), '3D must load on demand');
  await page.screenshot({ path: resolve(dirname(output), 'spectator.png'), fullPage: true });
  const browserProfiles = await page.evaluate(async ({ workerUrl, inputs }) => {
    const worker = new Worker(workerUrl, { type: 'module' });
    const profiles = [];
    try {
      for (const input of inputs) {
        const { name, ...request } = input;
        const start = performance.now();
        const reply = await new Promise((resolveReply, reject) => {
          worker.onmessage = ({ data }) => data.kind === 'result' ? resolveReply(data) : reject(new Error(JSON.stringify(data)));
          worker.onerror = (event) => reject(new Error(event.message || 'Worker failed'));
          worker.postMessage(request);
        });
        profiles.push({ name, ...reply, roundTripMs: performance.now() - start });
      }
      return profiles;
    } finally { worker.terminate(); }
  }, { workerUrl, inputs });
  const urls = [...new Set([...after3dNetwork.map((entry) => entry.name), workerUrl])].filter((url) => new URL(url).origin === new URL(baseUrl).origin && /\.(?:js|wasm)(?:\?|$)/.test(url));
  const assets = [];
  for (const url of urls) {
    const response = await page.request.get(url); assert.ok(response.ok());
    const bytes = await response.body();
    assets.push({ path: new URL(url).pathname, bytes: bytes.length, sha256: sha256(bytes), contentType: response.headers()['content-type'] });
  }
  const baseline = JSON.parse(readFileSync(new URL('../docs/experiments/documentation-baseline-2026-10-26.json', import.meta.url), 'utf8'));
  const records = [];
  for (const record of baseline.records) {
    const response = await page.request.get(new URL(record.path, baseUrl).href);
    assert.ok(response.ok());
    const bytes = await response.body();
    assert.equal(sha256(bytes), record.sha256, record.path);
    records.push({ path: record.path, bytes: bytes.length, sha256: sha256(bytes) });
  }
  const environment = { cpu: cpus()[0]?.model, memoryBytes: totalmem(), platform: platform(), osRelease: release(),
    browser: browser.version(), userAgent: await page.evaluate(() => navigator.userAgent), node: process.versions.node,
    graphics: await page.evaluate(() => {
      const gl = document.querySelector('[data-testid="board3d"] canvas')?.getContext('webgl2');
      const debug = gl?.getExtension('WEBGL_debug_renderer_info');
      return gl && debug ? { renderer: gl.getParameter(debug.UNMASKED_RENDERER_WEBGL), vendor: gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) } : null;
    }),
    rust: execFileSync('rustc', ['--version'], { encoding: 'utf8' }).trim() };
  await browser.close(); browser = undefined;
  // Close rendering before the native comparison, and exclude compilation from timings.
  const nativeProfiles = JSON.parse(execFileSync('cargo', ['run', '--quiet', '--release', '--locked', '-p', 'voxelshogi-wasm', '--example', 'search_profiles'], {
    cwd: root, encoding: 'utf8', input: JSON.stringify(inputs), maxBuffer: 8 * 1024 * 1024,
  }));
  const initialJsBytes = initialScripts.reduce((total, entry) => total + entry.decodedBodySize, 0);
  assert.ok(initialJsBytes > 0, 'resource byte sizes must be available');
  const report = { schema: 'voxelshogi-m2-browser-v1', checkedAtUtc: new Date().toISOString(), sourceCommit, dirty,
    runtimeFingerprint: sha256(JSON.stringify(sourceFiles)), sourceFiles, baseUrl, publishedCommit: buildInfo.commit, environment,
    settings: { concurrent3dRendering: true, workerReuse: true, limits: inputs[0].limits },
    initialNetwork, after3dNetwork, assets, records, inputs, browserProfiles, nativeProfiles,
    sizeComparison: { baselineCommit: baseline.sourceCommit, baselineEntryJsBytes: baseline.assets.find((asset) => asset.path === baseline.entryJs).bytes,
      actualInitialJsBytes: initialJsBytes, actualInitialJsTransferredBytes: initialScripts.reduce((total, entry) => total + entry.transferSize, 0) } };
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ output, sourceCommit, dirty, initialJsBytes,
    profiles: browserProfiles.map((r) => ({ name: r.name, depth: r.result.completedDepth, nodes: r.result.nodes, ...r.metrics, roundTripMs: r.roundTripMs })) }, null, 2));
} finally { await browser?.close(); server?.kill('SIGTERM'); }
