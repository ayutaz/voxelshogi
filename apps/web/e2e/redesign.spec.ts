import { test, expect } from './test';
import { display, selectSetting, settingsAction, sliceAt } from './arena-controls';
import {readFileSync} from 'node:fs';

test('match setup traps focus, closes with Escape and returns focus without replacing the game', async ({ page }) => {
  await page.goto('/');
  const opener=page.getByRole('button',{name:'AIと対戦',exact:true});await opener.click();
  const close=page.getByRole('button',{name:'閉じる',exact:true});await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');await expect(page.getByRole('button',{name:'対戦をはじめる',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);await expect(opener).toBeFocused();
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');
});

for (const [width,height] of [[390,844],[768,1024],[1440,900]]) for (const side of ['h-r','r-h']) for (const difficulty of ['easy','normal']) {
  test(`human entry starts ${side} against ${difficulty} at ${width} and the real AI answers`, async ({ page },info) => {
    await page.setViewportSize({width:width!,height:height!});
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
    page.once('dialog',dialog=>dialog.accept());await settingsAction(page,'新規対局');
    await expect(page.getByTestId('status')).toHaveText(side === 'h-r' ? '1手目 ☗先手の番' : '2手目 ☖後手の番');
    await sliceAt(page,'4');await page.locator(`.board2d [data-square="${from}"]`).click();await page.locator(`.board2d [data-square="${to}"]`).click();
    await expect(page.getByTestId('status')).toHaveText(side === 'h-r' ? '3手目 ☗先手の番' : '4手目 ☖後手の番');
    await expect(page.getByTestId('ai-phase')).toHaveText('人間の手番');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const path=info.outputPath(`attachments/launch-human-${width}-${side}-${difficulty}.png`);await page.screenshot({path,fullPage:true});await info.attach('human-match',{path,contentType:'image/png'});
  });
}
for (const [width,height] of [[390,844],[768,1024],[1440,900]]) {
  test(`history and terminal controls keep the board readable at ${width}x${height}`,async({page},info)=>{
    await page.setViewportSize({width:width!,height:height!});await page.goto('/');page.on('dialog',dialog=>dialog.accept());
    await selectSetting(page,'mode','h-r');
    const fixtures=JSON.parse(readFileSync(new URL('../../../crates/voxelshogi-wasm/tests/fixtures/search.json',import.meta.url),'utf8'));
    const initial=fixtures.find((f:{name:string})=>f.name==='corner-kings-b').record;
    const record={...initial,moves:['999888','111222'],result:null,termination:null};
    const load=async(value:unknown)=>page.getByTestId('import').setInputFiles({name:'fixed.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
    await load(record);await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
    await page.getByTestId('undo').click();await expect(page.getByTestId('ai-phase')).toContainText('履歴 1/2手');
    const branch=page.getByRole('button',{name:'この局面から対戦を分岐',exact:true});await expect(branch).toBeInViewport();
    expect((await branch.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const path=info.outputPath(`attachments/launch-history-${width}.png`);await page.screenshot({path,fullPage:true});await info.attach('history',{path,contentType:'image/png'});
    await load({...record,result:{Win:{winner:'White',reason:'Resignation'}},termination:'Resignation'});
    await page.getByRole('button',{name:'盤面を見る',exact:true}).click();
    await expect(page.getByRole('region',{name:'対局結果'})).toHaveCount(0);await expect(page.locator('.board2d .cell')).toHaveCount(81);
    const terminal=info.outputPath(`attachments/launch-terminal-${width}.png`);await page.screenshot({path:terminal,fullPage:true});await info.attach('terminal',{path:terminal,contentType:'image/png'});
  });
  test(`the reading board and primary controls fit ${width}x${height}`, async ({ page },info) => {
    await page.setViewportSize({ width:width!,height:height! });
    await page.goto('/');
    await display(page,'2d');
    await expect(page.locator('.board2d .cell')).toHaveCount(81);
    const path=info.outputPath(`attachments/launch-reading-${width}.png`);await page.screenshot({path,fullPage:true});await info.attach(`reading-${width}`,{path,contentType:'image/png'});
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
  });
}
