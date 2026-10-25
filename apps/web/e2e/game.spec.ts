import { expect, test, type Page } from '@playwright/test';

// Square index = z*81 + y*9 + x (see src/game/model.ts).
const idx = (x: number, y: number, z: number) => z * 81 + y * 9 + x;
const cell = (page: Page, i: number) => page.locator(`.board2d [data-square="${i}"]`);
// Engine move string for a board move between 0-indexed (x, y, z) squares: digits are 1-indexed.
const sq = (x: number, y: number, z: number) => `${x + 1}${y + 1}${z + 1}`;

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  (page as unknown as { errors: string[] }).errors = errors;
  await page.goto('/');
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

test.afterEach(async ({ page }) => {
  expect((page as unknown as { errors: string[] }).errors).toEqual([]);
});

test('shows the initial position in 2D and 3D', async ({ page }) => {
  await expect(page.locator('.board2d .cell')).toHaveCount(81);
  // layer V, rank 九: black king at file 5
  await expect(cell(page, idx(4, 8, 4))).toHaveText('玉');
  await expect(cell(page, idx(4, 6, 4))).toHaveText('歩');
  await expect(page.getByTestId('board3d').locator('canvas')).toBeVisible();
  await expect(page.getByTestId('mode')).toHaveValue('h-r');
  expect(await page.getByTestId('mode').locator('option').evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value))).toEqual(['h-r', 'r-h', 'r-r']);
});

test('human vs AI: select, see targets, move, inspect history, undo', async ({ page }) => {
  await cell(page, idx(4, 6, 4)).click();
  await expect(page.locator('.board2d .cell.target')).toHaveCount(1);
  await expect(cell(page, idx(4, 5, 4))).toHaveClass(/target/);
  await cell(page, idx(4, 5, 4)).click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await expect(cell(page, idx(4, 5, 4))).toHaveText('歩');
  await expect(cell(page, idx(4, 6, 4))).toHaveText('');
  await expect(page.getByTestId('move-list')).toContainText('1. ☗5七V→5六V');
  // At most one White pawn has moved, so one of these two must still be present.
  const whitePawnFile = (await cell(page, idx(3, 2, 4)).textContent()) === '歩' ? 3 : 5;
  await expect(cell(page, idx(whitePawnFile, 2, 4))).toHaveText('歩');
  await cell(page, idx(whitePawnFile, 2, 4)).click();
  await expect(page.locator('.board2d .cell.target')).toHaveCount(0);
  await page.getByTestId('undo').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await page.getByTestId('undo').click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await expect(cell(page, idx(4, 6, 4))).toHaveText('歩');
});

test('human as White: the AI opens and answers automatically', async ({ page }) => {
  await page.getByTestId('mode').selectOption('r-h');
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番', { timeout: 5000 });
  await cell(page, idx(4, 2, 4)).click();
  await cell(page, idx(4, 3, 4)).click();
  await expect(page.getByTestId('status')).toHaveText('4手目 ☖後手の番', { timeout: 5000 });
  await expect(page.getByTestId('move-list').locator('li')).toHaveCount(4);
});

test('AI vs AI can be watched and paused', async ({ page }) => {
  await page.getByTestId('mode').selectOption('r-r');
  await expect.poll(async () => page.getByTestId('move-list').locator('li').count(), { timeout: 8000 }).toBeGreaterThan(4);
  await page.getByTestId('toggle-run').click();
  const n = await page.getByTestId('move-list').locator('li').count();
  await page.waitForTimeout(1200);
  expect(await page.getByTestId('move-list').locator('li').count()).toBe(n);
  // While paused nothing changes over time, so a human click must not select AI pieces.
  const side = (await page.getByTestId('status').textContent())!.includes('先手') ? 'b' : 'w';
  const pawnRank = side === 'b' ? 6 : 2;
  for (let x = 0; x < 9; x++) await cell(page, idx(x, pawnRank, 4)).click();
  await page.waitForTimeout(300);
  expect(await page.locator('.board2d .cell.target').count()).toBe(0);
  expect(await page.locator('.board2d .cell.selected').count()).toBe(0);
});

test('records round-trip through save and load, and invalid files are rejected', async ({ page }) => {
  await cell(page, idx(4, 6, 4)).click();
  await cell(page, idx(4, 5, 4)).click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '保存' }).click();
  const download = await downloadPromise;
  const saved = await (await download.createReadStream()).toArray();
  const json = JSON.parse(Buffer.concat(saved).toString('utf8'));
  expect(json.ruleset_id).toBe('voxelshogi-standard-v1');
  expect(json.moves).toHaveLength(2);
  expect(json.moves[0]).toBe(sq(4, 6, 4) + sq(4, 5, 4));

  await page.getByRole('button', { name: '新規対局' }).click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await page.getByTestId('import').setInputFiles({ name: 'game.json', mimeType: 'application/json', buffer: Buffer.concat(saved) });
  await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await expect(page.getByTestId('mode')).toHaveValue('h-r');
  await expect(cell(page, idx(4, 5, 4))).toHaveText('歩');

  // A tampered record (illegal move) is rejected and the current game is kept.
  // the second move starts from the square the first move just vacated
  const bad = { ...json, moves: [sq(4, 6, 4) + sq(4, 5, 4), sq(4, 6, 4) + sq(4, 5, 4)] };
  await page.getByTestId('import').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bad)) });
  await expect(page.getByRole('alert')).toContainText('読み込めません');
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
});
