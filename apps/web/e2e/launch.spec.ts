import { selectSetting, settingsAction, sliceAt } from './arena-controls';
import { test, expect } from './test';
import { readFileSync } from 'node:fs';

for (const [width, height] of [[390, 844], [768, 1024], [1440, 900]]) {
  test(`watching starts from the board without downloading a model at ${width}x${height}`, async ({ page }, info) => {
    await page.setViewportSize({ width: width!, height: height! });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    const toggle = page.getByTestId('toggle-run');
    await expect(toggle).toHaveText('観戦を開始');
    await expect(toggle).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByTestId('mode')).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'AIと対戦', exact: true })).toBeInViewport();
    const board = await page.locator('.views').boundingBox();
    expect(board!.y).toBeGreaterThan(0); expect(board!.y + board!.height).toBeLessThanOrEqual(height!);
    const follow = page.getByTestId('follow-move'); await expect(follow).toBeInViewport();
    await selectSetting(page, 'difficulty-b', 'easy');
    await selectSetting(page, 'difficulty-w', 'easy');
    await toggle.click();
    await expect(page.getByTestId('status')).not.toHaveText('1手目 ☗先手の番');
    await toggle.click();
    await expect(toggle).toHaveText('再開');
    await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
    await expect(page.getByTestId('last-move')).toContainText('直前手');
    const beforeStep = await page.getByTestId('status').textContent();
    await page.getByTestId('ai-step').click();
    await expect(page.getByTestId('status')).not.toHaveText(beforeStep!);
    await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
    await expect(page.getByTestId('board3d')).toHaveAttribute('data-ready','true');
    const path = info.outputPath(`attachments/launch-${width}.png`);
    await page.screenshot({ path, fullPage: true });
    await info.attach(`launch-${width}`, { path, contentType: 'image/png' });
    expect(errors).toEqual([]);
  });
}

test('failed engine download offers an actionable Japanese recovery screen', async ({ page }) => {
  await page.route('**/*.wasm', route => route.abort('failed'));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('盤面を読み込めませんでした');
  await expect(page.getByRole('button', { name: '再読み込み' })).toBeVisible();
});

test('discard confirmation cancels all three replacements and accepting a new game works', async ({ page }) => {
  await page.goto('/');
  await selectSetting(page, 'difficulty-b', 'easy');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  const dialogs: string[] = [];
  const cancel = async (dialog: import('@playwright/test').Dialog) => { dialogs.push(dialog.message()); await dialog.dismiss(); };
  page.on('dialog', cancel);
  await settingsAction(page, '新規対局');
  await selectSetting(page, 'mode', 'h-r');
  await page.getByTestId('import').setInputFiles({ name: 'replacement.json', mimeType: 'application/json', buffer: Buffer.from('{}') });
  expect(dialogs).toHaveLength(3);
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await expect(page.getByTestId('mode')).toHaveValue('r-r');
  page.off('dialog', cancel); page.once('dialog', dialog => dialog.accept());
  await settingsAction(page, '新規対局');
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

test('a legal fixed record follows both colors across layers, undo/redo, OFF and manual slices', async ({ page }) => {
  await page.goto('/');
  page.on('dialog', dialog => dialog.accept());
  const fixtures = JSON.parse(readFileSync(new URL('../../../crates/voxelshogi-wasm/tests/fixtures/search.json', import.meta.url), 'utf8')) as { name: string; record: { initial: string; ruleset_id: string } }[];
  const initial = fixtures.find(item => item.name === 'corner-kings-b')!.record;
  const load = async (moves: string[]) => {
    // Kings at 999 and 111: each given move is one king step with no intervening piece.
    await page.getByTestId('import').setInputFiles({ name: 'layers.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ ...initial, moves, result: null, termination: null })) });
    await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
  };
  await load(['999888', '111222']);
  await expect(page.getByTestId('slice-index')).toHaveValue('1'); // White: I → II
  await expect(page.getByTestId('last-move')).toContainText('後手 1一I→2二II');
  await page.getByTestId('undo').click();
  await expect(page.getByTestId('slice-index')).toHaveValue('7'); // Black: IX → VIII
  await expect(page.getByTestId('last-move')).toContainText('先手 9九IX→8八VIII');
  await page.getByTestId('redo').click();
  await expect(page.getByTestId('slice-index')).toHaveValue('1');
  await page.getByTestId('undo').click(); await page.getByTestId('undo').click();
  await expect(page.getByTestId('last-move')).toContainText('開始局面');
  await expect(page.getByTestId('last-move')).not.toContainText('2二II');
  await page.getByTestId('redo').click();
  await page.getByTestId('follow-move').uncheck();
  await page.getByTestId('redo').click();
  await expect(page.getByTestId('slice-index')).toHaveValue('7');
  await sliceAt(page, '2');
  await expect(page.getByTestId('follow-move')).not.toBeChecked();
  await expect(page.getByTestId('slice-index')).toHaveValue('2');
  await page.getByTestId('follow-move').check();
  await expect(page.getByTestId('slice-index')).toHaveValue('1');
  await load(['999899', '111211']);
  await expect(page.getByTestId('slice-index')).toHaveValue('0'); // White stays on I
  await page.getByTestId('undo').click();
  await expect(page.getByTestId('slice-index')).toHaveValue('8'); // Black stays on IX
});

test('the public sharing metadata refers to a real board PNG', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', '将棋、9層にした。｜VoxelShogi Arena');
  await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute('content', 'summary_large_image');
  const image = await page.request.get('/social/voxelshogi.png');
  expect(image.ok()).toBe(true); expect(image.headers()['content-type']).toContain('image/png');
  const bytes = await image.body();
  expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  expect([bytes.readUInt32BE(16), bytes.readUInt32BE(20)]).toEqual([1200, 630]);
});

test('the board stays in place between waiting and real Normal thinking phases', async ({ page }) => {
  await page.goto('/');
  await selectSetting(page, 'thinking-budget', '1000');
  await page.getByTestId('move-delay').fill('1000');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await expect(page.getByTestId('ai-phase')).toHaveText('一時停止中');
  await expect(page.getByTestId('ai-analysis')).toBeHidden();
  const reference = await page.evaluate(() => ({ top: document.querySelector('.views')!.getBoundingClientRect().top, windowY: window.scrollY, mainY: document.querySelector('main')!.scrollTop }));
  await page.evaluate(() => {
    const phase = document.querySelector('[data-testid="ai-phase"]')!, board = document.querySelector('.views')!;
    const samples: { phase: string | null; top: number; windowY: number; mainY: number }[] = [];
    const measure = () => samples.push({ phase: phase.textContent, top: board.getBoundingClientRect().top, windowY: window.scrollY, mainY: document.querySelector('main')!.scrollTop });
    const observer = new MutationObserver(measure);
    observer.observe(phase, { subtree: true, childList: true, characterData: true }); measure();
    (window as unknown as { watchGeometry: typeof samples }).watchGeometry = samples;
  });
  await page.getByTestId('toggle-run').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { watchGeometry: { phase: string | null }[] }).watchGeometry.filter(s => s.phase === '次の着手待ち').length), { timeout: 10000 }).toBeGreaterThanOrEqual(2);
  await page.getByTestId('toggle-run').click();
  const samples = await page.evaluate(() => (window as unknown as { watchGeometry: { phase: string | null; top: number; windowY: number; mainY: number }[] }).watchGeometry);
  expect(samples.length).toBeGreaterThanOrEqual(3);
  expect(samples.some(s => s.phase?.includes('Normal 思考中'))).toBe(true);
  expect(samples.filter(s => s.phase === '次の着手待ち').length).toBeGreaterThanOrEqual(2);
  for (const sample of samples) {
    expect(Math.abs(sample.top - reference.top)).toBeLessThan(0.5);
    expect(Math.abs(sample.windowY - reference.windowY)).toBeLessThan(0.5);
    expect(Math.abs(sample.mainY - reference.mainY)).toBeLessThan(0.5);
  }
});
