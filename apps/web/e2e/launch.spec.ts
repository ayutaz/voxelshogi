import { expect, test } from '@playwright/test';

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
    if (width! < 1100) {
      const board = await page.locator('main').boundingBox();
      const settings = await page.locator('.panel.left').boundingBox();
      expect(board!.y).toBeLessThan(settings!.y);
      await expect(page.getByTestId('mode')).not.toBeVisible();
      await page.getByText('対局・AI設定', { exact: true }).click();
    }
    await page.getByTestId('difficulty-b').selectOption('easy');
    await page.getByTestId('difficulty-w').selectOption('easy');
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
    const snapshot = await page.screenshot({ fullPage: true });
    await info.attach(`launch-${width}`, { body: snapshot, contentType: 'image/png' });
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
  await page.getByTestId('difficulty-b').selectOption('easy');
  await page.getByTestId('ai-step').click();
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  const dialogs: string[] = [];
  const cancel = async (dialog: import('@playwright/test').Dialog) => { dialogs.push(dialog.message()); await dialog.dismiss(); };
  page.on('dialog', cancel);
  await page.getByRole('button', { name: '新規対局', exact: true }).click();
  await page.getByTestId('mode').selectOption('h-r');
  await page.getByTestId('import').setInputFiles({ name: 'replacement.json', mimeType: 'application/json', buffer: Buffer.from('{}') });
  expect(dialogs).toHaveLength(3);
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await expect(page.getByTestId('mode')).toHaveValue('r-r');
  page.off('dialog', cancel); page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '新規対局', exact: true }).click();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});
