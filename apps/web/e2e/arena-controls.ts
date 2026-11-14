import { expect, type Page } from '@playwright/test';

export async function closeSheet(page: Page) {
  const sheet = page.locator('.sheet-backdrop:not([hidden])');
  if (await sheet.count()) await sheet.getByRole('button', { name: '閉じる', exact: true }).click();
}
export async function openSettings(page: Page) {
  await closeSheet(page);
  await page.getByRole('button', { name: '対局設定', exact: true }).click();
}
export async function selectSetting(page: Page, testId: string, value: string) {
  await openSettings(page);
  await page.getByTestId(testId).selectOption(value);
  await closeSheet(page);
}
export async function settingsAction(page: Page, name: string) {
  await openSettings(page);
  await page.getByRole('button', { name, exact: true }).click();
  await closeSheet(page);
}
export async function openRecords(page: Page) {
  await closeSheet(page);
  await page.getByRole('button', { name: '棋譜', exact: true }).click();
}
export async function saveRecord(page: Page) {
  await openRecords(page);
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await closeSheet(page);
}
export async function sliceAt(page: Page, index: string) {
  const mobile = page.getByRole('combobox', { name: '表示する層' });
  if (await mobile.isVisible()) await mobile.selectOption(index);
  else {
    const roman = ['I','II','III','IV','V','VI','VII','VIII','IX'][Number(index)]!;
    await page.getByRole('button', { name: new RegExp(`^${roman}層を見る(?:、|$)`) }).click();
  }
  await expect(page.getByTestId('slice-index')).toHaveValue(index);
}
export async function display(page: Page, mode: '2d' | 'both') {
  await closeSheet(page);
  await page.getByRole('button', { name: mode === '2d' ? '断面を読む' : '立体で眺める', exact: true }).click();
}
