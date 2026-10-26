import { expect, test } from '@playwright/test';
import { loadWasm } from '../tests/loadWasm';
import { Game } from '../src/wasm/pkg/voxelshogi_wasm.js';

loadWasm();

test('spectator starts paused with independent Normal settings and steps exactly once through a real Worker', async ({ page }) => {
  const workers: string[] = [];
  page.on('worker', (worker) => workers.push(worker.url()));
  await page.goto('/');
  await expect(page.getByTestId('mode')).toHaveValue('r-r');
  await expect(page.getByTestId('difficulty-b')).toHaveValue('normal');
  await expect(page.getByTestId('difficulty-w')).toHaveValue('normal');
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 10_000 });
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  await expect(page.getByTestId('ai-analysis')).toContainText('深さ');
  await page.waitForTimeout(500);
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番', { timeout: 10_000 });
  expect(workers).toHaveLength(1); // no duplicate StrictMode worker or per-turn recreation
});

for (const b of ['easy', 'normal']) for (const w of ['easy', 'normal']) {
  test(`automatic spectator progresses with ${b}/${w}`, async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('difficulty-b').selectOption(b);
    await page.getByTestId('difficulty-w').selectOption(w);
    await page.getByTestId('thinking-budget').selectOption('100');
    await page.getByTestId('toggle-run').click();
    await expect.poll(() => page.getByTestId('move-list').locator('li').count(), { timeout: 10_000 }).toBeGreaterThanOrEqual(3);
    await page.getByTestId('toggle-run').click();
    await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
    const downloading = page.waitForEvent('download');
    await page.getByRole('button', { name: '保存', exact: true }).click();
    const download = await downloading;
    const json = Buffer.concat(await (await download.createReadStream()).toArray()).toString('utf8');
    const verified = Game.fromRecordJson(json); // Rust revalidates every move and the outcome
    try { expect(verified.moveCount()).toBeGreaterThanOrEqual(2); } finally { verified.free(); }
  });
}

test('2D/3D and camera remain interactive during real search, and cancel prevents a late move', async ({ page }) => {
  // Software-GL screenshots can take seconds in CI. Capture outside searches;
  // every actual control operation must still finish before its real reply.
  test.setTimeout(60_000);
  const workers: string[] = [];
  page.on('worker', (worker) => workers.push(worker.url()));
  await page.addInitScript(() => {
    const state = window as unknown as { renderedFrames: number };
    state.renderedFrames = 0;
    const original = WebGL2RenderingContext.prototype.clear;
    WebGL2RenderingContext.prototype.clear = function (mask: number) {
      state.renderedFrames++;
      return original.call(this, mask);
    };
  });
  await page.goto('/');
  await page.getByRole('button', { name: '3D+2D', exact: true }).click();
  const canvas = page.getByTestId('board3d').locator('canvas');
  await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
  await page.waitForTimeout(1000); // allow initial layout and camera damping to settle
  const frames = await page.evaluate(() => (window as unknown as { renderedFrames: number }).renderedFrames);
  expect(frames).toBeGreaterThan(0);
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => (window as unknown as { renderedFrames: number }).renderedFrames)).toBe(frames);
  await page.getByTestId('thinking-budget').selectOption('3000');
  const begin = async () => {
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  };
  const cancel = async () => {
    await page.getByTestId('cancel-search').click();
    await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
    await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  };
  await begin();
  await page.getByTestId('move-delay').fill('50');
  await expect(page.getByTestId('move-delay')).toHaveValue('50');
  await page.getByTestId('slice-index').fill('5');
  await expect(page.getByTestId('slice-index')).toHaveValue('5');
  await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  expect(workers).toHaveLength(1); // display speed did not restart the search
  await cancel();

  await canvas.scrollIntoViewIfNeeded();
  const beforeCamera = await canvas.screenshot();
  const box = (await canvas.boundingBox())!;
  await begin();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 50, box.y + box.height / 2 + 30, { steps: 2 });
  await page.mouse.up();
  await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  await cancel();
  expect((await canvas.screenshot()).equals(beforeCamera)).toBe(false);

  await begin();
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(page.getByTestId('board3d')).toHaveCount(0);
  await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  await cancel();
  await begin();
  await page.getByRole('button', { name: '3D+2D', exact: true }).click();
  await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready', 'true');
  await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  await cancel();
  await page.waitForTimeout(3300);
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await page.getByTestId('thinking-budget').selectOption('100');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  expect(workers).toHaveLength(5); // explicit cancellations recreated it
});

test('Worker load failures are visible and retry recreates the worker', async ({ page }) => {
  await page.route('**/assets/search.worker-*.js', (route) => route.abort());
  await page.goto('/');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('ai-error')).toBeVisible();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await page.unroute('**/assets/search.worker-*.js');
  await page.getByTestId('ai-retry').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 10_000 });
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
});

test('2D initial load defers the 3D module until it is selected', async ({ page }) => {
  const scripts: string[] = [];
  page.on('response', (response) => { if (response.request().resourceType() === 'script') scripts.push(response.url()); });
  await page.goto('/');
  await expect(page.getByTestId('status')).toBeVisible();
  expect(scripts.some((url) => /Board3D-/.test(url))).toBe(false);
  await expect(page.getByTestId('board3d')).toHaveCount(0);
  await page.getByRole('button', { name: '3D+2D', exact: true }).click();
  await expect(page.getByTestId('board3d').locator('canvas')).toBeVisible();
  expect(scripts.some((url) => /Board3D-/.test(url))).toBe(true);
});

test('new game, difficulty, undo/redo, goto and import invalidate a pending search', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('thinking-budget').selectOption('100');
  for (let i = 0; i < 2; ++i) {
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('status')).toHaveText(i === 0 ? '2手目 ☖後手の番' : '3手目 ☗先手の番');
  }
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  const record = Buffer.concat(await (await (await downloading).createReadStream()).toArray());
  await page.getByTestId('thinking-budget').selectOption('3000');
  const begin = async () => {
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('ai-phase')).toHaveText(/思考中/);
  };
  await begin(); await page.getByTestId('undo').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await begin(); await page.getByTestId('redo').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await begin(); await page.getByRole('button', { name: '開始局面', exact: true }).click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await begin(); await page.getByTestId('import').setInputFiles({ name: 'saved.json', mimeType: 'application/json', buffer: record });
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await begin(); await page.getByTestId('difficulty-b').selectOption('easy');
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  await page.getByTestId('difficulty-b').selectOption('normal');
  await begin(); await page.getByRole('button', { name: '新規対局', exact: true }).click();
  await page.waitForTimeout(3300);
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

function humanRecord(): string {
  const board = new Map([['8,8,8', 'K'], ['0,0,0', 'k'], ['4,3,4', 'P']]);
  const layers = Array.from({ length: 9 }, (_, z) => Array.from({ length: 9 }, (_, y) => {
    let rank = '', empty = 0;
    for (let x = 8; x >= 0; --x) {
      const piece = board.get(`${x},${y},${z}`);
      if (!piece) { empty++; continue; }
      if (empty) rank += empty;
      empty = 0; rank += piece;
    }
    return rank + (empty || '');
  }).join('/')).join('|');
  return JSON.stringify({ ruleset_id: 'voxelshogi-standard-v1', initial: `${layers} b P 1`, moves: [], result: null, termination: null });
}

test('human promotion, pawn drop and record round-trip remain available alongside AI spectator', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('mode').selectOption('h-r');
  const record = humanRecord();
  const load = async () => {
    await page.getByTestId('import').setInputFiles({ name: 'human.json', mimeType: 'application/json', buffer: Buffer.from(record) });
    await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
  };
  await load();
  const cell = (x: number, y: number) => page.locator(`.board2d [data-square="${4 * 81 + y * 9 + x}"]`);
  await cell(4, 3).click(); await cell(4, 2).click();
  await expect(page.getByRole('dialog', { name: '成りの選択' })).toBeVisible();
  await page.getByRole('button', { name: '成る', exact: true }).click();
  await expect(cell(4, 2)).toHaveText('と');
  await load();
  await page.getByTestId('hands-b').locator('[data-hand="P"]').click();
  await cell(3, 4).click();
  await expect(cell(3, 4)).toHaveText('歩');
  await expect(page.getByTestId('hands-b').locator('[data-hand="P"]')).toHaveCount(0);
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  const saved = Buffer.concat(await (await (await downloading).createReadStream()).toArray()).toString('utf8');
  expect(JSON.parse(saved).moves).toEqual(['P*455']);
  const verified = Game.fromRecordJson(saved);
  try { expect(verified.moveCount()).toBe(1); } finally { verified.free(); }
});

test('an asynchronous file read cannot replace a newer game', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('status')).toBeVisible();
  await page.evaluate(() => {
    const original = File.prototype.text;
    File.prototype.text = function () {
      return new Promise<string>((resolve) => {
        (window as unknown as { releaseImport: () => Promise<void> }).releaseImport = () => original.call(this).then(resolve);
      });
    };
  });
  await page.getByTestId('import').setInputFiles({ name: 'late.json', mimeType: 'application/json', buffer: Buffer.from(humanRecord()) });
  await expect(page.getByRole('alert')).toContainText('棋譜を読み込み中');
  await page.getByRole('button', { name: '新規対局', exact: true }).click();
  await page.evaluate(() => (window as unknown as { releaseImport: () => Promise<void> }).releaseImport());
  await expect(page.locator('.board2d [data-square="382"]')).toHaveText('歩'); // initial 5七V
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

test('humans can play either color against Normal search', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('thinking-budget').selectOption('100');
  await page.getByTestId('mode').selectOption('h-r');
  const cell = (y: number) => page.locator(`.board2d [data-square="${4 * 81 + y * 9 + 4}"]`);
  await cell(6).click(); await cell(5).click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await expect(page.getByTestId('ai-analysis')).toContainText('Normal');
  await page.getByTestId('mode').selectOption('r-h');
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await cell(2).click(); await cell(3).click();
  await expect(page.getByTestId('status')).toHaveText('4手目 ☖後手の番');
  await expect(page.getByTestId('ai-analysis')).toContainText('Normal');
  await page.getByRole('button', { name: '投了', exact: true }).click();
  await expect(page.getByTestId('status')).toHaveText('☗先手の勝ち（投了）');
  await expect(page.getByTestId('ai-step')).toBeDisabled();
});
