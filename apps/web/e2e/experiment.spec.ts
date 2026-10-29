import { test, expect } from '@playwright/test';

test('public navigation keeps watching and the model lab without the retired comparison room', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'VoxelShogi Arena' })).toBeVisible();
  await expect(page.getByRole('link', { name: '9王ルール比較室' })).toHaveCount(0);
  await page.getByRole('link', { name: 'モデル推論ラボ' }).click();
  await expect(page.getByRole('heading', { name: 'モデル推論ラボ' })).toBeVisible();
  await expect(page.getByRole('link', { name: '9王ルール比較室' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'AI対局の観戦へ' })).toHaveAttribute('href', '/');
});

test('the legacy comparison URL opens normal watching without downloading experiment records', async ({ page }) => {
  const experimentRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/experiments/')) experimentRequests.push(request.url()); });
  await page.goto('/?experiment=1');
  await expect(page.getByRole('heading', { name: 'VoxelShogi Arena' })).toBeVisible();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
  await expect(page.getByRole('heading', { name: '9王ルール比較室' })).toHaveCount(0);
  expect(experimentRequests).toEqual([]);
});

test('the model lab remains available with a legacy comparison parameter', async ({ page }) => {
  await page.goto('/?experiment=1&models=1');
  await expect(page.getByRole('heading', { name: 'モデル推論ラボ' })).toBeVisible();
  await expect(page.getByRole('link', { name: '9王ルール比較室' })).toHaveCount(0);
});
