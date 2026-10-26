import { test, expect } from '@playwright/test';

test('same record and position survive presentation switches and playback controls', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/?experiment=1');
  await expect(page.getByRole('heading', { name: '9王ルール比較室' })).toBeVisible();
  await expect(page.getByTestId('record-hash')).toHaveText(/[a-f0-9]{64}/);
  await expect(page.getByTestId('experiment-ply')).toHaveText('0');
  await page.getByRole('button', { name: '次の王捕獲' }).click();
  const ply = await page.getByTestId('experiment-ply').textContent();
  expect(Number(ply)).toBeGreaterThan(0);
  const hash = await page.getByTestId('position-hash').textContent();
  const digest = await page.getByTestId('record-hash').textContent();
  await page.getByLabel('観戦表示').selectOption('focus');
  await expect(page.getByTestId('king-event')).toBeVisible();
  await expect(page.getByTestId('experiment-ply')).toHaveText(ply!);
  await expect(page.getByTestId('position-hash')).toHaveText(hash!);
  await expect(page.getByTestId('record-hash')).toHaveText(digest!);
  await page.getByLabel('観戦表示').selectOption('overview');
  await expect(page.getByTestId('position-hash')).toHaveText(hash!);
  await page.getByRole('button', { name: '1手戻る' }).click();
  await expect(page.getByTestId('experiment-ply')).toHaveText(String(Number(ply) - 1));
  await page.getByRole('button', { name: '1手進む' }).click();
  await expect(page.getByTestId('position-hash')).toHaveText(hash!);
  await page.getByLabel('再生間隔').selectOption('200');
  await page.getByRole('button', { name: '再生', exact: true }).click();
  await expect(page.getByTestId('experiment-ply')).not.toHaveText(ply!);
  await page.getByRole('button', { name: '一時停止' }).click();
  const paused = await page.getByTestId('experiment-ply').textContent();
  await page.waitForTimeout(500);
  await expect(page.getByTestId('experiment-ply')).toHaveText(paused!);
  for (const rule of ['voxelshogi-nine-kings-all-v0', 'voxelshogi-nine-kings-score-v0']) {
    await page.getByLabel('比較するルール').selectOption(rule);
    await expect(page.getByTestId('experiment-ply')).toHaveText('0');
    await page.getByRole('button', { name: '最終局面' }).click();
    await expect(page.getByTestId('experiment-result')).toContainText(/終局|打ち切り/);
  }
  expect(errors).toEqual([]);
});

test('record corruption is rejected before replay', async ({ page }) => {
  await page.route('**/*.record.json', (route) => route.fulfill({ contentType: 'application/json', body: '{}' }));
  await page.goto('/?experiment=1');
  await expect(page.getByRole('alert')).toContainText('SHA-256');
  await expect(page.getByTestId('board3d')).toHaveCount(0);
});

test('800-ply trial can replay a complete all-kings capture', async ({ page }) => {
  await page.goto('/?experiment=1');
  await page.getByLabel('比較条件').selectOption('long');
  await page.getByLabel('比較するルール').selectOption('voxelshogi-nine-kings-all-v0');
  await expect(page.getByTestId('experiment-ply')).toHaveText('0');
  await page.getByRole('button', { name: '最終局面' }).click();
  await expect(page.getByTestId('experiment-result')).toContainText('目標捕獲数に到達');
  const scores = await page.locator('.experiment-score strong').allTextContents();
  expect(scores.some((s) => /9\s*\/\s*9/.test(s))).toBe(true);
});
