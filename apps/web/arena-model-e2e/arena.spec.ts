import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loadWasm } from '../tests/loadWasm';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';
import type { AiObservation } from '../src/ai/arena-record';
import type { Precision } from '../src/inference/manifest';
import { installInteractionProbe, readInteractionProbe } from '../e2e/interaction-probe';

// CI uses a private synthetic fixture. External Linux may select a hash-verified real HF release.
const fixture = resolve(process.env.M6_MODEL_FIXTURE ?? '../../runs/m6/browser-fixture');
const catalog = JSON.parse(readFileSync(resolve(fixture, 'catalog.json'), 'utf8')) as { releases: { id: string; manifest: { sha256: string } }[] };
loadWasm();
test.afterEach(async ({ page }, info) => {
  if (info.status !== info.expectedStatus) console.info('Arena model failure:', JSON.stringify(await page.evaluate(() => ({
    status: document.querySelector('[data-testid="status"]')?.textContent ?? null,
    phase: document.querySelector('[data-testid="ai-phase"]')?.textContent ?? null,
    error: document.querySelector('[data-testid="ai-error"]')?.textContent ?? null,
  })).catch(() => ({ pageClosed: true }))));
});
async function prepare(page: Page, context: BrowserContext, folder = 'model') {
  await context.route('**/models/m6/catalog.json', route => route.fulfill({ json: catalog }));
  await page.goto('/');
  await page.getByRole('button', { name: '学習済みモデルを読み込む', exact: true }).click();
  await page.getByTestId('model-folder').setInputFiles(resolve(fixture, folder));
  await expect(page.getByText(/フォルダーを追加しました/)).toBeVisible();
  for (const side of ['b', 'w']) await page.getByTestId(`difficulty-${side}`).selectOption('model');
}
async function saved(page: Page) {
  const downloading = page.waitForEvent('download');
  await page.getByTestId('export-ai-record').click();
  const download = await downloading;
  const json = Buffer.concat(await (await download.createReadStream()).toArray()).toString('utf8');
  return JSON.parse(json) as { applicationCommit: string; record: { moves: string[] }; viewCursor: number; observationsThroughCursor: AiObservation[];
    selectedAgents: { b: { model: { selection: { precision: Precision; backend: string } } }; w: { model: { selection: { precision: Precision; backend: string } } } } };
}

for (const [black, white] of [['fp32', 'fp16'], ['fp16', 'int8'], ['int8', 'fp32']] as const) {
  test(`actual ${black}/${white} local models play legal moves with same-format validation and saved conditions`, async ({ page, context }) => {
    const errors: string[] = [], modelDownloads: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    context.on('request', request => { if (request.url().includes('/models/m3/models/')) modelDownloads.push(request.url()); });
    await prepare(page, context);
    await page.getByTestId('precision-b').selectOption(black);
    await page.getByTestId('precision-w').selectOption(white);
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 60_000 });
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番', { timeout: 60_000 });
    await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
    const value = await saved(page);
    expect(value.applicationCommit).toMatch(/^[0-9a-f]{40}$/);
    expect(value.selectedAgents.b.model.selection).toMatchObject({ precision: black, backend: 'wasm' });
    expect(value.selectedAgents.w.model.selection).toMatchObject({ precision: white, backend: 'wasm' });
    expect(value.observationsThroughCursor).toHaveLength(2);
    for (const [index, observation] of value.observationsThroughCursor.entries()) {
      expect(observation.root).toMatchObject({ cursor: index, side: index === 0 ? 'b' : 'w' });
      const reply = observation.reply;
      if (reply.kind !== 'model-result') throw new Error('unexpected baseline fallback');
      expect(reply.model.selection).toMatchObject({ precision: index === 0 ? black : white, backend: 'wasm', packageHash: catalog.releases[0]!.manifest.sha256 });
      expect(reply.result.bestMove).toBe(value.record.moves[index]);
      expect(reply.validation.fixtures.map(item => item.name)).toEqual(['initial-b', 'after-one-w', 'mate-in-one-b', 'material-b']);
      expect(reply.validation.fixtures.every(item => item.comparison.policy.exceeded === 0 && item.comparison.value.exceeded === 0)).toBe(true);
      expect(Object.keys(reply.validation.profile.providers)).toEqual(['CPUExecutionProvider']);
      expect(reply.validation.profile.providers.CPUExecutionProvider).toBeGreaterThan(0);
      expect(reply.inferenceMs).toBeGreaterThan(0);
      expect(Number.isFinite(reply.result.value)).toBe(true);
    }
    const reference = readFileSync(resolve(fixture, 'model/reference', black, 'initial-b-value.f32')).readFloatLE();
    const first = value.observationsThroughCursor[0]!.reply;
    if (first.kind !== 'model-result') throw new Error('expected model');
    expect(Math.abs(first.result.value! - reference)).toBeLessThan(black === 'fp16' ? 0.01 : 0.0001);
    const verified = Game.fromRecordJson(JSON.stringify(value.record));
    try { expect(verified.moveCount()).toBe(2); } finally { verified.free(); }
    if (black === 'fp32') {
      await page.getByTestId('move-delay').fill('50');
      await page.getByTestId('toggle-run').click();
      // The list also includes one row for the initial position.
      await expect.poll(() => page.getByTestId('move-list').locator('li').count(), { timeout: 60_000 }).toBeGreaterThanOrEqual(5);
      await page.getByTestId('toggle-run').click();
      await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
      const automatic = await saved(page);
      expect(automatic.observationsThroughCursor.length).toBeGreaterThanOrEqual(4);
      const replay = Game.fromRecordJson(JSON.stringify(automatic.record));
      try { expect(replay.moveCount()).toBeGreaterThanOrEqual(4); } finally { replay.free(); }
    }
    expect(modelDownloads).toEqual([]); expect(errors).toEqual([]);
  });
}

test('model preparation keeps 3D controls responsive and cancellation prevents a late move', async ({ page, context }) => {
  await installInteractionProbe(page);
  await prepare(page, context);
  await page.getByRole('button', { name: '3D+2D', exact: true }).click();
  await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
  // Hold first module loading, not an inference reply: this measures preparation
  // responsiveness/cancellation, never simultaneous kernel/GPU performance.
  let release!: () => void, reached!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const arrival = new Promise<void>(resolve => { reached = resolve; });
  const pattern = '**/assets/policy.worker-*.js';
  await context.route(pattern, async route => { reached(); await gate; await route.continue().catch(() => {}); });
  await page.getByTestId('ai-step').click(); await arrival;
  await page.getByTestId('slice-index').fill('5');
  await expect(page.getByTestId('slice-index')).toHaveValue('5');
  await page.getByTestId('move-delay').fill('100');
  await expect(page.getByTestId('ai-phase')).toHaveText(/モデル準備・思考中/);
  await page.evaluate(() => window.interactionProbe.armCamera());
  const canvas = page.getByTestId('board3d').locator('canvas');
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * .4, box.y + box.height * .4);
  await page.mouse.down(); await page.mouse.move(box.x + box.width * .6, box.y + box.height * .6, { steps: 4 }); await page.mouse.up();
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  expect((await readInteractionProbe(page)).camera).toMatchObject({ pending: true, trusted: true });
  release(); await context.unroute(pattern);
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await page.getByTestId('precision-b').selectOption('int8');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 60_000 });
});

test('a changed local ONNX is rejected after metadata loading without making a move', async ({ page, context }) => {
  await prepare(page, context, 'corrupted');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('ai-error')).toContainText(/hash/i, { timeout: 60_000 });
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  expect((await saved(page)).observationsThroughCursor).toEqual([]);
});

test('an unavailable GPU is explicit and the chosen WASM model can play human versus AI', async ({ page, context }) => {
  await context.route('**/assets/policy.worker-*.js', async route => {
    const response = await route.fetch();
    await route.fulfill({ status: 200, contentType: 'text/javascript', body: 'Object.defineProperty(navigator,"gpu",{value:undefined});\n' + await response.text() });
  });
  await prepare(page, context);
  await page.getByTestId('backend-b').selectOption('webgpu');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('ai-error')).toContainText('WebGPU is not available', { timeout: 60_000 });
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await page.getByTestId('backend-b').selectOption('wasm');
  await page.getByTestId('mode').selectOption('r-h');
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 60_000 });
  await expect(page.getByTestId('ai-phase')).toHaveText('人間の手番');
  await expect(page.getByTestId('ai-step')).toBeDisabled();
  const value = await saved(page);
  expect(value.observationsThroughCursor).toHaveLength(1);
  expect(value.observationsThroughCursor[0]!.reply.kind).toBe('model-result');
});
