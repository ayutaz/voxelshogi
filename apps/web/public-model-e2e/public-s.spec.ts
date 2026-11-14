import { test, expect } from '../e2e/test';
import { openRecords, sliceAt } from '../e2e/arena-controls';
import { readFileSync } from 'node:fs';
import { loadWasm } from '../tests/loadWasm';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';

const catalog = JSON.parse(readFileSync(new URL('../public/models/m6/catalog.json', import.meta.url), 'utf8'));
loadWasm();

test.beforeEach(async ({ request }) => {
  if (process.env.E2E_COMMIT) {
    const response = await request.get('/build-info.json');
    expect(response.ok()).toBe(true);
    expect((await response.json()).commit).toBe(process.env.E2E_COMMIT);
  }
});

for (const precision of ['fp32', 'fp16', 'int8']) {
  test(`anonymous public S ${precision}: human move, real legal AI reply, verified format and mobile controls`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const downloads: string[] = [];
    page.on('request', request => {
      if (request.url().includes('huggingface.co/')) {
        expect(request.headers().authorization).toBeUndefined();
        if (request.url().endsWith('.onnx')) downloads.push(request.url());
      }
    });
    await page.goto('/');
    await page.getByRole('button', { name: 'AIと対戦', exact: true }).click();
    await page.getByLabel('相手のAI').selectOption('model');
    await expect(page.getByLabel('モデルの精度形式')).toBeVisible({ timeout: 60_000 });
    await page.getByLabel('モデルの精度形式').selectOption(precision);
    await page.getByRole('button', { name: '対戦をはじめる', exact: true }).click();
    await sliceAt(page, '4');
    await page.locator('.board2d [data-square="382"]').click();
    await page.locator('.board2d [data-square="373"]').click();
    await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番', { timeout: 120_000 });
    await expect(page.getByTestId('ai-phase')).toHaveText('人間の手番');
    await expect(page.getByTestId('ai-error')).toHaveCount(0);
    expect(downloads).toEqual([`https://huggingface.co/${catalog.releases[0].repo}/resolve/${catalog.releases[0].revision}/${precision}.onnx`]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const downloading = page.waitForEvent('download'); await openRecords(page);
    await page.getByTestId('export-ai-record').click();
    const download = await downloading;
    const record = JSON.parse(Buffer.concat(await (await download.createReadStream()).toArray()).toString('utf8'));
    expect(record.record.moves).toHaveLength(2);
    expect(record.observationsThroughCursor).toHaveLength(1);
    const reply = record.observationsThroughCursor[0].reply;
    expect(reply.kind).toBe('model-result');
    expect(reply.model).toMatchObject({ repo: catalog.releases[0].repo, revision: catalog.releases[0].revision, selection: { precision, backend: 'wasm', packageHash: catalog.releases[0].manifest.sha256 } });
    expect(reply.validation.fixtures).toHaveLength(4);
    expect(reply.validation.fixtures.every((f: { comparison: { policy: { exceeded: number }; value: { exceeded: number } } }) => f.comparison.policy.exceeded === 0 && f.comparison.value.exceeded === 0)).toBe(true);
    expect(reply.validation.profile.providers.CPUExecutionProvider).toBeGreaterThan(0);
    const game = Game.fromRecordJson(JSON.stringify(record.record)); expect(game.ply()).toBe(2); game.free();
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await page.screenshot({ path: info.outputPath(`attachments/public-s-${precision}.png`), fullPage: true });
  });
}

async function startAsWhite(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'AIと対戦', exact: true }).click();
  await page.getByLabel('あなたの先後').selectOption('r-h');
  await page.getByLabel('相手のAI').selectOption('model');
  await expect(page.getByLabel('モデルの精度形式')).toBeVisible({ timeout: 60_000 });
  await page.getByLabel('モデルの精度形式').selectOption('int8');
  await page.getByRole('button', { name: '対戦をはじめる', exact: true }).click();
}

test('public model download stays interactive and cancellation prevents a late move', async ({ page, context }) => {
  let release!: () => void, arrive!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const arrived = new Promise<void>(resolve => { arrive = resolve; });
  await context.route('**/resolve/*/int8.onnx', async route => { arrive(); await gate; await route.continue().catch(() => {}); });
  await startAsWhite(page); await arrived;
  await sliceAt(page, '5');
  await expect(page.getByTestId('slice-index')).toHaveValue('5');
  await page.getByTestId('toggle-run').click();
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  release(); await context.unroute('**/resolve/*/int8.onnx');
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

test('corrupt public weights show an error and never substitute Normal or an unverified move', async ({ page, context }) => {
  await context.route('**/resolve/*/int8.onnx', route => route.fulfill({ body: 'corrupt' }));
  await startAsWhite(page);
  await expect(page.getByTestId('ai-error')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await expect(page.getByTestId('ai-phase')).toHaveText('AIエラー');
});
