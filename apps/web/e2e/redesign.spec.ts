import { test, expect } from './test';
import { display, selectSetting, sliceAt } from './arena-controls';

test('match setup traps focus, closes with Escape and returns focus without replacing the game', async ({ page }) => {
  await page.goto('/');
  const opener=page.getByRole('button',{name:'AIと対戦',exact:true});await opener.click();
  const close=page.getByRole('button',{name:'閉じる',exact:true});await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');await expect(page.getByRole('button',{name:'対戦をはじめる',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);await expect(opener).toBeFocused();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

for (const side of ['h-r','r-h']) for (const difficulty of ['easy','normal']) {
  test(`human entry starts ${side} against ${difficulty} and the real AI answers`, async ({ page }) => {
    await page.goto('/');
    await selectSetting(page, 'thinking-budget', '100');
    await page.getByRole('button', { name: 'AIと対戦', exact: true }).click();
    await page.getByLabel('あなたの先後').selectOption(side);
    await page.getByLabel('相手のAI').selectOption(difficulty);
    await page.getByRole('button', { name: '対戦をはじめる', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'AIと対戦' })).toHaveCount(0);
    await expect(page.getByTestId('status')).toHaveText(side === 'h-r' ? '1手目 ☗先手の番' : '2手目 ☖後手の番');
    await sliceAt(page,'4');
    const from = side === 'h-r' ? 382 : 346, to = side === 'h-r' ? 373 : 355;
    await page.locator(`.board2d [data-square="${from}"]`).click();
    await page.locator(`.board2d [data-square="${to}"]`).click();
    await expect(page.getByTestId('status')).toHaveText(side === 'h-r' ? '3手目 ☗先手の番' : '4手目 ☖後手の番');
    await expect(page.getByTestId('ai-phase')).toHaveText('人間の手番');
    await expect(page.getByTestId('ai-step')).toBeDisabled();
  });
}
for (const [width,height] of [[390,844],[768,1024],[1440,900]]) {
  test(`the reading board and primary controls fit ${width}x${height}`, async ({ page },info) => {
    await page.setViewportSize({ width:width!,height:height! });
    await page.goto('/');
    await display(page,'2d');
    await expect(page.locator('.board2d .cell')).toHaveCount(81);
    const layout = await page.evaluate(() => {
      const rect = (selector:string) => { const r=document.querySelector(selector)!.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}; };
      return { board:rect('.board2d-grid'), first:rect('.board2d .cell'), toggle:rect('[data-testid="toggle-run"]'), follow:rect('[data-testid="follow-move"]'), overflow:document.documentElement.scrollWidth>innerWidth, width:innerWidth,height:innerHeight };
    });
    expect(layout.overflow).toBe(false);
    for (const rect of [layout.board,layout.toggle,layout.follow]) { expect(rect.top).toBeGreaterThanOrEqual(0);expect(rect.bottom).toBeLessThanOrEqual(layout.height); }
    if(width===390)expect(layout.first.width).toBeGreaterThanOrEqual(36);
    expect(layout.toggle.height).toBeGreaterThanOrEqual(44);
    const layer = page.getByRole('combobox',{name:'表示する層'});
    if(await layer.isVisible())expect((await layer.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    else { for(const rect of await page.locator('.layer-rail button').evaluateAll(buttons=>buttons.map(b=>({height:b.getBoundingClientRect().height,width:b.getBoundingClientRect().width})))){expect(rect.height).toBeGreaterThanOrEqual(44);expect(rect.width).toBeGreaterThanOrEqual(44);} }
    const path=info.outputPath(`attachments/launch-reading-${width}.png`);await page.screenshot({path,fullPage:true});await info.attach(`reading-${width}`,{path,contentType:'image/png'});
  });
}
