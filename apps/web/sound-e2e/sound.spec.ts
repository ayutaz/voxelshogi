import { test, expect } from '../e2e/test';
import { closeSheet, display, openRecords, sliceAt } from '../e2e/arena-controls';
import type { Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

interface SoundEvidence { contexts:number; starts:number[]; stops:number; peak:number }
declare global { interface Window { __soundEvidence:SoundEvidence } }
async function instrument(page:Page,broken=false) {
  await page.addInitScript(({broken})=>{
    const data:SoundEvidence={contexts:0,starts:[],stops:0,peak:0};window.__soundEvidence=data;
    if(broken){
      Object.defineProperty(window,'AudioContext',{value:function(){throw Error('controlled unavailable device');}});
      Storage.prototype.getItem=()=>{throw Error('controlled storage denial');};Storage.prototype.setItem=()=>{throw Error('controlled storage denial');};return;
    }
    const Original=window.AudioContext;
    Object.defineProperty(window,'AudioContext',{value:class extends Original {
      constructor(options?:AudioContextOptions){super(options);data.contexts++;}
      override createGain():GainNode {
        const gain=super.createGain(),connect=gain.connect.bind(gain);
        gain.connect=((destination:AudioNode|AudioParam,...args:number[])=>{
          if(destination===this.destination){
            const analyser=this.createAnalyser();analyser.fftSize=256;connect(analyser);analyser.connect(this.destination);
            const frame=new Float32Array(256);const observe=()=>{if(this.state==='closed')return;analyser.getFloatTimeDomainData(frame);for(const value of frame)data.peak=Math.max(data.peak,Math.abs(value));requestAnimationFrame(observe);};requestAnimationFrame(observe);return destination;
          }
          return (connect as (destination:AudioNode|AudioParam,...args:number[])=>AudioNode)(destination,...args);
        }) as typeof gain.connect;return gain;
      }
      override createBufferSource():AudioBufferSourceNode {
        const source=super.createBufferSource(),start=source.start.bind(source),stop=source.stop.bind(source);
        source.start=(when=0,offset=0,duration?:number)=>{if(duration===undefined)start(when,offset);else start(when,offset,duration);data.starts.push(source.buffer?.duration??0);};
        source.stop=(when=0)=>{stop(when);data.stops++;};return source;
      }
    }});
  },{broken});
}
async function evidence(page:Page){return page.evaluate(()=>window.__soundEvidence);}
async function human(page:Page){
  await page.getByRole('button',{name:'AIと対戦',exact:true}).click();await page.getByLabel('相手のAI').selectOption('easy');await page.getByRole('button',{name:'対戦をはじめる',exact:true}).click();await display(page,'2d');
}
function captureRecord(terminal=false){
  const layers=Array.from({length:9},()=>Array.from({length:9},()=>Array(9).fill('') as string[]));
  layers[8]![8]![0]='K';layers[0]![0]![8]='k';layers[4]![4]![4]='R';layers[4]![3]![4]='p';
  const initial=layers.map(rows=>rows.map(row=>{let out='',empty=0;for(const piece of row){if(!piece)empty++;else{if(empty)out+=empty;empty=0;out+=piece;}}return out+(empty||'');}).join('/')).join('|')+' b - 1';
  return {ruleset_id:'voxelshogi-standard-v1',initial,moves:terminal?['555545']:[],result:terminal?{Win:{winner:'Black',reason:'Resignation'}}:null,termination:terminal?'Resignation':null};
}
async function load(page:Page,terminal=false){
  await openRecords(page);await page.getByTestId('import').setInputFiles({name:'sound-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(captureRecord(terminal)))});await closeSheet(page);
  await expect(page.getByRole('alert')).toContainText('棋譜を読み込みました');
  if(terminal)await page.getByRole('button',{name:'盤面を見る',exact:true}).click();
  await page.getByRole('button',{name:'メッセージを閉じる'}).click();
  await display(page,'2d');await sliceAt(page,'4');
}
test.beforeEach(async({page,request})=>{
  page.on('dialog',dialog=>{void dialog.accept();});
  if(process.env.E2E_COMMIT){const r=await request.get('/build-info.json');expect(r.ok()).toBe(true);expect((await r.json()).commit).toBe(process.env.E2E_COMMIT);}
});
test.afterEach(async({page},info)=>{
  const data=await evidence(page).catch(()=>null);if(data){const path=info.outputPath('attachments/sound-evidence.json');mkdirSync(dirname(path),{recursive:true});writeFileSync(path,JSON.stringify({expectedCommit:process.env.E2E_COMMIT,browser:info.project.name,test:info.title,visibilityMayBeSimulated:info.title.includes('hidden'),...data}),{flag:'wx'});await info.attach('sound-evidence',{path,contentType:'application/json'});}
});

test('no audio before activation; test cue reaches the real output graph once',async({page})=>{
  await instrument(page);await page.goto('/');await expect(page.getByTestId('status')).toBeVisible();expect(await evidence(page)).toEqual({contexts:0,starts:[],stops:0,peak:0});
  await page.getByRole('button',{name:'表示設定',exact:true}).click();await page.getByRole('button',{name:'テスト音を鳴らす'}).click();
  await expect.poll(async()=>(await evidence(page)).peak).toBeGreaterThan(0.001);
  const data=await evidence(page);expect(data.contexts).toBe(1);expect(data.starts).toHaveLength(1);expect(data.starts[0]).toBeCloseTo(0.08,3);
});
test('accepted live capture produces one heavier cue and rejected clicks produce none',async({page})=>{
  await instrument(page);await page.goto('/');await human(page);await load(page);
  await page.locator('.board2d [data-square="364"]').click();expect((await evidence(page)).starts).toHaveLength(0);
  // Commit the capture and pause in one browser turn, before the real AI reply timer.
  // Separate Playwright round trips can take longer than the 400ms reply delay on WebKit.
  await page.evaluate(async()=>{document.querySelector<HTMLButtonElement>('.board2d [data-square="355"]')!.click();await Promise.resolve();document.querySelector<HTMLButtonElement>('[data-testid="toggle-run"]')!.click();});
  await expect(page.getByTestId('status')).toHaveText('2手目 ☖後手の番');
  await expect(page.getByTestId('toggle-run')).toHaveText('再開');
  await expect.poll(async()=>(await evidence(page)).starts.length).toBe(1);
  await expect.poll(async()=>(await evidence(page)).peak).toBeGreaterThan(0.001);
  expect((await evidence(page)).starts[0]).toBeCloseTo(0.13,3);
  await page.waitForTimeout(180);expect((await evidence(page)).starts).toHaveLength(1);
});
test('a human normal move and a real Easy reply each reach the output once',async({page})=>{
  await instrument(page);await page.goto('/');await human(page);await sliceAt(page,'4');
  await page.locator('.board2d [data-square="382"]').click();await page.locator('.board2d [data-square="373"]').click();
  await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await expect.poll(async()=>(await evidence(page)).peak).toBeGreaterThan(0.001);
  const data=await evidence(page);expect(data.starts).toHaveLength(2);expect(data.starts[0]).toBeCloseTo(0.08,3);expect(data.contexts).toBe(1);
});
test('mute stops playback, persists with volume, and can be enabled again',async({page})=>{
  await instrument(page);await page.goto('/');await page.getByRole('button',{name:'表示設定',exact:true}).click();
  // Toggle off in the same event-loop turn after playback starts, before the 80ms cue ends.
  await page.evaluate(async()=>{Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='テスト音を鳴らす')!.click();await Promise.resolve();document.querySelector<HTMLButtonElement>('.sheet-heading button')!.click();document.querySelector<HTMLButtonElement>('[aria-label="効果音をミュート"]')!.click();});
  expect((await evidence(page)).stops).toBeGreaterThan(0);
  await page.getByRole('button',{name:'表示設定',exact:true}).click();await page.getByLabel('効果音の音量').fill('60');await expect(page.getByRole('button',{name:'テスト音を鳴らす'})).toBeDisabled();
  await page.reload();await expect(page.getByRole('button',{name:'効果音をON'})).toHaveAttribute('aria-pressed','false');
  await page.getByRole('button',{name:'効果音をON'}).click();await page.getByRole('button',{name:'表示設定',exact:true}).click();await expect(page.getByLabel('効果音の音量')).toHaveValue('60');await page.getByRole('button',{name:'テスト音を鳴らす'}).click();await expect.poll(async()=>(await evidence(page)).peak).toBeGreaterThan(0.001);
});
test('import and backward history are silent; explicit forward has only the capture cue',async({page})=>{
  await instrument(page);await page.goto('/');await load(page,true);expect((await evidence(page)).starts).toHaveLength(0);
  await page.getByTestId('undo').click();expect((await evidence(page)).starts).toHaveLength(0);await page.getByTestId('redo').click();
  await expect.poll(async()=>(await evidence(page)).starts.length).toBe(1);expect((await evidence(page)).starts[0]).toBeCloseTo(0.13,3);
  await page.getByTestId('undo').click();expect((await evidence(page)).starts).toHaveLength(1);
});
test('hidden state suppresses sound and returning does not replay its backlog',async({page})=>{
  await instrument(page);await page.goto('/');await page.getByRole('button',{name:'表示設定',exact:true}).click();await page.getByRole('button',{name:'テスト音を鳴らす'}).click();await expect.poll(async()=>(await evidence(page)).starts.length).toBe(1);
  await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
  await page.getByRole('button',{name:'テスト音を鳴らす'}).click();expect((await evidence(page)).starts).toHaveLength(1);
  await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});document.dispatchEvent(new Event('visibilitychange'));});await page.waitForTimeout(180);expect((await evidence(page)).starts).toHaveLength(1);
  await page.getByRole('button',{name:'テスト音を鳴らす'}).click();await expect.poll(async()=>(await evidence(page)).starts.length).toBe(2);
});
test('unavailable audio and denied storage do not prevent human and real Easy AI moves',async({page})=>{
  await instrument(page,true);await page.goto('/');await human(page);await sliceAt(page,'4');
  await page.locator('.board2d [data-square="382"]').click();await page.locator('.board2d [data-square="373"]').click();await expect(page.getByTestId('status')).toHaveText('3手目 ☗先手の番');
  await page.getByRole('button',{name:'効果音をミュート'}).click();await expect(page.getByRole('button',{name:'効果音をON'})).toBeVisible();expect((await evidence(page)).starts).toHaveLength(0);
});
test('cancelling a real search never produces a late move sound',async({page})=>{
  await instrument(page);await page.goto('/');await display(page,'2d');await page.getByTestId('ai-step').click();await expect(page.getByTestId('toggle-run')).toHaveText('思考を中断');await page.getByTestId('toggle-run').click();await page.waitForTimeout(1300);
  await expect(page.getByTestId('status')).toHaveText('1手目 ☗先手の番');expect((await evidence(page)).starts).toHaveLength(0);
});
for(const [width,height] of [[390,844],[768,1024],[1440,900]])test(`sound controls fit ${width}x${height}`,async({page},info)=>{
  await instrument(page);await page.setViewportSize({width:width!,height:height!});await page.goto('/');await display(page,'2d');
  const toggle=page.getByRole('button',{name:'効果音をミュート'}),rect=(await toggle.boundingBox())!;expect(rect.width).toBeGreaterThanOrEqual(44);expect(rect.height).toBeGreaterThanOrEqual(44);expect(rect.x+rect.width).toBeLessThanOrEqual(width!);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'表示設定',exact:true}).click();await expect(page.getByLabel('効果音の音量')).toBeInViewport();
  const shot=info.outputPath(`attachments/sound-controls-${width}.png`);await page.screenshot({path:shot,fullPage:true});await info.attach('sound-controls',{path:shot,contentType:'image/png'});
});
